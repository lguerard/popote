import asyncio
import gc
import os
import tempfile
import yt_dlp
from faster_whisper import WhisperModel
from ..config import settings

# Cache the model only on CPU. On CUDA the model is freed after each
# transcription: Whisper large-v3 (~5 GB) + the Ollama LLM (~9 GB) do not
# fit together on a 10 GB GPU, so keeping it resident causes OOM.
_cpu_whisper_model: WhisperModel | None = None


def _load_whisper() -> WhisperModel:
    global _cpu_whisper_model
    if settings.whisper_device != "cuda":
        if _cpu_whisper_model is None:
            _cpu_whisper_model = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type="int8",
            )
        return _cpu_whisper_model
    return WhisperModel(
        settings.whisper_model,
        device="cuda",
        compute_type="float16",
    )


def _transcribe(wav_file: str) -> str:
    model = _load_whisper()
    try:
        segments, _ = model.transcribe(wav_file, beam_size=5)
        # Materialize the generator before releasing the model
        return " ".join(seg.text for seg in segments).strip()
    finally:
        if settings.whisper_device == "cuda":
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
