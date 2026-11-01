"""Garde-fous du site statique : liens, scripts, promesses des mentions."""
import re
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"
# Les pages versionnées ; l'accueil (index.html) est écrit chaque matin par l'export, hors git.
PAGES = sorted(p for p in [*SITE.glob("*.html"), *SITE.glob("carte/*.html")] if p != SITE / "index.html")
# Écrits chaque matin par l'export (champi/pages*.py), hors git : vérifiés par tests/test_pages_accueil.py.
GENERES = {"departements", "especes", "en-ce-moment.html", "index.html"}


def nom(p):
    return p.relative_to(SITE).as_posix()


def liens(page: Path) -> list[Path]:
    """Les liens et sources internes d'une page, résolus comme le navigateur (avec sa `<base>`)."""
    html = page.read_text(encoding="utf-8")
    base = re.search(r'<base href="([^"]+)">', html)
    dossier = page.parent / base.group(1) if base else page.parent
    html = re.sub(r"<base [^>]+>", "", html)
    return [(dossier / c).resolve() for c in re.findall(r'(?:href|src)="([^"#:?]+)["#?]', html)]


@pytest.mark.parametrize("page", PAGES, ids=nom)
def test_page_complete(page):
    html = page.read_text(encoding="utf-8")
    assert '<html lang="fr">' in html
    assert re.search(r"<title>[^<]{5,}</title>", html)
    assert re.search(r'<meta name="description" content="[^"]{60,}"', html)
    assert 'name="viewport"' in html


@pytest.mark.parametrize("page", PAGES, ids=nom)
def test_liens_internes_existent(page):
    for cible in liens(page):
        rel = cible.relative_to(SITE).as_posix() if cible.is_relative_to(SITE) else str(cible)
        if rel.split("/")[0] in GENERES or cible == SITE:
            continue
        assert cible.exists(), f"{nom(page)} → {rel} introuvable"


def test_la_carte_charge_tout_depuis_la_racine():
    """Sous /carte/, la carte garde ses fichiers à la racine : scripts, données, habitat, appli."""
    carte = SITE / "carte" / "index.html"
    assert '<base href="../">' in carte.read_text(encoding="utf-8")
    assert all(c.is_relative_to(SITE) and c.parent != SITE / "carte" for c in liens(carte))


@pytest.mark.parametrize("page", PAGES, ids=nom)
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


def test_l_appli_hors_ligne_garde_tous_les_scripts():
    """Un module oublié dans la coquille de sw.js, et la carte ne s'ouvre plus sans réseau."""
    coquille = re.search(r"const COQUILLE = \[(.*?)\];", (SITE / "sw.js").read_text(encoding="utf-8"), re.S).group(1)
    for js in SITE.glob("*.js"):
        if js.name != "sw.js":
            assert f'"{js.name}"' in coquille, js.name


def test_carte_lit_les_fichiers_que_l_export_ecrit():
    js = (SITE / "carte.js").read_text(encoding="utf-8")
    export = (SITE.parent / "champi" / "export_france.py").read_text(encoding="utf-8")
    france = (SITE.parent / "champi" / "france.py").read_text(encoding="utf-8")
    for f in ("carte.json", "especes.json"):
        assert f in js and f in export
    assert "data/apercu/${cle}.png" in js and '"apercu" / f"{esp.code}_{k}.png"' in export
    assert "data/meteo/${nom}.bin" in js and '"meteo"' in export and 'f"{nom}.bin"' in export
    assert "data/resumes/${dep}.json" in js and """"resumes" / f"{dep['code']}.json\"""" in export
    assert "habitat/blocs/${nom}_${l}.png" in js and '"blocs" / f"{nom}_{lettre}.png"' in france
    for f in ("communes.json", "blocs.json"):
        assert f"habitat/{f}" in js and f in france


@pytest.mark.parametrize("page", PAGES, ids=nom)
def test_site_personnel_non_indexe(page):
    """Publié à 50 m pour un usage personnel : jamais indexé (CLAUDE.md)."""
    assert '<meta name="robots" content="noindex, nofollow">' in page.read_text(encoding="utf-8")


def test_classes_de_couleur_alignees_sur_le_modele():
    """Une couleur CSS par classe visible (la première, « très faible », reste transparente)."""
    from champi.modele import CLASSES
    css = (SITE / "style.css").read_text(encoding="utf-8")
    assert len(set(re.findall(r"--classe-(\d):", css))) == len(CLASSES) - 1
