"""Couche « d » des blocs : ce qui s'ajoute à la forêt après coup, sans reconstruire l'habitat.

    python -m champi.sol telecharger        # réseau, ~2 min : data/ph_sol.npz (versionné)
    python -m champi.sol blocs habitat      # écrit la couche « d » des blocs d'une release extraite

Un octet par case : bits 0-6 = pH du sol × 10 (0 = inconnu), bit 7 = zone urbanisée.

- pH du sol : SoilGrids 2.0 (ISRIC, CC-BY 4.0), horizon 0-5 cm, moyenne, environ 250 m. Le
  service WCS rend la grille en latitude/longitude (EPSG:4326) : aucune reprojection, Pillow
  lit le GeoTIFF. La copie versionnée garde la construction indépendante du service. C'est une
  estimation modélisée, pas une mesure : la validation dit si elle aide (especes.SOL_PH).
- Zone urbanisée : Corine Land Cover 2018 (Géoplateforme), classes 1xx (tissu urbain, zones
  industrielles, réseaux, chantiers, espaces verts urbains, sports et loisirs). La BD Forêt
  compte comme forêt tout bois d'un demi-hectare, parcs urbains compris : ces bois-là n'ont pas
  d'indice. Corine ne voit rien sous 25 ha : un vrai massif enclavé dans une ville reste forêt.
"""
from __future__ import annotations

import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from .config import DATA
from .grille import Grille, lonlat_vers_merc
from .sources import http_get, rasteriser, wfs_geopf

WCS = "https://maps.isric.org/mapserv"
EMPRISE = (-5.5, 41.0, 10.5, 51.5)            # lon0, lat0, lon1, lat1 : la France, en degrés entiers
PAS = 0.0025                                   # degrés, environ 200 à 280 m
MORCEAU = 1.0                                  # degrés par requête
FICHIER = DATA / "ph_sol.npz"
CLC = "LANDCOVER.CLC18_FR:clc18_fr"
PH, URBAIN = 127, 128                          # masques de la couche « d »
FILS = 4                                       # requêtes Corine en parallèle : sans brusquer le service


def _morceau(lon: float, lat: float) -> np.ndarray:
    """pH × 10 d'un carré de MORCEAU degrés (coin sud-ouest), 0 là où SoilGrids n'a rien."""
    r = http_get(WCS, {"map": "/map/phh2o.map", "SERVICE": "WCS", "VERSION": "1.0.0", "REQUEST": "GetCoverage",
                       "COVERAGE": "phh2o_0-5cm_mean", "CRS": "EPSG:4326",
                       "BBOX": f"{lon},{lat},{lon + MORCEAU},{lat + MORCEAU}",
                       "RESX": PAS, "RESY": PAS, "FORMAT": "GEOTIFF_INT16"}, delai=120)
    im = Image.open(io.BytesIO(r.content))
    x0, y0 = im.tag_v2[33922][3:5]               # coin nord-ouest du premier pixel
    if abs(x0 - lon) > PAS / 2 or abs(y0 - (lat + MORCEAU)) > PAS / 2:
        raise ValueError(f"grille inattendue en {lon}, {lat} : origine {x0}, {y0}")
    v = np.asarray(im, dtype=np.int32)
    return np.where((v > 0) & (v <= PH), v, 0).astype(np.uint8)


def telecharger() -> None:
    lon0, lat0, lon1, lat1 = EMPRISE
    n = round(MORCEAU / PAS)
    ny, nx = round((lat1 - lat0) / PAS), round((lon1 - lon0) / PAS)
    ph = np.zeros((ny, nx), dtype=np.uint8)
    t0 = time.time()
    for i, lat in enumerate(np.arange(lat1 - MORCEAU, lat0 - 1e-9, -MORCEAU)):
        for j, lon in enumerate(np.arange(lon0, lon1 - 1e-9, MORCEAU)):
            m = _morceau(round(float(lon), 4), round(float(lat), 4))
            ph[i * n:i * n + m.shape[0], j * n:j * n + m.shape[1]] = m[:n, :n]
        print(f"  pH : bande {i + 1}/{round((lat1 - lat0) / MORCEAU)} ({time.time() - t0:.0f} s)", flush=True)
    np.savez_compressed(FICHIER, ph=ph, lon0=lon0, lat1=lat1, pas=PAS)
    connu = ph > 0
    print(f"Écrit {FICHIER.name} : {nx} × {ny}, pH connu sur {connu.mean():.0%}, "
          f"médiane {np.median(ph[connu]) / 10:.1f}")


@lru_cache(maxsize=1)
def _grille() -> tuple[np.ndarray, float, float, float]:
    z = np.load(FICHIER)
    return z["ph"], float(z["lon0"]), float(z["lat1"]), float(z["pas"])


def ph_points(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """pH × 10 au plus proche (0 = inconnu ou hors de la grille)."""
    ph, lon0, lat1, pas = _grille()
    lig = np.floor((lat1 - np.asarray(lat)) / pas).astype(np.int64)
    col = np.floor((np.asarray(lon) - lon0) / pas).astype(np.int64)
    lig, col = np.broadcast_arrays(lig, col)
    dedans = (lig >= 0) & (lig < ph.shape[0]) & (col >= 0) & (col < ph.shape[1])
    out = np.zeros(lig.shape, dtype=np.uint8)
    out[dedans] = np.minimum(ph[lig[dedans], col[dedans]], PH)
    return out


def ph_grille(g: Grille) -> np.ndarray:
    return ph_points(g.latitudes()[:, None], g.longitudes()[None, :])


def urbain_grille(g: Grille) -> np.ndarray:
    """Cases en territoire artificialisé selon Corine Land Cover 2018 (classes 1xx)."""
    entites = [(f["geometry"], 1) for f in wfs_geopf(CLC, g)
               if str(f["properties"].get("code_18") or "").startswith("1")]
    return rasteriser(entites, g).astype(bool)


def couche_d(g: Grille) -> np.ndarray:
    return ph_grille(g) | (urbain_grille(g).astype(np.uint8) << 7)


def ecrire_couche(chemin: Path, d: np.ndarray) -> None:
    Image.fromarray(d, mode="L").save(chemin, optimize=True)


def blocs(dossier: Path) -> None:
    """Écrit la couche « d » de tous les blocs d'une release extraite, et reporte pH et zone
    urbanisée sur l'échantillon (case par case, depuis la même couche)."""
    from .france import COTE, PAS_FIN, Bloc        # france importe sol : import local, pas circulaire
    index = json.loads((dossier / "blocs.json").read_text(encoding="utf-8"))
    ech = dict(np.load(dossier / "echantillon.npz"))
    x, y = lonlat_vers_merc(ech["lon"].astype(np.float64), ech["lat"].astype(np.float64))
    bx, by = np.floor(x / COTE).astype(int), np.floor(y / COTE).astype(int)
    col = np.floor((x - bx * COTE) / PAS_FIN).astype(int)
    lig = np.floor(((by + 1) * COTE - y) / PAS_FIN).astype(int)
    noms = np.array([f"{a}_{b}" for a, b in zip(bx, by)])
    ech_d = np.zeros(len(noms), dtype=np.uint8)

    def un(nom: str) -> tuple[str, np.ndarray]:
        d = couche_d(Bloc.depuis_nom(nom).grille())
        ecrire_couche(dossier / "blocs" / f"{nom}_d.png", d)
        return nom, d

    t0 = time.time()
    with ThreadPoolExecutor(FILS) as ex:
        for k, (nom, d) in enumerate(ex.map(un, index["blocs"]), 1):
            sel = np.nonzero(noms == nom)[0]
            ech_d[sel] = d[lig[sel], col[sel]]
            if k % 100 == 0:
                print(f"  couche d : {k}/{len(index['blocs'])} blocs ({time.time() - t0:.0f} s)", flush=True)
    ech["ph"] = ech_d & PH
    ech["urbain"] = (ech_d & URBAIN) > 0
    np.savez_compressed(dossier / "echantillon.npz", **ech)
    index["couche_d"] = "pH du sol (SoilGrids 2.0, 0-5 cm) et zones urbanisées (Corine Land Cover 2018)"
    (dossier / "blocs.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Couche d de {len(index['blocs'])} blocs ({time.time() - t0:.0f} s) : pH connu sur "
          f"{(ech['ph'] > 0).mean():.0%} de l'échantillon, {ech['urbain'].mean():.1%} des cases boisées en zone urbanisée")


if __name__ == "__main__":
    if sys.argv[1:] == ["telecharger"]:
        telecharger()
    elif sys.argv[1:2] == ["blocs"] and len(sys.argv) == 3:
        blocs(Path(sys.argv[2]))
    else:
        raise SystemExit(__doc__)
