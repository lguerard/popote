package com.popote.ui.screens

import android.content.Context
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.VibrationEffect
import android.os.Vibrator
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.popote.data.Ingredient
import com.popote.data.Recipe
import com.popote.ui.components.Stars
import com.popote.ui.components.formatSeconds
import com.popote.ui.components.ingredientAmount
import com.popote.ui.components.ingredientsForStep
import com.popote.ui.components.parseStepSeconds
import kotlinx.coroutines.delay
import kotlin.math.roundToInt

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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CookingModeOverlay(
    recipe: Recipe,
    scale: Double = 1.0,
    onExit: () -> Unit,
    onCooked: (rating: Int?) -> Unit,
) {
    val context = LocalContext.current
    val ingredients = recipe.ingredients
    // Page 0 = « mise en place » (tous les ingrédients et leurs quantités),
    // puis une page par étape.
    val offset = if (ingredients.isNotEmpty()) 1 else 0
    var page by remember { mutableIntStateOf(0) }
    val ready = remember { mutableStateListOf<Int>() }
    var showAllIngredients by remember { mutableStateOf(false) }
    var finished by remember { mutableStateOf(false) }
    var finalRating by remember { mutableStateOf<Int?>(null) }
    val timers = remember { mutableStateListOf<CookTimer>() }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var nextId by remember { mutableLongStateOf(1L) }

    val steps = recipe.steps
    val pageCount = steps.size + offset
    val stepIdx = page - offset
    val step = steps.getOrNull(stepIdx)
    val stepSeconds = step?.let { parseStepSeconds(it.text) }
    val stepIngredients = step?.let { ingredientsForStep(it.text, ingredients) }.orEmpty()
    val servings = recipe.servings?.let { (it * scale).roundToInt() }
    fun toggleReady(i: Int) { if (i in ready) ready.remove(i) else ready.add(i) }

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
                if (ingredients.isNotEmpty()) {
                    TextButton(onClick = { showAllIngredients = true }) { Text("🧺 Ingrédients") }
                }
                if (steps.isNotEmpty() && stepIdx >= 0) Text("${stepIdx + 1}/${steps.size}", style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            LinearProgressIndicator(
                progress = { if (pageCount == 0) 1f else (page + 1).toFloat() / pageCount },
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

            if (stepIdx < 0) {
                Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState())) {
                    Text("Mise en place", style = MaterialTheme.typography.headlineSmall)
                    Text(
                        (servings?.let { "Pour $it portion${if (it > 1) "s" else ""} · " } ?: "") +
                            "cochez au fur et à mesure",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(bottom = 8.dp),
                    )
                    ingredients.forEachIndexed { i, ing ->
                        IngredientLine(ing, scale, checked = i in ready, onToggle = { toggleReady(i) })
                    }
                }
            } else if (step != null) {
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
                    // Les étapes disent « ajouter la farine », rarement combien :
                    // les quantités des ingrédients cités, sous les yeux.
                    if (stepIngredients.isNotEmpty()) {
                        Card(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(12.dp)) {
                                Text("Pour cette étape", style = MaterialTheme.typography.labelLarge,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                                stepIngredients.forEach { ing -> IngredientLine(ing, scale) }
                            }
                        }
                    }
                }
            } else {
                Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Text("Cette recette n'a pas d'étapes.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }

            Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                FilledTonalButton(onClick = { if (page > 0) page-- }, enabled = page > 0,
                    modifier = Modifier.weight(1f).height(56.dp)) { Text("←", fontSize = 22.sp) }
                if (page < pageCount - 1) {
                    Button(onClick = { page++ }, modifier = Modifier.weight(1f).height(56.dp)) {
                        Text(if (stepIdx < 0) "C'est parti →" else "→", fontSize = if (stepIdx < 0) 18.sp else 22.sp)
                    }
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

    if (showAllIngredients) {
        ModalBottomSheet(onDismissRequest = { showAllIngredients = false }) {
            Column(
                Modifier.padding(horizontal = 20.dp).padding(bottom = 32.dp).verticalScroll(rememberScrollState()),
            ) {
                Text("🧺 Ingrédients" + (servings?.let { " · $it portion${if (it > 1) "s" else ""}" } ?: ""),
                    style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(bottom = 8.dp))
                ingredients.forEachIndexed { i, ing ->
                    IngredientLine(ing, scale, checked = i in ready, onToggle = { toggleReady(i) })
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

/** « 200 g · farine (tamisée) », quantité en évidence, cochable en mise en place. */
@Composable
private fun IngredientLine(
    ing: Ingredient,
    scale: Double,
    checked: Boolean? = null,
    onToggle: (() -> Unit)? = null,
) {
    val done = checked == true
    Row(
        Modifier.fillMaxWidth()
            .then(if (onToggle != null) Modifier.clickable(onClick = onToggle) else Modifier)
            .padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (checked != null) Checkbox(checked = checked, onCheckedChange = { onToggle?.invoke() })
        Text(
            ingredientAmount(ing, scale),
            Modifier.widthIn(min = 72.dp),
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            color = if (done) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.primary,
        )
        Column(Modifier.weight(1f)) {
            Text(ing.name, style = MaterialTheme.typography.titleMedium,
                color = if (done) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface)
            if (!ing.notes.isNullOrBlank()) Text(ing.notes, style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
