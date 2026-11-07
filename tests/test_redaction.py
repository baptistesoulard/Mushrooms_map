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
    assert R.niveau(_faits(part_bon=0.35)) == 4
    assert R.niveau(_faits(part_bon=0.2)) == 3            # « par endroits » jusqu'à 30 % de la forêt
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


def test_fiabilite_suit_l_intervalle_de_l_ecart():
    assert R.fiabilite({"ic_ecart": [0.01, 0.1]})["sens"] == "mieux"
    assert R.fiabilite({"ic_ecart": [-0.2, -0.05]})["sens"] == "moins"
    assert R.fiabilite({"ic_ecart": [-0.05, 0.02]})["sens"] == "pareil"
    assert R.fiabilite({"n": 4})["sens"] == "inconnu"
    assert "moins bien" in R.fiabilite({"ic_ecart": [-0.2, -0.05]})["texte"]


def test_libelles_de_jours():
    a = date(2026, 10, 30)
    assert R.libelle_jour(a, a) == "aujourd'hui, vendredi 30 octobre"
    assert R.libelle_jour(date(2026, 10, 31), a) == "demain, samedi 31 octobre"
    assert R.libelle_jour(date(2026, 11, 1), a) == "dimanche 1er novembre"


def test_sol_qui_freine_sans_contredire_le_verdict():
    """Sous le seuil, le sol freine l'indice sans le fermer : quand le verdict reste bon,
    « trop froid » le contredirait (vu le 2026-10-31 : « Bonnes conditions » puis « trop froid
    presque partout »). Contre-épreuve : verdict défavorable, « trop » reste juste."""
    bon = R.rediger(esp("trompette"), _faits(part_bon=0.35, limitant="sol_froid"))
    assert bon["verdict"] == "Bonnes conditions"
    assert "trop" not in bon["phrases"][-1] and "frais presque partout" in bon["phrases"][-1]
    mauvais = R.rediger(esp("trompette"), _faits(limitant="sol_froid"))
    assert "trop froid presque partout" in mauvais["phrases"][-1]
    chaud = R.rediger(esp("cepe"), _faits(part_bon=0.06, limitant="sol_chaud"))
    assert "trop" not in chaud["phrases"][-1] and "chaud presque partout" in chaud["phrases"][-1]
    assert "trop chaud" in R.rediger(esp("cepe"), _faits(limitant="sol_chaud"))["phrases"][-1]


def test_les_pres_ont_leurs_mots():
    pre = {**esp("cepe"), "milieu": "pre"}
    r = R.rediger(pre, _faits(limitant="pluie", pluie_moy=8))
    assert "sur les prés" in r["phrases"][-1] and "forêts" not in " ".join(r["phrases"])
