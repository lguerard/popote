"""Parsing déterministe de recettes : ni réseau, ni LLM.

Tout ce qui peut être lu de façon fiable sans modèle de langage est lu ici :
données structurées schema.org/Recipe, lignes d'ingrédients, durées ISO 8601,
sous-titres de vidéos. C'est à la fois plus rapide (aucun appel au LLM, qui
prend de quelques secondes à plusieurs minutes sur le GPU partagé) et plus
juste : on reprend ce que le site a écrit au lieu de le faire réinterpréter.

Le module n'importe que la bibliothèque standard et BeautifulSoup, pour rester
testable sans installer tout le backend (voir backend/tests/).
"""

import html as html_lib
import json
import re
import unicodedata

CATEGORIES = (
    "petit-déjeuner", "entrée", "plat", "dessert", "snack",
    "boisson", "sauce", "apéritif", "soupe",
)


def clean_text(value) -> str:
    """Texte brut sans balises HTML, entités décodées, espaces normalisés."""
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"<\s*br\s*/?\s*>|</\s*(?:p|li|div|h\d)\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" ([.,)])", r"\1", text)  # « <strong>20 min</strong>. » → « 20 min. »
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


def _fold(text: str) -> str:
    """Minuscules sans accents, pour comparer des mots-clés."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# ---------------------------------------------------------------------------
# Durées, portions
# ---------------------------------------------------------------------------

_ISO_DURATION = re.compile(
    r"^P(?:(?P<d>\d+)D)?(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+(?:\.\d+)?)S)?)?$", re.I
)


def parse_duration_minutes(value) -> int | None:
    """« PT1H30M » → 90. Accepte aussi un entier ou « 20 min ». 0 → None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        minutes = int(value)
    else:
        text = str(value).strip()
        match = _ISO_DURATION.match(text)
        if match:
            parts = {k: float(v) if v else 0.0 for k, v in match.groupdict().items()}
            seconds = parts["d"] * 86400 + parts["h"] * 3600 + parts["m"] * 60 + parts["s"]
            minutes = int(-(-seconds // 60))  # arrondi au-dessus : 90 s → 2 min
        else:
            hours = re.search(r"(\d+)\s*h(?:eures?|ours?)?\s*(\d+)?", text, re.I)
            mins = re.search(r"(\d+)\s*(?:min|mn|m\b)", text, re.I)
            if hours or mins:
                minutes = int(hours.group(1)) * 60 if hours else 0
                if mins:
                    minutes += int(mins.group(1))
                elif hours and hours.group(2):
                    minutes += int(hours.group(2))  # « 1 h 15 »
            else:
                digits = re.search(r"\d+", text)
                minutes = int(digits.group()) if digits else 0
    return minutes if minutes > 0 else None


def parse_int(value) -> int | None:
    """Premier entier trouvé (« 4 personnes » → 4). Listes : premier élément utile."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            parsed = parse_int(item)
            if parsed:
                return parsed
        return None
    if isinstance(value, (int, float)):
        number = int(value)
    else:
        match = re.search(r"\d+", str(value))
        number = int(match.group()) if match else 0
    return number if number > 0 else None


# ---------------------------------------------------------------------------
# Lignes d'ingrédients
# ---------------------------------------------------------------------------

_UNICODE_FRACTIONS = {
    "½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4",
    "⅕": "1/5", "⅛": "1/8",
}

_NUMBER_WORDS = {
    "un": "1", "une": "1", "deux": "2", "trois": "3", "quatre": "4", "cinq": "5",
    "six": "6", "sept": "7", "huit": "8", "neuf": "9", "dix": "10", "douze": "12",
    "a": "1", "an": "1", "one": "1", "two": "2", "three": "3", "four": "4",
}

# (motif regex, forme canonique ou None pour garder le texte tel quel)
_UNITS = [
    (r"kilogrammes?|kilos?|kg", "kg"),
    (r"milligrammes?|mg", "mg"),
    (r"grammes?|gr\.?|g", "g"),
    (r"millilitres?|ml", "ml"),
    (r"centilitres?|cl", "cl"),
    (r"d[ée]cilitres?|dl", "dl"),
    (r"litres?|l", "l"),
    (r"cuill(?:è|e|é)res?\s+(?:à|a)\s+soupe|c\.?\s*(?:à|a)\s*soupe|c\.?\s*(?:à|a)\.?\s*s\.?|c\.?\s*s\.|càs|cas|cs"
     r"|tablespoons?|tbsp\.?", "c. à s."),
    (r"cuill(?:è|e|é)res?\s+(?:à|a)\s+caf(?:é|e)|c\.?\s*(?:à|a)\s*caf(?:é|e)|c\.?\s*(?:à|a)\.?\s*c\.?|c\.?\s*c\.|càc|cac|cc"
     r"|teaspoons?|tsp\.?", "c. à c."),
    (r"cups?", "tasse"),
    (r"ounces?|oz", "oz"),
    (r"pounds?|lbs?", "lb"),
    (r"tasses?|verres?|bols?|pinc(?:é|e)es?|pinch(?:es)?|sachets?|gousses?|cloves?"
     r"|tranches?|slices?|bo(?:î|i)tes?|cans?|pots?|feuilles?|brins?|bottes?|poign(?:é|e)es?"
     r"|morceaux|morceau|carr(?:é|e)s?|b(?:â|a)tons?|branches?|t(?:ê|e)tes?|cubes?|doses?"
     r"|barquettes?|rouleaux|rouleau|paquets?|plaquettes?|boules?|bouquets?", None),
]
# Unités qui sont aussi des ingrédients (« 100 g de noix ») : unité seulement
# quand elles sont suivies de « de » (« 1 noix de beurre »).
_UNITS_BEFORE_DE = r"noix|filets?|zestes?|traits?|quartiers?|lamelles?|gouttes?"

_NUM = r"\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?"
_MIXED = r"\d+\s+\d+\s*/\s*\d+"
_QTY = rf"(?:{_MIXED}|{_NUM})(?:\s*(?:à|-|–|to|ou|or)\s*(?:{_MIXED}|{_NUM}))?"
_UNIT_ALT = "|".join(f"(?:{pattern})" for pattern, _ in _UNITS)

_INGREDIENT_RE = re.compile(
    rf"^(?P<qty>{_QTY})?\s*"
    rf"(?:(?P<unit>{_UNIT_ALT})(?=[\s.,;:()'’]|$)\.?"
    rf"|(?P<unit_de>{_UNITS_BEFORE_DE})(?=\s+(?:de\s|d['’])))?"
    rf"\s*(?:(?:de|des|du|of)\s+|d['’])?"
    rf"(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)


def canonical_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    raw = re.sub(r"\s+", " ", unit.strip())
    for pattern, canonical in _UNITS:
        if re.fullmatch(f"(?:{pattern})", raw, re.IGNORECASE):
            return canonical or raw.lower().rstrip(".")
    return raw.lower().rstrip(".")


def parse_ingredient_line(line: str) -> dict:
    """« 2 gousses d'ail (hachées) » → quantité, unité, nom, précisions."""
    text = clean_text(line)
    text = re.sub(r"^[\s\-–•*·▪►✓✔️🔸🔹]+", "", text)
    for symbol, fraction in _UNICODE_FRACTIONS.items():
        text = re.sub(rf"(\d)\s*{symbol}", rf"\1 {fraction}", text)
        text = text.replace(symbol, fraction)
    text = re.sub(r"^(?:un|une)\s+demie?\b", "1/2", text, flags=re.I)
    words = text.split(maxsplit=1)
    if (
        len(words) == 2
        and words[0].lower() in _NUMBER_WORDS
        and not re.match(r"(?:peu|bon|petit peu)\b", words[1], re.I)
    ):
        text = f"{_NUMBER_WORDS[words[0].lower()]} {words[1]}"

    result = {"quantity": None, "unit": None, "name": text, "notes": None}
    match = _INGREDIENT_RE.match(text)
    if not match:
        return result

    quantity = match.group("qty")
    unit = match.group("unit") or match.group("unit_de")
    rest = (match.group("rest") or "").strip()

    notes = None
    lead = re.match(r"^\(([^()]*)\)\s*(?:(?:de|des|du)\s+|d['’])?(.*)$", rest, re.I | re.S)
    if lead:
        # « 250 g (ou 1 pot) de yaourt » : la parenthèse précède le nom.
        notes, rest = lead.group(1).strip() or None, lead.group(2).strip()
    paren = re.search(r"\s*\(([^()]*)\)\s*$", rest)
    if paren:
        notes = ", ".join(p for p in (notes, paren.group(1).strip()) if p) or None
        rest = rest[: paren.start()].strip()
    if (quantity or unit) and "," in rest:
        rest, extra = (part.strip() for part in rest.split(",", 1))
        notes = ", ".join(p for p in (extra, notes) if p) or None

    name = rest.strip(" .,;:-")
    if not name:
        return result
    result["quantity"] = re.sub(r"\s*/\s*", "/", quantity.strip()) if quantity else None
    result["unit"] = canonical_unit(unit)
    result["name"] = name
    result["notes"] = notes
    return result


# ---------------------------------------------------------------------------
# Étapes
# ---------------------------------------------------------------------------

# Numéro en tête d'étape (« 1. », « 2) », « Étape 3 : »), sans avaler
# « 10-15 minutes » ni « 1.5 cuillère ».
_STEP_PREFIX = re.compile(
    r"^\s*(?:(?:étape|etape|step)\s*\d+\s*[:.)\-–]?|\d+\s*(?:[.)](?=\s)|:|[-–]\s)|[-•*·])\s*", re.I
)
# Débuts d'étape dans un bloc : « Étape N » n'importe où, « N. » seulement en
# début de texte ou après une fin de phrase (pas « four à 180. »).
_STEP_MARKERS = re.compile(
    r"(?:^|\s)(?:étape|etape|step)\s*\d+|(?:^|(?<=[.!?:])\s+)\d+\s*[.)]\s", re.I
)


def clean_step(text) -> str:
    return _STEP_PREFIX.sub("", clean_text(text)).strip()


def _split_blob(text: str) -> list[str]:
    """Découpe une étape-bloc (« Étape 1 : … Étape 2 : … ») en étapes."""
    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) > 1:
        return lines
    markers = list(_STEP_MARKERS.finditer(text))
    if len(markers) >= 2:
        bounds = [m.start() for m in markers] + [len(text)]
        return [text[a:b] for a, b in zip(bounds, bounds[1:]) if text[a:b].strip()]
    return [text]


def flatten_instructions(instructions) -> list[str]:
    raw: list[str] = []

    def walk(item):
        if item is None:
            return
        if isinstance(item, str):
            raw.extend(_split_blob(clean_text(item)))
        elif isinstance(item, list):
            for sub in item:
                walk(sub)
        elif isinstance(item, dict):
            if item.get("itemListElement"):
                walk(item["itemListElement"])
            elif item.get("text"):
                walk(item["text"])
            elif item.get("name"):
                walk(item["name"])

    walk(instructions)
    steps: list[str] = []
    for step in (clean_step(s) for s in raw):
        if step and (not steps or steps[-1] != step):
            steps.append(step)
    return steps


# ---------------------------------------------------------------------------
# Catégorie, tags, langue
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS = {
    "petit-déjeuner": [
        "petit dejeuner", "petit-dejeuner", "breakfast", "brunch", "porridge", "overnight oats",
        "granola", "muesli", "pancake", "pancakes", "smoothie bowl", "viennoiserie",
        "brioche", "croissant", "pain perdu", "tartine",
    ],
    "boisson": [
        "boisson", "boissons", "drink", "cocktail", "mocktail", "smoothie", "jus",
        "limonade", "milkshake", "chocolat chaud", "infusion", "sirop", "latte",
    ],
    "sauce": [
        "sauce", "sauces", "vinaigrette", "pesto", "mayonnaise", "ketchup", "coulis",
        "condiment", "chutney", "marinade", "dressing", "bechamel",
    ],
    "soupe": ["soupe", "soupes", "veloute", "potage", "bouillon", "gaspacho", "gazpacho", "minestrone", "soup"],
    "apéritif": [
        "aperitif", "apero", "amuse-bouche", "amuse bouche", "tapas", "houmous", "hummus",
        "guacamole", "tapenade", "dip", "gougeres", "blinis", "feuilletes",
    ],
    "entrée": ["entree", "entrees", "starter", "starters", "terrine", "carpaccio", "verrine", "salade", "salad"],
    "snack": ["snack", "gouter", "en-cas", "encas", "energy balls", "barre", "barres", "crackers"],
    "dessert": [
        "dessert", "desserts", "gateau", "gateaux", "cake", "cookie", "cookies", "brownie",
        "brownies", "mousse au chocolat", "tiramisu", "crumble", "flan", "fondant",
        "cheesecake", "muffin", "muffins", "madeleine", "madeleines", "biscuit", "biscuits",
        "sorbet", "glaces", "glace a la vanille", "glace au chocolat", "glace vanille", "creme glacee", "creme brulee", "panna cotta", "clafoutis", "macaron", "macarons",
        "patisserie", "entremets", "fraisier", "meringue", "compote", "beignet", "beignets",
        "tarte au chocolat", "tarte aux pommes", "tarte au citron", "salade de fruits",
        "crepe", "crepes", "gaufre", "gaufres", "cupcake", "cupcakes", "financier",
    ],
    "plat": [
        "plat", "plats", "plat principal", "main course", "main dish", "dinner", "diner",
        "dejeuner", "lunch", "curry", "gratin", "lasagnes", "risotto", "tartiflette",
    ],
}
_CATEGORY_PRIORITY = list(_CATEGORY_KEYWORDS)


def guess_category(*texts) -> str:
    """Catégorie la plus probable ; le mot-clé le plus long l'emporte.

    « Salade de fruits » contient « salade » (entrée) et « salade de fruits »
    (dessert) : le plus spécifique gagne. Les textes sont passés par ordre de
    confiance (catégorie du site, titre, mots-clés) : le premier qui donne un
    résultat décide.
    """
    for text in texts:
        if not text:
            continue
        if isinstance(text, (list, tuple)):
            text = " , ".join(str(t) for t in text)
        folded = _fold(str(text))
        best, best_len = None, 0
        for category in _CATEGORY_PRIORITY:
            for keyword in _CATEGORY_KEYWORDS[category]:
                if len(keyword) > best_len and re.search(rf"(?<![\w-]){re.escape(keyword)}(?![\w-])", folded):
                    best, best_len = category, len(keyword)
        if best:
            return best
    return "plat"


def normalize_category(value, title: str = "") -> str:
    if isinstance(value, str) and value.strip().lower() in CATEGORIES:
        return value.strip().lower()
    return guess_category(value, title)


_DIET_TAGS = {
    "vegandiet": "vegan", "vegetariandiet": "végétarien", "glutenfreediet": "sans gluten",
    "lactosefreediet": "sans lactose", "lowlactosediet": "sans lactose", "halaldiet": "halal",
    "kosherdiet": "casher", "lowcaloriediet": "léger", "lowfatdiet": "léger",
    "diabeticdiet": "diabétique", "lowsaltdiet": "peu salé",
}


def normalize_tags(tags, limit: int = 5) -> list[str]:
    out: list[str] = []
    for tag in tags or []:
        text = clean_text(tag).lower().strip(" #.,;")
        if text and len(text) <= 30 and len(text.split()) <= 3 and text not in out:
            out.append(text)
    return out[:limit]


def build_tags(node: dict, title: str, category: str, total_minutes: int | None) -> list[str]:
    candidates: list[str] = []
    diets = node.get("suitableForDiet") or []
    for diet in diets if isinstance(diets, list) else [diets]:
        key = str(diet).rsplit("/", 1)[-1].lower()
        if key in _DIET_TAGS:
            candidates.append(_DIET_TAGS[key])
    keywords = node.get("keywords") or []
    if isinstance(keywords, str):
        keywords = keywords.split(",")
    folded_title = _fold(title)
    for keyword in keywords:
        folded = _fold(clean_text(keyword))
        if folded and not folded.startswith("recette") and folded != folded_title and folded != _fold(category):
            candidates.append(clean_text(keyword))
    cuisine = node.get("recipeCuisine")
    for item in cuisine if isinstance(cuisine, list) else [cuisine]:
        if item:
            candidates.append(clean_text(item))
    if total_minutes and total_minutes <= 30:
        candidates.append("rapide")
    return normalize_tags(candidates)


_FR_WORDS = {
    "de", "la", "le", "les", "et", "du", "des", "pour", "dans", "avec", "une", "un",
    "au", "aux", "sur", "en", "puis", "à", "faire", "jusqu'à", "cuire",
}
_EN_WORDS = {
    "the", "and", "of", "to", "with", "in", "for", "until", "into", "then", "cup", "cups",
    "tablespoon", "teaspoon", "add", "bake", "minutes",
}


def looks_french(text: str) -> bool:
    words = re.findall(r"[a-zà-ÿœ']+", text.lower())
    fr = sum(w in _FR_WORDS for w in words)
    en = sum(w in _EN_WORDS for w in words)
    return fr >= 4 and fr > en * 1.5


# ---------------------------------------------------------------------------
# schema.org/Recipe (JSON-LD)
# ---------------------------------------------------------------------------

def _iter_jsonld_nodes(data):
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld_nodes(item)
    elif isinstance(data, dict):
        yield data
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in data:
                yield from _iter_jsonld_nodes(data[key])


def _is_recipe_node(node: dict) -> bool:
    node_type = node.get("@type")
    types = node_type if isinstance(node_type, list) else [node_type]
    return any(isinstance(t, str) and t.rsplit("/", 1)[-1].lower() == "recipe" for t in types)


def find_jsonld_recipe(soup) -> dict | None:
    """Premier nœud schema.org/Recipe trouvé dans les <script type="application/ld+json">."""
    for script in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw)
        except ValueError:
            # JSON-LD mal formé (virgule finale, retours ligne bruts…) : on
            # tente une réparation minimale avant d'abandonner ce bloc.
            try:
                data = json.loads(re.sub(r",\s*([}\]])", r"\1", raw.replace("\n", " ")))
            except ValueError:
                continue
        for node in _iter_jsonld_nodes(data):
            if _is_recipe_node(node):
                return node
    return None


def _first_image(image) -> str | None:
    if isinstance(image, str):
        return image or None
    if isinstance(image, list):
        for item in image:
            url = _first_image(item)
            if url:
                return url
    if isinstance(image, dict):
        return _first_image(image.get("url") or image.get("contentUrl"))
    return None


def _short_description(text: str) -> str | None:
    text = clean_text(text).replace("\n", " ")
    if len(text) > 300:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        text = " ".join(sentences[:2])[:300].rstrip()
    return text or None


def jsonld_to_recipe(node: dict) -> dict | None:
    """Recette prête à enregistrer, ou None si les données sont trop incomplètes."""
    title = clean_text(node.get("name"))
    raw_ingredients = node.get("recipeIngredient") or node.get("ingredients") or []
    if isinstance(raw_ingredients, str):
        raw_ingredients = [raw_ingredients]
    ingredients = [parse_ingredient_line(line) for line in raw_ingredients if clean_text(line)]
    steps = flatten_instructions(node.get("recipeInstructions"))
    if not title or len(ingredients) < 2 or not steps:
        return None

    prep = parse_duration_minutes(node.get("prepTime"))
    cook = parse_duration_minutes(node.get("cookTime"))
    total = parse_duration_minutes(node.get("totalTime"))
    if prep is None and total:
        # Seul le total est connu : on le range en préparation pour que la
        # carte et le filtre « ≤ 30 min » affichent/filtrent le bon total.
        prep = max(total - (cook or 0), 0) or None
    category = guess_category(node.get("recipeCategory"), title, node.get("keywords"))
    content = " ".join([title] + [i["name"] for i in ingredients] + steps)

    return {
        "title": title,
        "description": _short_description(node.get("description")),
        "language": "fr" if looks_french(content) else "en",
        "category": category,
        "servings": parse_int(node.get("recipeYield")),
        "prep_time": prep,
        "cook_time": cook,
        "ingredients": ingredients,
        "steps": [{"order": i, "text": step} for i, step in enumerate(steps, 1)],
        "tags": build_tags(node, title, category, (prep or 0) + (cook or 0) or total),
        "thumbnail_url": _first_image(node.get("image")),
    }


def jsonld_to_text(node: dict) -> str:
    """Texte compact d'un nœud Recipe, pour le LLM (recette à traduire, ou incomplète)."""
    lines = []
    if node.get("name"):
        lines.append(f"Titre : {clean_text(node['name'])}")
    if node.get("description"):
        lines.append(f"Description : {clean_text(node['description'])}")
    if node.get("recipeYield"):
        lines.append(f"Portions : {node['recipeYield']}")
    for key, label in (("prepTime", "Préparation"), ("cookTime", "Cuisson"), ("totalTime", "Temps total")):
        minutes = parse_duration_minutes(node.get(key))
        if minutes:
            lines.append(f"{label} : {minutes} minutes")
    if node.get("recipeCategory"):
        lines.append(f"Catégorie : {node['recipeCategory']}")
    ingredients = node.get("recipeIngredient") or node.get("ingredients") or []
    if isinstance(ingredients, str):
        ingredients = [ingredients]
    if ingredients:
        lines.append("Ingrédients :")
        lines.extend(f"- {clean_text(i)}" for i in ingredients)
    steps = flatten_instructions(node.get("recipeInstructions"))
    if steps:
        lines.append("Étapes :")
        lines.extend(f"{n}. {s}" for n, s in enumerate(steps, 1))
    return "\n".join(lines) if (ingredients or steps) else ""


# ---------------------------------------------------------------------------
# Texte de page (quand il n'y a pas de données structurées)
# ---------------------------------------------------------------------------

_NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript", "form", "svg", "button"]
_NOISE_PREFIXES = (
    "comment", "respond", "related", "share", "sharing", "social", "newsletter", "cookie",
    "consent", "advert", "sidebar", "breadcrumb", "popup", "modal", "promo", "yarpp",
    "jp-relatedposts", "author-box", "post-navigation",
)
_RECIPE_CONTAINERS = (
    ".wprm-recipe-container", ".wprm-recipe", ".tasty-recipes", ".mv-create-card",
    ".recipe-card", ".wp-block-recipe", "[itemtype*='schema.org/Recipe']",
    "[itemtype*='schema.org/recipe']", ".easyrecipe", ".zlrecipe-container", ".recipe-content",
)


def _strip_noise(soup) -> None:
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    for element in soup.find_all(True):
        if element.decomposed or element.name in ("html", "body", "main", "article"):
            continue
        tokens = [c.lower() for c in (element.get("class") or [])]
        if element.get("id"):
            tokens.append(element["id"].lower())
        if any(token.startswith(_NOISE_PREFIXES) for token in tokens):
            element.decompose()


def extract_page_text(soup, limit: int = 15000) -> str:
    """Texte utile de la page : la carte recette si on la trouve, sinon l'article."""
    _strip_noise(soup)
    heading = soup.find("h1")
    title = heading.get_text(" ", strip=True) if heading else ""
    for selector in _RECIPE_CONTAINERS:
        container = soup.select_one(selector)
        if container:
            text = container.get_text("\n", strip=True)
            if looks_like_recipe(text):
                if title and title not in text[:300]:
                    text = f"{title}\n{text}"
                return re.sub(r"\n{3,}", "\n\n", text)[:limit]
    body = soup.find("article") or soup.find("main") or soup.body or soup
    text = body.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)[:limit]


# ---------------------------------------------------------------------------
# Détection d'une recette dans un texte libre (page, légende, sous-titres)
# ---------------------------------------------------------------------------

_QTY_UNIT = re.compile(rf"(?<![\w/])(?:{_NUM})\s*(?:{_UNIT_ALT})(?=[\s.,;:()'’]|$)", re.I)
_QTY_LINE = re.compile(r"^\s*(?:[^\w\s]{1,3}\s*)?(?:\d|½|¼|¾)", re.M)
_COOKING_VERBS = re.compile(
    r"\b(m[ée]lang\w*|ajout\w*|cuire|cuisson|faites cuire|enfourn\w*|pr[ée]chauff\w*|versez|verser"
    r"|battez|battre|coupez|couper|[ée]minc\w*|hach\w*|fondre|incorpor\w*|r[ée]serv\w*|servez|servir"
    r"|fouett\w*|p[ée]tri\w*|laiss\w*|chauff\w*|dorer|dorez|mix\w*|add|bake|preheat|stir|cook"
    r"|heat|whisk|combine|serve|chop|slice|melt|fold|blend)\b",
    re.I,
)


def ingredient_signals(text: str) -> int:
    return max(len(_QTY_UNIT.findall(text)), len(_QTY_LINE.findall(text)))


def looks_like_recipe(text: str) -> bool:
    """Assez d'indices pour qu'un texte contienne une recette."""
    if not text:
        return False
    folded = _fold(text)
    has_sections = ("ingredient" in folded) and any(
        word in folded for word in ("preparation", "etape", "instructions", "directions", "method")
    )
    return has_sections or ingredient_signals(text) >= 3


def has_full_recipe(text: str) -> bool:
    """Ingrédients ET étapes présents (pas seulement une liste de courses).

    Sert à sauter la transcription d'une vidéo quand la légende suffit : une
    description YouTube avec les seuls ingrédients ne doit pas passer, sinon
    les étapes (dites à l'oral) seraient perdues.
    """
    if not text:
        return False
    verbs = {m.group(1).lower()[:5] for m in _COOKING_VERBS.finditer(text)}
    return ingredient_signals(text) >= 3 and len(verbs) >= 3


# ---------------------------------------------------------------------------
# Sous-titres
# ---------------------------------------------------------------------------

def subtitles_to_text(raw: str) -> str:
    """VTT/SRT → texte continu, sans horodatages ni lignes répétées.

    Les sous-titres automatiques de YouTube « déroulent » : chaque bloc
    reprend la ligne précédente, d'où la déduplication sur les dernières
    lignes gardées.
    """
    kept: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if (
            not line
            or "-->" in line
            or line.isdigit()
            or line.startswith(("WEBVTT", "NOTE", "Kind:", "Language:", "STYLE", "REGION"))
        ):
            continue
        line = html_lib.unescape(re.sub(r"<[^>]+>", "", line)).strip()
        if line and line not in kept[-3:]:
            kept.append(line)
    return " ".join(kept)
