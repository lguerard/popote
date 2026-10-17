package com.popote.ui.screens

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.popote.data.Ingredient
import com.popote.data.Recipe
import com.popote.data.Step

// ── Modification d'une recette ───────────────────────────────────────────────

// Lignes du formulaire : la clé reste stable quand on ajoute, supprime ou
// déplace une ligne, pour que le champ en cours de saisie garde le focus.
// Une ligne « section » est un intertitre (« Pâte ») : son nom est dans
// name/text et il s'applique aux lignes qui le suivent.
private data class IngredientDraft(
    val key: Long,
    val quantity: String = "",
    val unit: String = "",
    val name: String = "",
    val notes: String = "",
    val isSection: Boolean = false,
)

private data class StepDraft(val key: Long, val text: String = "", val isSection: Boolean = false)

/** Liste enregistrée → lignes, avec un intertitre à chaque changement de section
 *  (un intertitre vide ramène les lignes suivantes « sans section »). */
private fun <T, R> toRows(items: List<T>, section: (T) -> String?, header: (String) -> R, row: (T) -> R): List<R> {
    val rows = mutableListOf<R>()
    var current: String? = null
    for (item in items) {
        val next = section(item)?.takeIf { it.isNotBlank() }
        if (next != current) rows.add(header(next ?: ""))
        current = next
        rows.add(row(item))
    }
    return rows
}

private var nextKey = 0L
private fun newKey() = nextKey++

/** Saisie d'un entier : chiffres seulement, longueur bornée (limites du serveur). */
private fun digits(s: String, max: Int) = s.filter(Char::isDigit).take(max)

private fun String.orNull() = trim().ifEmpty { null }

/**
 * Formulaire de modification : titre, description, portions, temps, tags,
 * ingrédients et étapes. Rien n'est envoyé avant « Enregistrer » ; quitter
 * avec des changements demande confirmation.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecipeEditScreen(
    recipe: Recipe,
    saving: Boolean,
    error: String?,
    onDismissError: () -> Unit,
    onCancel: () -> Unit,
    onSave: (Map<String, Any?>) -> Unit,
) {
    var title by remember { mutableStateOf(recipe.title) }
    var description by remember { mutableStateOf(recipe.description ?: "") }
    var servings by remember { mutableStateOf(recipe.servings?.toString() ?: "") }
    var prep by remember { mutableStateOf(recipe.prep_time?.toString() ?: "") }
    var cook by remember { mutableStateOf(recipe.cook_time?.toString() ?: "") }
    var tags by remember { mutableStateOf(recipe.tags.joinToString(", ")) }
    val ingredients = remember {
        toRows(
            recipe.ingredients, { it.section },
            { IngredientDraft(newKey(), name = it, isSection = true) },
            { IngredientDraft(newKey(), it.quantity ?: "", it.unit ?: "", it.name, it.notes ?: "") },
        ).toMutableStateList()
    }
    val steps = remember {
        toRows(
            recipe.steps.sortedBy { it.order }, { it.section },
            { StepDraft(newKey(), it, isSection = true) },
            { StepDraft(newKey(), it.text) },
        ).toMutableStateList()
    }
    var changed by remember { mutableStateOf(false) }
    var confirmLeave by remember { mutableStateOf(false) }
    val titleOk = title.isNotBlank()

    fun edit(block: () -> Unit) { block(); changed = true }

    fun leave() { if (changed) confirmLeave = true else onCancel() }

    fun save() {
        if (!titleOk || saving) return
        onSave(
            mapOf(
                "title" to title.trim(),
                "description" to description.orNull(),
                "servings" to servings.toIntOrNull(),
                "prep_time" to prep.toIntOrNull(),
                "cook_time" to cook.toIntOrNull(),
                "tags" to tags.split(',').mapNotNull { it.orNull() },
                "ingredients" to sectioned(ingredients, { it.isSection }, { it.name }) { ing, section ->
                    ing.name.orNull()?.let { Ingredient(ing.quantity.orNull(), ing.unit.orNull(), it, ing.notes.orNull(), section) }
                },
                "steps" to sectioned(steps, { it.isSection }, { it.text }) { step, section -> step.text.orNull()?.let { it to section } }
                    .mapIndexed { i, (text, section) -> Step(i + 1, text, section) },
            )
        )
    }

    BackHandler { leave() }

    if (confirmLeave) {
        AlertDialog(
            onDismissRequest = { confirmLeave = false },
            title = { Text("Abandonner les modifications ?") },
            text = { Text("Les changements non enregistrés seront perdus.") },
            confirmButton = {
                TextButton(onClick = { confirmLeave = false; onCancel() }) { Text("Abandonner") }
            },
            dismissButton = {
                TextButton(onClick = { confirmLeave = false }) { Text("Continuer") }
            },
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Modifier la recette") },
                navigationIcon = {
                    IconButton(onClick = ::leave) { Icon(Icons.Default.Close, "Annuler") }
                },
                actions = {
                    if (saving) {
                        CircularProgressIndicator(modifier = Modifier.padding(end = 16.dp).size(24.dp), strokeWidth = 2.dp)
                    } else {
                        TextButton(onClick = ::save, enabled = titleOk) { Text("Enregistrer") }
                    }
                },
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding).imePadding(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (error != null) {
                item {
                    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                        Row(Modifier.padding(start = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                error,
                                Modifier.weight(1f),
                                color = MaterialTheme.colorScheme.onErrorContainer,
                                style = MaterialTheme.typography.bodySmall,
                            )
                            IconButton(onClick = onDismissError) { Icon(Icons.Default.Close, "Fermer") }
                        }
                    }
                }
            }

            item {
                OutlinedTextField(
                    value = title,
                    onValueChange = { edit { title = it.take(500) } },
                    label = { Text("Nom de la recette") },
                    isError = !titleOk,
                    supportingText = if (titleOk) null else { { Text("Le nom est obligatoire.") } },
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            item {
                OutlinedTextField(
                    value = description,
                    onValueChange = { edit { description = it } },
                    label = { Text("Description") },
                    minLines = 2,
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    NumberField("Portions", servings, { edit { servings = digits(it, 4) } }, Modifier.weight(1f))
                    NumberField("Prép. (min)", prep, { edit { prep = digits(it, 5) } }, Modifier.weight(1f))
                    NumberField("Cuisson (min)", cook, { edit { cook = digits(it, 5) } }, Modifier.weight(1f))
                }
            }
            item {
                OutlinedTextField(
                    value = tags,
                    onValueChange = { edit { tags = it } },
                    label = { Text("Tags") },
                    placeholder = { Text("facile, végétarien, rapide") },
                    supportingText = { Text("Séparés par des virgules") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }

            item { SectionTitle("Ingrédients") }
            itemsIndexed(ingredients, key = { _, d -> d.key }) { i, ing ->
                if (ing.isSection) {
                    SectionRow(
                        ing.name,
                        onChange = { name -> edit { ingredients[i] = ing.copy(name = name) } },
                        onRemove = { edit { ingredients.removeAt(i) } },
                    )
                } else {
                    IngredientRow(
                        ing,
                        onChange = { updated -> edit { ingredients[i] = updated } },
                        onRemove = { edit { ingredients.removeAt(i) } },
                    )
                }
            }
            item {
                AddButtons(
                    label = "Ajouter un ingrédient",
                    onAdd = { edit { ingredients.add(IngredientDraft(newKey())) } },
                    onAddSection = { edit { ingredients.add(IngredientDraft(newKey(), isSection = true)) } },
                )
            }

            item { SectionTitle("Étapes") }
            itemsIndexed(steps, key = { _, d -> d.key }) { i, step ->
                if (step.isSection) {
                    SectionRow(
                        step.text,
                        onChange = { text -> edit { steps[i] = step.copy(text = text) } },
                        onRemove = { edit { steps.removeAt(i) } },
                    )
                } else {
                    StepRow(
                        // Les intertitres ne comptent pas dans la numérotation.
                        number = steps.take(i + 1).count { !it.isSection },
                        step = step,
                        canMoveUp = i > 0,
                        canMoveDown = i < steps.lastIndex,
                        onChange = { text -> edit { steps[i] = step.copy(text = text) } },
                        onMove = { delta -> edit { steps.add(i + delta, steps.removeAt(i)) } },
                        onRemove = { edit { steps.removeAt(i) } },
                    )
                }
            }
            item {
                AddButtons(
                    label = "Ajouter une étape",
                    onAdd = { edit { steps.add(StepDraft(newKey())) } },
                    onAddSection = { edit { steps.add(StepDraft(newKey(), isSection = true)) } },
                )
            }

            item {
                Button(
                    onClick = ::save,
                    enabled = titleOk && !saving,
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                ) { Text(if (saving) "Enregistrement…" else "Enregistrer les modifications") }
            }
        }
    }
}

/** Lignes → éléments enregistrés, chacun avec la section du dernier intertitre au-dessus. */
private fun <T, R : Any> sectioned(
    rows: List<T>,
    isSection: (T) -> Boolean,
    title: (T) -> String,
    build: (T, String?) -> R?,
): List<R> {
    var section: String? = null
    return rows.mapNotNull { row ->
        if (isSection(row)) {
            section = title(row).orNull()
            null
        } else {
            build(row, section)
        }
    }
}

@Composable
private fun AddButtons(label: String, onAdd: () -> Unit, onAddSection: () -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        TextButton(onClick = onAdd) {
            Icon(Icons.Default.Add, null)
            Spacer(Modifier.width(4.dp))
            Text(label)
        }
        TextButton(onClick = onAddSection) {
            Icon(Icons.Default.Title, null)
            Spacer(Modifier.width(4.dp))
            Text("Section")
        }
    }
}

/** Intertitre de section (« Pâte », « Garniture ») ; vide = fin de la section précédente. */
@Composable
private fun SectionRow(title: String, onChange: (String) -> Unit, onRemove: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        OutlinedTextField(
            value = title,
            onValueChange = { onChange(it.take(100)) },
            label = { Text("Section") },
            placeholder = { Text("Pâte, garniture, sauce…") },
            singleLine = true,
            textStyle = MaterialTheme.typography.titleSmall.copy(
                fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary,
            ),
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
            modifier = Modifier.weight(1f),
        )
        IconButton(onClick = onRemove) {
            Icon(Icons.Default.Delete, "Supprimer la section", tint = MaterialTheme.colorScheme.error)
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.padding(top = 8.dp),
    )
}

@Composable
private fun NumberField(label: String, value: String, onChange: (String) -> Unit, modifier: Modifier) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label, maxLines = 1) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        modifier = modifier,
    )
}

@Composable
private fun IngredientRow(ing: IngredientDraft, onChange: (IngredientDraft) -> Unit, onRemove: () -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f))) {
        Column(Modifier.padding(start = 8.dp, top = 4.dp, bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedTextField(
                    value = ing.quantity,
                    onValueChange = { onChange(ing.copy(quantity = it)) },
                    label = { Text("Qté") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.weight(0.8f),
                )
                OutlinedTextField(
                    value = ing.unit,
                    onValueChange = { onChange(ing.copy(unit = it)) },
                    label = { Text("Unité") },
                    singleLine = true,
                    modifier = Modifier.weight(0.9f),
                )
                IconButton(onClick = onRemove) {
                    Icon(Icons.Default.Delete, "Supprimer l'ingrédient", tint = MaterialTheme.colorScheme.error)
                }
            }
            OutlinedTextField(
                value = ing.name,
                onValueChange = { onChange(ing.copy(name = it)) },
                label = { Text("Ingrédient") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(end = 8.dp),
            )
            OutlinedTextField(
                value = ing.notes,
                onValueChange = { onChange(ing.copy(notes = it)) },
                label = { Text("Précision (facultatif)") },
                placeholder = { Text("haché, à température ambiante…") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(end = 8.dp),
            )
        }
    }
}

@Composable
private fun StepRow(
    number: Int,
    step: StepDraft,
    canMoveUp: Boolean,
    canMoveDown: Boolean,
    onChange: (String) -> Unit,
    onMove: (Int) -> Unit,
    onRemove: () -> Unit,
) {
    Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Surface(
            shape = CircleShape,
            color = MaterialTheme.colorScheme.primaryContainer,
            modifier = Modifier.padding(top = 14.dp).size(28.dp),
        ) {
            Box(contentAlignment = Alignment.Center) {
                Text("$number", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onPrimaryContainer)
            }
        }
        OutlinedTextField(
            value = step.text,
            onValueChange = onChange,
            minLines = 2,
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
            modifier = Modifier.weight(1f),
        )
        Column {
            IconButton(onClick = { onMove(-1) }, enabled = canMoveUp, modifier = Modifier.size(36.dp)) {
                Icon(Icons.Default.KeyboardArrowUp, "Monter l'étape")
            }
            IconButton(onClick = { onMove(1) }, enabled = canMoveDown, modifier = Modifier.size(36.dp)) {
                Icon(Icons.Default.KeyboardArrowDown, "Descendre l'étape")
            }
            IconButton(onClick = onRemove, modifier = Modifier.size(36.dp)) {
                Icon(Icons.Default.Delete, "Supprimer l'étape", tint = MaterialTheme.colorScheme.error)
            }
        }
    }
}
