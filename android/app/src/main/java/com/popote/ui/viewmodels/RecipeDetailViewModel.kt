package com.popote.ui.viewmodels

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.popote.data.Account
import com.popote.data.CookLog
import com.popote.data.Recipe
import com.popote.data.RecipeCollection
import com.popote.data.RecipeRepository
import com.popote.data.SendRecipesRequest
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate

class RecipeDetailViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)

    private val _recipe = MutableStateFlow<Recipe?>(null)
    val recipe: StateFlow<Recipe?> = _recipe.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()
    private val _nutritionLoading = MutableStateFlow(false)
    val nutritionLoading: StateFlow<Boolean> = _nutritionLoading.asStateFlow()
    private val _notesDraft = MutableStateFlow<String?>(null)
    val notesDraft: StateFlow<String?> = _notesDraft.asStateFlow()
    private val _notesSaving = MutableStateFlow(false)
    val notesSaving: StateFlow<Boolean> = _notesSaving.asStateFlow()
    private val _history = MutableStateFlow<List<CookLog>>(emptyList())
    val history: StateFlow<List<CookLog>> = _history.asStateFlow()
    private val _collections = MutableStateFlow<List<RecipeCollection>?>(null)
    val collections: StateFlow<List<RecipeCollection>?> = _collections.asStateFlow()

    private val _accounts = MutableStateFlow<List<Account>?>(null)
    val accounts: StateFlow<List<Account>?> = _accounts.asStateFlow()
    private val _sendResult = MutableStateFlow<String?>(null)
    val sendResult: StateFlow<String?> = _sendResult.asStateFlow()

    private val _saving = MutableStateFlow(false)
    val saving: StateFlow<Boolean> = _saving.asStateFlow()

    private var polling: Job? = null

    fun load(id: String) {
        viewModelScope.launch {
            try {
                val r = repo.getRecipe(id)
                setRecipe(r)
                _notesDraft.value = r.notes ?: ""
                loadHistory(id)
            } catch (e: Exception) { _error.value = "Impossible de charger la recette : ${repo.describe(e)}" }
        }
    }

    private fun setRecipe(r: Recipe) {
        _recipe.value = r
        if (r.reextracting || r.thumbnail_generating) pollReextraction(r.id)
    }

    private fun loadHistory(id: String) {
        viewModelScope.launch {
            try { _history.value = repo.getHistory(id) } catch (_: Exception) {}
        }
    }

    /** Suit une réextraction ou une génération d'image jusqu'à la fin (tâches de fond du serveur). */
    private fun pollReextraction(id: String) {
        if (polling?.isActive == true) return
        polling = viewModelScope.launch {
            while (true) {
                delay(2000)
                val r = try { repo.getRecipe(id) } catch (_: Exception) { continue }
                _recipe.value = r
                if (!r.reextracting && !r.thumbnail_generating) {
                    _notesDraft.value = r.notes ?: _notesDraft.value
                    break
                }
            }
        }
    }

    private fun act(errorPrefix: String, block: suspend () -> Unit) {
        viewModelScope.launch {
            try { block() } catch (e: Exception) { _error.value = "$errorPrefix : ${repo.describe(e)}" }
        }
    }

    fun delete(id: String, onDone: () -> Unit) = act("Suppression impossible") {
        repo.deleteRecipe(id); onDone()
    }

    fun toggleFavorite() {
        val id = _recipe.value?.id ?: return
        act("Favori non enregistré") { setRecipe(repo.toggleFavorite(id)) }
    }

    fun setRating(n: Int) {
        val id = _recipe.value?.id ?: return
        _recipe.value = _recipe.value?.copy(rating = n)
        act("Note non enregistrée") { setRecipe(repo.setRating(id, n)) }
    }

    fun toggleCookAgain() {
        val r = _recipe.value ?: return
        val next = r.cook_again != true
        _recipe.value = r.copy(cook_again = next)
        act("Modification non enregistrée") { setRecipe(repo.setCookAgain(r.id, next)) }
    }

    fun markCooked(date: LocalDate, rating: Int?, comment: String?) {
        val id = _recipe.value?.id ?: return
        act("Impossible d'enregistrer") {
            setRecipe(repo.markCooked(id, date.toString(), rating, comment))
            loadHistory(id)
        }
    }

    fun deleteCookLog(logId: String) {
        val id = _recipe.value?.id ?: return
        act("Suppression impossible") {
            setRecipe(repo.deleteCookLog(id, logId))
            loadHistory(id)
        }
    }

    fun analyzeNutrition() {
        val id = _recipe.value?.id ?: return
        viewModelScope.launch {
            _nutritionLoading.value = true
            try {
                val n = repo.analyzeNutrition(id)
                _recipe.value = _recipe.value?.copy(nutrition = n)
            } catch (e: Exception) { _error.value = "Analyse nutritionnelle échouée : ${repo.describe(e)}" }
            finally { _nutritionLoading.value = false }
        }
    }

    fun reextract(replaceImage: Boolean) {
        val id = _recipe.value?.id ?: return
        act("Réextraction impossible") { setRecipe(repo.reextract(id, replaceImage)) }
    }

    fun generateImage() {
        val id = _recipe.value?.id ?: return
        act("Génération impossible") { setRecipe(repo.generateImage(id)) }
    }

    /** Crée (si besoin) le lien public puis le transmet à la feuille de partage. */
    fun shareLink(onLink: (String) -> Unit) {
        val id = _recipe.value?.id ?: return
        act("Partage impossible") {
            val r = repo.shareRecipe(id)
            setRecipe(r)
            r.share_token?.let { onLink(repo.publicLink("/partage/r/$it")) }
        }
    }

    /** Lien de la page importable par MyFitnessPal (crée le lien public si besoin). */
    fun importLink(onLink: (String) -> Unit) {
        val id = _recipe.value?.id ?: return
        act("Lien impossible") {
            val r = _recipe.value?.takeIf { it.share_token != null } ?: repo.shareRecipe(id).also { setRecipe(it) }
            r.share_token?.let { onLink(repo.publicLink("/api/public/recipes/$it/page")) }
        }
    }

    fun loadAccounts() {
        _sendResult.value = null
        act("Comptes indisponibles") { _accounts.value = repo.getShareableUsers() }
    }

    /** Envoie une copie de la recette au compte choisi. */
    fun sendTo(account: Account) {
        val id = _recipe.value?.id ?: return
        act("Envoi impossible") {
            val result = repo.sendRecipes(SendRecipesRequest(user_id = account.id, recipe_ids = listOf(id)))
            _sendResult.value = if (result.copied > 0) "✓ Recette envoyée à ${account.display_name}."
                else "✓ ${account.display_name} a déjà cette recette."
        }
    }

    fun revokeLink() {
        val id = _recipe.value?.id ?: return
        act("Révocation impossible") { setRecipe(repo.unshareRecipe(id)) }
    }

    fun loadCollections() {
        val id = _recipe.value?.id ?: return
        act("Carnets indisponibles") { _collections.value = repo.getCollections(id) }
    }

    fun toggleCollection(c: RecipeCollection) {
        val id = _recipe.value?.id ?: return
        val inside = c.contains_recipe == true
        _collections.value = _collections.value?.map { if (it.id == c.id) it.copy(contains_recipe = !inside) else it }
        act("Carnet non modifié") {
            if (inside) repo.removeFromCollection(c.id, id) else repo.addToCollection(c.id, id)
        }
    }

    fun createCollection(name: String) {
        val id = _recipe.value?.id ?: return
        if (name.isBlank()) return
        act("Création impossible") {
            val c = repo.createCollection(name, "📒")
            repo.addToCollection(c.id, id)
            _collections.value = repo.getCollections(id)
        }
    }

    /** Enregistre une modification à la main (titre, ingrédients, étapes…), puis [onDone]. */
    fun saveEdits(fields: Map<String, Any?>, onDone: () -> Unit = {}) {
        val id = _recipe.value?.id ?: return
        viewModelScope.launch {
            _saving.value = true
            try {
                setRecipe(repo.updateRecipe(id, fields))
                onDone()
            } catch (e: Exception) { _error.value = "Modifications non enregistrées : ${repo.describe(e)}" }
            finally { _saving.value = false }
        }
    }

    fun rename(title: String, onDone: () -> Unit) {
        val clean = title.trim().replace(Regex("""\s+"""), " ")
        if (clean.isEmpty() || clean == _recipe.value?.title) { onDone(); return }
        saveEdits(mapOf("title" to clean), onDone)
    }

    fun clearError() { _error.value = null }

    fun setNotesDraft(s: String) { _notesDraft.value = s }

    fun saveNotes() {
        val id = _recipe.value?.id ?: return
        val notes = _notesDraft.value ?: return
        viewModelScope.launch {
            _notesSaving.value = true
            try {
                repo.updateNotes(id, notes)
                _recipe.value = _recipe.value?.copy(notes = notes)
            } catch (e: Exception) { _error.value = "Notes non enregistrées : ${repo.describe(e)}" }
            finally { _notesSaving.value = false }
        }
    }
}
