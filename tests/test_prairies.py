"""Les prés (data/prairies.npz, versionné) : le fichier que lit l'export, et sa garde contre un
habitat refait avec une autre liste de communes."""
import numpy as np

from champi import prairies as P
from champi.export_france import charger_pres


def test_fichier_des_pres():
    z = np.load(P.FICHIER)
    assert {"pas", "ix", "iy", "altitude", "commune", "milieu", "communes"} <= set(z)
    assert float(z["pas"]) == P.PAS
    assert set(np.unique(z["milieu"]).tolist()) <= set(P.NOMS_MILIEUX)
    assert (z["commune"] > 0).all(), "un point hors commune n'appartient à aucun département"
    c = P.charger()
    assert 41 < c["lat"].min() and c["lat"].max() < 51.6 and -5.6 < c["lon"].min() and c["lon"].max() < 10
    assert c["altitude"].min() >= 0 and c["altitude"].max() < 4000


def test_empreinte_des_communes():
    a = [{"insee": "01001", "nom": "L'Abergement", "dep": "01"}, {"insee": "85001", "nom": "Aizenay", "dep": "85"}]
    assert P.empreinte_communes(a) == P.empreinte_communes([dict(x) for x in a])
    assert P.empreinte_communes(a) != P.empreinte_communes(a[::-1])


def test_autre_liste_de_communes_pas_d_especes_des_pres():
    """Les numéros de commune ne vaudraient plus rien : l'export saute ces espèces et le dit."""
    assert charger_pres([{"insee": "01001", "dep": "01"}], [{"code": "01"}]) is None
