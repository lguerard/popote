"""Icône de Popote (une poêle à paella, 🥘) : une seule description des formes,
d'où sortent toutes les versions.

    python3 scripts/icone.py            # icône Android + favicon SVG
    python3 scripts/icone.py --png      # + PNG du web (Playwright + Chromium)

Grille Android des icônes adaptatives : 108 × 108, le lanceur découpe la forme
(cercle, squircle Samsung…) et seul le cercle central de 66 de diamètre est
toujours visible. Tout le dessin y tient.

Android 13+ teinte les icônes « à thème » : le calque monochrome ne garde que
la silhouette (la couleur vient du thème du téléphone).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "android/app/src/main/res"
PUBLIC = ROOT / "frontend/public"

# Fond : orange Popote en dégradé radial (lumière en haut à gauche).
BACKGROUND = {"cx": 41, "cy": 30.2, "r": 91.8,
              "stops": [(0, "#FDBA74"), (0.55, "#F97316"), (1, "#C2410C")]}

# (type, paramètres…) ; ordre = ordre de dessin.
FOREGROUND = [
    # poêle : anses, flanc (épaisseur), bord, riz safrané
    ("rrect", 22, 55.5, 10, 7.5, 3.75, "#2B211C"),
    ("rrect", 76, 55.5, 10, 7.5, 3.75, "#2B211C"),
    ("ellipse", 54, 63, 24.5, 17.5, "#1C1512"),
    ("ellipse", 54, 59.5, 24.5, 17.5, "#3A2D26"),
    ("ellipse", 54, 59.5, 20.5, 14.2, "#F2A81D"),
    ("ellipse", 52, 57, 15.5, 9.5, "#FBC93F"),
    # poivrons
    ("rrect", 49, 65.2, 9, 3.4, 1.7, "#D7262E", (-12, 53.5, 66.9)),
    ("rrect", 49.5, 49.5, 8, 3.2, 1.6, "#D7262E", (10, 53.5, 51.1)),
    # crevettes : corps en arc, queue en triangle
    ("stroke", "M40.6,64.2 a5.6,5.6 0 1,1 8.9,-4.9", "#F26B3A", 4, 1),
    ("path", "M40.6,64.2 l-3.6,1.6 l1.6,-3.8 z", "#F26B3A"),
    ("stroke", "M67.4,54.8 a5.6,5.6 0 1,1 -8.9,4.9", "#F26B3A", 4, 1),
    ("path", "M67.4,54.8 l3.6,-1.6 l-1.6,3.8 z", "#F26B3A"),
    # petits pois
    ("ellipse", 40.5, 54.5, 2.1, 2.1, "#3DAE4B"),
    ("ellipse", 61.5, 67, 2.1, 2.1, "#3DAE4B"),
    ("ellipse", 69, 62.8, 2.1, 2.1, "#3DAE4B"),
    ("ellipse", 60.5, 50.3, 2.1, 2.1, "#3DAE4B"),
    # vapeur
    ("stroke", "M46,39.5 c-2.6,-2.6 2.6,-4.4 0,-8", "#FFFFFF", 2.8, 0.92),
    ("stroke", "M54,38 c-2.6,-2.6 2.6,-4.4 0,-8", "#FFFFFF", 2.8, 0.92),
    ("stroke", "M62,39.5 c-2.6,-2.6 2.6,-4.4 0,-8", "#FFFFFF", 2.8, 0.92),
]


def ellipse_d(cx, cy, rx, ry) -> str:
    return (f"M{cx - rx:g},{cy:g} a{rx:g},{ry:g} 0 1,0 {2 * rx:g},0 "
            f"a{rx:g},{ry:g} 0 1,0 {-2 * rx:g},0 z")


def rrect_d(x, y, w, h, r) -> str:
    def line(axis, length):  # pas de segment nul (« v0 ») : coin contre coin
        return f"{axis}{length:g} " if length else ""
    return (f"M{x + r:g},{y:g} {line('h', w - 2 * r)}a{r:g},{r:g} 0 0,1 {r:g},{r:g} "
            f"{line('v', h - 2 * r)}a{r:g},{r:g} 0 0,1 {-r:g},{r:g} {line('h', -(w - 2 * r))}"
            f"a{r:g},{r:g} 0 0,1 {-r:g},{-r:g} {line('v', -(h - 2 * r))}a{r:g},{r:g} 0 0,1 {r:g},{-r:g} z")


def shapes(elements):
    """(d, fill, stroke, rotation, even_odd) pour chaque forme."""
    for kind, *p in elements:
        if kind == "ellipse":
            yield {"d": ellipse_d(*p[:4]), "fill": p[4]}
        elif kind == "rrect":
            yield {"d": rrect_d(*p[:5]), "fill": p[5], "rotate": p[6] if len(p) > 6 else None}
        elif kind == "path":
            yield {"d": p[0], "fill": p[1], "even_odd": len(p) > 2 and p[2]}
        elif kind == "stroke":
            yield {"d": p[0], "stroke": p[1], "width": p[2], "alpha": p[3]}


def monochrome():
    """Silhouette : le bord de la poêle en anneau (le riz évidé), son
    épaisseur en croissant dessous, les anses, puis garniture et vapeur
    pleines dans le creux. Un seul ton : la couleur vient du thème."""
    rim, side = ellipse_d(54, 59.5, 24.5, 17.5), ellipse_d(54, 63, 24.5, 17.5)
    elements = [
        ("rrect", 22, 55.5, 10, 7.5, 3.75, "#FFFFFF"),
        ("rrect", 76, 55.5, 10, 7.5, 3.75, "#FFFFFF"),
        ("path", f"{side} {rim}", "#FFFFFF", True),                          # épaisseur
        ("path", f"{rim} {ellipse_d(54, 59.5, 20.5, 14.2)}", "#FFFFFF", True),  # anneau
    ]
    for element in FOREGROUND[6:]:  # garniture et vapeur (après poêle et riz)
        kind, *p = element
        if kind == "stroke":
            elements.append(("stroke", p[0], "#FFFFFF", p[2], 1))
        elif kind == "rrect":
            elements.append(("rrect", *p[:5], "#FFFFFF", *p[6:]))
        elif kind == "ellipse":
            elements.append(("ellipse", *p[:4], "#FFFFFF"))
        else:
            elements.append(("path", p[0], "#FFFFFF"))
    return elements


# ── Android (VectorDrawable) ─────────────────────────────────────────────────

def _argb(color: str, alpha: float = 1) -> str:
    return f"#{round(alpha * 255):02X}{color.lstrip('#').upper()}"


def vector_xml(elements, comment: str) -> str:
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           f"<!-- {comment} Généré par scripts/icone.py : modifier le script, pas ce fichier. -->",
           '<vector xmlns:android="http://schemas.android.com/apk/res/android"',
           '    android:width="108dp" android:height="108dp"',
           '    android:viewportWidth="108" android:viewportHeight="108">']
    for s in shapes(elements):
        attrs = [f'android:pathData="{s["d"]}"']
        if "stroke" in s:
            attrs += [f'android:strokeColor="{_argb(s["stroke"], s["alpha"])}"',
                      f'android:strokeWidth="{s["width"]:g}"', 'android:strokeLineCap="round"']
        else:
            attrs.append(f'android:fillColor="{_argb(s["fill"])}"')
            if s.get("even_odd"):
                attrs.append('android:fillType="evenOdd"')
        path = "<path " + " ".join(attrs) + "/>"
        if s.get("rotate"):
            angle, px, py = s["rotate"]
            out.append(f'    <group android:rotation="{angle:g}" android:pivotX="{px:g}" android:pivotY="{py:g}">')
            out.append(f"        {path}")
            out.append("    </group>")
        else:
            out.append(f"    {path}")
    out.append("</vector>")
    return "\n".join(out) + "\n"


def background_xml() -> str:
    b = BACKGROUND
    stops = "\n".join(
        f'                <item android:offset="{o:g}" android:color="{_argb(c)}"/>' for o, c in b["stops"]
    )
    return f'''<?xml version="1.0" encoding="utf-8"?>
<!-- Fond de l'icône. Généré par scripts/icone.py : modifier le script, pas ce fichier. -->
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:aapt="http://schemas.android.com/aapt"
    android:width="108dp" android:height="108dp"
    android:viewportWidth="108" android:viewportHeight="108">
    <path android:pathData="M0,0h108v108h-108z">
        <aapt:attr name="android:fillColor">
            <gradient android:type="radial" android:centerX="{b["cx"]:g}" android:centerY="{b["cy"]:g}"
                android:gradientRadius="{b["r"]:g}">
{stops}
            </gradient>
        </aapt:attr>
    </path>
</vector>
'''


ADAPTIVE = '''<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background"/>
    <foreground android:drawable="@drawable/ic_launcher_foreground"/>
    <!-- Android 13+ : icône à thème, teintée comme les autres applis. -->
    <monochrome android:drawable="@drawable/ic_launcher_monochrome"/>
</adaptive-icon>
'''


# ── SVG (web) ────────────────────────────────────────────────────────────────

def svg_body(elements) -> str:
    parts = []
    for s in shapes(elements):
        if "stroke" in s:
            attrs = (f'fill="none" stroke="{s["stroke"]}" stroke-width="{s["width"]:g}" '
                     f'stroke-linecap="round"' + (f' stroke-opacity="{s["alpha"]:g}"' if s["alpha"] < 1 else ""))
        else:
            attrs = f'fill="{s["fill"]}"' + (' fill-rule="evenodd"' if s.get("even_odd") else "")
        if s.get("rotate"):
            attrs += ' transform="rotate({:g} {:g} {:g})"'.format(*s["rotate"])
        parts.append(f'<path d="{s["d"]}" {attrs}/>')
    return "".join(parts)


def svg(view: tuple[float, float, float], radius: float = 0) -> str:
    """Icône complète ; view = (x, y, côté) : le cadrage (zoom sur la poêle)."""
    x, y, side = view
    b = BACKGROUND
    stops = "".join(f'<stop offset="{o:g}" stop-color="{c}"/>' for o, c in b["stops"])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:g} {y:g} {side:g} {side:g}">'
        f'<defs><radialGradient id="bg" gradientUnits="userSpaceOnUse" cx="{b["cx"]:g}" cy="{b["cy"]:g}" '
        f'r="{b["r"]:g}">{stops}</radialGradient></defs>'
        f'<rect x="{x:g}" y="{y:g}" width="{side:g}" height="{side:g}" rx="{radius:g}" fill="url(#bg)"/>'
        f"{svg_body(FOREGROUND)}</svg>\n"
    )


# Cadrages : la poêle occupe ~61 % de la grille Android ; ailleurs on zoome.
FAVICON = ((15, 17, 78), 18)           # 16-32 px : la poêle au plus grand
ANY = ((10, 12, 88), 20)               # icônes « any » du manifeste, coins arrondis
MASKABLE = ((6, 7, 96), 0)             # « maskable » : zone sûre = 80 % du carré
APPLE = ((9, 11, 90), 0)               # iOS arrondit lui-même


def render_png(svg_text: str, out: Path, size: int) -> None:
    from playwright.sync_api import sync_playwright

    sized = svg_text.replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=_chromium())
        page = browser.new_page(viewport={"width": size, "height": size})
        page.set_content(f"<html><body style='margin:0'>{sized}</body></html>")
        page.locator("svg").screenshot(path=str(out), omit_background=True)
        browser.close()


def _chromium() -> str | None:
    path = Path("/opt/pw-browsers/chromium")
    return str(path) if path.exists() else None


def main() -> None:
    drawable = RES / "drawable"
    (drawable / "ic_launcher_background.xml").write_text(background_xml())
    (drawable / "ic_launcher_foreground.xml").write_text(
        vector_xml(FOREGROUND, "Icône : poêle à paella (🥘), dans la zone sûre de 66 dp."))
    (drawable / "ic_launcher_monochrome.xml").write_text(
        vector_xml(monochrome(), "Icône à thème (Android 13+) : silhouette, teintée par le système."))
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        (RES / "mipmap-anydpi-v26" / name).write_text(ADAPTIVE)
    (PUBLIC / "favicon.svg").write_text(svg(*FAVICON))
    if "--png" in sys.argv:
        render_png(svg(*ANY), PUBLIC / "icon-192.png", 192)
        render_png(svg(*ANY), PUBLIC / "icon-512.png", 512)
        render_png(svg(*MASKABLE), PUBLIC / "icon-maskable-512.png", 512)
        render_png(svg(*APPLE), PUBLIC / "apple-touch-icon.png", 180)
    print("Icônes écrites.")


if __name__ == "__main__":
    main()
