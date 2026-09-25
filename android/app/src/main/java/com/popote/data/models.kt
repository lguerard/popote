package com.popote.data

data class Recipe(
    val id: String,
    val title: String,
    val description: String?,
    val source_url: String?,
    val source_type: String,
    val language: String?,
    val category: String?,
    val servings: Int?,
    val prep_time: Int?,
    val cook_time: Int?,
    val ingredients: List<Ingredient>,
    val steps: List<Step>,
    val tags: List<String>,
    val thumbnail_url: String?,
    val status: String,
    val error_msg: String?,
    val progress_message: String? = null,
    val is_favorite: Boolean = false,
    val notes: String? = null,
    val nutrition: Nutrition? = null,
    val similar_recipe_id: String? = null,
    val created_at: String,
    val updated_at: String,
    // Champs ajoutés côté serveur : nullables car Gson ne passe pas par le
    // constructeur (une valeur absente du JSON reste null, jamais la valeur
    // par défaut Kotlin).
    val rating: Int? = null,
    val cook_again: Boolean? = null,
    val cooked_count: Int = 0,
    val last_cooked_at: String? = null,
    val share_token: String? = null,
    val reextracting: Boolean = false,
    val thumbnail_generating: Boolean = false,
    val thumbnail_error: String? = null,
) {
    val totalTime get() = (prep_time ?: 0) + (cook_time ?: 0)
}

// ── Historique ────────────────────────────────────────────────────────────────

data class CookLog(val id: String, val cooked_on: String, val rating: Int?, val comment: String?)
data class CookedRequest(val cooked_on: String? = null, val rating: Int? = null, val comment: String? = null)

// ── Liste de courses persistée ───────────────────────────────────────────────

data class ShoppingEntry(
    val id: String,
    val name: String,
    val quantity: String?,
    val unit: String?,
    val aisle: String?,
    val recipes: List<String>?,
    val checked: Boolean,
)

data class ShoppingListResponse(
    val items: List<ShoppingEntry>?,
    val aisles: List<String>?,
    val share_token: String?,
)

data class GenerateShoppingRequest(
    val recipe_ids: List<String> = emptyList(),
    val date_from: String? = null,
    val date_to: String? = null,
    val replace: Boolean = true,
)

data class ShoppingItemCreate(val name: String)

// ── Frigo ─────────────────────────────────────────────────────────────────────

data class PantryRequest(val ingredients: List<String>, val assume_staples: Boolean = true)
data class PantryMatch(val recipe: Recipe, val matched: List<String>?, val missing: List<String>?, val coverage: Double)

// ── Carnets ───────────────────────────────────────────────────────────────────

data class RecipeCollection(
    val id: String,
    val name: String,
    val emoji: String?,
    val description: String?,
    val share_token: String?,
    val recipe_count: Int,
    val covers: List<String>?,
    val contains_recipe: Boolean?,
)

data class RecipeCollectionDetail(
    val id: String,
    val name: String,
    val emoji: String?,
    val description: String?,
    val share_token: String?,
    val recipe_count: Int,
    val recipes: List<Recipe>?,
)

data class CollectionCreate(val name: String, val emoji: String? = null, val description: String? = null)

data class Nutrition(
    val calories: Double?,
    val proteins: Double?,
    val carbs: Double?,
    val fat: Double?,
    val fiber: Double?,
)

data class MealPlan(
    val id: String,
    val date: String,
    val meal_type: String,
    val recipe_id: String,
    val recipe_title: String?,
    val recipe_thumbnail: String?,
)

data class MealPlanCreate(
    val date: String,
    val meal_type: String,
    val recipe_id: String,
    val recipe_title: String? = null,
    val recipe_thumbnail: String? = null,
)

data class ShoppingListRequest(val recipe_ids: List<String>)
data class ShoppingItem(val name: String, val quantity: String?, val unit: String?, val recipes: List<String>)

data class Ingredient(
    val quantity: String?,
    val unit: String?,
    val name: String,
    val notes: String?,
)

data class Step(
    val order: Int,
    val text: String,
)

data class ExtractionRequest(val input: String)

data class ExtractionResponse(
    val recipe_id: String,
    val status: String,
    val message: String,
)

data class LoginRequest(val email: String, val password: String)
data class AuthUser(val id: String, val email: String, val display_name: String)
data class LoginResponse(val access_token: String, val user: AuthUser)
