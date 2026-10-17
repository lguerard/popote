package com.popote.ui.screens

import android.app.Application
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.popote.data.RecipeRepository
import com.popote.data.RestoreReport
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate

class BackupViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)

    private val _busy = MutableStateFlow<String?>(null)  // action en cours
    val busy: StateFlow<String?> = _busy.asStateFlow()
    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message.asStateFlow()

    private fun launchAction(label: String, block: suspend () -> String) {
        if (_busy.value != null) return
        viewModelScope.launch {
            _busy.value = label
            _message.value = try { block() } catch (e: Exception) { "✗ ${repo.describe(e)}" }
            _busy.value = null
        }
    }

    fun export(uri: Uri) = launchAction("Préparation de la sauvegarde…") {
        repo.downloadBackup(uri)
        "✓ Sauvegarde enregistrée."
    }

    fun restore(uri: Uri) = launchAction("Restauration…") { describe(repo.importBackup(uri)) }

    private fun describe(r: RestoreReport): String {
        fun plural(n: Int, word: String) = "$n $word${if (n > 1) "s" else ""}"
        return buildString {
            append("✓ ${plural(r.recipes_added, "recette")} ajoutée${if (r.recipes_added > 1) "s" else ""}")
            if (r.images > 0) append(" (${plural(r.images, "image")})")
            if (r.collections_added > 0) append(", ${plural(r.collections_added, "carnet")}")
            append(".")
            if (r.recipes_skipped > 0) append("\n${plural(r.recipes_skipped, "recette")} déjà présente${if (r.recipes_skipped > 1) "s" else ""}, non dupliquée${if (r.recipes_skipped > 1) "s" else ""}.")
            if (r.invalid > 0) append("\n${plural(r.invalid, "élément")} illisible${if (r.invalid > 1) "s" else ""} ignoré${if (r.invalid > 1) "s" else ""}.")
        }
    }
}

/** Sauvegarde complète (recettes, images, carnets, historique) et restauration. */
@Composable
fun BackupSection(vm: BackupViewModel = viewModel()) {
    val busy by vm.busy.collectAsState()
    val message by vm.message.collectAsState()
    val exportTo = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri ->
        if (uri != null) vm.export(uri)
    }
    val restoreFrom = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) vm.restore(uri)
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Sauvegarde", style = MaterialTheme.typography.titleLarge)
        Text(
            "Toutes vos recettes dans un fichier .zip : contenu, images, notes, favoris, avis, historique et carnets. " +
                "La restauration ajoute les recettes sans dupliquer celles que vous avez déjà.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Button(
            onClick = { exportTo.launch("popote-sauvegarde-${LocalDate.now()}.zip") },
            enabled = busy == null,
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Exporter mes recettes") }
        OutlinedButton(
            onClick = { restoreFrom.launch(arrayOf("application/zip", "application/x-zip-compressed", "application/octet-stream")) },
            enabled = busy == null,
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Restaurer une sauvegarde") }
        busy?.let { label ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                Text(label, style = MaterialTheme.typography.bodySmall)
            }
        }
        message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
    }
}
