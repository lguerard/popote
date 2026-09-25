package com.popote.ui.screens

import android.content.Intent
import android.net.Uri
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.popote.data.CookLog
import com.popote.data.Nutrition
import com.popote.data.Recipe
import com.popote.data.RecipeCollection
import com.popote.ui.components.LocalServerUrl
import com.popote.ui.components.Stars
import com.popote.ui.components.formatIsoDate
import com.popote.ui.components.formatSeconds
import com.popote.ui.components.imageUrl
import com.popote.ui.components.parseStepSeconds
import com.popote.ui.components.shareText
import com.popote.ui.viewmodels.RecipeDetailViewModel
import java.time.LocalDate
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
    val history by vm.history.collectAsState()
    val collections by vm.collections.collectAsState()
    var showDeleteDialog by remember { mutableStateOf(false) }
    var showCookedDialog by remember { mutableStateOf(false) }
    var showReextractDialog by remember { mutableStateOf(false) }
    var showCollections by remember { mutableStateOf(false) }
    var menuOpen by remember { mutableStateOf(false) }
    var cookingMode by remember { mutableStateOf(false) }

    val context = LocalContext.current

    // Écran toujours allumé en mode cuisine
    DisposableEffect(cookingMode) {
        val window = (context as? ComponentActivity)?.window
        if (cookingMode) window?.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        onDispose { window?.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
    }

    LaunchedEffect(recipeId) { vm.load(recipeId) }

    if (cookingMode && recipe != null) {
        CookingModeOverlay(
            recipe = recipe!!,
            onExit = { cookingMode = false },
            onCooked = { rating ->
                vm.markCooked(LocalDate.now(), rating, null)
                cookingMode = false
            },
        )
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

    if (showCookedDialog) {
        CookedDialog(
            onDismiss = { showCookedDialog = false },
            onConfirm = { date, rating, comment ->
                vm.markCooked(date, rating, comment)
                showCookedDialog = false
            },
        )
    }

    if (showReextractDialog && recipe != null) {
        ReextractDialog(
            hasLocalImage = recipe!!.thumbnail_url?.startsWith("/media/") == true,
            onDismiss = { showReextractDialog = false },
            onConfirm = { replaceImage ->
                vm.reextract(replaceImage)
                showReextractDialog = false
            },
        )
    }

    if (showCollections) {
        CollectionsSheet(
            collections = collections,
            onToggle = vm::toggleCollection,
            onCreate = vm::createCollection,
            onDismiss = { showCollections = false },
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
                    val r = recipe
                    if (r != null) {
                        IconButton(onClick = vm::toggleFavorite) {
                            Icon(
                                if (r.is_favorite) Icons.Default.Favorite else Icons.Outlined.FavoriteBorder,
                                "Favori",
                                tint = if (r.is_favorite) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        IconButton(onClick = {
                            vm.shareLink { link -> shareText(context, "${r.title}\n$link", "Partager la recette") }
                        }) { Icon(Icons.Default.Share, "Partager") }
                        Box {
                            IconButton(onClick = { menuOpen = true }) { Icon(Icons.Default.MoreVert, "Plus") }
                            DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                                DropdownMenuItem(
                                    text = { Text("Ajouter à un carnet") },
                                    leadingIcon = { Icon(Icons.Default.CollectionsBookmark, null) },
                                    onClick = { menuOpen = false; vm.loadCollections(); showCollections = true },
                                )
                                if (r.source_url != null) {
                                    DropdownMenuItem(
                                        text = { Text("Réextraire depuis la source") },
                                        leadingIcon = { Icon(Icons.Default.Refresh, null) },
                                        enabled = !r.reextracting,
                                        onClick = { menuOpen = false; showReextractDialog = true },
                                    )
                                }
                                if (r.share_token != null) {
                                    DropdownMenuItem(
                                        text = { Text("Désactiver le lien de partage") },
                                        leadingIcon = { Icon(Icons.Default.LinkOff, null) },
                                        onClick = { menuOpen = false; vm.revokeLink() },
                                    )
                                }
                                DropdownMenuItem(
                                    text = { Text("Supprimer", color = MaterialTheme.colorScheme.error) },
                                    leadingIcon = { Icon(Icons.Default.Delete, null, tint = MaterialTheme.colorScheme.error) },
                                    onClick = { menuOpen = false; showDeleteDialog = true },
                                )
                            }
                        }
                    }
                },
            )
        }
    ) { padding ->
        when {
            recipe == null && error != null -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(error!!, color = MaterialTheme.colorScheme.error)
                    Button(onClick = { vm.clearError(); vm.load(recipeId) }) { Text("Réessayer") }
                }
            }
            recipe == null -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            else -> RecipeContent(
                recipe = recipe!!,
                modifier = Modifier.padding(padding),
                actionError = error,
                onDismissError = vm::clearError,
                nutritionLoading = nutritionLoading,
                onAnalyzeNutrition = vm::analyzeNutrition,
                notesDraft = notesDraft ?: "",
                onNotesDraftChange = vm::setNotesDraft,
                notesSaving = notesSaving,
                onSaveNotes = vm::saveNotes,
                onStartCooking = { cookingMode = true },
                history = history,
                onRate = vm::setRating,
                onToggleCookAgain = vm::toggleCookAgain,
                onCooked = { showCookedDialog = true },
                onDeleteLog = vm::deleteCookLog,
            )
        }
    }
}

// ── Dialogues ─────────────────────────────────────────────────────────────────

@Composable
private fun CookedDialog(onDismiss: () -> Unit, onConfirm: (LocalDate, Int?, String?) -> Unit) {
    var daysAgo by remember { mutableIntStateOf(0) }
    var rating by remember { mutableStateOf<Int?>(null) }
    var comment by remember { mutableStateOf("") }
    val date = LocalDate.now().minusDays(daysAgo.toLong())
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Je l'ai cuisinée") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf(0 to "Aujourd'hui", 1 to "Hier", 2 to "Avant-hier").forEach { (d, label) ->
                        FilterChip(selected = daysAgo == d, onClick = { daysAgo = d }, label = { Text(label) })
                    }
                }
                Stars(rating, onChange = { rating = it })
                OutlinedTextField(
                    value = comment, onValueChange = { comment = it },
                    placeholder = { Text("Un mot ? (trop salé, doubler la sauce…)") },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = { Button(onClick = { onConfirm(date, rating, comment) }) { Text("Enregistrer") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Annuler") } },
    )
}

@Composable
private fun ReextractDialog(hasLocalImage: Boolean, onDismiss: () -> Unit, onConfirm: (Boolean) -> Unit) {
    var replaceImage by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Réextraire la recette ?") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Titre, ingrédients, étapes et temps seront relus depuis la source. Vos notes, avis et historique sont conservés.")
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = replaceImage, onCheckedChange = { replaceImage = it })
                    Column {
                        Text("Remplacer aussi l'image par celle de la source")
                        if (hasLocalImage) Text("Sinon, votre image est conservée.",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        },
        confirmButton = { Button(onClick = { onConfirm(replaceImage) }) { Text("Réextraire") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Annuler") } },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CollectionsSheet(
    collections: List<RecipeCollection>?,
    onToggle: (RecipeCollection) -> Unit,
    onCreate: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    var name by remember { mutableStateOf("") }
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("📚 Carnets", style = MaterialTheme.typography.titleLarge)
            when {
                collections == null -> CircularProgressIndicator(Modifier.padding(16.dp))
                collections.isEmpty() -> Text("Aucun carnet : créez le premier ci-dessous.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                else -> collections.forEach { c ->
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                        Checkbox(checked = c.contains_recipe == true, onCheckedChange = { onToggle(c) })
                        Text("${c.emoji ?: "📒"} ${c.name}", Modifier.weight(1f))
                        Text("${c.recipe_count}", style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(value = name, onValueChange = { name = it }, singleLine = true,
                    placeholder = { Text("Nouveau carnet…") }, modifier = Modifier.weight(1f))
                FilledTonalButton(onClick = { onCreate(name); name = "" }, enabled = name.isNotBlank()) { Text("Créer") }
            }
        }
    }
}

// ── Content ───────────────────────────────────────────────────────────────────

@Composable
private fun RecipeContent(
    recipe: Recipe,
    modifier: Modifier = Modifier,
    actionError: String? = null,
    onDismissError: () -> Unit = {},
    nutritionLoading: Boolean,
    onAnalyzeNutrition: () -> Unit,
    notesDraft: String,
    onNotesDraftChange: (String) -> Unit,
    notesSaving: Boolean,
    onSaveNotes: () -> Unit,
    onStartCooking: () -> Unit,
    history: List<CookLog>,
    onRate: (Int) -> Unit,
    onToggleCookAgain: () -> Unit,
    onCooked: () -> Unit,
    onDeleteLog: (String) -> Unit,
) {
    val context = LocalContext.current
    val server = LocalServerUrl.current
    var scale by remember { mutableDoubleStateOf(1.0) }
    val scaledServings = recipe.servings?.let { (it * scale).roundToInt() }

    LazyColumn(modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 32.dp)) {

        if (actionError != null) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
                ) {
                    Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(actionError, Modifier.weight(1f), color = MaterialTheme.colorScheme.onErrorContainer, style = MaterialTheme.typography.bodySmall)
                        TextButton(onClick = onDismissError) { Text("OK") }
                    }
                }
            }
        }

        // Réextraction en cours / échouée
        if (recipe.reextracting) {
            item {
                Card(Modifier.fillMaxWidth().padding(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                    Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                        Text(recipe.progress_message ?: "Réextraction en cours…", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        } else if (!recipe.error_msg.isNullOrBlank()) {
            item {
                Card(Modifier.fillMaxWidth().padding(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                    Text(recipe.error_msg, Modifier.padding(12.dp), style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onErrorContainer)
                }
            }
        }

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

        val image = imageUrl(recipe.thumbnail_url, server)
        if (image != null) {
            item {
                AsyncImage(
                    model = image,
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f),
                )
            }
        }

        // Avis : étoiles, « à refaire », historique résumé
        item {
            Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Stars(recipe.rating, onChange = onRate)
                    FilterChip(
                        selected = recipe.cook_again == true,
                        onClick = onToggleCookAgain,
                        label = { Text(if (recipe.cook_again == true) "🔁 À refaire !" else "🔁 À refaire ?") },
                    )
                }
                Text(
                    if (recipe.cooked_count > 0)
                        "Cuisinée ${recipe.cooked_count} fois · dernière le ${formatIsoDate(recipe.last_cooked_at)}"
                    else "Jamais cuisinée",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        // Cuisiner / Je l'ai cuisinée
        item {
            Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (recipe.steps.isNotEmpty()) {
                    Button(
                        onClick = onStartCooking,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.tertiary),
                    ) {
                        Icon(Icons.Default.Restaurant, null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("Mode cuisine")
                    }
                }
                OutlinedButton(onClick = onCooked, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Default.Check, null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Je l'ai cuisinée")
                }
            }
        }

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

        if (recipe.description != null) {
            item {
                Text(recipe.description, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
            }
        }

        item {
            Row(Modifier.padding(horizontal = 16.dp, vertical = 4.dp).fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (recipe.prep_time != null) MetaChip("🥄 Prép.", "${recipe.prep_time} min")
                if (recipe.cook_time != null) MetaChip("🔥 Cuisson", "${recipe.cook_time} min")
                if (scaledServings != null) MetaChip("👥 Portions", "$scaledServings")
            }
        }

        item {
            Row(Modifier.padding(horizontal = 16.dp, vertical = 4.dp).horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (recipe.category != null) {
                    Surface(shape = MaterialTheme.shapes.small, color = MaterialTheme.colorScheme.primaryContainer) {
                        Text(recipe.category, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onPrimaryContainer,
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp))
                    }
                }
                recipe.tags.forEach { tag ->
                    Surface(shape = MaterialTheme.shapes.small, color = MaterialTheme.colorScheme.surfaceVariant) {
                        Text(tag, color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp))
                    }
                }
            }
        }

        item {
            SectionTitle("Nutrition")
            NutritionSection(recipe.nutrition, nutritionLoading, onAnalyzeNutrition)
        }

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

        if (recipe.steps.isNotEmpty()) {
            item { SectionTitle("Préparation") }
            itemsIndexed(recipe.steps) { idx, step ->
                Row(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Surface(shape = MaterialTheme.shapes.small, color = MaterialTheme.colorScheme.primary) {
                        Text("${idx + 1}", Modifier.padding(horizontal = 10.dp, vertical = 4.dp), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onPrimary, fontWeight = FontWeight.Bold)
                    }
                    Column(Modifier.weight(1f)) {
                        Text(step.text, style = MaterialTheme.typography.bodyLarge)
                        parseStepSeconds(step.text)?.let { sec ->
                            Text("⏱ ${formatSeconds(sec)}", style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.primary)
                        }
                    }
                }
            }
        }

        // Historique
        item {
            SectionTitle("Historique")
            if (history.isEmpty()) {
                Text("Pas encore cuisinée.", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 16.dp))
            }
        }
        items(history, key = { it.id }) { log ->
            ListItem(
                headlineContent = { Text(formatIsoDate(log.cooked_on)) },
                supportingContent = log.comment?.let { { Text(it) } },
                leadingContent = { if (log.rating != null) Stars(log.rating, size = 14.sp) },
                trailingContent = {
                    IconButton(onClick = { onDeleteLog(log.id) }) {
                        Icon(Icons.Default.Close, "Supprimer", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                },
            )
        }

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
