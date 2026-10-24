"""Surveillance des modèles : familles, tailles essayées et estimation de VRAM."""

from app.scripts.model_watch import candidates

GIB = 1024 ** 3


def test_new_families_and_size_tags_are_watched():
    assert {"gemma4", "qwen3.5"} <= set(candidates.CURATED_FAMILIES)
    assert {"4b", "e4b", "12b"} <= set(candidates.CANDIDATE_SIZE_TAGS)


def _best(name, budget):
    model, size = candidates.find_best_fitting_tag(name, budget)
    return model, round(size, 1)


def _fake_manifests(monkeypatch, sizes_gb):
    def fake(name, tag):
        size = sizes_gb.get(f"{name}:{tag}")
        return None if size is None else int(size * GIB)

    monkeypatch.setattr(candidates, "_manifest_size_bytes", fake)


def test_an_8_gb_model_fits_a_10_gb_card(monkeypatch):
    monkeypatch.delenv("MODEL_WATCH_VRAM_BUDGET_GB", raising=False)
    _fake_manifests(monkeypatch, {"gemma4:e4b": 3.0, "gemma4:12b": 8.1, "gemma4:27b": 17.0})
    budget = candidates.vram_budget_gb(10.0)
    assert _best("gemma4", budget) == ("gemma4:12b", 8.1)


def test_a_9_gb_model_still_does_not_fit(monkeypatch):
    monkeypatch.delenv("MODEL_WATCH_VRAM_BUDGET_GB", raising=False)
    _fake_manifests(monkeypatch, {"qwen2.5:7b": 4.7, "qwen2.5:14b": 9.0})
    budget = candidates.vram_budget_gb(10.0)
    assert _best("qwen2.5", budget) == ("qwen2.5:7b", 4.7)


def test_budget_can_be_set_explicitly_for_a_shared_card(monkeypatch):
    monkeypatch.setenv("MODEL_WATCH_VRAM_BUDGET_GB", "6")
    assert candidates.vram_budget_gb(10.0) == 6.0
    _fake_manifests(monkeypatch, {"gemma4:e4b": 3.0, "gemma4:12b": 8.1})
    assert _best("gemma4", 6.0) == ("gemma4:e4b", 3.0)


def test_estimate_counts_context_once():
    assert 8.5 < candidates.estimated_vram_gb(8.1) < 9.5
