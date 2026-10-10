package com.popote.ui.screens

import android.app.Application
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.popote.data.Account
import com.popote.data.AutomaticShares
import com.popote.data.RecipeRepository
import com.popote.data.SendRecipesRequest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class SharingViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)

    private val _accounts = MutableStateFlow<List<Account>?>(null)
    val accounts: StateFlow<List<Account>?> = _accounts.asStateFlow()
    private val _automatic = MutableStateFlow<AutomaticShares?>(null)
    val automatic: StateFlow<AutomaticShares?> = _automatic.asStateFlow()
    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message.asStateFlow()
    private val _sending = MutableStateFlow(false)
    val sending: StateFlow<Boolean> = _sending.asStateFlow()

    private fun act(block: suspend () -> Unit) {
        viewModelScope.launch {
            try { block() } catch (e: Exception) { _message.value = repo.describe(e) }
        }
    }

    fun load() = act {
        _accounts.value = repo.getShareableUsers()
        _automatic.value = repo.getAutomaticShares()
    }

    fun shareAll(account: Account, automatic: Boolean) = act {
        _sending.value = true
        try {
            val r = repo.sendRecipes(SendRecipesRequest(user_id = account.id, all = true, automatic = automatic))
            _message.value = buildString {
                append("✓ ${r.copied} recette${if (r.copied > 1) "s" else ""} envoyée${if (r.copied > 1) "s" else ""} à ${account.display_name}")
                if (r.skipped > 0) append(" (${r.skipped} déjà présente${if (r.skipped > 1) "s" else ""})")
                append(".")
                if (r.automatic) append(" Les prochaines suivront automatiquement.")
            }
            _automatic.value = repo.getAutomaticShares()
        } finally {
            _sending.value = false
        }
    }

    fun stopSending(account: Account) = act {
        repo.stopSending(account.id)
        _automatic.value = repo.getAutomaticShares()
    }

    fun stopReceiving(account: Account) = act {
        repo.stopReceiving(account.id)
        _automatic.value = repo.getAutomaticShares()
    }
}

/** Partager toute sa bibliothèque avec un autre compte, et gérer le partage automatique. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SharingSection(vm: SharingViewModel = viewModel()) {
    val accounts by vm.accounts.collectAsState()
    val automatic by vm.automatic.collectAsState()
    val message by vm.message.collectAsState()
    val sending by vm.sending.collectAsState()
    var selected by remember { mutableStateOf<Account?>(null) }
    var keepSending by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) { vm.load() }

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Partage avec d'autres comptes", style = MaterialTheme.typography.titleLarge)
        Text(
            "Les recettes partagées sont copiées dans le compte de la personne, avec un badge « Partagée par … ». " +
                "Pour une seule recette : menu ⋮ de la recette → Envoyer à un autre compte.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        val list = accounts
        when {
            list == null -> CircularProgressIndicator(Modifier.size(24.dp))
            list.isEmpty() -> Text("Aucun autre compte sur ce serveur.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            else -> {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    list.forEach { a ->
                        FilterChip(selected = selected?.id == a.id, onClick = { selected = a }, label = { Text("👤 ${a.display_name}") })
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = keepSending, onCheckedChange = { keepSending = it })
                    Text("Envoyer aussi automatiquement mes prochaines recettes", style = MaterialTheme.typography.bodyMedium)
                }
                Button(
                    onClick = { selected?.let { vm.shareAll(it, keepSending) } },
                    enabled = selected != null && !sending,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(if (sending) "Envoi…" else "Partager toutes mes recettes") }
            }
        }
        if (message != null) Text(message!!, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodyMedium)

        val outgoing = automatic?.outgoing.orEmpty()
        val incoming = automatic?.incoming.orEmpty()
        if (outgoing.isNotEmpty()) {
            Text("Mes nouvelles recettes sont envoyées à :", style = MaterialTheme.typography.titleSmall)
            outgoing.forEach { a -> AccountRow(a, "Arrêter") { vm.stopSending(a) } }
        }
        if (incoming.isNotEmpty()) {
            Text("Je reçois automatiquement les recettes de :", style = MaterialTheme.typography.titleSmall)
            incoming.forEach { a -> AccountRow(a, "Ne plus recevoir") { vm.stopReceiving(a) } }
        }
    }
}

@Composable
private fun AccountRow(account: Account, action: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text("👤 ${account.display_name}", Modifier.weight(1f))
        TextButton(onClick = onClick, colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error)) {
            Text(action)
        }
    }
}
