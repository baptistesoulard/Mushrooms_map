"""Le calendrier des champignons (champi/pages_mois.py) : une page par mois, tirée des saisons des
règles (jamais une liste écrite à la main), et son sommaire."""
from datetime import date, timedelta

from champi import especes as E
from champi import pages
from champi import pages_mois as M

ESPECES = E.en_json()["especes"]
JOURS = [date(2026, 11, 14) + timedelta(days=k) for k in range(8)]
GENERE_LE = "2026-11-14T05:20+00:00"


def test_adresses_et_prepositions():
    assert pages.chemin_mois(2) == "calendrier/fevrier/" and pages.chemin_mois(8) == "calendrier/aout/"
    assert [pages.de_mois(m) for m in (4, 8, 10, 11)] == ["d'avril", "d'août", "d'octobre", "de novembre"]


def test_un_mois_suit_les_saisons_des_regles():
    """Chaque espèce paraît dans les mois où sa saison le dit, à sa place (pleine ou début/fin), et
    nulle part ailleurs ; la page relie la fiche de chaque espèce citée."""
    for m in range(1, 13):
        page = M.page_mois(m, ESPECES, JOURS, GENERE_LE, {})
        plein, possible = M.especes_du_mois(ESPECES, m)
        for x in ESPECES:
            classe = pages.mois_saison(x["saison"])[m - 1]
            assert (x in plein) == (classe == "plein") and (x in possible) == (classe == "possible"), (m, x["code"])
            lien = f'href="../../{pages.chemin_espece(x["code"])}"'
            assert (lien in page) == bool(classe), (m, x["code"])
        assert f"<title>Quels champignons chercher en {E_MOIS[m - 1]} ? Le calendrier de la cueillette</title>" in page
        assert "probabilit" not in page.lower() and "chance de trouver" not in page.lower()


def test_novembre_et_les_mois_creux():
    page = M.page_mois(11, ESPECES, JOURS, GENERE_LE, {})
    assert "<h1>Les champignons de novembre</h1>" in page and "<h2>En pleine saison</h2>" in page
    assert "Où chercher cette semaine" in page                           # le mois en cours
    assert 'href="../octobre/">‹ Les champignons d&#x27;octobre</a>' in page
    assert 'href="../decembre/">Les champignons de décembre ›</a>' in page
    # Un mois sans aucune espèce dit ce qui revient le mois suivant, d'après les règles.
    for m in range(1, 13):
        plein, possible = M.especes_du_mois(ESPECES, m)
        if not plein and not possible:
            creux = M.page_mois(m, ESPECES, JOURS, GENERE_LE, {})
            assert "aucune espèce de la carte n&#x27;est de saison" in creux
            # Au sud, seules les espèces dont la saison du modèle déborde vraiment sur ce mois.
            for x in ESPECES:
                cite = pages.article(x["de"]) in creux.split("Au sud", 1)[-1].split("</p>", 1)[0]
                assert cite == (x in M.finissent_au_sud(ESPECES, m)), (m, x["code"])
            apres = m % 12 + 1
            if any(int(x["saison"][0][:2]) == apres for x in ESPECES):
                assert f'href="../{M.slug_mois(apres)}/">les champignons' in creux


def test_sommaire():
    page = M.page_index(ESPECES, JOURS, GENERE_LE)
    for m in range(1, 13):
        assert f'<a href="{M.slug_mois(m)}/">' in page
    assert '<li class="actuel"><a href="novembre/">Novembre</a>' in page
    assert 'href="../calendrier/novembre/">nov.</a>' in page                # le tableau mène aux mois


E_MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre"]
