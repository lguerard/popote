package com.popote.ui.assistant

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withLink
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import coil.compose.SubcomposeAsyncImage
import com.popote.ui.components.LocalServerUrl
import com.popote.ui.components.imageUrl

private const val MAX_CHARS = 4000

/** Question de départ : envoyée telle quelle, ou mise dans le champ à compléter. */
private data class Starter(val label: String, val send: String? = null, val fill: String? = null)

private fun starters(recipe: RecipeContext?): List<Starter> {
    val general = listOf(
        Starter("Qu'est-ce que je peux cuisiner avec… ?", fill = "Qu'est-ce que je peux cuisiner avec "),
        Starter("Invente-moi une recette…", fill = "Invente-moi une recette de "),
        Starter("Planifie mes dîners de la semaine", send = "Planifie mes dîners de la semaine avec mes recettes."),
        Starter("Que reste-t-il sur ma liste de courses ?", send = "Que reste-t-il sur ma liste de courses ?"),
    )
    if (recipe == null) return general
    return listOf(
        Starter("Adapte cette recette pour 6", send = "Adapte cette recette pour 6 personnes."),
        Starter("Par quoi remplacer… ?", fill = "Dans cette recette, par quoi remplacer "),
        Starter("Des recettes similaires ?",
            send = "J'ai d'autres recettes proches de celle-ci ? Sinon, des idées dans le même esprit ?"),
        Starter("Ajoute ses ingrédients aux courses",
            send = "Ajoute les ingrédients de cette recette à ma liste de courses."),
    ) + general.take(2)
}

/**
 * Panneau de l'assistant culinaire, par-dessus l'écran en cours.
 * [onOpenRecipe] et [onOpenTab] ("planning", "shopping") referment le
 * panneau et naviguent.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AssistantSheet(
    vm: AssistantViewModel,
    onDismiss: () -> Unit,
    onOpenRecipe: (String) -> Unit,
    onOpenTab: (String) -> Unit,
) {
    val entries by vm.entries.collectAsState()
    val context by vm.context.collectAsState()
    val busy by vm.busy.collectAsState()
    var draft by rememberSaveable { mutableStateOf("") }
    val listState = rememberLazyListState()
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    // Suit la réponse au fil de l'eau.
    val last = entries.lastOrNull()
    LaunchedEffect(entries.size, last?.text?.length, last?.recipes?.size, last?.actions?.size) {
        if (entries.isNotEmpty()) listState.animateScrollToItem(entries.lastIndex)
    }

    fun send(text: String) {
        vm.send(text)
        draft = ""
    }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(Modifier.fillMaxWidth().fillMaxHeight(0.94f).imePadding()) {
            Row(Modifier.padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("🧑‍🍳 Assistant", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                if (entries.isNotEmpty()) {
                    TextButton(onClick = vm::reset) { Text("Nouvelle conversation") }
                }
                IconButton(onClick = onDismiss) { Icon(Icons.Default.Close, "Fermer") }
            }
            context?.let { recipe ->
                InputChip(
                    selected = true,
                    onClick = vm::clearContext,
                    label = { Text("📖 ${recipe.title}", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    trailingIcon = { Icon(Icons.Default.Close, "Ne plus parler de cette recette", Modifier.size(16.dp)) },
                    modifier = Modifier.padding(horizontal = 16.dp),
                )
            }

            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                if (entries.isEmpty()) {
                    item {
                        Text(
                            "Pose une question sur tes recettes, ton planning ou ta liste de courses. " +
                                "Je peux aussi proposer des remplacements d'ingrédients ou inventer une recette.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    items(starters(context)) { starter ->
                        SuggestionChip(
                            onClick = {
                                val question = starter.send
                                if (question != null) send(question) else { draft = starter.fill ?: "" }
                            },
                            label = { Text(starter.label) },
                        )
                    }
                }
                items(entries, key = { it.id }) { entry ->
                    if (entry.role == "user") {
                        UserBubble(entry.text)
                    } else {
                        AssistantReply(entry, onOpenRecipe, onOpenTab)
                    }
                }
            }

            Row(
                Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = draft,
                    onValueChange = { draft = it.take(MAX_CHARS) },
                    placeholder = { Text("Pose ta question…") },
                    maxLines = 4,
                    modifier = Modifier.weight(1f),
                )
                if (busy) {
                    FilledTonalIconButton(onClick = vm::stop) { Icon(Icons.Default.Stop, "Arrêter la réponse") }
                } else {
                    FilledIconButton(onClick = { send(draft) }, enabled = draft.isNotBlank()) {
                        Icon(Icons.AutoMirrored.Filled.Send, "Envoyer")
                    }
                }
            }
        }
    }
}

@Composable
private fun UserBubble(text: String) {
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterEnd) {
        Text(
            text,
            modifier = Modifier
                .widthIn(max = 300.dp)
                .background(MaterialTheme.colorScheme.primaryContainer, RoundedCornerShape(16.dp))
                .padding(horizontal = 12.dp, vertical = 8.dp),
            color = MaterialTheme.colorScheme.onPrimaryContainer,
        )
    }
}

@Composable
private fun AssistantReply(entry: ChatEntry, onOpenRecipe: (String) -> Unit, onOpenTab: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (entry.text.isNotBlank()) MarkdownText(entry.text, onOpenRecipe)
        if (entry.pending && entry.status != null) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp)
                Text(entry.status, style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        entry.actions.forEach { action ->
            val icon = when (action.kind) { "planning" -> "📅"; "recette" -> "📗"; else -> "🛒" }
            AssistChip(
                onClick = {
                    when (action.kind) {
                        "planning" -> onOpenTab("planning")
                        "recette" -> action.recipeId?.let { onOpenRecipe(it) }
                        else -> onOpenTab("shopping")
                    }
                },
                label = { Text("$icon ${action.label} · Voir") },
            )
        }
        if (entry.recipes.isNotEmpty()) {
            Text("Recettes trouvées", style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(entry.recipes, key = { it.id }) { recipe -> RecipeMiniCard(recipe) { onOpenRecipe(recipe.id) } }
            }
        }
        if (entry.stopped) {
            Text("Réponse arrêtée.", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        entry.error?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        }
    }
}

@Composable
private fun RecipeMiniCard(recipe: FoundRecipe, onClick: () -> Unit) {
    val image = imageUrl(recipe.thumbnailUrl, LocalServerUrl.current)
    Card(onClick = onClick, modifier = Modifier.width(140.dp)) {
        Box(Modifier.fillMaxWidth().height(80.dp).background(MaterialTheme.colorScheme.secondaryContainer),
            contentAlignment = Alignment.Center) {
            if (image != null) {
                SubcomposeAsyncImage(model = image, contentDescription = null, contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(), error = { Text("🍽️") })
            } else {
                Text("🍽️")
            }
        }
        Column(Modifier.padding(8.dp)) {
            Text(recipe.title, style = MaterialTheme.typography.labelLarge, maxLines = 2, overflow = TextOverflow.Ellipsis)
            recipe.minutes?.let {
                Text("⏱ $it min", style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

/** Réponse en Markdown simple ; liens vers une recette ouverts dans l'appli. */
@Composable
private fun MarkdownText(text: String, onOpenRecipe: (String) -> Unit) {
    val context = LocalContext.current
    val linkColor = MaterialTheme.colorScheme.primary
    val linkStyles = TextLinkStyles(SpanStyle(color = linkColor, textDecoration = TextDecoration.Underline))
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        parseMarkdown(text).forEach { line ->
            if (line.inlines.isEmpty() && line.prefix.isEmpty()) {
                Spacer(Modifier.height(4.dp))
                return@forEach
            }
            val annotated: AnnotatedString = buildAnnotatedString {
                append(line.prefix)
                line.inlines.forEach { inline ->
                    when (inline) {
                        is Inline.Plain -> append(inline.text)
                        is Inline.Bold -> withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(inline.text) }
                        is Inline.RecipeLink -> withLink(
                            LinkAnnotation.Clickable("recette", linkStyles) { onOpenRecipe(inline.recipeId) }
                        ) { append(inline.text) }
                        is Inline.WebLink -> withLink(
                            LinkAnnotation.Clickable("web", linkStyles) {
                                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(inline.url)))
                            }
                        ) { append(inline.text) }
                    }
                }
            }
            Text(
                annotated,
                style = if (line.heading) MaterialTheme.typography.titleSmall else MaterialTheme.typography.bodyMedium,
                fontWeight = if (line.heading) FontWeight.Bold else null,
            )
        }
    }
}
