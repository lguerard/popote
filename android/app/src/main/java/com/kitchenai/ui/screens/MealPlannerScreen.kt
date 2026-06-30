package com.kitchenai.ui.screens

import android.app.Application
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kitchenai.R
import com.kitchenai.data.MealPlan
import com.kitchenai.data.MealPlanCreate
import com.kitchenai.data.Recipe
import com.kitchenai.data.RecipeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale

class MealPlannerViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)
    private val _plans = MutableStateFlow<List<MealPlan>>(emptyList())
    val plans: StateFlow<List<MealPlan>> = _plans.asStateFlow()
    private val _recipes = MutableStateFlow<List<Recipe>>(emptyList())
    val recipes: StateFlow<List<Recipe>> = _recipes.asStateFlow()
    private val _weekOffset = MutableStateFlow(0)
    val weekOffset: StateFlow<Int> = _weekOffset.asStateFlow()

    init { loadAll() }

    fun prevWeek() { _weekOffset.value--; loadAll() }
    fun nextWeek() { _weekOffset.value++; loadAll() }
    fun thisWeek() { _weekOffset.value = 0; loadAll() }

    private fun weekDates(): List<LocalDate> {
        val monday = LocalDate.now().with(java.time.DayOfWeek.MONDAY).plusWeeks(_weekOffset.value.toLong())
        return (0..6).map { monday.plusDays(it.toLong()) }
    }

    fun getWeekDates() = weekDates()

    private fun loadAll() {
        viewModelScope.launch {
            try {
                val dates = weekDates()
                val fmt = DateTimeFormatter.ISO_LOCAL_DATE
                _plans.value = repo.getMealPlans(dates.first().format(fmt), dates.last().format(fmt))
            } catch (_: Exception) {}
        }
    }

    fun loadRecipes(search: String = "") {
        viewModelScope.launch {
            try { _recipes.value = repo.getRecipes(search = search.ifBlank { null }) }
            catch (_: Exception) {}
        }
    }

    fun addMeal(date: LocalDate, mealType: String, recipe: Recipe) {
        viewModelScope.launch {
            try {
                repo.createMealPlan(MealPlanCreate(
                    date = date.format(DateTimeFormatter.ISO_LOCAL_DATE),
                    meal_type = mealType,
                    recipe_id = recipe.id,
                    recipe_title = recipe.title,
                    recipe_thumbnail = recipe.thumbnail_url,
                ))
                loadAll()
            } catch (_: Exception) {}
        }
    }

    fun removeMeal(id: String) {
        viewModelScope.launch {
            try { repo.deleteMealPlan(id); loadAll() } catch (_: Exception) {}
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MealPlannerScreen(onBack: () -> Unit, vm: MealPlannerViewModel = viewModel()) {
    val plans by vm.plans.collectAsState()
    val recipes by vm.recipes.collectAsState()
    val days = vm.getWeekDates()
    var picker by remember { mutableStateOf<Pair<LocalDate, String>?>(null) }
    var pickerSearch by remember { mutableStateOf("") }

    LaunchedEffect(picker) { if (picker != null) vm.loadRecipes(pickerSearch) }
    LaunchedEffect(pickerSearch) { if (picker != null) vm.loadRecipes(pickerSearch) }

    // API meal type keys stay as-is; only labels are localized
    val meals = listOf(
        "petit-déjeuner" to stringResource(R.string.meal_morning),
        "déjeuner" to stringResource(R.string.meal_noon),
        "dîner" to stringResource(R.string.meal_evening),
        "snack" to stringResource(R.string.meal_snack),
    )

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.planning_title)) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back)) } },
                actions = {
                    TextButton(onClick = vm::prevWeek) { Text("←") }
                    TextButton(onClick = vm::thisWeek) { Text(stringResource(R.string.today_abbr)) }
                    TextButton(onClick = vm::nextWeek) { Text("→") }
                },
            )
        }
    ) { padding ->
        Row(Modifier.padding(padding).fillMaxSize().horizontalScroll(rememberScrollState())) {
            Column(Modifier.width(80.dp)) {
                Spacer(Modifier.height(56.dp))
                meals.forEach { (_, label) ->
                    Box(Modifier.height(100.dp).fillMaxWidth(), contentAlignment = Alignment.Center) {
                        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            days.forEach { day ->
                Column(Modifier.width(140.dp)) {
                    val isToday = day == LocalDate.now()
                    Box(Modifier.height(56.dp).fillMaxWidth(), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(day.dayOfWeek.getDisplayName(TextStyle.SHORT, Locale.getDefault()).replaceFirstChar { it.uppercase() },
                                style = MaterialTheme.typography.labelMedium,
                                color = if (isToday) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface)
                            Text("${day.dayOfMonth}/${day.monthValue}",
                                style = MaterialTheme.typography.labelSmall,
                                color = if (isToday) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    meals.forEach { (mealType, _) ->
                        val cell = plans.filter { it.date == day.format(DateTimeFormatter.ISO_LOCAL_DATE) && it.meal_type == mealType }
                        Box(Modifier.height(100.dp).fillMaxWidth().padding(2.dp)) {
                            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                cell.forEach { plan ->
                                    Card(
                                        onClick = { vm.removeMeal(plan.id) },
                                        modifier = Modifier.fillMaxWidth(),
                                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
                                    ) {
                                        Text(plan.recipe_title ?: stringResource(R.string.recipe_fallback),
                                            style = MaterialTheme.typography.labelSmall,
                                            maxLines = 2, overflow = TextOverflow.Ellipsis,
                                            modifier = Modifier.padding(4.dp))
                                    }
                                }
                                IconButton(onClick = { picker = Pair(day, mealType); pickerSearch = "" }, modifier = Modifier.size(24.dp)) {
                                    Icon(Icons.Default.Add, null, modifier = Modifier.size(14.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if (picker != null) {
        AlertDialog(
            onDismissRequest = { picker = null },
            title = { Text(stringResource(R.string.add_meal_title)) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = pickerSearch, onValueChange = { pickerSearch = it },
                        placeholder = { Text(stringResource(R.string.search_short)) }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    LazyColumn(Modifier.heightIn(max = 300.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        items(recipes, key = { it.id }) { r ->
                            TextButton(onClick = { picker?.let { (d, m) -> vm.addMeal(d, m, r) }; picker = null },
                                modifier = Modifier.fillMaxWidth()) {
                                Text(r.title, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            }
                        }
                    }
                }
            },
            confirmButton = {},
            dismissButton = { TextButton(onClick = { picker = null }) { Text(stringResource(R.string.close)) } },
        )
    }
}
