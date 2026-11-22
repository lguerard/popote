package com.popote.ui.viewmodels

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.popote.data.Recipe
import com.popote.data.RecipeRepository
import java.time.LocalDate
import java.time.LocalTime
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

/** Le haut de l'accueil : le repas prévu, les courses, la semaine. */
data class Dashboard(
    /** Recette prévue au planning pour le prochain repas du jour (midi, puis soir). */
    val tonight: Recipe? = null,
    /** « déjeuner » ou « dîner ». */
    val tonightMeal: String? = null,
    /** Articles de la liste de courses pas encore cochés (null : liste pas lue). */
    val shoppingLeft: Int? = null,
    /** Pour les 7 jours à venir : un dîner est-il prévu ? */
    val weekDinners: List<Boolean> = emptyList(),
)

class HomeViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)

    private val _dashboard = MutableStateFlow(Dashboard())
    val dashboard: StateFlow<Dashboard> = _dashboard.asStateFlow()

    /** Relu à chaque retour sur l'accueil : le planning ou les courses ont pu changer. */
    fun loadDashboard() {
        viewModelScope.launch {
            val today = LocalDate.now()
            val plans = runCatching { repo.getMealPlans(today.toString(), today.plusDays(6).toString()) }.getOrNull()
            val todays = plans.orEmpty().filter { it.date == today.toString() }
            // Avant 14 h, le déjeuner d'abord ; ensuite le dîner.
            val order = if (LocalTime.now().hour < 14) listOf("déjeuner", "dîner") else listOf("dîner")
            val plan = order.firstNotNullOfOrNull { meal -> todays.firstOrNull { it.meal_type == meal } }
            val recipe = plan?.let { runCatching { repo.getRecipe(it.recipe_id) }.getOrNull() }
            val shopping = runCatching { repo.getShoppingItems() }.getOrNull()
            _dashboard.value = Dashboard(
                tonight = recipe,
                tonightMeal = plan?.meal_type,
                shoppingLeft = shopping?.items?.count { !it.checked },
                weekDinners = if (plans == null) emptyList() else (0L..6L).map { d ->
                    val day = today.plusDays(d).toString()
                    plans.any { it.date == day && it.meal_type == "dîner" }
                },
            )
        }
    }

    private val _recipes = MutableStateFlow<List<Recipe>>(emptyList())
    val recipes: StateFlow<List<Recipe>> = _recipes.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _search = MutableStateFlow("")
    val search: StateFlow<String> = _search.asStateFlow()

    private val _category = MutableStateFlow<String?>(null)
    val category: StateFlow<String?> = _category.asStateFlow()

    private val _maxTime = MutableStateFlow<Int?>(null)
    val maxTime: StateFlow<Int?> = _maxTime.asStateFlow()

    // "favorites" | "never_cooked" | "cook_again" | null
    private val _history = MutableStateFlow<String?>(null)
    val history: StateFlow<String?> = _history.asStateFlow()

    private val _sort = MutableStateFlow("recent")
    val sort: StateFlow<String> = _sort.asStateFlow()

    private val _refreshing = MutableStateFlow(false)
    val refreshing: StateFlow<Boolean> = _refreshing.asStateFlow()

    val serverUrl = repo.serverUrl.stateIn(viewModelScope, SharingStarted.Eagerly, "")

    init {
        viewModelScope.launch {
            combine(_search.debounce(400), _category, _maxTime, _history, _sort) { _, _, _, _, _ -> Unit }
                .collect { load() }
        }
    }

    fun load(pullToRefresh: Boolean = false) {
        viewModelScope.launch {
            if (pullToRefresh) _refreshing.value = true
            // Pas de grand spinner quand une liste est déjà affichée : elle
            // reste visible le temps de la mise à jour.
            else if (_recipes.value.isEmpty()) _isLoading.value = true
            _error.value = null
            try {
                val h = _history.value
                _recipes.value = repo.getRecipes(
                    search = _search.value.ifBlank { null },
                    category = _category.value,
                    maxTime = _maxTime.value,
                    favoritesOnly = h == "favorites",
                    neverCooked = h == "never_cooked",
                    cookAgain = h == "cook_again",
                    shared = h == "shared",
                    sort = _sort.value.takeIf { it != "recent" },
                )
            } catch (e: Exception) {
                _error.value = repo.describe(e)
            } finally {
                _isLoading.value = false
                _refreshing.value = false
            }
        }
    }

    fun setHistory(h: String?) { _history.value = h }
    fun setSort(s: String) { _sort.value = s }

    fun onSearchChange(q: String) { _search.value = q }
    fun setCategory(c: String?) { _category.value = c }
    fun setMaxTime(t: Int?) { _maxTime.value = t }
    fun resetFilters() { _category.value = null; _maxTime.value = null; _history.value = null }

    fun deleteRecipe(id: String) {
        viewModelScope.launch {
            try {
                repo.deleteRecipe(id)
                _recipes.value = _recipes.value.filter { it.id != id }
            } catch (e: Exception) {
                _error.value = "Erreur lors de la suppression"
            }
        }
    }
}
