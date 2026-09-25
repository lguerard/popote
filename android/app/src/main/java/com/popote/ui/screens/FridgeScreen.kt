package com.popote.ui.screens

import android.app.Application
import android.content.Context
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.popote.data.PantryMatch
import com.popote.data.RecipeRepository
import com.popote.ui.components.LocalServerUrl
import com.popote.ui.components.imageUrl
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class FridgeViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)
    // Le contenu du frigo est gardé entre deux ouvertures de l'appli.
    private val prefs = app.getSharedPreferences("frigo", Context.MODE_PRIVATE)

    private val _items = MutableStateFlow(
        prefs.getString("items", "").orEmpty().split("\n").filter { it.isNotBlank() }
    )
    val items: StateFlow<List<String>> = _items.asStateFlow()
    private val _results = MutableStateFlow<List<PantryMatch>?>(null)
    val results: StateFlow<List<PantryMatch>?> = _results.asStateFlow()
    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private fun save(list: List<String>) {
        _items.value = list
        prefs.edit().putString("items", list.joinToString("\n")).apply()
    }

    fun add(text: String) {
        val new = text.split(',', ';', '\n').map { it.trim() }.filter { it.isNotEmpty() }
            .filter { n -> _items.value.none { it.equals(n, ignoreCase = true) } }
        if (new.isNotEmpty()) save(_items.value + new)
    }

    fun remove(item: String) = save(_items.value - item)
    fun clear() { save(emptyList()); _results.value = null }

    fun search(assumeStaples: Boolean) {
        if (_items.value.isEmpty()) return
        viewModelScope.launch {
            _loading.value = true
            _error.value = null
            try { _results.value = repo.whatToCook(_items.value, assumeStaples) }
            catch (e: Exception) { _error.value = repo.describe(e) }
            finally { _loading.value = false }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun FridgeScreen(onRecipeClick: (String) -> Unit, vm: FridgeViewModel = viewModel()) {
    val pantry by vm.items.collectAsState()
    val results by vm.results.collectAsState()
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()
    var input by remember { mutableStateOf("") }
    var countStaples by remember { mutableStateOf(false) }
    val server = LocalServerUrl.current

    Scaffold(topBar = { TopAppBar(title = { Text("🧊 Qu'est-ce que je cuisine ?") }) }) { padding ->
        LazyColumn(
            Modifier.padding(padding).fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item {
                Text("Indiquez ce que vous avez sous la main : vos recettes sont classées selon ce qu'il manque.",
                    style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            item {
                OutlinedTextField(
                    value = input,
                    onValueChange = { input = it },
                    placeholder = { Text("tomates, œufs, feta…") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = { vm.add(input); input = "" }),
                    trailingIcon = {
                        IconButton(onClick = { vm.add(input); input = "" }, enabled = input.isNotBlank()) {
                            Icon(Icons.Default.Add, "Ajouter")
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            if (pantry.isNotEmpty()) {
                item {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        pantry.forEach { entry ->
                            InputChip(selected = false, onClick = { vm.remove(entry) }, label = { Text("$entry  ×") })
                        }
                        TextButton(onClick = vm::clear) { Text("Tout vider", color = MaterialTheme.colorScheme.error) }
                    }
                }
            }
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = countStaples, onCheckedChange = { countStaples = it })
                    Text("Je n'ai pas forcément sel, poivre et huile", style = MaterialTheme.typography.bodySmall)
                }
            }
            item {
                Button(
                    onClick = { vm.search(assumeStaples = !countStaples) },
                    enabled = pantry.isNotEmpty() && !loading,
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                ) {
                    if (loading) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                    else Text("Trouver des recettes")
                }
            }
            if (error != null) {
                item { Text(error!!, color = MaterialTheme.colorScheme.error) }
            }
            val list = results
            if (list != null && list.isEmpty()) {
                item {
                    Text("Aucune recette n'utilise ces ingrédients.", color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(vertical = 24.dp))
                }
            }
            if (list != null) {
                items(list, key = { it.recipe.id }) { match ->
                    val missing = match.missing.orEmpty()
                    Card(onClick = { onRecipeClick(match.recipe.id) }, modifier = Modifier.fillMaxWidth()) {
                        Row(Modifier.padding(10.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            val image = imageUrl(match.recipe.thumbnail_url, server)
                            if (image != null) {
                                AsyncImage(model = image, contentDescription = null, contentScale = ContentScale.Crop,
                                    modifier = Modifier.size(72.dp).clip(MaterialTheme.shapes.medium))
                            }
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(match.recipe.title, Modifier.weight(1f), fontWeight = FontWeight.SemiBold,
                                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    Surface(
                                        shape = MaterialTheme.shapes.small,
                                        color = if (missing.isEmpty()) MaterialTheme.colorScheme.tertiaryContainer
                                        else MaterialTheme.colorScheme.secondaryContainer,
                                    ) {
                                        Text(if (missing.isEmpty()) "Tout est là !" else "Il manque ${missing.size}",
                                            style = MaterialTheme.typography.labelSmall,
                                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp))
                                    }
                                }
                                LinearProgressIndicator(progress = { match.coverage.toFloat() }, modifier = Modifier.fillMaxWidth())
                                Text("✓ " + match.matched.orEmpty().joinToString(", "), style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.primary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                if (missing.isNotEmpty()) Text("✗ " + missing.joinToString(", "), style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            }
                        }
                    }
                }
            }
        }
    }
}
