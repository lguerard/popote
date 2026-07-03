package com.kitchenai.data

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
    val is_favorite: Boolean = false,
    val notes: String? = null,
    val nutrition: Nutrition? = null,
    val similar_recipe_id: String? = null,
    val created_at: String,
    val updated_at: String,
) {
    val totalTime get() = (prep_time ?: 0) + (cook_time ?: 0)
}

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
