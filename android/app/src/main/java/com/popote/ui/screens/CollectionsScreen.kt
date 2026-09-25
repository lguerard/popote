package com.popote.ui.screens

import android.app.Application
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.popote.data.RecipeCollection
import com.popote.data.RecipeCollectionDetail
import com.popote.data.RecipeRepository
import com.popote.ui.components.LocalServerUrl
import com.popote.ui.components.RecipeCard
import com.popote.ui.components.imageUrl
import com.popote.ui.components.shareText
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

private val COLLECTION_EMOJIS = listOf("📒", "☀️", "🎄", "🥗", "⚡", "🍰", "🌶️", "🥘", "🎉", "👶", "💪", "🌱")

class CollectionsViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)

    private val _collections = MutableStateFlow<List<RecipeCollection>?>(null)
    val collections: StateFlow<List<RecipeCollection>?> = _collections.asStateFlow()
    private val _detail = MutableStateFlow<RecipeCollectionDetail?>(null)
    val detail: StateFlow<RecipeCollectionDetail?> = _detail.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private fun act(block: suspend () -> Unit) {
        viewModelScope.launch {
            try { block(); _error.value = null } catch (e: Exception) { _error.value = repo.describe(e) }
        }
    }

    fun loadAll() = act { _collections.value = repo.getCollections() }

    fun create(name: String, emoji: String) = act {
        repo.createCollection(name, emoji)
        _collections.value = repo.getCollections()
    }

    fun open(id: String) = act {
        _detail.value = null
        _detail.value = repo.getCollection(id)
    }

    fun delete(id: String, onDone: () -> Unit) = act {
        repo.deleteCollection(id)
        _collections.value = repo.getCollections()
        onDone()
    }

    fun removeRecipe(collectionId: String, recipeId: String) = act {
        repo.removeFromCollection(collectionId, recipeId)
        _detail.value = repo.getCollection(collectionId)
    }

    fun share(id: String, onLink: (String) -> Unit) = act {
        val c = repo.shareCollection(id)
        _detail.value = _detail.value?.copy(share_token = c.share_token)
        c.share_token?.let { onLink(repo.publicLink("/partage/c/$it")) }
    }

    fun unshare(id: String) = act {
        val c = repo.unshareCollection(id)
        _detail.value = _detail.value?.copy(share_token = c.share_token)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CollectionsScreen(onOpen: (String) -> Unit, vm: CollectionsViewModel = viewModel()) {
    val collections by vm.collections.collectAsState()
    val error by vm.error.collectAsState()
    var creating by remember { mutableStateOf(false) }
    val server = LocalServerUrl.current

    LaunchedEffect(Unit) { vm.loadAll() }

    if (creating) {
        var name by remember { mutableStateOf("") }
        var emoji by remember { mutableStateOf(COLLECTION_EMOJIS.first()) }
        AlertDialog(
            onDismissRequest = { creating = false },
            title = { Text("Nouveau carnet") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = name, onValueChange = { name = it }, singleLine = true,
                        placeholder = { Text("Apéros d'été, Batch cooking…") }, modifier = Modifier.fillMaxWidth())
                    LazyVerticalGrid(columns = GridCells.Fixed(6), modifier = Modifier.heightIn(max = 120.dp)) {
                        items(COLLECTION_EMOJIS) { e ->
                            FilterChip(selected = emoji == e, onClick = { emoji = e }, label = { Text(e) })
                        }
                    }
                }
            },
            confirmButton = {
                Button(onClick = { vm.create(name, emoji); creating = false }, enabled = name.isNotBlank()) { Text("Créer") }
            },
            dismissButton = { TextButton(onClick = { creating = false }) { Text("Annuler") } },
        )
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text("📚 Carnets") }) },
        floatingActionButton = {
            ExtendedFloatingActionButton(onClick = { creating = true }, icon = { Icon(Icons.Default.Add, null) }, text = { Text("Carnet") })
        },
    ) { padding ->
        val list = collections
        when {
            list == null && error != null -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(error!!, color = MaterialTheme.colorScheme.error)
                    Button(onClick = vm::loadAll) { Text("Réessayer") }
                }
            }
            list == null -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            list.isEmpty() -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("📚", style = MaterialTheme.typography.displayMedium)
                    Text("Aucun carnet pour l'instant", style = MaterialTheme.typography.titleMedium)
                    Text("Regroupez vos recettes par thème, puis partagez un carnet par lien.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            else -> LazyVerticalGrid(
                columns = GridCells.Adaptive(160.dp),
                modifier = Modifier.padding(padding),
                contentPadding = PaddingValues(16.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(list, key = { it.id }) { c ->
                    Card(onClick = { onOpen(c.id) }) {
                        Box(Modifier.fillMaxWidth().aspectRatio(16f / 10f), contentAlignment = Alignment.Center) {
                            val cover = imageUrl(c.covers.orEmpty().firstOrNull(), server)
                            if (cover != null) {
                                AsyncImage(model = cover, contentDescription = null, contentScale = ContentScale.Crop,
                                    modifier = Modifier.fillMaxSize())
                            } else {
                                Text(c.emoji ?: "📒", style = MaterialTheme.typography.displaySmall)
                            }
                        }
                        Column(Modifier.padding(10.dp)) {
                            Text("${c.emoji ?: "📒"} ${c.name}", fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text("${c.recipe_count} recette${if (c.recipe_count > 1) "s" else ""}${if (c.share_token != null) " · 🔗" else ""}",
                                style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CollectionDetailScreen(
    collectionId: String,
    onBack: () -> Unit,
    onRecipeClick: (String) -> Unit,
    vm: CollectionsViewModel = viewModel(),
) {
    val detail by vm.detail.collectAsState()
    val error by vm.error.collectAsState()
    val context = LocalContext.current
    var menuOpen by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }

    LaunchedEffect(collectionId) { vm.open(collectionId) }

    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text("Supprimer ce carnet ?") },
            text = { Text("Les recettes qu'il contient sont conservées.") },
            confirmButton = {
                TextButton(onClick = { confirmDelete = false; vm.delete(collectionId, onBack) }) {
                    Text("Supprimer", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("Annuler") } },
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(detail?.let { "${it.emoji ?: "📒"} ${it.name}" } ?: "Carnet", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Retour") } },
                actions = {
                    val d = detail
                    if (d != null) {
                        IconButton(onClick = {
                            vm.share(d.id) { link -> shareText(context, "Mon carnet « ${d.name} » : $link", "Partager le carnet") }
                        }) { Icon(Icons.Default.Share, "Partager") }
                        Box {
                            IconButton(onClick = { menuOpen = true }) { Icon(Icons.Default.MoreVert, "Plus") }
                            DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                                if (d.share_token != null) {
                                    DropdownMenuItem(text = { Text("Désactiver le lien de partage") },
                                        onClick = { menuOpen = false; vm.unshare(d.id) })
                                }
                                DropdownMenuItem(
                                    text = { Text("Supprimer le carnet", color = MaterialTheme.colorScheme.error) },
                                    leadingIcon = { Icon(Icons.Default.Delete, null, tint = MaterialTheme.colorScheme.error) },
                                    onClick = { menuOpen = false; confirmDelete = true },
                                )
                            }
                        }
                    }
                },
            )
        },
    ) { padding ->
        val d = detail
        when {
            d == null && error != null -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Text(error!!, color = MaterialTheme.colorScheme.error)
            }
            d == null -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            d.recipes.isNullOrEmpty() -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Text("Ce carnet est vide. Ajoutez-y des recettes depuis leur fiche (menu ⋮).",
                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(32.dp))
            }
            else -> LazyVerticalGrid(
                columns = GridCells.Adaptive(180.dp),
                modifier = Modifier.padding(padding),
                contentPadding = PaddingValues(16.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(d.recipes.orEmpty(), key = { it.id }) { r ->
                    Column {
                        RecipeCard(recipe = r, onClick = { onRecipeClick(r.id) })
                        TextButton(onClick = { vm.removeRecipe(d.id, r.id) }) {
                            Text("Retirer du carnet", style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
            }
        }
    }
}
