package com.popote.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.popote.ui.viewmodels.AuthViewModel

/**
 * Porte d'entrée de l'application. Tant qu'aucun compte n'existe sur le
 * serveur, propose la création du premier — qui devient administrateur.
 */
@Composable
fun LoginScreen(
    vm: AuthViewModel,
    needsSetup: Boolean,
    onSettingsClick: () -> Unit,
) {
    val error by vm.error.collectAsState()
    val busy by vm.busy.collectAsState()

    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var displayName by remember { mutableStateOf("") }

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("🍳", style = MaterialTheme.typography.displayMedium)
        Text(
            if (needsSetup) "Bienvenue dans Popote" else "Popote",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
        )
        Text(
            if (needsSetup) "Crée le premier compte — il sera administrateur."
            else "Connecte-toi pour accéder aux recettes.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 4.dp, bottom = 20.dp),
        )

        if (needsSetup) {
            OutlinedTextField(
                value = displayName,
                onValueChange = { displayName = it; vm.clearError() },
                label = { Text("Nom affiché") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(12.dp))
        }

        OutlinedTextField(
            value = email,
            onValueChange = { email = it; vm.clearError() },
            label = { Text("Adresse e-mail") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Email,
                imeAction = ImeAction.Next,
            ),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(12.dp))

        OutlinedTextField(
            value = password,
            onValueChange = { password = it; vm.clearError() },
            label = { Text(if (needsSetup) "Mot de passe (8 caractères minimum)" else "Mot de passe") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Password,
                imeAction = ImeAction.Done,
            ),
            modifier = Modifier.fillMaxWidth(),
        )

        if (error != null) {
            Spacer(Modifier.height(12.dp))
            Text(
                error!!,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
            )
        }

        Spacer(Modifier.height(20.dp))
        Button(
            onClick = {
                if (needsSetup) vm.createFirstAccount(email, displayName, password)
                else vm.signIn(email, password)
            },
            enabled = !busy && email.isNotBlank() && password.isNotBlank() &&
                (!needsSetup || displayName.isNotBlank()),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                when {
                    busy && needsSetup -> "Création…"
                    busy -> "Connexion…"
                    needsSetup -> "Créer le compte"
                    else -> "Se connecter"
                }
            )
        }

        if (!needsSetup) {
            Spacer(Modifier.height(12.dp))
            Text(
                "Mot de passe oublié ? Demande un lien de réinitialisation à un administrateur, " +
                    "puis ouvre-le dans un navigateur.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
        }

        Spacer(Modifier.height(24.dp))
        TextButton(onClick = onSettingsClick) { Text("Changer de serveur") }
    }
}

/** Affiché quand le serveur ne répond pas : sans lui on ne sait même pas s'il
 *  faut demander une connexion. */
@Composable
fun ServerUnreachableScreen(
    message: String,
    onRetry: () -> Unit,
    onSettingsClick: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("🔌", style = MaterialTheme.typography.displaySmall)
        Text(
            message,
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 12.dp, bottom = 20.dp),
        )
        Button(onClick = onRetry) { Text("Réessayer") }
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = onSettingsClick) { Text("Paramètres du serveur") }
    }
}
