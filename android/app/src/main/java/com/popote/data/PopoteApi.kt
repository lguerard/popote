package com.popote.data

import retrofit2.http.*
import retrofit2.http.PATCH

interface PopoteApi {
    @POST("api/auth/login")
    suspend fun login(@Body body: LoginRequest): LoginResponse

    @GET("api/recipes")
    suspend fun getRecipes(
        @Query("search") search: String? = null,
        @Query("category") category: String? = null,
        @Query("source_type") sourceType: String? = null,
        @Query("max_time") maxTime: Int? = null,
        @Query("favorites_only") favoritesOnly: Boolean? = null,
        @Query("never_cooked") neverCooked: Boolean? = null,
        @Query("cook_again") cookAgain: Boolean? = null,
        @Query("sort") sort: String? = null,
        @Query("page") page: Int = 1,
        @Query("limit") limit: Int = 1000,
    ): List<Recipe>

    @GET("api/recipes/{id}")
    suspend fun getRecipe(@Path("id") id: String): Recipe

    @DELETE("api/recipes/{id}")
    suspend fun deleteRecipe(@Path("id") id: String)

    @POST("api/extract")
    suspend fun extract(@Body body: ExtractionRequest): ExtractionResponse

    @Multipart
    @POST("api/extract/image")
    suspend fun extractImage(@Part file: okhttp3.MultipartBody.Part): ExtractionResponse

    @GET("api/tasks/{id}")
    suspend fun getTask(@Path("id") id: String): Recipe

    @POST("api/recipes/{id}/favorite")
    suspend fun toggleFavorite(@Path("id") id: String): Recipe

    @PATCH("api/recipes/{id}")
    suspend fun patchRecipe(@Path("id") id: String, @Body body: Map<String, @JvmSuppressWildcards Any?>): Recipe

    // Historique et avis
    @POST("api/recipes/{id}/cooked")
    suspend fun markCooked(@Path("id") id: String, @Body body: CookedRequest): Recipe

    @GET("api/recipes/{id}/history")
    suspend fun getHistory(@Path("id") id: String): List<CookLog>

    @DELETE("api/recipes/{id}/history/{logId}")
    suspend fun deleteCookLog(@Path("id") id: String, @Path("logId") logId: String): Recipe

    // Partage, réextraction
    @POST("api/recipes/{id}/share")
    suspend fun shareRecipe(@Path("id") id: String): Recipe

    @DELETE("api/recipes/{id}/share")
    suspend fun unshareRecipe(@Path("id") id: String): Recipe

    @POST("api/recipes/{id}/reextract")
    suspend fun reextract(@Path("id") id: String, @Query("replace_image") replaceImage: Boolean): Recipe

    // Frigo
    @POST("api/recipes/what-to-cook")
    suspend fun whatToCook(@Body body: PantryRequest): List<PantryMatch>

    // Carnets
    @GET("api/collections")
    suspend fun getCollections(@Query("recipe_id") recipeId: String? = null): List<RecipeCollection>

    @GET("api/collections/{id}")
    suspend fun getCollection(@Path("id") id: String): RecipeCollectionDetail

    @POST("api/collections")
    suspend fun createCollection(@Body body: CollectionCreate): RecipeCollection

    @DELETE("api/collections/{id}")
    suspend fun deleteCollection(@Path("id") id: String)

    @PUT("api/collections/{id}/recipes/{recipeId}")
    suspend fun addToCollection(@Path("id") id: String, @Path("recipeId") recipeId: String)

    @DELETE("api/collections/{id}/recipes/{recipeId}")
    suspend fun removeFromCollection(@Path("id") id: String, @Path("recipeId") recipeId: String)

    @POST("api/collections/{id}/share")
    suspend fun shareCollection(@Path("id") id: String): RecipeCollection

    @DELETE("api/collections/{id}/share")
    suspend fun unshareCollection(@Path("id") id: String): RecipeCollection

    // Liste de courses persistée
    @GET("api/shopping/items")
    suspend fun getShoppingItems(): ShoppingListResponse

    @POST("api/shopping/items/generate")
    suspend fun generateShoppingItems(@Body body: GenerateShoppingRequest): ShoppingListResponse

    @POST("api/shopping/items")
    suspend fun addShoppingItem(@Body body: ShoppingItemCreate): ShoppingEntry

    @PATCH("api/shopping/items/{id}")
    suspend fun updateShoppingItem(@Path("id") id: String, @Body body: Map<String, @JvmSuppressWildcards Any?>): ShoppingEntry

    @DELETE("api/shopping/items/{id}")
    suspend fun deleteShoppingItem(@Path("id") id: String)

    @DELETE("api/shopping/items")
    suspend fun clearShoppingItems(@Query("only_checked") onlyChecked: Boolean)

    @POST("api/shopping/share")
    suspend fun shareShoppingList(): ShoppingListResponse

    @DELETE("api/shopping/share")
    suspend fun unshareShoppingList(): ShoppingListResponse

    @POST("api/recipes/{id}/nutrition")
    suspend fun analyzeNutrition(@Path("id") id: String): Nutrition

    @POST("api/shopping-list")
    suspend fun getShoppingList(@Body body: ShoppingListRequest): List<ShoppingItem>

    @GET("api/meal-plans")
    suspend fun getMealPlans(
        @Query("date_from") dateFrom: String? = null,
        @Query("date_to") dateTo: String? = null,
    ): List<MealPlan>

    @POST("api/meal-plans")
    suspend fun createMealPlan(@Body body: MealPlanCreate): MealPlan

    @DELETE("api/meal-plans/{id}")
    suspend fun deleteMealPlan(@Path("id") id: String)

    @GET("api/achievements")
    suspend fun getAchievements(): List<Achievement>

    @POST("api/achievements/cooking-mode")
    suspend fun trackCookingMode(): Map<String, Boolean>

    @GET("api/health")
    suspend fun health(): Map<String, String>
}
