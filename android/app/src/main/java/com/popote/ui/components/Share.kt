package com.popote.ui.components

import android.content.Context
import android.content.Intent

/** Ouvre la feuille de partage Android (WhatsApp, SMS, mail…) avec ce texte. */
fun shareText(context: Context, text: String, title: String = "Partager") {
    val send = Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"
        putExtra(Intent.EXTRA_TEXT, text)
    }
    context.startActivity(Intent.createChooser(send, title))
}
