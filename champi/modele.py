"""Le calcul de l'indice, sans aucune entrée-sortie : des tableaux entrent, des tableaux sortent.

    indice = habitat × météo
    habitat = essence × roche × altitude × pente (× forêt ouverte)
    météo   = saison × pluie × température du sol × gel

Un produit, pas une moyenne : chaque facteur peut à lui seul fermer la porte (pas de cèpe
sous une gelée, quelle que soit la forêt). C'est un INDICE de favorabilité entre 0 et 1,
pas une probabilité : personne ne recense les endroits où les champignons ne poussent pas.
"""
from __future__ import annotations

from datetime import date

import numpy as np

from . import especes as E


def trapeze(x, a, b, c, d):
    """0 sous a, monte jusqu'à 1 en b, 1 jusqu'à c, redescend à 0 en d."""
    x = np.asarray(x, dtype=np.float32)
    montee = np.clip((x - a) / max(b - a, 1e-6), 0, 1)
    descente = np.clip((d - x) / max(d - c, 1e-6), 0, 1)
    return np.minimum(montee, descente).astype(np.float32)


def montee(x, a, b):
    """0 sous a, 1 au-delà de b, linéaire entre les deux."""
    return np.clip((np.asarray(x, dtype=np.float32) - a) / max(b - a, 1e-6), 0, 1).astype(np.float32)


def _jour(mmjj: str, annee: int) -> int:
    m, j = (int(v) for v in mmjj.split("-"))
    return date(annee, m, j).toordinal()


def facteur_saison(esp: E.Espece, jour: date) -> float:
    a, b, c, d = (_jour(s, jour.year) for s in esp.saison)
    return float(trapeze(jour.toordinal(), a, b, c, d))


def facteur_habitat(esp: E.Espece, essence, ouverte, roche, altitude, pente) -> np.ndarray:
    tab_ess = np.zeros(256, dtype=np.float32)
    for k, v in esp.essences.items():
        tab_ess[k] = v
    tab_roche = np.zeros(256, dtype=np.float32)
    for k, v in esp.roches.items():
        tab_roche[k] = v
    f = tab_ess[essence] * tab_roche[roche]
    f = f * trapeze(altitude, *esp.altitude)
    f = f * facteur_pente(pente)
    return np.where(ouverte, f * E.FORET_OUVERTE, f).astype(np.float32)


def facteur_pente(pente) -> np.ndarray:
    p = np.asarray(pente, dtype=np.float32)
    baisse = (p - E.PENTE_DEBUT) / (E.PENTE_FIN - E.PENTE_DEBUT) * (1 - E.PENTE_PLANCHER)
    return np.clip(1 - baisse, E.PENTE_PLANCHER, 1).astype(np.float32)


def pluie_efficace(pluie_mm, ensoleillement) -> np.ndarray:
    """Un versant au soleil sèche plus vite : une part de la pluie y compte moins."""
    return (np.asarray(pluie_mm, dtype=np.float32)
            * (1 - E.SECHERESSE_SUD * np.asarray(ensoleillement, dtype=np.float32)))


def temperature_locale(t_niveau_mer, altitude, gradient, ensoleillement=None, soleil=0.0):
    """Température ramenée du niveau de la mer à l'altitude de la case (et à son versant)."""
    t = np.asarray(t_niveau_mer, dtype=np.float32) - gradient * np.asarray(altitude, dtype=np.float32)
    if ensoleillement is not None:
        t = t + soleil * np.asarray(ensoleillement, dtype=np.float32)
    return t.astype(np.float32)


def entrees_meteo(esp: E.Espece, k: int, pluie, tmin, tsol, ensoleillement):
    """Les trois entrées météo du jour d'indice `k`, à partir de séries locales (temps en axe 0).

    `pluie` en mm, `tmin` et `tsol` déjà ramenées à l'altitude de la case (°C).
    Renvoie (pluie de la fenêtre, efficace ; température du sol, moyenne des 7 jours
    précédents ; nombre de jours de gel des 7 derniers jours, jour compris).
    """
    j_min, j_max = esp.pluie_jours
    if k - j_max < 0 or k - 7 < 0:
        raise ValueError(f"pas assez d'historique pour le jour {k} (il faut {max(j_max, 7)} jours)")
    fenetre = np.asarray(pluie[k - j_max:k - j_min + 1], dtype=np.float32).sum(axis=0)
    t_sol = np.asarray(tsol[k - 7:k], dtype=np.float32).mean(axis=0)
    gel = (np.asarray(tmin[k - 6:k + 1]) < E.GEL_SEUIL).sum(axis=0)
    return pluie_efficace(fenetre, ensoleillement), t_sol, gel


def facteurs_meteo(esp: E.Espece, pluie_fenetre, t_sol_moyenne, jours_gel) -> dict[str, np.ndarray]:
    """Les trois facteurs météo d'une case, séparés pour pouvoir dire lequel limite."""
    return {
        "pluie": montee(pluie_fenetre, *esp.pluie_mm),
        "sol": trapeze(t_sol_moyenne, *esp.sol),
        "gel": np.power(np.float32(esp.gel), np.asarray(jours_gel, dtype=np.float32)).astype(np.float32),
    }


def indice(habitat, saison: float, facteurs: dict[str, np.ndarray]) -> np.ndarray:
    m = np.float32(saison)
    for f in facteurs.values():
        m = m * f
    return (np.asarray(habitat, dtype=np.float32) * m).astype(np.float32)


# Classes affichées. Seuils fixes, pas des quantiles : quand il ne pousse rien, la carte
# doit rester pâle partout, pas « remplir » ses classes.
CLASSES = [
    (0.10, "Très faible"),
    (0.25, "Faible"),
    (0.40, "Moyen"),
    (0.55, "Bon"),
    (1.01, "Très bon"),
]


def classe(valeur: float) -> int:
    for k, (seuil, _) in enumerate(CLASSES):
        if valeur < seuil:
            return k
    return len(CLASSES) - 1
