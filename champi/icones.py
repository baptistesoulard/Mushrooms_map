"""Le logo de Champimétéo (2026-11-07) : un cèpe en réserve dans une goutte de pluie, « champi » et
« météo » d'un seul coup d'œil.

Une seule géométrie, sur une grille de 64, d'où sortent le logo des pages (`svg_marque`, en ligne
dans la barre du haut : la goutte à l'accent du thème, le cèpe aux couleurs du creux, celles du fond
en mode sombre), `site/favicon.svg` et les icônes de l'appli (`python -m champi.icones` : PNG
dessinés par Pillow, sans convertisseur SVG). Il remplace le champignon rouge à pois d'avant, qui
faisait penser à une amanite tue-mouches, puis un cèpe sous trois gouttes, trop « image clipart ».
"""
from __future__ import annotations

import re
import sys

from .config import SITE

# Les formes, en commandes SVG absolues (M, C, L, Z) sur une grille de 64.
GOUTTE = "M32 2.5C25 13 11 26 11 40.5C11 52 20.5 61.5 32 61.5C43.5 61.5 53 52 53 40.5C53 26 39 13 32 2.5Z"
CHAPEAU = "M15.5 38C15.5 29.5 23 24 32 24C41 24 48.5 29.5 48.5 38C48.5 39.6 47.5 40.4 46 40.4L18 40.4C16.5 40.4 15.5 39.6 15.5 38Z"
PIED = "M27.2 42.4C24 46.2 22.6 51.6 25.4 55.4C27.4 58.1 36.6 58.1 38.6 55.4C41.4 51.6 40 46.2 36.8 42.4Z"   # renflé, comme un cèpe

# Les couleurs fixes (favicon, icônes) ; dans les pages, elles suivent le thème (style.css).
BRUN = "#9c3510"           # --accent du thème clair : la goutte
CHAPEAU_C = "#f3dcbc"
PIED_C = "#fbf3e6"
FOND = "#fbfaf7"           # --fond du thème clair, fond des icônes


def svg_marque(taille: int = 30, page: bool = True) -> str:
    """Le logo en SVG. `page` : en ligne dans une page, aux couleurs du thème (classes `marque-*`,
    style.css) ; sinon couleurs fixes, pour un fichier."""
    if page:
        return (f'<svg class="marque-logo" viewBox="0 0 64 64" width="{taille}" height="{taille}" aria-hidden="true">'
                f'<path class="marque-goutte" d="{GOUTTE}"/><path class="marque-chapeau" d="{CHAPEAU}"/>'
                f'<path class="marque-pied" d="{PIED}"/></svg>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
            f'<path d="{GOUTTE}" fill="{BRUN}"/><path d="{CHAPEAU}" fill="{CHAPEAU_C}"/>'
            f'<path d="{PIED}" fill="{PIED_C}"/></svg>\n')


# --- Le sous-bois : le décor du bas des bandeaux et du pied de page -------------------------

# Collines, arbres, sol, champignons : clair, puis sombre (accordés à --surface et --accent-doux).
SOUS_BOIS_COULEURS = {"sous-bois.svg": ("#f1e6d8", "#e8d6c1", "#dcc3a6", "#9c3510"),
                      "sous-bois-sombre.svg": ("#221f1b", "#2a2520", "#332b23", "#f2a65a")}


def sous_bois(colline: str, arbre: str, sol: str, champi: str) -> str:
    """Une bande de 1200 × 74 : collines, sapins et feuillus, sol, quelques champignons. Posée en
    fond par style.css (`--sous-bois`), répétée en largeur ; toujours le même dessin, décoratif.
    Les courbes se raccordent d'une bande à l'autre : même hauteur aux deux bords, et la même
    pente (le premier point de contrôle et le dernier sont symétriques), sinon une marche."""
    sapins, feuillus, champis = [], [], []
    for x, h in ((60, 30), (92, 24), (182, 34), (318, 28), (350, 22), (522, 32), (700, 26), (732, 34),
                 (884, 28), (1012, 32), (1044, 24), (1152, 30)):
        b, w = 52, h * .32
        sapins.append(f"M{x} {b - h}L{x - w:g} {b - h * .45:g}L{x + w:g} {b - h * .45:g}Z"
                      f"M{x} {b - h * .75:g}L{x - w * 1.35:g} {b}L{x + w * 1.35:g} {b}Z")
    for x, r in ((132, 12), (252, 14), (440, 11), (604, 13), (806, 12), (962, 14), (1100, 11)):
        feuillus.append(f'<circle cx="{x}" cy="{50 - r * 1.6:g}" r="{r}"/><rect x="{x - 1.5}" y="{50 - r:g}" '
                        f'width="3" height="{r + 4}"/>')
    for x, t in ((226, 1), (240, .7), (642, .9), (982, 1.1), (996, .75)):
        champis.append(f'<path d="M{x - 6 * t:g} {61 - 4 * t:g}C{x - 6 * t:g} {61 - 9 * t:g} {x + 6 * t:g} {61 - 9 * t:g} '
                       f'{x + 6 * t:g} {61 - 4 * t:g}Z"/><rect x="{x - 1.6 * t:g}" y="{61 - 4.5 * t:g}" '
                       f'width="{3.2 * t:g}" height="{5 * t:g}" rx="{t:g}"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 74" width="1200" height="74">'
            f'<path fill="{colline}" d="M0 38C140 30 260 40 400 34C540 28 660 42 800 34C940 26 1060 46 1200 38L1200 74L0 74Z"/>'
            f'<g fill="{arbre}"><path d="{"".join(sapins)}"/>{"".join(feuillus)}</g>'
            f'<path fill="{sol}" d="M0 58C200 54 380 60 600 57C820 54 1000 62 1200 58L1200 74L0 74Z"/>'

            f'<g fill="{champi}" fill-opacity=".5">{"".join(champis)}</g></svg>\n')


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

    for chemin, couleur in ((GOUTTE, BRUN), (CHAPEAU, CHAPEAU_C), (PIED, PIED_C)):
        d.polygon(p(chemin), fill=couleur)
    return im.resize((taille, taille), Image.LANCZOS)


def ecrire() -> list[str]:
    """`favicon.svg`, `favicon.ico`, les icônes de l'appli et le sous-bois, dans site/."""
    (SITE / "favicon.svg").write_text(svg_marque(page=False), encoding="utf-8")
    ecrits = ["favicon.svg"]
    for nom, couleurs in SOUS_BOIS_COULEURS.items():
        (SITE / "img" / nom).write_text(sous_bois(*couleurs), encoding="utf-8")
        ecrits.append(f"img/{nom}")
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
