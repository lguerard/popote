"""Score a model's recipe extraction against a golden test case.

Heuristic, not an LLM judge: deterministic, free, and fast enough to run
against several candidate models in one evaluation pass. It doesn't try to
capture everything that makes an extraction "good" — it captures the parts
that break the app when wrong (valid structured JSON, the right ingredients
present, a plausible step count, correct category/language), which is what
actually matters for this specific pipeline.
"""


def score_extraction(data: dict, expected: dict) -> tuple[float, list[str]]:
    """Returns (score out of 100, list of human-readable notes)."""
    notes: list[str] = []
    score = 0.0

    if "error" in data:
        return 0.0, ["Le modèle n'a pas trouvé de recette dans le texte."]

    # Structure JSON valide (dicts pour les ingredients, etc.) : deja
    # garanti par _parse_json + _normalize_recipe_shape en amont, donc ce
    # test verifie surtout qu'on a bien un dict exploitable.
    if not isinstance(data, dict):
        return 0.0, ["Réponse non structurée (pas un objet JSON)."]
    score += 40
    notes.append("JSON valide (+40)")

    title = str(data.get("title") or "").lower()
    if any(kw in title for kw in expected["title_keywords"]):
        score += 5
        notes.append("Titre pertinent (+5)")
    else:
        notes.append(f"Titre inattendu : {data.get('title')!r}")

    ingredients = data.get("ingredients") or []
    ingredient_text = " ".join(
        str(item.get("name", "")) for item in ingredients if isinstance(item, dict)
    ).lower()
    expected_kw = expected["ingredient_keywords"]
    found = [kw for kw in expected_kw if kw in ingredient_text]
    ing_score = 20 * (len(found) / len(expected_kw)) if expected_kw else 20
    score += ing_score
    notes.append(f"Ingrédients trouvés {len(found)}/{len(expected_kw)} (+{ing_score:.1f})")

    steps = data.get("steps") or []
    n_steps = len(steps) if isinstance(steps, list) else 0
    if expected["min_steps"] <= n_steps <= expected["max_steps"]:
        score += 15
        notes.append(f"Nombre d'étapes plausible : {n_steps} (+15)")
    else:
        diff = min(abs(n_steps - expected["min_steps"]), abs(n_steps - expected["max_steps"]))
        partial = max(0.0, 15 - diff * 3)
        score += partial
        notes.append(f"Nombre d'étapes {n_steps}, attendu {expected['min_steps']}-{expected['max_steps']} (+{partial:.1f})")

    if data.get("category") == expected["category"]:
        score += 10
        notes.append("Catégorie correcte (+10)")
    else:
        notes.append(f"Catégorie {data.get('category')!r}, attendu {expected['category']!r}")

    if data.get("language") == expected["language"]:
        score += 5
        notes.append("Langue correcte (+5)")

    servings = data.get("servings")
    if isinstance(servings, int) and expected.get("servings") is not None:
        if servings == expected["servings"]:
            score += 5
            notes.append("Portions correctes (+5)")
        else:
            notes.append(f"Portions {servings}, attendu {expected['servings']}")

    return round(min(score, 100.0), 1), notes
