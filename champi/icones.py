"""Le logo de Champimétéo (2026-11-07) : un cèpe sous trois gouttes de pluie, « champi » et « météo ».

Une seule géométrie, sur une grille de 64, d'où sortent le logo des pages (`svg_marque`, en ligne
dans la barre du haut, aux couleurs du thème), `site/favicon.svg` et les icônes de l'appli
(`python -m champi.icones` : PNG dessinés par Pillow, sans convertisseur SVG). Il remplace le
champignon rouge à pois d'avant, qui faisait penser à une amanite tue-mouches.
"""
from __future__ import annotations

import re
import sys

from .config import SITE

# Les formes, en commandes SVG absolues (M, C, L, Z) sur une grille de 64.
CHAPEAU = "M7 34C7 20 18 11 32 11C46 11 57 20 57 34C57 36.5 55.5 38 53 38L11 38C8.5 38 7 36.5 7 34Z"
PIED = "M22 38C19.5 45 20.5 53 25 58C27.5 60.5 36.5 60.5 39 58C43.5 53 44.5 45 42 38Z"
REFLET = "M15 28C18 21.5 23.5 17 30 15.8"               # un trait clair sur le chapeau


def goutte(cx: float, cy: float, r: float) -> str:
    """Une goutte, pointe en haut : un demi-cercle en bas, deux courbes vers la pointe."""
    h = 2.2 * r
    return (f"M{cx:g} {cy - h:g}C{cx + .25 * r:g} {cy - 1.4 * r:g} {cx + r:g} {cy - .7 * r:g} {cx + r:g} {cy:g}"
            f"C{cx + r:g} {cy + .55 * r:g} {cx + .55 * r:g} {cy + r:g} {cx:g} {cy + r:g}"
            f"C{cx - .55 * r:g} {cy + r:g} {cx - r:g} {cy + .55 * r:g} {cx - r:g} {cy:g}"
            f"C{cx - r:g} {cy - .7 * r:g} {cx - .25 * r:g} {cy - 1.4 * r:g} {cx:g} {cy - h:g}Z")


GOUTTES = [goutte(18, 6.8, 2.6), goutte(32, 5.4, 2.6), goutte(46, 6.8, 2.6)]

# Les couleurs fixes (favicon, icônes) ; dans les pages, chapeau et gouttes suivent le thème.
BRUN = "#9c3510"           # --accent du thème clair
REFLET_C = "#d9662b"       # --classe-3
PIED_C = "#f2e3c9"
TRAIT = "#5a4130"          # le trait des dessins d'espèces
PLUIE = "#4f7ea8"
FOND = "#fbfaf7"           # --fond du thème clair, fond des icônes


def svg_marque(taille: int = 26, page: bool = True) -> str:
    """Le logo en SVG. `page` : en ligne dans une page, chapeau et gouttes aux couleurs du thème
    (classes `marque-*`, style.css) ; sinon couleurs fixes, pour un fichier."""
    if page:
        return (f'<svg class="marque-logo" viewBox="0 0 64 64" width="{taille}" height="{taille}" aria-hidden="true">'
                f'<path class="marque-pied" d="{PIED}"/><path class="marque-chapeau" d="{CHAPEAU}"/>'
                f'<path class="marque-reflet" d="{REFLET}"/>'
                + "".join(f'<path class="marque-goutte" d="{g}"/>' for g in GOUTTES) + "</svg>")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
            f'<path d="{PIED}" fill="{PIED_C}" stroke="{TRAIT}" stroke-width="2" stroke-linejoin="round"/>'
            f'<path d="{CHAPEAU}" fill="{BRUN}" stroke="{TRAIT}" stroke-width="2" stroke-linejoin="round"/>'
            f'<path d="{REFLET}" fill="none" stroke="{REFLET_C}" stroke-width="3" stroke-linecap="round"/>'
            + "".join(f'<path d="{g}" fill="{PLUIE}"/>' for g in GOUTTES) + "</svg>\n")


# --- Les icônes PNG, dessinées par Pillow ----------------------------------------------

def points(chemin: str, pas: int = 24) -> list[tuple[float, float]]:
    """Les commandes M, L, C, Z d'un chemin, échantillonnées en points (courbes en `pas` segments)."""
    jetons = re.findall(r"[MLCZ]|-?\d*\.?\d+", chemin)
    sortie: list[tuple[float, float]] = []
    i, commande = 0, None
    while i < len(jetons):
        if jetons[i] in "MLCZ":
            commande = jetons[i]
            i += 1
            if commande == "Z":
                continue
        v = [float(t) for t in jetons[i:i + (6 if commande == "C" else 2)]]
        i += len(v)
        if commande in "ML":
            sortie.append((v[0], v[1]))
        elif commande == "C":
            x0, y0 = sortie[-1]
            for k in range(1, pas + 1):
                t = k / pas
                a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t ** 2 * (1 - t), t ** 3
                sortie.append((a * x0 + b * v[0] + c * v[2] + d * v[4], a * y0 + b * v[1] + c * v[3] + d * v[5]))
    return sortie


def dessiner(taille: int, part: float = .8, arrondi: float = .0):
    """L'icône carrée : le logo sur le fond clair, occupant `part` du côté (les icônes masquables
    gardent le logo dans le disque central : `part` plus petit). Dessinée 4 fois plus grande puis
    réduite, pour des bords lisses."""
    from PIL import Image, ImageDraw
    ss = 4
    n = taille * ss
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if arrondi:
        d.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(arrondi * n), fill=FOND)
    else:
        d.rectangle([0, 0, n, n], fill=FOND)
    echelle = n * part / 64
    decal = (n - 64 * echelle) / 2

    def p(chemin):
        return [(decal + x * echelle, decal + y * echelle) for x, y in points(chemin)]

    epais = max(1, round(2 * echelle))
    for chemin, couleur in ((PIED, PIED_C), (CHAPEAU, BRUN)):
        pts = p(chemin)
        d.polygon(pts, fill=couleur)
        d.line(pts + [pts[0]], fill=TRAIT, width=epais, joint="curve")
    reflet = p(REFLET)
    w = max(1, round(3 * echelle))
    d.line(reflet, fill=REFLET_C, width=w, joint="curve")
    for x, y in (reflet[0], reflet[-1]):
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=REFLET_C)
    for g in GOUTTES:
        d.polygon(p(g), fill=PLUIE)
    return im.resize((taille, taille), Image.LANCZOS)


def ecrire() -> list[str]:
    """`favicon.svg`, `favicon.ico` et les icônes de l'appli, dans site/."""
    (SITE / "favicon.svg").write_text(svg_marque(page=False), encoding="utf-8")
    ecrits = ["favicon.svg"]
    for nom, taille, part in (("icone-180.png", 180, .78), ("icone-192.png", 192, .78), ("icone-512.png", 512, .78),
                              ("icone-masquable-512.png", 512, .6)):
        dessiner(taille, part).convert("RGB").save(SITE / nom, optimize=True)
        ecrits.append(nom)
    ico = dessiner(256, .86, arrondi=.18)
    ico.save(SITE / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    ecrits.append("favicon.ico")
    return ecrits


if __name__ == "__main__":
    if sys.argv[1:]:
        raise SystemExit("python -m champi.icones")
    print("Écrit :", ", ".join(ecrire()))
