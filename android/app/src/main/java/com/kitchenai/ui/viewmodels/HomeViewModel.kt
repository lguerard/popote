package com.kitchenai.ui.viewmodels

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.kitchenai.data.Recipe
import com.kitchenai.data.RecipeRepository
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

class HomeViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)

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

    val serverUrl = repo.serverUrl.stateIn(viewModelScope, SharingStarted.Eagerly, "")

    init {
        viewModelScope.launch {
            combine(_search.debounce(400), _category, _maxTime) { s, c, t -> Triple(s, c, t)
            }.collect { (s, c, t) ->
                load(s.ifBlank { null }, c, t)
            }
        }
    }

    fun load(search: String? = null, category: String? = _category.value, maxTime: Int? = _maxTime.value) {
        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null
            try {
                _recipes.value = repo.getRecipes(search = search, category = category, maxTime = maxTime)
            } catch (e: Exception) {
                _error.value = "Impossible de contacter le serveur"
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun onSearchChange(q: String) { _search.value = q }
    fun setCategory(c: String?) { _category.value = c }
    fun setMaxTime(t: Int?) { _maxTime.value = t }
    fun resetFilters() { _category.value = null; _maxTime.value = null }

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
