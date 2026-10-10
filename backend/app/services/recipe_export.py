"""Export d'une recette vers d'autres applications (MyFitnessPal…).

MyFitnessPal n'a pas d'API ouverte, mais son importateur de recettes
(« Ajouter une recette » → « Importer depuis le web ») lit les données
schema.org/Recipe d'une page. Popote expose donc, pour une recette partagée
par lien, une page HTML rendue côté serveur avec ces données — la page
/partage/r/… de l'application, elle, est rendue en JavaScript et un robot
d'import n'y verrait rien.
"""

import html
import json
import math

_NUTRIENTS = {
    "calories": ("calories", "kcal"),
    "proteins": ("proteinContent", "g"),
    "carbs": ("carbohydrateContent", "g"),
    "fat": ("fatContent", "g"),
    "fiber": ("fiberContent", "g"),
}


def _text(value) -> str:
    return " ".join(str(value).split()) if value not in (None, "") else ""


def ingredient_line(ingredient) -> str:
    """« 200 g farine, tamisée » : une ligne par ingrédient, comme sur un site."""
    if not isinstance(ingredient, dict):
        return _text(ingredient)
    main = " ".join(
        part for part in (_text(ingredient.get(k)) for k in ("quantity", "unit", "name")) if part
    )
    notes = _text(ingredient.get("notes"))
    return f"{main}, {notes}" if main and notes else main


def ingredient_lines(ingredients) -> list[str]:
    lines = [ingredient_line(i) for i in (ingredients if isinstance(ingredients, list) else [])]
    return [line for line in lines if line]


def step_texts(steps) -> list[str]:
    texts = []
    for step in steps if isinstance(steps, list) else []:
        text = _text(step.get("text") if isinstance(step, dict) else step)
        if text:
            texts.append(text)
    return texts


def _duration(minutes) -> str | None:
    return f"PT{int(minutes)}M" if isinstance(minutes, (int, float)) and minutes > 0 else None


def absolute_url(url: str | None, base_url: str) -> str | None:
    if not url:
        return None
    return f"{base_url.rstrip('/')}{url}" if url.startswith("/") else url


def recipe_jsonld(recipe, base_url: str, page_url: str) -> dict:
    """Données schema.org/Recipe d'une recette (objet Recipe ou équivalent)."""
    data = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": recipe.title,
        "url": page_url,
        "recipeIngredient": ingredient_lines(recipe.ingredients),
        "recipeInstructions": [
            {"@type": "HowToStep", "position": n, "text": text}
            for n, text in enumerate(step_texts(recipe.steps), 1)
        ],
    }
    optional = {
        "description": _text(recipe.description) or None,
        "image": absolute_url(recipe.thumbnail_url, base_url),
        "recipeYield": f"{recipe.servings} portions" if recipe.servings else None,
        "prepTime": _duration(recipe.prep_time),
        "cookTime": _duration(recipe.cook_time),
        "totalTime": _duration((recipe.prep_time or 0) + (recipe.cook_time or 0)),
        "recipeCategory": recipe.category,
        "keywords": ", ".join(map(str, recipe.tags)) if isinstance(recipe.tags, list) else None,
    }
    data.update({k: v for k, v in optional.items() if v})
    nutrition = recipe.nutrition if isinstance(recipe.nutrition, dict) else {}
    facts = {
        prop: f"{round(float(nutrition[key]))} {unit}"
        for key, (prop, unit) in _NUTRIENTS.items()
        if isinstance(nutrition.get(key), (int, float)) and math.isfinite(nutrition[key])
    }
    if facts:
        data["nutrition"] = {"@type": "NutritionInformation", "servingSize": "1 portion", **facts}
    return data


def render_recipe_page(recipe, base_url: str, page_url: str, app_url: str) -> str:
    """Page autonome : lisible par un humain, importable par un robot."""
    data = recipe_jsonld(recipe, base_url, page_url)
    # Aucun « < » brut : « </script> » dans un texte fermerait la balise
    # avant la fin du JSON (\u003c reste du JSON valide).
    jsonld = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    e = html.escape
    image = data.get("image")
    meta = []
    if recipe.servings:
        meta.append(f"{recipe.servings} portions")
    if recipe.prep_time:
        meta.append(f"préparation {recipe.prep_time} min")
    if recipe.cook_time:
        meta.append(f"cuisson {recipe.cook_time} min")
    ingredients = "".join(f"<li>{e(line)}</li>" for line in data["recipeIngredient"])
    steps = "".join(f"<li>{e(s['text'])}</li>" for s in data["recipeInstructions"])
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(recipe.title)}</title>
<meta property="og:type" content="article">
<meta property="og:title" content="{e(recipe.title)}">
{f'<meta property="og:image" content="{e(image)}">' if image else ''}
{f'<meta name="description" content="{e(data["description"])}">' if data.get("description") else ''}
<script type="application/ld+json">{jsonld}</script>
<style>
body{{font-family:system-ui,sans-serif;max-width:720px;margin:0 auto;padding:16px;line-height:1.5;color:#222;background:#fff}}
img{{width:100%;max-height:360px;object-fit:cover;border-radius:12px}}
.meta{{color:#666}} a{{color:#c2410c}}
</style>
</head>
<body>
<article>
{f'<img src="{e(image)}" alt="">' if image else ''}
<h1>{e(recipe.title)}</h1>
{f'<p>{e(data["description"])}</p>' if data.get("description") else ''}
{f'<p class="meta">{e(" · ".join(meta))}</p>' if meta else ''}
<h2>Ingrédients</h2>
<ul>{ingredients}</ul>
<h2>Préparation</h2>
<ol>{steps}</ol>
</article>
<p><a href="{e(app_url)}">Ouvrir dans Popote</a></p>
</body>
</html>
"""
