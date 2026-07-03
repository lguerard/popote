package com.kitchenai.ui.screens

import android.app.Application
import android.content.Intent
import android.net.Uri
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.FavoriteBorder
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.kitchenai.data.Nutrition
import com.kitchenai.data.Recipe
import com.kitchenai.data.RecipeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlin.math.abs
import kotlin.math.floor
import kotlin.math.roundToInt

// ── Scaling helpers ────────────────────────────────────────────────────────────

private fun parseFraction(s: String?): Double? {
    if (s.isNullOrBlank()) return null
    val frac = Regex("""^(\d+)\s*/\s*(\d+)$""").find(s.trim())
    if (frac != null) return frac.groupValues[1].toDouble() / frac.groupValues[2].toDouble()
    val mixed = Regex("""^(\d+)\s+(\d+)\s*/\s*(\d+)$""").find(s.trim())
    if (mixed != null) return mixed.groupValues[1].toDouble() + mixed.groupValues[2].toDouble() / mixed.groupValues[3].toDouble()
    return s.trim().toDoubleOrNull()
}

private fun formatQty(n: Double): String {
    if (n <= 0) return "0"
    val whole = floor(n).toInt()
    val frac = n - whole
    val FRACS = listOf(Pair(1, 4), Pair(1, 3), Pair(1, 2), Pair(2, 3), Pair(3, 4))
    if (frac < 0.04) return if (whole > 0) whole.toString() else "0"
    for ((num, den) in FRACS) {
        if (abs(frac - num.toDouble() / den) < 0.06)
            return if (whole > 0) "$whole $num/$den" else "$num/$den"
    }
    val r = (n * 10).roundToInt() / 10.0
    return if (r % 1.0 == 0.0) r.toInt().toString() else r.toString()
}

private fun scaleQty(qty: String?, scale: Double): String? {
    val n = parseFraction(qty) ?: return qty
    return formatQty(n * scale)
}

// ── ViewModel ─────────────────────────────────────────────────────────────────

class RecipeDetailViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)
    private val _recipe = MutableStateFlow<Recipe?>(null)
    val recipe: StateFlow<Recipe?> = _recipe.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()
    private val _nutritionLoading = MutableStateFlow(false)
    val nutritionLoading: StateFlow<Boolean> = _nutritionLoading.asStateFlow()
    private val _notesDraft = MutableStateFlow<String?>(null)
    val notesDraft: StateFlow<String?> = _notesDraft.asStateFlow()
    private val _notesSaving = MutableStateFlow(false)
    val notesSaving: StateFlow<Boolean> = _notesSaving.asStateFlow()

    fun load(id: String) {
        viewModelScope.launch {
            try {
                val r = repo.getRecipe(id)
                _recipe.value = r
                _notesDraft.value = r.notes ?: ""
            } catch (_: Exception) { _error.value = "Impossible de charger la recette" }
        }
    }

    fun delete(id: String, onDone: () -> Unit) {
        viewModelScope.launch {
            try { repo.deleteRecipe(id); onDone() }
            catch (_: Exception) { _error.value = "Erreur lors de la suppression" }
        }
    }

    fun toggleFavorite() {
        val id = _recipe.value?.id ?: return
        viewModelScope.launch {
            try { _recipe.value = repo.toggleFavorite(id) }
            catch (_: Exception) {}
        }
    }

    fun analyzeNutrition() {
        val id = _recipe.value?.id ?: return
        viewModelScope.launch {
            _nutritionLoading.value = true
            try {
                val n = repo.analyzeNutrition(id)
                _recipe.value = _recipe.value?.copy(nutrition = n)
            } catch (_: Exception) { _error.value = "Analyse nutritionnelle échouée" }
            finally { _nutritionLoading.value = false }
        }
    }

    fun setNotesDraft(s: String) { _notesDraft.value = s }

    fun saveNotes() {
        val id = _recipe.value?.id ?: return
        val notes = _notesDraft.value ?: return
        viewModelScope.launch {
            _notesSaving.value = true
            try {
                repo.updateNotes(id, notes)
                _recipe.value = _recipe.value?.copy(notes = notes)
            } catch (_: Exception) { _error.value = "Erreur sauvegarde notes" }
            finally { _notesSaving.value = false }
        }
    }
}

// ── Screen ────────────────────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecipeDetailScreen(
    recipeId: String,
    onBack: () -> Unit,
    vm: RecipeDetailViewModel = viewModel(),
) {
    val recipe by vm.recipe.collectAsState()
    val error by vm.error.collectAsState()
    val nutritionLoading by vm.nutritionLoading.collectAsState()
    val notesDraft by vm.notesDraft.collectAsState()
    val notesSaving by vm.notesSaving.collectAsState()
    var showDeleteDialog by remember { mutableStateOf(false) }
    var cookingMode by remember { mutableStateOf(false) }

    val context = LocalContext.current

    // Wake lock during cooking mode
    DisposableEffect(cookingMode) {
        val window = (context as? ComponentActivity)?.window
        if (cookingMode) window?.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        onDispose { window?.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
    }

    LaunchedEffect(recipeId) { vm.load(recipeId) }

    if (cookingMode && recipe != null) {
        CookingModeOverlay(recipe = recipe!!, onExit = { cookingMode = false })
        return
    }

    if (showDeleteDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteDialog = false },
            title = { Text("Supprimer la recette ?") },
            text = { Text("Cette action est irréversible.") },
            confirmButton = {
                TextButton(
                    onClick = { vm.delete(recipeId) { onBack() } },
                    colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error),
                ) { Text("Supprimer") }
            },
            dismissButton = { TextButton(onClick = { showDeleteDialog = false }) { Text("Annuler") } },
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(recipe?.title ?: "Recette", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Retour") }
                },
                actions = {
                    if (recipe != null) {
                        IconButton(onClick = vm::toggleFavorite) {
                            Icon(
                                if (recipe!!.is_favorite) Icons.Default.Favorite else Icons.Outlined.FavoriteBorder,
                                "Favori",
                                tint = if (recipe!!.is_favorite) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        IconButton(onClick = { showDeleteDialog = true }) {
                            Icon(Icons.Default.Delete, "Supprimer", tint = MaterialTheme.colorScheme.error)
                        }
                    }
                },
            )
        }
    ) { padding ->
        when {
            error != null -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Text(error!!, color = MaterialTheme.colorScheme.error)
            }
            recipe == null -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            else -> RecipeContent(
                recipe = recipe!!,
                modifier = Modifier.padding(padding),
                nutritionLoading = nutritionLoading,
                onAnalyzeNutrition = vm::analyzeNutrition,
                notesDraft = notesDraft ?: "",
                onNotesDraftChange = vm::setNotesDraft,
                notesSaving = notesSaving,
                onSaveNotes = vm::saveNotes,
                onStartCooking = { cookingMode = true },
            )
        }
    }
}

// ── Full-screen cooking mode ───────────────────────────────────────────────────

@Composable
private fun CookingModeOverlay(recipe: Recipe, onExit: () -> Unit) {
    var stepIdx by remember { mutableIntStateOf(0) }
    val steps = recipe.steps
    val progress = if (steps.isEmpty()) 1f else (stepIdx + 1).toFloat() / steps.size

    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(Modifier.fillMaxSize().padding(24.dp)) {
            // Header
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onExit) { Icon(Icons.Default.Close, "Quitter") }
                Text(recipe.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("${stepIdx + 1}/${steps.size}", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            LinearProgressIndicator(progress = { progress }, modifier = Modifier.fillMaxWidth().padding(vertical = 16.dp))

            // Step content
            if (steps.isNotEmpty()) {
                val step = steps[stepIdx]
                Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
                    Column(verticalArrangement = Arrangement.spacedBy(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Surface(shape = MaterialTheme.shapes.medium, color = MaterialTheme.colorScheme.primary) {
                            Text("Étape ${step.order}", Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                                style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onPrimary)
                        }
                        Text(step.text, style = MaterialTheme.typography.headlineSmall, modifier = Modifier.fillMaxWidth())
                    }
                }
            }

            // Navigation
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                FilledTonalButton(onClick = { if (stepIdx > 0) stepIdx-- }, enabled = stepIdx > 0) { Text("← Précédent") }
                if (stepIdx < steps.size - 1) {
                    Button(onClick = { stepIdx++ }) { Text("Suivant →") }
                } else {
                    Button(onClick = onExit, colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.tertiary)) {
                        Icon(Icons.Default.Check, null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Terminé !")
                    }
                }
            }
        }
    }
}

// ── Content ───────────────────────────────────────────────────────────────────

@Composable
private fun RecipeContent(
    recipe: Recipe,
    modifier: Modifier = Modifier,
    nutritionLoading: Boolean,
    onAnalyzeNutrition: () -> Unit,
    notesDraft: String,
    onNotesDraftChange: (String) -> Unit,
    notesSaving: Boolean,
    onSaveNotes: () -> Unit,
    onStartCooking: () -> Unit,
) {
    val context = LocalContext.current
    var scale by remember { mutableDoubleStateOf(1.0) }
    val scaledServings = recipe.servings?.let { (it * scale).roundToInt() }

    LazyColumn(modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 32.dp)) {

        // Duplicate warning
        if (recipe.similar_recipe_id != null) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
                ) {
                    Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Warning, null, tint = MaterialTheme.colorScheme.onErrorContainer)
                        Text("Une recette similaire existe déjà dans votre collection.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onErrorContainer)
                    }
                }
            }
        }

        // Thumbnail
        if (recipe.thumbnail_url != null) {
            item {
                AsyncImage(
                    model = recipe.thumbnail_url,
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f),
                )
            }
        }

        // Mode Cuisine button
        if (recipe.steps.isNotEmpty()) {
            item {
                Button(
                    onClick = onStartCooking,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.tertiary),
                ) {
                    Icon(Icons.Default.Restaurant, null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("Mode Cuisine")
                }
            }
        }

        // Source link
        if (recipe.source_url != null) {
            item {
                val sourceIcon = when (recipe.source_type) { "video" -> "🎬"; "web" -> "🌐"; else -> "🔗" }
                val sourceLabel = when (recipe.source_type) { "video" -> "Vidéo source"; "web" -> "Site source"; else -> "Source" }
                OutlinedCard(
                    onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(recipe.source_url))) },
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
                ) {
                    Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(sourceIcon, style = MaterialTheme.typography.titleLarge)
                        Column(Modifier.weight(1f)) {
                            Text(sourceLabel, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(recipe.source_url, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        Icon(Icons.AutoMirrored.Filled.OpenInNew, null, tint = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.size(16.dp))
                    }
                }
            }
        }

        // Description
        if (recipe.description != null) {
            item {
                Text(recipe.description, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
            }
        }

        // Meta
        item {
            Row(Modifier.padding(horizontal = 16.dp, vertical = 4.dp).fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (recipe.prep_time != null) MetaChip("🥄 Prép.", "${recipe.prep_time} min")
                if (recipe.cook_time != null) MetaChip("🔥 Cuisson", "${recipe.cook_time} min")
                if (scaledServings != null) MetaChip("👥 Portions", "$scaledServings")
            }
        }

        // Category + tags
        item {
            Row(Modifier.padding(horizontal = 16.dp, vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (recipe.category != null) {
                    AssistChip(onClick = {}, label = { Text(recipe.category, fontWeight = FontWeight.SemiBold) },
                        colors = AssistChipDefaults.assistChipColors(containerColor = MaterialTheme.colorScheme.primaryContainer, labelColor = MaterialTheme.colorScheme.onPrimaryContainer))
                }
                recipe.tags.forEach { AssistChip(onClick = {}, label = { Text(it) }) }
            }
        }

        // Nutrition
        item {
            SectionTitle("Nutrition")
            NutritionSection(recipe.nutrition, nutritionLoading, onAnalyzeNutrition)
        }

        // Ingrédients
        if (recipe.ingredients.isNotEmpty()) {
            item {
                Row(Modifier.padding(start = 16.dp, end = 16.dp, top = 24.dp, bottom = 4.dp).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("Ingrédients", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                }
            }
            item {
                Row(Modifier.padding(horizontal = 16.dp, vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("Portions :", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    listOf(0.5 to "½×", 1.0 to "1×", 2.0 to "2×", 3.0 to "3×").forEach { (v, label) ->
                        FilterChip(selected = scale == v, onClick = { scale = v }, label = { Text(label, style = MaterialTheme.typography.labelMedium) })
                    }
                }
            }
            items(recipe.ingredients) { ing ->
                val scaledQty = scaleQty(ing.quantity, scale)
                ListItem(
                    headlineContent = { Text(ing.name) },
                    leadingContent = {
                        Text(listOfNotNull(scaledQty, ing.unit).joinToString(" "), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.primary)
                    },
                    supportingContent = ing.notes?.let { { Text(it) } },
                )
                HorizontalDivider(Modifier.padding(horizontal = 16.dp))
            }
        }

        // Étapes
        if (recipe.steps.isNotEmpty()) {
            item { SectionTitle("Préparation") }
            itemsIndexed(recipe.steps) { idx, step ->
                Row(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Surface(shape = MaterialTheme.shapes.small, color = MaterialTheme.colorScheme.primary) {
                        Text("${idx + 1}", Modifier.padding(horizontal = 10.dp, vertical = 4.dp), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onPrimary, fontWeight = FontWeight.Bold)
                    }
                    Text(step.text, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
                }
            }
        }

        // Notes
        item {
            SectionTitle("Notes personnelles")
            OutlinedTextField(
                value = notesDraft,
                onValueChange = onNotesDraftChange,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                placeholder = { Text("Vos notes, astuces, modifications…") },
                minLines = 3,
            )
            Spacer(Modifier.height(8.dp))
            Button(
                onClick = onSaveNotes,
                enabled = !notesSaving,
                modifier = Modifier.padding(horizontal = 16.dp),
            ) {
                if (notesSaving) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                else Text("Sauvegarder les notes")
            }
        }
    }
}

@Composable
private fun NutritionSection(nutrition: Nutrition?, loading: Boolean, onAnalyze: () -> Unit) {
    if (nutrition != null) {
        Row(Modifier.padding(horizontal = 16.dp, vertical = 8.dp).fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (nutrition.calories != null) NutriChip("🔥", "${nutrition.calories.roundToInt()} kcal")
            if (nutrition.proteins != null) NutriChip("💪", "${nutrition.proteins.roundToInt()}g prot.")
            if (nutrition.carbs != null) NutriChip("🌾", "${nutrition.carbs.roundToInt()}g glucides")
            if (nutrition.fat != null) NutriChip("🧈", "${nutrition.fat.roundToInt()}g lip.")
        }
    } else {
        Row(Modifier.padding(horizontal = 16.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Non analysé", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            FilledTonalButton(onClick = onAnalyze, enabled = !loading) {
                if (loading) CircularProgressIndicator(Modifier.size(14.dp), strokeWidth = 2.dp)
                else Text("Analyser (IA)")
            }
        }
    }
}

@Composable
private fun NutriChip(emoji: String, label: String) {
    ElevatedCard(shape = MaterialTheme.shapes.small) {
        Column(Modifier.padding(horizontal = 10.dp, vertical = 6.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(emoji, style = MaterialTheme.typography.labelMedium)
            Text(label, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun MetaChip(label: String, value: String) {
    ElevatedCard(shape = MaterialTheme.shapes.medium) {
        Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(text, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold,
        modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 24.dp, bottom = 8.dp))
}
