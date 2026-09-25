package com.popote.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "settings")
val SERVER_URL_KEY = stringPreferencesKey("server_url")
// Jeton de session renvoyé par POST /api/auth/login, envoyé ensuite en
// « Authorization: Bearer … » sur chaque requête.
val TOKEN_KEY = stringPreferencesKey("auth_token")
val USER_NAME_KEY = stringPreferencesKey("user_name")
val DEFAULT_SERVER_URL: String get() = com.popote.BuildConfig.DEFAULT_SERVER_URL

class ApiClient(context: Context) {
    private val dataStore = context.dataStore
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    val serverUrl: Flow<String> = dataStore.data.map { prefs ->
        prefs[SERVER_URL_KEY] ?: DEFAULT_SERVER_URL
    }

    val token: Flow<String?> = dataStore.data.map { prefs -> prefs[TOKEN_KEY] }

    // Copie du jeton lue par l'intercepteur, qui ne peut pas suspendre.
    // Mise à jour par RecipeRepository avant chaque appel.
    @Volatile
    var currentToken: String? = null

    private var currentBaseUrl: String = ""
    private var _api: PopoteApi? = null

    fun getApi(baseUrl: String): PopoteApi {
        val normalizedUrl = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"
        if (normalizedUrl != currentBaseUrl || _api == null) {
            currentBaseUrl = normalizedUrl
            _api = buildRetrofit(normalizedUrl).create(PopoteApi::class.java)
        }
        return _api!!
    }

    private val authInterceptor = Interceptor { chain ->
        val sent = currentToken
        val request = if (sent != null) {
            chain.request().newBuilder().header("Authorization", "Bearer $sent").build()
        } else chain.request()
        val response = chain.proceed(request)
        // Jeton expiré ou compte supprimé : on l'oublie, l'appli repasse
        // sur l'écran de connexion au lieu d'enchaîner les erreurs.
        if (response.code == 401 && sent != null && !request.url.encodedPath.endsWith("/auth/login")) {
            currentToken = null
            scope.launch {
                dataStore.edit { prefs ->
                    if (prefs[TOKEN_KEY] == sent) prefs.remove(TOKEN_KEY)
                }
            }
        }
        response
    }

    private fun buildRetrofit(baseUrl: String): Retrofit {
        val logging = HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC }
        val client = OkHttpClient.Builder()
            .addInterceptor(authInterceptor)
            .addInterceptor(logging)
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(300, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()
        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }
}
