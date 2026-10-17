package com.popote.ui.viewmodels

import android.app.Application
import android.net.Uri
import com.popote.data.ExtractionFailedException
import com.popote.data.ExtractionResponse
import kotlinx.coroutines.delay
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
    /** Import de plusieurs liens, suivi ligne par ligne. */
    data class Batch(val rows: List<BatchRow>, val alreadySaved: Int, val ignored: Int) : AddState() {
        val finished get() = rows.count { it.status == "done" || it.status == "failed" }
        val isFinished get() = finished == rows.size
    }
}

data class BatchRow(
    val recipeId: String,
    val link: String,
    val status: String = "pending",
    val title: String? = null,
    val message: String? = null,
)

/** Liens d'un texte collé (approximation de la détection du serveur, pour l'annoncer). */
fun linksIn(text: String): List<String> =
    Regex("""(?:https?://|www\.)[^\s<>"']+|(?m)^[a-z0-9-]+(?:\.[a-z0-9-]+)+/\S*""", RegexOption.IGNORE_CASE)
        .findAll(text).map { it.value.trimEnd('.', ',', ';', ':', '!', '?', ')') }.distinct().toList()

class AddRecipeViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)

    private val _state = MutableStateFlow<AddState>(AddState.Idle)
    val state: StateFlow<AddState> = _state.asStateFlow()

    /** Plusieurs liens : envoyés en une fois, extraits l'un après l'autre par le serveur. */
    fun submitBatch(input: String) {
        viewModelScope.launch {
            _state.value = AddState.Submitting
            val response = try {
                repo.extractBatch(input)
            } catch (e: Exception) {
                _state.value = AddState.Error(repo.describe(e)); return@launch
            }
            var batch = AddState.Batch(
                rows = response.items.orEmpty().map { BatchRow(it.recipe_id, it.input) },
                alreadySaved = response.already_saved.orEmpty().size,
                ignored = response.ignored,
            )
            _state.value = batch
            while (!batch.isFinished) {
                delay(3000)
                val recipes = try {
                    repo.getTasks(batch.rows.map { it.recipeId }).associateBy { it.id }
                } catch (_: Exception) {
                    continue  // réseau coupé : l'import continue sur le serveur
                }
                batch = batch.copy(rows = batch.rows.map { row ->
                    recipes[row.recipeId]?.let { r ->
                        row.copy(
                            status = r.status,
                            title = r.title.takeIf { r.status == "done" },
                            message = if (r.status == "failed") r.error_msg else r.progress_message,
                        )
                    } ?: row
                })
                if (_state.value !is AddState.Batch) return@launch  // écran réinitialisé
                _state.value = batch
            }
        }
    }

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
