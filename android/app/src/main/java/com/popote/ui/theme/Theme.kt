package com.popote.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import com.popote.data.ColorSource
import com.popote.data.ThemeMode
import com.popote.data.ThemeSettings

val Orange50 = Color(0xFFFFF7ED)
val Orange100 = Color(0xFFFFEDD5)
val Orange400 = Color(0xFFFB923C)
val Orange500 = Color(0xFFF97316)
val Orange600 = Color(0xFFEA580C)
val Orange700 = Color(0xFFC2410C)
val Amber50 = Color(0xFFFFFBEB)

/** Couleurs proposées dans les paramètres (« Couleur au choix »). */
val ThemeSwatches = listOf(
    0xFFEA580C, 0xFFD32F2F, 0xFFC2185B, 0xFF7B1FA2, 0xFF3949AB,
    0xFF1565C0, 0xFF00838F, 0xFF2E7D32, 0xFF827717, 0xFF6D4C41,
)

private fun c(argb: Int) = Color(argb)

/** Thème complet tiré d'une seule couleur, en clair ou en sombre (rôles Material 3). */
fun seedColorScheme(seed: Long, dark: Boolean): ColorScheme {
    val p = SeedPalettes(seed.toInt())
    return if (!dark) lightColorScheme(
        primary = c(p.primary[40]), onPrimary = c(p.primary[100]),
        primaryContainer = c(p.primary[90]), onPrimaryContainer = c(p.primary[10]),
        inversePrimary = c(p.primary[80]),
        secondary = c(p.secondary[40]), onSecondary = c(p.secondary[100]),
        secondaryContainer = c(p.secondary[90]), onSecondaryContainer = c(p.secondary[10]),
        tertiary = c(p.tertiary[40]), onTertiary = c(p.tertiary[100]),
        tertiaryContainer = c(p.tertiary[90]), onTertiaryContainer = c(p.tertiary[10]),
        background = c(p.neutral[98]), onBackground = c(p.neutral[10]),
        surface = c(p.neutral[98]), onSurface = c(p.neutral[10]),
        surfaceVariant = c(p.neutralVariant[90]), onSurfaceVariant = c(p.neutralVariant[30]),
        surfaceTint = c(p.primary[40]),
        inverseSurface = c(p.neutral[20]), inverseOnSurface = c(p.neutral[95]),
        outline = c(p.neutralVariant[50]), outlineVariant = c(p.neutralVariant[80]),
        surfaceBright = c(p.neutral[98]), surfaceDim = c(p.neutral[87]),
        surfaceContainerLowest = c(p.neutral[100]), surfaceContainerLow = c(p.neutral[96]),
        surfaceContainer = c(p.neutral[94]), surfaceContainerHigh = c(p.neutral[92]),
        surfaceContainerHighest = c(p.neutral[90]),
    ) else darkColorScheme(
        primary = c(p.primary[80]), onPrimary = c(p.primary[20]),
        primaryContainer = c(p.primary[30]), onPrimaryContainer = c(p.primary[90]),
        inversePrimary = c(p.primary[40]),
        secondary = c(p.secondary[80]), onSecondary = c(p.secondary[20]),
        secondaryContainer = c(p.secondary[30]), onSecondaryContainer = c(p.secondary[90]),
        tertiary = c(p.tertiary[80]), onTertiary = c(p.tertiary[20]),
        tertiaryContainer = c(p.tertiary[30]), onTertiaryContainer = c(p.tertiary[90]),
        background = c(p.neutral[6]), onBackground = c(p.neutral[90]),
        surface = c(p.neutral[6]), onSurface = c(p.neutral[90]),
        surfaceVariant = c(p.neutralVariant[30]), onSurfaceVariant = c(p.neutralVariant[80]),
        surfaceTint = c(p.primary[80]),
        inverseSurface = c(p.neutral[90]), inverseOnSurface = c(p.neutral[20]),
        outline = c(p.neutralVariant[60]), outlineVariant = c(p.neutralVariant[30]),
        surfaceBright = c(p.neutral[24]), surfaceDim = c(p.neutral[6]),
        surfaceContainerLowest = c(p.neutral[4]), surfaceContainerLow = c(p.neutral[10]),
        surfaceContainer = c(p.neutral[12]), surfaceContainerHigh = c(p.neutral[17]),
        surfaceContainerHighest = c(p.neutral[22]),
    )
}

/** L'orange de Popote : couleurs d'origine en clair, fonds assortis. */
private fun popoteColorScheme(dark: Boolean): ColorScheme {
    val base = seedColorScheme(0xFFEA580C, dark)
    return if (dark) base else base.copy(
        primary = Orange600, onPrimary = Color.White,
        primaryContainer = Orange100, onPrimaryContainer = Orange700,
        background = Amber50, surfaceVariant = Orange50,
    )
}

/** L'appli est-elle en sombre (choix de l'utilisateur, ou celui du téléphone) ? */
@Composable
fun ThemeSettings.isDark(): Boolean = when (mode) {
    ThemeMode.LIGHT -> false
    ThemeMode.DARK -> true
    ThemeMode.SYSTEM -> isSystemInDarkTheme()
}

@Composable
fun PopoteTheme(settings: ThemeSettings = ThemeSettings(), content: @Composable () -> Unit) {
    val dark = settings.isDark()
    val context = LocalContext.current
    val colors = when {
        settings.color == ColorSource.DYNAMIC && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S ->
            if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        settings.color == ColorSource.CUSTOM -> seedColorScheme(settings.customColor, dark)
        else -> popoteColorScheme(dark)
    }
    MaterialTheme(colorScheme = colors, typography = Typography(), content = content)
}
