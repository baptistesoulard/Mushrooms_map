"""Accès réseau (WFS, WMS, API JSON) et rastérisation des polygones.

Pas de GDAL ni de PROJ : les services de la Géoplateforme et du BRGM renvoient directement
du Web Mercator (ou du WGS84, converti dans `grille.py`), et les polygones sont rastérisés
avec Pillow.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw

from .config import CACHE, USER_AGENT
from .grille import Grille, lonlat_vers_merc

GEOPF_WFS = "https://data.geopf.fr/wfs/ows"
GEOPF_WMS_R = "https://data.geopf.fr/wms-r/wms"
BRGM_WFS = "https://geoservices.brgm.fr/geologie"


def http_get(url: str, params: dict | None = None, essais: int = 5, delai: float = 60.0) -> requests.Response:
    """GET avec reprises (attente croissante). Lève l'erreur au dernier essai."""
    for essai in range(1, essais + 1):
        try:
            r = requests.get(url, params=params, timeout=delai, headers={"User-Agent": USER_AGENT})
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r
        except (requests.RequestException, ValueError) as e:
            if essai == essais:
                raise
            # Service saturé (429, 503) : il dit parfois combien attendre ; sinon on double.
            reponse = getattr(e, "response", None)
            attente = reponse.headers.get("Retry-After") if reponse is not None else None
            time.sleep(min(120, float(attente)) if attente and attente.isdigit() else min(120, 3 * 2 ** essai))
    raise AssertionError("inatteignable")


def json_en_cache(nom: str, charger) -> dict:
    """Relit `cache/<nom>.json` s'il existe, sinon appelle `charger()` et l'y écrit."""
    chemin = CACHE / f"{nom}.json"
    if chemin.exists():
        return json.loads(chemin.read_text(encoding="utf-8"))
    donnees = charger()
    CACHE.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    return donnees


def wfs_geopf(couche: str, grille: Grille, page: int = 5000, **params) -> list[dict]:
    """Toutes les entités d'une couche WFS Géoplateforme dans l'emprise, en EPSG:3857."""
    entites: list[dict] = []
    debut = 0
    while True:
        p = {
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
            "TYPENAMES": couche, "SRSNAME": "EPSG:3857", "OUTPUTFORMAT": "application/json",
            "BBOX": f"{grille.x0},{grille.y0},{grille.x1},{grille.y1},EPSG:3857",
            "COUNT": page, "STARTINDEX": debut, **params,
        }
        lot = http_get(GEOPF_WFS, p, delai=180).json().get("features", [])
        entites.extend(lot)
        if len(lot) < page:
            return entites
        debut += page


def wms_bil(couche: str, grille: Grille, tuile: int = 1024) -> np.ndarray:
    """Valeurs brutes float32 d'une couche WMS-R (format BIL), sur la grille exacte."""
    sortie = np.full((grille.ny, grille.nx), np.nan, dtype=np.float32)
    for i0 in range(0, grille.ny, tuile):
        for j0 in range(0, grille.nx, tuile):
            h, w = min(tuile, grille.ny - i0), min(tuile, grille.nx - j0)
            x0 = grille.x0 + j0 * grille.pas
            y1 = grille.y1 - i0 * grille.pas
            p = {
                "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": couche,
                "STYLES": "", "CRS": "EPSG:3857", "WIDTH": w, "HEIGHT": h,
                "BBOX": f"{x0},{y1 - h * grille.pas},{x0 + w * grille.pas},{y1}",
                "FORMAT": "image/x-bil;bits=32",
            }
            r = http_get(GEOPF_WMS_R, p, delai=180)
            if not r.headers.get("Content-Type", "").startswith("image/x-bil"):
                raise RuntimeError(f"WMS {couche} : réponse inattendue {r.text[:200]}")
            sortie[i0:i0 + h, j0:j0 + w] = np.frombuffer(r.content, dtype="<f4").reshape(h, w)
    return sortie


def wms_bil_lonlat(couche: str, grille: Grille, pas_deg: float = 0.0003, tuile: int = 1024) -> np.ndarray:
    """Comme `wms_bil`, mais lu en latitude/longitude puis interpolé (bilinéaire) aux centres
    des cases Mercator.

    Demandé directement en Mercator, le relief de l'IGN revient avec une ligne sur trois en
    double (rééchantillonnage au plus proche) : la pente et l'exposition en sortent striées.
    En latitude/longitude, un peu plus fin que les cases, il n'y a aucun doublon (mesuré le
    2026-10-31 sur le bloc d'Annecy). Hors de France, le service renvoie des valeurs négatives
    de remplissage : NaN.
    """
    b = grille.bornes_lonlat()
    marge = 2 * pas_deg
    lat0, lat1 = b["sud"] - marge, b["nord"] + marge
    lon0, lon1 = b["ouest"] - marge, b["est"] + marge
    ny = int(np.ceil((lat1 - lat0) / pas_deg))
    nx = int(np.ceil((lon1 - lon0) / (pas_deg * 4 / 3)))      # pixels à peu près carrés vers 45° N
    dlat, dlon = (lat1 - lat0) / ny, (lon1 - lon0) / nx
    brut = np.full((ny, nx), np.nan, dtype=np.float32)        # ligne 0 au nord
    for i0 in range(0, ny, tuile):
        for j0 in range(0, nx, tuile):
            h, w = min(tuile, ny - i0), min(tuile, nx - j0)
            nord, ouest = lat1 - i0 * dlat, lon0 + j0 * dlon
            p = {
                "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": couche,
                "STYLES": "", "CRS": "EPSG:4326", "WIDTH": w, "HEIGHT": h,
                "BBOX": f"{nord - h * dlat},{ouest},{nord},{ouest + w * dlon}",
                "FORMAT": "image/x-bil;bits=32",
            }
            r = http_get(GEOPF_WMS_R, p, delai=180)
            if not r.headers.get("Content-Type", "").startswith("image/x-bil"):
                raise RuntimeError(f"WMS {couche} : réponse inattendue {r.text[:200]}")
            brut[i0:i0 + h, j0:j0 + w] = np.frombuffer(r.content, dtype="<f4").reshape(h, w)
    brut[brut < -100] = np.nan
    # Bilinéaire séparable : les centres des cases forment une grille (lat par ligne, lon par colonne).
    fi = (lat1 - grille.latitudes()) / dlat - 0.5
    fj = (grille.longitudes() - lon0) / dlon - 0.5
    i0 = np.clip(np.floor(fi).astype(int), 0, ny - 2)
    j0 = np.clip(np.floor(fj).astype(int), 0, nx - 2)
    wi = np.clip(fi - i0, 0, 1)[:, None]
    wj = np.clip(fj - j0, 0, 1)[None, :]
    a, c = brut[i0][:, j0], brut[i0][:, j0 + 1]
    d, e = brut[i0 + 1][:, j0], brut[i0 + 1][:, j0 + 1]
    return ((a * (1 - wj) + c * wj) * (1 - wi) + (d * (1 - wj) + e * wj) * wi).astype(np.float32)


# --- Géométries --------------------------------------------------------------------

def polygones(geometrie: dict):
    """Itère les polygones (liste d'anneaux) d'une géométrie GeoJSON Polygon/MultiPolygon."""
    if geometrie is None:
        return
    t = geometrie["type"]
    if t == "Polygon":
        yield geometrie["coordinates"]
    elif t == "MultiPolygon":
        yield from geometrie["coordinates"]


def geometrie_lonlat_vers_merc(geometrie: dict) -> dict:
    """Convertit une géométrie GeoJSON WGS84 en Web Mercator."""
    def anneau(a):
        a = np.asarray(a, dtype=float)
        x, y = lonlat_vers_merc(a[:, 0], a[:, 1])
        return np.column_stack([x, y]).tolist()

    polys = [[anneau(a) for a in poly] for poly in polygones(geometrie)]
    return {"type": "MultiPolygon", "coordinates": polys}


def rasteriser(entites, grille: Grille, dtype=np.uint8, fond=0) -> np.ndarray:
    """Rastérise des couples (géométrie Mercator, valeur) ; les suivants écrasent les précédents.

    Une case prend la valeur du polygone qui contient son centre. Les trous n'effacent
    rien : un polygone plus petit, logé dans le trou d'un autre, garde sa valeur quel que
    soit l'ordre.
    """
    sortie = np.full((grille.ny, grille.nx), fond, dtype=dtype)
    for geometrie, valeur in entites:
        for poly in polygones(geometrie):
            ext = np.asarray(poly[0], dtype=float)
            if len(ext) < 3:
                continue
            # Coordonnées pixel ; Pillow place l'entier au centre du pixel, d'où le -0,5.
            cols, lignes = grille.vers_pixels(ext[:, 0], ext[:, 1])
            j0 = max(int(np.floor(cols.min())), 0)
            j1 = min(int(np.ceil(cols.max())) + 1, grille.nx)
            i0 = max(int(np.floor(lignes.min())), 0)
            i1 = min(int(np.ceil(lignes.max())) + 1, grille.ny)
            if j0 >= j1 or i0 >= i1:
                continue
            masque = Image.new("1", (j1 - j0, i1 - i0), 0)
            dessin = ImageDraw.Draw(masque)
            for k, a in enumerate(poly):
                a = np.asarray(a, dtype=float)
                c, l = grille.vers_pixels(a[:, 0], a[:, 1])
                points = list(zip((c - j0 - 0.5).tolist(), (l - i0 - 0.5).tolist()))
                if len(points) >= 3:
                    dessin.polygon(points, fill=1 if k == 0 else 0)
            m = np.asarray(masque, dtype=bool)
            if m.any():
                sortie[i0:i1, j0:j1][m] = valeur
    return sortie


def ecrire_json(chemin: Path, donnees) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
