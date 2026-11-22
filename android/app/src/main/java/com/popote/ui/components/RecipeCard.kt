package com.popote.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.Schedule
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.SubcomposeAsyncImage
import com.popote.data.Recipe
import com.popote.ui.screens.sourceLabel

/**
 * Carte d'une recette : grande photo arrondie avec sa source et le favori,
 * puis le titre et la durée.
 */
@Composable
fun RecipeCard(recipe: Recipe, onClick: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).clickable(onClick = onClick).padding(bottom = 6.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(
            Modifier.fillMaxWidth().aspectRatio(1.1f).clip(RoundedCornerShape(22.dp)),
            contentAlignment = Alignment.Center,
        ) {
            val image = imageUrl(recipe.thumbnail_url, LocalServerUrl.current)
            if (image != null) {
                // Image absente ou lien expiré (Instagram, TikTok…) : visuel de
                // remplacement plutôt qu'un rectangle blanc.
                SubcomposeAsyncImage(
                    model = image,
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(),
                    error = { RecipePlaceholder(recipe.category) },
                    loading = { RecipePlaceholder(recipe.category) },
                )
            } else {
                RecipePlaceholder(recipe.category)
            }
            // Recette reçue d'un autre compte
            if (recipe.shared_by_name != null) {
                Pill("De ${recipe.shared_by_name}", cs.inverseSurface, cs.inverseOnSurface,
                    Modifier.align(Alignment.TopStart).padding(8.dp))
            }
            if (recipe.is_favorite) {
                Surface(shape = CircleShape, color = cs.surface, modifier = Modifier.align(Alignment.TopEnd).padding(8.dp).size(32.dp)) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(Icons.Default.Favorite, "Favori", Modifier.size(17.dp), tint = cs.primary)
                    }
                }
            }
            sourceLabel(recipe.source_type)?.let {
                Pill(it, cs.surface.copy(alpha = 0.92f), cs.onSurface, Modifier.align(Alignment.BottomStart).padding(8.dp))
            }
        }
        Column(Modifier.padding(horizontal = 4.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(
                recipe.title,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.ExtraBold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                val meta = listOfNotNull(
                    recipe.totalTime.takeIf { it > 0 }?.let { "$it min" },
                    recipe.category?.replaceFirstChar { it.uppercase() },
                ).joinToString(" · ")
                if (recipe.totalTime > 0) Icon(Icons.Outlined.Schedule, null, Modifier.size(14.dp), tint = cs.onSurfaceVariant)
                Text(meta, style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant, maxLines = 1,
                    overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                if ((recipe.rating ?: 0) > 0) {
                    Icon(Icons.Default.Star, null, Modifier.size(14.dp), tint = cs.primary)
                    Text("${recipe.rating}", style = MaterialTheme.typography.labelMedium, color = cs.primary,
                        fontWeight = FontWeight.Bold)
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
