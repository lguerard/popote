import json

import pytest
from bs4 import BeautifulSoup

from app.services import recipe_parsing as rp


@pytest.mark.parametrize("value, expected", [
    ("PT15M", 15),
    ("PT1H30M", 90),
    ("P0DT0H20M", 20),
    ("PT1M30S", 2),
    ("PT0M", None),
    (None, None),
    (25, 25),
    ("20 min", 20),
    ("1 h 15", 75),
])
def test_parse_duration_minutes(value, expected):
    assert rp.parse_duration_minutes(value) == expected


@pytest.mark.parametrize("value, expected", [
    ("4", 4), ("4 personnes", 4), (["6", "6 parts"], 6), (12, 12),
    ("Pour 8 cookies", 8), (None, None), ("", None),
])
def test_parse_int(value, expected):
    assert rp.parse_int(value) == expected


@pytest.mark.parametrize("line, qty, unit, name, notes", [
    ("200 g de farine", "200", "g", "farine", None),
    ("125g de margarine (70% de matière grasse)", "125", "g", "margarine", "70% de matière grasse"),
    ("1 1/2 c. à soupe d'huile d'olive", "1 1/2", "c. à s.", "huile d'olive", None),
    ("1 à 2 c.à.s de miel liquide", "1 à 2", "c. à s.", "miel liquide", None),
    ("2 cs de sucre", "2", "c. à s.", "sucre", None),
    ("1 c. à café de cannelle", "1", "c. à c.", "cannelle", None),
    ("½ citron", "1/2", None, "citron", None),
    ("3 œufs", "3", None, "œufs", None),
    ("Sel, poivre", None, None, "Sel, poivre", None),
    ("1 oignon, émincé", "1", None, "oignon", "émincé"),
    ("100 g de noix", "100", "g", "noix", None),
    ("1 noix de beurre", "1", "noix", "beurre", None),
    ("2 gousses d'ail (hachées)", "2", "gousses", "ail", "hachées"),
    ("une pincée de sel", "1", "pincée", "sel", None),
    ("Un peu de sel", None, None, "Un peu de sel", None),
    ("20 cl de crème liquide", "20", "cl", "crème liquide", None),
    ("1,5 kg de pommes de terre", "1,5", "kg", "pommes de terre", None),
    ("1 l de lait", "1", "l", "lait", None),
    ("2-3 carottes", "2-3", None, "carottes", None),
    ("250 g (ou 1 pot) de yaourt", "250", "g", "yaourt", "ou 1 pot"),
    ("Quelques feuilles de basilic", None, None, "Quelques feuilles de basilic", None),
    ("- 100 grammes de cassonade", "100", "g", "cassonade", None),
    ("2 cups flour", "2", "tasse", "flour", None),
    ("200&nbsp;g de chocolat noir", "200", "g", "chocolat noir", None),
])
def test_parse_ingredient_line(line, qty, unit, name, notes):
    parsed = rp.parse_ingredient_line(line)
    assert (parsed["quantity"], parsed["unit"], parsed["name"], parsed["notes"]) == (qty, unit, name, notes)


def test_flatten_instructions_howto_steps_and_sections():
    instructions = [
        {"@type": "HowToSection", "name": "Pâte", "itemListElement": [
            {"@type": "HowToStep", "text": "Mélanger la farine et le sucre."},
            {"@type": "HowToStep", "text": "Ajouter les œufs."},
        ]},
        {"@type": "HowToStep", "text": "<p>Enfourner <strong>20 minutes</strong>.</p>"},
    ]
    assert rp.flatten_instructions(instructions) == [
        "Mélanger la farine et le sucre.", "Ajouter les œufs.", "Enfourner 20 minutes.",
    ]


def test_flatten_instructions_splits_numbered_blob_without_breaking_numbers():
    blob = "1. Préchauffer le four à 180. Beurrer le moule. 2. Mélanger 10-15 minutes. 3. Cuire."
    assert rp.flatten_instructions(blob) == [
        "Préchauffer le four à 180. Beurrer le moule.", "Mélanger 10-15 minutes.", "Cuire.",
    ]


def test_flatten_instructions_etape_markers_and_html_lines():
    assert rp.flatten_instructions("Étape 1 : Couper. Étape 2 : Cuire.") == ["Couper.", "Cuire."]
    assert rp.flatten_instructions("Couper.<br>Cuire.") == ["Couper.", "Cuire."]


def test_clean_step_keeps_leading_quantities():
    assert rp.clean_step("10-15 minutes de repos") == "10-15 minutes de repos"
    assert rp.clean_step("2) Ajouter le sel") == "Ajouter le sel"


@pytest.mark.parametrize("texts, expected", [
    (("Dessert", "Cookies"), "dessert"),
    (("Plat principal", ""), "plat"),
    ((None, "Overnight oats framboise-chocolat"), "petit-déjeuner"),
    ((None, "Velouté de potimarron"), "soupe"),
    ((None, "Salade de fruits frais"), "dessert"),
    ((None, "Salade de lentilles"), "entrée"),
    ((None, "Smoothie bowl mangue"), "petit-déjeuner"),
    ((None, "Mousse au chocolat express"), "dessert"),
    ((None, "Pesto de basilic"), "sauce"),
    ((None, "Poulet glacé au miel"), "plat"),
    ((None, "Croziflette"), "plat"),
])
def test_guess_category(texts, expected):
    assert rp.guess_category(*texts) == expected


def test_normalize_category_keeps_valid_values_and_maps_others():
    assert rp.normalize_category("dessert") == "dessert"
    assert rp.normalize_category("Plat principal") == "plat"
    assert rp.normalize_category("n'importe quoi", "Soupe de courge") == "soupe"


def _page(*jsonld_blocks, body="", lang="fr"):
    scripts = "".join(
        f'<script type="application/ld+json">{b if isinstance(b, str) else json.dumps(b)}</script>'
        for b in jsonld_blocks
    )
    return BeautifulSoup(f'<html lang="{lang}"><head>{scripts}</head><body>{body}</body></html>', "html.parser")


FRENCH_RECIPE = {
    "@type": "Recipe",
    "name": "Cookies vegan moelleux",
    "description": "Des cookies vegan fondants.",
    "recipeYield": ["12", "12 cookies"],
    "prepTime": "PT15M",
    "cookTime": "PT10M",
    "recipeCategory": "Dessert",
    "keywords": "cookies, vegan, chocolat, recette cookies vegan",
    "suitableForDiet": "https://schema.org/VeganDiet",
    "image": [{"@type": "ImageObject", "url": "https://example.com/cookies.jpg"}],
    "recipeIngredient": [
        "125 g de margarine", "100 g de sucre roux", "200 g de farine",
        "1 sachet de levure chimique", "100 g de pépites de chocolat",
    ],
    "recipeInstructions": [
        {"@type": "HowToStep", "text": "Préchauffer le four à 180 °C."},
        {"@type": "HowToStep", "text": "Mélanger la margarine et le sucre, puis ajouter la farine."},
        {"@type": "HowToStep", "text": "Former des boules et cuire 10 minutes."},
    ],
}


def test_find_jsonld_recipe_in_graph_and_skips_broken_blocks():
    soup = _page("{not json", {"@context": "https://schema.org", "@graph": [{"@type": "WebPage"}, FRENCH_RECIPE]})
    assert rp.find_jsonld_recipe(soup)["name"] == "Cookies vegan moelleux"


def test_find_jsonld_recipe_accepts_type_list_and_trailing_comma():
    raw = '{"@type": ["Recipe", "NewsArticle"], "name": "X", "recipeIngredient": ["a", "b"],}'
    assert rp.find_jsonld_recipe(_page(raw))["name"] == "X"


def test_jsonld_to_recipe_french():
    recipe = rp.jsonld_to_recipe(FRENCH_RECIPE)
    assert recipe["title"] == "Cookies vegan moelleux"
    assert recipe["language"] == "fr"
    assert recipe["category"] == "dessert"
    assert (recipe["servings"], recipe["prep_time"], recipe["cook_time"]) == (12, 15, 10)
    assert recipe["ingredients"][0] == {"quantity": "125", "unit": "g", "name": "margarine", "notes": None}
    assert [s["order"] for s in recipe["steps"]] == [1, 2, 3]
    assert recipe["tags"][0] == "vegan"
    assert "rapide" in recipe["tags"]
    assert not any(t.startswith("recette") for t in recipe["tags"])
    assert recipe["thumbnail_url"] == "https://example.com/cookies.jpg"


def test_jsonld_to_recipe_total_time_only_is_kept_as_preparation():
    node = dict(FRENCH_RECIPE, prepTime=None, cookTime=None, totalTime="PT40M")
    recipe = rp.jsonld_to_recipe(node)
    assert (recipe["prep_time"], recipe["cook_time"]) == (40, None)


def test_jsonld_to_recipe_rejects_incomplete_data():
    assert rp.jsonld_to_recipe(dict(FRENCH_RECIPE, recipeInstructions=[])) is None
    assert rp.jsonld_to_recipe(dict(FRENCH_RECIPE, recipeIngredient=["200 g de farine"])) is None


def test_jsonld_to_recipe_flags_english_content():
    node = dict(
        FRENCH_RECIPE,
        name="Chewy vegan cookies",
        recipeIngredient=["1 cup of flour", "1/2 cup of sugar", "2 tablespoons of oil"],
        recipeInstructions=["Preheat the oven to 350F.", "Mix the flour and the sugar with the oil.",
                            "Bake for 10 minutes until golden."],
    )
    assert rp.jsonld_to_recipe(node)["language"] == "en"


def test_jsonld_to_text_is_compact_and_complete():
    text = rp.jsonld_to_text(FRENCH_RECIPE)
    assert "Préparation : 15 minutes" in text
    assert "- 200 g de farine" in text
    assert "3. Former des boules" in text


def test_extract_page_text_prefers_recipe_card_and_drops_noise():
    body = """
    <h1>Mousse au chocolat</h1>
    <div class="has-sidebar"><p>Mon histoire personnelle très longue avant la recette.</p></div>
    <div class="wprm-recipe-container">
      <h3>Ingrédients</h3><ul><li>200 g de chocolat</li><li>4 œufs</li><li>20 g de sucre</li></ul>
      <h3>Préparation</h3><ol><li>Faire fondre le chocolat.</li></ol>
    </div>
    <div class="comments-area"><p>Super recette merci !</p></div>
    """
    text = rp.extract_page_text(_page(body=body))
    assert text.startswith("Mousse au chocolat")
    assert "200 g de chocolat" in text
    assert "histoire personnelle" not in text
    assert "Super recette" not in text


def test_extract_page_text_falls_back_to_article_without_card():
    body = '<nav>Menu</nav><article><p>Faites fondre 200 g de chocolat.</p></article><div class="comment-list">x</div>'
    text = rp.extract_page_text(_page(body=body))
    assert "200 g de chocolat" in text and "Menu" not in text


CAPTION_WITH_RECIPE = """🍪 COOKIES VEGAN 🍪
Ingrédients :
🔸 125g de margarine
🔸 100g de sucre
🔸 200g de farine
🔸 100g de pépites de chocolat
Préchauffez le four à 180°. Mélangez la margarine et le sucre, ajoutez la farine puis enfournez 10 min.
#vegan #cookies"""

CAPTION_INGREDIENTS_ONLY = """Les ingrédients de la vidéo :
- 200 g de farine
- 3 œufs
- 50 cl de lait
Abonne-toi pour plus de recettes !"""


def test_has_full_recipe():
    assert rp.has_full_recipe(CAPTION_WITH_RECIPE)
    assert not rp.has_full_recipe(CAPTION_INGREDIENTS_ONLY)
    assert not rp.has_full_recipe("Trop bon ce resto ! 😋 #food")


def test_looks_like_recipe():
    assert rp.looks_like_recipe(CAPTION_INGREDIENTS_ONLY)
    assert rp.looks_like_recipe("Ingrédients\n...\nPréparation\n...")
    assert not rp.looks_like_recipe("Accueil Contact Mentions légales")


def test_looks_french():
    assert rp.looks_french("Faire fondre le chocolat au bain-marie puis ajouter les œufs et la farine.")
    assert not rp.looks_french("Melt the chocolate and add the eggs to the flour until smooth.")


def test_subtitles_to_text_dedupes_rolling_captions():
    vtt = """WEBVTT
Kind: captions
Language: fr

00:00:00.000 --> 00:00:02.000
<c>bonjour</c> à tous

00:00:02.000 --> 00:00:04.000
bonjour à tous
aujourd'hui des cookies

00:00:04.000 --> 00:00:06.000
aujourd'hui des cookies
il faut 200 g de farine
"""
    assert rp.subtitles_to_text(vtt) == "bonjour à tous aujourd'hui des cookies il faut 200 g de farine"


def test_normalize_tags():
    assert rp.normalize_tags(["Vegan", "vegan", "#Facile", "une phrase beaucoup trop longue pour un tag", ""]) == [
        "vegan", "facile",
    ]
