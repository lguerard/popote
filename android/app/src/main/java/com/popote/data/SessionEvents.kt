package com.popote.data

import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow

/**
 * Pont entre la couche réseau et l'écran de connexion.
 *
 * L'intercepteur OkHttp n'a pas accès au ViewModel : quand le serveur répond
 * 401 alors qu'on croyait avoir une session (jeton révoqué par un changement
 * de mot de passe sur un autre appareil, session expirée), il signale ici, et
 * l'AuthViewModel ramène l'application sur l'écran de connexion.
 */
object SessionEvents {
    private val _expired = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    val expired: SharedFlow<Unit> = _expired

    fun notifyExpired() {
        _expired.tryEmit(Unit)
    }
}
