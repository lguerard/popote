"""Lecture d'une recette publiée sur un site, via recipe-scrapers.

recipe-scrapers (MIT, https://github.com/hhursev/recipe-scrapers) est la
bibliothèque de référence des gestionnaires de recettes auto-hébergés
(Tandoor…). Elle connaît plus de 700 sites un par un (Marmiton, 750g,
CuisineAZ, Jow, Ricardo, HelloFresh…) et, ailleurs, lit les données
schema.org/Recipe sous toutes leurs formes — JSON-LD, mais aussi microdata et
RDFa, que notre lecteur JSON-LD maison ne voyait pas. Elle est maintenue par
une large communauté : quand un site change, elle est corrigée pour tout le
monde.

Le lecteur maison (recipe_parsing.find_jsonld_recipe) reste le repli si la
bibliothèque est absente ou ne trouve rien.
"""

import logging

from . import recipe_parsing as rp

logger = logging.getLogger(__name__)

try:
    from recipe_scrapers import scrape_html
except ImportError:  # dépendance optionnelle (tests minimalistes)
    scrape_html = None


def _call(scraper, name: str):
    """Valeur d'un champ, None s'il est absent : chaque champ manquant lève sa propre exception."""
    try:
        value = getattr(scraper, name)()
    except Exception:
        return None
    return None if value in ("", [], {}) else value


def scrape_recipe(html: str, url: str | None) -> tuple[dict, str] | None:
    """(recette au format Popote, texte compact pour le LLM), ou None.

    None si la page ne publie pas de recette exploitable (au moins un titre,
    deux ingrédients et une étape) : les autres méthodes prennent le relais.
    """
    if scrape_html is None or not html:
        return None
    try:
        scraper = scrape_html(html, org_url=url or "https://localhost/", supported_only=False)
    except Exception:
        return None

    title = rp.clean_text(_call(scraper, "title"))[:500]
    raw_ingredients = [line for line in rp.as_list(_call(scraper, "ingredients")) if rp.clean_text(line)]
    ingredients, lines = _ingredients(scraper, raw_ingredients)
    pairs = _steps(scraper)
    steps = [text for _, text in pairs]
    if not title or len(ingredients) < 2 or not steps:
        return None

    prep = rp.parse_duration_minutes(_call(scraper, "prep_time"))
    cook = rp.parse_duration_minutes(_call(scraper, "cook_time"))
    total = rp.parse_duration_minutes(_call(scraper, "total_time"))
    if prep is None and total:
        prep = max(total - (cook or 0), 0) or None
    keywords = _call(scraper, "keywords")
    category = rp.guess_category(_call(scraper, "category"), title, keywords)
    content = " ".join([title] + [i["name"] for i in ingredients] + steps)
    recipe = {
        "title": title,
        "description": rp._short_description(_call(scraper, "description")),
        "language": "fr" if rp.looks_french(content) else "en",
        "category": category,
        "servings": rp.parse_int(_call(scraper, "yields")),
        "prep_time": prep,
        "cook_time": cook,
        "ingredients": ingredients,
        "steps": rp.steps_from_pairs(pairs),
        "tags": rp.build_tags(
            {"keywords": keywords, "recipeCuisine": _call(scraper, "cuisine")},
            title, category, (prep or 0) + (cook or 0) or total,
        ),
        "thumbnail_url": _call(scraper, "image"),
    }
    text = "\n".join(
        [f"Titre : {title}", "Ingrédients :"]
        + rp.lines_with_headings((section, f"- {rp.clean_text(line)}") for section, line in lines)
        + ["Étapes :"]
        + rp.lines_with_headings((sec, f"{n}. {step}") for n, (sec, step) in enumerate(pairs, 1))
    )
    return recipe, text


def _ingredients(scraper, raw_lines: list[str]) -> tuple[list[dict], list[tuple[str | None, str]]]:
    """(ingrédients, lignes d'origine avec leur section), groupés en sections
    quand le site les publie (« Pour la pâte »)."""
    groups = _call(scraper, "ingredient_groups") or []
    if len(groups) > 1:
        ingredients, lines = [], []
        for group in groups:
            section = rp.clean_text(getattr(group, "purpose", None)).rstrip(" :")[: rp.MAX_SECTION_LENGTH] or None
            for line in getattr(group, "ingredients", None) or []:
                if rp.clean_text(line):
                    ingredient = rp.parse_ingredient_line(line)
                    if section:
                        ingredient["section"] = section
                    ingredients.append(ingredient)
                    lines.append((section, line))
        if len(ingredients) >= 2:
            return ingredients, lines
    ingredients = rp.parse_ingredient_lines(raw_lines)
    return ingredients, [(None, line) for line in raw_lines]


def _steps(scraper) -> list[tuple[str | None, str]]:
    """Étapes (section, texte) ; sections prises dans les données schema.org
    (HowToSection) que la liste à plat de recipe-scrapers ne garde pas."""
    pairs = rp.sectioned_instructions(_call(scraper, "instructions_list") or _call(scraper, "instructions"))
    if any(section for section, _ in pairs):
        return pairs
    try:
        schema = scraper.schema.data or {}
    except Exception:
        return pairs
    from_schema = rp.sectioned_instructions(schema.get("recipeInstructions")) if isinstance(schema, dict) else []
    names = {section for section, _ in from_schema if section}
    # recipe-scrapers aplatit les sections en glissant leur nom comme une
    # étape (« 1. Pâte ») : sans ces faux pas, ce sont les mêmes étapes.
    real = [text for _, text in pairs if text.rstrip(" :") not in names]
    if names and len(real) <= len(from_schema):
        return from_schema
    return pairs
