"""Partage entre comptes (copie) et export vers MyFitnessPal (schema.org)."""

import json
import re
import uuid
from types import SimpleNamespace

from app.services import image_service, recipe_export, sharing


def _recipe(**kw):
    base = dict(
        id=uuid.uuid4(), origin_recipe_id=None, title="Crêpes", description="Fines.",
        source_url="https://ex.fr", source_type="web", language="fr", servings=4,
        prep_time=10, cook_time=20, category="dessert", tags=["facile"], nutrition=None,
        ingredients=[{"quantity": "250", "unit": "g", "name": "farine", "notes": "tamisée"},
                     {"quantity": "3", "unit": None, "name": "œufs", "notes": None}],
        steps=[{"order": 1, "text": "Mélanger."}, {"order": 2, "text": "Cuire."}],
        thumbnail_url="/media/recipes/x.png", is_favorite=True, notes="perso", rating=5,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_copy_keeps_the_content_but_not_personal_data():
    fields = sharing.copy_fields(_recipe())
    assert fields["title"] == "Crêpes" and fields["ingredients"][0]["name"] == "farine"
    assert not {"is_favorite", "notes", "rating", "share_token", "thumbnail_url"} & fields.keys()


def test_copy_of_a_copy_points_to_the_original():
    original = _recipe()
    copy = _recipe(origin_recipe_id=original.id)
    assert sharing.origin_of(original) == original.id
    assert sharing.origin_of(copy) == original.id


def test_local_thumbnail_is_duplicated(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "media_dir", str(tmp_path))
    url = image_service.save_thumbnail_bytes("a", b"img", "png")
    copy = image_service.copy_local_thumbnail(url, "b")
    assert copy != url and copy.startswith("/media/recipes/b-")
    image_service.delete_local_thumbnail(url)
    assert (tmp_path / copy.removeprefix("/media/")).read_bytes() == b"img"
    assert image_service.copy_local_thumbnail("https://cdn/x.jpg", "b") == "https://cdn/x.jpg"
    assert image_service.copy_local_thumbnail("/media/recipes/disparue.png", "b") is None


def test_ingredient_lines_for_import():
    assert recipe_export.ingredient_lines(_recipe().ingredients) == ["250 g farine, tamisée", "3 œufs"]
    assert recipe_export.ingredient_lines([{"name": ""}, "sel", 5, None]) == ["sel", "5"]
    assert recipe_export.ingredient_lines("pas une liste") == []


def test_jsonld_is_a_complete_schema_org_recipe():
    data = recipe_export.recipe_jsonld(
        _recipe(nutrition={"calories": 312.4, "proteins": 9, "fat": float("nan")}),
        "https://popote.fr", "https://popote.fr/api/public/recipes/t/page",
    )
    assert data["@type"] == "Recipe" and data["name"] == "Crêpes"
    assert data["image"] == "https://popote.fr/media/recipes/x.png"
    assert data["recipeYield"] == "4 portions"
    assert (data["prepTime"], data["cookTime"], data["totalTime"]) == ("PT10M", "PT20M", "PT30M")
    assert [s["text"] for s in data["recipeInstructions"]] == ["Mélanger.", "Cuire."]
    assert data["nutrition"] == {
        "@type": "NutritionInformation", "servingSize": "1 portion",
        "calories": "312 kcal", "proteinContent": "9 g",
    }


def test_page_embeds_the_jsonld_safely():
    page = recipe_export.render_recipe_page(
        _recipe(title="<b>Crêpes</b>", steps=["Cuire </script><script>alert(1)</script>"],
                thumbnail_url=None),
        "https://popote.fr", "https://popote.fr/p", "https://popote.fr/partage/r/t",
    )
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    assert len(blocks) == 1
    assert json.loads(blocks[0])["recipeInstructions"][0]["text"].startswith("Cuire </script>")
    assert "<b>Crêpes</b>" not in page and "&lt;b&gt;Crêpes&lt;/b&gt;" in page
    assert "<script>alert" not in page
