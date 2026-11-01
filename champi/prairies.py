"""Les prés de France, pour les champignons des champs (coulemelle, rosé des prés).

    python -m champi.prairies            # réseau, ~15 min : data/prairies.npz (versionné)

Un point tous les 576 m Mercator (environ 400 m au sol) dans les prairies, pelouses et
mosaïques agricoles de Corine Land Cover 2018 (Géoplateforme), avec son altitude (RGE ALTI de
l'IGN, lue à 0,004°) et sa commune (couche « c » des blocs d'habitat). Gardé dans le dépôt,
comme le pH du sol : le calcul de chaque matin n'appelle aucun service.

Ces points ne sont jamais publiés : les prés sont presque tous privés (pâtures d'éleveurs),
et la carte n'en dit que ce qui vaut pour un département ou une commune.

Demande l'habitat de la release (`site/habitat/`), pour les communes.
"""
from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from .config import DATA, PAS_FIN
from .france import BLOC, COTE, Bloc
from .grille import Grille, lonlat_vers_merc, merc_vers_lonlat
from .sources import GEOPF_WMS_R, http_get, rasteriser, wfs_geopf

FICHIER = DATA / "prairies.npz"
PAS = 8 * PAS_FIN                       # 576 m Mercator : 64 × 64 points par bloc
PAR_BLOC = BLOC // 8
CLC = "LANDCOVER.CLC18_FR:clc18_fr"
# Les milieux retenus, codés de 1 à 5 dans le fichier (les affinités sont dans especes.py).
MILIEUX = {
    "231": 1,   # prairies et autres surfaces toujours en herbe à usage agricole
    "321": 2,   # pelouses et pâturages naturels
    "242": 3,   # systèmes culturaux et parcellaires complexes (le bocage y tombe souvent)
    "243": 4,   # surfaces agricoles interrompues par des espaces naturels importants
    "324": 5,   # forêt et végétation arbustive en mutation (clairières, coupes, friches)
}
NOMS_MILIEUX = {1: "Prairies", 2: "Pelouses et pâturages naturels", 3: "Bocage et parcellaire complexe",
                4: "Mosaïque agricole et naturelle", 5: "Clairières et friches"}
RELIEF = "ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES"
EMPRISE = (41.0, 51.5, -5.6, 10.0)      # sud, nord, ouest, est
PAS_ALT = 0.004                         # degrés de latitude
TUILE = 1000
FILS = 4                                # requêtes Corine en parallèle : sans brusquer le service


def altitudes_france() -> tuple[np.ndarray, float, float, float, float]:
    """Le relief de la France en latitude/longitude (ligne 0 au nord), NaN hors de France."""
    sud, nord, ouest, est = EMPRISE
    dlat, dlon = PAS_ALT, PAS_ALT * 4 / 3
    ny, nx = int(np.ceil((nord - sud) / dlat)), int(np.ceil((est - ouest) / dlon))
    alt = np.full((ny, nx), np.nan, dtype=np.float32)
    for i0 in range(0, ny, TUILE):
        for j0 in range(0, nx, TUILE):
            h, w = min(TUILE, ny - i0), min(TUILE, nx - j0)
            n, o = nord - i0 * dlat, ouest + j0 * dlon
            r = http_get(GEOPF_WMS_R, {
                "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": RELIEF, "STYLES": "",
                "CRS": "EPSG:4326", "WIDTH": w, "HEIGHT": h, "BBOX": f"{n - h * dlat},{o},{n},{o + w * dlon}",
                "FORMAT": "image/x-bil;bits=32"}, delai=180)
            if not r.headers.get("Content-Type", "").startswith("image/x-bil"):
                raise RuntimeError(f"relief : réponse inattendue {r.text[:200]}")
            alt[i0:i0 + h, j0:j0 + w] = np.frombuffer(r.content, dtype="<f4").reshape(h, w)
    return np.where(alt < -100, np.nan, alt), nord, ouest, dlat, dlon


def empreinte_communes(communes: list[dict]) -> str:
    """Les points portent le numéro de leur commune dans la liste de l'habitat : son empreinte dit
    si le fichier vaut encore pour l'habitat publié."""
    return hashlib.sha1("|".join(c["insee"] for c in communes).encode()).hexdigest()[:16]


def milieux_bloc(nom: str) -> np.ndarray:
    """Le milieu de chaque point du bloc (0 : ni pré, ni pelouse, ni mosaïque agricole)."""
    b = Bloc.depuis_nom(nom)
    g = Grille(b.bx * COTE, (b.by + 1) * COTE, PAS, PAR_BLOC, PAR_BLOC)
    entites = [(f["geometry"], MILIEUX[c]) for f in wfs_geopf(CLC, g)
               if (c := str(f["properties"].get("code_18") or "")) in MILIEUX]
    return rasteriser(entites, g)


def construire(habitat) -> dict:
    index = json.loads((habitat / "blocs.json").read_text(encoding="utf-8"))
    noms = sorted(index["blocs"])
    t0 = time.time()
    alt, nord, ouest, dlat, dlon = altitudes_france()
    print(f"Relief : {alt.shape[1]} × {alt.shape[0]} ({time.time() - t0:.0f} s)", flush=True)
    sortie = {k: [] for k in ("ix", "iy", "altitude", "commune", "milieu")}
    # Le centre de chaque point dans la case de 72 m qui le porte (couche « c » des blocs).
    centre = np.arange(PAR_BLOC) * 8 + 4
    with ThreadPoolExecutor(FILS) as ex:
        for k, (nom, milieu) in enumerate(zip(noms, ex.map(milieux_bloc, noms)), 1):
            b = Bloc.depuis_nom(nom)
            c = np.asarray(Image.open(habitat / "blocs" / f"{nom}_c.png").convert("RGB"), dtype=np.int32)
            commune = ((c[..., 0] << 8) | c[..., 1])[np.ix_(centre, centre)]
            lig, col = np.nonzero((milieu > 0) & (commune > 0))
            ix = b.bx * PAR_BLOC + col                         # colonne Mercator, depuis l'origine
            iy = (b.by + 1) * PAR_BLOC - 1 - lig               # ligne Mercator, vers le nord
            lon, lat = merc_vers_lonlat((ix + 0.5) * PAS, (iy + 0.5) * PAS)
            i = np.clip(np.round((nord - lat) / dlat - 0.5).astype(int), 0, alt.shape[0] - 1)
            j = np.clip(np.round((lon - ouest) / dlon - 0.5).astype(int), 0, alt.shape[1] - 1)
            a = alt[i, j]
            garde = np.isfinite(a)
            for cle, v in (("ix", ix), ("iy", iy), ("altitude", np.round(a)), ("commune", commune[lig, col]),
                           ("milieu", milieu[lig, col])):
                sortie[cle].append(v[garde])
            if k % 100 == 0:
                print(f"  {k}/{len(noms)} blocs ({time.time() - t0:.0f} s)", flush=True)
    types = {"ix": np.int16, "iy": np.int16, "altitude": np.int16, "commune": np.uint16, "milieu": np.uint8}
    pts = {k: np.concatenate(v).astype(types[k]) for k, v in sortie.items()}
    ordre = np.lexsort((pts["ix"], pts["iy"]))                 # trié : il se comprime mieux
    pts = {k: v[ordre] for k, v in pts.items()}
    communes = json.loads((habitat / "communes.json").read_text(encoding="utf-8"))
    np.savez_compressed(FICHIER, pas=PAS, communes=empreinte_communes(communes), **pts)
    n = len(pts["ix"])
    print(f"Écrit {FICHIER.name} : {n} points ({n * (PAS / 1000) ** 2 * 0.5:.0f} km² environ), "
          f"{', '.join(f'{NOMS_MILIEUX[m]} {np.mean(pts['milieu'] == m):.0%}' for m in NOMS_MILIEUX)} "
          f"({time.time() - t0:.0f} s)")
    return pts


def charger() -> dict[str, np.ndarray]:
    """Les points des prés : latitude, longitude, altitude, commune, milieu."""
    z = np.load(FICHIER)
    lon, lat = merc_vers_lonlat((z["ix"].astype(np.float64) + 0.5) * float(z["pas"]),
                                (z["iy"].astype(np.float64) + 0.5) * float(z["pas"]))
    # Quelques dizaines de points de bord de mer reviennent du service sous -50 m : ramenés à 0.
    return {"lat": lat, "lon": lon, "altitude": np.maximum(z["altitude"], 0).astype(np.float32),
            "commune": z["commune"], "milieu": z["milieu"], "communes": str(z["communes"])}


if __name__ == "__main__":
    from .export_france import HABITAT
    construire(HABITAT)
