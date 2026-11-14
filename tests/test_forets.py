"""Forêts publiques nommées : noms, contours, cases de l'échantillon, verdict, et leur place sur la
page d'un département — sur des forêts fabriquées (le fichier national vient du réseau)."""
from datetime import date, timedelta

import numpy as np

from champi import forets as F
from champi import pages_departements as P
from champi.grille import merc_vers_lonlat

JOURS = [date(2026, 11, 1) + timedelta(days=k) for k in range(8)]
ESPECES = [{"code": "cepe", "nom": "Cèpe", "de": "du cèpe", "latin": "Boletus edulis"},
           {"code": "girolle", "nom": "Girolle", "de": "de la girolle", "latin": "Cantharellus cibarius"}]


def test_noms_propres_et_courts():
    assert F.nom_propre("Forêt Domaniale de Mervent") == "Forêt domaniale de Mervent"
    assert F.nom_propre("Forêt  Départementale d'Aizenay ") == "Forêt départementale d'Aizenay"
    assert F.nom_propre("Forêt du Hâvre du Payré") == "Forêt du Hâvre du Payré"
    assert P.nom_court("Forêt domaniale des Pays de Monts") == "des Pays de Monts"
    assert P.nom_court("Forêt domaniale d'Olonne") == "d'Olonne"
    assert P.nom_court("Massif de la Chartreuse") == "Massif de la Chartreuse"


def test_contours_encodes_et_points_dedans():
    """Un carré de 10 km percé d'un trou de 4 km : la règle pair-impair laisse le trou dehors."""
    exterieur = np.array([[0, 0], [10_000, 0], [10_000, 10_000], [0, 10_000], [0, 0]], dtype=float)
    trou = np.array([[3_000, 3_000], [7_000, 3_000], [7_000, 7_000], [3_000, 7_000], [3_000, 3_000]], dtype=float)
    anneaux = [F.decoder(F._encoder(a)) for a in (exterieur, trou)]
    assert np.allclose(anneaux[1], trou)
    px = np.array([1_000, 5_000, 9_000, 11_000], dtype=float)
    py = np.array([1_000, 5_000, 9_500, 5_000], dtype=float)
    assert F.dedans(px, py, anneaux).tolist() == [True, False, True, False]


def test_affecter_les_cases_et_le_departement():
    """Les cases libres dans la forêt, son département (la majorité), et rien sous POINTS_MIN cases."""
    x0, y0 = 100_000.0, 5_900_000.0
    carre = np.array([[x0, y0], [x0 + 3_000, y0], [x0 + 3_000, y0 + 3_000], [x0, y0 + 3_000], [x0, y0]])
    xs, ys = np.meshgrid(np.arange(x0 - 1_000, x0 + 4_000, 290.0), np.arange(y0 - 1_000, y0 + 4_000, 290.0))
    lon, lat = merc_vers_lonlat(xs.ravel(), ys.ravel())
    dep = np.where(xs.ravel() < x0 + 2_500, 3, 7).astype(np.int16)
    libre = np.ones(len(lon), dtype=bool)
    libre[0] = False
    foret = {"id": "F1", "nom": "Forêt domaniale d'Essai", "nature": "domaniale", "ha": 900,
             "anneaux": [F._encoder(carre)]}
    petite = dict(foret, id="F2", anneaux=[F._encoder(carre[:, :] * 0 + [[x0, y0], [x0 + 300, y0],
                                                                          [x0 + 300, y0 + 300], [x0, y0 + 300],
                                                                          [x0, y0]])])
    r = F.affecter([foret, petite], np.asarray(lat), np.asarray(lon), dep, libre)
    assert [f["id"] for f in r] == ["F1"]
    pts = r[0]["points"]
    assert 90 <= len(pts) <= 120 and r[0]["departement"] == 3          # ~3 km / 290 m = ~10 × 10 cases


def test_verdict_d_une_foret():
    from champi import especes as E
    from champi.export_france import verdict_foret
    cepe = next(e for e in E.ESPECES if e.code == "cepe")
    km2 = np.full(100, 0.04)
    bon = verdict_foret(cepe, date(2026, 10, 1), 45.0, np.full(100, 0.9), km2)
    assert bon["niveau"] == 4 and bon["part_bon"] == 1.0
    rien = verdict_foret(cepe, date(2026, 10, 1), 45.0, np.zeros(100), km2)
    assert rien["niveau"] == 1
    hors = verdict_foret(cepe, date(2026, 2, 1), 45.0, np.full(100, 0.9), km2)
    assert hors["niveau"] == 0


def jours_foret(niveaux, part=0.5):
    return [{"niveau": n, "part_bon": part if n >= 3 else 0.0, "indice_moyen": n / 4} for n in niveaux]


def test_section_et_questions_des_forets():
    forets = [
        {"id": "a", "nom": "Forêt domaniale de Mervent", "nature": "domaniale", "ha": 2548,
         "especes": {"cepe": jours_foret([4] * 8), "girolle": jours_foret([1] * 8)}},
        {"id": "b", "nom": "Forêt départementale d'Aizenay", "nature": "autre", "ha": 235,
         "especes": {"cepe": jours_foret([1, 1, 3, 1, 1, 1, 1, 1]), "girolle": jours_foret([1] * 8)}},
        {"id": "c", "nom": "Forêt domaniale des Pays de Monts", "nature": "domaniale", "ha": 2301,
         "especes": {"cepe": jours_foret([3] * 8, 0.1), "girolle": jours_foret([1] * 8)}},
    ]
    classees = P.classer_forets(forets, ESPECES)
    assert [f["id"] for f, _, _ in classees] == ["a", "c", "b"]
    html = "\n".join(P.section_forets(forets, ESPECES, JOURS, "en Vendée"))
    assert "<h2>Où chercher en Vendée : les forêts publiques</h2>" in html
    assert ('<th scope="row">Forêt domaniale de Mervent<span class="cl">2 548 ha</span></th>'
            "<td>Cèpe : bon</td><td>dim. 1 : cèpe, bon</td>") in html
    assert "<td>rien de favorable</td><td>mar. 3 : cèpe, par endroits</td>" in html
    assert P._statut({"nom": "Forêt du Hâvre du Payré", "nature": "autre"}) == "publique"
    assert P._statut({"nom": "Forêt départementale d'Aizenay", "nature": "autre"}) == ""
    r = {"cepe": [{"niveau": 4, "verdict": "Bonnes conditions", "phrases": [], "indice_moyen": 1.0,
                   "communes": [{"nom": "Mervent"}]}] * 8,
         "girolle": [{"niveau": 1, "verdict": "Conditions défavorables", "phrases": [], "indice_moyen": 0.2,
                      "communes": []}] * 8}
    qr = dict(P.questions({"code": "85", "nom": "Vendée"}, ESPECES, r, JOURS, "2026-11-01T05:20+00:00", forets))
    assert ("Parmi les forêts publiques, les mieux placées aujourd'hui sont la forêt domaniale de Mervent "
            "(cèpe, bon) et la forêt domaniale des Pays de Monts (cèpe, par endroits).") in qr["Où chercher des champignons en Vendée ?"]
    page = P.page_departement({"code": "85", "nom": "Vendée"}, ESPECES, r, JOURS, "2026-11-01T05:20+00:00",
                              forets=forets)
    assert "les forêts de Mervent, des Pays de Monts et d&#x27;Aizenay" in page     # la description
    # Les champignons de la semaine d'abord, les forêts publiques ensuite (demande du 2026-11-14).
    assert (page.index("<h2>La semaine, espèce par espèce</h2>") < page.index('<section class="carte-espece">')
            < page.index("<h2>Où chercher en Vendée : les forêts publiques</h2>")
            < page.index("<h2>Questions fréquentes</h2>"))
    assert '"mentions":[{"@type":"Place","name":"Forêt domaniale de Mervent"}' in page
