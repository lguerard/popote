import sys
import types
from pathlib import Path

# `app.*` importable sans installer le backend comme paquet.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _stub_if_missing(name: str, **attrs) -> None:
    """Remplace une dépendance lourde absente (Chromium, Whisper…) par un module vide.

    Les tests ne touchent qu'à la logique de décision et de parsing ; ils
    doivent tourner avec quelques paquets purs Python, sans installer
    Playwright, yt-dlp ni faster-whisper.
    """
    try:
        __import__(name)
    except ImportError:
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        sys.modules[name] = module


_stub_if_missing("playwright")
_stub_if_missing("playwright.async_api", async_playwright=None)
_stub_if_missing("yt_dlp", YoutubeDL=None)
_stub_if_missing("faster_whisper", WhisperModel=object)
