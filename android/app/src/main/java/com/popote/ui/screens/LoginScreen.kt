package com.popote.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.popote.ui.viewmodels.LoginViewModel

/**
 * Connexion avec le même compte que le site. Le serveur exige un jeton sur
 * toutes les routes de données : sans cet écran, l'appli ne pouvait rien
 * afficher ni importer.
 */
@Composable
fun LoginScreen(
    pendingShare: Boolean = false,
    vm: LoginViewModel = viewModel(),
) {
    val savedUrl by vm.serverUrl.collectAsState(initial = "")
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()
    var server by remember(savedUrl) { mutableStateOf(savedUrl) }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var showServer by remember { mutableStateOf(false) }

    Scaffold { padding ->
        Column(
            Modifier.padding(padding).padding(24.dp).fillMaxSize().verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.height(32.dp))
            Text("🍳", style = MaterialTheme.typography.displayLarge)
            Text("Popote", style = MaterialTheme.typography.headlineLarge, color = MaterialTheme.colorScheme.primary)
            Text(
                if (pendingShare) "Connecte-toi pour importer la recette partagée."
                else "Connecte-toi avec ton compte Popote.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )

            OutlinedTextField(
                value = email,
                onValueChange = { email = it },
                label = { Text("Adresse e-mail") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
            )
            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                label = { Text("Mot de passe") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
            )

            if (showServer) {
                OutlinedTextField(
                    value = server,
                    onValueChange = { server = it },
                    label = { Text("Adresse du serveur") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                )
            } else {
                TextButton(onClick = { showServer = true }) {
                    Text("Serveur : $server", style = MaterialTheme.typography.bodySmall)
                }
            }

            if (error != null) {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                    Text(error!!, Modifier.padding(12.dp), color = MaterialTheme.colorScheme.onErrorContainer)
                }
            }

            Button(
                onClick = { vm.login(server, email, password) },
                enabled = !loading && email.isNotBlank() && password.isNotBlank() && server.isNotBlank(),
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) {
                if (loading) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                else Text("Se connecter")
            }
            Text(
                "Pas encore de compte ? Crée-le depuis le site, puis reviens ici.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
        }
    }
}
