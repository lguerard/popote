package com.kitchenai.ui.screens

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kitchenai.R
import com.kitchenai.ui.components.RecipeCard
import com.kitchenai.ui.viewmodels.HomeViewModel

data class CategoryItem(val value: String?, val label: String, val emoji: String)
data class TimeItem(val value: Int?, val label: String)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    onRecipeClick: (String) -> Unit,
    onAddClick: () -> Unit,
    onSettingsClick: () -> Unit,
    vm: HomeViewModel = viewModel(),
) {
    val recipes by vm.recipes.collectAsState()
    val isLoading by vm.isLoading.collectAsState()
    val error by vm.error.collectAsState()
    val search by vm.search.collectAsState()
    val selectedCategory by vm.category.collectAsState()
    val selectedMaxTime by vm.maxTime.collectAsState()
    val scrollBehavior = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()

    val categories = listOf(
        CategoryItem(null, stringResource(R.string.cat_all), "🍽️"),
        CategoryItem("petit-déjeuner", stringResource(R.string.cat_breakfast), "☕"),
        CategoryItem("entrée", stringResource(R.string.cat_starter), "🥗"),
        CategoryItem("plat", stringResource(R.string.cat_main), "🍲"),
        CategoryItem("dessert", stringResource(R.string.cat_dessert), "🍰"),
        CategoryItem("snack", stringResource(R.string.cat_snack), "🥨"),
        CategoryItem("soupe", stringResource(R.string.cat_soup), "🍜"),
        CategoryItem("apéritif", stringResource(R.string.cat_aperitif), "🥂"),
        CategoryItem("boisson", stringResource(R.string.cat_drink), "🥤"),
        CategoryItem("sauce", stringResource(R.string.cat_sauce), "🫙"),
    )

    val timeFilters = listOf(
        TimeItem(null, stringResource(R.string.time_all)),
        TimeItem(30, stringResource(R.string.time_30min)),
        TimeItem(60, stringResource(R.string.time_1h)),
    )

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        topBar = {
            LargeTopAppBar(
                title = { Text("🍳 Popote") },
                actions = {
                    IconButton(onClick = onSettingsClick) {
                        Icon(Icons.Default.Settings, contentDescription = stringResource(R.string.settings))
                    }
                },
                scrollBehavior = scrollBehavior,
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = onAddClick,
                icon = { Icon(Icons.Default.Add, null) },
                text = { Text(stringResource(R.string.add)) },
                containerColor = MaterialTheme.colorScheme.primary,
                contentColor = MaterialTheme.colorScheme.onPrimary,
            )
        },
    ) { padding ->
        Column(Modifier.padding(padding)) {
            SearchBar(
                inputField = {
                    SearchBarDefaults.InputField(
                        query = search,
                        onQueryChange = vm::onSearchChange,
                        onSearch = {},
                        expanded = false,
                        onExpandedChange = {},
                        placeholder = { Text(stringResource(R.string.search_placeholder)) },
                        leadingIcon = { Icon(Icons.Default.Search, null) },
                    )
                },
                expanded = false,
                onExpandedChange = {},
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            ) {}

            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                categories.forEach { cat ->
                    FilterChip(
                        selected = selectedCategory == cat.value,
                        onClick = { vm.setCategory(cat.value) },
                        label = { Text("${cat.emoji} ${cat.label}") },
                    )
                }
            }

            Row(
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text("⏱", style = MaterialTheme.typography.labelMedium, modifier = Modifier.align(Alignment.CenterVertically))
                timeFilters.forEach { t ->
                    FilterChip(
                        selected = selectedMaxTime == t.value,
                        onClick = { vm.setMaxTime(t.value) },
                        label = { Text(t.label, style = MaterialTheme.typography.labelSmall) },
                    )
                }
                if (selectedCategory != null || selectedMaxTime != null) {
                    TextButton(onClick = vm::resetFilters, contentPadding = PaddingValues(horizontal = 8.dp)) {
                        Text(stringResource(R.string.filter_reset), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.error)
                    }
                }
            }

            when {
                isLoading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
                }
                error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(error!!, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.error)
                        Button(onClick = { vm.load() }) { Text(stringResource(R.string.retry)) }
                    }
                }
                recipes.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("🍽️", style = MaterialTheme.typography.displayLarge)
                        Spacer(Modifier.height(16.dp))
                        Text(stringResource(R.string.no_recipes), style = MaterialTheme.typography.titleLarge)
                        Text(stringResource(R.string.no_recipes_hint), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                else -> LazyVerticalGrid(
                    columns = GridCells.Adaptive(180.dp),
                    contentPadding = PaddingValues(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    items(recipes, key = { it.id }) { recipe ->
                        RecipeCard(recipe = recipe, onClick = { onRecipeClick(recipe.id) })
                    }
                    item { Spacer(Modifier.height(80.dp)) }
                }
            }
        }
    }
}
