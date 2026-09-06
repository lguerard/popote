package com.popote.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "settings")
val SERVER_URL_KEY = stringPreferencesKey("server_url")
val SESSION_TOKEN_KEY = stringPreferencesKey("session_token")
val DEFAULT_SERVER_URL: String get() = com.popote.BuildConfig.DEFAULT_SERVER_URL

class ApiClient(context: Context) {
    private val dataStore = context.dataStore

    val serverUrl: Flow<String> = dataStore.data.map { prefs ->
        prefs[SERVER_URL_KEY] ?: DEFAULT_SERVER_URL
    }

    // Lu par l'intercepteur à chaque requête : mis à jour dès la connexion,
    // sans reconstruire le client OkHttp.
    @Volatile
    private var token: String? = null

    fun setToken(value: String?) {
        token = value
    }

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

    private fun buildRetrofit(baseUrl: String): Retrofit {
        val logging = HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC }
        val client = OkHttpClient.Builder()
            .addInterceptor(logging)
            // L'API exige une session depuis l'ajout des comptes. Le jeton part
            // avec chaque requête ; les routes anonymes (login, /health) ne le
            // regardent pas, donc il n'y a rien à filtrer ici.
            .addInterceptor { chain ->
                val request = chain.request()
                val current = token
                val authed = if (current.isNullOrEmpty()) {
                    request
                } else {
                    request.newBuilder().header("Authorization", "Bearer $current").build()
                }
                val response = chain.proceed(authed)
                // Jeton refusé alors qu'on en avait un : session révoquée
                // (mot de passe changé ailleurs) ou expirée. On repasse par
                // l'écran de connexion plutôt que d'afficher « erreur réseau ».
                if (response.code == 401 && !current.isNullOrEmpty()) {
                    SessionEvents.notifyExpired()
                }
                response
            }
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
