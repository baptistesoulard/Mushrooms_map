"""Les forêts publiques nommées (décision du 2026-11-07) : `data/forets_publiques.json.gz`, versionné.

La BD TOPO de l'IGN (couche `foret_publique`, d'après l'ONF) donne le nom et le statut de chaque
forêt relevant du régime forestier : domaniale, ou autre forêt publique (communale, départementale…).
Les pages des départements nomment les plus grandes, avec leurs conditions du jour : à l'échelle
de la forêt entière, jamais une parcelle ni un coin, et jamais une forêt privée.

`python -m champi.forets` refait le fichier (réseau, quelques minutes, depuis le poste ou Actions) :
les forêts d'au moins `SEUIL_HA`, contours simplifiés à `TOLERANCE_M` (l'échantillon de l'export
a une case tous les ~290 m : plus fin ne servirait à rien). Chaque nuit, l'export rattache chaque
forêt aux cases de l'échantillon qu'elle contient (`affecter`), puis calcule son verdict comme celui
d'un département (`redaction.niveau`).
"""
from __future__ import annotations

import gzip
import json
import re
import sys
import time
from datetime import date

import numpy as np

from .carte_departements import _simplifier_anneau
from .config import DATA
from .grille import lonlat_vers_merc
from .sources import GEOPF_WFS, http_get

FICHIER = DATA / "forets_publiques.json.gz"
COUCHE = "BDTOPO_V3:foret_publique"
SOURCE = "IGN, BD TOPO V3 (foret_publique), d'après l'ONF ; Licence Ouverte 2.0"
SEUIL_HA = 100            # surface au sol : plus petit, une forêt n'a que quelques cases d'échantillon
TOLERANCE_M = 100.0       # simplification des contours, en mètres Mercator
TUILE_M = 100_000         # les requêtes, par carrés de 100 km (Mercator)
# La France métropolitaine en Mercator (ouest, sud, est, nord), Corse comprise.
EMPRISE = (-600_000, 5_050_000, 1_100_000, 6_650_000)
POINTS_MIN = 8            # moins de cases d'échantillon (hors zones protégées) : pas de verdict


def nom_propre(toponyme: str) -> str:
    """« Forêt Domaniale de Mervent » → « Forêt domaniale de Mervent » : les mots du statut en
    minuscules, le nom propre tel quel."""
    t = re.sub(r"\s+", " ", toponyme or "").strip()
    return re.sub(r"^(Forêt|Bois) (Domaniale|Départementale|Communale|Sectionale|Indivise|Régionale|"
                  r"Intercommunale|Syndicale)\b", lambda m: f"{m.group(1)} {m.group(2).lower()}", t)


def _lat_moyenne(anneaux: list[np.ndarray]) -> tuple[float, float]:
    y = float(np.mean(np.concatenate([a[:, 1] for a in anneaux])))
    lat = float(np.degrees(2 * np.arctan(np.exp(y / 6378137.0)) - np.pi / 2))
    return y, lat


def _encoder(anneau: np.ndarray) -> list[int]:
    """Un anneau en mètres entiers : le premier point, puis les écarts (fichier compact)."""
    p = np.round(anneau).astype(np.int64)
    d = np.diff(p, axis=0)
    return [int(p[0, 0]), int(p[0, 1])] + [int(v) for v in d.ravel()]


def decoder(code: list[int]) -> np.ndarray:
    v = np.array(code, dtype=np.float64).reshape(-1, 2)
    return np.cumsum(v, axis=0)


def _entites(x0: float, y0: float, x1: float, y1: float) -> list[dict]:
    """Les forêts publiques qui touchent un carré, toutes pages comprises."""
    sortie, debut, page = [], 0, 5000
    while True:
        lot = http_get(GEOPF_WFS, {
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": COUCHE,
            "SRSNAME": "EPSG:3857", "OUTPUTFORMAT": "application/json",
            "PROPERTYNAME": "geometrie,cleabs,toponyme,nature",
            "BBOX": f"{x0},{y0},{x1},{y1},EPSG:3857", "COUNT": page, "STARTINDEX": debut,
        }, delai=180, attendre_json=True).get("features", [])
        sortie.extend(lot)
        if len(lot) < page:
            return sortie
        debut += page


def _foret(f: dict) -> dict | None:
    """Une entité WFS → une forêt du fichier (None sans nom ou trop petite)."""
    p, g = f.get("properties") or {}, f.get("geometry") or {}
    nom = nom_propre(p.get("toponyme") or "")
    if not nom or g.get("type") not in ("Polygon", "MultiPolygon"):
        return None
    polygones = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    surface, anneaux = 0.0, []
    for poly in polygones:
        for k, anneau in enumerate(poly):
            a = np.array(anneau, dtype=np.float64)[:, :2]
            if len(a) < 4:
                continue
            _, lat = _lat_moyenne([a])
            s = abs(float(np.dot(a[:, 0], np.roll(a[:, 1], -1)) - np.dot(np.roll(a[:, 0], -1), a[:, 1]))) / 2
            surface += (s if k == 0 else -s) * np.cos(np.radians(lat)) ** 2 / 1e4
            simple = _simplifier_anneau(a, TOLERANCE_M)
            if len(simple) >= 4:
                anneaux.append(simple)
    if surface < SEUIL_HA or not anneaux:
        return None
    return {"id": p.get("cleabs") or f.get("id"), "nom": nom,
            "nature": "domaniale" if (p.get("nature") or "").lower().startswith("forêt domaniale") else "autre",
            "ha": int(round(surface)), "anneaux": [_encoder(a) for a in anneaux]}


def construire() -> dict:
    """Toutes les forêts publiques d'au moins `SEUIL_HA`, carré par carré (une forêt à cheval
    sur deux carrés n'est gardée qu'une fois)."""
    t0 = time.time()
    x0, y0, x1, y1 = EMPRISE
    forets: dict[str, dict] = {}
    vus = 0
    carres = [(x, y) for x in range(x0, x1, TUILE_M) for y in range(y0, y1, TUILE_M)]
    for k, (x, y) in enumerate(carres):
        for f in _entites(x, y, x + TUILE_M, y + TUILE_M):
            cle = (f.get("properties") or {}).get("cleabs") or f.get("id")
            if cle in forets or cle is None:
                continue
            vus += 1
            if (fo := _foret(f)):
                forets[cle] = fo
        if k % 20 == 0:
            print(f"  {k + 1}/{len(carres)} carrés, {len(forets)} forêts gardées sur {vus} vues "
                  f"({time.time() - t0:.0f} s)", flush=True)
    sortie = {"source": SOURCE, "construit_le": date.today().isoformat(), "seuil_ha": SEUIL_HA,
              "tolerance_m": TOLERANCE_M, "forets": sorted(forets.values(), key=lambda f: f["id"])}
    FICHIER.write_bytes(gzip.compress(json.dumps(sortie, ensure_ascii=False, separators=(",", ":"))
                                      .encode("utf-8"), mtime=0))
    print(f"Écrit {FICHIER.name} : {len(forets)} forêts d'au moins {SEUIL_HA} ha "
          f"({FICHIER.stat().st_size / 1e6:.1f} Mo, {time.time() - t0:.0f} s)")
    return sortie


def charger() -> dict | None:
    return json.loads(gzip.decompress(FICHIER.read_bytes()).decode("utf-8")) if FICHIER.exists() else None


# --- Chaque nuit : quelles cases de l'échantillon dans quelle forêt ------------------------

def dedans(px: np.ndarray, py: np.ndarray, anneaux: list[np.ndarray]) -> np.ndarray:
    """Les points dans les anneaux, règle pair-impair (les trous et les îlots comptent juste)."""
    garde = np.zeros(len(px), dtype=bool)
    for a in anneaux:
        x1, y1 = a[:, 0][None, :], a[:, 1][None, :]
        x2, y2 = np.roll(a[:, 0], -1)[None, :], np.roll(a[:, 1], -1)[None, :]
        X, Y = px[:, None], py[:, None]
        coupe = (y1 > Y) != (y2 > Y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xc = x1 + (Y - y1) * (x2 - x1) / (y2 - y1)
        garde ^= (np.count_nonzero(coupe & (X < xc), axis=1) % 2).astype(bool)
    return garde


def affecter(forets: list[dict], lat: np.ndarray, lon: np.ndarray, departement: np.ndarray,
             libre: np.ndarray) -> list[dict]:
    """Pour chaque forêt, les cases de l'échantillon qu'elle contient hors zones protégées
    (`points`) et son département (celui de la plupart de ses cases, rang de `departement`).
    Les forêts qui n'ont pas `POINTS_MIN` cases libres sont laissées de côté."""
    x, y = lonlat_vers_merc(lon, lat)
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    ordre = np.argsort(x, kind="stable")
    xs = x[ordre]
    sortie = []
    for f in forets:
        anneaux = [decoder(c) for c in f["anneaux"]]
        tout = np.concatenate(anneaux)
        (bx0, by0), (bx1, by1) = tout.min(axis=0), tout.max(axis=0)
        i0, i1 = np.searchsorted(xs, [bx0, bx1])
        cand = ordre[i0:i1]
        cand = cand[(y[cand] >= by0) & (y[cand] <= by1) & libre[cand]]
        if len(cand) < POINTS_MIN:
            continue
        pts = cand[dedans(x[cand], y[cand], anneaux)]
        if len(pts) < POINTS_MIN:
            continue
        dep = int(np.bincount(departement[pts]).argmax())
        sortie.append({"id": f["id"], "nom": f["nom"], "nature": f["nature"], "ha": f["ha"],
                       "departement": dep, "points": pts})
    return sortie


if __name__ == "__main__":
    if sys.argv[1:]:
        raise SystemExit("python -m champi.forets")
    construire()
