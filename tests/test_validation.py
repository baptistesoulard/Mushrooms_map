from datetime import date

import numpy as np
import pytest

from champi.france import BLOC
from champi.validation import _paire, _somme_zone, auc, quotidien


def _auc_brute(cas, temoins):
    total = 0.0
    for c in cas:
        for t in temoins:
            total += 1.0 if c > t else 0.5 if c == t else 0.0
    return total / (len(cas) * len(temoins))


def test_auc_egale_le_calcul_par_paires():
    rng = np.random.default_rng(3)
    cas = rng.integers(0, 5, 30).astype(float)       # beaucoup d'égalités, exprès
    tem = rng.integers(0, 5, 50).astype(float)
    assert auc(cas, tem) == pytest.approx(_auc_brute(cas, tem))


def test_auc_bornes():
    assert auc(np.array([2.0, 3.0]), np.array([0.0, 1.0])) == 1.0
    assert auc(np.array([0.0]), np.array([1.0])) == 0.0
    assert auc(np.array([1.0]), np.array([1.0])) == 0.5


def test_paire():
    assert _paire(0.5, np.array([0.1, 0.5, 0.9])) == pytest.approx(0.5)


def test_jours_de_paris():
    """Heures UTC d'une année vers les jours de Paris : UTC+1 l'hiver, UTC+2 l'été."""
    heures = np.arange(365 * 24, dtype=np.float32)          # 2023 : la valeur dit l'heure UTC
    somme = quotidien(np.ones_like(heures), 2023, "somme")
    assert np.isnan(somme[0])                               # le 1er janvier commence la veille en UTC
    assert somme[1] == 24 and somme[100] == 24
    assert somme[84] == 23                                  # 26 mars : passage à l'heure d'été
    assert somme[301] == 25                                 # 29 octobre : retour à l'heure d'hiver
    assert somme[-1] == 24                                  # 31 décembre complet ; 23 h UTC est déjà le 1er janvier
    # Le 2 janvier de Paris va de 23 h UTC le 1er à 22 h UTC le 2.
    assert quotidien(heures, 2023, "min")[1] == 23
    assert quotidien(heures, 2023, "moyenne")[1] == pytest.approx(np.mean(np.arange(23, 47)))
    # Une heure manquante rend le jour inconnu, sans toucher aux voisins.
    trou = np.ones_like(heures)
    trou[24 * 50] = np.nan
    s = quotidien(trou, 2023, "somme")
    assert np.isnan(s[50]) and s[51] == 24


def test_somme_sur_la_zone_coupee_au_bord():
    v = np.ones((BLOC, BLOC))
    lig, col = np.array([100, 0, BLOC - 1]), np.array([100, 0, 3])
    assert list(_somme_zone(v, lig, col)) == [25, 9, 15]
    v[101, 102] = 0                                        # dans la zone de (100, 100)
    v[100, 103] = 0                                        # juste dehors
    assert _somme_zone(v, np.array([100]), np.array([100]))[0] == 24
