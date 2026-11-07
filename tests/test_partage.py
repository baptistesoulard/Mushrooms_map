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
    assert partage.FORET == jetons["foret-pale"]             # la légende de la carte de l'accueil


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
    des contours : un pixel de l'aperçu tombe dans le pixel de l'image qui couvre sa position."""
    cadre = [0.0, 0.0, 1000.0, 500.0]                       # 1 000 × 500 m : des pixels de 50 m
    grille = Grille(-100.0, 600.0, 10.0, 120, 70)           # l'aperçu déborde du cadre, pas de 10 m
    codes = np.full((grille.ny, grille.nx), 251, dtype=np.uint8)
    codes[30, 40] = 150                                      # centre (305, 295) : classe 5
    cepe = np.full_like(codes, 251)
    cepe[1, 1] = 150                                         # centre (-85, 585) : hors du cadre
    deps = [{"code": "01", "nom": "Ain"}]
    especes = E.en_json()["especes"]
    nat = pages.national(especes, deps, {}, 8)
    partage.ecrire(tmp_path, deps, {"01": 0}, especes, {}, nat, JOURS, codes,
                   np.full(codes.size, -1, dtype=np.int16), 200, SEUILS, par_espece={"cepe": cepe},
                   grille=grille, cadre=cadre)
    for nom in ("carte-france.png", "carte-france-cepe.png"):
        img = Image.open(tmp_path / nom).convert("RGB")
        assert img.size == (partage.LARGEUR_UNE, partage.LARGEUR_UNE // 2)
    toutes = np.asarray(Image.open(tmp_path / "carte-france.png").convert("RGB"))
    i, j = int(np.floor((500 - 295) / 500 * 280)), int(np.floor(305 / 1000 * 560))
    fonce = np.all(toutes == partage._rgb(partage.CLASSES[-1]), axis=-1)
    assert fonce[i, j] and fonce.sum() == 1
    assert not np.all(np.asarray(Image.open(tmp_path / "carte-france-cepe.png").convert("RGB"))
                      == partage._rgb(partage.CLASSES[-1]), axis=-1).any()


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
