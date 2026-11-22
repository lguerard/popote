package com.popote.ui.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

/*
 * Briques du style « 2026 » (Material 3 Expressive) : grand bloc sombre pour
 * l'action du moment, bouton festonné, progression ondulée, tuiles et barre de
 * navigation flottante. Les couleurs viennent du thème, Material You compris.
 */

/** Couleurs du grand bloc sombre (« Ce soir », mode cuisine). */
data class HeroColors(
    val container: Color,
    val content: Color,
    val muted: Color,
    val accent: Color,
    val onAccent: Color,
    /** Fond d'un élément posé sur le bloc (pastille, compteur). */
    val raised: Color,
    val outline: Color,
)

@Composable
fun heroColors(): HeroColors {
    val cs = MaterialTheme.colorScheme
    val dark = cs.background.luminance() < 0.5f
    return if (dark) HeroColors(
        container = cs.primaryContainer,
        content = cs.onPrimaryContainer,
        muted = cs.onPrimaryContainer.copy(alpha = 0.8f),
        accent = cs.primary,
        onAccent = cs.onPrimary,
        raised = cs.onPrimaryContainer.copy(alpha = 0.12f),
        outline = cs.onPrimaryContainer.copy(alpha = 0.4f),
    ) else {
        // Ton très foncé de la couleur principale (le thème n'en donne pas
        // toujours un : l'orange de Popote s'arrête à un orange brûlé).
        val deep = lerp(cs.onPrimaryContainer, Color.Black, if (cs.onPrimaryContainer.luminance() > 0.05f) 0.6f else 0.2f)
        HeroColors(
            container = deep,
            content = cs.surface,
            muted = cs.surface.copy(alpha = 0.8f),
            accent = cs.inversePrimary,
            onAccent = deep,
            raised = cs.surface.copy(alpha = 0.12f),
            outline = cs.surface.copy(alpha = 0.4f),
        )
    }
}

/** Forme festonnée (« cookie ») des boutons principaux. */
class CookieShape(private val lobes: Int = 9, private val depth: Float = 0.075f) : Shape {
    override fun createOutline(size: Size, layoutDirection: LayoutDirection, density: Density): Outline {
        val path = Path()
        val cx = size.width / 2f
        val cy = size.height / 2f
        val r = min(cx, cy) / (1f + depth)
        val n = 144
        for (i in 0..n) {
            val a = i.toFloat() / n * 2f * PI.toFloat()
            val rr = r * (1f + depth * cos(lobes * a))
            val x = cx + rr * cos(a)
            val y = cy + rr * sin(a)
            if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        path.close()
        return Outline.Generic(path)
    }
}

/** Barre de progression ondulée : la partie faite ondule, le reste est droit. */
@Composable
fun WavyProgress(progress: Float, color: Color, trackColor: Color, modifier: Modifier = Modifier) {
    Canvas(modifier.fillMaxWidth().height(16.dp)) {
        val p = progress.coerceIn(0f, 1f)
        val stroke = 5.dp.toPx()
        val amp = 3.dp.toPx()
        val wave = 18.dp.toPx()
        val mid = size.height / 2f
        val start = stroke / 2f
        val end = start + (size.width - stroke) * p
        val gap = 7.dp.toPx()
        if (end + gap < size.width - start) {
            drawLine(trackColor, Offset(end + gap, mid), Offset(size.width - start, mid), stroke, StrokeCap.Round)
        }
        if (p > 0f) {
            val path = Path()
            var x = start
            path.moveTo(x, mid)
            while (x < end) {
                x = min(x + 1.5f, end)
                path.lineTo(x, mid + amp * sin((x - start) / wave * 2f * PI.toFloat()))
            }
            drawPath(path, color, style = Stroke(stroke, cap = StrokeCap.Round))
        }
    }
}

/** Tuile colorée cliquable du tableau de bord. */
@Composable
fun BentoTile(
    container: Color,
    content: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    shape: Shape = RoundedCornerShape(28.dp),
    body: @Composable ColumnScope.() -> Unit,
) {
    Surface(onClick = onClick, shape = shape, color = container, contentColor = content, modifier = modifier) {
        Column(
            Modifier.fillMaxSize().padding(horizontal = 18.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.SpaceBetween,
            content = body,
        )
    }
}

/** Petite étiquette arrondie (« Ce soir », « Vidéo »…). */
@Composable
fun Pill(text: String, container: Color, content: Color, modifier: Modifier = Modifier) {
    Surface(shape = CircleShape, color = container, contentColor = content, modifier = modifier) {
        Text(
            text,
            Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.ExtraBold,
            maxLines = 1,
        )
    }
}

data class NavItem(val route: String, val label: String, val icon: ImageVector)

/**
 * Barre de navigation flottante : une pilule sombre, l'onglet ouvert s'élargit
 * avec son nom.
 */
@Composable
fun FloatingNavBar(items: List<NavItem>, selected: String?, onSelect: (String) -> Unit, modifier: Modifier = Modifier) {
    val cs = MaterialTheme.colorScheme
    Box(
        modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 16.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Surface(shape = CircleShape, color = cs.inverseSurface, shadowElevation = 6.dp) {
            Row(
                Modifier.padding(6.dp).selectableGroup(),
                horizontalArrangement = Arrangement.spacedBy(2.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                items.forEach { item ->
                    val on = item.route == selected
                    val bg by animateColorAsState(if (on) cs.inversePrimary else Color.Transparent, label = "nav")
                    val fg = if (on) cs.onPrimaryContainer else cs.inverseOnSurface
                    Row(
                        Modifier
                            .height(52.dp)
                            .clip(CircleShape)
                            .background(bg)
                            .selectable(selected = on, onClick = { onSelect(item.route) }, role = Role.Tab)
                            .animateContentSize()
                            .padding(horizontal = if (on) 16.dp else 14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Icon(item.icon, contentDescription = if (on) null else item.label, tint = fg)
                        if (on) Text(item.label, color = fg, style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.ExtraBold, maxLines = 1)
                    }
                }
            }
        }
    }
}
