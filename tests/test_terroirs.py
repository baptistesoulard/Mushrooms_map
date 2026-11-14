"""Les portraits des départements (champi/terroirs.py) : dix départements, un texte qui ne change
pas d'un jour à l'autre, après les champignons de la semaine et avant les forêts publiques."""
import json
from pathlib import Path

from champi import pages_departements as P
from champi.terroirs import TERROIRS
from test_pages_departements import ESPECES, JOURS, resumes

DEPARTEMENTS = json.loads((Path(__file__).resolve().parent.parent / "data" / "departements.json")
                          .read_text(encoding="utf-8"))


def test_dix_portraits_complets():
    assert len(TERROIRS) == 10 and set(TERROIRS) <= set(DEPARTEMENTS)
    for code, t in TERROIRS.items():
        assert t.forets and t.especes and t.ou and t.savoir, code
        texte = repr(t).lower()
        assert "probabilit" not in texte and "chance" not in texte, code


def test_le_portrait_sur_la_page():
    r = resumes([4] * 8, [1] * 8, [0] * 8)
    page = P.page_departement({"code": "74", "nom": "Haute-Savoie"}, ESPECES, r, JOURS, "2026-11-01T05:20+00:00")
    titre = "<h2>Les champignons en Haute-Savoie : forêts, espèces, saisons</h2>"
    assert titre in page and "<strong>Bon à savoir.</strong>" in page and "renseignez-vous en mairie" in page
    assert (page.index("<h2>La semaine, espèce par espèce</h2>") < page.index('<section class="carte-espece">')
            < page.index(titre) < page.index("<h2>Questions fréquentes</h2>"))
    sans = P.page_departement({"code": "85", "nom": "Vendée"}, ESPECES, r, JOURS, "2026-11-01T05:20+00:00")
    assert "forêts, espèces, saisons</h2>" not in sans                      # pas de portrait : rien
