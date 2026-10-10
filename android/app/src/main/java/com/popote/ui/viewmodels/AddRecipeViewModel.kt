package com.popote.ui.viewmodels

import android.app.Application
import android.net.Uri
import com.popote.data.ExtractionFailedException
import com.popote.data.ExtractionResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.popote.data.RecipeRepository
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
        val text = input.trim()
        // Lien qui n'a rien donné : on peut toujours coller la légende ou le texte.
        val isLink = text.contains("://") || Regex("""^\S+\.[a-z]{2,}/\S*$""", RegexOption.IGNORE_CASE).matches(text)
        startExtraction(
            failureHint = if (isLink) "Astuce : copiez la légende du post (ou le texte de la recette) et collez-la ici." else null,
        ) { repo.extract(text) }
    }

    /** Photo choisie dans la galerie ou prise à l'instant. */
    fun submitImage(uri: Uri) = startExtraction {
        val resolver = getApplication<Application>().contentResolver
        val mime = resolver.getType(uri) ?: "image/jpeg"
        val bytes = withContext(Dispatchers.IO) {
            resolver.openInputStream(uri)?.use { it.readBytes() }
        } ?: throw Exception("Impossible de lire la photo")
        repo.extractImage(bytes, mime)
    }

    private fun startExtraction(failureHint: String? = null, start: suspend () -> ExtractionResponse) {
        viewModelScope.launch {
            _state.value = AddState.Submitting
            try {
                val response = start()
                _state.value = AddState.Polling(response.recipe_id, "En attente…")
                val recipe = repo.pollTask(response.recipe_id) { status, progress ->
                    val label = when (status) {
                        "reconnecting" -> "Connexion perdue, nouvelle tentative…"
                        "pending" -> "En attente…"
                        "processing" -> progress ?: "Extraction en cours…"
                        else -> status
                    }
                    _state.value = AddState.Polling(response.recipe_id, label)
                }
                _state.value = AddState.Success(recipe.id)
            } catch (e: ExtractionFailedException) {
                _state.value = AddState.Error(listOfNotNull(e.message, failureHint).joinToString("\n\n"))
            } catch (e: Exception) {
                _state.value = AddState.Error(repo.describe(e))
            }
        }
    }

    fun reset() { _state.value = AddState.Idle }
}
