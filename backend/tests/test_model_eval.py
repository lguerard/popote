"""Évaluation d'un modèle (app/scripts/model_eval) : cas, notes, sortie JSON."""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.scripts.model_eval import __main__ as cli
from app.scripts.model_eval import cases, runner, scoring
from app.services import llm_service

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def recipe(n, **kw):
    base = dict(
        id=uuid.UUID(int=n), title=f"Gratin n°{n}", description="Un gratin.", status="done",
        reextracting=False, shared_by_id=None, servings=4, prep_time=15, cook_time=40,
        category="plat", rating=None, cooked_count=0, cook_again=None,
        created_at=NOW - timedelta(days=n), updated_at=NOW - timedelta(days=n),
        ingredients=[
            {"quantity": "1", "unit": "kg", "name": "pommes de terre", "notes": None},
            {"quantity": "50", "unit": "cl", "name": "lait", "notes": None},
            {"quantity": "2", "unit": None, "name": "gousses d'ail", "notes": "écrasées"},
        ],
        steps=[{"order": 1, "text": "Éplucher les pommes de terre."},
               {"order": 2, "text": "Chauffer le lait avec l'ail."},
               {"order": 3, "text": "Enfourner 40 minutes."}],
        nutrition={"calories": 320, "proteins": 9, "carbs": 45, "fat": 11, "fiber": 4},
    )
    base.update(kw)
    return SimpleNamespace(**base)


# --- notes -------------------------------------------------------------------

def test_perfect_recipe_scores_100_and_partial_answers_get_partial_credit():
    expected = cases._expected_recipe(recipe(1))
    perfect = {
        "title": "Gratin n°1", "servings": 4, "prep_time": 15, "cook_time": 40, "category": "plat",
        "ingredients": [{"quantity": "1", "unit": "kg", "name": "pomme de terre"},
                        {"quantity": "50", "unit": "cl", "name": "lait"},
                        {"quantity": "2", "unit": None, "name": "ail"}],
        "steps": [{"text": "a"}, {"text": "b"}, {"text": "c"}],
    }
    assert scoring.score_recipe(perfect, expected)[0] == 100
    partial = dict(perfect, ingredients=perfect["ingredients"][:1], servings=2, category="dessert")
    score, notes = scoring.score_recipe(partial, expected)
    assert 30 < score < 80
    assert any("ingrédients retrouvés 1/3" in n for n in notes)


def test_no_recipe_scores_zero():
    assert scoring.score_recipe({"error": "Aucune recette trouvée"}, {"title": "x"})[0] == 0


def test_bundled_keyword_cases_are_still_scorable():
    case = cases.load_bundled()["extraction"][0]
    data = {"title": "Pâtes au pesto", "language": "fr", "category": "plat", "servings": 2,
            "ingredients": [{"name": n} for n in ("pâtes", "basilic", "pignons", "ail", "parmesan", "huile d'olive")],
            "steps": [{"text": s} for s in "abcd"]}
    assert scoring.score_recipe(data, case["expected"])[0] == 100


def test_nutrition_tolerance_and_consistency():
    ref = {"calories": 400, "proteins": 20, "carbs": 50, "fat": 13, "fiber": 5}
    assert scoring.score_nutrition(dict(ref), ref)[0] == 100
    off = scoring.score_nutrition({"calories": 520, "proteins": 20, "carbs": 50, "fat": 13, "fiber": 5}, ref)[0]
    assert 50 < off < 100       # 30 % d'écart et calories incohérentes : crédit partiel
    assert scoring.score_nutrition({"calories": None}, ref)[0] == 0
    # La référence n'est qu'une ancienne estimation : 20 % d'écart cohérent = pleine note.
    near = {"calories": 480, "proteins": 24, "carbs": 60, "fat": 15.6, "fiber": 6}
    assert scoring.score_nutrition(near, ref)[0] == 100
    assert scoring.score_nutrition({**near, "calories": 5000}, ref)[0] < 70   # hors bornes, incohérent


def test_inconsistent_reference_is_not_a_nutrition_case():
    good = {"calories": 400, "proteins": 20, "carbs": 50, "fat": 13, "fiber": 5}
    assert cases.nutrition_case(recipe(1, nutrition=good)) is not None
    stale = {"calories": 900, "proteins": 20, "carbs": 50, "fat": 13, "fiber": 5}   # 517 kcal d'après les macros
    assert cases.nutrition_case(recipe(1, nutrition=stale)) is None


def test_description_is_scored_loosely():
    good = scoring.score_description("A golden potato gratin served in a white ceramic dish, topped with melted cheese.")[0]
    assert good == 100
    assert scoring.score_description("")[0] == 0
    french = scoring.score_description("Un gratin doré servi dans un plat blanc avec du fromage fondu.")[0]
    assert 40 <= french < good
    rambling = scoring.score_description(" ".join(["word"] * 120))[0]
    assert rambling < good


def test_similarity_ignores_case_and_accents():
    assert scoring.similarity("Crêpes de Mamie", "crepes de mamie") == 1


# --- cas -----------------------------------------------------------------------

def test_harvest_prefers_validated_then_newest_and_caps():
    pool = [recipe(n) for n in range(1, 21)]
    pool[15].rating = 5                       # ancienne mais notée : en tête
    pool.append(recipe(30, status="failed"))  # jamais retenue
    pool.append(recipe(31, shared_by_id=uuid.uuid4()))
    built, sources = cases.build_cases(pool, max_cases=5, bundled={t: [] for t in cases.TASKS})
    ids = [c["id"] for c in built["extraction"]]
    assert len(ids) == 5
    assert ids[0] == f"recette-{str(uuid.UUID(int=16))[:8]}"
    assert ids[1:] == [f"recette-{str(uuid.UUID(int=n))[:8]}" for n in (1, 2, 3, 4)]
    assert len(built["nutrition"]) == 5 and len(built["description"]) == 5
    assert "base" in sources["extraction"]


def test_harvested_extraction_case_carries_the_saved_recipe():
    case = cases.extraction_case(recipe(7))
    assert "pommes de terre" in case["input"] and "Gratin n°7" in case["input"]
    assert case["expected"]["servings"] == 4 and case["expected"]["steps_count"] == 3
    assert case["expected"]["ingredients"][0] == {"quantity": "1", "unit": "kg", "name": "pommes de terre"}


def test_rendering_is_deterministic():
    assert cases.render_source(recipe(3)) == cases.render_source(recipe(3))
    styles = {cases.render_source(recipe(n))[1] for n in range(1, 30)}
    assert styles == {"page web", "transcription"}


def test_too_few_recipes_fall_back_to_bundled_cases():
    built, sources = cases.build_cases([recipe(1)], max_cases=12)
    assert len(built["extraction"]) == 3
    assert [c["source"] for c in built["extraction"]] == ["db", "bundled", "bundled"]
    assert len(built["photo_recipe"]) == 3 and "photos fournies" in sources["photo_recipe"]
    empty, _ = cases.build_cases([], max_cases=12)
    assert all(len(empty[t]) >= 3 for t in cases.TASKS)


def test_recipe_without_nutrition_is_not_a_nutrition_case():
    assert cases.nutrition_case(recipe(1, nutrition=None)) is None
    assert cases.nutrition_case(recipe(1, nutrition={"calories": 300})) is None


def test_bundled_images_exist():
    for case in cases.load_bundled()["photo_recipe"]:
        assert (cases.HERE / case["image"]).stat().st_size > 10_000


def test_cases_hash_changes_with_the_cases():
    a, _ = cases.build_cases([recipe(1)], 12)
    b, _ = cases.build_cases([recipe(2)], 12)
    assert cases.cases_hash(a) == cases.cases_hash(cases.build_cases([recipe(1)], 12)[0])
    assert cases.cases_hash(a) != cases.cases_hash(b)


def test_load_recipes_reads_through_the_session():
    class FakeResult:
        def scalars(self):
            return SimpleNamespace(all=lambda: [recipe(1)])

    class FakeSession:
        async def execute(self, stmt):
            self.stmt = str(stmt)
            return FakeResult()

    session = FakeSession()
    rows = asyncio.run(cases.load_recipes(session))
    assert len(rows) == 1 and "recipes" in session.stmt


# --- requêtes et sortie --------------------------------------------------------

def test_requests_use_the_production_builders_and_the_given_model():
    built, _ = cases.build_cases([recipe(1)], 12)
    for task in cases.TASKS:
        body = runner.build_request(task, built[task][0], "candidat:9b")
        assert body["model"] == "candidat:9b"
        assert body["think"] is False and body["options"]["temperature"] == 0
        assert body["options"]["num_ctx"] == llm_service.settings.ollama_num_ctx
    assert "images" in runner.build_request("photo_recipe", built["photo_recipe"][0], "m")["messages"][-1]


def _fake_ollama(monkeypatch, reply):
    real = httpx.AsyncClient

    def handler(request):
        body = json.loads(request.content)
        return reply(body)

    monkeypatch.setattr(runner.httpx, "AsyncClient",
                        lambda *a, **kw: real(*a, transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(llm_service, "_schema_supported", True)


def _answer(body):
    system = body["messages"][0]["content"]
    if "nutritionniste" in system:
        content = json.dumps({"calories": 320, "proteins": 9, "carbs": 45, "fat": 11, "fiber": 4})
    elif "text-to-image" in system:
        content = "A golden potato gratin served in a white baking dish."
    else:
        content = json.dumps({"found": True, "title": "Gratin n°1", "ingredients": [
            {"quantity": "1", "unit": "kg", "name": "pommes de terre", "notes": "", "section": ""}],
            "steps": ["a", "b", "c"], "servings": 4, "category": "plat"})
    return httpx.Response(200, json={"message": {"content": content},
                                     "eval_count": 100, "eval_duration": 2_000_000_000})


def _run_cli(monkeypatch, argv, pool):
    async def fake_harvest(max_cases):
        built, sources = cases.build_cases(pool, max_cases)
        return built, sources, []
    monkeypatch.setattr(cli, "harvest", fake_harvest)
    return asyncio.run(cli.main(argv))


def test_cli_output_shape(monkeypatch):
    _fake_ollama(monkeypatch, _answer)
    out = _run_cli(monkeypatch, ["--model", "m:1b", "--max-cases", "4"], [recipe(n) for n in range(1, 6)])
    assert out["app"] == "popote" and out["model"] == "m:1b"
    assert set(out["tasks"]) == set(cases.TASKS)
    for summary in out["tasks"].values():
        assert set(summary) == {"score", "n", "failed", "avg_seconds", "notes"}
        assert 0 <= summary["score"] <= 100 and summary["failed"] == 0
    assert out["tasks"]["extraction"]["n"] == 4
    assert out["tasks"]["nutrition"]["score"] == 100
    assert out["eval_tokens_per_s"] == 50.0
    json.dumps(out)


def test_invalid_json_scores_zero_and_counts_as_failed(monkeypatch):
    _fake_ollama(monkeypatch, lambda body: httpx.Response(200, json={"message": {"content": "pas du json {"}}))
    out = _run_cli(monkeypatch, ["--model", "m"], [])
    assert out["tasks"]["extraction"]["score"] == 0
    assert out["tasks"]["extraction"]["failed"] == 3
    assert out["eval_tokens_per_s"] is None


def test_unreachable_ollama_is_reported_per_case(monkeypatch):
    def down(body):
        raise httpx.ConnectError("refused")
    _fake_ollama(monkeypatch, down)
    out = _run_cli(monkeypatch, ["--model", "m"], [])
    assert all(t["failed"] == t["n"] for t in out["tasks"].values())
    assert "erreur" in out["tasks"]["nutrition"]["notes"][1]


def test_cases_only_never_calls_ollama(monkeypatch):
    def boom(body):
        raise AssertionError("Ollama appelé")
    _fake_ollama(monkeypatch, boom)
    out = _run_cli(monkeypatch, ["--model", "m", "--cases-only", "--max-cases", "2"], [recipe(n) for n in range(1, 9)])
    assert out["cases_only"] is True
    assert {t: v["n"] for t, v in out["tasks"].items()} == {
        "extraction": 2, "photo_recipe": 2, "nutrition": 2, "description": 2}
    assert out["cases_hash"]


def test_model_is_required():
    with pytest.raises(SystemExit):
        asyncio.run(cli.main([]))
