"""« Météo favorable 7 années sur 10 à cette date » : ce que la météo d'une espèce est d'habitude.

Le verdict du jour ne dit pas s'il sort de l'ordinaire. Début novembre, le pied-de-mouton est
« bon » presque partout la plupart des années, le cèpe rarement : « bon dans 95 départements » ne
pèse pas pareil pour l'un et pour l'autre. Ce module mesure, pour chaque espèce et chaque décade
de l'année, la part des jours où sa météo (saison × pluie × sol × gel : l'indice sans l'habitat)
atteint `SEUIL`, aux lieux et aux années des séries de la validation (réanalyse ERA5, depuis
1995 ; `cache/validation/meteo_passee.npz`), avec la fonction même de la validation
(`validation.indices_meteo`). Aucune règle n'en dépend : c'est un repère pour le lecteur.

    python -m champi.climatologie      # demande le cache de la validation → data/climatologie.json

Le fichier est versionné : le job du jour n'a pas ce cache, l'export relit le fichier.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date

import numpy as np

from .config import DATA

FICHIER = DATA / "climatologie.json"
# Une forêt qui convient bien à l'espèce (habitat 0,8) passe « bonne » (indice ≥ 0,40,
# `modele.CLASSES`) dès que sa météo atteint 0,5.
SEUIL = 0.5


def decade(d: date) -> int:
    """0 à 35 : trois décades par mois, la troisième du 21 au dernier jour."""
    return (d.month - 1) * 3 + min(2, (d.day - 1) // 10)


def agreger(jours: dict[date, float]) -> tuple[np.ndarray, np.ndarray]:
    """Pour une série : par décade, le nombre de jours favorables et le nombre de jours."""
    favorables, tous = np.zeros(36), np.zeros(36)
    for d, m in jours.items():
        k = decade(d)
        tous[k] += 1
        favorables[k] += m >= SEUIL
    return favorables, tous


def calculer(series: dict, especes) -> dict[str, list[float]]:
    """Par espèce, la part des jours favorables de chaque décade, toutes séries confondues. Une
    série par lieu (0,1°) et par année ; terrain plat, à l'altitude de la maille de la réanalyse."""
    from . import validation as V
    sortie = {}
    for esp in especes:
        favorables, tous = np.zeros(36), np.zeros(36)
        for (lat, _, _), s in series.items():
            f, t = agreger({d: m for d, (_, m) in V.indices_meteo(esp, s, s["altitude"], 0.0, lat).items()})
            favorables += f
            tous += t
        sortie[esp.code] = [round(float(a / b), 3) if b else 0.0 for a, b in zip(favorables, tous)]
        print(f"  {esp.nom} : début novembre, favorable {sortie[esp.code][30]:.0%} des jours", flush=True)
    return sortie


def _une_espece(code: str) -> list[float]:
    """Une espèce dans son propre processus (un quart d'heure et plus en série pour douze)."""
    from . import especes as E
    from . import validation as V
    return calculer(V.meteo_passee(set()), [next(e for e in E.ESPECES if e.code == code)])[code]


def charger() -> dict | None:
    return json.loads(FICHIER.read_text(encoding="utf-8")) if FICHIER.exists() else None


def frequence(clim: dict | None, code: str, d: date) -> float | None:
    """La part des jours favorables à l'espèce à cette date, ou None sans mesure."""
    valeurs = (clim or {}).get("especes", {}).get(code)
    return valeurs[decade(d)] if valeurs else None


def en_mots(f: float | None) -> str | None:
    """« météo favorable 7 années sur 10 à cette date » (arrondi au plus proche, pas au pair)."""
    if f is None:
        return None
    if f < 0.05:
        return "météo rarement favorable à cette date"
    if f >= 0.95:
        return "météo favorable presque chaque année à cette date"
    n = int(f * 10 + 0.5)
    return f"météo favorable {n} année{'s' if n > 1 else ''} sur 10 à cette date"


def main() -> None:
    from . import especes as E
    from . import validation as V
    t0 = time.time()
    series = V.meteo_passee(set())
    if not series:
        raise SystemExit("Pas de météo passée en cache : lancer d'abord python -m champi.validation meteo.")
    annees = sorted({an for _, _, an in series})
    print(f"Climatologie : {len(series)} séries (lieu × année), {annees[0]}-{annees[-1]}")
    codes = [e.code for e in E.ESPECES]
    with ProcessPoolExecutor() as ex:
        valeurs = list(ex.map(_une_espece, codes))
    sortie = {
        "calcule_le": date.today().isoformat(),
        "periode": [annees[0], annees[-1]],
        "series": len(series),
        "seuil": SEUIL,
        "especes": dict(zip(codes, valeurs)),
    }
    FICHIER.write_text(json.dumps(sortie, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Écrit {FICHIER.relative_to(DATA.parent)} en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
