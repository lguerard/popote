import asyncio
import gc
import logging
import os
import tempfile
import yt_dlp
from faster_whisper import WhisperModel
from ..config import settings

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


def _transcribe(wav_file: str) -> str:
    model, on_gpu = _load_whisper()
    try:
        segments, _ = model.transcribe(wav_file, beam_size=5)
        # Materialize the generator before releasing the model
        return " ".join(seg.text for seg in segments).strip()
    finally:
        if on_gpu:
            del model
            gc.collect()


def _download_and_transcribe_sync(url: str) -> tuple[str, str | None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": audio_path,
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                    "preferredquality": "0",
                }
            ],
        }

        info = {}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # Find downloaded wav
        wav_file = None
        for f in os.listdir(tmpdir):
            if f.endswith(".wav"):
                wav_file = os.path.join(tmpdir, f)
                break

        if not wav_file:
            raise RuntimeError("Téléchargement audio échoué")

        transcript = _transcribe(wav_file)
        thumbnail_url = info.get("thumbnail") or None

        return transcript, thumbnail_url


async def download_and_transcribe(url: str) -> tuple[str, str | None]:
    """Returns (transcription_text, thumbnail_url).

    yt-dlp and Whisper are blocking; run them in a worker thread so the
    event loop (and every other API request) stays responsive.
    """
    return await asyncio.to_thread(_download_and_transcribe_sync, url)
