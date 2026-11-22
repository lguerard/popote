package com.popote.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.EmojiEvents
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SwapVert
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.SubcomposeAsyncImage
import com.popote.data.Recipe
import com.popote.ui.components.BentoTile
import com.popote.ui.components.CookieShape
import com.popote.ui.components.LocalServerUrl
import com.popote.ui.components.Pill
import com.popote.ui.components.RecipeCard
import com.popote.ui.components.RecipePlaceholder
import com.popote.ui.components.heroColors
import com.popote.ui.components.imageUrl
import com.popote.ui.components.ingredientAmount
import com.popote.ui.viewmodels.Dashboard
import com.popote.ui.viewmodels.HomeViewModel
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToInt

data class CategoryItem(val value: String?, val label: String, val emoji: String)
data class TimeItem(val value: Int?, val label: String)

val CATEGORIES = listOf(
    CategoryItem(null, "Tout", "🍽️"),
    CategoryItem("petit-déjeuner", "Petit-déj", "☕"),
    CategoryItem("entrée", "Entrée", "🥗"),
    CategoryItem("plat", "Plat", "🍲"),
    CategoryItem("dessert", "Dessert", "🍰"),
    CategoryItem("snack", "Snack", "🥨"),
    CategoryItem("soupe", "Soupe", "🍜"),
    CategoryItem("apéritif", "Apéritif", "🥂"),
    CategoryItem("boisson", "Boisson", "🥤"),
    CategoryItem("sauce", "Sauce", "🫙"),
)

val HISTORY_FILTERS = listOf(
    "favorites" to "Favoris",
    "never_cooked" to "Jamais faites",
    "cook_again" to "À refaire",
    "shared" to "Reçues",
)

val SORTS = listOf(
    "recent" to "Plus récentes",
    "rating" to "Mieux notées",
    "last_cooked" to "Cuisinées récemment",
    "most_cooked" to "Les plus cuisinées",
    "title" to "Titre (A→Z)",
)

val TIME_FILTERS = listOf(
    TimeItem(null, "Tout"),
    TimeItem(30, "≤ 30 min"),
    TimeItem(60, "≤ 1 h"),
)

/**
 * Accueil : le repas prévu (« Ce soir »), quatre tuiles (courses, semaine,
 * frigo, assistant), puis toutes les recettes avec recherche et filtres.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    onRecipeClick: (String) -> Unit,
    onAddClick: () -> Unit,
    onSettingsClick: () -> Unit,
    onAchievementsClick: () -> Unit = {},
    onAssistantClick: () -> Unit = {},
    onCook: (id: String, servings: Int) -> Unit = { id, _ -> onRecipeClick(id) },
    onOpenTab: (String) -> Unit = {},
    vm: HomeViewModel = viewModel(),
) {
    val recipes by vm.recipes.collectAsState()
    val isLoading by vm.isLoading.collectAsState()
    val error by vm.error.collectAsState()
    val search by vm.search.collectAsState()
    val selectedCategory by vm.category.collectAsState()
    val selectedMaxTime by vm.maxTime.collectAsState()
    val history by vm.history.collectAsState()
    val sort by vm.sort.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val dashboard by vm.dashboard.collectAsState()
    var sortMenu by remember { mutableStateOf(false) }
    var moreMenu by remember { mutableStateOf(false) }
    val cs = MaterialTheme.colorScheme

    // À chaque retour sur l'accueil : planning et courses ont pu changer.
    LaunchedEffect(Unit) { vm.loadDashboard() }

    Scaffold { padding ->
        PullToRefreshBox(
            isRefreshing = refreshing,
            onRefresh = { vm.load(pullToRefresh = true); vm.loadDashboard() },
            modifier = Modifier.padding(padding).fillMaxSize(),
        ) {
            LazyVerticalGrid(
                columns = GridCells.Adaptive(160.dp),
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 24.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.fillMaxSize(),
            ) {
                item(span = { GridItemSpan(maxLineSpan) }) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(
                                LocalDate.now().format(DateTimeFormatter.ofPattern("EEEE d MMMM", Locale.FRENCH))
                                    .replaceFirstChar { it.uppercase() },
                                style = MaterialTheme.typography.titleSmall,
                                color = cs.onSurfaceVariant,
                            )
                            Text("On mange quoi ?", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Black)
                        }
                        FilledIconButton(
                            onClick = onAssistantClick,
                            modifier = Modifier.size(48.dp),
                            colors = IconButtonDefaults.filledIconButtonColors(containerColor = cs.inversePrimary,
                                contentColor = cs.onPrimaryContainer),
                        ) { Icon(Icons.Default.AutoAwesome, "Assistant culinaire") }
                        Box {
                            IconButton(onClick = { moreMenu = true }, modifier = Modifier.size(48.dp)) {
                                Icon(Icons.Default.MoreVert, "Plus")
                            }
                            DropdownMenu(expanded = moreMenu, onDismissRequest = { moreMenu = false }) {
                                DropdownMenuItem(text = { Text("Succès") }, leadingIcon = { Icon(Icons.Default.EmojiEvents, null) },
                                    onClick = { moreMenu = false; onAchievementsClick() })
                                DropdownMenuItem(text = { Text("Paramètres") }, leadingIcon = { Icon(Icons.Default.Settings, null) },
                                    onClick = { moreMenu = false; onSettingsClick() })
                            }
                        }
                    }
                }

                item(span = { GridItemSpan(maxLineSpan) }) {
                    TonightHero(
                        dashboard = dashboard,
                        onOpen = onRecipeClick,
                        onCook = onCook,
                        onPlan = { onOpenTab("planning") },
                        onIdea = onAssistantClick,
                    )
                }

                item(span = { GridItemSpan(maxLineSpan) }) {
                    ShortcutTiles(dashboard, onOpenTab = onOpenTab, onAssistant = onAssistantClick)
                }

                item(span = { GridItemSpan(maxLineSpan) }) {
                    Row(Modifier.padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("Recettes", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Black,
                            modifier = Modifier.weight(1f))
                        Box {
                            IconButton(onClick = { sortMenu = true }) { Icon(Icons.Default.SwapVert, "Trier") }
                            DropdownMenu(expanded = sortMenu, onDismissRequest = { sortMenu = false }) {
                                SORTS.forEach { (value, label) ->
                                    DropdownMenuItem(
                                        text = { Text(if (sort == value) "✓ $label" else label) },
                                        onClick = { vm.setSort(value); sortMenu = false },
                                    )
                                }
                            }
                        }
                        Button(onClick = onAddClick, contentPadding = PaddingValues(start = 14.dp, end = 18.dp),
                            modifier = Modifier.height(48.dp)) {
                            Icon(Icons.Default.Add, null, Modifier.size(20.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("Importer", fontWeight = FontWeight.ExtraBold)
                        }
                    }
                }

                item(span = { GridItemSpan(maxLineSpan) }) {
                    TextField(
                        value = search,
                        onValueChange = vm::onSearchChange,
                        placeholder = { Text("Un plat, un ingrédient, « sans four »…") },
                        leadingIcon = { Icon(Icons.Default.Search, null) },
                        singleLine = true,
                        shape = CircleShape,
                        colors = TextFieldDefaults.colors(
                            focusedIndicatorColor = androidx.compose.ui.graphics.Color.Transparent,
                            unfocusedIndicatorColor = androidx.compose.ui.graphics.Color.Transparent,
                            unfocusedContainerColor = cs.surfaceContainerHigh,
                            focusedContainerColor = cs.surfaceContainerHigh,
                        ),
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                item(span = { GridItemSpan(maxLineSpan) }) {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(
                            modifier = Modifier.horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            CATEGORIES.forEach { cat ->
                                RoundChip(cat.label, selected = selectedCategory == cat.value, onClick = { vm.setCategory(cat.value) })
                            }
                        }
                        Row(
                            modifier = Modifier.horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            TIME_FILTERS.filter { it.value != null }.forEach { t ->
                                RoundChip(t.label, selected = selectedMaxTime == t.value,
                                    onClick = { vm.setMaxTime(if (selectedMaxTime == t.value) null else t.value) }, tonal = true)
                            }
                            HISTORY_FILTERS.forEach { (value, label) ->
                                RoundChip(label, selected = history == value,
                                    onClick = { vm.setHistory(if (history == value) null else value) }, tonal = true)
                            }
                            if (selectedCategory != null || selectedMaxTime != null || history != null) {
                                TextButton(onClick = vm::resetFilters) { Text("Réinitialiser", color = cs.error) }
                            }
                        }
                    }
                }

                when {
                    isLoading -> item(span = { GridItemSpan(maxLineSpan) }) {
                        Box(Modifier.fillMaxWidth().padding(48.dp), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator(color = cs.primary)
                        }
                    }
                    error != null -> item(span = { GridItemSpan(maxLineSpan) }) {
                        Column(Modifier.fillMaxWidth().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            Text(error!!, style = MaterialTheme.typography.bodyLarge, color = cs.error)
                            Button(onClick = { vm.load() }) { Text("Réessayer") }
                        }
                    }
                    recipes.isEmpty() -> item(span = { GridItemSpan(maxLineSpan) }) {
                        Column(Modifier.fillMaxWidth().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("Aucune recette", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                            Text("Importez-en une depuis une vidéo, un site ou une photo.", style = MaterialTheme.typography.bodyMedium,
                                color = cs.onSurfaceVariant)
                        }
                    }
                    else -> items(recipes, key = { it.id }) { recipe ->
                        RecipeCard(recipe = recipe, onClick = { onRecipeClick(recipe.id) })
                    }
                }
            }
        }
    }
}

/** Filtre en pilule, plus grand que le FilterChip par défaut (doigt mouillé en cuisine). */
@Composable
private fun RoundChip(label: String, selected: Boolean, onClick: () -> Unit, tonal: Boolean = false) {
    val cs = MaterialTheme.colorScheme
    val hero = heroColors()
    Surface(
        onClick = onClick,
        shape = CircleShape,
        color = when {
            selected && tonal -> cs.primaryContainer
            selected -> hero.container
            else -> cs.surface
        },
        contentColor = when {
            selected && tonal -> cs.onPrimaryContainer
            selected -> hero.content
            else -> cs.onSurface
        },
        border = if (selected) null else BorderStroke(1.5.dp, cs.outlineVariant),
        modifier = Modifier.height(44.dp),
    ) {
        Box(Modifier.padding(horizontal = 18.dp), contentAlignment = Alignment.Center) {
            Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
        }
    }
}

/** Le grand bloc du haut : le repas prévu aujourd'hui, ou une invitation à en prévoir un. */
@Composable
private fun TonightHero(
    dashboard: Dashboard,
    onOpen: (String) -> Unit,
    onCook: (String, Int) -> Unit,
    onPlan: () -> Unit,
    onIdea: () -> Unit,
) {
    val hero = heroColors()
    val recipe = dashboard.tonight
    Surface(
        onClick = { if (recipe != null) onOpen(recipe.id) else onPlan() },
        shape = RoundedCornerShape(36.dp),
        color = hero.container,
        contentColor = hero.content,
        modifier = Modifier.fillMaxWidth(),
    ) {
        if (recipe == null) {
            Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Pill("Ce soir", hero.accent, hero.onAccent)
                Text("Rien de prévu pour l'instant", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Black)
                Text("Choisis une recette dans le planning, ou demande une idée avec ce qu'il te reste.",
                    style = MaterialTheme.typography.bodyLarge, color = hero.muted)
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                    OutlinedButton(onClick = onPlan, border = BorderStroke(1.5.dp, hero.outline),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = hero.content),
                        modifier = Modifier.height(52.dp)) { Text("Planifier", fontWeight = FontWeight.Bold) }
                    Spacer(Modifier.weight(1f))
                    CookieButton("Une idée ?", onClick = onIdea, size = 96)
                }
            }
            return@Surface
        }
        TonightRecipe(recipe, dashboard.tonightMeal, onCook)
    }
}

@Composable
private fun TonightRecipe(recipe: Recipe, meal: String?, onCook: (String, Int) -> Unit) {
    val hero = heroColors()
    val base = recipe.servings?.takeIf { it > 0 }
    var servings by rememberSaveable(recipe.id) { mutableIntStateOf(base ?: 0) }
    val scale = if (base != null && servings > 0) servings.toDouble() / base else 1.0
    Box {
        // Photo de la recette, en assiette, débordant du coin.
        Box(
            Modifier.align(Alignment.TopEnd).offset(x = 28.dp, y = (-24).dp).size(150.dp)
                .clip(CircleShape).background(hero.raised).padding(12.dp).clip(CircleShape),
        ) {
            val image = imageUrl(recipe.thumbnail_url, LocalServerUrl.current)
            if (image != null) SubcomposeAsyncImage(
                model = image, contentDescription = null, contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
                error = { RecipePlaceholder(recipe.category) },
                loading = { RecipePlaceholder(recipe.category) },
            ) else RecipePlaceholder(recipe.category)
        }
        Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Pill(if (meal == "déjeuner") "Ce midi · déjeuner" else "Ce soir · dîner", hero.accent, hero.onAccent)
            Column(Modifier.padding(end = 110.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(recipe.title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Black,
                    maxLines = 3, overflow = TextOverflow.Ellipsis)
                Text(
                    listOfNotNull(
                        recipe.totalTime.takeIf { it > 0 }?.let { "$it min" },
                        recipe.category?.replaceFirstChar { it.uppercase() },
                        sourceLabel(recipe.source_type)?.let { "depuis $it".lowercase() },
                    ).joinToString(" · "),
                    style = MaterialTheme.typography.bodyMedium, color = hero.muted,
                )
            }
            if (base != null) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Portions", style = MaterialTheme.typography.titleSmall, color = hero.muted)
                    Row(
                        Modifier.clip(CircleShape).background(hero.raised).padding(4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        IconButton(onClick = { if (servings > 1) servings-- }, modifier = Modifier.size(44.dp)) {
                            Icon(Icons.Default.Remove, "Une portion de moins", tint = hero.content)
                        }
                        Text("$servings", Modifier.widthIn(min = 28.dp), fontWeight = FontWeight.Black, fontSize = 20.sp,
                            textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                        IconButton(onClick = { if (servings < 24) servings++ }, modifier = Modifier.size(44.dp)) {
                            Icon(Icons.Default.Add, "Une portion de plus", tint = hero.content)
                        }
                    }
                }
            }
            Row(verticalAlignment = Alignment.Bottom) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    recipe.ingredients.take(3).forEach { ing ->
                        Text(
                            listOf(ingredientAmount(ing, scale), ing.name).filter { it.isNotBlank() }.joinToString(" "),
                            style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = hero.muted,
                            maxLines = 1, overflow = TextOverflow.Ellipsis,
                        )
                    }
                    if (recipe.ingredients.size > 3) Text("+ ${recipe.ingredients.size - 3} autres",
                        style = MaterialTheme.typography.bodySmall, color = hero.muted)
                }
                CookieButton("Cuisiner", onClick = { onCook(recipe.id, if (base != null) servings else 0) })
            }
        }
    }
}

/** Gros bouton festonné du bloc sombre. */
@Composable
private fun CookieButton(label: String, onClick: () -> Unit, size: Int = 112) {
    val hero = heroColors()
    Surface(
        onClick = onClick,
        shape = remember { CookieShape() },
        color = hero.accent,
        contentColor = hero.onAccent,
        modifier = Modifier.size(size.dp),
    ) {
        Box(contentAlignment = Alignment.Center) {
            Text(label, fontWeight = FontWeight.Black, fontSize = if (size >= 112) 18.sp else 16.sp)
        }
    }
}

/** Quatre raccourcis : courses, semaine, frigo, assistant. */
@Composable
private fun ShortcutTiles(dashboard: Dashboard, onOpenTab: (String) -> Unit, onAssistant: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.height(124.dp)) {
            BentoTile(cs.tertiaryContainer, cs.onTertiaryContainer, onClick = { onOpenTab("shopping") }, Modifier.weight(1f)) {
                Text("Courses", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                Column {
                    val left = dashboard.shoppingLeft
                    Text(
                        when (left) { null -> "Liste"; 0 -> "Tout est pris"; 1 -> "1 article"; else -> "$left articles" },
                        style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Black, maxLines = 1,
                    )
                    Text(if (left == null || left > 0) "à acheter" else "liste à jour", style = MaterialTheme.typography.bodyMedium)
                }
            }
            BentoTile(cs.secondaryContainer, cs.onSecondaryContainer, onClick = { onOpenTab("planning") }, Modifier.weight(1f),
                shape = RoundedCornerShape(28.dp, 28.dp, 28.dp, 8.dp)) {
                Text("Dîners de la semaine", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                val week = dashboard.weekDinners.ifEmpty { List(7) { false } }
                val planned = week.count { it }
                Row(
                    Modifier.fillMaxWidth().semantics { contentDescription = "$planned dîners prévus sur 7" },
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    week.forEach { on ->
                        Box(
                            Modifier.weight(1f).height(34.dp).clip(RoundedCornerShape(8.dp))
                                .then(
                                    if (on) Modifier.background(cs.onSecondaryContainer)
                                    else Modifier.border(1.5.dp, cs.onSecondaryContainer.copy(alpha = 0.45f), RoundedCornerShape(8.dp))
                                ),
                        )
                    }
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.height(124.dp)) {
            BentoTile(cs.surfaceContainerHigh, cs.onSurface, onClick = { onOpenTab("fridge") }, Modifier.weight(1f),
                shape = RoundedCornerShape(28.dp, 8.dp, 28.dp, 28.dp)) {
                Text("Frigo", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                Text("Que faire avec ce qu'il me reste ?", style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.ExtraBold, maxLines = 3)
            }
            BentoTile(cs.primaryContainer, cs.onPrimaryContainer, onClick = onAssistant, Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Icon(Icons.Default.AutoAwesome, null, Modifier.size(16.dp))
                    Text("Assistant", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                }
                Surface(shape = RoundedCornerShape(16.dp), color = cs.surface, contentColor = cs.onSurface) {
                    Text("« Une idée pour ce soir ? »", Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
                        style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, maxLines = 2)
                }
            }
        }
    }
}

/** « Vidéo », « Site »… : d'où vient la recette. */
fun sourceLabel(type: String?): String? = when (type) {
    "video" -> "Vidéo"
    "web" -> "Site"
    "text" -> "Texte"
    "manual" -> "Maison"
    else -> null
}
