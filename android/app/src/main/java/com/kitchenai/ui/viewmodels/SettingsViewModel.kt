package com.kitchenai.ui.viewmodels

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.kitchenai.R
import com.kitchenai.data.RecipeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class SettingsViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = RecipeRepository(app)

    val serverUrl = repo.serverUrl

    private val _testResult = MutableStateFlow<String?>(null)
    val testResult: StateFlow<String?> = _testResult.asStateFlow()

    fun saveUrl(url: String) {
        viewModelScope.launch { repo.saveServerUrl(url) }
    }

    fun testConnection(url: String) {
        viewModelScope.launch {
            repo.saveServerUrl(url)
            val ok = repo.checkHealth()
            _testResult.value = if (ok)
                getApplication<Application>().getString(R.string.settings_connected)
            else
                getApplication<Application>().getString(R.string.settings_unreachable)
        }
    }

    fun clearTestResult() { _testResult.value = null }
}
