"""La carte publique par zones de 250 m (décision du 2026-11-06) : `data/zones/<bloc>.png`.

Le site est trouvable par les moteurs : la carte que voit tout le monde ne descend pas sous la
zone de 5 × 5 cases (250 m à 46° N, comme les cases font 50 m). Les cases de 50 m restent pour
qui a le mot de passe (`chiffre.py`). Pour que le 50 m ne se refasse pas à partir de ce qui est
publié, les zones ne portent que des agrégats, calculés chaque nuit dans Actions à partir des
blocs de la release, avant leur chiffrement :

- pour chaque espèce de forêt, l'habitat le plus favorable de la zone (le maximum de
  `modele.facteur_habitat` sur ses cases boisées, hors zones urbanisées et protégées) : la zone
  dit « il y a ici de quoi », sans dire où ;
- l'altitude et l'ensoleillement moyens de ces cases, pour ramener la météo à la zone ;
- deux drapeaux : des forêts (protégées comprises), et une majorité de forêts publiques.

Le navigateur multiplie cet habitat par la saison et la météo de la zone (`modele.js`,
`indices`, champ `habitat`), comme pour une case : `tests/test_modele_js.py` vérifie l'égalité.

Un bloc de 512 cases n'est pas un multiple de 5 : la dernière zone de chaque ligne et de chaque
colonne prend les 7 dernières cases, jamais moins de 5. Les zones ne débordent jamais d'un bloc.

Format : un PNG en niveaux de gris de `N` colonnes et `N × (E + 4)` lignes, des plans de N × N
l'un sous l'autre : les E espèces de forêt (habitat × 255, dans l'ordre de `carte.json`
« zones.especes »), l'altitude moyenne + 1000 (octet haut, puis bas), l'ensoleillement × 100 + 100,
les drapeaux (bit 0 : forêt hors zone protégée, donc un indice ; bit 1 : surtout des forêts
publiques ; bit 2 : de la forêt, protégée comprise).

    python -m champi.zones          # après l'export, avant `python -m champi.chiffre`
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from . import especes as E
from . import modele as M
from .config import FACTEUR_ZONE, SITE, SITE_DATA
from .france import ALTITUDE_DECALAGE, BLOC, Bloc
from .sources import ecrire_json

ZONE = FACTEUR_ZONE                   # 5 cases de 50 m
N = BLOC // ZONE                      # 102 zones par côté ; la dernière prend 7 cases
DEBUTS = np.arange(N) * ZONE          # première case de chaque zone (pour reduceat)
PLANS = len(E.DE_FORET) + 4
FORET, PUBLIQUE, BOISEE = 1, 2, 4     # drapeaux
HABITAT = SITE / "habitat"
SORTIE = SITE_DATA / "zones"


def zone_de(i):
    """Rang de la zone d'une ligne (ou colonne) de cases du bloc."""
    return np.minimum(np.asarray(i) // ZONE, N - 1)


def _par_zone(ufunc, v: np.ndarray) -> np.ndarray:
    """`ufunc.reduceat` sur les lignes puis les colonnes : un tableau N × N."""
    return ufunc.reduceat(ufunc.reduceat(v, DEBUTS, axis=0), DEBUTS, axis=1)


def agreger(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray | None, lat: np.ndarray) -> np.ndarray:
    """Les plans d'un bloc (`PLANS × N × N`, octets) à partir de ses couches a, b, c, d (RGB,
    512 × 512 × 3 ; `d` en niveaux de gris, ou None pour une release qui ne l'a pas) et de la
    latitude du centre de chaque ligne de cases."""
    essence = a[..., 2] & 15
    ouverte = (a[..., 2] >> 4) & 1
    public = (a[..., 2] >> 5) & 1
    altitude = ((a[..., 0].astype(np.int32) << 8) | a[..., 1]) - ALTITUDE_DECALAGE
    pente = b[..., 0]
    ensoleillement = (b[..., 1].astype(np.float32) - 100) / 100
    roche = b[..., 2] & 3
    protege = c[..., 2] > 0
    ph = (d & 127) if d is not None else np.zeros_like(essence)
    urbain = (d >> 7).astype(bool) if d is not None else np.zeros(essence.shape, bool)

    boisee = (essence > 0) & ~urbain
    foret = boisee & ~protege
    lats = np.broadcast_to(lat[:, None], essence.shape)
    plans = np.zeros((PLANS, N, N), dtype=np.uint8)
    if foret.any():
        lig, col = np.nonzero(foret)
        for k, esp in enumerate(E.DE_FORET):
            h = np.zeros(essence.shape, dtype=np.float32)
            h[lig, col] = M.facteur_habitat(esp, essence[lig, col], ouverte[lig, col], roche[lig, col],
                                            altitude[lig, col], pente[lig, col], lats[lig, col], ph=ph[lig, col])
            plans[k] = np.round(_par_zone(np.maximum, h) * 255).astype(np.uint8)
    n = _par_zone(np.add, foret.astype(np.int32))
    vide = np.maximum(n, 1)
    alt = np.round(_par_zone(np.add, np.where(foret, altitude, 0).astype(np.float64)) / vide).astype(np.int32)
    sol = np.round(_par_zone(np.add, np.where(foret, ensoleillement, 0).astype(np.float64)) / vide * 100).astype(np.int32)
    alt_code = np.where(n > 0, np.clip(alt + ALTITUDE_DECALAGE, 0, 65535), 0)
    e = len(E.DE_FORET)
    plans[e] = alt_code >> 8
    plans[e + 1] = alt_code & 255
    plans[e + 2] = np.where(n > 0, np.clip(sol + 100, 0, 200), 0)
    publics = _par_zone(np.add, (foret & (public > 0)).astype(np.int32))
    plans[e + 3] = ((n > 0) * FORET | ((n > 0) & (2 * publics >= n)) * PUBLIQUE
                    | (_par_zone(np.add, boisee.astype(np.int32)) > 0) * BOISEE).astype(np.uint8)
    return plans


def latitudes(bloc: Bloc) -> np.ndarray:
    return bloc.grille().latitudes().astype(np.float32)


def _lire(chemin: Path, mode: str = "RGB") -> np.ndarray:
    return np.asarray(Image.open(chemin).convert(mode))


def bloc(nom: str) -> str:
    dossier = HABITAT / "blocs"
    d = dossier / f"{nom}_d.png"
    plans = agreger(_lire(dossier / f"{nom}_a.png"), _lire(dossier / f"{nom}_b.png"), _lire(dossier / f"{nom}_c.png"),
                    _lire(d, "L") if d.exists() else None, latitudes(Bloc.depuis_nom(nom)))
    Image.fromarray(plans.reshape(PLANS * N, N), mode="L").save(SORTIE / f"{nom}.png", optimize=True)
    return nom


def tout() -> None:
    noms = json.loads((SITE_DATA / "carte.json").read_text(encoding="utf-8"))["blocs"]["liste"]
    SORTIE.mkdir(parents=True, exist_ok=True)
    for ancien in SORTIE.glob("*.png"):
        ancien.unlink()
    with ProcessPoolExecutor(max_workers=os.cpu_count() or 2) as ex:
        n = sum(1 for _ in ex.map(bloc, noms, chunksize=8))
    chemin = SITE_DATA / "carte.json"
    carte = json.loads(chemin.read_text(encoding="utf-8"))
    carte["zones"] = {"facteur": ZONE, "n": N, "especes": [e.code for e in E.DE_FORET], "plans": PLANS,
                      "altitude_decalage": ALTITUDE_DECALAGE}
    ecrire_json(chemin, carte)
    print(f"Zones de 250 m : {n} blocs → {SORTIE.relative_to(SITE)}")


if __name__ == "__main__":
    tout()
