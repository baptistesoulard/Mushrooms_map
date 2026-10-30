"""Grille régulière en Web Mercator (EPSG:3857), la projection de la carte.

Tout est calculé directement dans la projection d'affichage : une image dont les pixels
sont réguliers en Mercator se pose telle quelle sur la carte Leaflet, sans reprojection.
Les conversions sont écrites à la main (sphère de rayon R, comme Leaflet) : aucune
dépendance à PROJ, qui se casse facilement sous Windows.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

R = 6378137.0


def lonlat_vers_merc(lon, lat):
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    x = R * np.radians(lon)
    y = R * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))
    return x, y


def merc_vers_lonlat(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    lon = np.degrees(x / R)
    lat = np.degrees(2 * np.arctan(np.exp(y / R)) - np.pi / 2)
    return lon, lat


@dataclass(frozen=True)
class Grille:
    """Grille de `ny` lignes (du nord au sud) et `nx` colonnes (d'ouest en est)."""

    x0: float   # bord ouest, m Mercator
    y1: float   # bord nord, m Mercator
    pas: float  # côté d'une case, m Mercator
    nx: int
    ny: int

    @property
    def x1(self) -> float:
        return self.x0 + self.nx * self.pas

    @property
    def y0(self) -> float:
        return self.y1 - self.ny * self.pas

    def centres_x(self) -> np.ndarray:
        return self.x0 + (np.arange(self.nx) + 0.5) * self.pas

    def centres_y(self) -> np.ndarray:
        return self.y1 - (np.arange(self.ny) + 0.5) * self.pas

    def longitudes(self) -> np.ndarray:
        return merc_vers_lonlat(self.centres_x(), 0.0)[0]

    def latitudes(self) -> np.ndarray:
        return merc_vers_lonlat(0.0, self.centres_y())[1]

    def pas_au_sol(self) -> np.ndarray:
        """Côté d'une case au sol (m), par ligne : le Mercator dilate de 1/cos(lat)."""
        return self.pas * np.cos(np.radians(self.latitudes()))

    def grossir(self, facteur: int) -> "Grille":
        assert self.nx % facteur == 0 and self.ny % facteur == 0
        return Grille(self.x0, self.y1, self.pas * facteur, self.nx // facteur, self.ny // facteur)

    def bornes_lonlat(self) -> dict:
        """Coins de l'image pour Leaflet : [[sud, ouest], [nord, est]]."""
        ouest, sud = merc_vers_lonlat(self.x0, self.y0)
        est, nord = merc_vers_lonlat(self.x1, self.y1)
        return {"sud": float(sud), "ouest": float(ouest), "nord": float(nord), "est": float(est)}

    def vers_pixels(self, x, y):
        """Coordonnées Mercator → coordonnées pixel (colonne, ligne) flottantes."""
        return (np.asarray(x) - self.x0) / self.pas, (self.y1 - np.asarray(y)) / self.pas

    def en_dict(self) -> dict:
        return {"x0": self.x0, "y1": self.y1, "pas": self.pas, "nx": self.nx, "ny": self.ny}

    @classmethod
    def depuis_dict(cls, d: dict) -> "Grille":
        return cls(float(d["x0"]), float(d["y1"]), float(d["pas"]), int(d["nx"]), int(d["ny"]))


def grille_englobante(lon_min, lat_min, lon_max, lat_max, pas: float, multiple: float, marge: float) -> Grille:
    """Plus petite grille de pas `pas` couvrant l'emprise, bords calés sur `multiple`."""
    xa, ya = lonlat_vers_merc(lon_min, lat_min)
    xb, yb = lonlat_vers_merc(lon_max, lat_max)
    x0 = math.floor((float(xa) - marge) / multiple) * multiple
    y0 = math.floor((float(ya) - marge) / multiple) * multiple
    x1 = math.ceil((float(xb) + marge) / multiple) * multiple
    y1 = math.ceil((float(yb) + marge) / multiple) * multiple
    return Grille(x0, y1, pas, int(round((x1 - x0) / pas)), int(round((y1 - y0) / pas)))
