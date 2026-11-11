"""Remplacements d'ingrédients éprouvés, avec leurs proportions.

L'assistant tourne sur un petit modèle local : laissé seul, il propose
volontiers « remplacez les œufs par de l'eau ». Cette table lui donne les
équivalences classiques, quantités comprises, qu'il adapte ensuite à la
recette. Un ingrédient absent de la table n'est pas une erreur : le modèle
répond alors de lui-même, en le disant.
"""

from . import grocery

# (noms qui désignent l'ingrédient, remplacements « quoi : combien, quand »)
_TABLE: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("œuf", "oeuf"), (
        "1 œuf = 1 c. à s. de graines de lin moulues + 3 c. à s. d'eau, 10 min de repos (gâteaux, cookies, galettes)",
        "1 œuf = 50 g de compote de pommes ou ½ banane écrasée (gâteaux moelleux, plus sucré)",
        "1 œuf = 60 g de yaourt nature (gâteaux, pancakes)",
        "1 blanc = 2 c. à s. d'aquafaba (jus de pois chiches), se monte en neige comme un blanc",
    )),
    (("beurre",), (
        "100 g de beurre = 80 g d'huile neutre (gâteaux, muffins ; pas pour une pâte feuilletée)",
        "100 g de beurre = 100 g de margarine végétale (pâtisserie, pâtes à tarte)",
        "100 g de beurre = 100 g de purée d'amande ou de cacahuète (cookies, brownies)",
        "dans un gâteau, la moitié du beurre peut devenir de la compote de pommes",
    )),
    (("lait",), (
        "lait végétal (soja, avoine, amande) à volume égal ; le soja est le plus proche en cuisson",
        "moitié eau, moitié crème liquide, pour une sauce ou une béchamel",
    )),
    (("lait de coco",), (
        "crème liquide à volume égal (moins parfumé)",
        "yaourt nature allongé d'un peu d'eau, ajouté hors du feu",
    )),
    (("crème liquide", "crème entière", "crème fleurette", "crème"), (
        "crème végétale (soja, avoine, coco) à volume égal ; seule la crème de coco bien froide se fouette",
        "lait + 1 c. à s. de fécule de maïs pour 25 cl, pour lier une sauce",
        "lait de coco dans un curry ou un plat épicé",
    )),
    (("crème fraîche", "crème épaisse"), (
        "yaourt grec ou fromage blanc à poids égal, ajouté hors du feu (il tranche s'il bout)",
        "crème liquide + quelques gouttes de jus de citron",
        "crème végétale épaisse (soja, avoine) à poids égal",
    )),
    (("yaourt",), (
        "skyr, fromage blanc ou yaourt végétal à poids égal",
        "crème fraîche allongée d'un peu de lait",
    )),
    (("babeurre", "lait ribot", "buttermilk", "lait fermenté"), (
        "25 cl de lait + 1 c. à s. de jus de citron ou de vinaigre, 10 min de repos",
        "moitié yaourt, moitié lait",
    )),
    (("mascarpone",), (
        "ricotta égouttée + 2 c. à s. de crème liquide pour 250 g",
        "fromage frais type Saint-Moret ou cream cheese à poids égal (plus acidulé)",
    )),
    (("parmesan",), (
        "pecorino ou grana padano à poids égal (le pecorino est plus salé)",
        "2 c. à s. de levure maltée pour 30 g (version végane)",
    )),
    (("farine de blé", "farine"), (
        "pour lier une sauce : fécule de maïs, deux fois moins que de farine",
        "pâtisserie sans gluten : 70 % farine de riz + 30 % fécule, poids égal au total",
        "jusqu'à un quart de la farine en poudre d'amande dans un gâteau (plus moelleux)",
    )),
    (("fécule de maïs", "maïzena", "fécule"), (
        "fécule de pomme de terre ou arrow-root à poids égal",
        "farine de blé, deux fois plus que de fécule (sauce un peu moins brillante)",
    )),
    (("levure chimique",), (
        "1 sachet (11 g) = ½ c. à c. de bicarbonate + 1 c. à s. de jus de citron ou de vinaigre",
        "½ c. à c. de bicarbonate si la pâte contient déjà yaourt ou babeurre",
    )),
    (("sucre",), (
        "sucre complet, rapadura ou sucre de coco à poids égal (goût plus caramélisé)",
        "miel ou sirop d'érable : ¾ du poids, et 2 c. à s. de liquide en moins pour 100 g",
    )),
    (("miel",), ("sirop d'érable ou sirop d'agave à volume égal",)),
    (("chocolat noir", "chocolat"), (
        "30 g de chocolat noir = 3 c. à s. de cacao non sucré + 1 c. à s. de beurre ou d'huile + 1 c. à s. de sucre",
    )),
    (("gélatine",), (
        "agar-agar : 2 g pour 6 feuilles (12 g) de gélatine, à faire bouillir 1 à 2 min ; il prend à température ambiante",
    )),
    (("vin blanc",), (
        "bouillon de volaille ou de légumes + 1 c. à s. de vinaigre de cidre ou de jus de citron pour 25 cl",
        "jus de raisin blanc + un trait de vinaigre (sauces sucrées-salées)",
    )),
    (("vin rouge",), (
        "bouillon de bœuf ou de légumes + 1 c. à s. de vinaigre balsamique pour 25 cl",
        "jus de raisin rouge + un trait de vinaigre",
    )),
    (("jus de citron", "citron"), (
        "citron vert à volume égal",
        "vinaigre de cidre ou de vin blanc, moitié moins (plus acide)",
    )),
    (("échalote",), ("½ oignon pour 2 échalotes, + une pointe d'ail",)),
    (("ail",), ("1 gousse = ¼ c. à c. d'ail en poudre, ou ½ c. à c. d'ail semoule",)),
    (("herbes fraîches", "persil", "basilic", "coriandre", "ciboulette"), (
        "herbes séchées : 1 c. à c. pour 1 c. à s. de fraîches, ajoutées en début de cuisson",
        "basilic → pesto (1 c. à s.) ; coriandre → persil + zeste de citron vert",
    )),
    (("sauce soja",), (
        "tamari à volume égal (sans gluten)",
        "un peu de bouillon corsé + une pincée de sel",
    )),
    (("chapelure",), (
        "biscottes ou crackers écrasés, flocons d'avoine mixés, ou poudre d'amande (sans gluten)",
    )),
    (("viande hachée", "bœuf haché", "steak haché"), (
        "lentilles vertes ou corail cuites, poids égal (bolognaise, chili)",
        "protéines de soja texturées : un tiers du poids, réhydratées dans un bouillon",
        "champignons hachés et revenus, moitié-moitié avec la viande",
    )),
    (("poulet",), (
        "pois chiches ou tofu ferme dans un curry ou un plat mijoté, poids égal",
        "dinde à poids égal",
    )),
    (("lardons",), (
        "lardons de volaille à poids égal",
        "tofu fumé en dés ou champignons + 1 c. à c. de paprika fumé (végétarien)",
    )),
]


def _tokens(name: str) -> frozenset[str]:
    return frozenset(grocery.ingredient_tokens(name))


_INDEX = [(_tokens(name), name, options) for names, options in _TABLE for name in names]


def lookup(ingredient: str) -> tuple[str, list[str]] | None:
    """(nom reconnu, remplacements) pour l'ingrédient, ou None s'il est inconnu.

    Le nom le plus précis l'emporte : « lait de coco » avant « lait »,
    « crème fraîche » avant « crème ».
    """
    query = _tokens(ingredient)
    best = None
    for key, name, options in _INDEX:
        if key and key <= query and (best is None or len(key) > len(best[0])):
            best = (key, name, options)
    return (best[1], list(best[2])) if best else None
