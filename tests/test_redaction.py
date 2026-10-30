from dataclasses import asdict
from datetime import date

from champi import especes as E
from champi import redaction as R

NBSP = " "


def _faits(**k):
    base = {"saison": 1.0, "part_bon": 0.0, "part_moyen": 0.0, "limitant": "aucun", "pluie_moy": 30.0,
            "meilleure_tranche": None, "froid_au_dessus": None, "chaud_en_dessous": None,
            "debut_saison": False}
    base.update(k)
    return base


def esp(code):
    return asdict(E.PAR_CODE[code])


def test_niveaux():
    assert R.niveau(_faits(saison=0)) == 0
    assert R.niveau(_faits(part_bon=0.2)) == 4
    assert R.niveau(_faits(part_bon=0.06)) == 3
    assert R.niveau(_faits(part_moyen=0.06)) == 2
    assert R.niveau(_faits()) == 1


def test_hors_saison_accorde_l_article():
    t = R.rediger(esp("morille"), _faits(saison=0))
    assert t["verdict"] == "Hors saison"
    assert t["phrases"][0].startswith("La saison de la morille court")
    assert "du 1er mars" in t["phrases"][0]
    assert R.rediger(esp("cepe"), _faits(saison=0))["phrases"][0].startswith("La saison du cèpe")


def test_froid_au_dessus_d_une_altitude():
    t = R.rediger(esp("cepe"), _faits(part_moyen=0.1, limitant="sol_froid", froid_au_dessus=1200,
                                      meilleure_tranche=[600, 800]))
    assert f"600{NBSP}m et 800{NBSP}m" in t["phrases"][0]
    assert f"au-dessus de 1{NBSP}200{NBSP}m" in t["phrases"][1]


def test_pluie_insuffisante_cite_le_seuil():
    t = R.rediger(esp("cepe"), _faits(limitant="pluie", pluie_moy=12.4))
    assert f"12{NBSP}mm" in t["phrases"][-1] and "environ 45" in t["phrases"][-1]


def test_jamais_de_zero_signe():
    assert R.nombre(-0.2) == "0"
    assert R.nombre(-0.04, 1) == "0,0"
    assert R.nombre(-3.5, 1) == "-3,5"
    assert R.nombre(1234) == f"1{NBSP}234"


def test_libelles_de_jours():
    a = date(2026, 10, 30)
    assert R.libelle_jour(a, a) == "aujourd'hui, vendredi 30 octobre"
    assert R.libelle_jour(date(2026, 10, 31), a) == "demain, samedi 31 octobre"
    assert R.libelle_jour(date(2026, 11, 1), a) == "dimanche 1er novembre"
