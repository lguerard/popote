package com.kitchenai.ui.theme

import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Orange50 = Color(0xFFFFF7ED)
val Orange100 = Color(0xFFFFEDD5)
val Orange400 = Color(0xFFFB923C)
val Orange500 = Color(0xFFF97316)
val Orange600 = Color(0xFFEA580C)
val Orange700 = Color(0xFFC2410C)
val Amber50 = Color(0xFFFFFBEB)

private val LightColors = lightColorScheme(
    primary = Orange600,
    onPrimary = Color.White,
    primaryContainer = Orange100,
    onPrimaryContainer = Orange700,
    secondary = Orange400,
    onSecondary = Color.White,
    background = Amber50,
    surface = Color.White,
    surfaceVariant = Orange50,
    onSurface = Color(0xFF1C1B1F),
    onSurfaceVariant = Color(0xFF49454F),
)

@Composable
fun PopoteTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = LightColors,
        typography = Typography(),
        content = content,
    )
}
