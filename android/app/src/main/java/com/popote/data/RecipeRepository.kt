package com.popote.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first

class RecipeRepository(private val context: Context) {
    private val apiClient = ApiClient(context)

    val serverUrl = apiClient.serverUrl

    private suspend fun api(): PopoteApi {
        val url = apiClient.serverUrl.first()
        // Le jeton est relu à chaque appel : il peut avoir changé (connexion,
        // déconnexion, changement de mot de passe) depuis la dernière requête.
        apiClient.setToken(context.dataStore.data.first()[SESSION_TOKEN_KEY])
        return apiClient.getApi(url)
    }

    suspend fun saveServerUrl(url: String) {
        context.dataStore.edit { it[SERVER_URL_KEY] = url.trimEnd('/') }
    }

    /* ------------------------------- comptes ------------------------------ */

    private suspend fun saveToken(token: String?) {
        context.dataStore.edit { prefs ->
            if (token == null) prefs.remove(SESSION_TOKEN_KEY) else prefs[SESSION_TOKEN_KEY] = token
        }
        apiClient.setToken(token)
    }

    suspend fun authStatus(): AuthStatus = api().authStatus()

    suspend fun login(email: String, password: String): AccountUser {
        val response = api().login(LoginRequest(email.trim(), password))
        saveToken(response.token)
        return response.user
    }

    suspend fun setupFirstAccount(email: String, displayName: String, password: String): AccountUser {
        val response = api().setup(SetupRequest(email.trim(), displayName.trim(), password))
        saveToken(response.token)
        return response.user
    }

    suspend fun logout() {
        // Le jeton est effacé même si le serveur est injoignable : sinon
        // l'application resterait bloquée sur un compte qu'on veut quitter.
        try {
            api().logout()
        } catch (_: Exception) {
        } finally {
            saveToken(null)
        }
    }

    suspend fun changePassword(current: String, new: String) {
        api().changePassword(ChangePasswordRequest(current, new))
        // Le serveur garde vivante la session qui fait le changement : le jeton
        // en cours reste valable, rien à re-enregistrer.
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
