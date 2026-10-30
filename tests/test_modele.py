from datetime import date

import numpy as np
import pytest

from champi import especes as E
from champi import modele as M
from champi.grille import Grille, grille_englobante, lonlat_vers_merc, merc_vers_lonlat

CEPE = E.PAR_CODE["cepe"]


def test_trapeze():
    v = M.trapeze([0, 5, 10, 15, 20, 25, 30], 5, 10, 20, 30)
    assert v.tolist() == pytest.approx([0, 0, 1, 1, 1, 0.5, 0])


def test_saison_nulle_hors_saison_pleine_au_coeur():
    assert M.facteur_saison(CEPE, date(2026, 2, 1)) == 0
    assert M.facteur_saison(CEPE, date(2026, 9, 15)) == 1
    assert 0 < M.facteur_saison(CEPE, date(2026, 6, 20)) < 1


def test_un_facteur_nul_ferme_la_porte():
    f = {"pluie": np.array([1.0]), "sol": np.array([1.0]), "gel": np.array([0.0])}
    assert M.indice(np.array([1.0]), 1.0, f)[0] == 0


def test_versant_sud_plus_sec_et_plus_chaud():
    assert M.pluie_efficace(40, 0.5) < 40 < M.pluie_efficace(40, -0.5)
    sud = M.temperature_locale(15, 1000, E.GRADIENT_SOL, 0.5, E.SOLEIL_SOL)
    nord = M.temperature_locale(15, 1000, E.GRADIENT_SOL, -0.5, E.SOLEIL_SOL)
    assert sud > nord


def test_temperature_baisse_avec_l_altitude():
    assert M.temperature_locale(15, 2000, E.GRADIENT_AIR) == pytest.approx(15 - 13)


def test_fenetre_de_pluie():
    """Pour le cèpe, la pluie compte de 20 à 6 jours avant, pas la veille."""
    n = 40
    k = 30
    pluie = np.zeros(n)
    pluie[k - 10] = 50       # dans la fenêtre
    pluie[k - 2] = 100       # trop récent : la pousse n'a pas encore suivi
    t = np.full(n, 15.0)
    p, t_sol, gel = M.entrees_meteo(CEPE, k, pluie, t, t, 0.0)
    assert p == pytest.approx(50)
    assert t_sol == pytest.approx(15)
    assert gel == 0


def test_gel_compte_les_sept_derniers_jours():
    n, k = 40, 30
    tmin = np.full(n, 5.0)
    tmin[[k, k - 3, k - 6, k - 7]] = -3   # k-7 sort de la fenêtre
    _, _, gel = M.entrees_meteo(CEPE, k, np.zeros(n), tmin, np.full(n, 10.0), 0.0)
    assert gel == 3


def test_historique_insuffisant_refuse():
    with pytest.raises(ValueError):
        M.entrees_meteo(CEPE, 5, np.zeros(10), np.zeros(10), np.zeros(10), 0.0)


def test_habitat_hors_foret_nul_et_pente_penalisee():
    h = M.facteur_habitat(CEPE, np.array([0, 8, 8]), np.array([False] * 3), np.array([2, 2, 2]),
                          np.array([1000, 1000, 1000]), np.array([10, 10, 50]))
    assert h[0] == 0 and h[1] == pytest.approx(1.0) and h[2] == pytest.approx(E.PENTE_PLANCHER)


def test_classes_croissantes():
    seuils = [s for s, _ in M.CLASSES]
    assert seuils == sorted(seuils)
    assert M.classe(0.0) == 0 and M.classe(1.0) == len(M.CLASSES) - 1


# --- Règles des espèces ---------------------------------------------------------------

@pytest.mark.parametrize("esp", E.ESPECES, ids=lambda e: e.code)
def test_regles_coherentes(esp):
    from champi.habitat import ESSENCES, ROCHES
    assert set(esp.essences) == set(ESSENCES), "une affinité par essence, ni plus ni moins"
    assert set(esp.roches) == set(ROCHES)
    assert all(0 <= v <= 1 for v in [*esp.essences.values(), *esp.roches.values()])
    assert esp.essences[0] == 0, "hors forêt : pas d'indice"
    assert list(esp.altitude) == sorted(esp.altitude)
    assert list(esp.sol) == sorted(esp.sol)
    assert esp.pluie_mm[0] < esp.pluie_mm[1]
    assert 0 <= esp.pluie_jours[0] < esp.pluie_jours[1] <= 29, "le job ne garde que 30 jours passés"
    jours = [date(2026, *map(int, s.split("-"))) for s in esp.saison]
    assert jours == sorted(jours)
    assert 0 < esp.gel <= 1


# --- Grille ---------------------------------------------------------------------------

def test_mercator_aller_retour():
    x, y = lonlat_vers_merc(6.5, 46.0)
    lon, lat = merc_vers_lonlat(x, y)
    assert (float(lon), float(lat)) == pytest.approx((6.5, 46.0))


def test_grille_calee_et_grossie():
    g = grille_englobante(5.8, 45.68, 7.05, 46.41, 72.0, 360.0, 1500.0)
    assert g.x0 % 360 == 0 and g.y1 % 360 == 0
    assert g.nx % 5 == 0 and g.ny % 5 == 0
    p = g.grossir(5)
    assert (p.x1, p.y0) == (g.x1, g.y0)
    b = g.bornes_lonlat()
    assert b["ouest"] < 5.8 and b["est"] > 7.05 and b["sud"] < 45.68 and b["nord"] > 46.41


def test_pas_au_sol_vers_50_m():
    g = Grille(*lonlat_vers_merc(6.0, 46.0), 72.0, 10, 10)
    assert g.pas_au_sol().mean() == pytest.approx(50, abs=1)
