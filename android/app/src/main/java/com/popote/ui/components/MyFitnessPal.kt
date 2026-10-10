package com.popote.ui.components

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri

/** Identifiant de l'appli MyFitnessPal sur le Play Store. */
const val MFP_PACKAGE = "com.myfitnesspal.android"

/**
 * Ouvre l'appli MyFitnessPal, ou sa page du Play Store si elle n'est pas
 * installée. MyFitnessPal n'expose ni API ni cible de partage pour les
 * recettes : on prépare le presse-papiers avant d'ouvrir l'appli, il n'y a
 * plus qu'à coller.
 *
 * @return true si l'appli a été ouverte, false si c'est le Play Store.
 */
fun openMyFitnessPal(context: Context): Boolean {
    val launch = context.packageManager.getLaunchIntentForPackage(MFP_PACKAGE)
    if (launch != null) {
        context.startActivity(launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        return true
    }
    val store = Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=$MFP_PACKAGE"))
    try {
        context.startActivity(store.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    } catch (_: ActivityNotFoundException) {
        context.startActivity(
            Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=$MFP_PACKAGE"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }
    return false
}

/**
 * Adresse joignable seulement depuis le réseau local (192.168.x.x, …) :
 * les serveurs de MyFitnessPal ne pourront pas y lire la recette.
 */
fun isLocalServer(url: String?): Boolean {
    val host = url?.let { Uri.parse(it).host }?.lowercase() ?: return false
    if (host == "localhost" || host.endsWith(".local") || host.endsWith(".lan") || !host.contains('.')) return true
    val parts = host.split('.').mapNotNull { it.toIntOrNull() }
    if (parts.size != 4) return false
    return parts[0] == 10 || parts[0] == 127 ||
        (parts[0] == 192 && parts[1] == 168) ||
        (parts[0] == 172 && parts[1] in 16..31) ||
        (parts[0] == 100 && parts[1] in 64..127) // Tailscale / CGNAT
}
