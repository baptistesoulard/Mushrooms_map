"""Pages par département : phrases, tableau et garde-fous, sur des résumés fabriqués."""
import re
from datetime import date, timedelta

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
    assert '<meta name="robots" content="noindex, nofollow">' in page        # pas indexée tant qu'INDEXER est faux
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
    page = P.page_index(deps, ESPECES, r, "2026-11-01T05:20+00:00")
    assert [m for m in re.findall(r'href="(\w+)\.html"', page)] == ["19", "2A", "21"]
    assert "bon : cèpe et girolle" in page
