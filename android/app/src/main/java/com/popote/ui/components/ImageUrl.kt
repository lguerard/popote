package com.popote.ui.components

import androidx.compose.runtime.compositionLocalOf

/**
 * Adresse du serveur, fournie par MainActivity. Les images importées ou
 * générées sont servies par le serveur avec une URL relative (/media/…) :
 * sans ce préfixe, Coil ne savait pas où les chercher et elles ne
 * s'affichaient jamais dans l'appli.
 */
val LocalServerUrl = compositionLocalOf { "" }

fun imageUrl(url: String?, server: String): String? = when {
    url.isNullOrBlank() -> null
    url.startsWith("/") -> server.trimEnd('/') + url
    else -> url
}
