package com.popote.ui.screens

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.EmojiEvents
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SwapVert
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.popote.ui.components.RecipeCard
import com.popote.ui.viewmodels.HomeViewModel

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
    "favorites" to "❤️ Favoris",
    "never_cooked" to "🆕 Jamais faites",
    "cook_again" to "🔁 À refaire",
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
    TimeItem(60, "≤ 1h"),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    onRecipeClick: (String) -> Unit,
    onAddClick: () -> Unit,
    onSettingsClick: () -> Unit,
    onAchievementsClick: () -> Unit = {},
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
    var sortMenu by remember { mutableStateOf(false) }
    val scrollBehavior = TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        topBar = {
            // Barre compacte, masquée en défilant : l'écran est pour les recettes.
            TopAppBar(
                title = { Text("🍳 Popote") },
                actions = {
                    Box {
                        IconButton(onClick = { sortMenu = true }) {
                            Icon(Icons.Default.SwapVert, contentDescription = "Trier")
                        }
                        DropdownMenu(expanded = sortMenu, onDismissRequest = { sortMenu = false }) {
                            SORTS.forEach { (value, label) ->
                                DropdownMenuItem(
                                    text = { Text(if (sort == value) "✓ $label" else label) },
                                    onClick = { vm.setSort(value); sortMenu = false },
                                )
                            }
                        }
                    }
                    IconButton(onClick = onAchievementsClick) {
                        Icon(Icons.Default.EmojiEvents, contentDescription = "Succès")
                    }
                    IconButton(onClick = onSettingsClick) {
                        Icon(Icons.Default.Settings, contentDescription = "Paramètres")
                    }
                },
                scrollBehavior = scrollBehavior,
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = onAddClick,
                icon = { Icon(Icons.Default.Add, null) },
                text = { Text("Ajouter") },
                containerColor = MaterialTheme.colorScheme.primary,
                contentColor = MaterialTheme.colorScheme.onPrimary,
            )
        },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = refreshing,
            onRefresh = { vm.load(pullToRefresh = true) },
            modifier = Modifier.padding(padding).fillMaxSize(),
        ) {
            // Recherche et filtres défilent avec la grille au lieu de rester
            // figés en haut : ils ne mangent plus la moitié de l'écran.
            LazyVerticalGrid(
                columns = GridCells.Adaptive(160.dp),
                contentPadding = PaddingValues(start = 12.dp, end = 12.dp, top = 4.dp, bottom = 88.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.fillMaxSize(),
            ) {
                item(span = { GridItemSpan(maxLineSpan) }) {
                    OutlinedTextField(
                        value = search,
                        onValueChange = vm::onSearchChange,
                        placeholder = { Text("Rechercher une recette…") },
                        leadingIcon = { Icon(Icons.Default.Search, null) },
                        singleLine = true,
                        shape = RoundedCornerShape(28.dp),
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                item(span = { GridItemSpan(maxLineSpan) }) {
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Row(
                            modifier = Modifier.horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            CATEGORIES.forEach { cat ->
                                FilterChip(
                                    selected = selectedCategory == cat.value,
                                    onClick = { vm.setCategory(cat.value) },
                                    label = { Text("${cat.emoji} ${cat.label}") },
                                )
                            }
                        }
                        Row(
                            modifier = Modifier.horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            HISTORY_FILTERS.forEach { (value, label) ->
                                FilterChip(
                                    selected = history == value,
                                    onClick = { vm.setHistory(if (history == value) null else value) },
                                    label = { Text(label, style = MaterialTheme.typography.labelSmall) },
                                )
                            }
                            TIME_FILTERS.filter { it.value != null }.forEach { t ->
                                FilterChip(
                                    selected = selectedMaxTime == t.value,
                                    onClick = { vm.setMaxTime(if (selectedMaxTime == t.value) null else t.value) },
                                    label = { Text("⏱ ${t.label}", style = MaterialTheme.typography.labelSmall) },
                                )
                            }
                            if (selectedCategory != null || selectedMaxTime != null || history != null) {
                                TextButton(onClick = vm::resetFilters, contentPadding = PaddingValues(horizontal = 8.dp)) {
                                    Text("Réinitialiser", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.error)
                                }
                            }
                        }
                    }
                }

                when {
                    isLoading -> item(span = { GridItemSpan(maxLineSpan) }) {
                        Box(Modifier.fillMaxWidth().padding(48.dp), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
                        }
                    }
                    error != null -> item(span = { GridItemSpan(maxLineSpan) }) {
                        Column(Modifier.fillMaxWidth().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            Text(error!!, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.error)
                            Button(onClick = { vm.load() }) { Text("Réessayer") }
                        }
                    }
                    recipes.isEmpty() -> item(span = { GridItemSpan(maxLineSpan) }) {
                        Column(Modifier.fillMaxWidth().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("🍽️", style = MaterialTheme.typography.displayLarge)
                            Spacer(Modifier.height(16.dp))
                            Text("Aucune recette", style = MaterialTheme.typography.titleLarge)
                            Text("Appuyez sur Ajouter pour commencer", style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
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
