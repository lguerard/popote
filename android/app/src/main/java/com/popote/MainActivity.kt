package com.popote

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavType
import androidx.navigation.compose.*
import androidx.navigation.navArgument
import com.popote.ui.screens.*
import com.popote.ui.theme.PopoteTheme
import com.popote.ui.viewmodels.AuthState
import com.popote.ui.viewmodels.AuthViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val sharedText = if (intent?.action == Intent.ACTION_SEND && intent.type == "text/plain") {
            intent.getStringExtra(Intent.EXTRA_TEXT)
        } else null

        setContent {
            PopoteTheme {
                val authVm: AuthViewModel = viewModel()
                val authState by authVm.state.collectAsState()

                // L'API refuse tout sans session : rien n'est affiché tant que
                // le serveur n'a pas dit qui nous sommes.
                when (val state = authState) {
                    is AuthState.Checking -> ChargementCompte()

                    is AuthState.Unreachable -> ReglagesSeuls(state.message, authVm)

                    is AuthState.NeedsSetup ->
                        LoginOuReglages(authVm, needsSetup = true)

                    is AuthState.SignedOut ->
                        LoginOuReglages(authVm, needsSetup = false)

                    is AuthState.SignedIn -> ApplicationConnectee(
                        sharedText = sharedText,
                        compte = state.user.display_name,
                        onSignOut = { authVm.signOut() },
                    )
                }
            }
        }
    }
}

@Composable
private fun ChargementCompte() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}

/** Serveur injoignable : la seule action utile est de corriger son adresse. */
@Composable
private fun ReglagesSeuls(message: String, authVm: AuthViewModel) {
    var reglages by remember { mutableStateOf(false) }
    if (reglages) {
        SettingsScreen(onBack = { reglages = false; authVm.refresh() })
    } else {
        ServerUnreachableScreen(
            message = message,
            onRetry = { authVm.refresh() },
            onSettingsClick = { reglages = true },
        )
    }
}

/** Écran de connexion, avec accès aux réglages du serveur. */
@Composable
private fun LoginOuReglages(authVm: AuthViewModel, needsSetup: Boolean) {
    var reglages by remember { mutableStateOf(false) }
    if (reglages) {
        SettingsScreen(onBack = { reglages = false; authVm.refresh() })
    } else {
        LoginScreen(vm = authVm, needsSetup = needsSetup, onSettingsClick = { reglages = true })
    }
}

@Composable
private fun ApplicationConnectee(
    sharedText: String?,
    compte: String,
    onSignOut: () -> Unit,
) {
    val navController = rememberNavController()
    val currentBackStack by navController.currentBackStackEntryAsState()
    val currentRoute = currentBackStack?.destination?.route

    val topLevelRoutes = setOf("home", "shopping", "planning", "achievements")

    Scaffold(
        bottomBar = {
            if (currentRoute in topLevelRoutes) {
                NavigationBar {
                    NavigationBarItem(
                        selected = currentRoute == "home",
                        onClick = { navController.navigate("home") { launchSingleTop = true; restoreState = true } },
                        icon = { Icon(Icons.Default.MenuBook, null) },
                        label = { Text("Recettes") },
                    )
                    NavigationBarItem(
                        selected = currentRoute == "planning",
                        onClick = { navController.navigate("planning") { launchSingleTop = true; restoreState = true } },
                        icon = { Icon(Icons.Default.CalendarMonth, null) },
                        label = { Text("Planning") },
                    )
                    NavigationBarItem(
                        selected = currentRoute == "shopping",
                        onClick = { navController.navigate("shopping") { launchSingleTop = true; restoreState = true } },
                        icon = { Icon(Icons.Default.ShoppingCart, null) },
                        label = { Text("Courses") },
                    )
                    NavigationBarItem(
                        selected = currentRoute == "achievements",
                        onClick = { navController.navigate("achievements") { launchSingleTop = true; restoreState = true } },
                        icon = { Icon(Icons.Default.EmojiEvents, null) },
                        label = { Text("Succès") },
                    )
                }
            }
        }
    ) { innerPadding ->
        NavHost(navController, startDestination = if (sharedText != null) "add" else "home",
            modifier = androidx.compose.ui.Modifier.padding(innerPadding)) {
            composable("home") {
                HomeScreen(
                    onRecipeClick = { id -> navController.navigate("recipe/$id") },
                    onAddClick = { navController.navigate("add") },
                    onSettingsClick = { navController.navigate("settings") },
                )
            }
            composable("planning") {
                MealPlannerScreen(onBack = { navController.popBackStack() })
            }
            composable("shopping") {
                ShoppingListScreen(onBack = { navController.popBackStack() })
            }
            composable(
                "recipe/{id}",
                arguments = listOf(navArgument("id") { type = NavType.StringType }),
            ) { backStack ->
                RecipeDetailScreen(
                    recipeId = backStack.arguments!!.getString("id")!!,
                    onBack = { navController.popBackStack() },
                )
            }
            composable("add") {
                AddRecipeScreen(
                    sharedText = sharedText,
                    onBack = { navController.popBackStack() },
                    onSuccess = { id ->
                        navController.navigate("recipe/$id") { popUpTo("home") }
                    },
                )
            }
            composable("achievements") {
                AchievementsScreen(onBack = { navController.popBackStack() })
            }
            composable("settings") {
                SettingsScreen(
                    onBack = { navController.popBackStack() },
                    accountName = compte,
                    onSignOut = onSignOut,
                )
            }
        }
    }
}
