import os
import tempfile
import yt_dlp
from faster_whisper import WhisperModel
from ..config import settings

_whisper_model: WhisperModel | None = None


def get_whisper() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type="float16" if settings.whisper_device == "cuda" else "int8",
        )
    return _whisper_model


async def download_and_transcribe(url: str) -> tuple[str, str | None]:
    """Returns (transcription_text, thumbnail_url)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.%(ext)s")
        thumbnail_path = os.path.join(tmpdir, "thumb")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": audio_path,
            "writethumbnail": True,
            "outtmpl_thumbnail": thumbnail_path,
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

        # Transcribe
        model = get_whisper()
        segments, _ = model.transcribe(wav_file, beam_size=5)
        transcript = " ".join(seg.text for seg in segments).strip()

        # Thumbnail
        thumbnail_url = info.get("thumbnail") or None

        return transcript, thumbnail_url
