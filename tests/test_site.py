"""Garde-fous du site statique : liens, scripts, promesses des mentions."""
import re
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"
PAGES = sorted(SITE.glob("*.html"))


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_page_complete(page):
    html = page.read_text(encoding="utf-8")
    assert '<html lang="fr">' in html
    assert re.search(r"<title>[^<]{5,}</title>", html)
    assert re.search(r'<meta name="description" content="[^"]{60,}"', html)
    assert 'name="viewport"' in html


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_liens_internes_existent(page):
    html = page.read_text(encoding="utf-8")
    for cible in re.findall(r'(?:href|src)="([^"#:]+)"', html):
        if cible == "./":
            continue
        assert (SITE / cible).exists(), f"{page.name} → {cible} introuvable"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_aucun_script_tiers(page):
    """Leaflet est servi par le site ; seuls les fonds de carte viennent de l'IGN."""
    html = page.read_text(encoding="utf-8")
    assert not re.search(r'<script[^>]+src="https?://', html)
    assert not re.search(r'<link[^>]+href="https?://', html)


def test_stockage_navigateur_declare():
    """Toute clé localStorage du site est déclarée dans les mentions."""
    js = "\n".join(p.read_text(encoding="utf-8") for p in SITE.glob("*.js"))
    cles = set(re.findall(r'"(champi-[a-z-]+)"', js))
    mentions = (SITE / "a-propos.html").read_text(encoding="utf-8")
    assert cles, "la clé de l'espèce mémorisée a disparu ?"
    for c in cles:
        assert c in mentions


def test_carte_lit_les_fichiers_que_l_export_ecrit():
    js = (SITE / "carte.js").read_text(encoding="utf-8")
    export = (SITE.parent / "champi" / "export.py").read_text(encoding="utf-8")
    for f in ("carte.json", "especes.json", "attributs.png", "lieux.png"):
        assert f in js and f in export
    assert "data/indice/${cle}.png" in js and '"indice" / f"{esp.code}_{k}.png"' in export


def test_classes_de_couleur_alignees_sur_le_modele():
    """Une couleur CSS par classe visible (la première, « très faible », reste transparente)."""
    from champi.modele import CLASSES
    css = (SITE / "style.css").read_text(encoding="utf-8")
    assert len(set(re.findall(r"--classe-(\d):", css))) == len(CLASSES) - 1
