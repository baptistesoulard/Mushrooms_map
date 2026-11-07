"""Le contour des départements, pour la carte de la page des départements : un tracé SVG par
département, simplifié (environ 1 km), en Mercator comme la carte du site.

    python -m champi.carte_departements      # réseau, quelques secondes : data/departements_carte.json
    python -m champi.carte_departements fin  # sans réseau, demande site/habitat/ : data/departements_fin.json

Gardé dans le dépôt : les pages du matin le relisent sans réseau. Source : ADMIN EXPRESS COG
CARTO de l'IGN (Géoplateforme), Licence Ouverte.

`cadre` : l'emprise du dessin en mètres Mercator (ouest, sud, est, nord). La carte de France de
l'accueil (`partage.carte_cadre`) est peinte sur ce cadre et sa marge (`cadre_une`), pour que les
contours s'y posent.
Le fichier du 2026-11-01 n'en avait pas : son cadre, ajouté le 2026-11-07, a été recalé sur les
communes des blocs d'habitat (centre de chaque département, écart moyen d'environ 0,1 unité du dessin).
"""
from __future__ import annotations

import json
import re

import numpy as np

from .config import DATA
from .grille import Grille, lonlat_vers_merc
from .sources import polygones, wfs_geopf

FICHIER = DATA / "departements_carte.json"
COUCHE = "ADMINEXPRESS-COG-CARTO.LATEST:departement"
LARGEUR = 1000                           # largeur du dessin (unités SVG)
TOLERANCE_M = 1800                       # simplification, en mètres Mercator (moins d'une unité du dessin)
AIRE_MIN_M2 = 4e7                        # îlots plus petits (40 km² Mercator) : écartés
MARGE_UNE = 16                           # unités du dessin autour de la France, sur la carte de l'accueil
TOLERANCE_FRONTIERE = 2.5                # unités du dessin (~4 km) : deux tracés simplifiés d'une même limite


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
              "cadre": [round(float(xmin)), round(float(ymax - hauteur / echelle)),
                        round(float(xmin + LARGEUR / echelle)), round(float(ymax))],
              "traces": {c: "".join(trace(a) for a in anneaux[c]) for c in sorted(anneaux)}}
    sortie["frontieres"] = frontieres(sortie["traces"])
    FICHIER.write_text(json.dumps(sortie, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Écrit {FICHIER.name} : {len(anneaux)} départements, {FICHIER.stat().st_size // 1024} Ko")
    return sortie


def lire_traces(d: str) -> list[np.ndarray]:
    """Les anneaux d'un tracé (« Mx yl dx dy … z », au dixième), en coordonnées du dessin."""
    anneaux = []
    for morceau in d.split("M")[1:]:
        n = np.array(re.findall(r"-?\d+(?:\.\d+)?", morceau), dtype=float)
        pts = np.cumsum(n.reshape(-1, 2), axis=0)
        anneaux.append(pts)
    return anneaux


def _distances(points: np.ndarray, anneau: np.ndarray) -> np.ndarray:
    """La distance de chaque point à l'anneau fermé (ses segments)."""
    a, b = anneau, np.roll(anneau, -1, axis=0)
    ab = b - a
    l2 = np.maximum((ab ** 2).sum(axis=1), 1e-9)
    t = np.clip(((points[:, None, :] - a[None]) * ab[None]).sum(axis=2) / l2[None], 0, 1)
    proj = a[None] + t[..., None] * ab[None]
    return np.sqrt(((points[:, None, :] - proj) ** 2).sum(axis=2)).min(axis=1)


def frontieres(traces: dict[str, str], tol: float = TOLERANCE_FRONTIERE) -> list[str]:
    """Les limites ENTRE départements, sans le littoral ni les frontières du pays : les segments
    d'un contour qui longent un autre département (extrémités et milieu à moins de `tol`). Chaque
    département ayant été simplifié seul, une limite commune a deux tracés voisins : on garde celui
    du département au plus petit code. Tracés SVG en unités du dessin, comme `traces`."""
    anneaux = {c: lire_traces(d) for c, d in traces.items()}
    boites = {c: (np.min([a.min(axis=0) for a in l], axis=0) - tol, np.max([a.max(axis=0) for a in l], axis=0) + tol)
              for c, l in anneaux.items()}
    sortie = []
    for code, liste in anneaux.items():
        voisins = [v for v in anneaux if v > code and np.all(boites[v][0] <= boites[code][1])
                   and np.all(boites[code][0] <= boites[v][1])]
        for anneau in liste:
            fin = np.roll(anneau, -1, axis=0)
            milieu = (anneau + fin) / 2
            garde = np.zeros(len(anneau), dtype=bool)
            for v in voisins:
                proche = lambda pts: np.min([_distances(pts, a) for a in anneaux[v]], axis=0) <= tol
                garde |= proche(anneau) & proche(fin) & proche(milieu)
            if not garde.any():
                continue
            # Les suites de segments gardés, en commençant après un segment écarté (anneau fermé).
            depart = int(np.argmin(garde)) if not garde.all() else 0
            ordre = np.roll(np.arange(len(anneau)), -depart)
            suite: list[int] = []
            for i in list(ordre) + ([ordre[0]] if garde.all() else []):
                if garde[i]:
                    suite.append(i)
                    continue
                if suite:
                    sortie.append(_chemin(anneau, suite))
                    suite = []
            if suite:
                sortie.append(_chemin(anneau, suite))
    return sortie


def voisins(traces: dict[str, str], tol: float = TOLERANCE_FRONTIERE, longueur_min: float = 3.0) -> dict[str, list[str]]:
    """Les départements qui se touchent : ceux dont les contours se longent (segments à moins de
    `tol`, comme `frontieres`) sur au moins `longueur_min` unités du dessin (~5 km), pour ne pas
    compter un coin commun. Symétrique, chaque liste triée par code."""
    anneaux = {c: lire_traces(d) for c, d in traces.items()}
    boites = {c: (np.min([a.min(axis=0) for a in l], axis=0) - tol, np.max([a.max(axis=0) for a in l], axis=0) + tol)
              for c, l in anneaux.items()}
    sortie: dict[str, set[str]] = {c: set() for c in anneaux}
    for code, liste in anneaux.items():
        for v in anneaux:
            if v <= code or not (np.all(boites[v][0] <= boites[code][1]) and np.all(boites[code][0] <= boites[v][1])):
                continue
            longueur = 0.0
            for anneau in liste:
                fin = np.roll(anneau, -1, axis=0)
                proche = lambda pts: np.min([_distances(pts, a) for a in anneaux[v]], axis=0) <= tol   # noqa: E731
                garde = proche(anneau) & proche(fin) & proche((anneau + fin) / 2)
                longueur += float(np.hypot(*(fin - anneau)[garde].T).sum())
            if longueur >= longueur_min:
                sortie[code].add(v)
                sortie[v].add(code)
    return {c: sorted(v) for c, v in sortie.items()}


def _chemin(anneau: np.ndarray, segments: list[int]) -> str:
    """Le tracé SVG des segments i → i+1 qui se suivent, au dixième, en relatif comme `traces`."""
    idx = segments + [(segments[-1] + 1) % len(anneau)]
    p = np.round(anneau[idx] * 10).astype(int)
    d = np.diff(p, axis=0)
    return f"M{p[0, 0] / 10:g} {p[0, 1] / 10:g}l" + " ".join(f"{x / 10:g} {y / 10:g}" for x, y in d)


def cadre_une(contours: dict) -> tuple[list[float], list[float]]:
    """La carte de l'accueil : la `viewBox` du dessin (x, y, largeur, hauteur) et l'emprise en
    mètres Mercator (ouest, sud, est, nord) de l'image peinte dessous, le dessin et sa marge."""
    x0, y0, x1, y1 = contours["cadre"]
    par, m = (x1 - x0) / contours["largeur"], MARGE_UNE          # m Mercator par unité du dessin
    return ([-m, -m, contours["largeur"] + 2 * m, contours["hauteur"] + 2 * m],
            [x0 - m * par, y0 - m * par, x1 + m * par, y1 + m * par])


# --- Contours fins, pour la carte de près ------------------------------------------------
#
# `departements_fin.json` : les mêmes limites à ~250 m, tirées des blocs d'habitat (la commune de
# chaque case, rastérisée depuis ADMIN EXPRESS) : un carré de PAS_FIN_CONTOURS cases prend le
# département de la case de son centre ; les limites suivent les bords entre carrés de départements
# différents, lissées à TOLERANCE_FIN. Calé sur les communes de la carte, sans réseau. Pour la carte
# à partir du zoom 9, où le tracé à ~2 km s'écartait des vraies limites.

FICHIER_FIN = DATA / "departements_fin.json"
PAS_FIN_CONTOURS = 4                     # cases de 72 m par carré : 288 m Mercator, ~200 m au sol
TOLERANCE_FIN = 1.2                      # carrés : le lissage des marches de l'escalier
BOUCLE_MIN = 3                           # carrés : une boucle plus petite est un artefact (case isolée)
UNITE_FIN = 10                           # m Mercator par unité des tracés fins


def _departements_raster(habitat, pas: int) -> tuple[np.ndarray, float, float, list[str]]:
    """Le rang (1…) du département de la case au centre de chaque carré de `pas` cases, 0 hors
    commune ; l'origine (ouest, nord) en m Mercator, et les codes des rangs."""
    from PIL import Image
    from .france import BLOC, COTE, Bloc
    communes = json.loads((habitat / "communes.json").read_text(encoding="utf-8"))
    codes = sorted({c["dep"] for c in communes})
    rang = {c: k + 1 for k, c in enumerate(codes)}
    dep_de_commune = np.array([0] + [rang[c["dep"]] for c in communes], dtype=np.int16)
    blocs = [Bloc.depuis_nom(n) for n in json.loads((habitat / "blocs.json").read_text(encoding="utf-8"))["blocs"]]
    bx0, bx1 = min(b.bx for b in blocs), max(b.bx for b in blocs)
    by0, by1 = min(b.by for b in blocs), max(b.by for b in blocs)
    n = BLOC // pas
    grille = np.zeros(((by1 - by0 + 1) * n, (bx1 - bx0 + 1) * n), dtype=np.int16)
    for b in blocs:
        c = np.asarray(Image.open(habitat / "blocs" / f"{b.nom}_c.png").convert("RGB"), dtype=np.int32)
        commune = ((c[..., 0] << 8) | c[..., 1])[pas // 2::pas, pas // 2::pas]
        lig, col = (by1 - b.by) * n, (b.bx - bx0) * n
        grille[lig:lig + n, col:col + n] = dep_de_commune[np.minimum(commune, len(dep_de_commune) - 1)]
    return grille, bx0 * COTE, (by1 + 1) * COTE, codes


def _chainer(segments: list[tuple[tuple[int, int], tuple[int, int]]]) -> list[np.ndarray]:
    """Des segments unitaires de la grille en lignes : on suit chaque chemin d'un bout à l'autre
    (sommets de degré autre que 2), puis les boucles restantes."""
    voisins: dict = {}
    for a, b in segments:
        voisins.setdefault(a, []).append(b)
        voisins.setdefault(b, []).append(a)
    vus: set = set()
    lignes = []

    def suivre(depart, suivant):
        ligne = [depart, suivant]
        vus.add(frozenset((depart, suivant)))
        while len(voisins[ligne[-1]]) == 2:
            prochain = next((v for v in voisins[ligne[-1]] if frozenset((ligne[-1], v)) not in vus), None)
            if prochain is None:
                break
            vus.add(frozenset((ligne[-1], prochain)))
            ligne.append(prochain)
        return np.array(ligne, dtype=float)

    for s, vs in voisins.items():
        if len(vs) != 2:
            for v in vs:
                if frozenset((s, v)) not in vus:
                    lignes.append(suivre(s, v))
    for s, vs in voisins.items():
        for v in vs:
            if frozenset((s, v)) not in vus:
                lignes.append(suivre(s, v))
    return lignes


def _bords(grille: np.ndarray, garder) -> list[tuple]:
    """Les segments (sommets de la grille, (ligne, colonne)) entre deux carrés voisins a ≠ b
    retenus par `garder(a, b)` (tableaux)."""
    segs = []
    a, b = grille[:, :-1], grille[:, 1:]                       # voisins est-ouest : un bord vertical
    for i, j in zip(*np.nonzero((a != b) & garder(a, b))):
        segs.append(((int(i), int(j) + 1), (int(i) + 1, int(j) + 1)))
    a, b = grille[:-1, :], grille[1:, :]                       # voisins nord-sud : un bord horizontal
    for i, j in zip(*np.nonzero((a != b) & garder(a, b))):
        segs.append(((int(i) + 1, int(j)), (int(i) + 1, int(j) + 1)))
    return segs


def construire_fin(habitat=None) -> dict:
    """`departements_fin.json` : les limites entre départements, et le contour entier de chacun
    (côte comprise, pour le département choisi), en tracés relatifs d'unités de UNITE_FIN m
    depuis `origine` (ouest, nord), y vers le sud."""
    from .config import SITE
    from .france import PAS_FIN
    habitat = habitat or SITE / "habitat"
    grille, x0, y1, codes = _departements_raster(habitat, PAS_FIN_CONTOURS)
    pas = PAS_FIN * PAS_FIN_CONTOURS

    def traces(lignes):
        sortie = []
        for l in lignes:
            if np.array_equal(l[0], l[-1]) and np.ptp(l, axis=0).max() < BOUCLE_MIN:
                continue
            if len(l) >= 3 and np.array_equal(l[0], l[-1]):
                l = _simplifier_anneau(l[:-1], TOLERANCE_FIN)
                l = np.vstack([l, l[:1]])
            else:
                l = _simplifier(l, TOLERANCE_FIN)
            p = np.round(l[:, ::-1] * pas / UNITE_FIN).astype(int)        # (colonne, ligne) → unités
            d = np.diff(p, axis=0)
            d = d[(d != 0).any(axis=1)]
            if len(d):
                sortie.append(f"M{p[0, 0]} {p[0, 1]}l" + " ".join(f"{x} {y}" for x, y in d))
        return sortie

    limites = traces(_chainer(_bords(grille, lambda a, b: (a > 0) & (b > 0))))
    par_dep = {}
    for k, code in enumerate(codes, start=1):
        if code.startswith("97") or not (grille == k).any():
            continue
        segs = _bords(grille, lambda a, b, k=k: (a == k) | (b == k))
        par_dep[code] = "".join(traces(_chainer(segs)))
    sortie = {"origine": [x0, y1], "unite": UNITE_FIN, "precision_m": pas, "frontieres": limites,
              "departements": par_dep}
    FICHIER_FIN.write_text(json.dumps(sortie, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Écrit {FICHIER_FIN.name} : {len(limites)} limites, {len(par_dep)} départements, "
          f"{FICHIER_FIN.stat().st_size // 1024} Ko")
    return sortie


def charger_fin() -> dict | None:
    return json.loads(FICHIER_FIN.read_text(encoding="utf-8")) if FICHIER_FIN.exists() else None


def charger() -> dict | None:
    return json.loads(FICHIER.read_text(encoding="utf-8")) if FICHIER.exists() else None


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["fin"]:
        construire_fin()
    else:
        noms = json.loads((DATA / "departements.json").read_text(encoding="utf-8"))
        construire({c for c in noms if not c.startswith("97")})
