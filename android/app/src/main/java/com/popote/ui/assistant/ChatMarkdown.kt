package com.popote.ui.assistant

// Markdown simple des réponses de l'assistant : listes, titres, **gras** et
// liens. Pas de HTML, rien d'exécuté : seuls les liens vers une recette
// (/recettes/ID) et les liens http(s) restent cliquables, comme sur le web
// (frontend/src/assistant/Markdown.jsx).

sealed class Inline {
    data class Plain(val text: String) : Inline()
    data class Bold(val text: String) : Inline()
    /** Lien vers une recette de la bibliothèque. */
    data class RecipeLink(val text: String, val recipeId: String) : Inline()
    data class WebLink(val text: String, val url: String) : Inline()
}

data class MdLine(val prefix: String, val inlines: List<Inline>, val heading: Boolean = false)

private val INLINE = Regex("""\*\*(.+?)\*\*|\[([^\]]+)]\(([^)\s]+)\)""")
private val RECIPE_PATH = Regex("""^/recettes/([0-9a-fA-F-]{36})/?$""")
private val BULLET = Regex("""^\s*[-*•]\s+""")
private val NUMBERED = Regex("""^\s*(\d+)[.)]\s+""")
private val HEADING = Regex("""^\s*#{1,6}\s+""")

fun parseInline(text: String): List<Inline> {
    val out = mutableListOf<Inline>()
    var last = 0
    for (match in INLINE.findAll(text)) {
        if (match.range.first > last) out.add(Inline.Plain(text.substring(last, match.range.first)))
        val bold = match.groups[1]
        if (bold != null) {
            out.add(Inline.Bold(bold.value))
        } else {
            val label = match.groupValues[2]
            val target = match.groupValues[3]
            val recipe = RECIPE_PATH.find(target)?.groupValues?.get(1)
            out.add(when {
                recipe != null -> Inline.RecipeLink(label, recipe)
                target.startsWith("http://") || target.startsWith("https://") -> Inline.WebLink(label, target)
                else -> Inline.Plain(label)  // autre lien : texte seul
            })
        }
        last = match.range.last + 1
    }
    if (last < text.length) out.add(Inline.Plain(text.substring(last)))
    return out
}

/** Lignes du message, puces et numéros normalisés, lignes vides conservées. */
fun parseMarkdown(text: String): List<MdLine> = text.lines().map { line ->
    when {
        HEADING.containsMatchIn(line) -> MdLine("", parseInline(line.replace(HEADING, "")), heading = true)
        BULLET.containsMatchIn(line) -> MdLine("•  ", parseInline(line.replace(BULLET, "")))
        NUMBERED.containsMatchIn(line) -> {
            val n = NUMBERED.find(line)!!.groupValues[1]
            MdLine("$n.  ", parseInline(line.replace(NUMBERED, "")))
        }
        else -> MdLine("", parseInline(line))
    }
}
