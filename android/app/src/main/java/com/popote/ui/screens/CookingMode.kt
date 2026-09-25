package com.popote.ui.screens

import android.content.Context
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.VibrationEffect
import android.os.Vibrator
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.popote.data.Recipe
import com.popote.ui.components.Stars
import com.popote.ui.components.formatSeconds
import com.popote.ui.components.parseStepSeconds
import kotlinx.coroutines.delay

/** Minuteur calculé depuis son heure de fin : juste même si l'appli passe en arrière-plan. */
private data class CookTimer(
    val id: Long,
    val label: String,
    val total: Int,
    val endsAt: Long?,      // null = en pause
    val remaining: Int,     // secondes restantes quand en pause
    val done: Boolean = false,
) {
    fun remainingAt(now: Long): Int =
        if (endsAt != null) (((endsAt - now) + 999) / 1000).toInt().coerceAtLeast(0) else remaining
}

private fun alarm(context: Context) {
    try {
        ToneGenerator(AudioManager.STREAM_ALARM, 100)
            .startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 1500)
    } catch (_: Exception) { }
    try {
        @Suppress("DEPRECATION")
        val vibrator = context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        vibrator?.vibrate(VibrationEffect.createWaveform(longArrayOf(0, 400, 200, 400, 200, 400), -1))
    } catch (_: Exception) { }
}

@Composable
fun CookingModeOverlay(
    recipe: Recipe,
    onExit: () -> Unit,
    onCooked: (rating: Int?) -> Unit,
) {
    val context = LocalContext.current
    var stepIdx by remember { mutableIntStateOf(0) }
    var showIngredients by remember { mutableStateOf(false) }
    var finished by remember { mutableStateOf(false) }
    var finalRating by remember { mutableStateOf<Int?>(null) }
    val timers = remember { mutableStateListOf<CookTimer>() }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var nextId by remember { mutableLongStateOf(1L) }

    val steps = recipe.steps
    val step = steps.getOrNull(stepIdx)
    val stepSeconds = step?.let { parseStepSeconds(it.text) }

    // Tic d'horloge tant qu'un minuteur tourne ; sonne à la fin de chacun.
    val anyRunning = timers.any { it.endsAt != null }
    LaunchedEffect(anyRunning) {
        while (anyRunning) {
            now = System.currentTimeMillis()
            val ended = timers.indices.filter { timers[it].endsAt != null && timers[it].remainingAt(now) == 0 }
            ended.forEach { i -> timers[i] = timers[i].copy(endsAt = null, remaining = 0, done = true) }
            if (ended.isNotEmpty()) alarm(context)
            if (timers.none { it.endsAt != null }) break
            delay(500)
        }
    }

    fun startTimer(label: String, seconds: Int) {
        timers.add(CookTimer(nextId++, label, seconds, System.currentTimeMillis() + seconds * 1000L, seconds))
    }

    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onExit) { Icon(Icons.Default.Close, "Quitter") }
                Text(recipe.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f),
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (steps.isNotEmpty()) Text("${stepIdx + 1}/${steps.size}", style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            LinearProgressIndicator(
                progress = { if (steps.isEmpty()) 1f else (stepIdx + 1).toFloat() / steps.size },
                modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp),
            )

            // Minuteurs en cours (plusieurs à la fois)
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                timers.toList().forEachIndexed { i, t ->
                    val left = t.remainingAt(now)
                    InputChip(
                        selected = t.endsAt != null || t.done,
                        onClick = {
                            timers[i] = when {
                                t.done -> t
                                t.endsAt != null -> t.copy(endsAt = null, remaining = left)
                                else -> t.copy(endsAt = System.currentTimeMillis() + t.remaining * 1000L)
                            }
                        },
                        label = { Text(if (t.done) "${t.label} : prêt !" else "${t.label} ${formatSeconds(left)}${if (t.endsAt == null) " ⏸" else ""}") },
                        colors = InputChipDefaults.inputChipColors(
                            selectedContainerColor = if (t.done) MaterialTheme.colorScheme.tertiaryContainer
                            else MaterialTheme.colorScheme.primaryContainer,
                        ),
                    )
                    // Le chip complet met en pause/reprend ; un bouton séparé le retire.
                    IconButton(onClick = { timers.removeAt(i) }, modifier = Modifier.size(28.dp)) {
                        Icon(Icons.Default.Close, "Retirer le minuteur", Modifier.size(14.dp))
                    }
                }
                AssistChip(
                    onClick = { startTimer("Minuteur ${timers.size + 1}", 5 * 60) },
                    label = { Text("+ 5 min") },
                    leadingIcon = { Icon(Icons.Default.Timer, null, Modifier.size(16.dp)) },
                )
            }

            if (step != null) {
                Column(
                    Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(20.dp, Alignment.CenterVertically),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Surface(shape = MaterialTheme.shapes.medium, color = MaterialTheme.colorScheme.primary) {
                        Text("Étape ${stepIdx + 1}", Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                            style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onPrimary)
                    }
                    Text(step.text, style = MaterialTheme.typography.headlineSmall, textAlign = TextAlign.Center,
                        modifier = Modifier.fillMaxWidth())
                    if (stepSeconds != null) {
                        FilledTonalButton(onClick = { startTimer("Étape ${stepIdx + 1}", stepSeconds) }) {
                            Icon(Icons.Default.Timer, null, Modifier.size(18.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("Lancer ${formatSeconds(stepSeconds)}")
                        }
                    }
                }
            } else {
                Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Text("Cette recette n'a pas d'étapes.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }

            if (recipe.ingredients.isNotEmpty()) {
                TextButton(onClick = { showIngredients = !showIngredients }) {
                    Text(if (showIngredients) "▾ Ingrédients" else "▸ Ingrédients")
                }
                if (showIngredients) {
                    Column(Modifier.heightIn(max = 160.dp).verticalScroll(rememberScrollState()).padding(horizontal = 8.dp)) {
                        recipe.ingredients.forEach { ing ->
                            Text(listOfNotNull(ing.quantity, ing.unit, ing.name).joinToString(" "),
                                style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
            }

            Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                FilledTonalButton(onClick = { if (stepIdx > 0) stepIdx-- }, enabled = stepIdx > 0,
                    modifier = Modifier.weight(1f).height(56.dp)) { Text("←", fontSize = 22.sp) }
                if (stepIdx < steps.size - 1) {
                    Button(onClick = { stepIdx++ }, modifier = Modifier.weight(1f).height(56.dp)) { Text("→", fontSize = 22.sp) }
                } else {
                    Button(
                        onClick = { finished = true },
                        modifier = Modifier.weight(1f).height(56.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.tertiary),
                    ) {
                        Icon(Icons.Default.Check, null, Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Terminé !")
                    }
                }
            }
        }
    }

    if (finished) {
        AlertDialog(
            onDismissRequest = { finished = false },
            title = { Text("Bon appétit ! 🍽️") },
            text = {
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
                    Text("Comment c'était ?")
                    Spacer(Modifier.height(8.dp))
                    Stars(finalRating, onChange = { finalRating = it }, size = 34.sp)
                }
            },
            confirmButton = {
                Button(onClick = { finished = false; onCooked(finalRating) }) { Text("Marquer comme cuisinée") }
            },
            dismissButton = { TextButton(onClick = { finished = false; onExit() }) { Text("Sortir sans noter") } },
        )
    }
}
