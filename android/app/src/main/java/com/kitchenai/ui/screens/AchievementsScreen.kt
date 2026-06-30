package com.kitchenai.ui.screens

import android.app.Application
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kitchenai.R
import com.kitchenai.data.Achievement
import com.kitchenai.data.RecipeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class AchievementsViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)
    private val _achievements = MutableStateFlow<List<Achievement>>(emptyList())
    val achievements: StateFlow<List<Achievement>> = _achievements.asStateFlow()

    init { load() }

    private fun load() {
        viewModelScope.launch {
            try { _achievements.value = repo.getAchievements() } catch (_: Exception) {}
        }
    }
}

private val CATEGORY_ORDER = listOf("collection", "cuisine", "organisation", "decouverte", "perfectionniste")

@Composable
private fun categoryLabel(key: String): String = when (key) {
    "collection" -> stringResource(R.string.achievement_cat_collection)
    "cuisine" -> stringResource(R.string.achievement_cat_cooking)
    "organisation" -> stringResource(R.string.achievement_cat_organisation)
    "decouverte" -> stringResource(R.string.achievement_cat_discovery)
    "perfectionniste" -> stringResource(R.string.achievement_cat_perfectionist)
    else -> key
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AchievementsScreen(onBack: () -> Unit, vm: AchievementsViewModel = viewModel()) {
    val achievements by vm.achievements.collectAsState()
    val grouped = achievements.groupBy { it.category }
    val total = achievements.size
    val unlocked = achievements.count { it.isUnlocked }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.achievements_title)) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back)) } },
            )
        }
    ) { padding ->
        LazyColumn(Modifier.padding(padding).fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            item {
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(stringResource(R.string.achievements_overall_progress), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                            Text("$unlocked/$total", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                        }
                        LinearProgressIndicator(
                            progress = { if (total > 0) unlocked.toFloat() / total else 0f },
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
            }

            CATEGORY_ORDER.forEach { cat ->
                val catItems = grouped[cat] ?: return@forEach
                item(key = "header_$cat") {
                    Text(categoryLabel(cat), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                items(catItems, key = { it.id }) { ach ->
                    AchievementCard(ach)
                }
            }
        }
    }
}

@Composable
private fun AchievementCard(a: Achievement) {
    val unlocked = a.isUnlocked
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (unlocked) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant,
        ),
    ) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(a.icon, style = MaterialTheme.typography.headlineMedium,
                color = if (unlocked) Color.Unspecified else Color.Gray)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text(a.name, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold,
                        color = if (unlocked) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurfaceVariant)
                    if (unlocked && a.unlocked_at != null) {
                        Text(a.unlocked_at.take(10), style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary)
                    }
                }
                Text(a.description, style = MaterialTheme.typography.bodySmall,
                    color = if (unlocked) MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f) else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f))
                if (a.goal > 1) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        LinearProgressIndicator(
                            progress = { a.progressFraction },
                            modifier = Modifier.weight(1f),
                        )
                        Text("${minOf(a.progress, a.goal)}/${a.goal}", style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}
