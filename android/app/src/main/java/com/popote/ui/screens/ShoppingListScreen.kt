package com.popote.ui.screens

import android.app.Application
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.DeleteSweep
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.popote.data.GenerateShoppingRequest
import com.popote.data.Recipe
import com.popote.data.RecipeRepository
import com.popote.data.ShoppingEntry
import com.popote.ui.components.shareText
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

private val AISLE_EMOJI = mapOf(
    "Fruits et légumes" to "🥕",
    "Boucherie et poissonnerie" to "🥩",
    "Crèmerie et œufs" to "🧀",
    "Boulangerie" to "🥖",
    "Épicerie salée" to "🥫",
    "Épicerie sucrée" to "🍫",
    "Épices et condiments" to "🧂",
    "Surgelés" to "❄️",
    "Boissons" to "🥤",
    "Autres" to "🛍️",
)

class ShoppingListViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)

    private val _items = MutableStateFlow<List<ShoppingEntry>?>(null)
    val items: StateFlow<List<ShoppingEntry>?> = _items.asStateFlow()
    private val _aisles = MutableStateFlow<List<String>>(emptyList())
    val aisles: StateFlow<List<String>> = _aisles.asStateFlow()
    private val _shareToken = MutableStateFlow<String?>(null)
    val shareToken: StateFlow<String?> = _shareToken.asStateFlow()
    private val _recipes = MutableStateFlow<List<Recipe>>(emptyList())
    val recipes: StateFlow<List<Recipe>> = _recipes.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()
    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    private fun apply(resp: com.popote.data.ShoppingListResponse) {
        _items.value = resp.items ?: emptyList()
        _aisles.value = resp.aisles ?: emptyList()
        _shareToken.value = resp.share_token
    }

    fun refresh() {
        viewModelScope.launch {
            try { apply(repo.getShoppingItems()); _error.value = null }
            catch (e: Exception) { if (_items.value == null) _error.value = repo.describe(e) }
        }
    }

    /** Resynchronise régulièrement : ce que coche le reste du foyer apparaît tout seul. */
    suspend fun keepInSync() {
        while (true) {
            refresh()
            delay(5000)
        }
    }

    fun loadRecipes() {
        viewModelScope.launch {
            try { _recipes.value = repo.getRecipes() } catch (e: Exception) { _error.value = repo.describe(e) }
        }
    }

    fun toggle(item: ShoppingEntry) {
        _items.value = _items.value?.map { if (it.id == item.id) it.copy(checked = !item.checked) else it }
        viewModelScope.launch {
            try { repo.setShoppingChecked(item.id, !item.checked) }
            catch (e: Exception) { _error.value = repo.describe(e); refresh() }
        }
    }

    fun delete(item: ShoppingEntry) {
        _items.value = _items.value?.filter { it.id != item.id }
        viewModelScope.launch {
            try { repo.deleteShoppingItem(item.id) } catch (e: Exception) { _error.value = repo.describe(e); refresh() }
        }
    }

    fun add(name: String) {
        if (name.isBlank()) return
        viewModelScope.launch {
            try { repo.addShoppingItem(name); refresh() } catch (e: Exception) { _error.value = repo.describe(e) }
        }
    }

    fun clear(onlyChecked: Boolean) {
        viewModelScope.launch {
            try { repo.clearShopping(onlyChecked); refresh() } catch (e: Exception) { _error.value = repo.describe(e) }
        }
    }

    fun generate(recipeIds: List<String>, replace: Boolean, onDone: () -> Unit) {
        viewModelScope.launch {
            _busy.value = true
            try {
                apply(repo.generateShopping(GenerateShoppingRequest(recipe_ids = recipeIds, replace = replace)))
                onDone()
            } catch (e: Exception) { _error.value = repo.describe(e) }
            finally { _busy.value = false }
        }
    }

    fun share(onLink: (String) -> Unit) {
        viewModelScope.launch {
            try {
                val resp = repo.shareShoppingList()
                apply(resp)
                resp.share_token?.let { onLink(repo.publicLink("/partage/courses/$it")) }
            } catch (e: Exception) { _error.value = repo.describe(e) }
        }
    }

    fun unshare() {
        viewModelScope.launch {
            try { apply(repo.unshareShoppingList()) } catch (e: Exception) { _error.value = repo.describe(e) }
        }
    }

    fun clearError() { _error.value = null }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ShoppingListScreen(onBack: () -> Unit, vm: ShoppingListViewModel = viewModel()) {
    val entries by vm.items.collectAsState()
    val aisles by vm.aisles.collectAsState()
    val shareToken by vm.shareToken.collectAsState()
    val error by vm.error.collectAsState()
    val context = LocalContext.current
    var picking by remember { mutableStateOf(false) }
    var menuOpen by remember { mutableStateOf(false) }
    var newItem by remember { mutableStateOf("") }

    LaunchedEffect(Unit) { vm.keepInSync() }

    if (picking) {
        RecipePicker(vm = vm, hasItems = !entries.isNullOrEmpty(), onClose = { picking = false })
        return
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Courses", fontWeight = FontWeight.Black) },
                actions = {
                    IconButton(onClick = { vm.share { link -> shareText(context, "Notre liste de courses : $link", "Partager la liste") } }) {
                        Icon(Icons.Default.Share, "Partager avec le foyer")
                    }
                    Box {
                        IconButton(onClick = { menuOpen = true }) { Icon(Icons.Default.MoreVert, "Plus") }
                        DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                            DropdownMenuItem(
                                text = { Text("Retirer les articles cochés") },
                                leadingIcon = { Icon(Icons.Default.DeleteSweep, null) },
                                onClick = { menuOpen = false; vm.clear(onlyChecked = true) },
                            )
                            DropdownMenuItem(
                                text = { Text("Vider la liste") },
                                onClick = { menuOpen = false; vm.clear(onlyChecked = false) },
                            )
                            if (shareToken != null) {
                                DropdownMenuItem(
                                    text = { Text("Désactiver le lien du foyer") },
                                    onClick = { menuOpen = false; vm.unshare() },
                                )
                            }
                        }
                    }
                },
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { vm.loadRecipes(); picking = true },
                icon = { Icon(Icons.Default.Add, null) },
                text = { Text("Recettes") },
            )
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            if (error != null) {
                Card(
                    Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
                ) {
                    Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(error!!, Modifier.weight(1f), color = MaterialTheme.colorScheme.onErrorContainer, style = MaterialTheme.typography.bodySmall)
                        TextButton(onClick = { vm.clearError(); vm.refresh() }) { Text("OK") }
                    }
                }
            }

            TextField(
                value = newItem,
                onValueChange = { newItem = it },
                placeholder = { Text("Ajouter : « 2 kg de pommes », lessive…") },
                shape = CircleShape,
                colors = TextFieldDefaults.colors(
                    focusedIndicatorColor = Color.Transparent,
                    unfocusedIndicatorColor = Color.Transparent,
                    unfocusedContainerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
                    focusedContainerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
                ),
                singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { vm.add(newItem); newItem = "" }),
                trailingIcon = {
                    IconButton(onClick = { vm.add(newItem); newItem = "" }, enabled = newItem.isNotBlank()) {
                        Icon(Icons.Default.Add, "Ajouter")
                    }
                },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            )

            val list = entries
            when {
                list == null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                list.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("🛒", style = MaterialTheme.typography.displayMedium)
                        Text("La liste est vide", style = MaterialTheme.typography.titleMedium)
                        Text("Ajoutez des recettes, ou générez les courses de la semaine depuis le planning.",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(horizontal = 32.dp))
                    }
                }
                else -> {
                    val remaining = list.count { !it.checked }
                    val order = aisles.ifEmpty { AISLE_EMOJI.keys.toList() }
                    val groups = list.groupBy { it.aisle ?: "Autres" }
                        .toList()
                        .sortedBy { (aisle, _) -> order.indexOf(aisle).let { if (it < 0) order.size else it } }
                    // Une couleur par recette : la pastille d'un article dit d'où il vient.
                    val recipeNames = list.flatMap { it.recipes.orEmpty() }.distinct()
                    val dot = recipeDotColors()
                    val recipeColor = recipeNames.withIndex().associate { (i, name) -> name to dot[i % dot.size] }
                    LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 96.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        item {
                            Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.padding(bottom = 4.dp)) {
                                Text("${list.size - remaining} sur ${list.size} dans le panier",
                                    style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                LinearProgressIndicator(
                                    progress = { if (list.isEmpty()) 0f else (list.size - remaining).toFloat() / list.size },
                                    modifier = Modifier.fillMaxWidth().height(10.dp).clip(CircleShape),
                                    trackColor = MaterialTheme.colorScheme.surfaceContainerHighest,
                                )
                                if (recipeNames.isNotEmpty()) Row(
                                    Modifier.horizontalScroll(rememberScrollState()),
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                ) {
                                    recipeNames.forEach { name ->
                                        Surface(shape = CircleShape, color = MaterialTheme.colorScheme.surfaceContainerHigh) {
                                            Row(Modifier.padding(start = 10.dp, end = 14.dp).height(36.dp),
                                                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                                Box(Modifier.size(12.dp).clip(CircleShape).background(recipeColor.getValue(name)))
                                                Text(name, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold, maxLines = 1)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        groups.forEachIndexed { index, (aisle, rows) ->
                            val left = rows.count { !it.checked }
                            item(key = "aisle-$aisle") {
                                val (bg, fg) = aisleColors(index)
                                Surface(shape = RoundedCornerShape(14.dp), color = bg, contentColor = fg,
                                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp)) {
                                    Row(Modifier.padding(horizontal = 14.dp).height(40.dp), verticalAlignment = Alignment.CenterVertically) {
                                        Text(aisle, Modifier.weight(1f), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.ExtraBold)
                                        Text(if (left > 0) "$left à prendre" else "tout est pris", style = MaterialTheme.typography.labelLarge)
                                    }
                                }
                            }
                            items(rows.sortedBy { it.checked }, key = { it.id }) { entry ->
                                ShoppingRow(entry, entry.recipes.orEmpty().mapNotNull { recipeColor[it] },
                                    onToggle = { vm.toggle(entry) }, onDelete = { vm.delete(entry) })
                            }
                        }
                    }
                }
            }
        }
    }
}

/** Couleurs des bandeaux de rayon, tirées du thème, en alternance. */
@Composable
private fun aisleColors(index: Int): Pair<Color, Color> {
    val cs = MaterialTheme.colorScheme
    return when (index % 4) {
        0 -> cs.tertiaryContainer to cs.onTertiaryContainer
        1 -> cs.secondaryContainer to cs.onSecondaryContainer
        2 -> cs.primaryContainer to cs.onPrimaryContainer
        else -> cs.surfaceContainerHighest to cs.onSurface
    }
}

/** Pastilles des recettes : nettement différentes, y compris en clarté. */
@Composable
private fun recipeDotColors(): List<Color> {
    val cs = MaterialTheme.colorScheme
    return listOf(cs.primary, Color(0xFF3E7CB1), cs.tertiary, Color(0xFF6F8F3E), Color(0xFFB0457A), cs.secondary)
}

@Composable
private fun ShoppingRow(item: ShoppingEntry, dots: List<Color>, onToggle: () -> Unit, onDelete: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    Surface(
        onClick = onToggle,
        shape = RoundedCornerShape(18.dp),
        color = cs.surfaceContainerLow,
        modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
    ) {
        Row(Modifier.padding(start = 12.dp, end = 4.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            // Case arrondie, pleine une fois cochée.
            Box(
                Modifier.size(28.dp).clip(RoundedCornerShape(9.dp))
                    .then(if (item.checked) Modifier.background(cs.primary) else Modifier.border(2.dp, cs.outline, RoundedCornerShape(9.dp))),
                contentAlignment = Alignment.Center,
            ) {
                if (item.checked) Icon(Icons.Default.Check, null, Modifier.size(18.dp), tint = cs.onPrimary)
            }
            Column(Modifier.weight(1f)) {
                Text(item.name, fontWeight = FontWeight.Bold,
                    color = if (item.checked) cs.onSurfaceVariant else cs.onSurface,
                    textDecoration = if (item.checked) TextDecoration.LineThrough else null)
                val from = item.recipes.orEmpty()
                if (from.isNotEmpty()) Text(from.take(2).joinToString(", "), style = MaterialTheme.typography.labelSmall,
                    color = cs.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            if (dots.isNotEmpty()) Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                dots.distinct().take(3).forEach { Box(Modifier.size(10.dp).clip(CircleShape).background(it)) }
            }
            val qty = listOfNotNull(item.quantity, item.unit).joinToString(" ")
            if (qty.isNotBlank()) Text(qty, color = cs.onSurfaceVariant, fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.bodyMedium)
            IconButton(onClick = onDelete) {
                Icon(Icons.Default.Close, "Retirer ${item.name}", tint = cs.onSurfaceVariant)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RecipePicker(vm: ShoppingListViewModel, hasItems: Boolean, onClose: () -> Unit) {
    val recipes by vm.recipes.collectAsState()
    val busy by vm.busy.collectAsState()
    val selected = remember { mutableStateListOf<String>() }
    var replace by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Choisir des recettes") },
                navigationIcon = { IconButton(onClick = onClose) { Icon(Icons.Default.Close, "Fermer") } },
            )
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                items(recipes, key = { it.id }) { r ->
                    val sel = r.id in selected
                    Card(
                        onClick = { if (sel) selected.remove(r.id) else selected.add(r.id) },
                        colors = CardDefaults.cardColors(
                            containerColor = if (sel) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface,
                        ),
                    ) {
                        Row(Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = sel, onCheckedChange = { if (sel) selected.remove(r.id) else selected.add(r.id) })
                            Text(r.title, Modifier.weight(1f), maxLines = 2, overflow = TextOverflow.Ellipsis)
                        }
                    }
                }
            }
            if (hasItems) {
                Row(Modifier.padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = replace, onCheckedChange = { replace = it })
                    Text("Remplacer la liste actuelle (sinon, ajouter)", style = MaterialTheme.typography.bodySmall)
                }
            }
            Button(
                onClick = { vm.generate(selected.toList(), replace = !hasItems || replace, onDone = onClose) },
                enabled = selected.isNotEmpty() && !busy,
                modifier = Modifier.fillMaxWidth().padding(16.dp),
            ) {
                if (busy) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                else Text("Ajouter les ingrédients (${selected.size})")
            }
        }
    }
}
