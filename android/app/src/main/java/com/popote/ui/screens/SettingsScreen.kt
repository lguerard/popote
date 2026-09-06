package com.popote.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.popote.ui.viewmodels.SettingsViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    accountName: String? = null,
    onSignOut: (() -> Unit)? = null,
    vm: SettingsViewModel = viewModel(),
) {
    val currentUrl by vm.serverUrl.collectAsState(initial = "")
    val testResult by vm.testResult.collectAsState()
    var urlInput by remember(currentUrl) { mutableStateOf(currentUrl) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Paramètres") },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Retour") } },
            )
        }
    ) { padding ->
        Column(
            Modifier
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("Serveur Popote", style = MaterialTheme.typography.titleLarge)
            Text(
                "Entrez l'adresse IP ou le nom de domaine de votre serveur.\nPar exemple : http://192.168.1.100",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            OutlinedTextField(
                value = urlInput,
                onValueChange = { urlInput = it; vm.clearTestResult() },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("URL du serveur") },
                placeholder = { Text("http://192.168.1.100") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Uri,
                    imeAction = ImeAction.Done,
                ),
            )

            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(
                    onClick = { vm.testConnection(urlInput) },
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Tester")
                }
                Button(
                    onClick = { vm.saveUrl(urlInput); onBack() },
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Enregistrer")
                }
            }

            if (testResult != null) {
                val isOk = testResult!!.startsWith("✓")
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = if (isOk) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.errorContainer,
                    )
                ) {
                    Text(
                        testResult!!,
                        Modifier.padding(12.dp),
                        color = if (isOk) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onErrorContainer,
                    )
                }
            }

            // Le bloc compte n'a de sens qu'une fois connecté ; l'écran est
            // aussi joignable depuis la page de connexion pour corriger l'URL.
            if (accountName != null) {
                HorizontalDivider()
                MonCompte(vm, accountName, onSignOut)
            }
        }
    }
}

@Composable
private fun MonCompte(
    vm: SettingsViewModel,
    accountName: String,
    onSignOut: (() -> Unit)?,
) {
    val result by vm.passwordResult.collectAsState()
    val ok by vm.passwordOk.collectAsState()
    val busy by vm.passwordBusy.collectAsState()

    var current by remember { mutableStateOf("") }
    var nouveau by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf("") }

    // Une fois le changement réussi, on vide les champs.
    LaunchedEffect(ok) {
        if (ok) {
            current = ""; nouveau = ""; confirmation = ""
        }
    }

    Text("Mon compte", style = MaterialTheme.typography.titleLarge)
    Text(
        accountName,
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )

    Text("Changer le mot de passe", style = MaterialTheme.typography.titleMedium)

    OutlinedTextField(
        value = current,
        onValueChange = { current = it; vm.clearPasswordResult() },
        label = { Text("Mot de passe actuel") },
        singleLine = true,
        visualTransformation = PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Next),
        modifier = Modifier.fillMaxWidth(),
    )
    OutlinedTextField(
        value = nouveau,
        onValueChange = { nouveau = it; vm.clearPasswordResult() },
        label = { Text("Nouveau mot de passe (8 caractères minimum)") },
        singleLine = true,
        visualTransformation = PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Next),
        modifier = Modifier.fillMaxWidth(),
    )
    OutlinedTextField(
        value = confirmation,
        onValueChange = { confirmation = it; vm.clearPasswordResult() },
        label = { Text("Confirme le nouveau mot de passe") },
        singleLine = true,
        visualTransformation = PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
        modifier = Modifier.fillMaxWidth(),
    )

    if (result != null) {
        Card(
            colors = CardDefaults.cardColors(
                containerColor = if (ok) MaterialTheme.colorScheme.primaryContainer
                else MaterialTheme.colorScheme.errorContainer,
            )
        ) {
            Text(
                result!!,
                Modifier.padding(12.dp),
                color = if (ok) MaterialTheme.colorScheme.onPrimaryContainer
                else MaterialTheme.colorScheme.onErrorContainer,
            )
        }
    }

    Button(
        onClick = { vm.changePassword(current, nouveau, confirmation) },
        enabled = !busy && current.isNotBlank() && nouveau.isNotBlank() && confirmation.isNotBlank(),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(if (busy) "Enregistrement…" else "Changer le mot de passe")
    }

    Text(
        "Mot de passe oublié ? Un administrateur génère un lien de réinitialisation " +
            "depuis l'interface web et te le transmet.",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )

    if (onSignOut != null) {
        OutlinedButton(onClick = onSignOut, modifier = Modifier.fillMaxWidth()) {
            Text("Se déconnecter")
        }
    }
}
