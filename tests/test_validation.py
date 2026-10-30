import numpy as np
import pytest

from champi.validation import _paire, auc


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
