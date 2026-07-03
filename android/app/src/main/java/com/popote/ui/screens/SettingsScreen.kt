package com.kitchenai.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kitchenai.ui.viewmodels.SettingsViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onBack: () -> Unit,
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
        Column(Modifier.padding(padding).padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("Serveur KitchenAI", style = MaterialTheme.typography.titleLarge)
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
        }
    }
}
