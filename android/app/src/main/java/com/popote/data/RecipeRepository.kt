package com.popote.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import com.google.gson.JsonParser
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
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
        favoritesOnly: Boolean = false,
        neverCooked: Boolean = false,
        cookAgain: Boolean = false,
        sort: String? = null,
    ): List<Recipe> = api().getRecipes(
        search = search, category = category, sourceType = sourceType, maxTime = maxTime,
        favoritesOnly = favoritesOnly.takeIf { it }, neverCooked = neverCooked.takeIf { it },
        cookAgain = cookAgain.takeIf { it }, sort = sort,
    )

    suspend fun getRecipe(id: String): Recipe = api().getRecipe(id)

    suspend fun deleteRecipe(id: String) = api().deleteRecipe(id)

    suspend fun extract(input: String): ExtractionResponse = api().extract(ExtractionRequest(input))

    /** Recette photographiée (livre, fiche manuscrite…) : lue par OCR côté serveur. */
    suspend fun extractImage(bytes: ByteArray, mimeType: String): ExtractionResponse {
        val body = bytes.toRequestBody(mimeType.toMediaTypeOrNull())
        val part = okhttp3.MultipartBody.Part.createFormData("file", "photo.jpg", body)
        return api().extractImage(part)
    }

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
    suspend fun setRating(id: String, rating: Int): Recipe = api().patchRecipe(id, mapOf("rating" to rating))
    suspend fun setCookAgain(id: String, value: Boolean): Recipe = api().patchRecipe(id, mapOf("cook_again" to value))

    // Historique
    suspend fun markCooked(id: String, date: String, rating: Int?, comment: String?): Recipe =
        api().markCooked(id, CookedRequest(date, rating, comment?.ifBlank { null }))
    suspend fun getHistory(id: String): List<CookLog> = api().getHistory(id)
    suspend fun deleteCookLog(id: String, logId: String): Recipe = api().deleteCookLog(id, logId)

    // Partage, réextraction
    suspend fun shareRecipe(id: String): Recipe = api().shareRecipe(id)
    suspend fun unshareRecipe(id: String): Recipe = api().unshareRecipe(id)
    suspend fun reextract(id: String, replaceImage: Boolean): Recipe = api().reextract(id, replaceImage)
    suspend fun generateImage(id: String): Recipe = api().generateImage(id)

    // Frigo
    suspend fun whatToCook(ingredients: List<String>, assumeStaples: Boolean): List<PantryMatch> =
        api().whatToCook(PantryRequest(ingredients, assumeStaples))

    // Carnets
    suspend fun getCollections(recipeId: String? = null): List<RecipeCollection> = api().getCollections(recipeId)
    suspend fun getCollection(id: String): RecipeCollectionDetail = api().getCollection(id)
    suspend fun createCollection(name: String, emoji: String?): RecipeCollection =
        api().createCollection(CollectionCreate(name.trim(), emoji))
    suspend fun deleteCollection(id: String) = api().deleteCollection(id)
    suspend fun addToCollection(id: String, recipeId: String) = api().addToCollection(id, recipeId)
    suspend fun removeFromCollection(id: String, recipeId: String) = api().removeFromCollection(id, recipeId)
    suspend fun shareCollection(id: String): RecipeCollection = api().shareCollection(id)
    suspend fun unshareCollection(id: String): RecipeCollection = api().unshareCollection(id)

    // Liste de courses persistée
    suspend fun getShoppingItems(): ShoppingListResponse = api().getShoppingItems()
    suspend fun generateShopping(request: GenerateShoppingRequest): ShoppingListResponse =
        api().generateShoppingItems(request)
    suspend fun addShoppingItem(name: String): ShoppingEntry = api().addShoppingItem(ShoppingItemCreate(name.trim()))
    suspend fun setShoppingChecked(id: String, checked: Boolean): ShoppingEntry =
        api().updateShoppingItem(id, mapOf("checked" to checked))
    suspend fun deleteShoppingItem(id: String) = api().deleteShoppingItem(id)
    suspend fun clearShopping(onlyChecked: Boolean) = api().clearShoppingItems(onlyChecked)
    suspend fun shareShoppingList(): ShoppingListResponse = api().shareShoppingList()
    suspend fun unshareShoppingList(): ShoppingListResponse = api().unshareShoppingList()

    /** Lien public (partage) complet, à envoyer via la feuille de partage Android. */
    suspend fun publicLink(path: String): String = apiClient.serverUrl.first().trimEnd('/') + path

    /** Message lisible d'une erreur réseau/API, pour l'afficher tel quel. */
    fun describe(e: Exception): String = when (e) {
        is HttpException -> errorDetail(e) ?: "Erreur du serveur (${e.code()})"
        is java.io.IOException -> "Serveur injoignable"
        else -> e.message ?: "Erreur inconnue"
    }
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
