"""Ce qui est habituel à cette date : décades, comptage des jours favorables, mots."""
from datetime import date

import numpy as np

from champi import climatologie as C
from champi import especes as E


def test_trois_decades_par_mois():
    assert [C.decade(date(2026, 1, j)) for j in (1, 10, 11, 20, 21, 31)] == [0, 0, 1, 1, 2, 2]
    assert C.decade(date(2026, 11, 2)) == 30 and C.decade(date(2026, 12, 31)) == 35


def test_avec_une_meteo_ideale_la_frequence_suit_la_saison():
    """Pluie, sol et gel toujours parfaits : favorable tous les jours de la pleine saison du
    pied-de-mouton (jusqu'au 15 novembre à 46° N), jamais hors saison, de moins en moins en
    décembre."""
    serie = {"debut": "2025-01-01", "altitude": 300.0,
             "precipitation_sum": np.full(365, 4.0, dtype=np.float32),
             "temperature_2m_min": np.full(365, 5.0, dtype=np.float32),
             "soil_temperature_0_to_7cm_mean": np.full(365, 10.0, dtype=np.float32)}
    pied = next(e for e in E.ESPECES if e.code == "pied_de_mouton")
    f = C.calculer({(46.0, 6.0, 2025): serie}, [pied])["pied_de_mouton"]
    assert f[C.decade(date(2025, 11, 1))] == 1.0 and f[C.decade(date(2025, 9, 15))] == 1.0
    assert f[C.decade(date(2025, 2, 1))] == 0.0
    assert f[32] >= f[33] >= f[34] and f[34] < 0.5


def test_la_frequence_du_jour_et_ses_mots():
    clim = {"especes": {"cepe": [0.0] * 30 + [0.14] + [0.0] * 5}}
    assert C.frequence(clim, "cepe", date(2026, 11, 2)) == 0.14
    assert C.frequence(clim, "girolle", date(2026, 11, 2)) is None and C.frequence(None, "cepe", date.today()) is None
    assert C.en_mots(0.74) == "météo favorable 7 années sur 10 à cette date"
    assert C.en_mots(0.65) == "météo favorable 7 années sur 10 à cette date"      # au plus proche, pas au pair
    assert C.en_mots(0.14) == "météo favorable 1 année sur 10 à cette date"
    assert C.en_mots(0.03) == "météo rarement favorable à cette date"
    assert C.en_mots(0.97) == "météo favorable presque chaque année à cette date"
    assert C.en_mots(None) is None
