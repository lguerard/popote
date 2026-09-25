package com.popote.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.SubcomposeAsyncImage
import com.popote.data.Recipe

@Composable
fun RecipeCard(recipe: Recipe, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        shape = MaterialTheme.shapes.large,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp, hoveredElevation = 4.dp),
    ) {
        Column {
            Box(
                modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f)
                    .clip(MaterialTheme.shapes.large),
                contentAlignment = Alignment.Center,
            ) {
                val image = imageUrl(recipe.thumbnail_url, LocalServerUrl.current)
                if (image != null) {
                    // Image absente ou lien expiré (Instagram, TikTok…) : visuel de
                    // remplacement plutôt qu'un rectangle blanc.
                    SubcomposeAsyncImage(
                        model = image,
                        contentDescription = recipe.title,
                        contentScale = ContentScale.Crop,
                        modifier = Modifier.fillMaxSize(),
                        error = { RecipePlaceholder(recipe.category) },
                        loading = { RecipePlaceholder(recipe.category) },
                    )
                } else {
                    RecipePlaceholder(recipe.category)
                }
                // Source icon badge
                Surface(
                    modifier = Modifier.align(Alignment.TopEnd).padding(6.dp),
                    shape = MaterialTheme.shapes.small,
                    color = MaterialTheme.colorScheme.surface.copy(alpha = 0.85f),
                ) {
                    Text(
                        text = when (recipe.source_type) {
                            "video" -> "🎬"; "web" -> "🌐"; "text" -> "📝"; else -> "✏️"
                        },
                        modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp),
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    recipe.title,
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (recipe.totalTime > 0)
                        Text("⏱ ${recipe.totalTime} min", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (recipe.servings != null)
                        Text("👥 ${recipe.servings}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if ((recipe.rating ?: 0) > 0)
                        Text("★ ${recipe.rating}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                    if (recipe.cook_again == true)
                        Text("🔁", style = MaterialTheme.typography.labelSmall)
                }
                if (recipe.tags.isNotEmpty()) {
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        recipe.tags.take(2).forEach { tag ->
                            Surface(
                                shape = MaterialTheme.shapes.small,
                                color = MaterialTheme.colorScheme.surfaceVariant,
                            ) {
                                Text(
                                    tag,
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

private val CATEGORY_EMOJI = mapOf(
    "petit-déjeuner" to "☕", "entrée" to "🥗", "plat" to "🍲", "dessert" to "🍰",
    "snack" to "🥨", "soupe" to "🍜", "apéritif" to "🥂", "boisson" to "🥤", "sauce" to "🫙",
)

@Composable
fun RecipePlaceholder(category: String?) {
    Surface(color = MaterialTheme.colorScheme.primaryContainer, modifier = Modifier.fillMaxSize()) {
        Box(contentAlignment = Alignment.Center) {
            Text(CATEGORY_EMOJI[category] ?: "🍽️", style = MaterialTheme.typography.displaySmall)
        }
    }
}
