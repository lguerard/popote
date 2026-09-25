import pytest

from app.services import grocery


@pytest.mark.parametrize("name, aisle", [
    ("Lait de coco", "Épicerie salée"),
    ("lait", "Crèmerie et œufs"),
    ("Lait d'amande", "Boissons"),
    ("Beurre de cacahuète", "Épicerie sucrée"),
    ("gingembre en poudre", "Épices et condiments"),
    ("gingembre frais", "Fruits et légumes"),
    ("thym", "Épices et condiments"),
    ("thym frais", "Fruits et légumes"),
    ("Blancs de poulet émincés", "Boucherie et poissonnerie"),
    ("Pâte feuilletée", "Boulangerie"),
    ("pâtes", "Épicerie salée"),
    ("petits pois surgelés", "Surgelés"),
    ("Poivron rouge", "Fruits et légumes"),
    ("poivre noir", "Épices et condiments"),
    ("jus de citron", "Fruits et légumes"),
    ("œufs", "Crèmerie et œufs"),
    ("Vin blanc sec", "Boissons"),
    ("papier cuisson", "Autres"),
])
def test_guess_aisle(name, aisle):
    assert grocery.guess_aisle(name) == aisle


@pytest.mark.parametrize("raw, expected", [
    ("1/2", 0.5), ("1 1/2", 1.5), ("1,5", 1.5), ("2-3", 3.0), ("200", 200.0),
    ("", None), (None, None), ("une pincée", None),
])
def test_parse_quantity(raw, expected):
    assert grocery.parse_quantity(raw) == expected


def test_merge_sums_compatible_units_and_skips_tap_water():
    items = grocery.merge_ingredients([
        ("Pain", [
            {"quantity": "500", "unit": "g", "name": "farine"},
            {"quantity": "30", "unit": "cl", "name": "eau tiède"},
            {"quantity": "20", "unit": "cl", "name": "lait"},
        ]),
        ("Crêpes", [
            {"quantity": "1", "unit": "kg", "name": "Farine"},
            {"quantity": "150", "unit": "ml", "name": "lait"},
            {"quantity": "1/2", "name": "citron"},
        ]),
    ])
    by_name = {i["name"].lower(): i for i in items}
    assert "eau tiède" not in by_name
    assert (by_name["farine"]["quantity"], by_name["farine"]["unit"]) == ("1.5", "kg")
    assert by_name["farine"]["recipes"] == ["Pain", "Crêpes"]
    assert (by_name["lait"]["quantity"], by_name["lait"]["unit"]) == ("35", "cl")
    assert by_name["citron"]["quantity"] == "1/2"


def test_merge_rounds_countable_items_up_and_keeps_incompatible_units_apart():
    items = grocery.merge_ingredients([
        ("A", [{"quantity": "2", "name": "œufs"}, {"quantity": "1", "unit": "c. à s.", "name": "sucre"}]),
        ("B", [{"quantity": "1/2", "name": "oeuf"}, {"quantity": "100", "unit": "g", "name": "sucre"}]),
    ])
    eggs = [i for i in items if i["name"].lower().startswith(("œuf", "oeuf"))]
    assert len(eggs) == 1 and eggs[0]["quantity"] == "3"
    assert len([i for i in items if i["name"].lower() == "sucre"]) == 2


def test_merge_is_sorted_by_aisle():
    items = grocery.merge_ingredients([("X", [
        {"name": "sel"}, {"name": "carotte"}, {"name": "poulet"},
    ])])
    assert [i["aisle"] for i in items] == [
        "Fruits et légumes", "Boucherie et poissonnerie", "Épices et condiments",
    ]


def test_rank_by_pantry_orders_by_missing_then_matches():
    recipes = [
        {"id": "salade", "ingredients": [
            {"name": "tomates cerises"}, {"name": "mozzarella"}, {"name": "sel"}, {"name": "basilic"},
        ]},
        {"id": "caprese", "ingredients": [{"name": "tomate"}, {"name": "mozzarella"}]},
        {"id": "curry", "ingredients": [{"name": "poulet"}, {"name": "lait de coco"}]},
    ]
    ranked = grocery.rank_by_pantry(recipes, ["Tomates", "mozzarella di bufala"])
    assert [r["recipe"]["id"] for r in ranked] == ["caprese", "salade"]
    assert ranked[1]["missing"] == ["basilic"]  # le sel ne compte pas
    assert ranked[0]["coverage"] == 1.0


def test_rank_by_pantry_counts_staples_when_asked():
    recipes = [{"id": "r", "ingredients": [{"name": "œufs"}, {"name": "sel"}]}]
    ranked = grocery.rank_by_pantry(recipes, ["oeufs"], assume_staples=False)
    assert ranked[0]["missing"] == ["sel"]
    assert grocery.rank_by_pantry(recipes, []) == []
