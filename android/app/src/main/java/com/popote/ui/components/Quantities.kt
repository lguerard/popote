package com.popote.ui.components

import com.popote.data.Ingredient
import java.text.Normalizer
import kotlin.math.abs
import kotlin.math.floor
import kotlin.math.roundToInt

// ── Quantités et nombre de portions ──────────────────────────────────────────

fun parseFraction(s: String?): Double? {
    if (s.isNullOrBlank()) return null
    val t = s.trim().replace(',', '.')
    Regex("""^(\d+)\s*/\s*(\d+)$""").find(t)?.let {
        val den = it.groupValues[2].toDouble()
        return if (den == 0.0) null else it.groupValues[1].toDouble() / den
    }
    Regex("""^(\d+)\s+(\d+)\s*/\s*(\d+)$""").find(t)?.let {
        val den = it.groupValues[3].toDouble()
        return if (den == 0.0) null else it.groupValues[1].toDouble() + it.groupValues[2].toDouble() / den
    }
    return t.toDoubleOrNull()?.takeIf { it.isFinite() }
}

fun formatQty(n: Double): String {
    if (n <= 0) return "0"
    // « 416 2/3 g » ne se pèse pas : arrondi à l'unité, ou au demi pour 10-50.
    if (n >= 50) return n.roundToInt().toString()
    if (n >= 10) {
        val half = (n * 2).roundToInt() / 2.0
        return if (half % 1.0 == 0.0) half.toInt().toString() else half.toString()
    }
    val whole = floor(n).toInt()
    val frac = n - whole
    if (frac < 0.04) return if (whole > 0) whole.toString() else "0"
    for ((num, den) in listOf(1 to 4, 1 to 3, 1 to 2, 2 to 3, 3 to 4)) {
        if (abs(frac - num.toDouble() / den) < 0.06)
            return if (whole > 0) "$whole $num/$den" else "$num/$den"
    }
    val r = (n * 10).roundToInt() / 10.0
    return if (r % 1.0 == 0.0) r.toInt().toString() else r.toString()
}

/** Quantité multipliée par [scale] ; texte libre (« une pincée ») inchangé. */
fun scaleQty(qty: String?, scale: Double): String? {
    if (scale == 1.0) return qty
    val n = parseFraction(qty) ?: return qty
    return formatQty(n * scale)
}

/** Nombre saisi par l'utilisateur : « 200 », « 1,5 », « 1/2 », « 200 g », « x1.5 ». */
fun parseAmount(s: String?): Double? {
    val t = s?.trim()?.trimStart('x', 'X', '×', '*')?.trim() ?: return null
    parseFraction(t)?.let { return it }
    val lead = Regex("""^(\d+(?:[.,]\d+)?)""").find(t)?.groupValues?.get(1) ?: return null
    return lead.replace(',', '.').toDoubleOrNull()?.takeIf { it.isFinite() }
}

/**
 * Multiplicateur qui donne [target] à la place de [original] : 200 g de
 * chocolat au lieu de 120 → × 1,67, appliqué ensuite à tous les ingrédients.
 * Null si l'une des deux quantités n'est pas un nombre (« une pincée »).
 */
fun scaleFor(original: String?, target: String?): Double? {
    val from = parseFraction(original) ?: return null
    val to = parseAmount(target) ?: return null
    return if (from > 0 && to > 0) to / from else null
}

/** « ×1,5 », « ×1,67 » : multiplicateur lisible, deux décimales au plus. */
fun formatScale(scale: Double): String {
    val rounded = (scale * 100).roundToInt() / 100.0
    val text = if (rounded % 1.0 == 0.0) rounded.toInt().toString() else rounded.toString().replace('.', ',')
    return "×$text"
}

/** « 200 g », « 3 », « 1/2 c. à s. » — vide si ni quantité ni unité. */
fun ingredientAmount(i: Ingredient, scale: Double = 1.0): String =
    listOfNotNull(scaleQty(i.quantity, scale), i.unit)
        .filter { it.isNotBlank() }
        .joinToString(" ")

// ── Ingrédients utilisés par une étape ───────────────────────────────────────

// Mots qui ne désignent pas l'ingrédient lui-même (« gros sel », « farine de blé »).
private val NOT_INGREDIENT = setOf(
    "de", "du", "des", "la", "le", "les", "au", "aux", "en", "et", "ou", "un", "une", "pour", "avec", "sans",
    "gros", "grosse", "grosses", "petit", "petite", "petits", "petites", "bien", "tres", "frais", "fraiche",
    "fraiches", "fin", "fine", "fines", "demi", "entier", "entiere", "the", "and", "of", "fresh",
)

private fun fold(s: String): String =
    Normalizer.normalize(s.lowercase().replace("œ", "oe").replace("æ", "ae"), Normalizer.Form.NFD)
        .replace(Regex("""\p{Mn}+"""), "")

private fun words(s: String): List<String> =
    Regex("""[a-z0-9]+""").findAll(fold(s)).map { it.value }.toList()

/** Mot ramené au singulier (« œufs » → « oeuf ») ; appliqué des deux côtés. */
private fun stem(w: String): String =
    if (w.length > 3 && (w.endsWith("s") || w.endsWith("x")) && !w.endsWith("ss")) w.dropLast(1) else w

/** Mot principal du nom de l'ingrédient (« huile d'olive » → « huile »). */
private fun headWord(name: String): String? =
    words(name).firstOrNull { it.length >= 2 && it !in NOT_INGREDIENT && it.any(Char::isLetter) }?.let(::stem)

/**
 * Ingrédients cités dans le texte d'une étape, dans l'ordre de la liste :
 * le mode cuisine affiche leurs quantités sous l'étape, que les recettes ne
 * répètent presque jamais (« ajouter la farine »).
 */
fun ingredientsForStep(step: String, ingredients: List<Ingredient>): List<Ingredient> {
    val inStep = words(step).map(::stem).toSet()
    return ingredients.filter { ing -> headWord(ing.name)?.let { it in inStep } == true }
}
