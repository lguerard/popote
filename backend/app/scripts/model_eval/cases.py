"""Cas d'évaluation : tirés des VRAIES recettes de la base, à chaque passage.

Ce que la base garde, et donc ce qui peut servir de vérité :

- les recettes enregistrées (titre, ingrédients avec quantités, étapes,
  portions, durées, catégorie), souvent corrigées à la main après
  l'extraction. Le texte source, lui, n'est PAS conservé : le cas
  d'extraction rejoue donc la recette mise en page comme une page web
  bruitée ou une transcription orale (choix fixe par recette), et le
  modèle doit retrouver la recette enregistrée ;
- la nutrition déjà calculée (colonne ``nutrition``) : référence pour la
  tâche nutrition. Elle a été produite par le modèle en place (ou Claude) :
  un candidat est donc noté sur son accord avec elle, à tolérance large ;
- titre, catégorie, ingrédients et étapes : entrée de la description du plat.

Les photos envoyées ne sont pas conservées (seule la recette lue l'est) :
la tâche photo_recipe utilise les photos fournies avec le module.

Déterministe : les recettes « validées » (notées, cuisinées, ou modifiées
après leur création) d'abord, les plus récentes en premier, plafonnées par
tâche ; la mise en page de chaque recette dépend de son identifiant et
d'une graine fixe. Les cas fournis (eval_cases.json) complètent une tâche
qui en a moins de MIN_CASES.
"""

import hashlib
import json
from datetime import timedelta
from pathlib import Path

from ...services import recipe_parsing

TASKS = ("extraction", "photo_recipe", "nutrition", "description")
DEFAULT_MAX_CASES = 12
MIN_CASES = 3
SEED = "popote-model-eval-1"
# Assez de recettes pour remplir chaque tâche après filtrage.
HARVEST_LIMIT = 400

HERE = Path(__file__).parent
BUNDLED_FILE = HERE / "eval_cases.json"


def load_bundled() -> dict:
    return json.loads(BUNDLED_FILE.read_text(encoding="utf-8"))


def _pick(recipe_id, n: int, salt: str = "") -> int:
    digest = hashlib.sha256(f"{SEED}|{salt}|{recipe_id}".encode()).hexdigest()
    return int(digest[:8], 16) % n


def _get(recipe, name, default=None):
    return recipe.get(name, default) if isinstance(recipe, dict) else getattr(recipe, name, default)


def _ingredients(recipe) -> list[dict]:
    return [
        i for i in recipe_parsing.as_list(_get(recipe, "ingredients"))
        if isinstance(i, dict) and str(i.get("name") or "").strip()
    ]


def _steps(recipe) -> list[str]:
    out = []
    for s in recipe_parsing.as_list(_get(recipe, "steps")):
        text = s.get("text") if isinstance(s, dict) else s
        if str(text or "").strip():
            out.append(str(text).strip())
    return out


def _status(recipe) -> str:
    status = _get(recipe, "status")
    return getattr(status, "value", status) or ""


def is_validated(recipe) -> bool:
    """Une personne s'y est intéressée : notée, cuisinée, ou modifiée après coup."""
    if _get(recipe, "rating") is not None or (_get(recipe, "cooked_count") or 0) > 0:
        return True
    if _get(recipe, "cook_again") is not None:
        return True
    created, updated = _get(recipe, "created_at"), _get(recipe, "updated_at")
    return bool(created and updated and updated - created > timedelta(minutes=5))


def usable(recipe) -> bool:
    """Recette terminée, à soi (pas une copie reçue), avec de quoi évaluer."""
    return (
        _status(recipe) == "done"
        and not _get(recipe, "reextracting")
        and _get(recipe, "shared_by_id") is None
        and len(_ingredients(recipe)) >= 2
        and bool(str(_get(recipe, "title") or "").strip())
    )


def ordered(recipes) -> list:
    """Validées d'abord, puis les plus récentes ; l'identifiant départage."""
    def key(r):
        created = _get(r, "created_at")
        return (not is_validated(r), -(created.timestamp() if created else 0), str(_get(r, "id")))
    return sorted((r for r in recipes if usable(r)), key=key)


def _short_id(recipe) -> str:
    return str(_get(recipe, "id"))[:8]


# ---------------------------------------------------------------------------
# Mise en page d'une recette enregistrée (entrée de la tâche extraction)
# ---------------------------------------------------------------------------

_HEADERS = (
    "Accueil > Recettes > {category}\n\n",
    "Publié le 12 mars — 87 commentaires — ★★★★☆ (154 votes)\nAbonnez-vous à la newsletter !\n\n",
    "Menu Recherche Connexion\nPublicité\n\n",
)
_FOOTERS = (
    "\n\nVous aimerez aussi : tarte aux pommes, gratin de courgettes…\n© Tous droits réservés — Mentions légales",
    "\n\nCommentaires (12)\nMarie : trop bon, je refais ce week-end !\nPolitique de cookies",
    "\n\nPartager sur Facebook · Pinterest · Imprimer la recette",
)


def _ingredient_line(i: dict) -> str:
    parts = [str(i.get(k) or "").strip() for k in ("quantity", "unit")]
    name = str(i.get("name")).strip()
    qty = " ".join(p for p in parts if p)
    line = f"{qty} {'de ' if qty and parts[1] else ''}{name}".strip()
    notes = str(i.get("notes") or "").strip()
    return f"{line} ({notes})" if notes else line


def _web_page(recipe) -> str:
    title = str(_get(recipe, "title")).strip()
    meta = []
    if _get(recipe, "servings"):
        meta.append(f"Pour {_get(recipe, 'servings')} personnes")
    if _get(recipe, "prep_time"):
        meta.append(f"Préparation : {_get(recipe, 'prep_time')} min")
    if _get(recipe, "cook_time"):
        meta.append(f"Cuisson : {_get(recipe, 'cook_time')} min")
    lines = [_HEADERS[_pick(_get(recipe, "id"), 3, "h")].format(category=_get(recipe, "category") or "Plats"), title]
    if meta:
        lines.append(" | ".join(meta))
    lines += ["", "Ingrédients"]
    section = None
    for i in _ingredients(recipe):
        if i.get("section") and i["section"] != section:
            section = i["section"]
            lines.append(f"{section} :")
        lines.append(f"- {_ingredient_line(i)}")
    steps = _steps(recipe)
    if steps:
        lines += ["", "Préparation"] + [f"{n}. {s}" for n, s in enumerate(steps, 1)]
    return "\n".join(lines) + _FOOTERS[_pick(_get(recipe, "id"), 3, "f")]


def _transcript(recipe) -> str:
    title = str(_get(recipe, "title")).strip()
    ings = ", ".join(_ingredient_line(i) for i in _ingredients(recipe))
    text = f"Alors aujourd'hui on fait « {title} », c'est super simple. Il vous faut {ings}."
    servings = _get(recipe, "servings")
    if servings:
        text += f" Ça fait {servings} portions."
    middle = ("Ensuite,", "Après ça,", "Puis")
    steps = _steps(recipe)
    for n, step in enumerate(steps):
        if n == 0:
            lead = "Alors on commence :"
        elif n == len(steps) - 1:
            lead = "Et pour finir,"
        else:
            lead = middle[(n - 1) % len(middle)]
        text += f" {lead} {step[0].lower() + step[1:]}"
    if _get(recipe, "cook_time"):
        text += f" Comptez à peu près {_get(recipe, 'cook_time')} minutes de cuisson."
    return text + " Et voilà, bon appétit !"


def render_source(recipe) -> tuple[str, str]:
    """(texte, style) : la recette telle qu'une page web ou une vidéo la donnerait."""
    if _pick(_get(recipe, "id"), 3, "style") == 2 and _steps(recipe):
        return _transcript(recipe), "transcription"
    return _web_page(recipe), "page web"


def _expected_recipe(recipe) -> dict:
    return {
        "title": str(_get(recipe, "title")).strip(),
        "ingredients": [
            {"quantity": i.get("quantity") or "", "unit": i.get("unit") or "", "name": i["name"]}
            for i in _ingredients(recipe)
        ],
        "steps_count": len(_steps(recipe)) or None,
        "servings": _get(recipe, "servings"),
        "prep_time": _get(recipe, "prep_time"),
        "cook_time": _get(recipe, "cook_time"),
        "category": _get(recipe, "category"),
    }


def extraction_case(recipe) -> dict | None:
    if not _steps(recipe):
        return None
    text, style = render_source(recipe)
    return {"id": f"recette-{_short_id(recipe)}", "source": "db", "style": style,
            "input": text, "expected": _expected_recipe(recipe)}


def nutrition_case(recipe) -> dict | None:
    values = _get(recipe, "nutrition") or {}
    if not isinstance(values, dict):
        return None
    expected = {k: values.get(k) for k in ("calories", "proteins", "carbs", "fat", "fiber")
                if isinstance(values.get(k), (int, float)) and not isinstance(values.get(k), bool)}
    if "calories" not in expected or len(expected) < 3 or not _get(recipe, "servings"):
        return None
    return {"id": f"nutrition-{_short_id(recipe)}", "source": "db", "title": _get(recipe, "title"),
            "servings": _get(recipe, "servings"), "ingredients": _ingredients(recipe), "expected": expected}


def description_case(recipe) -> dict | None:
    if not _steps(recipe):
        return None
    return {"id": f"description-{_short_id(recipe)}", "source": "db", "title": _get(recipe, "title"),
            "description": _get(recipe, "description"), "category": _get(recipe, "category"),
            "ingredients": _ingredients(recipe), "steps": _steps(recipe)}


_BUILDERS = {"extraction": extraction_case, "nutrition": nutrition_case, "description": description_case}


def build_cases(recipes, max_cases: int = DEFAULT_MAX_CASES, bundled: dict | None = None) -> tuple[dict, dict]:
    """({tâche: [cas]}, {tâche: note sur l'origine des cas})."""
    bundled = bundled if bundled is not None else load_bundled()
    max_cases = max(1, max_cases)
    pool = ordered(recipes)
    cases, sources = {}, {}
    for task in TASKS:
        picked = []
        builder = _BUILDERS.get(task)
        if builder:
            for recipe in pool:
                if len(picked) >= max_cases:
                    break
                case = builder(recipe)
                if case:
                    picked.append(case)
        from_db = len(picked)
        if from_db < MIN_CASES:
            extra = [dict(c, source="bundled") for c in bundled.get(task, [])]
            picked += extra[: max(0, min(MIN_CASES, max_cases) - from_db)] if from_db else extra[:max_cases]
        cases[task] = picked
        if task == "photo_recipe":
            sources[task] = "photos fournies (les photos envoyées ne sont pas conservées par Popote)"
        elif from_db >= MIN_CASES:
            sources[task] = f"{from_db} recette(s) de la base"
        elif from_db:
            sources[task] = f"{from_db} recette(s) de la base + {len(picked) - from_db} cas fourni(s)"
        else:
            sources[task] = "cas fournis (pas assez de recettes en base)"
    return cases, sources


def cases_hash(cases: dict) -> str:
    """Empreinte du jeu de cas : un résultat en cache n'est réutilisé que si elle est identique."""
    blob = json.dumps({t: cs for t, cs in sorted(cases.items())},
                      sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


async def load_recipes(session, limit: int = HARVEST_LIMIT) -> list:
    """Recettes terminées, les plus récentes d'abord (le tri fin est fait par ``ordered``)."""
    from sqlalchemy import select

    from ...models.recipe import ExtractionStatus, Recipe

    result = await session.execute(
        select(Recipe).where(Recipe.status == ExtractionStatus.done)
        .order_by(Recipe.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())
