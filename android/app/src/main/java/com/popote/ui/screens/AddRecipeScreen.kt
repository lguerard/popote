package com.popote.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.popote.ui.viewmodels.AddRecipeViewModel
import com.popote.ui.viewmodels.AddState
import com.popote.ui.viewmodels.BatchRow
import com.popote.ui.viewmodels.linksIn
import androidx.compose.ui.text.style.TextOverflow

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddRecipeScreen(
    sharedText: String? = null,
    onSharedConsumed: () -> Unit = {},
    onBack: () -> Unit,
    onSuccess: (String) -> Unit,
    // Recette ouverte depuis un import groupé : l'écran d'ajout reste dans la
    // pile, le retour retrouve le suivi des autres liens.
    onOpenRecipe: (String) -> Unit = onSuccess,
    vm: AddRecipeViewModel = viewModel(),
) {
    var input by remember { mutableStateOf("") }
    val state by vm.state.collectAsState()
    val pickPhoto = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) vm.submitImage(uri)
    }

    // Partage reçu d'une autre appli : import lancé directement, sans
    // repasser par le bouton. Le serveur retrouve l'URL même au milieu
    // d'un texte (« Regarde ce reel ! https://… »).
    LaunchedEffect(sharedText) {
        val shared = sharedText ?: return@LaunchedEffect
        input = shared
        // Plusieurs liens partagés d'un coup : import groupé.
        if (linksIn(shared).size > 1) vm.submitBatch(shared) else vm.submit(shared)
        onSharedConsumed()
    }

    LaunchedEffect(state) {
        if (state is AddState.Success) {
            onSuccess((state as AddState.Success).recipeId)
            vm.reset()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Ajouter une recette") },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Retour") } },
            )
        }
    ) { padding ->
        Column(
            Modifier.padding(padding).padding(16.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            when (val s = state) {
                is AddState.Idle, is AddState.Error -> {
                    Text(
                        "Collez une URL ou du texte",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        "Fonctionne avec YouTube, TikTok, Instagram, Marmiton, 750g, et n'importe quel site de recettes ou texte libre.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )

                    OutlinedTextField(
                        value = input,
                        onValueChange = { input = it },
                        modifier = Modifier.fillMaxWidth().height(200.dp),
                        placeholder = { Text("https://www.youtube.com/watch?v=…\nou texte brut de recette…") },
                        label = { Text("URL ou texte") },
                        maxLines = 10,
                    )

                    if (s is AddState.Error) {
                        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                            Text(
                                s.message,
                                Modifier.padding(12.dp),
                                color = MaterialTheme.colorScheme.onErrorContainer,
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }

                    val links = remember(input) { linksIn(input) }
                    if (links.size > 1) {
                        // Plusieurs liens collés (reels enregistrés, favoris…) : tous d'un coup.
                        Button(
                            onClick = { vm.submitBatch(input) },
                            modifier = Modifier.fillMaxWidth().height(52.dp),
                        ) {
                            Text("📚  Importer les ${links.size} liens", style = MaterialTheme.typography.titleMedium)
                        }
                    } else {
                        Button(
                            onClick = { vm.submit(input) },
                            modifier = Modifier.fillMaxWidth().height(52.dp),
                            enabled = input.isNotBlank(),
                        ) {
                            Text("Extraire la recette", style = MaterialTheme.typography.titleMedium)
                        }
                    }
                    Text(
                        "Astuce : collez plusieurs liens (un par ligne) pour les importer tous d'un coup.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )

                    OutlinedButton(
                        onClick = { pickPhoto.launch("image/*") },
                        modifier = Modifier.fillMaxWidth().height(52.dp),
                    ) {
                        Text("📷  Depuis une photo (livre, fiche manuscrite…)")
                    }

                    // Sources hint
                    ElevatedCard {
                        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("Sources supportées", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            listOf(
                                "🎬 YouTube, TikTok, Instagram, Vimeo",
                                "🌐 Marmiton, 750g, AllRecipes…",
                                "📱 Facebook, Twitter/X, Twitch",
                                "📝 Texte libre (toute langue)",
                            ).forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
                        }
                    }
                }

                is AddState.Submitting, is AddState.Polling -> {
                    Box(Modifier.fillMaxWidth().padding(vertical = 48.dp), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(16.dp)) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(56.dp),
                                color = MaterialTheme.colorScheme.primary,
                                strokeWidth = 5.dp,
                            )
                            Text(
                                if (s is AddState.Polling) s.statusLabel else "Envoi en cours…",
                                style = MaterialTheme.typography.titleMedium,
                            )
                            Text(
                                "L'extraction peut prendre quelques minutes\npour les longues vidéos.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                textAlign = TextAlign.Center,
                            )
                        }
                    }
                }

                is AddState.Batch -> BatchProgress(
                    s,
                    onOpen = onOpenRecipe,
                    onDone = onBack,
                    onAgain = { input = ""; vm.reset() },
                )

                is AddState.Success -> {}
            }
        }
    }
}

/** Suivi d'un import de plusieurs liens, ligne par ligne. */
@Composable
private fun BatchProgress(batch: AddState.Batch, onOpen: (String) -> Unit, onDone: () -> Unit, onAgain: () -> Unit) {
    val total = batch.rows.size
    val added = batch.rows.count { it.status == "done" }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            if (batch.isFinished) "Terminé : $added recette${if (added > 1) "s" else ""} ajoutée${if (added > 1) "s" else ""} sur $total"
            else "Import en cours : ${batch.finished} / $total",
            style = MaterialTheme.typography.titleMedium,
        )
        if (total > 0) {
            LinearProgressIndicator(
                progress = { batch.finished.toFloat() / total },
                modifier = Modifier.fillMaxWidth(),
            )
        }
        if (!batch.isFinished) {
            Text(
                "Les liens sont extraits l'un après l'autre. Vous pouvez quitter cet écran : l'import continue sur le serveur.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        batch.rows.forEach { row -> BatchRowItem(row, onOpen) }
        if (batch.alreadySaved > 0) {
            Text(
                "${batch.alreadySaved} lien${if (batch.alreadySaved > 1) "s" else ""} déjà dans Popote, non réimporté${if (batch.alreadySaved > 1) "s" else ""}.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (batch.ignored > 0) {
            Text(
                "${batch.ignored} lien${if (batch.ignored > 1) "s" else ""} au-delà de 50 non envoyé${if (batch.ignored > 1) "s" else ""} : relancez-les ensuite.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
        }
        if (batch.isFinished) {
            Button(onClick = onDone, modifier = Modifier.fillMaxWidth()) { Text("Voir mes recettes") }
            OutlinedButton(onClick = onAgain, modifier = Modifier.fillMaxWidth()) { Text("Importer d'autres liens") }
        }
    }
}

@Composable
private fun BatchRowItem(row: BatchRow, onOpen: (String) -> Unit) {
    val (icon, label) = when (row.status) {
        "done" -> "✅" to (row.title ?: "Ajoutée")
        "failed" -> "⚠️" to "Échec"
        "processing" -> "🔄" to (row.message ?: "Extraction…")
        else -> "⏳" to "En attente"
    }
    Card(
        onClick = { if (row.status == "done") onOpen(row.recipeId) },
        enabled = row.status == "done",
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(icon)
            Column(Modifier.weight(1f)) {
                Text(label, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text(row.link, style = MaterialTheme.typography.labelSmall, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (row.status == "failed" && row.message != null) {
                    Text(row.message, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}
