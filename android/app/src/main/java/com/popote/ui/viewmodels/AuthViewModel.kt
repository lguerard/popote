package com.popote.ui.viewmodels

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.popote.data.AccountUser
import com.popote.data.RecipeRepository
import com.popote.data.SessionEvents
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import retrofit2.HttpException

/** État de la porte d'entrée de l'application. */
sealed interface AuthState {
    /** Vérification du serveur en cours. */
    data object Checking : AuthState
    /** Serveur injoignable ou URL non configurée : on propose les réglages. */
    data class Unreachable(val message: String) : AuthState
    /** Aucun compte n'existe encore côté serveur. */
    data object NeedsSetup : AuthState
    data object SignedOut : AuthState
    data class SignedIn(val user: AccountUser) : AuthState
}

class AuthViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)

    private val _state = MutableStateFlow<AuthState>(AuthState.Checking)
    val state: StateFlow<AuthState> = _state.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    init {
        refresh()
        // Un 401 sur n'importe quelle requête signifie que la session est morte.
        viewModelScope.launch {
            SessionEvents.expired.collect { onSessionExpired() }
        }
    }

    /** Demande au serveur s'il a déjà un compte et si notre jeton vaut encore. */
    fun refresh() {
        viewModelScope.launch {
            _state.value = AuthState.Checking
            try {
                val status = repo.authStatus()
                _state.value = when {
                    status.needs_setup -> AuthState.NeedsSetup
                    status.user != null -> AuthState.SignedIn(status.user)
                    else -> AuthState.SignedOut
                }
            } catch (_: Exception) {
                _state.value = AuthState.Unreachable(
                    "Serveur injoignable. Vérifie l'adresse dans les paramètres."
                )
            }
        }
    }

    fun signIn(email: String, password: String) {
        _error.value = null
        viewModelScope.launch {
            _busy.value = true
            try {
                _state.value = AuthState.SignedIn(repo.login(email, password))
            } catch (e: HttpException) {
                _error.value =
                    if (e.code() == 401) "Identifiants incorrects" else "Connexion impossible"
            } catch (_: Exception) {
                _error.value = "Serveur injoignable"
            } finally {
                _busy.value = false
            }
        }
    }

    fun createFirstAccount(email: String, displayName: String, password: String) {
        _error.value = null
        if (password.length < 8) {
            _error.value = "Mot de passe : 8 caractères minimum."
            return
        }
        viewModelScope.launch {
            _busy.value = true
            try {
                _state.value = AuthState.SignedIn(repo.setupFirstAccount(email, displayName, password))
            } catch (e: HttpException) {
                _error.value =
                    if (e.code() == 409) "Un compte existe déjà. Connecte-toi." else "Création impossible"
            } catch (_: Exception) {
                _error.value = "Serveur injoignable"
            } finally {
                _busy.value = false
            }
        }
    }

    fun signOut() {
        viewModelScope.launch {
            repo.logout()
            _state.value = AuthState.SignedOut
        }
    }

    private fun onSessionExpired() {
        // Déjà déconnecté : rien à faire, et surtout pas d'aller-retour réseau.
        if (_state.value !is AuthState.SignedIn) return
        viewModelScope.launch {
            repo.logout()
            _error.value = "Session expirée, reconnecte-toi."
            _state.value = AuthState.SignedOut
        }
    }

    fun clearError() {
        _error.value = null
    }
}
