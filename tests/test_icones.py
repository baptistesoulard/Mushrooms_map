"""Le logo (champi/icones.py) : une seule géométrie pour la barre, le favicon et les icônes."""
from pathlib import Path

from PIL import Image

from champi import icones as I
from champi import pages

SITE = Path(__file__).resolve().parent.parent / "site"


def test_favicon_et_icones_a_jour():
    """`python -m champi.icones` a été relancé après le dernier changement du logo."""
    assert (SITE / "favicon.svg").read_text(encoding="utf-8") == I.svg_marque(page=False)
    for nom, taille in (("icone-180.png", 180), ("icone-192.png", 192), ("icone-512.png", 512),
                        ("icone-masquable-512.png", 512)):
        assert Image.open(SITE / nom).size == (taille, taille), nom


def test_logo_de_la_barre_aux_couleurs_du_theme():
    barre = pages.barre("", "methode.html")
    assert '<svg class="marque-logo"' in barre and 'class="marque-chapeau"' in barre
    assert '<span class="marque-nom">Champi<span>météo</span></span>' in barre
    assert "fill=" not in I.svg_marque()            # les couleurs viennent de style.css (clair, sombre)


def test_chemins_echantillonnes():
    pts = I.points(I.GOUTTE, pas=8)
    assert pts[0] == (32.0, 2.5) and len(pts) == 1 + 4 * 8
    assert all(0 <= x <= 64 and 0 <= y <= 64 for x, y in pts)
    im = I.dessiner(64, part=1)
    couleur = lambda c: tuple(int(c[k:k + 2], 16) for k in (1, 3, 5))     # noqa: E731
    assert im.size == (64, 64)
    assert im.getpixel((32, 16))[:3] == couleur(I.BRUN)                  # la goutte
    assert im.getpixel((32, 32))[:3] == couleur(I.CHAPEAU_C)             # le chapeau, en réserve
    assert im.getpixel((32, 50))[:3] == couleur(I.PIED_C)                # le pied
