package com.kitchenai.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first

class RecipeRepository(private val context: Context) {
    private val apiClient = ApiClient(context)

    val serverUrl = apiClient.serverUrl

    private suspend fun api(): KitchenAiApi {
        val url = apiClient.serverUrl.first()
        return apiClient.getApi(url)
    }

    suspend fun saveServerUrl(url: String) {
        context.dataStore.edit { it[SERVER_URL_KEY] = url.trimEnd('/') }
    }

    suspend fun getRecipes(
        search: String? = null,
        category: String? = null,
        sourceType: String? = null,
        maxTime: Int? = null,
    ): List<Recipe> = api().getRecipes(search = search, category = category, sourceType = sourceType, maxTime = maxTime)

    suspend fun getRecipe(id: String): Recipe = api().getRecipe(id)

    suspend fun deleteRecipe(id: String) = api().deleteRecipe(id)

    suspend fun extract(input: String): ExtractionResponse = api().extract(ExtractionRequest(input))

    suspend fun pollTask(id: String, onStatus: (String) -> Unit): Recipe {
        while (true) {
            val task = api().getTask(id)
            onStatus(task.status)
            when (task.status) {
                "done" -> return task
                "failed" -> throw Exception(task.error_msg ?: "Extraction échouée")
                else -> delay(2000)
            }
        }
    }

    suspend fun toggleFavorite(id: String): Recipe = api().toggleFavorite(id)
    suspend fun updateNotes(id: String, notes: String) { api().patchRecipe(id, mapOf("notes" to notes)) }
    suspend fun analyzeNutrition(id: String): Nutrition = api().analyzeNutrition(id)
    suspend fun getShoppingList(ids: List<String>): List<ShoppingItem> = api().getShoppingList(ShoppingListRequest(ids))
    suspend fun getMealPlans(dateFrom: String? = null, dateTo: String? = null): List<MealPlan> = api().getMealPlans(dateFrom, dateTo)
    suspend fun createMealPlan(data: MealPlanCreate): MealPlan = api().createMealPlan(data)
    suspend fun deleteMealPlan(id: String) = api().deleteMealPlan(id)

    suspend fun getAchievements(): List<Achievement> = api().getAchievements()
    suspend fun trackCookingMode() = try { api().trackCookingMode() } catch (_: Exception) {}

    suspend fun checkHealth(): Boolean = try {
        api().health()
        true
    } catch (e: Exception) {
        false
    }
}
