package com.popote.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.popote.data.ColorSource
import com.popote.data.ThemeMode
import com.popote.data.ThemeSettings
import com.popote.data.dynamicColorAvailable
import com.popote.data.saveThemeSettings
import com.popote.data.themeSettings
import com.popote.ui.theme.ThemeSwatches
import kotlinx.coroutines.launch

/** Paramètres d'apparence : clair / sombre / système, et d'où viennent les couleurs. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppearanceSection() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settingsFlow = remember(context) { context.themeSettings() }
    val settings by settingsFlow.collectAsState(initial = ThemeSettings())
    fun save(changed: ThemeSettings) {
        scope.launch { context.saveThemeSettings(changed) }
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Apparence", style = MaterialTheme.typography.titleLarge)

        Text("Thème", style = MaterialTheme.typography.labelLarge)
        val modes = listOf(ThemeMode.SYSTEM to "Système", ThemeMode.LIGHT to "Clair", ThemeMode.DARK to "Sombre")
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            modes.forEachIndexed { index, (mode, label) ->
                SegmentedButton(
                    selected = settings.mode == mode,
                    onClick = { save(settings.copy(mode = mode)) },
                    shape = SegmentedButtonDefaults.itemShape(index, modes.size),
                ) { Text(label) }
            }
        }

        Text("Couleurs", style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(top = 8.dp))
        if (dynamicColorAvailable) {
            ColorChoice(
                "Material You", "Les couleurs de ton fond d'écran",
                selected = settings.color == ColorSource.DYNAMIC,
            ) { save(settings.copy(color = ColorSource.DYNAMIC)) }
        }
        ColorChoice("Orange Popote", null, selected = settings.color == ColorSource.POPOTE) {
            save(settings.copy(color = ColorSource.POPOTE))
        }
        ColorChoice(
            "Couleur au choix", "L'appli en tire tout son thème, en clair comme en sombre",
            selected = settings.color == ColorSource.CUSTOM,
        ) { save(settings.copy(color = ColorSource.CUSTOM)) }

        if (settings.color == ColorSource.CUSTOM) {
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                ThemeSwatches.forEach { swatch ->
                    val chosen = settings.customColor == swatch
                    Box(
                        Modifier
                            .size(40.dp)
                            .clip(CircleShape)
                            .background(Color(swatch))
                            .border(
                                width = if (chosen) 3.dp else 0.dp,
                                color = MaterialTheme.colorScheme.onSurface,
                                shape = CircleShape,
                            )
                            .clickable { save(settings.copy(customColor = swatch)) },
                        contentAlignment = Alignment.Center,
                    ) {
                        if (chosen) Icon(Icons.Default.Check, "Couleur choisie", tint = Color.White)
                    }
                }
            }
        }
        if (!dynamicColorAvailable) {
            Text(
                "Material You (couleurs du fond d'écran) demande Android 12 ou plus.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun ColorChoice(title: String, subtitle: String?, selected: Boolean, onSelect: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .selectable(selected = selected, onClick = onSelect, role = Role.RadioButton)
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = selected, onClick = null)
        Column(Modifier.padding(start = 8.dp)) {
            Text(title, style = MaterialTheme.typography.bodyLarge)
            if (subtitle != null) {
                Text(subtitle, style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}
