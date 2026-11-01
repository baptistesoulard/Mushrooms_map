"""Le contour des départements, pour la carte de la page des départements : un tracé SVG par
département, simplifié (environ 1 km), en Mercator comme la carte du site.

    python -m champi.carte_departements      # réseau, quelques secondes : data/departements_carte.json

Gardé dans le dépôt : les pages du matin le relisent sans réseau. Source : ADMIN EXPRESS COG
CARTO de l'IGN (Géoplateforme), Licence Ouverte.
"""
from __future__ import annotations

import json

import numpy as np

from .config import DATA
from .grille import Grille, lonlat_vers_merc
from .sources import polygones, wfs_geopf

FICHIER = DATA / "departements_carte.json"
COUCHE = "ADMINEXPRESS-COG-CARTO.LATEST:departement"
LARGEUR = 1000                           # largeur du dessin (unités SVG)
TOLERANCE_M = 1800                       # simplification, en mètres Mercator (moins d'une unité du dessin)
AIRE_MIN_M2 = 4e7                        # îlots plus petits (40 km² Mercator) : écartés


def _simplifier(points: np.ndarray, tol: float) -> np.ndarray:
    """Douglas-Peucker, sans dépendance : garde les sommets qui s'écartent de plus de `tol`."""
    garde = np.zeros(len(points), dtype=bool)
    garde[0] = garde[-1] = True
    pile = [(0, len(points) - 1)]
    while pile:
        i, j = pile.pop()
        if j <= i + 1:
            continue
        a, b = points[i], points[j]
        d = b - a
        n = np.hypot(*d) or 1.0
        seg = points[i + 1:j]
        dist = np.abs(d[0] * (seg[:, 1] - a[1]) - d[1] * (seg[:, 0] - a[0])) / n
        k = int(np.argmax(dist))
        if dist[k] > tol:
            garde[i + 1 + k] = True
            pile += [(i, i + 1 + k), (i + 1 + k, j)]
    return points[garde]


def _simplifier_anneau(anneau: np.ndarray, tol: float) -> np.ndarray:
    """Un anneau fermé : ses deux bouts sont le même point, que Douglas-Peucker ne sait pas couper ;
    on le coupe au sommet le plus éloigné du premier, et chaque moitié se simplifie seule."""
    k = int(np.argmax(np.hypot(*(anneau - anneau[0]).T)))
    return np.concatenate([_simplifier(anneau[:k + 1], tol)[:-1], _simplifier(anneau[k:], tol)])


def _aire(points: np.ndarray) -> float:
    x, y = points[:, 0], points[:, 1]
    return abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) / 2


def construire(codes: set[str]) -> dict:
    """`codes` : les départements de la carte (métropole). Le tracé de chacun, et le cadre."""
    x0, y0 = lonlat_vers_merc(-5.5, 41.2)
    x1, y1 = lonlat_vers_merc(9.8, 51.2)
    emprise = Grille(float(x0), float(y1), 1000.0, int((x1 - x0) / 1000) + 1, int((y1 - y0) / 1000) + 1)
    anneaux = {}
    for f in wfs_geopf(COUCHE, emprise):
        code = f["properties"]["code_insee"]
        if code not in codes:
            continue
        for poly in polygones(f["geometry"]):
            ext = np.asarray(poly[0], dtype=float)
            if _aire(ext) >= AIRE_MIN_M2:
                anneaux.setdefault(code, []).append(_simplifier_anneau(ext, TOLERANCE_M))
    tous = np.concatenate([a for liste in anneaux.values() for a in liste])
    xmin, ymin = tous.min(axis=0)
    xmax, ymax = tous.max(axis=0)
    echelle = LARGEUR / (xmax - xmin)
    hauteur = round((ymax - ymin) * echelle)

    def trace(a):
        """Le premier point en absolu, les suivants en relatif (« l »), au dixième : plus court."""
        p = np.round(np.column_stack([(a[:, 0] - xmin) * echelle, (ymax - a[:, 1]) * echelle]) * 10).astype(int)
        d = np.diff(p, axis=0)
        d = d[(d != 0).any(axis=1)]
        return (f"M{p[0, 0] / 10:g} {p[0, 1] / 10:g}l" + " ".join(f"{x / 10:g} {y / 10:g}" for x, y in d) + "z")

    sortie = {"largeur": LARGEUR, "hauteur": hauteur,
              "traces": {c: "".join(trace(a) for a in anneaux[c]) for c in sorted(anneaux)}}
    FICHIER.write_text(json.dumps(sortie, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Écrit {FICHIER.name} : {len(anneaux)} départements, {FICHIER.stat().st_size // 1024} Ko")
    return sortie


def charger() -> dict | None:
    return json.loads(FICHIER.read_text(encoding="utf-8")) if FICHIER.exists() else None


if __name__ == "__main__":
    noms = json.loads((DATA / "departements.json").read_text(encoding="utf-8"))
    construire({c for c in noms if not c.startswith("97")})
