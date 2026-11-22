package com.popote.data

import android.content.Context
import android.os.Build
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

/** Clair, sombre, ou comme le téléphone. */
enum class ThemeMode { SYSTEM, LIGHT, DARK }

/** D'où viennent les couleurs de l'appli. */
enum class ColorSource {
    /** Material You : couleurs du fond d'écran (Android 12 et plus). */
    DYNAMIC,
    /** L'orange de Popote. */
    POPOTE,
    /** Une couleur choisie, d'où l'appli tire tout le thème. */
    CUSTOM,
}

data class ThemeSettings(
    val mode: ThemeMode = ThemeMode.SYSTEM,
    val color: ColorSource = ColorSource.POPOTE,
    val customColor: Long = 0xFF1565C0,
)

/** Material You n'existe qu'à partir d'Android 12. */
val dynamicColorAvailable: Boolean get() = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S

private val THEME_MODE_KEY = stringPreferencesKey("theme_mode")
private val COLOR_SOURCE_KEY = stringPreferencesKey("color_source")
private val CUSTOM_COLOR_KEY = longPreferencesKey("custom_color")

private inline fun <reified T : Enum<T>> enumOr(name: String?, default: T): T =
    enumValues<T>().firstOrNull { it.name == name } ?: default

fun Context.themeSettings(): Flow<ThemeSettings> = dataStore.data.map { prefs ->
    val defaults = ThemeSettings()
    ThemeSettings(
        mode = enumOr(prefs[THEME_MODE_KEY], defaults.mode),
        color = enumOr(prefs[COLOR_SOURCE_KEY], defaults.color)
            // Choisi sur un autre téléphone (sauvegarde) : pas de Material You ici.
            .let { if (it == ColorSource.DYNAMIC && !dynamicColorAvailable) ColorSource.POPOTE else it },
        customColor = prefs[CUSTOM_COLOR_KEY] ?: defaults.customColor,
    )
}

suspend fun Context.saveThemeSettings(settings: ThemeSettings) {
    dataStore.edit { prefs ->
        prefs[THEME_MODE_KEY] = settings.mode.name
        prefs[COLOR_SOURCE_KEY] = settings.color.name
        prefs[CUSTOM_COLOR_KEY] = settings.customColor
    }
}
