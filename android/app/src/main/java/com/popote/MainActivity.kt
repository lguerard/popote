package com.kitchenai

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.navigation.NavType
import androidx.navigation.compose.*
import androidx.navigation.navArgument
import com.kitchenai.ui.screens.*
import com.kitchenai.ui.theme.PopoteTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val sharedText = if (intent?.action == Intent.ACTION_SEND && intent.type == "text/plain") {
            intent.getStringExtra(Intent.EXTRA_TEXT)
        } else null

        setContent {
            PopoteTheme {
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
                            SettingsScreen(onBack = { navController.popBackStack() })
                        }
                    }
                }
            }
        }
    }
}
