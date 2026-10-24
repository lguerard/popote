"""Notes sur 100, avec crédit partiel, pour chaque tâche évaluée.

Heuristiques déterministes plutôt qu'un modèle juge : gratuites, rapides,
et identiques d'un mois sur l'autre. Elles mesurent ce qui casse l'appli
quand c'est faux (JSON exploitable, bons ingrédients, quantités, nombre
d'étapes, portions, durées, catégorie) plutôt que le style.

Chaque critère a un poids et une valeur entre 0 et 1 ; un critère sans
valeur attendue (durée inconnue dans la base, par exemple) est retiré du
calcul au lieu de compter comme raté.
"""

import difflib
import re
import unicodedata

from ...services import recipe_parsing


def fold(text) -> str:
    """Minuscules sans accents ni ponctuation, espaces normalisés."""
    decomposed = unicodedata.normalize("NFKD", str(text or "").lower().replace("œ", "oe"))
    text = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def similarity(a, b) -> float:
    """Ressemblance 0-1 de deux textes (difflib), à la casse et aux accents près."""
    a, b = fold(a), fold(b)
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _ramp(error: float, full: float, zero: float) -> float:
    """1 jusqu'à ``full``, 0 à partir de ``zero``, linéaire entre les deux."""
    if error <= full:
        return 1.0
    if error >= zero:
        return 0.0
    return 1 - (error - full) / (zero - full)


def _weighted(criteria: list[tuple[float, float | None, str]]) -> tuple[float, list[str]]:
    """[(poids, valeur 0-1 ou None, note)] → (note sur 100, notes lisibles)."""
    kept = [(w, v, note) for w, v, note in criteria if v is not None]
    total = sum(w for w, _, _ in kept)
    if not total:
        return 0.0, ["aucun critère mesurable"]
    score = 100 * sum(w * v for w, v, _ in kept) / total
    return round(score, 1), [f"{note} ({v:.0%})" for _, v, note in kept if v < 1]


# ---------------------------------------------------------------------------
# Recettes (texte et photo)
# ---------------------------------------------------------------------------

_SINGULAR = re.compile(r"(?<=[a-z])(s|x)\b")


def _key(name) -> str:
    """Nom d'ingrédient comparable : « Pommes de terre » ≈ « pomme de terre »."""
    return _SINGULAR.sub("", fold(name))


def _matches(expected: str, got: str) -> bool:
    e, g = _key(expected), _key(got)
    if not e or not g:
        return False
    if (len(e) >= 3 and e in g) or (len(g) >= 4 and g in e):
        return True
    # « ail » pour « gousses d'ail » : tous les mots significatifs de l'un dans l'autre.
    ew, gw = set(e.split()), set(g.split())
    small, big = (ew, gw) if len(ew) <= len(gw) else (gw, ew)
    small = {w for w in small if len(w) >= 3}
    if small and small <= big:
        return True
    return difflib.SequenceMatcher(None, e, g).ratio() >= 0.8


def _quantity(value) -> float | None:
    """« 1,2 » → 1.2, « 1/2 » → 0.5, « 2-3 » → 2.0 ; None si pas de nombre."""
    text = str(value or "").replace(",", ".")
    frac = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if frac and int(frac.group(2)):
        return int(frac.group(1)) / int(frac.group(2))
    num = re.search(r"\d+(?:\.\d+)?", text)
    return float(num.group()) if num else None


def _expected_ingredients(expected: dict) -> list[dict]:
    items = expected.get("ingredients")
    if items:
        return [i if isinstance(i, dict) else {"name": str(i)} for i in items]
    return [{"name": kw} for kw in expected.get("ingredient_keywords", [])]


def _steps_range(expected: dict) -> tuple[int, int] | None:
    if "min_steps" in expected:
        return expected["min_steps"], expected["max_steps"]
    n = expected.get("steps_count")
    if not n:
        return None
    margin = max(1, round(n * 0.25))
    return max(1, n - margin), n + margin


def _close_minutes(got, want) -> float | None:
    if not want:
        return None
    if not got:
        return 0.0
    return 1.0 if abs(got - want) <= max(5, want * 0.2) else 0.0


def score_recipe(data, expected: dict) -> tuple[float, list[str]]:
    """Recette extraite (déjà normalisée par llm_service) contre la recette attendue."""
    if not isinstance(data, dict) or "error" in data:
        return 0.0, ["aucune recette rendue"]

    got = [i for i in data.get("ingredients") or [] if isinstance(i, dict) and i.get("name")]
    wanted = _expected_ingredients(expected)
    found, qty_checks = 0, []
    for item in wanted:
        match = next((g for g in got if _matches(item["name"], g["name"])), None)
        if not match:
            continue
        found += 1
        want_q = _quantity(item.get("quantity"))
        if want_q is not None:
            got_q = _quantity(match.get("quantity"))
            same_q = got_q is not None and abs(got_q - want_q) <= max(0.01, want_q * 0.02)
            want_u = recipe_parsing.canonical_unit(item.get("unit") or None)
            got_u = recipe_parsing.canonical_unit(match.get("unit") or None)
            same_u = fold(want_u) == fold(got_u) or not want_u
            qty_checks.append(1.0 if same_q and same_u else 0.5 if same_q else 0.0)
    recall = found / len(wanted) if wanted else None
    # Ingrédients inventés : chaque ingrédient en trop (au-delà de 30 %) coûte un peu.
    extra = max(0, len(got) - max(len(wanted), 1) * 1.3)
    precision = None if not wanted else max(0.0, 1 - extra / max(len(wanted), 1))

    steps = data.get("steps") or []
    n_steps = len(steps) if isinstance(steps, list) else 0
    bounds = _steps_range(expected)
    steps_v = None
    if bounds:
        lo, hi = bounds
        gap = 0 if lo <= n_steps <= hi else min(abs(n_steps - lo), abs(n_steps - hi))
        steps_v = max(0.0, 1 - 0.25 * gap)

    title_v = None
    if expected.get("title"):
        title_v = similarity(data.get("title"), expected["title"])
    if expected.get("title_keywords"):
        kw_v = float(any(fold(k) in fold(data.get("title")) for k in expected["title_keywords"]))
        title_v = kw_v if title_v is None else max(title_v, kw_v)

    servings = expected.get("servings")
    servings_v = None if not servings else float(data.get("servings") == servings)
    times = [v for v in (
        _close_minutes(data.get("prep_time"), expected.get("prep_time")),
        _close_minutes(data.get("cook_time"), expected.get("cook_time")),
    ) if v is not None]

    return _weighted([
        (15, 1.0, "JSON valide"),
        (35, recall, f"ingrédients retrouvés {found}/{len(wanted)}"),
        (5, precision, f"ingrédients en trop ({len(got)} pour {len(wanted)})"),
        (10, sum(qty_checks) / len(qty_checks) if qty_checks else None, "quantités et unités"),
        (10, steps_v, f"{n_steps} étapes, attendu {bounds[0]}-{bounds[1]}" if bounds else "étapes"),
        (10, title_v, f"titre {data.get('title')!r}"),
        (5, servings_v, f"portions {data.get('servings')}, attendu {servings}"),
        (5, sum(times) / len(times) if times else None, "durées"),
        (5, None if not expected.get("category") else float(data.get("category") == expected["category"]),
         f"catégorie {data.get('category')!r}, attendu {expected.get('category')!r}"),
        (5, None if not expected.get("language") else float(data.get("language") == expected["language"]),
         f"langue {data.get('language')!r}"),
    ])


# ---------------------------------------------------------------------------
# Nutrition
# ---------------------------------------------------------------------------

NUTRITION_FIELDS = ("calories", "proteins", "carbs", "fat", "fiber")
# Plancher de l'erreur relative : 2 g d'écart sur 1 g de fibres n'est pas
# une erreur de 200 %.
_FLOORS = {"calories": 60.0, "proteins": 4.0, "carbs": 5.0, "fat": 4.0, "fiber": 2.0}


def score_nutrition(values: dict, expected: dict) -> tuple[float, list[str]]:
    """Estimation par portion contre des valeurs de référence, à tolérance large.

    Pleine note jusqu'à 15 % d'écart, zéro à 60 %. Un cinquième de la note
    vérifie la cohérence interne (calories ≈ 4 × protéines + 4 × glucides
    + 9 × lipides), qui ne dépend pas de la référence.
    """
    if not isinstance(values, dict):
        return 0.0, ["réponse illisible"]
    criteria = []
    for field in NUTRITION_FIELDS:
        want = expected.get(field)
        if want is None:
            continue
        got = values.get(field)
        if got is None:
            criteria.append((16, 0.0, f"{field} absent"))
            continue
        error = abs(got - want) / max(want, _FLOORS[field])
        criteria.append((16, _ramp(error, 0.15, 0.6), f"{field} {got:g}, référence {want:g}"))
    cal, p, c, f = (values.get(k) for k in ("calories", "proteins", "carbs", "fat"))
    if None not in (cal, p, c, f):
        atwater = 4 * p + 4 * c + 9 * f
        error = abs(atwater - cal) / max(cal, _FLOORS["calories"])
        criteria.append((20, _ramp(error, 0.15, 0.5), f"calories incohérentes avec les macros ({atwater:.0f})"))
    else:
        criteria.append((20, 0.0, "macros incomplètes"))
    return _weighted(criteria)


# ---------------------------------------------------------------------------
# Description du plat (prompt de l'image générée)
# ---------------------------------------------------------------------------

_EN_WORDS = {"the", "a", "an", "with", "and", "of", "on", "in", "served", "topped", "golden",
             "bowl", "plate", "glass", "white", "fresh", "creamy", "slices", "garnished"}
_FR_WORDS = {"le", "la", "les", "un", "une", "des", "avec", "et", "de", "du", "sur", "dans",
             "servi", "assiette", "bol"}
_VESSELS = re.compile(
    r"\b(plate|bowl|glass|jar|pan|dish|cup|board|platter|skillet|pot|mug|tray|ramekin|"
    r"basket|bottle|casserole|tin|saucer|cocotte|verrine)s?\b", re.I)
_PREAMBLE = re.compile(r"^(here|sure|prompt|description|voici)\b", re.I)


def score_description(text: str, min_words: int = 8, max_words: int = 45) -> tuple[float, list[str]]:
    """Note volontairement lâche : une phrase anglaise non vide, de la bonne longueur.

    Le prompt de production (IMAGE_DESCRIPTION_PROMPT) demande UNE phrase en
    anglais, 35 mots au plus, qui dit dans quoi le plat est servi ; c'est
    ce qui est vérifié, sans juger le goût de la description.
    """
    text = (text or "").strip()
    if not text:
        return 0.0, ["description vide"]
    words = re.findall(r"[A-Za-zÀ-ÿ'’-]+", text)
    n = len(words)
    if n < min_words:
        length_v = n / min_words
    else:
        length_v = _ramp(max(0, n - max_words) / max_words, 0, 1)
    lower = [w.lower() for w in words]
    en = sum(w in _EN_WORDS for w in lower)
    fr = sum(w in _FR_WORDS for w in lower)
    sentences = len([s for s in re.split(r"[.!?]+(?:\s|$)", text) if s.strip()])
    form_v = float(sentences <= 1 and not _PREAMBLE.match(text) and "\n" not in text and "*" not in text)
    return _weighted([
        (40, 1.0, "non vide"),
        (25, length_v, f"{n} mots, attendu {min_words}-{max_words}"),
        (15, float(en >= 2 and en > fr), "en anglais"),
        (10, form_v, "une seule phrase, sans préambule"),
        (10, float(bool(_VESSELS.search(text))), "dit dans quoi le plat est servi"),
    ])
