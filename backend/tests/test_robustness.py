"""Données inattendues (JSON-LD des sites, sortie du LLM) : jamais de plantage.

Cas trouvés en « fuzzant » les fonctions de parsing avec du JSON aléatoire :
un champ attendu comme liste qui arrive en nombre/booléen/objet, des NaN,
des valeurs qui débordent les colonnes de la base.
"""

import json

import pytest

from app.services import grocery, llm_service
from app.services import recipe_parsing as rp
from app.services.extraction_steps import error_text


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 10**12, "9" * 5000, "P99999999D"])
def test_absurd_durations_are_ignored(value):
    assert rp.parse_duration_minutes(value) is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 10**12, "100000000000000000000 personnes"])
def test_absurd_servings_are_ignored(value):
    assert rp.parse_int(value) is None


def test_plausible_values_still_parse():
    assert rp.parse_duration_minutes("PT2H") == 120
    assert rp.parse_duration_minutes(["", "PT15M"]) == 15
    assert rp.parse_duration_minutes(48 * 60) == 2880  # marinade de deux jours
    assert rp.parse_int("6 personnes") == 6


@pytest.mark.parametrize("raw", [42, True, {"text": "farine"}, 3.5])
def test_jsonld_with_odd_ingredient_field(raw):
    node = {
        "@type": "Recipe", "name": "Tarte", "recipeIngredient": raw,
        "recipeInstructions": ["Mélanger.", "Cuire."], "keywords": 12,
    }
    assert rp.jsonld_to_recipe(node) is None  # moins de deux ingrédients : incomplet
    assert "Tarte" in rp.jsonld_to_text(node)


def test_jsonld_ignores_nested_objects_among_ingredients():
    node = {
        "@type": "Recipe", "name": "Crêpes",
        "recipeIngredient": ["250 g de farine", {"x": 1}, ["?"], "3 œufs"],
        "recipeInstructions": "Mélanger. Cuire.",
        "keywords": {"@id": "x"},
    }
    recipe = rp.jsonld_to_recipe(node)
    assert [i["name"] for i in recipe["ingredients"]] == ["farine", "œufs"]


def test_jsonld_title_fits_the_database_column():
    node = {
        "@type": "Recipe", "name": "Gâteau " * 200,
        "recipeIngredient": ["1 œuf", "100 g de sucre"], "recipeInstructions": ["Cuire."],
    }
    assert len(rp.jsonld_to_recipe(node)["title"]) <= 500


@pytest.mark.parametrize("tags", [5, True, {"a": 1}, "vegan, rapide", [None, {"x": 1}, "été"]])
def test_normalize_tags_accepts_anything(tags):
    assert all(isinstance(t, str) for t in rp.normalize_tags(tags))


def test_normalize_tags_splits_a_comma_string():
    assert rp.normalize_tags("vegan, rapide") == ["vegan", "rapide"]


@pytest.mark.parametrize("field", ["ingredients", "steps", "tags"])
@pytest.mark.parametrize("value", [7, True, {"name": "sel"}, "une seule ligne"])
def test_llm_response_with_non_list_fields(field, value):
    data = {
        "title": "Soupe", "ingredients": [{"name": "poireau"}], "steps": ["Cuire."],
        "tags": [], field: value,
    }
    recipe = llm_service.parse_llm_content(json.dumps(data))
    assert isinstance(recipe["ingredients"], list)
    assert isinstance(recipe["steps"], list)
    assert isinstance(recipe["tags"], list)


def test_llm_response_with_nan_and_huge_numbers():
    content = (
        '{"title": "Soupe", "ingredients": [{"name": "poireau"}], "steps": ["Cuire."],'
        ' "servings": NaN, "prep_time": Infinity, "cook_time": 99999999999}'
    )
    recipe = llm_service.parse_llm_content(content)
    assert recipe["servings"] is None
    assert recipe["prep_time"] is None
    assert recipe["cook_time"] is None


def test_llm_title_fits_the_database_column():
    recipe = llm_service.parse_llm_content(json.dumps({
        "title": "x" * 2000, "ingredients": [{"name": "sel"}], "steps": ["Saler."],
    }))
    assert len(recipe["title"]) <= 500


def test_image_description_input_with_odd_fields():
    text = llm_service.image_description_input("Soupe", 12, None, {"name": "sel"}, "Servir chaud.")
    assert "Soupe" in text and "Servir chaud." in text


@pytest.mark.parametrize("ingredients", [5, True, "sel", {"name": "sel"}])
def test_grocery_with_non_list_ingredients(ingredients):
    grocery.merge_ingredients([("Soupe", ingredients)])
    grocery.rank_by_pantry([{"id": 1, "ingredients": ingredients}], ["sel"])


@pytest.mark.parametrize("value", ["nan", "inf", "1e999", "1 1/0"])
def test_parse_quantity_rejects_non_numbers(value):
    assert grocery.parse_quantity(value) is None


def test_shopping_list_survives_nan_quantities():
    items = grocery.merge_ingredients([("A", [{"name": "lait", "quantity": "nan", "unit": "ml"}])])
    assert [i["name"] for i in items] == ["Lait"]


class _SilentError(Exception):
    pass


def test_error_text_never_empty_and_hides_sql():
    assert error_text(_SilentError()) == "_SilentError"
    db_error = Exception("value too long for type character varying(500)\n[SQL: UPDATE recipes SET ...]")
    assert error_text(db_error) == "value too long for type character varying(500)"
