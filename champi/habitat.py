"""Construit l'habitat statique du département : relief, forêts, roche, zones protégées.

À lancer à la main, rarement (les sources changent tous les quelques ans) :

    python -m champi.habitat

Écrit `data/habitat_<dép>.npz` (versionné), que le job quotidien relit sans réseau ni
dépendance géographique. Les téléchargements bruts restent dans `cache/` (non versionné).
"""
from __future__ import annotations

import json
import time
import unicodedata
from datetime import date

import numpy as np

from .config import CACHE, DATA, DEPARTEMENT, MARGE_M, NOM_DEPARTEMENT, PAS_FIN, PAS_ZONE
from .grille import Grille, grille_englobante
from .sources import (
    BRGM_WFS, geometrie_lonlat_vers_merc, http_get, json_en_cache, polygones, rasteriser,
    wfs_geopf, wms_bil,
)

# --- Légendes (codes stockés dans le .npz, relus par le site) ----------------------

ESSENCES = {
    0: "Hors forêt",
    1: "Feuillus en mélange",
    2: "Hêtre",
    3: "Chênes",
    4: "Châtaignier",
    5: "Autres feuillus",
    6: "Peupleraie",
    7: "Forêt mixte (feuillus et conifères)",
    8: "Sapin, épicéa",
    9: "Mélèze",
    10: "Pins",
    11: "Douglas",
    12: "Conifères en mélange",
    13: "Lande",
    14: "Coupe ou trouée forestière",
}

_ESSENCE_BDFORET = {
    "Feuillus": 1, "Hêtre": 2, "Chênes décidus": 3, "Chênes sempervirents": 3,
    "Châtaignier": 4, "Robinier": 5, "Peuplier": 6, "Mixte": 7, "Sapin, épicéa": 8,
    "Mélèze": 9, "Pin sylvestre": 10, "Pin laricio, pin noir": 10, "Pin maritime": 10,
    "Pin d'Alep": 10, "Pin à crochets, pin cembro": 10, "Pins mélangés": 10, "Autres pins": 10,
    "Pin autre": 10,
    "Douglas": 11, "Conifères": 12, "Autres conifères autre que pin": 12,
}

ROCHES = {0: "Non renseigné", 1: "Calcaire", 2: "Siliceuse (acide)", 3: "Mixte ou argileuse"}

ORIENTATIONS = {0: "Terrain plat", 1: "Nord", 2: "Nord-est", 3: "Est", 4: "Sud-est",
                5: "Sud", 6: "Sud-ouest", 7: "Ouest", 8: "Nord-ouest"}

PROTECTIONS = {
    "patrinat_rnn:rnn": "Réserve naturelle nationale",
    "patrinat_rnr:rnr": "Réserve naturelle régionale",
    "patrinat_apb:apb": "Arrêté de protection de biotope",
    "patrinat_rb:rb": "Réserve biologique",
    "patrinat_pn:parc_national": "Cœur de parc national",
}


def _retenue(couche: str, p: dict) -> bool:
    """Des parcs nationaux, seul le cœur a une réglementation propre (pas l'aire d'adhésion)."""
    return couche != "patrinat_pn:parc_national" or (p.get("zone") or "").startswith("C")


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


# --- Étapes -------------------------------------------------------------------------

def communes() -> dict:
    return json_en_cache(f"communes_{DEPARTEMENT}", lambda: http_get(
        f"https://geo.api.gouv.fr/departements/{DEPARTEMENT}/communes",
        {"format": "geojson", "geometry": "contour", "fields": "nom,code"},
    ).json())


def grille_du_departement(com: dict) -> Grille:
    pts = np.concatenate([np.asarray(p[0]) for f in com["features"] for p in polygones(f["geometry"])])
    (lon0, lat0), (lon1, lat1) = pts.min(0), pts.max(0)
    return grille_englobante(lon0, lat0, lon1, lat1, PAS_FIN, PAS_ZONE, MARGE_M)


def relief(grille: Grille, cle: str = DEPARTEMENT, marge: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Altitude (RGE ALTI, IGN), pente (°), indice d'ensoleillement [-1, 1], orientation (classe).

    `marge` cases de plus de chaque côté sont lues puis retirées : la pente d'une case de
    bord se calcule alors avec ses vraies voisines (blocs jointifs sans couture).
    """
    chemin = CACHE / f"altitude_{cle}.npy"
    lue = Grille(grille.x0 - marge * grille.pas, grille.y1 + marge * grille.pas, grille.pas,
                 grille.nx + 2 * marge, grille.ny + 2 * marge)
    if chemin.exists():
        alt = np.load(chemin)
    else:
        alt = wms_bil("ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES", lue)
        CACHE.mkdir(parents=True, exist_ok=True)
        np.save(chemin, alt)
    # Hors de France (Suisse, mer), le service renvoie des valeurs négatives de remplissage.
    alt = np.where(alt < -100, np.nan, alt).astype(np.float32)
    grille = lue

    # Le Mercator est conforme : à chaque ligne, même échelle dans les deux directions.
    d = grille.pas_au_sol()[:, None]
    rempli = np.where(np.isnan(alt), np.nanmean(alt) if np.isfinite(alt).any() else 0.0, alt)
    dz_ligne, dz_col = np.gradient(rempli)
    gx = dz_col / d            # dz/dx vers l'est
    gy = -dz_ligne / d         # dz/dy vers le nord (les lignes vont vers le sud)
    pente = np.degrees(np.arctan(np.hypot(gx, gy)))
    # Orientation = direction de la descente, en degrés depuis le nord, sens horaire.
    azimut = (np.degrees(np.arctan2(-gx, -gy)) + 360.0) % 360.0
    ensoleillement = np.sin(np.radians(pente)) * -np.cos(np.radians(azimut))
    classe = (np.floor(((azimut + 22.5) % 360) / 45).astype(np.uint8) + 1)
    classe[pente < 5] = 0
    c = (slice(marge, alt.shape[0] - marge), slice(marge, alt.shape[1] - marge))
    return alt[c], pente.astype(np.float32)[c], ensoleillement.astype(np.float32)[c], classe[c]


def forets(grille: Grille, cle: str = DEPARTEMENT) -> tuple[np.ndarray, np.ndarray]:
    """Essence dominante (codes ESSENCES) et drapeau « forêt ouverte » (BD Forêt V2, IGN)."""
    donnees = json_en_cache(f"bdforet_{cle}", lambda: {
        "type": "FeatureCollection",
        "features": wfs_geopf("LANDCOVER.FORESTINVENTORY.V2:formation_vegetale", grille),
    })
    inconnues: dict[str, int] = {}
    essence, ouverte = [], []
    for f in donnees["features"]:
        p = f["properties"]
        tfv = p.get("tfv_g11") or ""
        nom = p.get("essence") or ""
        if tfv.startswith("Lande"):
            code = 13
        elif "sans couvert" in tfv:
            code = 14
        elif nom in _ESSENCE_BDFORET:
            code = _ESSENCE_BDFORET[nom]
        else:
            if nom not in ("NC",):
                inconnues[nom] = inconnues.get(nom, 0) + 1
            continue  # formations herbacées et non concernées : hors forêt
        essence.append((f["geometry"], code))
        if "ouverte" in tfv:
            ouverte.append((f["geometry"], 1))
    if inconnues:
        print("  essences BD Forêt non classées (ignorées) :", inconnues)
    return rasteriser(essence, grille), rasteriser(ouverte, grille).astype(bool)


def _classe_roche(descr: str) -> int:
    d = _sans_accents(descr)
    if any(m in d for m in ("calcaire", "craie", "dolomie", "gypse")):
        return 1
    if any(m in d for m in ("granite", "gneiss", "schiste", "gres", "sable", "quartz", "micaschiste",
                            "rhyolite", "migmatite")):
        return 2
    return 3


def roches(grille: Grille, cle: str = DEPARTEMENT) -> tuple[np.ndarray, dict]:
    """Lithologie simplifiée au 1/1 000 000 (BRGM), en trois classes de réaction du sol.

    La carte au 1/50 000 (BD Charm-50) serait bien plus fine, mais son téléchargement
    passe par un formulaire : pas scriptable. Le 1/1 000 000 ne distingue que les grands
    ensembles (massifs calcaires, cristallin, molasse) : c'est la variable la plus grossière
    du modèle, et le site le dit.
    """
    def charger():
        ouest, sud, est, nord = _bbox_lonlat(grille)
        r = http_get(BRGM_WFS, {
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
            "TYPENAMES": "ms:LITHO_1M_SIMPLIFIEE", "OUTPUTFORMAT": "geojson",
            "BBOX": f"{sud},{ouest},{nord},{est},urn:ogc:def:crs:EPSG::4326",
        }, delai=120)
        try:
            texte = r.content.decode("utf-8")
        except UnicodeDecodeError:
            texte = r.content.decode("latin-1")
        return json.loads(texte)

    donnees = json_en_cache(f"lithologie_{cle}", charger)
    entites, vues = [], {}
    for f in donnees["features"]:
        descr = f["properties"].get("DESCR") or ""
        code = _classe_roche(descr)
        vues[descr] = ROCHES[code]
        entites.append((geometrie_lonlat_vers_merc(f["geometry"]), code))
    return rasteriser(entites, grille), vues


def _bbox_lonlat(grille: Grille):
    b = grille.bornes_lonlat()
    return b["ouest"], b["sud"], b["est"], b["nord"]


def zones_protegees(grille: Grille, cle: str = DEPARTEMENT) -> tuple[np.ndarray, list[dict]]:
    """Espaces protégés à réglementation propre (INPN) : index dans la liste renvoyée (0 = aucun)."""
    entites, liste = [], []
    for couche, nature in PROTECTIONS.items():
        lot = json_en_cache(f"{couche.split(':')[1]}_{cle}", lambda c=couche: {
            "features": wfs_geopf(c, grille)})["features"]
        for f in lot:
            p = f["properties"]
            if not _retenue(couche, p):
                continue
            nom = p.get("nom_site") or p.get("nom") or p.get("NOM_SITE") or nature
            liste.append({"nature": nature, "nom": nom})
            entites.append((f["geometry"], len(liste)))
    if len(liste) > 255:
        raise ValueError("plus de 255 zones protégées : passer le raster en uint16")
    return rasteriser(entites, grille), liste


def forets_publiques(grille: Grille, cle: str = DEPARTEMENT) -> np.ndarray:
    """Forêts relevant du régime forestier (domaniales, communales…), BD TOPO (IGN)."""
    lot = json_en_cache(f"foret_publique_{cle}", lambda: {
        "features": wfs_geopf("BDTOPO_V3:foret_publique", grille)})["features"]
    return rasteriser([(f["geometry"], 1) for f in lot], grille).astype(bool)


def construire() -> None:
    t0 = time.time()
    com = communes()
    grille = grille_du_departement(com)
    print(f"Grille {grille.nx} × {grille.ny} cases de {grille.pas:.0f} m Mercator")

    noms_communes = [f["properties"]["nom"] for f in com["features"]]
    commune = rasteriser(
        [(geometrie_lonlat_vers_merc(f["geometry"]), i + 1) for i, f in enumerate(com["features"])],
        grille, dtype=np.uint16)
    print(f"  communes : {len(noms_communes)}  ({time.time() - t0:.0f} s)")

    alt, pente, ensoleillement, orientation = relief(grille)
    print(f"  relief : {np.nanmin(alt):.0f} à {np.nanmax(alt):.0f} m  ({time.time() - t0:.0f} s)")

    essence, ouverte = forets(grille)
    print(f"  forêts : {np.mean(essence[commune > 0] > 0):.0%} du département  ({time.time() - t0:.0f} s)")

    roche, lithologies = roches(grille)
    protege, protections = zones_protegees(grille)
    public = forets_publiques(grille)
    print(f"  roches, {len(protections)} zones protégées, forêts publiques  ({time.time() - t0:.0f} s)")

    DATA.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        DATA / f"habitat_{DEPARTEMENT}.npz",
        altitude=np.nan_to_num(alt, nan=-1).round().astype(np.int16),
        pente=np.clip(pente, 0, 90).round().astype(np.uint8),
        ensoleillement=np.clip(ensoleillement * 100, -100, 100).round().astype(np.int8),
        orientation=orientation,
        essence=essence,
        ouverte=ouverte,
        roche=roche,
        protege=protege,
        public=public,
        commune=commune,
    )
    meta = {
        "departement": DEPARTEMENT,
        "nom": NOM_DEPARTEMENT,
        "construit_le": date.today().isoformat(),
        "grille": grille.en_dict(),
        "essences": ESSENCES,
        "roches": ROCHES,
        "lithologies_brgm": lithologies,
        "orientations": ORIENTATIONS,
        "protections": protections,
        "communes": noms_communes,
        "sources": {
            "relief": "IGN, RGE ALTI (Géoplateforme, ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES), Licence Ouverte",
            "forets": "IGN, BD Forêt V2 (LANDCOVER.FORESTINVENTORY.V2), Licence Ouverte",
            "roches": "BRGM, lithologie simplifiée au 1/1 000 000 (LITHO_1M_SIMPLIFIEE), Licence Ouverte",
            "protections": "INPN / PatriNat, via la Géoplateforme (RNN, RNR, APB, RB)",
            "forets_publiques": "IGN, BD TOPO V3 (foret_publique), Licence Ouverte",
            "communes": "geo.api.gouv.fr (IGN, ADMIN EXPRESS), Licence Ouverte",
        },
    }
    (DATA / f"habitat_{DEPARTEMENT}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    taille = (DATA / f"habitat_{DEPARTEMENT}.npz").stat().st_size / 1e6
    print(f"Écrit data/habitat_{DEPARTEMENT}.npz ({taille:.1f} Mo) en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    construire()
