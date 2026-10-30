"""Météo des points d'une grille d'environ 5 km, via Open-Meteo (gratuit, sans clé).

- prévisions : les 30 derniers jours et les 8 prochains (job quotidien) ;
- archive (réanalyse ERA5-Land) : séries passées, pour la validation.

Les températures sont ramenées au niveau de la mer avec l'altitude qu'Open-Meteo a
utilisée pour chaque point, puis redescendues à l'altitude de chaque case de 50 m
(`modele.temperature_locale`). La pluie est interpolée telle quelle.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

import numpy as np

from . import especes as E
from .grille import Grille
from .sources import http_get

PREVISIONS = "https://api.open-meteo.com/v1/forecast"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
VARIABLES = ["precipitation_sum", "temperature_2m_min", "soil_temperature_0_to_7cm_mean"]

PAS_LAT = 0.05   # ≈ 5,6 km
PAS_LON = 0.07   # ≈ 5,4 km à 46° N
PAR_REQUETE = 80


@dataclass
class Meteo:
    """Séries quotidiennes sur une grille régulière de points (lat croissante, lon croissante)."""

    dates: list[date]
    lats: np.ndarray            # (nlat,)
    lons: np.ndarray            # (nlon,)
    altitude: np.ndarray        # (nlat, nlon), altitude des points selon Open-Meteo
    pluie: np.ndarray           # (njours, nlat, nlon), mm
    tmin_mer: np.ndarray        # (njours, nlat, nlon), °C ramenés au niveau de la mer
    tsol_mer: np.ndarray        # idem, sol 0-7 cm

    def indice(self, jour: date) -> int:
        return self.dates.index(jour)


def points(grille: Grille) -> tuple[np.ndarray, np.ndarray]:
    """Grille de points météo couvrant l'emprise, avec un pas de marge de chaque côté."""
    b = grille.bornes_lonlat()
    lat0 = np.floor(b["sud"] / PAS_LAT) * PAS_LAT - PAS_LAT
    lat1 = np.ceil(b["nord"] / PAS_LAT) * PAS_LAT + PAS_LAT
    lon0 = np.floor(b["ouest"] / PAS_LON) * PAS_LON - PAS_LON
    lon1 = np.ceil(b["est"] / PAS_LON) * PAS_LON + PAS_LON
    lats = np.round(np.arange(lat0, lat1 + 1e-9, PAS_LAT), 4)
    lons = np.round(np.arange(lon0, lon1 + 1e-9, PAS_LON), 4)
    return lats, lons


def _remplir(serie: np.ndarray) -> np.ndarray:
    """Comble les trous (null) d'une série par la valeur voisine la plus proche dans le temps."""
    s = serie.astype(np.float32).copy()
    ok = ~np.isnan(s)
    if not ok.any():
        return s
    idx = np.where(ok, np.arange(len(s)), 0)
    np.maximum.accumulate(idx, out=idx)
    s = s[idx]
    premier = np.argmax(ok)
    s[:premier] = s[premier]
    return s


def _interroger(url: str, lats_pts, lons_pts, params: dict, pause: float) -> list[dict]:
    reponses = []
    for k in range(0, len(lats_pts), PAR_REQUETE):
        if k:
            time.sleep(pause)   # limite d'Open-Meteo : 600 appels pondérés par minute
        p = {
            "latitude": ",".join(f"{v:.4f}" for v in lats_pts[k:k + PAR_REQUETE]),
            "longitude": ",".join(f"{v:.4f}" for v in lons_pts[k:k + PAR_REQUETE]),
            "daily": ",".join(VARIABLES), "timezone": "Europe/Paris", **params,
        }
        r = http_get(url, p, essais=6, delai=120).json()
        reponses.extend(r if isinstance(r, list) else [r])
    return reponses


def _assembler(reponses, lats, lons) -> Meteo:
    nlat, nlon = len(lats), len(lons)
    dates = [date.fromisoformat(t) for t in reponses[0]["daily"]["time"]]
    n = len(dates)
    alt = np.zeros((nlat, nlon), dtype=np.float32)
    champs = {v: np.zeros((n, nlat, nlon), dtype=np.float32) for v in VARIABLES}
    for k, rep in enumerate(reponses):
        i, j = divmod(k, nlon)
        alt[i, j] = rep.get("elevation") or 0.0
        for v in VARIABLES:
            brut = np.array([np.nan if x is None else x for x in rep["daily"][v]], dtype=np.float32)
            champs[v][:, i, j] = _remplir(brut)
    for v in VARIABLES:   # un point entièrement vide prend la moyenne des autres, jour par jour
        c = champs[v]
        if np.isnan(c).any():
            moy = np.nanmean(c.reshape(n, -1), axis=1)[:, None, None]
            champs[v] = np.where(np.isnan(c), moy, c)
    return Meteo(
        dates=dates, lats=lats, lons=lons, altitude=alt,
        pluie=np.maximum(champs["precipitation_sum"], 0),
        tmin_mer=champs["temperature_2m_min"] + E.GRADIENT_AIR * alt,
        tsol_mer=champs["soil_temperature_0_to_7cm_mean"] + E.GRADIENT_SOL * alt,
    )


def previsions(grille: Grille, jours_passes: int = 30, jours_futurs: int = 8) -> Meteo:
    lats, lons = points(grille)
    la, lo = np.meshgrid(lats, lons, indexing="ij")
    reponses = _interroger(PREVISIONS, la.ravel(), lo.ravel(),
                           {"past_days": jours_passes, "forecast_days": jours_futurs}, pause=25)
    return _assembler(reponses, lats, lons)


def archive_points(lats_pts, lons_pts, debut: date, fin: date) -> list[dict]:
    """Séries ERA5-Land brutes (réponses Open-Meteo) pour une liste de points quelconques."""
    return _interroger(ARCHIVE, list(lats_pts), list(lons_pts),
                       {"start_date": debut.isoformat(), "end_date": fin.isoformat()}, pause=30)


class Interpolateur:
    """Interpolation bilinéaire des champs de points vers des cases (lat, lon) quelconques."""

    def __init__(self, lats: np.ndarray, lons: np.ndarray, lat_cases: np.ndarray, lon_cases: np.ndarray):
        fi = (lat_cases - lats[0]) / (lats[1] - lats[0])
        fj = (lon_cases - lons[0]) / (lons[1] - lons[0])
        self.i0 = np.clip(np.floor(fi).astype(int), 0, len(lats) - 2)
        self.j0 = np.clip(np.floor(fj).astype(int), 0, len(lons) - 2)
        self.wi = np.clip(fi - self.i0, 0, 1).astype(np.float32)
        self.wj = np.clip(fj - self.j0, 0, 1).astype(np.float32)

    def __call__(self, champ: np.ndarray) -> np.ndarray:
        i0, j0, wi, wj = self.i0, self.j0, self.wi, self.wj
        return ((champ[i0, j0] * (1 - wi) + champ[i0 + 1, j0] * wi) * (1 - wj)
                + (champ[i0, j0 + 1] * (1 - wi) + champ[i0 + 1, j0 + 1] * wi) * wj).astype(np.float32)
