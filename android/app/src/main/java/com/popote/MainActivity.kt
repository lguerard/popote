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
import androidx.navigation.NavType
import androidx.navigation.compose.*
import androidx.navigation.navArgument
import androidx.navigation.NavGraph.Companion.findStartDestination
import com.popote.data.RecipeRepository
import com.popote.ui.components.LocalServerUrl
import com.popote.ui.screens.*
import com.popote.ui.theme.PopoteTheme

class MainActivity : ComponentActivity() {
    // Texte reçu via « Partager → Popote » (lien Instagram, TikTok, page web…)
    // en attente d'import. État Compose : un partage reçu alors que l'appli
    // est déjà ouverte (onNewIntent) déclenche aussi l'import.
    private var sharedText by mutableStateOf<String?>(null)

    private fun readShare(intent: Intent?): String? {
        if (intent?.action != Intent.ACTION_SEND) return null
        if (intent.type?.startsWith("text/") != true) return null
        return (intent.getStringExtra(Intent.EXTRA_TEXT) ?: intent.getStringExtra(Intent.EXTRA_SUBJECT))
            ?.takeIf { it.isNotBlank() }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        readShare(intent)?.let { sharedText = it }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // Pas relu après une rotation : l'import aurait été relancé.
        if (savedInstanceState == null) sharedText = readShare(intent)
        val repo = RecipeRepository(applicationContext)

        setContent {
            PopoteTheme {
                val loggedIn by repo.isLoggedIn.collectAsState(initial = null)
                when (loggedIn) {
                    null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                    false -> LoginScreen(pendingShare = sharedText != null)
                    true -> PopoteApp()
                }
            }
        }
    }

    @Composable
    private fun PopoteApp() {
        val navController = rememberNavController()
        val currentBackStack by navController.currentBackStackEntryAsState()
        val currentRoute = currentBackStack?.destination?.route
        val repo = remember { RecipeRepository(applicationContext) }
        val serverUrl by repo.serverUrl.collectAsState(initial = "")

        LaunchedEffect(sharedText) {
            if (sharedText != null && currentRoute != "add") {
                navController.navigate("add") { launchSingleTop = true }
            }
        }

        // Onglets du bas : l'état de chaque onglet est conservé quand on en change.
        fun openTab(route: String) {
            navController.navigate(route) {
                popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                launchSingleTop = true
                restoreState = true
            }
        }

        val tabs = listOf(
            Triple("home", "Recettes", Icons.Default.MenuBook),
            Triple("fridge", "Frigo", Icons.Default.Kitchen),
            Triple("planning", "Planning", Icons.Default.CalendarMonth),
            Triple("shopping", "Courses", Icons.Default.ShoppingCart),
            Triple("collections", "Carnets", Icons.Default.CollectionsBookmark),
        )

        CompositionLocalProvider(LocalServerUrl provides serverUrl) {
        Scaffold(
            bottomBar = {
                if (currentRoute in tabs.map { it.first }) {
                    NavigationBar {
                        tabs.forEach { (route, label, icon) ->
                            NavigationBarItem(
                                selected = currentRoute == route,
                                onClick = { openTab(route) },
                                icon = { Icon(icon, null) },
                                label = { Text(label) },
                            )
                        }
                    }
                }
            }
        ) { innerPadding ->
            NavHost(navController, startDestination = "home",
                modifier = androidx.compose.ui.Modifier.padding(innerPadding)) {
                composable("home") {
                    HomeScreen(
                        onRecipeClick = { id -> navController.navigate("recipe/$id") },
                        onAddClick = { navController.navigate("add") },
                        onSettingsClick = { navController.navigate("settings") },
                        onAchievementsClick = { navController.navigate("achievements") },
                    )
                }
                composable("fridge") {
                    FridgeScreen(onRecipeClick = { id -> navController.navigate("recipe/$id") })
                }
                composable("planning") {
                    MealPlannerScreen(
                        onBack = { navController.popBackStack() },
                        onRecipeClick = { id -> navController.navigate("recipe/$id") },
                        onShoppingReady = { openTab("shopping") },
                    )
                }
                composable("shopping") {
                    ShoppingListScreen(onBack = { navController.popBackStack() })
                }
                composable("collections") {
                    CollectionsScreen(onOpen = { id -> navController.navigate("collection/$id") })
                }
                composable(
                    "collection/{id}",
                    arguments = listOf(navArgument("id") { type = NavType.StringType }),
                ) { backStack ->
                    CollectionDetailScreen(
                        collectionId = backStack.arguments!!.getString("id")!!,
                        onBack = { navController.popBackStack() },
                        onRecipeClick = { id -> navController.navigate("recipe/$id") },
                    )
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
                        onSharedConsumed = { sharedText = null },
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
                    SettingsScreen(onBack = { navController.popBackStack() })
                }
            }
        }
        }
    }
}
