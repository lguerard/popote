package com.popote.ui.components

/** Durée totale (secondes) citée dans une étape : « cuire 10 min », « 1 h 30 »… */
fun parseStepSeconds(text: String): Int? {
    val re = Regex("""(\d+)\s*(heures?|h\b|min(?:ute)?s?|sec(?:onde)?s?)""", RegexOption.IGNORE_CASE)
    var total = 0
    var found = false
    re.findAll(text).forEach { m ->
        found = true
        val n = m.groupValues[1].toInt()
        val unit = m.groupValues[2].lowercase()
        total += when {
            unit.startsWith("h") -> n * 3600
            unit.startsWith("min") -> n * 60
            else -> n
        }
    }
    return if (found && total > 0) total else null
}

fun formatSeconds(sec: Int): String {
    val h = sec / 3600
    val m = (sec % 3600) / 60
    val s = sec % 60
    return when {
        h > 0 -> "%dh%02d:%02d".format(h, m, s)
        else -> "%d:%02d".format(m, s)
    }
}

/** « 2026-09-25 » → « 25/09/2026 ». */
fun formatIsoDate(iso: String?): String {
    if (iso.isNullOrBlank()) return ""
    val parts = iso.take(10).split("-")
    return if (parts.size == 3) "${parts[2]}/${parts[1]}/${parts[0]}" else iso
}
