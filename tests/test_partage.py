"""Images de partage : couleurs du site, classes de l'indice, et des PNG de la bonne taille."""
import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from PIL import Image

from champi import especes as E
from champi import pages, partage
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
