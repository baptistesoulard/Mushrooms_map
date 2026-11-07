"""Images de partage : couleurs du site, classes de l'indice, et des PNG de la bonne taille."""
import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from PIL import Image

from champi import especes as E
from champi import carte_departements, pages, partage
from champi.grille import Grille
from champi.modele import CLASSES

SITE = Path(__file__).resolve().parent.parent / "site"
JOURS = [date(2026, 11, 1) + timedelta(days=k) for k in range(8)]
SEUILS = [s for s, _ in CLASSES]


def test_couleurs_du_site():
    """Les images reprennent les couleurs de style.css : même fond, même échelle de l'indice."""
    css = (SITE / "style.css").read_text(encoding="utf-8")
    racine = css.split("@media")[0]
    jetons = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-f]{6});", racine))
    assert partage.CLASSES == [jetons[f"classe-{k}"] for k in range(1, len(CLASSES))]
    assert (partage.FOND, partage.TRAIT, partage.TEXTE) == (jetons["fond"], jetons["trait"], jetons["texte"])
    # La carte de l'accueil : les couleurs des verdicts de la carte des départements.
    for n, c in enumerate(partage.NIVEAUX_COULEURS):
        attendu = re.search(rf"\.carte-deps path\.n{n}[^{{]*\{{\s*fill:\s*([^;]+);", css).group(1).strip()
        assert c == (jetons[attendu[6:-1]] if attendu.startswith("var(") else attendu), n


def test_classes_comme_le_modele():
    codes = np.array([0, 19, 20, 49, 50, 80, 109, 110, 139, 140, 200, 251, 255])
    attendu = [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, -1, -1]     # seuils 0,10 · 0,25 · 0,40 · 0,55 · 0,70 ; hors forêt
    assert partage.classes(codes, 200, SEUILS).tolist() == attendu


def test_images(tmp_path):
    """La France et chaque département qui a de la forêt ; rien pour un département sans pixel."""
    especes = E.en_json()["especes"]
    deps = [{"code": "85", "nom": "Vendée"}, {"code": "01", "nom": "Ain"}, {"code": "2A", "nom": "Corse-du-Sud"}]
    rang = {"01": 0, "2A": 1, "85": 2}
    codes = np.full((60, 80), 251, dtype=np.uint8)
    codes[5:30, 5:40] = 150                                  # l'Ain : de bonnes conditions
    codes[35:55, 45:75] = 30                                 # la Vendée : faibles
    pixel_dep = np.full(codes.size, -1, dtype=np.int16).reshape(codes.shape)
    pixel_dep[5:30, 5:40], pixel_dep[35:55, 45:75] = 0, 2
    resumes = {"85": {"cepe": [{"niveau": n, "indice_moyen": 0.2, "part_bon": 0.0} for n in [1, 2, 3, 4, 4, 3, 2, 0]]}}
    nat = pages.national(especes, deps, resumes, 8)
    partage.ecrire(tmp_path, deps, rang, especes, resumes, nat, JOURS, codes, pixel_dep.ravel(), 200, SEUILS)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["01.png", "85.png", "carte-france.png", "france.png"]
    for nom in ("france.png", "85.png"):
        assert Image.open(tmp_path / nom).size == (partage.LARGEUR, partage.HAUTEUR)
    carte = Image.open(tmp_path / "carte-france.png")
    assert carte.width <= partage.VIGNETTE[0] and carte.height <= partage.VIGNETTE[1]


def test_carte_departement_agrandie_d_un_nombre_entier():
    cl = np.full((100, 100), -1, dtype=np.int8)
    cl[40:60, 30:50] = 4
    dans = np.zeros(cl.shape, dtype=bool)
    dans[40:60, 30:50] = True
    img = partage.carte_departement(cl, dans)
    assert img.width % 26 == 0 and img.height <= partage.CARTE[1]     # 20 pixels + 3 de marge de chaque côté


def test_cartes_de_l_accueil_sur_le_cadre_des_contours(tmp_path):
    """Les cartes de l'accueil (toutes espèces, puis chaque espèce) couvrent exactement le cadre
    des contours : chaque pixel prend la couleur du verdict du carré où tombe son centre ;
    « toutes » prend le meilleur verdict du carré."""
    cadre = [0.0, 0.0, 1000.0, 500.0]
    grille = Grille(-100.0, 600.0, 100.0, 12, 7)            # des carrés de 100 m, qui débordent du cadre
    cepe = np.full((7, 12), -1, dtype=np.int8)
    cepe[4, 5] = 4                                           # x 400-500, y 100-200 : bon
    girolle = np.full_like(cepe, -1)
    girolle[4, 5], girolle[1, 2] = 2, 0                      # possible ; hors saison en x 100-200, y 400-500
    deps = [{"code": "01", "nom": "Ain"}]
    especes = E.en_json()["especes"]
    partage.ecrire(tmp_path, deps, {"01": 0}, especes, {}, pages.national(especes, deps, {}, 8), JOURS,
                   np.full((7, 12), 251, dtype=np.uint8), np.full(84, -1, dtype=np.int16), 200, SEUILS,
                   une={"cepe": cepe, "girolle": girolle}, grille=grille, cadre=cadre)
    largeur = partage.LARGEUR_UNE * partage.NETTETE_UNE
    images = {n: np.asarray(Image.open(tmp_path / f"carte-france{n}.png").convert("RGB"))
              for n in ("", "-cepe", "-girolle")}
    assert all(im.shape == (largeur // 2, largeur, 3) for im in images.values())

    def couleur(im, x, y):                                   # le pixel qui couvre (x, y) m Mercator
        return tuple(im[int((500 - y) / 500 * im.shape[0]), int(x / 1000 * im.shape[1])])

    rgb = [partage._rgb(c) for c in partage.NIVEAUX_COULEURS]
    assert couleur(images["-cepe"], 450, 150) == rgb[4] and couleur(images["-girolle"], 450, 150) == rgb[2]
    assert couleur(images[""], 450, 150) == rgb[4] and couleur(images[""], 150, 450) == rgb[0]
    assert couleur(images["-cepe"], 150, 450) == partage._rgb(partage.FOND)     # pas de verdict : le fond
    assert couleur(images[""], 650, 150) == partage._rgb(partage.FOND)


def test_cadre_des_contours():
    """Le cadre Mercator des contours a les proportions du dessin : la carte de l'accueil peinte
    sur ce cadre a la forme du SVG posé dessus."""
    c = carte_departements.charger()
    x0, y0, x1, y1 = c["cadre"]
    assert abs((x1 - x0) / (y1 - y0) - c["largeur"] / c["hauteur"]) < 2e-3
    assert -600_000 < x0 < -500_000 and 6_600_000 < y1 < 6_700_000      # Pointe de Corsen, Bray-Dunes
    # Avec la marge : la viewBox et l'image de l'accueil gardent la même échelle.
    box, emprise = carte_departements.cadre_une(c)
    assert abs((emprise[2] - emprise[0]) / box[2] - (x1 - x0) / c["largeur"]) < 1e-6
    assert abs((emprise[3] - emprise[1]) / box[3] - (x1 - x0) / c["largeur"]) < 1e-2


def test_frontieres_entre_departements_seulement():
    """Les limites entre départements, sans le littoral : deux carrés voisins simplifiés chacun de
    son côté (leur limite commune décalée de 1 unité) ; seule la limite commune reste, tracée une
    fois, depuis le plus petit code."""
    traces = {"01": "M0 0l10 0 0 10 -10 0z", "02": "M11 0l10 0 0 10 -10 0z"}
    f = carte_departements.frontieres(traces)
    assert len(f) == 1
    (anneau,) = carte_departements.lire_traces(f[0])
    assert np.allclose(anneau[:, 0], 10) and sorted(anneau[:, 1].tolist()) == [0, 10]
    assert carte_departements.frontieres({"01": traces["01"]}) == []          # seul : aucun voisin
    assert carte_departements.frontieres(traces, tol=0.5) == []               # trop loin l'un de l'autre


def test_contours_fins_suivent_les_bords_entre_carres():
    """Les contours fins (carte de près) : la limite entre deux départements d'une grille suit le
    bord entre leurs carrés, d'un seul tenant ; le contour d'un département se referme."""
    grille = np.zeros((6, 8), dtype=np.int16)
    grille[1:5, 1:4], grille[1:5, 4:7] = 1, 2                  # deux rectangles côte à côte
    limite = carte_departements._chainer(carte_departements._bords(grille, lambda a, b: (a > 0) & (b > 0)))
    assert len(limite) == 1 and sorted(map(tuple, limite[0][[0, -1]])) == [(1.0, 4.0), (5.0, 4.0)]
    (tour,) = carte_departements._chainer(carte_departements._bords(grille, lambda a, b: (a == 1) | (b == 1)))
    assert np.array_equal(tour[0], tour[-1]) and len(tour) == 2 * (4 + 3) + 1
