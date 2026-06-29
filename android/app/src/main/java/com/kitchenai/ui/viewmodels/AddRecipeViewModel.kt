package com.kitchenai.ui.viewmodels

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.kitchenai.data.RecipeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class AddState {
    object Idle : AddState()
    object Submitting : AddState()
    data class Polling(val recipeId: String, val statusLabel: String) : AddState()
    data class Success(val recipeId: String) : AddState()
    data class Error(val message: String) : AddState()
}

class AddRecipeViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)

    private val _state = MutableStateFlow<AddState>(AddState.Idle)
    val state: StateFlow<AddState> = _state.asStateFlow()

    fun submit(input: String) {
        viewModelScope.launch {
            _state.value = AddState.Submitting
            try {
                val response = repo.extract(input.trim())
                _state.value = AddState.Polling(response.recipe_id, "En attente…")
                val recipe = repo.pollTask(response.recipe_id) { status ->
                    val label = when (status) {
                        "pending" -> "En attente…"
                        "processing" -> "Extraction en cours…"
                        else -> status
                    }
                    _state.value = AddState.Polling(response.recipe_id, label)
                }
                _state.value = AddState.Success(recipe.id)
            } catch (e: Exception) {
                _state.value = AddState.Error(e.message ?: "Erreur inconnue")
            }
        }
    }

    fun reset() { _state.value = AddState.Idle }
}
