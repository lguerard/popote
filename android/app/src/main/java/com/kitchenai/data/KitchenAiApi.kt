package com.kitchenai.data

import retrofit2.http.*
import retrofit2.http.PATCH

interface KitchenAiApi {
    @GET("api/recipes")
    suspend fun getRecipes(
        @Query("search") search: String? = null,
        @Query("category") category: String? = null,
        @Query("source_type") sourceType: String? = null,
        @Query("max_time") maxTime: Int? = null,
        @Query("page") page: Int = 1,
        @Query("limit") limit: Int = 100,
    ): List<Recipe>

    @GET("api/recipes/{id}")
    suspend fun getRecipe(@Path("id") id: String): Recipe

    @DELETE("api/recipes/{id}")
    suspend fun deleteRecipe(@Path("id") id: String)

    @POST("api/extract")
    suspend fun extract(@Body body: ExtractionRequest): ExtractionResponse

    @GET("api/tasks/{id}")
    suspend fun getTask(@Path("id") id: String): Recipe

    @POST("api/recipes/{id}/favorite")
    suspend fun toggleFavorite(@Path("id") id: String): Recipe

    @PATCH("api/recipes/{id}")
    suspend fun patchRecipe(@Path("id") id: String, @Body body: Map<String, String?>): Recipe

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
