"""Lightweight mock server for Popote screenshot generation in CI."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

NOW = "2026-06-29T12:00:00"

RECIPES = [
    {
        "id": "1", "title": "Boeuf Bourguignon",
        "description": "Un classique de la cuisine française mijotée.",
        "source_url": "https://www.youtube.com/watch?v=example",
        "source_type": "video", "language": "fr", "category": "Plats",
        "servings": 4, "prep_time": 30, "cook_time": 180,
        "ingredients": [
            {"quantity": "800", "unit": "g", "name": "boeuf à braiser", "notes": None},
            {"quantity": "1", "unit": "bouteille", "name": "vin rouge Bourgogne", "notes": None},
            {"quantity": "200", "unit": "g", "name": "lardons", "notes": None},
            {"quantity": "3", "unit": None, "name": "carottes", "notes": "coupées en rondelles"},
            {"quantity": "2", "unit": None, "name": "oignons", "notes": None},
            {"quantity": "1", "unit": "bouquet", "name": "garni", "notes": None},
        ],
        "steps": [
            {"order": 1, "text": "Faire mariner le boeuf dans le vin rouge avec les carottes et oignons pendant 12 heures."},
            {"order": 2, "text": "Faire revenir les lardons dans une cocotte. Ajouter la viande égouttée et faire dorer 10 minutes."},
            {"order": 3, "text": "Verser la marinade, ajouter le bouquet garni. Porter à ébullition puis mijoter 2h30 à feu doux."},
            {"order": 4, "text": "Rectifier l'assaisonnement. Servir avec des pommes de terre vapeur."},
        ],
        "tags": ["boeuf", "mijoté", "hiver"], "thumbnail_url": None,
        "status": "done", "error_msg": None,
        "is_favorite": True, "notes": "Encore meilleur réchauffé le lendemain !",
        "nutrition": {"calories": 520.0, "proteins": 42.0, "carbs": 12.0, "fat": 28.0, "fiber": 3.0},
        "similar_recipe_id": None, "created_at": NOW, "updated_at": NOW,
    },
    {
        "id": "2", "title": "Tarte Tatin aux Pommes",
        "description": "La tarte renversée aux pommes caramélisées.",
        "source_url": "https://marmiton.org/recettes/tarte-tatin",
        "source_type": "web", "language": "fr", "category": "Desserts",
        "servings": 6, "prep_time": 20, "cook_time": 35,
        "ingredients": [
            {"quantity": "6", "unit": None, "name": "pommes Golden", "notes": "pelées et coupées en quartiers"},
            {"quantity": "100", "unit": "g", "name": "beurre demi-sel", "notes": None},
            {"quantity": "150", "unit": "g", "name": "sucre", "notes": None},
            {"quantity": "1", "unit": None, "name": "pâte feuilletée", "notes": "ronde 28 cm"},
        ],
        "steps": [
            {"order": 1, "text": "Préchauffer le four à 200°C. Faire fondre le beurre dans une poêle allant au four."},
            {"order": 2, "text": "Ajouter le sucre et caraméliser 5 minutes. Disposer les pommes en rosace dans le caramel."},
            {"order": 3, "text": "Couvrir avec la pâte feuilletée en rentrant les bords. Enfourner 30 minutes."},
            {"order": 4, "text": "Laisser tiédir 5 minutes puis retourner sur un plat. Servir tiède."},
        ],
        "tags": ["pommes", "dessert", "caramel"], "thumbnail_url": None,
        "status": "done", "error_msg": None,
        "is_favorite": False, "notes": None,
        "nutrition": {"calories": 380.0, "proteins": 3.0, "carbs": 58.0, "fat": 16.0, "fiber": 2.0},
        "similar_recipe_id": None, "created_at": NOW, "updated_at": NOW,
    },
    {
        "id": "3", "title": "Pad Thaï au Poulet",
        "description": "Le plat de nouilles thaïlandaises le plus populaire.",
        "source_url": None, "source_type": "text", "language": "fr", "category": "Cuisine du monde",
        "servings": 2, "prep_time": 15, "cook_time": 15,
        "ingredients": [
            {"quantity": "200", "unit": "g", "name": "nouilles de riz", "notes": "trempées 30 min"},
            {"quantity": "300", "unit": "g", "name": "blanc de poulet", "notes": "émincé"},
            {"quantity": "2", "unit": None, "name": "oeufs", "notes": None},
            {"quantity": "3", "unit": "c. à soupe", "name": "sauce nuoc-mâm", "notes": None},
            {"quantity": "2", "unit": "c. à soupe", "name": "sucre de palme", "notes": None},
            {"quantity": "100", "unit": "g", "name": "germes de soja", "notes": None},
        ],
        "steps": [
            {"order": 1, "text": "Faire chauffer un wok à feu vif avec de l'huile. Faire sauter le poulet 5 minutes."},
            {"order": 2, "text": "Pousser le poulet sur le côté, casser les oeufs et brouiller."},
            {"order": 3, "text": "Ajouter les nouilles égouttées, la sauce nuoc-mâm et le sucre. Mélanger 3 minutes."},
            {"order": 4, "text": "Ajouter les germes de soja. Servir avec cacahuètes concassées et citron vert."},
        ],
        "tags": ["thaï", "nouilles", "rapide"], "thumbnail_url": None,
        "status": "done", "error_msg": None,
        "is_favorite": False, "notes": None, "nutrition": None,
        "similar_recipe_id": None, "created_at": NOW, "updated_at": NOW,
    },
    {
        "id": "4", "title": "Soupe à l'Oignon Gratinée",
        "description": "La soupe parisienne par excellence, avec son gratin de fromage.",
        "source_url": "https://www.youtube.com/watch?v=example2",
        "source_type": "video", "language": "fr", "category": "Entrées",
        "servings": 4, "prep_time": 15, "cook_time": 60,
        "ingredients": [
            {"quantity": "1", "unit": "kg", "name": "oignons", "notes": "émincés finement"},
            {"quantity": "50", "unit": "g", "name": "beurre", "notes": None},
            {"quantity": "1", "unit": "L", "name": "bouillon de boeuf", "notes": None},
            {"quantity": "200", "unit": "g", "name": "Gruyère râpé", "notes": None},
            {"quantity": "4", "unit": "tranches", "name": "pain de campagne", "notes": "grillées"},
        ],
        "steps": [
            {"order": 1, "text": "Faire fondre les oignons dans le beurre à feu doux pendant 40 minutes jusqu'à caramélisation."},
            {"order": 2, "text": "Mouiller avec le bouillon, saler, poivrer. Laisser mijoter 20 minutes."},
            {"order": 3, "text": "Répartir la soupe dans des bols allant au four. Poser une tranche de pain et couvrir de gruyère."},
            {"order": 4, "text": "Passer sous le gril du four 5 minutes jusqu'à gratinage doré."},
        ],
        "tags": ["soupe", "fromage", "hiver"], "thumbnail_url": None,
        "status": "done", "error_msg": None,
        "is_favorite": True, "notes": None, "nutrition": None,
        "similar_recipe_id": None, "created_at": NOW, "updated_at": NOW,
    },
    {
        "id": "5", "title": "Risotto aux Champignons",
        "description": "Crémeux et savoureux, un risotto aux champignons des bois.",
        "source_url": None, "source_type": "text", "language": "fr", "category": "Plats",
        "servings": 4, "prep_time": 10, "cook_time": 30,
        "ingredients": [
            {"quantity": "320", "unit": "g", "name": "riz Arborio", "notes": None},
            {"quantity": "400", "unit": "g", "name": "champignons mélangés", "notes": None},
            {"quantity": "1", "unit": "L", "name": "bouillon de légumes", "notes": "chaud"},
            {"quantity": "100", "unit": "ml", "name": "vin blanc sec", "notes": None},
            {"quantity": "80", "unit": "g", "name": "Parmesan râpé", "notes": None},
            {"quantity": "1", "unit": None, "name": "oignon", "notes": "finement émincé"},
        ],
        "steps": [
            {"order": 1, "text": "Faire revenir l'oignon dans le beurre. Ajouter le riz et nacrer 2 minutes."},
            {"order": 2, "text": "Déglacer au vin blanc. Ajouter les champignons sautés."},
            {"order": 3, "text": "Verser le bouillon louche par louche en remuant constamment pendant 18 minutes."},
            {"order": 4, "text": "Hors du feu, incorporer le parmesan et le beurre. Mantecatura 2 minutes."},
        ],
        "tags": ["champignons", "riz", "végétarien"], "thumbnail_url": None,
        "status": "done", "error_msg": None,
        "is_favorite": False, "notes": None, "nutrition": None,
        "similar_recipe_id": None, "created_at": NOW, "updated_at": NOW,
    },
]

MEAL_PLANS = [
    {"id": "mp1", "date": "2026-06-29", "meal_type": "déjeuner", "recipe_id": "1",
     "recipe_title": "Boeuf Bourguignon", "recipe_thumbnail": None},
    {"id": "mp2", "date": "2026-06-30", "meal_type": "dîner", "recipe_id": "2",
     "recipe_title": "Tarte Tatin aux Pommes", "recipe_thumbnail": None},
    {"id": "mp3", "date": "2026-07-01", "meal_type": "déjeuner", "recipe_id": "3",
     "recipe_title": "Pad Thaï au Poulet", "recipe_thumbnail": None},
    {"id": "mp4", "date": "2026-07-02", "meal_type": "petit-déjeuner", "recipe_id": "5",
     "recipe_title": "Risotto aux Champignons", "recipe_thumbnail": None},
]

ACHIEVEMENTS = [
    {"id": "first_recipe", "name": "Premier Pas", "icon": "🌟", "description": "Ajoutez votre première recette",
     "progress": 5, "goal": 1, "unlocked_at": "2026-06-01T10:00:00", "category": "collection"},
    {"id": "collection_10", "name": "Collectionneur", "icon": "📚", "description": "10 recettes dans votre collection",
     "progress": 5, "goal": 10, "unlocked_at": None, "category": "collection"},
    {"id": "collection_50", "name": "Bibliothèque", "icon": "🏛️", "description": "50 recettes dans votre collection",
     "progress": 5, "goal": 50, "unlocked_at": None, "category": "collection"},
    {"id": "collection_100", "name": "Grand Chef", "icon": "👨‍🍳", "description": "100 recettes dans votre collection",
     "progress": 5, "goal": 100, "unlocked_at": None, "category": "collection"},
    {"id": "first_cooking", "name": "En Cuisine !", "icon": "🍳", "description": "Utilisez Mode Cuisine pour la 1ère fois",
     "progress": 3, "goal": 1, "unlocked_at": "2026-06-15T19:00:00", "category": "cuisine"},
    {"id": "cooking_10", "name": "Chef Confirmé", "icon": "⭐", "description": "Mode Cuisine utilisé 10 fois",
     "progress": 3, "goal": 10, "unlocked_at": None, "category": "cuisine"},
    {"id": "cooking_50", "name": "Chef Étoilé", "icon": "🌟", "description": "Mode Cuisine utilisé 50 fois",
     "progress": 3, "goal": 50, "unlocked_at": None, "category": "cuisine"},
    {"id": "first_shopping", "name": "Organisé", "icon": "🛒", "description": "Générez votre première liste de courses",
     "progress": 1, "goal": 1, "unlocked_at": "2026-06-20T11:00:00", "category": "organisation"},
    {"id": "first_meal_plan", "name": "Planificateur", "icon": "📅", "description": "Planifiez votre première semaine",
     "progress": 4, "goal": 1, "unlocked_at": "2026-06-22T09:00:00", "category": "organisation"},
    {"id": "full_week", "name": "Semaine Complète", "icon": "🏆", "description": "Remplissez tous les repas d'une semaine",
     "progress": 4, "goal": 28, "unlocked_at": None, "category": "organisation"},
    {"id": "gourmet", "name": "Gourmet", "icon": "🍽️", "description": "Recettes dans 5 catégories différentes",
     "progress": 4, "goal": 5, "unlocked_at": None, "category": "decouverte"},
    {"id": "world_tour", "name": "Tour du Monde", "icon": "🌍", "description": "Recettes en 3 langues différentes",
     "progress": 1, "goal": 3, "unlocked_at": None, "category": "decouverte"},
    {"id": "video_hunter", "name": "Chasseur de Vidéos", "icon": "🎬", "description": "Extrayez 10 recettes depuis des vidéos",
     "progress": 2, "goal": 10, "unlocked_at": None, "category": "decouverte"},
    {"id": "first_favorite", "name": "Coup de Cœur", "icon": "❤️", "description": "Mettez une recette en favori",
     "progress": 2, "goal": 1, "unlocked_at": "2026-06-10T14:00:00", "category": "perfectionniste"},
    {"id": "nutritionniste", "name": "Nutritionniste", "icon": "🥗", "description": "Analysez la nutrition de 5 recettes",
     "progress": 1, "goal": 5, "unlocked_at": None, "category": "perfectionniste"},
    {"id": "photographe", "name": "Photographe", "icon": "📷", "description": "Ajoutez une recette par photo/OCR",
     "progress": 0, "goal": 1, "unlocked_at": None, "category": "perfectionniste"},
    {"id": "noteur", "name": "Carnet de Notes", "icon": "📝", "description": "Écrivez des notes sur 3 recettes",
     "progress": 1, "goal": 3, "unlocked_at": None, "category": "perfectionniste"},
]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence request logs

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/api/recipes":
            self._json(RECIPES)
        elif p.startswith("/api/recipes/"):
            rid = p.split("/")[3]
            r = next((x for x in RECIPES if x["id"] == rid), None)
            self._json(r or {}, 404 if not r else 200)
        elif p == "/api/meal-plans":
            self._json(MEAL_PLANS)
        elif p == "/api/achievements":
            self._json(ACHIEVEMENTS)
        elif p == "/api/health":
            self._json({"status": "ok"})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        p = self.path.split("?")[0]
        if "/favorite" in p:
            rid = p.split("/")[3]
            r = next((x for x in RECIPES if x["id"] == rid), RECIPES[0])
            self._json(r)
        elif "/nutrition" in p:
            self._json({"calories": 450.0, "proteins": 35.0, "carbs": 20.0, "fat": 22.0, "fiber": 4.0})
        elif p == "/api/shopping-list":
            self._json([
                {"name": "boeuf à braiser", "quantity": "800", "unit": "g", "recipes": ["Boeuf Bourguignon"]},
                {"name": "carottes", "quantity": "3", "unit": None, "recipes": ["Boeuf Bourguignon"]},
                {"name": "lardons", "quantity": "200", "unit": "g", "recipes": ["Boeuf Bourguignon"]},
                {"name": "oignons", "quantity": "3", "unit": None, "recipes": ["Boeuf Bourguignon", "Soupe à l'Oignon"]},
                {"name": "vin rouge Bourgogne", "quantity": "1", "unit": "bouteille", "recipes": ["Boeuf Bourguignon"]},
            ])
        elif p == "/api/meal-plans":
            self._json(MEAL_PLANS[0], 201)
        elif p == "/api/achievements/cooking-mode":
            self._json({"ok": True})
        elif p == "/api/extract":
            self._json({"recipe_id": "1", "status": "pending", "message": "Extraction en cours..."})
        else:
            self._json({"ok": True})

    def do_DELETE(self):
        self._json({}, 204)

    def do_PATCH(self):
        self._json(RECIPES[0])


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8000), Handler)
    print("Mock server running on :8000")
    server.serve_forever()
