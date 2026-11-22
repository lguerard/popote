package com.popote.ui.assistant

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.google.gson.JsonObject
import com.popote.data.AssistantException
import com.popote.data.ChatMessage
import com.popote.data.RecipeRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Écriture faite par l'assistant (ajout au planning, aux courses, recette créée). */
data class AssistantAction(val kind: String, val label: String, val recipeId: String? = null)

data class FoundRecipe(val id: String, val title: String, val thumbnailUrl: String?, val minutes: Int?)

data class ChatEntry(
    val id: Long,
    val role: String,  // "user" ou "assistant"
    val text: String = "",
    val pending: Boolean = false,
    val status: String? = null,
    val actions: List<AssistantAction> = emptyList(),
    val recipes: List<FoundRecipe> = emptyList(),
    val error: String? = null,
    val stopped: Boolean = false,
)

/** Recette ouverte quand l'assistant a été appelé depuis sa fiche. */
data class RecipeContext(val id: String, val title: String)

/**
 * Conversation avec l'assistant culinaire (le même que sur le web, voir
 * backend/app/services/assistant.py). Tenue ici, le temps de la session de
 * l'appli, et renvoyée en entier à chaque question ; le serveur diffuse la
 * réponse mot à mot.
 */
class AssistantViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)

    private val _entries = MutableStateFlow<List<ChatEntry>>(emptyList())
    val entries: StateFlow<List<ChatEntry>> = _entries.asStateFlow()
    private val _context = MutableStateFlow<RecipeContext?>(null)
    val context: StateFlow<RecipeContext?> = _context.asStateFlow()
    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    private var job: Job? = null
    private var nextId = 0L
    // Numéro de la question en cours : une réponse arrêtée ne doit pas
    // marquer comme finie celle qui l'a remplacée.
    private var run = 0L

    /** Ouverture depuis une fiche : la question portera sur cette recette. */
    fun setContext(recipe: RecipeContext?) {
        if (recipe != null) _context.value = recipe
    }

    fun clearContext() { _context.value = null }

    fun send(question: String) {
        val text = question.trim()
        if (text.isEmpty() || _busy.value) return
        // Historique envoyé : les échanges aboutis, sans les réponses vides ou en erreur.
        val history = _entries.value
            .filter { it.text.isNotBlank() && !it.pending }
            .map { ChatMessage(it.role, it.text) } + ChatMessage("user", text)
        val reply = ChatEntry(nextId + 1, "assistant", pending = true, status = "Je réfléchis…")
        _entries.update { it + ChatEntry(nextId, "user", text) + reply }
        nextId += 2
        _busy.value = true
        val current = ++run
        job = viewModelScope.launch {
            try {
                repo.assistantChat(history, _context.value?.id).collect { event -> apply(reply.id, event) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: AssistantException) {
                update(reply.id) { it.copy(error = e.message) }
            } catch (e: Exception) {
                update(reply.id) { it.copy(error = repo.describe(e)) }
            } finally {
                update(reply.id) { it.copy(pending = false, status = null) }
                if (run == current) _busy.value = false
            }
        }
    }

    /** Arrête la réponse en cours (la connexion est fermée, le serveur s'arrête aussi). */
    fun stop() {
        val running = _entries.value.lastOrNull { it.pending } ?: return
        job?.cancel()
        update(running.id) { it.copy(pending = false, status = null, stopped = true) }
        _busy.value = false
    }

    fun reset() {
        job?.cancel()
        _entries.value = emptyList()
        _busy.value = false
    }

    private fun apply(id: Long, event: JsonObject) {
        fun str(key: String) = event.get(key)?.takeIf { it.isJsonPrimitive }?.asString
        when (str("type")) {
            "status" -> update(id) { it.copy(status = str("text")) }
            "delta" -> update(id) { it.copy(text = it.text + (str("text") ?: ""), status = null) }
            "action" -> update(id) {
                it.copy(actions = it.actions + AssistantAction(str("kind") ?: "", str("label") ?: "", str("recipe_id")))
            }
            "recipes" -> update(id) { entry ->
                val found = event.getAsJsonArray("recipes")?.mapNotNull { element ->
                    val r = element.takeIf { it.isJsonObject }?.asJsonObject ?: return@mapNotNull null
                    FoundRecipe(
                        id = r.get("id")?.asString ?: return@mapNotNull null,
                        title = r.get("title")?.asString ?: "",
                        thumbnailUrl = r.get("thumbnail_url")?.takeIf { !it.isJsonNull }?.asString,
                        minutes = r.get("minutes")?.takeIf { !it.isJsonNull }?.asInt,
                    )
                }.orEmpty()
                entry.copy(recipes = (entry.recipes + found).distinctBy { it.id }.take(8))
            }
            "error" -> update(id) { it.copy(error = str("message")) }
            "done" -> update(id) { it.copy(pending = false, status = null) }
        }
    }

    private fun update(id: Long, change: (ChatEntry) -> ChatEntry) {
        _entries.update { list -> list.map { if (it.id == id) change(it) else it } }
    }
}
