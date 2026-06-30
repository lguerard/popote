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
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kitchenai.R
import com.kitchenai.data.Recipe
import com.kitchenai.data.RecipeRepository
import com.kitchenai.data.ShoppingItem
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class ShoppingListViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)
    private val _recipes = MutableStateFlow<List<Recipe>>(emptyList())
    val recipes: StateFlow<List<Recipe>> = _recipes.asStateFlow()
    private val _items = MutableStateFlow<List<ShoppingItem>?>(null)
    val items: StateFlow<List<ShoppingItem>?> = _items.asStateFlow()
    private val _selectedIds = MutableStateFlow<Set<String>>(emptySet())
    val selectedIds: StateFlow<Set<String>> = _selectedIds.asStateFlow()
    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    init { loadRecipes() }

    private fun loadRecipes() {
        viewModelScope.launch {
            try { _recipes.value = repo.getRecipes() } catch (_: Exception) {}
        }
    }

    fun toggle(id: String) {
        _selectedIds.value = if (_selectedIds.value.contains(id))
            _selectedIds.value - id else _selectedIds.value + id
    }

    fun generate() {
        viewModelScope.launch {
            _loading.value = true
            try { _items.value = repo.getShoppingList(_selectedIds.value.toList()) }
            catch (_: Exception) {}
            finally { _loading.value = false }
        }
    }

    fun reset() { _items.value = null }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ShoppingListScreen(onBack: () -> Unit, vm: ShoppingListViewModel = viewModel()) {
    val recipes by vm.recipes.collectAsState()
    val shoppingItems by vm.items.collectAsState()
    val selected by vm.selectedIds.collectAsState()
    val loading by vm.loading.collectAsState()
    val checkedItems = remember { mutableStateMapOf<String, Boolean>() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.shopping_title)) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back)) } },
                actions = {
                    if (shoppingItems != null) {
                        TextButton(onClick = vm::reset) { Text(stringResource(R.string.shopping_edit)) }
                    }
                },
            )
        }
    ) { padding ->
        if (shoppingItems != null) {
            val unchecked = shoppingItems!!.filter { checkedItems[it.name] != true }
            val done = shoppingItems!!.filter { checkedItems[it.name] == true }
            LazyColumn(Modifier.padding(padding).fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                items(unchecked, key = { it.name }) { item ->
                    ShoppingItemRow(item, false) { checkedItems[item.name] = true }
                }
                if (done.isNotEmpty()) {
                    item {
                        Text(stringResource(R.string.shopping_in_cart), style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 8.dp))
                    }
                    items(done, key = { "done_${it.name}" }) { item ->
                        ShoppingItemRow(item, true) { checkedItems[item.name] = false }
                    }
                }
            }
        } else {
            Column(Modifier.padding(padding).fillMaxSize()) {
                Text(stringResource(R.string.shopping_select), style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(16.dp))
                LazyColumn(
                    Modifier.weight(1f),
                    contentPadding = PaddingValues(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(recipes, key = { it.id }) { r ->
                        val sel = selected.contains(r.id)
                        Card(
                            onClick = { vm.toggle(r.id) },
                            colors = CardDefaults.cardColors(
                                containerColor = if (sel) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface
                            ),
                        ) {
                            Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                Checkbox(checked = sel, onCheckedChange = { vm.toggle(r.id) })
                                Column(Modifier.weight(1f)) {
                                    Text(r.title, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
                                    if (r.category != null) Text(r.category, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        }
                    }
                }
                Button(
                    onClick = vm::generate,
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    enabled = selected.isNotEmpty() && !loading,
                ) {
                    if (loading) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                    else Text(pluralStringResource(R.plurals.shopping_generate, selected.size, selected.size))
                }
            }
        }
    }
}

@Composable
private fun ShoppingItemRow(item: ShoppingItem, checked: Boolean, onToggle: () -> Unit) {
    Card(onClick = onToggle, colors = CardDefaults.cardColors(containerColor = if (checked) MaterialTheme.colorScheme.surfaceVariant else MaterialTheme.colorScheme.surface)) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Checkbox(checked = checked, onCheckedChange = { onToggle() })
            Column(Modifier.weight(1f)) {
                Text(item.name, fontWeight = FontWeight.Medium,
                    textDecoration = if (checked) TextDecoration.LineThrough else null)
                if (!item.quantity.isNullOrBlank() || !item.unit.isNullOrBlank())
                    Text(listOfNotNull(item.quantity, item.unit).joinToString(" "),
                        style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}
