package com.popote.ui.screens

import android.content.Context
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.VibrationEffect
import android.os.Vibrator
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.ShoppingBasket
import com.popote.ui.components.heroColors
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
import com.popote.ui.components.sectionStart
import com.popote.ui.components.RecipePartTitle
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

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
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

    val hero = heroColors()
    val cs = MaterialTheme.colorScheme
    Surface(Modifier.fillMaxSize(), color = hero.container, contentColor = hero.content) {
        Column(Modifier.fillMaxSize().systemBarsPadding().padding(horizontal = 20.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                FilledIconButton(onClick = onExit, modifier = Modifier.size(48.dp),
                    colors = IconButtonDefaults.filledIconButtonColors(containerColor = hero.raised, contentColor = hero.content)) {
                    Icon(Icons.Default.Close, "Quitter le mode cuisine")
                }
                Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(recipe.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.ExtraBold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(
                        (servings?.let { "$it portion${if (it > 1) "s" else ""} · " } ?: "") + "écran toujours allumé",
                        style = MaterialTheme.typography.labelMedium, color = hero.muted,
                    )
                }
                if (ingredients.isNotEmpty()) {
                    FilledIconButton(onClick = { showAllIngredients = true }, modifier = Modifier.size(48.dp),
                        colors = IconButtonDefaults.filledIconButtonColors(containerColor = hero.raised, contentColor = hero.content)) {
                        Icon(Icons.Default.ShoppingBasket, "Tous les ingrédients")
                    }
                } else Spacer(Modifier.size(48.dp))
            }

            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (pageCount in 1..24) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                        repeat(pageCount) { i ->
                            Box(
                                Modifier.weight(1f).height(8.dp).clip(CircleShape).background(
                                    when {
                                        i < page -> hero.accent
                                        i == page -> hero.content
                                        else -> hero.raised
                                    }
                                )
                            )
                        }
                    }
                } else {
                    LinearProgressIndicator(
                        progress = { if (pageCount == 0) 1f else (page + 1).toFloat() / pageCount },
                        color = hero.accent, trackColor = hero.raised,
                        modifier = Modifier.fillMaxWidth().height(8.dp).clip(CircleShape),
                    )
                }
                Text(
                    if (stepIdx < 0) "Mise en place" else "Étape ${stepIdx + 1} sur ${steps.size}",
                    style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.ExtraBold,
                    letterSpacing = 1.sp, color = hero.accent,
                )
            }

            // Minuteurs en cours (plusieurs à la fois)
            if (timers.isNotEmpty()) Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                timers.toList().forEachIndexed { i, t ->
                    val left = t.remainingAt(now)
                    // Toucher la pastille met en pause ou relance ; la croix la retire.
                    Surface(
                        onClick = {
                            timers[i] = when {
                                t.done -> t
                                t.endsAt != null -> t.copy(endsAt = null, remaining = left)
                                else -> t.copy(endsAt = System.currentTimeMillis() + t.remaining * 1000L)
                            }
                        },
                        shape = CircleShape,
                        color = if (t.done) cs.tertiaryContainer else hero.accent,
                        contentColor = if (t.done) cs.onTertiaryContainer else hero.onAccent,
                    ) {
                        Row(Modifier.padding(start = 14.dp, end = 4.dp).height(44.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                if (t.done) "${t.label} : prêt !" else "${t.label} ${formatSeconds(left)}${if (t.endsAt == null) " ⏸" else ""}",
                                fontWeight = FontWeight.Bold,
                            )
                            IconButton(onClick = { timers.removeAt(i) }, modifier = Modifier.size(40.dp)) {
                                Icon(Icons.Default.Close, "Retirer le minuteur", Modifier.size(16.dp))
                            }
                        }
                    }
                }
            }

            if (stepIdx < 0) {
                Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState())) {
                    Text(
                        (servings?.let { "Pour $it portion${if (it > 1) "s" else ""} · " } ?: "") + "coche au fur et à mesure",
                        style = MaterialTheme.typography.bodyLarge, color = hero.muted,
                        modifier = Modifier.padding(bottom = 8.dp),
                    )
                    ingredients.forEachIndexed { i, ing ->
                        sectionStart(ingredients, i) { it.section }?.let { PartTitle(it, hero.accent) }
                        IngredientLine(ing, scale, checked = i in ready, onToggle = { toggleReady(i) })
                    }
                }
            } else if (step != null) {
                Column(
                    Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(18.dp),
                ) {
                    // Partie de la recette en cours (« Pâte », « Glaçage »).
                    step.section?.takeIf { it.isNotBlank() }?.let { PartTitle(it, hero.accent) }
                    Text(step.text, fontSize = 28.sp, lineHeight = 35.sp, fontWeight = FontWeight.ExtraBold)
                    // Les étapes disent « ajouter la farine », rarement combien :
                    // les quantités des ingrédients cités, sous les yeux.
                    if (stepIngredients.isNotEmpty()) {
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            stepIngredients.forEach { ing ->
                                Row(
                                    Modifier.clip(CircleShape).background(hero.raised).padding(start = 6.dp, end = 14.dp).height(42.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                ) {
                                    val amount = ingredientAmount(ing, scale)
                                    if (amount.isNotBlank()) Surface(shape = CircleShape, color = hero.accent, contentColor = hero.onAccent) {
                                        Text(amount, Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                                            style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Black)
                                    } else Spacer(Modifier.width(6.dp))
                                    Text(ing.name, fontWeight = FontWeight.Bold)
                                }
                            }
                        }
                    }
                    if (stepSeconds != null) {
                        Surface(shape = RoundedCornerShape(28.dp), color = cs.tertiaryContainer, contentColor = cs.onTertiaryContainer) {
                            Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                                Icon(Icons.Default.Timer, null, Modifier.size(36.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(formatSeconds(stepSeconds), fontSize = 28.sp, fontWeight = FontWeight.Black)
                                    Text("pour cette étape", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                                }
                                Button(
                                    onClick = { startTimer("Étape ${stepIdx + 1}", stepSeconds) },
                                    colors = ButtonDefaults.buttonColors(containerColor = cs.onTertiaryContainer, contentColor = cs.tertiaryContainer),
                                    modifier = Modifier.height(48.dp),
                                ) { Text("Lancer", fontWeight = FontWeight.ExtraBold) }
                            }
                        }
                    }
                }
            } else {
                Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Text("Cette recette n'a pas d'étapes.", color = hero.muted)
                }
            }

            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = { if (page > 0) page-- }, enabled = page > 0,
                    shape = RoundedCornerShape(32.dp),
                    border = BorderStroke(1.5.dp, hero.outline),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = hero.content),
                    modifier = Modifier.width(88.dp).height(112.dp),
                ) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Étape précédente", Modifier.size(28.dp)) }
                val last = page >= pageCount - 1
                Button(
                    onClick = { if (last) finished = true else page++ },
                    shape = RoundedCornerShape(40.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = hero.accent, contentColor = hero.onAccent),
                    modifier = Modifier.weight(1f).height(112.dp),
                ) {
                    if (last) Icon(Icons.Default.Check, null, Modifier.size(28.dp).padding(end = 6.dp))
                    Text(
                        when {
                            last -> "Terminé !"
                            stepIdx < 0 -> "C'est parti"
                            else -> "Étape suivante"
                        },
                        fontSize = 26.sp, fontWeight = FontWeight.Black,
                    )
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
                    sectionStart(ingredients, i) { it.section }?.let { RecipePartTitle(it) }
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
        if (checked != null) Checkbox(
            checked = checked, onCheckedChange = { onToggle?.invoke() },
            colors = CheckboxDefaults.colors(
                checkedColor = heroColors().accent, checkmarkColor = heroColors().onAccent,
                uncheckedColor = LocalContentColor.current.copy(alpha = 0.7f),
            ),
        )
        Text(
            ingredientAmount(ing, scale),
            Modifier.widthIn(min = 72.dp),
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            color = if (done) LocalContentColor.current.copy(alpha = 0.5f) else heroColors().accent,
        )
        Column(Modifier.weight(1f)) {
            Text(ing.name, style = MaterialTheme.typography.titleMedium,
                color = LocalContentColor.current.copy(alpha = if (done) 0.5f else 1f),
                textDecoration = if (done) TextDecoration.LineThrough else null)
            if (!ing.notes.isNullOrBlank()) Text(ing.notes, style = MaterialTheme.typography.bodySmall,
                color = LocalContentColor.current.copy(alpha = 0.7f))
        }
    }
}

/** Titre d'une partie de la recette (« Pâte », « Glaçage ») sur le fond sombre. */
@Composable
private fun PartTitle(text: String, color: androidx.compose.ui.graphics.Color) {
    Text(text.uppercase(), style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Black,
        letterSpacing = 1.sp, color = color, modifier = Modifier.padding(top = 8.dp, bottom = 2.dp))
}
