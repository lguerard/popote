package com.popote.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import com.google.gson.JsonParser
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import retrofit2.HttpException

class RecipeRepository(private val context: Context) {
    private val apiClient = ApiClient(context)

    val serverUrl = apiClient.serverUrl
    val isLoggedIn = apiClient.token.map { it != null }
    val userName = context.dataStore.data.map { it[USER_NAME_KEY] }

    private suspend fun api(): PopoteApi {
        val url = apiClient.serverUrl.first()
        apiClient.currentToken = apiClient.token.first()
        return apiClient.getApi(url)
    }

    suspend fun login(email: String, password: String) {
        try {
            val response = api().login(LoginRequest(email.trim().lowercase(), password))
            context.dataStore.edit {
                it[TOKEN_KEY] = response.access_token
                it[USER_NAME_KEY] = response.user.display_name
            }
        } catch (e: HttpException) {
            throw Exception(errorDetail(e) ?: "Connexion impossible (erreur ${e.code()})")
        }
    }

    suspend fun logout() {
        context.dataStore.edit {
            it.remove(TOKEN_KEY)
            it.remove(USER_NAME_KEY)
        }
    }

    /** Message « detail » renvoyé par l'API FastAPI, s'il y en a un. */
    private fun errorDetail(e: HttpException): String? = try {
        val body = e.response()?.errorBody()?.string() ?: ""
        val detail = JsonParser.parseString(body).asJsonObject.get("detail")
        if (detail != null && detail.isJsonPrimitive) detail.asString else null
    } catch (_: Exception) {
        null
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

    suspend fun pollTask(id: String, onStatus: (String, String?) -> Unit): Recipe {
        while (true) {
            val task = api().getTask(id)
            onStatus(task.status, task.progress_message)
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
