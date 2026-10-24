import asyncio
import gc
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Awaitable, Callable

import yt_dlp
from faster_whisper import WhisperModel

from ..config import settings
from . import recipe_parsing

logger = logging.getLogger(__name__)

# Whisper n'est jamais gardé sur le GPU entre deux vidéos : sur une carte de
# 10 Go partagée (Ollama, génération d'image, autres services), il est
# chargé à la demande et libéré dès la fin de la transcription, l'analyse
# de la recette par Ollama arrivant juste après. Sur CPU (RAM, pas VRAM),
# le modèle est gardé WHISPER_IDLE_UNLOAD_SECONDS après le dernier usage
# (rechargement lent), puis libéré lui aussi.
_cpu_whisper_model: WhisperModel | None = None
_cpu_model_lock = threading.Lock()
_cpu_unload_timer: threading.Timer | None = None

# Set once the GPU has failed to load: every later transcription goes
# straight to CPU instead of raising the same error again.
_cuda_unavailable = False


def _load_cpu_whisper() -> WhisperModel:
    global _cpu_whisper_model
    with _cpu_model_lock:
        _cancel_cpu_unload()
        if _cpu_whisper_model is None:
            # Modèle plus petit sur CPU : large-v3 y transcrit à peine plus vite
            # que le temps réel, un reel de 2 minutes suffisait à faire dépasser
            # le délai de 5 minutes de l'extraction.
            _cpu_whisper_model = WhisperModel(
                settings.whisper_cpu_model,
                device="cpu",
                compute_type="int8",
            )
        return _cpu_whisper_model


def _cancel_cpu_unload() -> None:
    global _cpu_unload_timer
    if _cpu_unload_timer is not None:
        _cpu_unload_timer.cancel()
        _cpu_unload_timer = None


def _release_cpu_whisper() -> None:
    global _cpu_whisper_model
    with _cpu_model_lock:
        _cancel_cpu_unload()
        if _cpu_whisper_model is None:
            return
        _cpu_whisper_model = None
    gc.collect()
    logger.info("Modèle Whisper CPU libéré (inutilisé)")


def _schedule_cpu_unload() -> None:
    """Libère le modèle CPU après WHISPER_IDLE_UNLOAD_SECONDS sans transcription."""
    global _cpu_unload_timer
    delay = settings.whisper_idle_unload_seconds
    if delay <= 0:
        _release_cpu_whisper()
        return
    with _cpu_model_lock:
        _cancel_cpu_unload()
        _cpu_unload_timer = threading.Timer(delay, _release_cpu_whisper)
        _cpu_unload_timer.daemon = True
        _cpu_unload_timer.start()


def _release_gpu_whisper(model) -> None:
    """Rend la VRAM tout de suite, sans attendre le ramasse-miettes."""
    try:
        # CTranslate2 libère les poids sur le GPU ; del seul attendait que
        # plus rien ne référence le modèle (traceback d'une exception…).
        model.model.unload_model()
    except Exception:
        logger.debug("unload_model indisponible pour Whisper", exc_info=True)
    del model
    gc.collect()


def _is_out_of_memory(exc: Exception) -> bool:
    return "out of memory" in str(exc).lower()


def _load_whisper() -> tuple[WhisperModel, bool]:
    """Load Whisper, on GPU when asked for and actually usable.

    Returns
    -------
    tuple[WhisperModel, bool]
        The model, and whether it sits on the GPU (hence must be freed
        after use).
    """
    global _cuda_unavailable
    if settings.whisper_device != "cuda" or _cuda_unavailable:
        return _load_cpu_whisper(), False
    try:
        return WhisperModel(
            settings.whisper_model,
            device="cuda",
            # int8_float16 : poids en 8 bits, calculs en fp16. Moitié moins de
            # VRAM que float16 pour une transcription équivalente.
            compute_type=settings.whisper_compute_type,
        ), True
    except Exception as exc:
        # Missing libcublas/libcudnn in the image, driver too old, VRAM
        # already taken by Ollama... None of it should turn a video
        # import into a hard failure: fall back to CPU, slower but
        # working, and say so loudly enough to be fixed. A full GPU is
        # temporary (Ollama is unloaded before each transcription, see
        # video_to_text): only a real CUDA problem disables it for good.
        if not _is_out_of_memory(exc):
            _cuda_unavailable = True
        logger.warning(
            "Whisper could not start on GPU (%s) — falling back to CPU (%s)%s.",
            exc, settings.whisper_cpu_model,
            "" if _is_out_of_memory(exc) else " until the next restart",
        )
        return _load_cpu_whisper(), False


def _transcribe(audio_file: str) -> str:
    model, on_gpu = _load_whisper()
    try:
        # vad_filter : saute le silence et la musique, qui font l'essentiel
        # d'un reel sans narration — plus rapide, et Whisper n'y invente plus
        # de phrases. beam_size=1 (décodage glouton) : ~2x plus rapide sur
        # CPU, largement assez précis pour que le LLM en tire la recette.
        try:
            segments, _ = model.transcribe(
                audio_file, beam_size=1, vad_filter=True, condition_on_previous_text=False,
            )
            # Materialize the generator before releasing the model
            return " ".join(seg.text for seg in segments).strip()
        except ValueError as exc:
            # faster-whisper (encore en 1.1.1) : quand le filtre VAD ne garde
            # aucune parole (reel en musique seule), la détection de langue
            # appelle max() sur une liste vide. Aucune parole = transcription
            # vide, pas une erreur. Le message dépend de la version de Python.
            if "empty sequence" not in str(exc) and "iterable argument is empty" not in str(exc):
                raise
            logger.info("Aucune parole détectée dans %s", audio_file)
            return ""
    finally:
        if on_gpu:
            _release_gpu_whisper(model)
        else:
            del model
            _schedule_cpu_unload()


def _combine_sources(
    title: str, transcript: str, description: str, on_screen: str = "",
) -> str:
    """Titre, transcription et légende du post en un seul texte pour le LLM.

    Beaucoup de reels recette (Instagram, TikTok) n'ont pas de narration :
    la recette est dans la légende, ou affichée à l'écran (texte incrusté,
    lu par OCR, voir _ocr_video_text).
    """
    parts = []
    if title.strip():
        parts.append(f"Titre de la vidéo : {title.strip()}")
    if transcript.strip():
        parts.append(f"Transcription de la vidéo :\n{transcript.strip()}")
    if description.strip():
        parts.append(f"Légende de la publication :\n{description.strip()}")
    if on_screen.strip():
        parts.append(f"Texte affiché à l'écran pendant la vidéo :\n{on_screen.strip()}")
    return "\n\n".join(parts)


# ── Texte incrusté (OCR des images de la vidéo) ─────────────────────────────
# Une image toutes les 2 s suffit : un texte incrusté reste affiché le temps
# d'être lu. Plafonné pour qu'un long reel ne coûte pas plusieurs minutes.
_OCR_FRAME_INTERVAL_SECONDS = 2
_OCR_MAX_FRAMES = 45
_OCR_MAX_DURATION_SECONDS = 600
# En dessous, Tesseract lit surtout des motifs du décor comme des lettres.
_OCR_MIN_WORD_CONFIDENCE = 60


def _fold_line(line: str) -> str:
    folded = recipe_parsing._fold(line).replace("œ", "oe").replace("æ", "ae")
    return re.sub(r"[^a-z0-9]+", " ", folded).strip()


def merge_ocr_lines(frame_texts: list[str]) -> str:
    """Fusionne le texte lu sur chaque image en supprimant les répétitions.

    Un même texte reste affiché sur plusieurs images consécutives : sans
    dédoublonnage, chaque ingrédient apparaîtrait cinq ou six fois. Les
    lignes trop courtes ou sans lettres (bruit d'OCR sur le décor) sont
    écartées ; une ligne déjà vue, ou contenue dans une ligne déjà vue
    (texte qui apparaît mot à mot), n'est pas répétée.
    """
    kept: list[str] = []
    seen: list[str] = []
    for text in frame_texts:
        for raw in text.splitlines():
            line = " ".join(raw.split())
            folded = _fold_line(line)
            letters = sum(c.isalpha() for c in folded)
            if len(folded) < 3 or letters < 3 or letters < len(folded.replace(" ", "")) * 0.5:
                continue
            if any(folded in other for other in seen):
                continue
            # Version plus complète d'une ligne gardée (texte animé qui
            # s'écrit progressivement) : elle remplace l'ancienne.
            for i, other in enumerate(seen):
                if other in folded:
                    seen[i], kept[i] = folded, line
                    break
            else:
                seen.append(folded)
                kept.append(line)
    return "\n".join(kept)


def _ocr_frame(path: str) -> str:
    import pytesseract
    from PIL import Image, ImageOps

    with Image.open(path) as img:
        gray = ImageOps.grayscale(img)
        data = pytesseract.image_to_data(
            gray, lang="fra+eng", output_type=pytesseract.Output.DICT,
        )
    lines: dict[tuple, list[str]] = {}
    for i, word in enumerate(data["text"]):
        word = word.strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if not word or conf < _OCR_MIN_WORD_CONFIDENCE:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
    return "\n".join(" ".join(words) for words in lines.values())


def _ocr_video_text(url: str) -> str:
    """Texte incrusté dans la vidéo : images extraites par ffmpeg, lues par Tesseract."""
    with tempfile.TemporaryDirectory() as tmpdir:
        opts = {
            **_ydl_base(),
            # Basse définition : le texte incrusté est gros, et une vidéo
            # 480p se télécharge et se décode bien plus vite.
            "format": "bv*[height<=720][ext=mp4]/b[height<=720]/bv*/b/worst",
            "outtmpl": os.path.join(tmpdir, "video.%(ext)s"),
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
        videos = [
            os.path.join(tmpdir, f) for f in os.listdir(tmpdir)
            if f.startswith("video.") and not f.endswith(".part")
        ]
        if not videos:
            return ""
        frames_dir = os.path.join(tmpdir, "frames")
        os.makedirs(frames_dir)
        subprocess.run(
            [
                "ffmpeg", "-loglevel", "error", "-i", videos[0],
                "-vf", f"fps=1/{_OCR_FRAME_INTERVAL_SECONDS},scale=720:-2",
                "-frames:v", str(_OCR_MAX_FRAMES),
                os.path.join(frames_dir, "f%03d.png"),
            ],
            check=True, timeout=120,
        )
        frames = sorted(os.path.join(frames_dir, f) for f in os.listdir(frames_dir))
        # Tesseract tourne en sous-processus : quelques threads suffisent à
        # occuper plusieurs cœurs.
        with ThreadPoolExecutor(max_workers=4) as pool:
            texts = list(pool.map(_ocr_frame, frames))
    return merge_ocr_lines(texts)


def _ydl_base() -> dict:
    """Options yt-dlp communes : quelques nouvelles tentatives sur les
    erreurs réseau, et les cookies d'un compte s'ils sont fournis (Instagram
    exige de plus en plus souvent une connexion, voir DEPLOIEMENT.md)."""
    opts = {
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "retries": 3, "extractor_retries": 2, "socket_timeout": 20,
    }
    cookies = _cookies_copy()
    if cookies:
        opts["cookiefile"] = cookies
    return opts


def _cookies_copy() -> str | None:
    """Copie des cookies du compte fournis (cookies/cookies.txt), s'il y en a.

    Copie : yt-dlp et gallery-dl réécrivent leur fichier de cookies en
    sortant, alors que celui fourni est monté en lecture seule.
    """
    cookies = settings.ytdlp_cookies_file
    if not cookies or not os.path.isfile(cookies):
        return None
    copy = os.path.join(tempfile.gettempdir(), "popote-ytdlp-cookies.txt")
    shutil.copyfile(cookies, copy)
    return copy


# ── Posts en images (carrousel Instagram, mode photo TikTok) ─────────────────
# La recette y est souvent écrite sur les images elles-mêmes, que yt-dlp ne
# sait pas récupérer : gallery-dl (https://github.com/mikf/gallery-dl) le fait,
# et l'OCR des vidéos (_ocr_frame) les lit.
_POST_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
_MAX_POST_IMAGES = 20


def _natural_key(name: str) -> list:
    """« img_2 » avant « img_10 » : l'ordre des images du carrousel."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def post_images_text(url: str) -> str:
    """Texte écrit sur les images d'un post, dans l'ordre ; "" si rien de lisible."""
    exe = shutil.which("gallery-dl")
    if not exe:
        return ""
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            exe, "--quiet", "--no-part", "--no-mtime", "-D", tmpdir,
            "--range", f"1-{_MAX_POST_IMAGES}",
            "--filter", "extension in ('jpg', 'jpeg', 'png', 'webp')",
        ]
        cookies = _cookies_copy()
        if cookies:
            cmd += ["--cookies", cookies]
        try:
            subprocess.run(cmd + [url], capture_output=True, timeout=120, check=False)
        except (subprocess.TimeoutExpired, OSError):
            logger.warning("Images du post %s non récupérées", url, exc_info=True)
        images = sorted(
            (f for f in os.listdir(tmpdir) if f.lower().endswith(_POST_IMAGE_EXTENSIONS)),
            key=_natural_key,
        )
        if not images:
            return ""
        with ThreadPoolExecutor(max_workers=4) as pool:
            texts = list(pool.map(_ocr_frame, (os.path.join(tmpdir, f) for f in images)))
    return merge_ocr_lines(texts)


def _fetch_info(url: str) -> dict:
    with yt_dlp.YoutubeDL({**_ydl_base(), "skip_download": True}) as ydl:
        return ydl.extract_info(url, download=False) or {}


def _pick_subtitle_track(info: dict) -> tuple[str, bool] | None:
    """(langue, automatique ?) du meilleur sous-titre, ou None.

    Priorité aux sous-titres écrits par l'auteur, puis aux automatiques dans
    la langue d'origine : les pistes automatiques « traduites » que YouTube
    propose dans toutes les langues sont de piètre qualité.
    """
    def first(tracks, prefixes):
        for prefix in prefixes:
            for lang in tracks:
                if lang.lower() == prefix or lang.lower().startswith(prefix + "-"):
                    return lang
        return None

    manual = {k: v for k, v in (info.get("subtitles") or {}).items() if k != "live_chat"}
    lang = first(manual, ["fr", "en"]) or next(iter(manual), None)
    if lang:
        return lang, False
    auto = info.get("automatic_captions") or {}
    original = [lang for lang in auto if lang.endswith("-orig")]
    if original:
        return original[0], True
    prefixes = [p for p in ((info.get("language") or "").lower(), "fr", "en") if p]
    lang = first(auto, prefixes)
    return (lang, True) if lang else None


def _fetch_subtitles(url: str, info: dict) -> str:
    track = _pick_subtitle_track(info)
    if not track:
        return ""
    lang, automatic = track
    with tempfile.TemporaryDirectory() as tmpdir:
        opts = {
            **_ydl_base(),
            "skip_download": True,
            "writesubtitles": not automatic,
            "writeautomaticsub": automatic,
            "subtitleslangs": [lang],
            "subtitlesformat": "vtt/srt/best",
            "outtmpl": os.path.join(tmpdir, "subs.%(ext)s"),
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info(url, download=True)
        except Exception:
            logger.warning("Sous-titres indisponibles pour %s", url, exc_info=True)
            return ""
        for name in os.listdir(tmpdir):
            if name.endswith((".vtt", ".srt")):
                with open(os.path.join(tmpdir, name), encoding="utf-8", errors="replace") as fh:
                    text = recipe_parsing.subtitles_to_text(fh.read())
                return text if len(text) >= 50 else ""
    return ""


def _download_audio_and_transcribe(url: str) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        # Pas de conversion WAV via ffmpeg : faster-whisper décode directement
        # m4a/webm/mp4, la conversion ne faisait que coûter du temps.
        opts = {
            **_ydl_base(),
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": os.path.join(tmpdir, "audio.%(ext)s"),
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
        files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if not f.endswith(".part")]
        if not files:
            raise RuntimeError("Téléchargement audio échoué")
        return _transcribe(max(files, key=os.path.getsize))


async def _noop_progress(_message: str) -> None:
    pass


async def _free_gpu_for_whisper() -> None:
    """Décharge le modèle Ollama pour que Whisper tienne sur le GPU.

    Ollama (gardé chargé, OLLAMA_KEEP_ALIVE) occupe presque toute la VRAM : Whisper
    ne pouvait jamais y charger et transcrivait sur CPU, plusieurs fois
    plus lentement. Ollama recharge son modèle tout seul à l'étape suivante
    (analyse de la recette), en quelques secondes.
    """
    if settings.whisper_device != "cuda" or _cuda_unavailable or not settings.whisper_free_gpu:
        return
    from .llm_service import unload_ollama_model
    try:
        await unload_ollama_model()
    except Exception:
        logger.warning("Impossible de libérer le GPU d'Ollama avant Whisper", exc_info=True)


async def video_to_text(
    url: str, progress: Callable[[str], Awaitable[None]] | None = None
) -> tuple[str, str | None]:
    """(texte pour le LLM, vignette) d'une vidéo, par la voie la plus rapide.

    1. Légende contenant déjà ingrédients ET étapes : aucun téléchargement.
    2. Sous-titres (auteur ou automatiques) : quelques Ko au lieu de l'audio.
    3. Sinon, audio + Whisper, de loin l'étape la plus lente.

    yt-dlp et Whisper sont bloquants : chaque étape tourne dans un thread
    pour que la boucle d'événements (et les autres requêtes) reste libre.
    """
    progress = progress or _noop_progress
    info = await asyncio.to_thread(_fetch_info, url)
    title = info.get("title") or ""
    description = info.get("description") or ""
    thumbnail = info.get("thumbnail") or None

    if recipe_parsing.has_full_recipe(description):
        logger.info("vidéo %s : recette complète dans la légende, transcription sautée", url)
        return _combine_sources(title, "", description), thumbnail

    await progress("Récupération des sous-titres de la vidéo…")
    transcript = await asyncio.to_thread(_fetch_subtitles, url, info)
    if transcript:
        logger.info("vidéo %s : sous-titres utilisés", url)
    else:
        await progress("Transcription de l'audio de la vidéo…")
        await _free_gpu_for_whisper()
        try:
            transcript = await asyncio.to_thread(_download_audio_and_transcribe, url)
            logger.info("vidéo %s : audio transcrit par Whisper", url)
        except Exception:
            # L'audio n'est qu'une des sources : la légende et le texte affiché
            # à l'écran peuvent suffire. Un échec de Whisper ne doit pas faire
            # échouer toute l'extraction.
            logger.warning("Transcription impossible pour %s", url, exc_info=True)
            transcript = ""

    combined = _combine_sources(title, transcript, description)
    duration = info.get("duration") or 0
    if recipe_parsing.has_full_recipe(combined) or duration > _OCR_MAX_DURATION_SECONDS:
        return combined, thumbnail

    # Reel sans narration ni légende détaillée : la recette est souvent
    # écrite à l'écran. Un échec ici ne doit pas faire perdre ce qu'on a déjà.
    await progress("Lecture du texte affiché dans la vidéo…")
    try:
        on_screen = await asyncio.to_thread(_ocr_video_text, url)
    except Exception:
        logger.warning("OCR de la vidéo %s impossible", url, exc_info=True)
        on_screen = ""
    if on_screen:
        logger.info("vidéo %s : %d lignes de texte incrusté lues", url, on_screen.count("\n") + 1)
    return _combine_sources(title, transcript, description, on_screen), thumbnail
