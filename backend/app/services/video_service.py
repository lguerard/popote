import asyncio
import gc
import logging
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Awaitable, Callable

import yt_dlp
from faster_whisper import WhisperModel

from ..config import settings
from . import recipe_parsing

logger = logging.getLogger(__name__)

# Cache the model only on CPU. On CUDA the model is freed after each
# transcription: Whisper large-v3 (~5 GB) + the Ollama LLM (~9 GB) do not
# fit together on a 10 GB GPU, so keeping it resident causes OOM.
_cpu_whisper_model: WhisperModel | None = None

# Set once the GPU has failed to load: every later transcription goes
# straight to CPU instead of raising the same error again.
_cuda_unavailable = False


def _load_cpu_whisper() -> WhisperModel:
    global _cpu_whisper_model
    if _cpu_whisper_model is None:
        _cpu_whisper_model = WhisperModel(
            settings.whisper_model,
            device="cpu",
            compute_type="int8",
        )
    return _cpu_whisper_model


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
            compute_type="float16",
        ), True
    except Exception as exc:
        # Missing libcublas/libcudnn in the image, driver too old, VRAM
        # already taken by Ollama... None of it should turn a video
        # import into a hard failure: fall back to CPU, slower but
        # working, and say so loudly enough to be fixed.
        _cuda_unavailable = True
        logger.warning(
            "Whisper could not start on GPU (%s) — falling back to CPU "
            "for this run. Transcription will be much slower.", exc,
        )
        return _load_cpu_whisper(), False


def _transcribe(audio_file: str) -> str:
    model, on_gpu = _load_whisper()
    try:
        # vad_filter : saute le silence et la musique, qui font l'essentiel
        # d'un reel sans narration — plus rapide, et Whisper n'y invente plus
        # de phrases. beam_size=1 (décodage glouton) : ~2x plus rapide sur
        # CPU, largement assez précis pour que le LLM en tire la recette.
        segments, _ = model.transcribe(
            audio_file, beam_size=1, vad_filter=True, condition_on_previous_text=False,
        )
        # Materialize the generator before releasing the model
        return " ".join(seg.text for seg in segments).strip()
    finally:
        if on_gpu:
            del model
            gc.collect()


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
            **_YDL_BASE,
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


_YDL_BASE = {"quiet": True, "no_warnings": True, "noplaylist": True}


def _fetch_info(url: str) -> dict:
    with yt_dlp.YoutubeDL({**_YDL_BASE, "skip_download": True}) as ydl:
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
            **_YDL_BASE,
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
            **_YDL_BASE,
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
        transcript = await asyncio.to_thread(_download_audio_and_transcribe, url)
        logger.info("vidéo %s : audio transcrit par Whisper", url)

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
