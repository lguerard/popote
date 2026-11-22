package com.popote.ui.theme

import kotlin.math.atan2
import kotlin.math.cbrt
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.sin

// Palette tonale à la manière de Material 3, sans dépendance : une couleur
// est décrite en LCh (CIELAB : luminance L* perçue, chroma, teinte) ; chaque
// rôle du thème garde la teinte et prend une luminance fixe (le « ton » de
// Material 3 est justement L*). Une couleur hors de l'écran (sRGB) perd du
// chroma jusqu'à y entrer, sans changer de teinte ni de luminance.

data class Lch(val l: Double, val c: Double, val h: Double)

private fun toLinear(channel: Int): Double {
    val v = channel / 255.0
    return if (v <= 0.04045) v / 12.92 else ((v + 0.055) / 1.055).pow(2.4)
}

private fun fromLinear(v: Double): Double =
    if (v <= 0.0031308) 12.92 * v else 1.055 * v.pow(1 / 2.4) - 0.055

// Blanc de référence D65.
private const val XN = 0.95047
private const val YN = 1.0
private const val ZN = 1.08883

private fun f(t: Double) = if (t > 216.0 / 24389) cbrt(t) else (24389.0 / 27 * t + 16) / 116
private fun fInv(t: Double) = if (t * t * t > 216.0 / 24389) t * t * t else (116 * t - 16) / (24389.0 / 27)

fun argbToLch(argb: Int): Lch {
    val r = toLinear((argb shr 16) and 0xFF)
    val g = toLinear((argb shr 8) and 0xFF)
    val b = toLinear(argb and 0xFF)
    val x = 0.4124 * r + 0.3576 * g + 0.1805 * b
    val y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    val z = 0.0193 * r + 0.1192 * g + 0.9505 * b
    val fx = f(x / XN); val fy = f(y / YN); val fz = f(z / ZN)
    val l = 116 * fy - 16
    val a = 500 * (fx - fy)
    val bb = 200 * (fy - fz)
    val h = Math.toDegrees(atan2(bb, a)).let { if (it < 0) it + 360 else it }
    return Lch(l, hypot(a, bb), h)
}

/** sRGB de (L, C, h), ou null hors de l'écran. */
private fun lchToRgb(l: Double, c: Double, h: Double): DoubleArray? {
    val a = c * cos(Math.toRadians(h))
    val b = c * sin(Math.toRadians(h))
    val fy = (l + 16) / 116
    val x = XN * fInv(fy + a / 500)
    val y = YN * fInv(fy)
    val z = ZN * fInv(fy - b / 200)
    val rgb = doubleArrayOf(
        3.2406 * x - 1.5372 * y - 0.4986 * z,
        -0.9689 * x + 1.8758 * y + 0.0415 * z,
        0.0557 * x - 0.2040 * y + 1.0570 * z,
    ).map { fromLinear(it) }
    return if (rgb.all { it in -0.001..1.001 }) rgb.toDoubleArray() else null
}

/** Couleur de luminance [tone] (0 noir … 100 blanc), de teinte [hue], au plus [chroma]. */
fun tone(hue: Double, chroma: Double, tone: Double): Int {
    if (tone <= 0) return 0xFF000000.toInt()
    if (tone >= 100) return 0xFFFFFFFF.toInt()
    var c = chroma
    var rgb = lchToRgb(tone, c, hue)
    while (rgb == null && c > 0) {
        c = (c - 1).coerceAtLeast(0.0)
        rgb = lchToRgb(tone, c, hue)
    }
    val (r, g, b) = (rgb ?: lchToRgb(tone, 0.0, hue)!!).map { (it.coerceIn(0.0, 1.0) * 255).roundToInt() }
    return (0xFF shl 24) or (r shl 16) or (g shl 8) or b
}

/** Une gamme de tons d'une même teinte : primaire, secondaire, neutre… */
class TonalPalette(private val hue: Double, private val chroma: Double) {
    operator fun get(t: Int): Int = tone(hue, chroma, t.toDouble())
}

/** Les palettes d'un thème, dérivées d'une seule couleur (comme Material You). */
class SeedPalettes(seed: Int) {
    private val lch = argbToLch(seed)
    // Couleur grise (fond d'écran sans couleur) : on garde un léger chroma
    // pour que le thème ne soit pas entièrement gris.
    val primary = TonalPalette(lch.h, maxOf(lch.c, 36.0))
    val secondary = TonalPalette(lch.h, minOf(maxOf(lch.c / 3, 12.0), 24.0))
    val tertiary = TonalPalette((lch.h + 60) % 360, 24.0)
    val neutral = TonalPalette(lch.h, 4.0)
    val neutralVariant = TonalPalette(lch.h, 8.0)
}
