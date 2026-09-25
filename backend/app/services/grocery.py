"""Liste de courses : fusion des ingrédients, rayons, « qu'ai-je dans le frigo ».

Logique pure (ni base, ni réseau) pour rester testable seule, comme
recipe_parsing.
"""

import re

from .recipe_parsing import _fold, canonical_unit

# ---------------------------------------------------------------------------
# Normalisation des noms d'ingrédients
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "de", "d", "du", "des", "la", "le", "les", "l", "a", "au", "aux", "en", "et",
    "ou", "un", "une", "pour", "avec", "sans", "bien", "tres", "gros", "grosse",
    "petit", "petite", "moyen", "moyenne", "grand", "grande", "bio", "entier",
    "entiere", "hache", "hachee", "emince", "emincee", "rape", "rapee", "coupe",
    "coupee", "cuit", "cuite", "environ", "facultatif", "optionnel", "type",
}


def _singular(word: str) -> str:
    if len(word) > 3 and word.endswith(("s", "x")) and not word.endswith(("ss", "us")):
        return word[:-1]
    return word


def ingredient_tokens(name: str) -> list[str]:
    """« Blancs de poulet émincés » → ["blanc", "poulet"]."""
    folded = _fold(name or "").replace("œ", "oe").replace("æ", "ae")
    folded = re.sub(r"\(.*?\)", " ", folded)
    words = re.findall(r"[a-z0-9]+", folded)
    return [_singular(w) for w in words if w not in _STOP_WORDS and not w.isdigit()]


def ingredient_key(name: str) -> str:
    return " ".join(ingredient_tokens(name))


def _contains(tokens: list[str], phrase: list[str]) -> bool:
    n = len(phrase)
    return any(tokens[i:i + n] == phrase for i in range(len(tokens) - n + 1))


# ---------------------------------------------------------------------------
# Rayons
# ---------------------------------------------------------------------------

AISLES = (
    "Fruits et légumes",
    "Boucherie et poissonnerie",
    "Crèmerie et œufs",
    "Boulangerie",
    "Épicerie salée",
    "Épicerie sucrée",
    "Épices et condiments",
    "Surgelés",
    "Boissons",
    "Autres",
)

# Expressions séparées par des virgules. L'expression la plus longue présente
# dans le nom l'emporte : « lait de coco » → épicerie, « lait » → crèmerie,
# « gingembre en poudre » → épices, « gingembre » → légumes.
_AISLE_KEYWORDS = {
    "Fruits et légumes": """
        ail, oignon, oignon nouveau, cebette, echalote, carotte, tomate, tomate cerise,
        courgette, aubergine, poivron, piment frais, concombre, salade, laitue, roquette,
        epinard, mache, chou, chou fleur, brocoli, celeri, fenouil, poireau, radis, navet,
        betterave, patate douce, pomme de terre, potimarron, courge, butternut, citrouille,
        champignon, asperge, artichaut, avocat, haricot vert, petits pois, mais doux,
        gingembre, citron, citron vert, jus de citron, jus de citron vert, orange,
        pamplemousse, clementine, mandarine, pomme, poire, banane, fraise, framboise,
        myrtille, mure, cerise, abricot, peche, nectarine, prune, raisin, kiwi, mangue,
        ananas, melon, pasteque, grenade, figue, rhubarbe, fruit rouge, persil, coriandre,
        basilic, menthe, ciboulette, aneth, cerfeuil, thym frais, romarin frais,
        citronnelle, pousse de soja, legume, fruit""",
    "Boucherie et poissonnerie": """
        poulet, blanc de poulet, dinde, canard, magret, boeuf, veau, porc, agneau, jambon,
        lardon, bacon, saucisse, chorizo, merguez, steak, viande, viande hachee, escalope,
        filet mignon, roti, cuisse, aiguillette, saumon, saumon fume, thon, cabillaud, colin,
        merlu, truite, dorade, bar, sardine, maquereau, crevette, gambas, moule,
        saint jacques, calamar, poulpe, poisson, crabe, surimi, anchois""",
    "Crèmerie et œufs": """
        oeuf, jaune d oeuf, blanc d oeuf, lait, beurre, creme, creme fraiche, creme liquide,
        yaourt, yogourt, fromage, fromage blanc, fromage rape, faisselle, skyr,
        petit suisse, mascarpone, ricotta, mozzarella, burrata, parmesan, gruyere,
        emmental, comte, cheddar, feta, chevre, roquefort, camembert, brie, reblochon,
        raclette, tofu, tempeh""",
    "Boulangerie": """
        pain, baguette, pain de mie, brioche, pain burger, pain pita, tortilla, wrap,
        croissant, biscotte, chapelure, pate feuilletee, pate brisee, pate sablee,
        pate a pizza""",
    "Épicerie salée": """
        pates, spaghetti, tagliatelle, penne, fusilli, linguine, lasagne, nouille,
        vermicelle, riz, quinoa, boulgour, semoule, couscous, lentille, pois chiche,
        haricot rouge, haricot blanc, flageolet, feve, polenta, flocons d avoine, avoine,
        tomate concassee, coulis de tomate, concentre de tomate, pulpe de tomate, passata,
        bouillon, cube de bouillon, fond de veau, lait de coco, creme de coco, olive,
        capre, cornichon, thon en boite, sardine en boite, graine, graines de chia, sesame,
        noix, noisette, amande, cajou, pistache, cacahuete, pignon, levure maltee, chips""",
    "Épicerie sucrée": """
        farine, maizena, fecule, sucre, sucre glace, sucre roux, cassonade, vergeoise,
        sucre vanille, vanille, gousse de vanille, extrait de vanille, levure,
        levure chimique, levure boulanger, bicarbonate, chocolat, chocolat noir,
        chocolat au lait, chocolat blanc, pepite de chocolat, cacao, miel, sirop d erable,
        sirop d agave, confiture, pate a tartiner, beurre de cacahuete, puree d amande,
        poudre d amande, amande en poudre, noix de coco, coco rapee, gelatine, agar agar,
        biscuit, speculoos, cafe, the, compote, fruit sec, raisin sec, abricot sec,
        cranberry, datte, caramel, praline, granola, cereale, muesli, lait concentre""",
    "Épices et condiments": """
        sel, fleur de sel, poivre, epice, cumin, curry, curcuma, paprika, piment,
        piment d espelette, cannelle, muscade, gingembre en poudre, ail en poudre,
        herbes de provence, thym, laurier, romarin, origan, cardamome, clou de girofle,
        badiane, anis, ras el hanout, garam masala, quatre epices, huile, huile d olive,
        huile de tournesol, huile de colza, huile de sesame, vinaigre, vinaigre balsamique,
        vinaigre de cidre, moutarde, ketchup, mayonnaise, sauce soja, tamari,
        sauce worcestershire, tabasco, sriracha, harissa, pesto, sauce huitre, nuoc mam,
        sauce poisson, mirin""",
    "Boissons": """
        vin, vin blanc, vin rouge, biere, cidre, rhum, cognac, porto, champagne, prosecco,
        jus, jus d orange, jus de pomme, eau gazeuse, eau petillante, limonade, soda,
        lait d amande, lait d avoine, lait de soja, boisson vegetale""",
}

_AISLE_PHRASES = sorted(
    (
        (tokens, aisle)
        for aisle, blob in _AISLE_KEYWORDS.items()
        for phrase in blob.split(",")
        if (tokens := ingredient_tokens(phrase))
    ),
    key=lambda item: -len(item[0]),
)


def guess_aisle(name: str) -> str:
    """Rayon du supermarché où trouver l'ingrédient (« Autres » si inconnu)."""
    tokens = ingredient_tokens(name)
    if "surgele" in tokens:
        return "Surgelés"
    for phrase, aisle in _AISLE_PHRASES:
        if _contains(tokens, phrase):
            return aisle
    return "Autres"


# ---------------------------------------------------------------------------
# Fusion des ingrédients de plusieurs recettes
# ---------------------------------------------------------------------------

# L'eau du robinet ne s'achète pas ; l'eau gazeuse, si (voir Boissons).
_TAP_WATER = re.compile(r"^eau(?: (?:tiede|froide|chaude|bouillante|temperature|ambiante))*$")

# Unités converties vers une unité de base pour additionner 500 g et 1 kg.
_TO_BASE = {"mg": ("g", 0.001), "g": ("g", 1), "kg": ("g", 1000),
            "ml": ("ml", 1), "cl": ("ml", 10), "dl": ("ml", 100), "l": ("ml", 1000)}


def parse_quantity(value) -> float | None:
    """« 1/2 », « 1 1/2 », « 1,5 », « 2-3 » (borne haute) → nombre, sinon None."""
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    rng = re.match(r"^(\d+(?:\.\d+)?)\s*(?:-|à|a|–)\s*(\d+(?:\.\d+)?)$", text)
    if rng:
        return float(rng.group(2))
    mixed = re.match(r"^(\d+)\s+(\d+)\s*/\s*(\d+)$", text)
    if mixed:
        return int(mixed.group(1)) + int(mixed.group(2)) / int(mixed.group(3))
    frac = re.match(r"^(\d+)\s*/\s*(\d+)$", text)
    if frac and int(frac.group(2)):
        return int(frac.group(1)) / int(frac.group(2))
    try:
        return float(text)
    except ValueError:
        return None


def format_quantity(amount: float, unit: str | None) -> tuple[str, str | None]:
    """(quantité, unité) lisibles : 1500 g → « 1.5 kg », 0.5 → « 1/2 »."""
    if unit is None and amount > 1 and amount != int(amount):
        # 2,5 œufs ne s'achètent pas : on arrondit à l'unité supérieure.
        amount = float(int(amount) + 1)
    if unit == "g" and amount >= 1000:
        amount, unit = amount / 1000, "kg"
    elif unit == "ml" and amount >= 1000:
        amount, unit = amount / 1000, "l"
    elif unit == "ml" and amount >= 10 and amount % 10 == 0:
        amount, unit = amount / 10, "cl"
    for value, label in ((0.25, "1/4"), (1 / 3, "1/3"), (0.5, "1/2"), (2 / 3, "2/3"), (0.75, "3/4")):
        if abs(amount - value) < 0.02:
            return label, unit
    rounded = round(amount, 2)
    text = str(int(rounded)) if rounded == int(rounded) else f"{rounded:g}"
    return text, unit


def merge_ingredients(recipes: list[tuple[str, list[dict]]]) -> list[dict]:
    """Fusionne les ingrédients de plusieurs recettes en une liste de courses.

    Parameters
    ----------
    recipes : list of (titre, ingrédients)
        Une entrée par recette (une recette planifiée deux fois apparaît
        deux fois : ses quantités comptent double).

    Returns
    -------
    list of dict
        name, quantity, unit, aisle, recipes — triés par rayon puis nom.
        Deux lignes du même ingrédient s'additionnent quand leurs unités
        sont compatibles (g/kg, ml/cl/l, ou identiques) ; sinon elles
        restent séparées plutôt que de produire un total faux.
    """
    merged: dict[tuple, dict] = {}
    for title, ingredients in recipes:
        for ing in ingredients or []:
            if not isinstance(ing, dict):
                continue
            name = " ".join(str(ing.get("name") or "").split())
            key = ingredient_key(name)
            if not key or _TAP_WATER.match(key):
                continue
            unit = canonical_unit(ing.get("unit"))
            base_unit, factor = _TO_BASE.get(unit or "", (unit, 1))
            amount = parse_quantity(ing.get("quantity"))
            entry = merged.setdefault((key, base_unit), {
                "name": name[:1].upper() + name[1:],
                "unit": base_unit,
                "amount": 0.0,
                "has_amount": False,
                "recipes": [],
                "aisle": guess_aisle(name),
            })
            if amount is not None:
                entry["amount"] += amount * factor
                entry["has_amount"] = True
            if title and title not in entry["recipes"]:
                entry["recipes"].append(title)

    items = []
    for entry in merged.values():
        quantity, unit = (None, entry["unit"])
        if entry["has_amount"]:
            quantity, unit = format_quantity(entry["amount"], entry["unit"])
        items.append({
            "name": entry["name"],
            "quantity": quantity,
            "unit": unit,
            "aisle": entry["aisle"],
            "recipes": entry["recipes"],
        })
    order = {aisle: i for i, aisle in enumerate(AISLES)}
    items.sort(key=lambda item: (order.get(item["aisle"], len(AISLES)), item["name"].lower()))
    return items


# ---------------------------------------------------------------------------
# « Qu'est-ce que je cuisine ? »
# ---------------------------------------------------------------------------

# Considérés comme toujours présents dans une cuisine : les compter
# rendrait « manquante » presque chaque recette pour une pincée de sel.
_STAPLES = {
    ("sel",), ("poivre",), ("eau",), ("huile",), ("huile", "olive"),
    ("huile", "neutre"), ("huile", "vegetale"), ("huile", "tournesol"),
    ("sel", "poivre"), ("fleur", "sel"),
}


def _is_staple(tokens: list[str]) -> bool:
    return tuple(tokens) in _STAPLES or bool(_TAP_WATER.match(" ".join(tokens)))


def _pantry_has(ingredient: list[str], pantry: list[list[str]]) -> bool:
    ing = set(ingredient)
    for item in pantry:
        # « tomate » couvre « tomates cerises » ; « œufs bio » couvre « œufs ».
        if set(item) <= ing or ing <= set(item):
            return True
    return False


def rank_by_pantry(
    recipes: list[dict], pantry: list[str], assume_staples: bool = True,
) -> list[dict]:
    """Classe des recettes selon ce qu'on a déjà sous la main.

    Parameters
    ----------
    recipes : list of dict
        Chaque recette avec au moins ``ingredients``.
    pantry : list of str
        Ce qu'il y a dans le frigo / les placards, en texte libre.
    assume_staples : bool
        Ne pas compter sel, poivre, huile, eau.

    Returns
    -------
    list of dict
        ``{"recipe", "matched", "missing", "coverage"}`` pour chaque recette
        utilisant au moins un ingrédient disponible : d'abord celles où il
        manque le moins, puis celles qui en utilisent le plus.
    """
    pantry_tokens = [t for t in (ingredient_tokens(p) for p in pantry) if t]
    if not pantry_tokens:
        return []
    results = []
    for recipe in recipes:
        matched, missing = [], []
        for ing in recipe.get("ingredients") or []:
            if not isinstance(ing, dict):
                continue
            name = str(ing.get("name") or "").strip()
            tokens = ingredient_tokens(name)
            if not tokens or (assume_staples and _is_staple(tokens)):
                continue
            (matched if _pantry_has(tokens, pantry_tokens) else missing).append(name)
        if not matched:
            continue
        results.append({
            "recipe": recipe,
            "matched": matched,
            "missing": missing,
            "coverage": len(matched) / (len(matched) + len(missing)),
        })
    results.sort(key=lambda r: (len(r["missing"]), -len(r["matched"])))
    return results
