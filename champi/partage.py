"""Images de partage, réécrites chaque matin par l'export : l'aperçu qu'affichent les
messageries et les réseaux quand on y colle le lien d'une page (`og:image`, 1200 × 630).

`data/partage/<département>.png` et `france.png` : à gauche la carte du jour (pour chaque
pixel de 1,15 km, la meilleure des espèces), à droite la semaine espèce par espèce, aux
couleurs du site (`style.css`, vérifié par les tests). `carte-france.png` : la carte seule,
pour l'accueil. Aucun coin : des pixels de 1,15 km, comme la vue large de la carte.

Ne lit aucune donnée : reçoit l'aperçu du jour et les niveaux, rend des PNG.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .pages import JOURS_COURTS, NOM, date_longue

LARGEUR, HAUTEUR = 1200, 630
CARTE = (560, 430)                           # la place de la carte, à gauche, sous le titre
VIGNETTE = (560, 560)                        # la carte seule, pour l'accueil
# Les couleurs du site (style.css) : la classe 0 de l'indice n'en a pas (transparente sur la carte).
FOND, TRAIT, TEXTE, TEXTE_2, TEXTE_3 = "#fbfaf7", "#e2ded5", "#1d1b17", "#57534a", "#7a756a"
CLASSES = ["#f9d7a6", "#f2a65a", "#d9662b", "#9c3510", "#5e1b13"]   # --classe-1 à --classe-5
FORET = "#dfe6d3"                 # forêt à l'indice très faible : la forme des massifs
VOISINS = "#e6e3dc"               # la forêt des départements voisins, pour situer
POLICES = {
    False: ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"],
    True: ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
           "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"],
}


@lru_cache(maxsize=None)
def police(taille: int, gras: bool = False):
    for chemin in POLICES[gras]:
        try:
            return ImageFont.truetype(chemin, taille)
        except OSError:
            continue
    return ImageFont.load_default(taille)        # Pillow ≥ 10.1 : une police vectorielle


def _rgb(hexa: str) -> tuple[int, int, int]:
    return tuple(int(hexa[i:i + 2], 16) for i in (1, 3, 5))


def classes(codes: np.ndarray, echelle: int, seuils: list[float]) -> np.ndarray:
    """Codes de l'aperçu (indice × échelle, ou au-delà hors forêt) → classe 0 à 4, -1 hors forêt."""
    k = np.searchsorted(np.asarray(seuils[:-1]), codes / echelle, side="right")
    return np.where(codes <= echelle, k, -1).astype(np.int8)


def _peindre(cl: np.ndarray, voisin: np.ndarray | None = None) -> Image.Image:
    rgb = np.empty((*cl.shape, 3), dtype=np.uint8)
    rgb[:] = _rgb(FOND)
    rgb[cl == 0] = _rgb(FORET)
    for k, c in enumerate(CLASSES, start=1):
        rgb[cl == k] = _rgb(c)
    if voisin is not None:
        rgb[voisin] = _rgb(VOISINS)
    return Image.fromarray(rgb, "RGB")


def carte_france(cl: np.ndarray, place: tuple[int, int] = CARTE) -> Image.Image:
    """Toute la France dans `place` (largeur, hauteur) : le meilleur pixel de chaque carré, pour
    que les bons massifs restent visibles une fois réduits."""
    f = int(np.ceil(max(cl.shape[1] / place[0], cl.shape[0] / place[1])))
    h, w = (cl.shape[0] // f) * f, (cl.shape[1] // f) * f
    reduite = cl[:h, :w].reshape(h // f, f, w // f, f).max(axis=(1, 3))
    img = _peindre(reduite)
    s = min(place[0] / img.width, place[1] / img.height)
    return img.resize((round(img.width * s), round(img.height * s)), Image.Resampling.NEAREST)


def carte_departement(cl: np.ndarray, dans: np.ndarray, place: tuple[int, int] = CARTE) -> Image.Image:
    """Le département seul en couleurs, la forêt des voisins en gris autour ; des pixels
    agrandis d'un nombre entier de fois."""
    lignes, colonnes = np.nonzero(dans)
    i0, i1 = max(lignes.min() - 3, 0), min(lignes.max() + 4, cl.shape[0])
    j0, j1 = max(colonnes.min() - 3, 0), min(colonnes.max() + 4, cl.shape[1])
    morceau, d = cl[i0:i1, j0:j1], dans[i0:i1, j0:j1]
    img = _peindre(morceau, voisin=(~d) & (morceau >= 0))
    s = max(1, min(place[0] // img.width, place[1] // img.height))
    return img.resize((img.width * s, img.height * s), Image.Resampling.NEAREST)


def _ajuster(texte: str, largeur: int, taille: int, gras: bool = False):
    """La plus grande police (jusqu'à `taille`) où le texte tient dans `largeur`."""
    while taille > 14 and police(taille, gras).getlength(texte) > largeur:
        taille -= 2
    return police(taille, gras)


def image(titre: str, sous_titre: str, carte: Image.Image, legende_carte: str,
          lignes: list[tuple[str, list[int | None], list[str] | None]], jours: list[date]) -> Image.Image:
    """`lignes` : (espèce, niveau de chaque jour — None sans forêt calculée —, texte de chaque
    case ou None)."""
    img = Image.new("RGB", (LARGEUR, HAUTEUR), FOND)
    d = ImageDraw.Draw(img)
    d.text((40, 34), titre, fill=TEXTE, font=_ajuster(titre, LARGEUR - 80, 46, gras=True))
    d.text((40, 94), sous_titre, fill=TEXTE_2, font=police(24))
    # La carte, centrée dans sa place, et sa légende dessous.
    x0, y0 = 40, 146
    img.paste(carte, (x0 + (CARTE[0] - carte.width) // 2, y0 + (CARTE[1] - carte.height) // 2))
    d.text((x0, HAUTEUR - 26), legende_carte, fill=TEXTE_3, font=police(17), anchor="ls")
    # La semaine : des lignes plus serrées quand les espèces sont nombreuses.
    gauche, haut, nom_l = 640, 150, 170
    pas = min(44, (HAUTEUR - 64 - (haut + 46)) // max(len(lignes), 1))
    case = pas - 6
    for k, j in enumerate(jours):
        x = gauche + nom_l + k * pas
        d.text((x + case / 2, haut), f"{JOURS_COURTS[j.weekday()]}", fill=TEXTE if k == 0 else TEXTE_3,
               font=police(15, gras=k == 0), anchor="mt")
        d.text((x + case / 2, haut + 18), str(j.day), fill=TEXTE if k == 0 else TEXTE_3,
               font=police(15, gras=k == 0), anchor="mt")
    y = haut + 46
    for nom, niveaux, textes in lignes:
        d.text((gauche, y + case / 2), nom, fill=TEXTE_2, font=_ajuster(nom, nom_l - 8, min(19, case // 2 + 2)),
               anchor="lm")
        for k, n in enumerate(niveaux):
            x = gauche + nom_l + k * pas
            boite = (x, y, x + case, y + case)
            if n is not None and n >= 2:
                d.rounded_rectangle(boite, radius=6, fill=CLASSES[n - 1])
            else:
                d.rounded_rectangle(boite, radius=6, outline=TRAIT, width=2)
            texte = "–" if n == 0 else (textes[k] if textes else "")
            if texte:
                d.text((x + case / 2, y + case / 2), texte, fill="#ffffff" if (n or 0) >= 3 else TEXTE_2,
                       font=police(min(16, case // 2), gras=True), anchor="mm")
        y += pas
    # Légende de la semaine.
    x, y = gauche, y + 12
    for n, mot in ((4, "bon"), (3, "par endroits"), (2, "possible")):
        d.rounded_rectangle((x, y, x + 18, y + 18), radius=4, fill=CLASSES[n - 1])
        d.text((x + 24, y + 9), mot, fill=TEXTE_2, font=police(16), anchor="lm")
        x += 24 + police(16).getlength(mot) + 22
    d.text((LARGEUR - 40, HAUTEUR - 26), NOM, fill=TEXTE_3, font=police(18, gras=True), anchor="rs")
    return img


def en_saison(lignes: list) -> list:
    """Les espèces en saison un jour de la semaine au moins ; toutes si aucune ne l'est."""
    return [l for l in lignes if any(n for n in l[1] if n)] or lignes


def ecrire(dossier: Path, departements: list[dict], rang: dict, especes: list[dict], resumes: dict,
           nat: dict, jours: list[date], codes: np.ndarray, pixel_dep: np.ndarray, echelle: int,
           seuils: list[float]) -> None:
    """`codes` : l'aperçu du jour, la meilleure espèce de chaque pixel ; `pixel_dep` : le rang du
    département de chaque pixel (-1 hors forêt), `rang` celui de chaque code de département."""
    dossier.mkdir(parents=True, exist_ok=True)
    cl = classes(codes, echelle, seuils)
    sous_titre = f"La semaine à partir du {date_longue(jours[0])}"
    carte_france(cl, VIGNETTE).save(dossier / "carte-france.png", optimize=True)
    france = carte_france(cl)
    lignes = []
    for x in especes:
        niv = nat[x["code"]]
        meilleurs = [max((n for n, v in j.items() if v), default=None) for j in niv]
        comptes = [str(len(j[4]) + len(j[3])) if j[4] or j[3] else "" for j in niv]
        lignes.append((x["nom"], meilleurs, comptes))
    image(NOM, sous_titre, france, "Aujourd'hui, toutes espèces : la meilleure de chaque forêt",
          en_saison(lignes), jours).save(dossier / "france.png", optimize=True)
    for dep in departements:
        dans = (pixel_dep == rang[dep["code"]]).reshape(cl.shape)
        if not dans.any():
            continue
        r = resumes.get(dep["code"]) or {}
        lignes = [(x["nom"], [(r.get(x["code"]) or [])[k]["niveau"] if k < len(r.get(x["code"]) or []) else None
                              for k in range(len(jours))], None) for x in especes]
        image(f"Champignons en {dep['nom']} ({dep['code']})", sous_titre, carte_departement(cl, dans),
              "Aujourd'hui, toutes espèces : la meilleure de chaque forêt", en_saison(lignes), jours
              ).save(dossier / f"{dep['code']}.png", optimize=True)
