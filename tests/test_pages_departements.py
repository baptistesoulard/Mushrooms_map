"""Pages par département : phrases, tableau et garde-fous, sur des résumés fabriqués."""
import re
from datetime import date, timedelta

from champi import pages
from champi import pages_departements as P

JOURS = [date(2026, 11, 1) + timedelta(days=k) for k in range(8)]
ESPECES = [
    {"code": "cepe", "nom": "Cèpe", "de": "du cèpe", "latin": "Boletus edulis"},
    {"code": "girolle", "nom": "Girolle", "de": "de la girolle", "latin": "Cantharellus cibarius"},
    {"code": "morille", "nom": "Morille", "de": "de la morille", "latin": "Morchella spp."},
]
VERDICTS = ["Hors saison", "Conditions défavorables", "Pousse possible, sans plus",
            "Bonnes conditions par endroits", "Bonnes conditions"]


def jour(niveau, communes=("Pouzauges", "Mauléon")):
    return {"niveau": niveau, "verdict": VERDICTS[niveau], "phrases": ["Une phrase."], "indice_moyen": niveau / 4,
            "communes": [{"nom": c} for c in communes]}


def resumes(cepe, girolle, morille):
    return {"cepe": [jour(n) for n in cepe], "girolle": [jour(n) for n in girolle],
            "morille": [jour(n) for n in morille]}


def test_articles_et_enumeration():
    assert P.article("du cèpe") == "le cèpe" and P.article("de la girolle") == "la girolle"
    assert P.enumerer(["a"]) == "a" and P.enumerer(["a", "b", "c"]) == "a, b et c"


def test_synthese():
    r = resumes([4] * 8, [1, 1, 2, 4, 4, 3, 3, 3], [0] * 8)
    assert P.synthese(ESPECES, r, JOURS) == [
        "Aujourd'hui, bonnes conditions pour le cèpe.",
        "Dans la semaine, bonnes conditions aussi pour la girolle (dès mercredi 4 novembre).",
        "Hors saison toute la semaine : la morille.",
    ]
    rien = resumes([1] * 8, [3] * 8, [0] * 8)
    assert P.synthese(ESPECES, rien, JOURS)[0] == "Aujourd'hui, bonnes conditions par endroits pour la girolle."


def test_page_departement():
    r = resumes([4] * 8, [1] * 8, [0] * 8)
    r["cepe"][0]["communes"] = [{"nom": "Saint-<Mesmin>"}]
    page = P.page_departement({"code": "85", "nom": "Vendée"}, ESPECES, r, JOURS, "2026-11-01T05:20+00:00")
    assert f'<meta name="robots" content="{"index, follow" if pages.INDEXER else "noindex, nofollow"}">' in page
    assert "<title>Champignons en Vendée (85) : les conditions de la semaine</title>" in page
    assert "Calculé le dimanche 1er novembre 2026 à 6 h 20" in page          # heure de Paris, heure d'hiver
    assert len(re.findall(r'<a class="niveau n\w"', page)) == 3 * 8
    assert 'href="../carte/?departement=85&amp;espece=cepe&amp;jour=2026-11-03"' in page   # la carte, sous /carte/
    assert "Saint-&lt;Mesmin&gt;" in page and "<Mesmin>" not in page        # échappé
    assert "Aucun jour favorable cette semaine." in page                     # la girolle
    girolle = page.split("<h3>Girolle ")[1].split("</section>")[0]
    assert "Communes les mieux placées" not in girolle                       # rien de favorable ce jour-là


def test_index_par_numero():
    deps = [{"code": c, "nom": n} for c, n in (("21", "Côte-d'Or"), ("2A", "Corse-du-Sud"), ("19", "Corrèze"))]
    r = {d["code"]: resumes([4] * 8, [4] * 8, [0] * 8) for d in deps}
    page = P.page_index(deps, ESPECES, r, JOURS, "2026-11-01T05:20+00:00")
    assert [m for m in re.findall(r'href="(\w+)\.html"', page)] == ["19", "2A", "21"]
    assert "bon : cèpe et girolle" in page


def test_carte_des_departements():
    """Chaque département est un lien coloré au verdict de l'espèce du moment ; les données du
    choix (espèce, jour) suivent l'ordre des tracés."""
    import json
    deps = [{"code": c, "nom": n} for c, n in (("21", "Côte-d'Or"), ("2A", "Corse-du-Sud"), ("19", "Corrèze"))]
    r = {"21": resumes([4] * 8, [1] * 8, [0] * 8), "2A": resumes([2] * 8, [3] * 8, [0] * 8),
         "19": resumes([3] + [4] * 7, [0] * 8, [0] * 8)}
    contours = {"largeur": 100, "hauteur": 90, "traces": {"21": "M1 1l1 0 0 1z", "2A": "M5 5l1 0 0 1z",
                                                          "19": "M9 9l1 0 0 1z"}}
    page = P.page_index(deps, ESPECES, r, JOURS, "2026-11-01T05:20+00:00", contours)
    assert re.findall(r'<a href="(\w+)\.html" data-dep="\1"><path class="n(\w)"', page) == \
        [("19", "3"), ("2A", "2"), ("21", "4")]                       # le cèpe, le mieux placé aujourd'hui
    donnees = json.loads(re.search(r'<script type="application/json" id="niveaux-deps">(.+?)</script>', page).group(1))
    assert donnees["defaut"] == "cepe" and donnees["ordre"] == ["19", "2A", "21"]
    assert donnees["especes"]["cepe"]["niveaux"][:2] == ["324", "424"]
    assert donnees["especes"]["girolle"]["niveaux"][0] == "031"
    assert '<strong>Bonnes conditions</strong> (1) : <a href="21.html">Côte-d&#x27;Or</a>' in page
