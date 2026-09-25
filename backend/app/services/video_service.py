import asyncio
import gc
import logging
import os
import tempfile
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


def _combine_sources(title: str, transcript: str, description: str) -> str:
    """Titre, transcription et légende du post en un seul texte pour le LLM.

    Beaucoup de reels recette (Instagram, TikTok) n'ont pas de narration :
    la recette est dans la légende, ou affichée à l'écran (texte incrusté,
    non extrait ici).
    """
    parts = []
    if title.strip():
        parts.append(f"Titre de la vidéo : {title.strip()}")
    if transcript.strip():
        parts.append(f"Transcription de la vidéo :\n{transcript.strip()}")
    if description.strip():
        parts.append(f"Légende de la publication :\n{description.strip()}")
    return "\n\n".join(parts)


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
    return _combine_sources(title, transcript, description), thumbnail
