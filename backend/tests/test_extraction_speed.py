import asyncio

from app.api.extract import StepTracker
from app.services import video_service


class _FakeWhisper:
    fail_cuda_with = None

    def __init__(self, name, device, compute_type):
        if device == "cuda" and self.fail_cuda_with:
            raise RuntimeError(self.fail_cuda_with)
        self.name, self.device = name, device


def _reset(monkeypatch, error):
    _FakeWhisper.fail_cuda_with = error
    monkeypatch.setattr(video_service, "WhisperModel", _FakeWhisper)
    monkeypatch.setattr(video_service, "_cuda_unavailable", False)
    monkeypatch.setattr(video_service, "_cpu_whisper_model", None)
    monkeypatch.setattr(video_service.settings, "whisper_device", "cuda")


def test_full_gpu_falls_back_to_small_cpu_model_for_this_run_only(monkeypatch):
    _reset(monkeypatch, "CUDA failed with error out of memory")
    model, on_gpu = video_service._load_whisper()
    assert not on_gpu and model.name == video_service.settings.whisper_cpu_model
    assert video_service._cuda_unavailable is False

    _FakeWhisper.fail_cuda_with = None
    model, on_gpu = video_service._load_whisper()
    assert on_gpu and model.name == video_service.settings.whisper_model


def test_missing_cuda_libraries_disable_the_gpu_for_good(monkeypatch):
    _reset(monkeypatch, "Library libcublas.so.12 is not found")
    _, on_gpu = video_service._load_whisper()
    assert not on_gpu and video_service._cuda_unavailable is True


def test_ollama_is_unloaded_before_whisper_on_gpu(monkeypatch):
    from app.services import llm_service

    calls = []

    async def fake_unload():
        calls.append("unload")

    monkeypatch.setattr(llm_service, "unload_ollama_model", fake_unload)
    _reset(monkeypatch, None)
    asyncio.run(video_service._free_gpu_for_whisper())
    assert calls == ["unload"]

    monkeypatch.setattr(video_service.settings, "whisper_device", "cpu")
    asyncio.run(video_service._free_gpu_for_whisper())
    assert calls == ["unload"]


def test_timeout_message_names_the_stuck_step():
    steps = StepTracker("réextraction https://exemple.fr")
    steps.record("Lecture des informations de la vidéo…")
    steps.record("Transcription de l'audio de la vidéo…")
    message = steps.timeout_message("Réextraction", "la recette n'a pas été modifiée.")
    assert message == (
        "Réextraction trop longue (plus de 5 minutes), bloquée à l'étape "
        "« Transcription de l'audio de la vidéo » : la recette n'a pas été modifiée."
    )
    assert StepTracker("x").timeout_message() == "Extraction trop longue (plus de 5 minutes) : abandonnée."
