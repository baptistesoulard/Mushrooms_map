"""La voie rapide du job quotidien rend exactement ce que rendrait le calcul case par case."""
from datetime import date, timedelta

import numpy as np
import pytest

from champi import especes as E
from champi import modele as M
from champi.export import HORS_DEPARTEMENT, HORS_FORET, PROTEGE, Agregat, Calcul, cases_de_foret
from champi.grille import Grille, lonlat_vers_merc
from champi.meteo import Interpolateur, Meteo


def _habitat(ny=10, nx=10):
    rng = np.random.default_rng(1)
    h = {
        "commune": np.ones((ny, nx), dtype=np.uint16),
        "essence": rng.integers(0, 13, (ny, nx)).astype(np.uint8),
        "altitude": rng.integers(300, 2000, (ny, nx)).astype(np.int16),
        "ensoleillement": rng.integers(-60, 60, (ny, nx)).astype(np.int8),
        "pente": rng.integers(0, 50, (ny, nx)).astype(np.uint8),
        "ouverte": np.zeros((ny, nx), dtype=bool),
        "roche": rng.integers(0, 4, (ny, nx)).astype(np.uint8),
        "protege": np.zeros((ny, nx), dtype=np.uint8),
        "public": np.zeros((ny, nx), dtype=bool),
        "orientation": rng.integers(0, 9, (ny, nx)).astype(np.uint8),
    }
    x0, y1 = lonlat_vers_merc(6.3, 46.0)
    grille = Grille(float(x0), float(y1), 72.0, nx, ny)
    return grille, h


def _meteo(grille):
    rng = np.random.default_rng(2)
    b = grille.bornes_lonlat()
    lats = np.array([b["sud"] - 0.05, b["sud"] + 0.05, b["nord"] + 0.1])
    lons = np.array([b["ouest"] - 0.07, b["ouest"] + 0.07, b["est"] + 0.1])
    n = 38
    return Meteo(
        dates=[date(2026, 9, 1) + timedelta(days=i) for i in range(n)], lats=lats, lons=lons,
        altitude=rng.uniform(300, 1500, (3, 3)).astype(np.float32),
        pluie=rng.gamma(0.6, 6, (n, 3, 3)).astype(np.float32),
        tmin_mer=rng.normal(6, 5, (n, 3, 3)).astype(np.float32),
        tsol_mer=rng.normal(16, 4, (n, 3, 3)).astype(np.float32),
    )


@pytest.mark.parametrize("esp", E.ESPECES, ids=lambda e: e.code)
def test_voie_rapide_egale_calcul_direct(esp):
    grille, h = _habitat()
    meteo = _meteo(grille)
    cases = cases_de_foret(grille, h)
    k = 32
    rapide = Calcul(meteo, cases).entrees(esp, k)

    interp = Interpolateur(meteo.lats, meteo.lons, cases.lat, cases.lon)
    pluie = np.stack([interp(meteo.pluie[d]) for d in range(len(meteo.dates))])
    tmin = np.stack([M.temperature_locale(interp(meteo.tmin_mer[d]), cases.altitude, E.GRADIENT_AIR)
                     for d in range(len(meteo.dates))])
    tsol = np.stack([M.temperature_locale(interp(meteo.tsol_mer[d]), cases.altitude, E.GRADIENT_SOL,
                                          cases.ensoleillement, E.SOLEIL_SOL)
                     for d in range(len(meteo.dates))])
    direct = M.entrees_meteo(esp, k, pluie, tmin, tsol, cases.ensoleillement)
    for a, b in zip(rapide, direct):
        np.testing.assert_allclose(a, b, rtol=1e-5, atol=1e-4)


def test_interpolation_exacte_aux_points():
    lats, lons = np.array([45.0, 45.1]), np.array([6.0, 6.1])
    champ = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    i = Interpolateur(lats, lons, np.array([45.0, 45.1, 45.05]), np.array([6.0, 6.1, 6.05]))
    np.testing.assert_allclose(i(champ), [1.0, 4.0, 2.5])


def test_codes_des_zones():
    grille, h = _habitat(10, 10)
    h["essence"][:] = 8
    h["essence"][:5, :5] = 0                 # zone 0 : hors forêt
    h["protege"][:5, 5:] = 3                 # zone 1 : protégée
    h["commune"][5:, 5:] = 0                 # zone 3 : hors département
    cases = cases_de_foret(grille, h)
    a = Agregat(grille, h, cases, 5)
    codes = a.indice(np.full(len(cases.lat), 0.5, dtype=np.float32))
    assert codes.ravel().tolist() == [HORS_FORET, PROTEGE, 100, HORS_DEPARTEMENT]


def test_zone_peu_boisee_reduite():
    grille, h = _habitat(5, 5)
    h["essence"][:] = 0
    h["essence"][0, :4] = 8                  # 4 cases boisées sur 25 = 16 %
    cases = cases_de_foret(grille, h)
    a = Agregat(grille, h, cases, 5)
    code = a.indice(np.full(len(cases.lat), 1.0, dtype=np.float32))[0, 0]
    assert code == round(200 * (4 / 25) / 0.3)


def test_grille_publiee_a_50_m_case_par_case():
    """Facteur 1 : chaque case garde sa valeur ; hors forêt, protégée, hors département codées."""
    grille, h = _habitat(2, 3)
    h["essence"][:] = 8
    h["essence"][0, 0] = 0
    h["protege"][0, 1] = 1
    h["commune"][1, 2] = 0
    cases = cases_de_foret(grille, h)
    a = Agregat(grille, h, cases, 1)
    valeurs = np.linspace(0.1, 0.4, len(cases.lat)).astype(np.float32)
    codes = a.indice(valeurs)
    assert codes.shape == (2, 3)
    assert codes[0, 0] == HORS_FORET and codes[0, 1] == PROTEGE and codes[1, 2] == HORS_DEPARTEMENT
    libres = [(i, j) for i in range(2) for j in range(3) if (i, j) not in [(0, 0), (0, 1), (1, 2)]]
    attendu = {(int(l), int(c)): v for l, c, v in zip(cases.lignes, cases.colonnes, valeurs)}
    for i, j in libres:
        assert codes[i, j] == round(attendu[(i, j)] * 200)


def test_valeurs_sans_foret_codees_255():
    grille, h = _habitat(5, 5)
    h["essence"][:] = 0
    h["essence"][2, 2] = 8
    cases = cases_de_foret(grille, h)
    assert Agregat(grille, h, cases, 1).valeurs(np.array([12.4]))[2, 2] == 12
    assert Agregat(grille, h, cases, 1).valeurs(np.array([12.4]))[0, 0] == 255
    assert Agregat(grille, h, cases, 5).valeurs(np.array([12.4]))[0, 0] == 12


def test_verdicts_des_carres_comme_les_departements():
    """La carte de l'accueil : le verdict de chaque carré est celui qu'un département aurait avec la
    même forêt (`redaction.niveau`) ; pas de verdict sous CARRE_MIN_KM2 de forêt hors zones
    protégées, ni pour un carré sans forêt."""
    from champi import export_france as X
    from champi import pages_accueil, redaction
    from champi.config import PAS_FIN

    assert pages_accueil.CARRE_UNE_M == PAS_FIN * X.APERCU * X.VUE
    rng = np.random.default_rng(3)
    n_carres, par = 6, 400
    pixel = np.repeat(np.arange(n_carres), par)
    km2 = np.full(pixel.size, 0.01)                          # 4 km² par carré
    libre = np.ones(pixel.size, dtype=bool)
    indice = rng.uniform(0, 0.39, pixel.size)
    saison = np.ones(pixel.size)
    indice[0:160] = 0.5                                      # carré 0 : 40 % bon
    indice[400:430] = 0.45                                   # carré 1 : 7,5 % bon
    indice[800:1200] = rng.uniform(0, 0.2, 400)              # carré 2 : défavorable
    indice[820:850] = 0.3                                    # … 7,5 % moyen : possible
    saison[1200:1600] = 0                                    # carré 3 : hors saison
    libre[1600:1990] = False                                 # carré 4 : presque tout protégé
    indice[2000:2400] = rng.uniform(0, 0.2, 400)             # carré 5 : défavorable
    niv = X.verdicts_carres(pixel, 3, 3, km2, libre, indice, saison).ravel()
    for c in range(n_carres):
        if c == 4:
            continue
        s = slice(c * par, (c + 1) * par)
        bon = float((km2[s] * (indice[s] >= 0.40)).sum() / km2[s].sum())
        moyen = float((km2[s] * (indice[s] >= 0.25)).sum() / km2[s].sum())
        attendu = redaction.niveau({"saison": float(saison[s].max()), "part_bon": bon, "part_moyen": moyen})
        assert niv[c] == attendu, c
    assert niv[:4].tolist() == [4, 3, 2, 0]
    assert niv[4] == -1 and niv[6:].tolist() == [-1, -1, -1]


def test_apercu_la_meilleure_foret_du_pixel():
    """L'aperçu (vue régionale) prend la meilleure case de chaque pixel, comme les zones de 250 m
    prennent l'habitat le plus favorable : pas de moyenne diluée par la forêt clairsemée. Les cases
    protégées ne comptent pas ; un pixel sans forêt libre reste hors forêt."""
    from types import SimpleNamespace
    from champi import export_france as X
    from champi.export import ECHELLE, HORS_FORET
    from champi.grille import merc_vers_lonlat

    g = Grille(0.0, 2000.0, 1000.0, 2, 2)                    # quatre pixels de 1 km
    x = np.array([100.0, 900.0, 500.0, 1500.0, 1500.0])
    y = np.array([1900.0, 1100.0, 1500.0, 1500.0, 500.0])
    lon, lat = merc_vers_lonlat(x, y)
    ech = SimpleNamespace(lon=lon, lat=lat, protege=np.array([False, False, True, True, False]))
    image = X.Apercu(g, ech).image(np.array([0.2, 0.6, 0.9, 0.9, 0.3]))
    assert image[0, 0] == round(0.6 * ECHELLE)               # la meilleure des deux libres, pas 0,4
    assert image[0, 1] == HORS_FORET                          # seule une case protégée
    assert image[1, 1] == round(0.3 * ECHELLE) and image[1, 0] == HORS_FORET
