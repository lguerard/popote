package com.popote.ui.viewmodels

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.popote.data.RecipeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import retrofit2.HttpException

class SettingsViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)

    val serverUrl = repo.serverUrl

    private val _testResult = MutableStateFlow<String?>(null)
    val testResult: StateFlow<String?> = _testResult.asStateFlow()

    // Changement de mot de passe : null tant que rien n'a été tenté.
    private val _passwordResult = MutableStateFlow<String?>(null)
    val passwordResult: StateFlow<String?> = _passwordResult.asStateFlow()

    private val _passwordOk = MutableStateFlow(false)
    val passwordOk: StateFlow<Boolean> = _passwordOk.asStateFlow()

    private val _passwordBusy = MutableStateFlow(false)
    val passwordBusy: StateFlow<Boolean> = _passwordBusy.asStateFlow()

    fun saveUrl(url: String) {
        viewModelScope.launch { repo.saveServerUrl(url) }
    }

    fun testConnection(url: String) {
        viewModelScope.launch {
            repo.saveServerUrl(url)
            val ok = repo.checkHealth()
            _testResult.value = if (ok) "✓ Connecté !" else "✗ Serveur inaccessible"
        }
    }

    fun clearTestResult() { _testResult.value = null }

    fun clearPasswordResult() {
        _passwordResult.value = null
        _passwordOk.value = false
    }

    fun changePassword(current: String, new: String, confirmation: String) {
        _passwordOk.value = false
        if (new.length < 8) {
            _passwordResult.value = "Mot de passe : 8 caractères minimum."
            return
        }
        if (new != confirmation) {
            _passwordResult.value = "Les deux mots de passe ne correspondent pas."
            return
        }
        viewModelScope.launch {
            _passwordBusy.value = true
            _passwordResult.value = null
            try {
                repo.changePassword(current, new)
                _passwordOk.value = true
                _passwordResult.value =
                    "Mot de passe modifié. Tes autres appareils ont été déconnectés."
            } catch (e: HttpException) {
                _passwordResult.value = when (e.code()) {
                    400 -> "Mot de passe actuel incorrect"
                    401 -> "Session expirée, reconnecte-toi"
                    else -> "Changement impossible"
                }
            } catch (_: Exception) {
                _passwordResult.value = "Serveur injoignable"
            } finally {
                _passwordBusy.value = false
            }
        }
    }
}
