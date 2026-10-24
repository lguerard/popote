import asyncio

from app.services.extraction_steps import StepTracker
from app.services import video_service


class _FakeWhisper:
    fail_cuda_with = None

    def __init__(self, name, device, compute_type):
        if device == "cuda" and self.fail_cuda_with:
            raise RuntimeError(self.fail_cuda_with)
        self.name, self.device, self.compute_type = name, device, compute_type


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


def test_gpu_whisper_uses_turbo_in_int8_float16_by_default(monkeypatch):
    _reset(monkeypatch, None)
    assert video_service.settings.whisper_model == "large-v3-turbo"
    model, on_gpu = video_service._load_whisper()
    assert on_gpu and model.compute_type == "int8_float16"


class _Segment:
    text = "bonjour"


class _TranscribingModel:
    def __init__(self):
        self.unloaded = False
        outer = self

        class _Ct2:
            def unload_model(self):
                outer.unloaded = True

        self.model = _Ct2()

    def transcribe(self, *args, **kwargs):
        return [_Segment()], None


def test_gpu_whisper_is_released_right_after_the_job(monkeypatch):
    model = _TranscribingModel()
    monkeypatch.setattr(video_service, "_load_whisper", lambda: (model, True))
    assert video_service._transcribe("audio.m4a") == "bonjour"
    assert model.unloaded


def test_cpu_whisper_is_released_when_idle(monkeypatch):
    _reset(monkeypatch, None)
    monkeypatch.setattr(video_service.settings, "whisper_device", "cpu")
    monkeypatch.setattr(video_service.settings, "whisper_idle_unload_seconds", 0)
    monkeypatch.setattr(video_service, "_cpu_unload_timer", None)
    model, on_gpu = video_service._load_whisper()
    assert not on_gpu and video_service._cpu_whisper_model is model
    video_service._schedule_cpu_unload()
    assert video_service._cpu_whisper_model is None

    monkeypatch.setattr(video_service.settings, "whisper_idle_unload_seconds", 300)
    video_service._load_whisper()
    video_service._schedule_cpu_unload()
    timer = video_service._cpu_unload_timer
    assert timer is not None and timer.interval == 300
    assert video_service._cpu_whisper_model is not None  # gardé pendant le délai
    video_service._load_whisper()  # réutilisé : le délai repart de zéro
    assert video_service._cpu_unload_timer is None and timer.finished.is_set()
    video_service._release_cpu_whisper()


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


def test_offload_ratio_from_ollama_ps():
    from app.services import llm_service

    ps = {"models": [
        {"name": "qwen2.5:14b", "size": 11_000_000_000, "size_vram": 8_800_000_000},
        {"name": "llava:latest", "size": 5, "size_vram": 5},
    ]}
    assert round(llm_service.offload_ratio(ps, "qwen2.5:14b"), 2) == 0.2
    assert llm_service.offload_ratio(ps, "llava") == 0
    assert llm_service.offload_ratio(ps, "qwen2.5:7b") is None


def test_timeout_message_explains_an_offloaded_model(monkeypatch):
    from app.services import llm_service

    monkeypatch.setattr(llm_service, "cpu_offload_ratio", 0.2)
    hint = llm_service.offload_hint()
    assert "20% tourne sur le processeur" in hint
    # Nomme le modèle en cause et propose le repli léger, texte seul.
    assert llm_service.settings.ollama_model in hint and "OLLAMA_MODEL=qwen2.5:7b" in hint
    steps = StepTracker("x")
    steps.record("Analyse de la recette par l'IA…")
    assert steps.timeout_message(hint=hint).endswith(hint)

    monkeypatch.setattr(llm_service, "cpu_offload_ratio", 0.0)
    assert llm_service.offload_hint() == ""
