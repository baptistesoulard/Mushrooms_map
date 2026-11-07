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
    assert "<title>Où trouver des champignons en Vendée (85) : la semaine du 1er novembre</title>" in page
    assert "<h1>Où trouver des champignons en Vendée cette semaine</h1>" in page
    assert '<header class="bandeau">' in page and '<p class="sur-titre">Département · 85</p>' in page
    assert '<p class="en-bref">Aujourd&#x27;hui, bonnes conditions pour le cèpe.</p>' in page
    assert '<footer class="pied-site">' in page                              # le pied commun
    assert "Calculé le dimanche 1er novembre 2026 à 6 h 20" in page          # heure de Paris, heure d'hiver
    assert len(re.findall(r'<a class="niveau n\w"', page)) == 3 * 8
    assert 'href="../../carte/?departement=85&amp;espece=cepe&amp;jour=2026-11-03"' in page   # sous /carte/
    assert "Saint-&lt;Mesmin&gt;" in page and "<Mesmin>" not in page        # échappé
    assert "Aucun jour favorable cette semaine." in page                     # la girolle
    girolle = page.split('>Girolle</a> ')[1].split("</section>")[0]
    assert "Communes les mieux placées" not in girolle                       # rien de favorable ce jour-là
    assert '<h3><a href="../../especes/cepe/">Cèpe</a>' in page             # chaque espèce mène à sa fiche


def test_donnees_structurees_du_departement():
    """Le fil d'Ariane et les questions fréquentes : celles des données structurées sont, mot pour
    mot, celles écrites dans la page."""
    import html
    import json
    r = resumes([4] * 8, [3] * 8, [0] * 8)
    page = P.page_departement({"code": "40", "nom": "Landes"}, ESPECES, r, JOURS, "2026-11-01T05:20+00:00")
    graphe = json.loads(re.search(r'<script type="application/ld\+json">(.+?)</script>', page).group(1))["@graph"]
    types = {g["@type"]: g for g in graphe}
    assert set(types) == {"WebPage", "BreadcrumbList", "FAQPage"}
    assert [x["name"] for x in types["BreadcrumbList"]["itemListElement"]] == [pages.NOM, "Départements", "Landes"]
    assert types["BreadcrumbList"]["itemListElement"][2]["item"] == f"{pages.ADRESSE}departements/landes/"
    faq = page.split('<section class="faq">')[1].split("</section>")[0]
    visibles = [(html.unescape(q), html.unescape(rep))
                for q, rep in re.findall(r"<h3>(.+?)</h3>\n  <p>(.+?)</p>", faq)]
    attendues = [(q["name"], q["acceptedAnswer"]["text"]) for q in types["FAQPage"]["mainEntity"]]
    assert visibles == attendues and len(attendues) == 4
    assert attendues[0][0] == "Y a-t-il des champignons en ce moment dans les Landes ?"
    assert attendues[0][1].startswith("Aujourd'hui, bonnes conditions pour le cèpe.")
    assert "Pouzauges, Mauléon" in attendues[1][1] or "Pouzauges et Mauléon" in attendues[1][1]
    assert "probabilit" not in page.lower() and "chance de trouver" not in page.lower()


def test_chiffres_de_tete():
    r = resumes([2, 2, 4, 4, 2, 2, 2, 2], [1] * 8, [0] * 8)
    for j in r["cepe"]:
        j.update(part_bon=0.34, km2=503.0)
    esp = [dict(ESPECES[0], habituel=0.7), *ESPECES[1:]]
    assert P.chiffres(esp, r, JOURS) == [
        ("Le mieux placé aujourd'hui", "Cèpe", "Pousse possible, sans plus"),
        ("Forêt aux bonnes conditions", "34 %", "des 503 km² de forêt, pour le cèpe"),
        ("Meilleur jour de la semaine", "Mardi 3 novembre", "Cèpe : bon"),
        ("D'habitude à cette date", "7 années sur 10", "en France, la météo du cèpe est favorable"),
    ]
    hors = resumes([0] * 8, [0] * 8, [0] * 8)
    assert P.chiffres(ESPECES, hors, JOURS) == [("Aujourd'hui", "Hors saison", "pour toutes les espèces suivies")]


def test_voisins_et_prepositions():
    r = resumes([4] * 8, [1] * 8, [0] * 8)
    voisins = [({"code": "44", "nom": "Loire-Atlantique"}, resumes([1] * 8, [3] * 8, [0] * 8)),
               ({"code": "79", "nom": "Deux-Sèvres"}, resumes([1] * 8, [1] * 8, [0] * 8))]
    page = P.page_departement({"code": "85", "nom": "Vendée"}, ESPECES, r, JOURS, "2026-11-01T05:20+00:00", voisins)
    assert '<li><a href="../loire-atlantique/">Loire-Atlantique (44)</a> : par endroits pour la girolle</li>' in page
    assert '<li><a href="../deux-sevres/">Deux-Sèvres (79)</a> : rien de favorable aujourd&#x27;hui</li>' in page
    assert [pages.dans(c, n) for c, n in (("85", "Vendée"), ("40", "Landes"), ("01", "Ain"), ("75", "Paris"),
                                          ("83", "Var"), ("26", "Drôme"))] == \
        ["en Vendée", "dans les Landes", "dans l'Ain", "à Paris", "dans le Var", "dans la Drôme"]


def test_voisins_des_contours():
    """Les départements qui se touchent, tirés des contours versionnés : un coin commun ne compte pas."""
    from champi import carte_departements as C
    v = C.voisins(C.charger()["traces"])
    assert v["85"] == ["17", "44", "49", "79"] and v["2A"] == ["2B"] and v["75"] == ["92", "93", "94"]
    assert all(c in v[w] for c, l in v.items() for w in l)                  # symétrique


def test_index_par_numero():
    deps = [{"code": c, "nom": n} for c, n in (("21", "Côte-d'Or"), ("2A", "Corse-du-Sud"), ("19", "Corrèze"))]
    r = {d["code"]: resumes([4] * 8, [4] * 8, [0] * 8) for d in deps}
    page = P.page_index(deps, ESPECES, r, JOURS, "2026-11-01T05:20+00:00")
    assert re.findall(r'<li><a href="([\w-]+)/">', page) == ["correze", "corse-du-sud", "cote-d-or"]
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
    assert re.findall(r'<a href="[\w-]+/" data-dep="(\w+)"><path class="n(\w)"', page) == \
        [("19", "3"), ("2A", "2"), ("21", "4")]                       # le cèpe, le mieux placé aujourd'hui
    assert donnees_pages(page)["21"] == "cote-d-or/"                  # pages.js : les liens du classement
    donnees = json.loads(re.search(r'<script type="application/json" id="niveaux-deps">(.+?)</script>', page).group(1))
    assert donnees["defaut"] == "cepe" and donnees["ordre"] == ["19", "2A", "21"]
    assert donnees["especes"]["cepe"]["niveaux"][:2] == ["324", "424"]
    assert donnees["especes"]["girolle"]["niveaux"][0] == "031"
    assert '<strong>Bonnes conditions</strong> (1) : <a href="cote-d-or/">Côte-d&#x27;Or</a>' in page


def donnees_pages(page: str) -> dict:
    import json
    return json.loads(re.search(r'<script type="application/json" id="niveaux-deps">(.+?)</script>', page).group(1))["pages"]


def test_adresses_lisibles_et_renvois(tmp_path):
    """Les pages vivent à une adresse lisible (departements/vendee/) ; l'ancienne (departements/85.html)
    renvoie aussitôt à la nouvelle, sans être indexée, et dit aux moteurs où est la page."""
    assert pages.slug("Côte-d'Or") == "cote-d-or" and pages.slug("Territoire de Belfort") == "territoire-de-belfort"
    assert pages.chemin_departement("85", "Vendée") == "departements/vendee/"
    assert pages.chemin_espece("pied_de_mouton") == "especes/pied-de-mouton/"
    deps = [{"code": "85", "nom": "Vendée"}, {"code": "2A", "nom": "Corse-du-Sud"}]
    r = {d["code"]: resumes([4] * 8, [1] * 8, [0] * 8) for d in deps}
    chemins = P.ecrire(tmp_path, deps, ESPECES, r, JOURS, "2026-11-01T05:20+00:00")
    assert chemins == ["departements/", "departements/vendee/", "departements/corse-du-sud/"]
    assert (tmp_path / "departements" / "vendee" / "index.html").exists()
    ancien = (tmp_path / "departements" / "85.html").read_text(encoding="utf-8")
    assert '<meta http-equiv="refresh" content="0; url=vendee/">' in ancien
    assert f'<link rel="canonical" href="{pages.ADRESSE}departements/vendee/">' in ancien
    assert '<meta name="robots" content="noindex, follow">' in ancien
