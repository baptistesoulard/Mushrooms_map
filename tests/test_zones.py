"""La carte publique par zones de 250 m (champi/zones.py) : rien de plus fin que la zone."""
import numpy as np

from champi import especes as E
from champi import modele as M
from champi import zones as Z
from champi.france import ALTITUDE_DECALAGE, BLOC


def _bloc(rng):
    a = np.zeros((BLOC, BLOC, 3), np.uint8)
    b = np.zeros((BLOC, BLOC, 3), np.uint8)
    c = np.zeros((BLOC, BLOC, 3), np.uint8)
    d = np.zeros((BLOC, BLOC), np.uint8)
    foret = rng.random((BLOC, BLOC)) < 0.6
    essence = np.where(foret, rng.integers(1, 15, (BLOC, BLOC)), 0)
    altitude = rng.integers(0, 2200, (BLOC, BLOC)) + ALTITUDE_DECALAGE
    a[..., 0], a[..., 1] = altitude >> 8, altitude & 255
    a[..., 2] = essence | (rng.random((BLOC, BLOC)) < 0.2) << 4 | (rng.random((BLOC, BLOC)) < 0.5) << 5
    b[..., 0] = rng.integers(0, 50, (BLOC, BLOC))
    b[..., 1] = rng.integers(0, 201, (BLOC, BLOC))
    b[..., 2] = rng.integers(0, 4, (BLOC, BLOC)) | rng.integers(0, 9, (BLOC, BLOC)) << 2
    d[...] = np.where(rng.random((BLOC, BLOC)) < 0.8, rng.integers(35, 85, (BLOC, BLOC)), 0)
    lat = np.linspace(46.2, 45.9, BLOC).astype(np.float32)
    return a, b, c, d, lat


def test_geometrie():
    assert Z.N * Z.ZONE <= BLOC < (Z.N + 1) * Z.ZONE
    rangs = Z.zone_de(np.arange(BLOC))
    tailles = np.bincount(rangs)
    assert tailles.min() >= Z.ZONE, "aucune zone plus petite que 5 cases"
    assert tailles[-1] == BLOC - (Z.N - 1) * Z.ZONE == 7


def test_habitat_le_plus_favorable_de_la_zone():
    rng = np.random.default_rng(3)
    a, b, c, d, lat = _bloc(rng)
    c[:10, :10, 2] = 1                                  # une zone protégée en coin
    d[20:25, 20:25] |= 128                              # une zone urbanisée
    plans = Z.agreger(a, b, c, d, lat)
    assert plans.shape == (Z.PLANS, Z.N, Z.N) and plans.dtype == np.uint8
    essence = a[..., 2] & 15
    alt = ((a[..., 0].astype(np.int32) << 8) | a[..., 1]) - ALTITUDE_DECALAGE
    for k, esp in enumerate(E.DE_FORET):
        h = M.facteur_habitat(esp, essence, (a[..., 2] >> 4) & 1, b[..., 2] & 3, alt, b[..., 0],
                              np.broadcast_to(lat[:, None], essence.shape), ph=d & 127)
        h = np.where((essence > 0) & (c[..., 2] == 0) & (d < 128), h, 0)
        for zl, zc in [(3, 7), (50, 50), (Z.N - 1, Z.N - 1), (Z.N - 1, 0)]:
            l0, c0 = zl * Z.ZONE, zc * Z.ZONE
            l1 = BLOC if zl == Z.N - 1 else l0 + Z.ZONE
            c1 = BLOC if zc == Z.N - 1 else c0 + Z.ZONE
            assert plans[k, zl, zc] == np.round(h[l0:l1, c0:c1].max() * np.float32(255)), (esp.code, zl, zc)
    e = len(E.DE_FORET)
    drapeaux = plans[e + 3]
    assert drapeaux[0, 0] & Z.BOISEE and not drapeaux[0, 0] & Z.FORET, "zone protégée : de la forêt, pas d'indice"
    assert not plans[:e, 0, 0].any()
    assert not plans[:e, 4, 4].any(), "les bois d'une zone urbanisée ne comptent pas"
    zl, zc = 30, 40
    bloc = (slice(zl * 5, zl * 5 + 5), slice(zc * 5, zc * 5 + 5))
    f = (essence[bloc] > 0) & (c[bloc][..., 2] == 0) & (d[bloc] < 128)
    alt_code = (int(plans[e, zl, zc]) << 8) | int(plans[e + 1, zl, zc])
    assert alt_code - ALTITUDE_DECALAGE == round(float(alt[bloc][f].mean()))
    publiques = ((a[bloc][..., 2] >> 5) & 1)[f].sum()
    assert bool(drapeaux[zl, zc] & Z.PUBLIQUE) == (2 * publiques >= f.sum())


def test_bloc_sans_foret():
    rng = np.random.default_rng(4)
    a, b, c, d, lat = _bloc(rng)
    a[..., 2] = 0
    plans = Z.agreger(a, b, c, None, lat)
    assert not plans.any()
