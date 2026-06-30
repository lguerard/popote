package com.kitchenai.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kitchenai.R
import com.kitchenai.ui.viewmodels.AddRecipeViewModel
import com.kitchenai.ui.viewmodels.AddState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddRecipeScreen(
    sharedText: String? = null,
    onBack: () -> Unit,
    onSuccess: (String) -> Unit,
    vm: AddRecipeViewModel = viewModel(),
) {
    var input by remember { mutableStateOf(sharedText ?: "") }
    val state by vm.state.collectAsState()

    LaunchedEffect(state) {
        if (state is AddState.Success) {
            onSuccess((state as AddState.Success).recipeId)
            vm.reset()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.add_recipe_title)) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back)) } },
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
                        stringResource(R.string.add_recipe_paste_hint),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        stringResource(R.string.add_recipe_description),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )

                    OutlinedTextField(
                        value = input,
                        onValueChange = { input = it },
                        modifier = Modifier.fillMaxWidth().height(200.dp),
                        placeholder = { Text(stringResource(R.string.add_recipe_placeholder)) },
                        label = { Text(stringResource(R.string.add_recipe_input_label)) },
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

                    Button(
                        onClick = { vm.submit(input) },
                        modifier = Modifier.fillMaxWidth().height(52.dp),
                        enabled = input.isNotBlank(),
                    ) {
                        Text(stringResource(R.string.add_recipe_extract), style = MaterialTheme.typography.titleMedium)
                    }

                    ElevatedCard {
                        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(stringResource(R.string.add_recipe_sources_title), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            listOf(
                                stringResource(R.string.add_recipe_source_video),
                                stringResource(R.string.add_recipe_source_web),
                                stringResource(R.string.add_recipe_source_social),
                                stringResource(R.string.add_recipe_source_text),
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
                                if (s is AddState.Polling) s.statusLabel else stringResource(R.string.add_recipe_submitting),
                                style = MaterialTheme.typography.titleMedium,
                            )
                            Text(
                                stringResource(R.string.add_recipe_processing_hint),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                textAlign = TextAlign.Center,
                            )
                        }
                    }
                }

                is AddState.Success -> {}
            }
        }
    }
}
