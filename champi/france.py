"""Habitat de la France métropolitaine, par blocs de 512 × 512 cases de 50 m.

Construit dans GitHub Actions (`.github/workflows/habitat.yml`), jamais sur le poste :
les sources brutes pèsent une vingtaine de Go. Chaque bloc est indépendant (ses sources
sont lues dans son emprise) : la construction se répartit sur des dizaines de tâches.

    python -m champi.france preparer --groupes 40   # communes, blocs à construire, groupes
    python -m champi.france groupe 7                # construit les blocs du groupe 7
    python -m champi.france bloc 18_156             # un seul bloc (essai)
    python -m champi.france assembler               # index des blocs, échantillon national

La construction est INCRÉMENTALE : le workflow extrait d'abord la release publiée dans
`habitat/`, et seuls les blocs qui lui manquent sont construits, puis ajoutés. Une
construction interrompue (service saturé, délai dépassé) publie ce qu'elle a fait ; la
suivante complète. Changer `FORMAT` (ou `--tout`) reconstruit tout.

Un bloc = trois PNG RGB, lus tels quels par le site (calcul dans le navigateur) et par
l'export quotidien (échantillon) :

    a : R, G = altitude + 1000 (16 bits) ; B = essence | ouverte << 4 | public << 5
    b : R = pente (°) ; G = ensoleillement × 100 + 100 ; B = roche | orientation << 2
    c : R, G = commune (index national, 16 bits) ; B = zone protégée (index du bloc)
    d : niveaux de gris, bits 0-6 = pH du sol × 10 (0 = inconnu), bit 7 = zone urbanisée (`sol.py`) ;
        ajoutée après coup aux blocs déjà publiés (`python -m champi.sol blocs`) : pas de FORMAT

Hors forêt, `a` et `b` valent zéro (rien à calculer, et l'image se comprime bien).
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from . import sol
from .config import CACHE, PAS_FIN, RACINE
from .grille import Grille
from .habitat import forets, forets_publiques, relief, roches, zones_protegees
from .sources import GEOPF_WFS, http_get, rasteriser, wfs_geopf

FORMAT = 1                            # à changer avec le format ou le calcul d'un bloc : tout est refait
BLOC = 512
COTE = BLOC * PAS_FIN                 # 36 864 m Mercator, environ 25 km au sol
ECHANTILLON = 4                       # une case sur 4 × 4 pour l'export quotidien
SORTIE = RACINE / "habitat"           # non versionné : publié comme asset d'une release
ALTITUDE_DECALAGE = 1000              # altitudes de -1000 à 64 535 m sur 16 bits

COMMUNES = "ADMINEXPRESS-COG-CARTO.LATEST:commune"
DEPARTEMENTS = "ADMINEXPRESS-COG-CARTO.LATEST:departement"


@dataclass(frozen=True)
class Bloc:
    bx: int
    by: int

    @property
    def nom(self) -> str:
        return f"{self.bx}_{self.by}"

    @classmethod
    def depuis_nom(cls, nom: str) -> "Bloc":
        bx, by = nom.split("_")
        return cls(int(bx), int(by))

    def grille(self) -> Grille:
        return Grille(self.bx * COTE, (self.by + 1) * COTE, PAS_FIN, BLOC, BLOC)


def bloc_de(x: float, y: float) -> Bloc:
    return Bloc(int(np.floor(x / COTE)), int(np.floor(y / COTE)))


# --- Préparation --------------------------------------------------------------------

def _wfs_attributs(couche: str, proprietes: str) -> list[dict]:
    """Toutes les entités d'une couche, sans géométrie (paginé)."""
    sortie, debut = [], 0
    while True:
        lot = http_get(GEOPF_WFS, {
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": couche,
            "OUTPUTFORMAT": "application/json", "PROPERTYNAME": proprietes,
            "COUNT": 5000, "STARTINDEX": debut, "SORTBY": "code_insee",
        }, delai=180, attendre_json=True)["features"]
        sortie.extend(f["properties"] for f in lot)
        if len(lot) < 5000:
            return sortie
        debut += 5000


def communes_nationales() -> list[dict]:
    """Communes de métropole (Corse comprise), triées par code INSEE : l'index national est
    la position + 1 (0 = hors de France)."""
    brut = _wfs_attributs(COMMUNES, "code_insee,nom_officiel,code_insee_du_departement")
    # Outre-mer exclu, Saint-Pierre-et-Miquelon compris (département « NR », code INSEE 975..).
    garde = [{"insee": c["code_insee"], "nom": c["nom_officiel"], "dep": c["code_insee_du_departement"]}
             for c in brut if not c["code_insee"].startswith("97")]
    return sorted(garde, key=lambda c: c["insee"])


def blocs_de_france() -> list[str]:
    """Blocs qui touchent un département de métropole (rastérisation au 1/16 de bloc)."""
    emprise = Grille(-20 * COTE, 182 * COTE, COTE / 16, 52 * 16, 48 * 16)
    deps = wfs_geopf(DEPARTEMENTS, emprise)
    deps = [d for d in deps if not d["properties"]["code_insee"].startswith("97")]
    masque = rasteriser([(d["geometry"], 1) for d in deps], emprise).astype(bool)
    lignes, colonnes = np.nonzero(masque)
    xs = emprise.x0 + (colonnes + 0.5) * emprise.pas
    ys = emprise.y1 - (lignes + 0.5) * emprise.pas
    noms = {bloc_de(x, y).nom for x, y in zip(xs, ys)}
    return sorted(noms, key=lambda n: tuple(map(int, n.split("_"))))


def publie() -> dict | None:
    """L'index de la release publiée (extraite dans `habitat/`), s'il est au FORMAT courant."""
    chemin = SORTIE / "blocs.json"
    if not chemin.exists():
        return None
    index = json.loads(chemin.read_text(encoding="utf-8"))
    return index if index.get("format") == FORMAT else None


def preparer(groupes: int, tout: bool = False) -> list[int]:
    SORTIE.mkdir(parents=True, exist_ok=True)
    base = None if tout else publie()
    blocs = blocs_de_france()
    if base:
        # Les blocs publiés renvoient aux index de SA liste de communes : on la garde.
        faits = set(base["blocs"]) | set(base.get("vides", []))
        a_construire = [b for b in blocs if b not in faits]
    else:
        com = communes_nationales()
        (SORTIE / "communes.json").write_text(json.dumps(com, ensure_ascii=False), encoding="utf-8")
        a_construire = blocs
    groupes = min(groupes, len(a_construire))
    # Répartition entrelacée : les blocs voisins (souvent de même densité) vont à des groupes
    # différents, pour que les tâches durent à peu près autant.
    liste = {"blocs": blocs, "incremental": base is not None, "a_construire": a_construire,
             "groupes": [a_construire[g::groupes] for g in range(groupes)]}
    (SORTIE / "liste.json").write_text(json.dumps(liste), encoding="utf-8")
    print(f"{len(blocs)} blocs, {len(a_construire)} à construire en {groupes} groupes"
          + (" (complément de la release publiée)" if base else ""))
    return list(range(groupes))


# --- Un bloc ------------------------------------------------------------------------

def _ecrire(chemin: Path, rgb: np.ndarray) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb.astype(np.uint8), mode="RGB").save(chemin, optimize=True)


def _nettoyer(cle: str) -> None:
    for f in CACHE.glob(f"*_{cle}.*"):
        f.unlink()


def construire_bloc(nom: str, index_communes: dict[str, int]) -> dict | None:
    """Construit un bloc ; renvoie ses métadonnées, ou None s'il n'a aucune forêt en France."""
    bloc = Bloc.depuis_nom(nom)
    g = bloc.grille()
    cle = f"bloc{nom}"
    try:
        com_geo = wfs_geopf(COMMUNES, g)
        commune = rasteriser([(f["geometry"], index_communes[f["properties"]["code_insee"]])
                              for f in com_geo if f["properties"]["code_insee"] in index_communes],
                             g, dtype=np.uint16)
        if not (commune > 0).any():
            return None
        essence, ouverte = forets(g, cle)
        foret = (essence > 0) & (commune > 0)
        if not foret.any():
            return None
        alt, pente, ens, orientation = relief(g, cle, marge=1)
        roche, _ = roches(g)
        protege, protections = zones_protegees(g, cle)
        public = forets_publiques(g, cle)
    finally:
        _nettoyer(cle)

    altitude = np.nan_to_num(alt, nan=0.0).round().astype(np.int32) + ALTITUDE_DECALAGE
    altitude = np.where(foret, np.clip(altitude, 0, 65535), 0).astype(np.uint16)
    pente8 = np.where(foret, np.clip(pente, 0, 90).round(), 0).astype(np.uint8)
    ens8 = np.where(foret, np.clip(ens * 100, -100, 100).round() + 100, 0).astype(np.uint8)
    a = np.stack([altitude >> 8, altitude & 255,
                  np.where(foret, essence | (ouverte.astype(np.uint8) << 4) | (public.astype(np.uint8) << 5), 0)], -1)
    b = np.stack([pente8, ens8, np.where(foret, roche | (orientation << 2), 0)], -1)
    c = np.stack([commune >> 8, commune & 255, protege], -1)
    for lettre, rgb in (("a", a), ("b", b), ("c", c)):
        _ecrire(SORTIE / "blocs" / f"{nom}_{lettre}.png", rgb)
    d = sol.couche_d(g)
    sol.ecrire_couche(SORTIE / "blocs" / f"{nom}_d.png", d)

    # Échantillon pour l'export quotidien : une case sur 4 × 4, au centre de chaque carré.
    m = np.zeros_like(foret)
    m[ECHANTILLON // 2::ECHANTILLON, ECHANTILLON // 2::ECHANTILLON] = True
    lig, col = np.nonzero(foret & m)
    lat, lon = g.latitudes()[lig], g.longitudes()[col]
    (SORTIE / "echantillon").mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        SORTIE / "echantillon" / f"{nom}.npz",
        lat=lat.astype(np.float32), lon=lon.astype(np.float32),
        altitude=(altitude[lig, col].astype(np.int32) - ALTITUDE_DECALAGE).astype(np.int16),
        pente=pente8[lig, col], ensoleillement=(ens8[lig, col].astype(np.int16) - 100).astype(np.int8),
        essence=essence[lig, col], ouverte=ouverte[lig, col], roche=roche[lig, col],
        protege=protege[lig, col] > 0, public=public[lig, col], commune=commune[lig, col],
        ph=d[lig, col] & sol.PH, urbain=(d[lig, col] & sol.URBAIN) > 0,
    )
    meta = {"nom": nom, "n_foret": int(foret.sum()), "protections": protections}
    (SORTIE / "meta").mkdir(parents=True, exist_ok=True)
    (SORTIE / "meta" / f"{nom}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta


def _index_communes() -> dict[str, int]:
    com = json.loads((SORTIE / "communes.json").read_text(encoding="utf-8"))
    return {c["insee"]: i + 1 for i, c in enumerate(com)}


def groupe(n: int, passes: int = 3, minutes: float = 150) -> None:
    """Construit les blocs du groupe ; ceux qui échouent (service saturé) sont repris après une
    pause, jusqu'à `passes` fois. Après `minutes`, plus aucun bloc n'est commencé : la tâche
    rend ce qu'elle a fait avant d'être tuée par GitHub, et la construction suivante complète."""
    liste = json.loads((SORTIE / "liste.json").read_text(encoding="utf-8"))
    index = _index_communes()
    t0 = time.time()
    restants = liste["groupes"][n]
    for passe in range(1, passes + 1):
        echecs = []
        for k, nom in enumerate(restants, 1):
            if (SORTIE / "meta" / f"{nom}.json").exists() or (SORTIE / "vides" / nom).exists():
                continue
            if time.time() - t0 > 60 * minutes:
                reste = [b for b in restants[k - 1:] if not (SORTIE / "meta" / f"{b}.json").exists()]
                print(f"::warning title=groupe {n}::délai atteint, {len(reste)} blocs laissés à la "
                      f"construction suivante", flush=True)
                raise SystemExit(1)
            t = time.time()
            try:
                meta = construire_bloc(nom, index)
            except Exception as e:   # un service indisponible : les autres blocs continuent
                print(f"[{k}/{len(restants)}] {nom} : ÉCHEC {e!r}", flush=True)
                if passe == passes:  # annotation GitHub Actions : lisible sans connexion
                    print(f"::error title=bloc {nom}::{type(e).__name__} {str(e)[:300]}", flush=True)
                echecs.append(nom)
                continue
            if meta is None:   # bloc sans forêt en France : on le note pour ne pas le refaire
                (SORTIE / "vides").mkdir(parents=True, exist_ok=True)
                (SORTIE / "vides" / nom).write_text("", encoding="utf-8")
            n_foret = meta["n_foret"] if meta else 0
            print(f"[{k}/{len(restants)}] {nom} : {n_foret} cases boisées ({time.time() - t:.0f} s, "
                  f"total {time.time() - t0:.0f} s)", flush=True)
        if not echecs:
            return
        restants = echecs
        if passe < passes:
            print(f"{len(echecs)} blocs à reprendre après une pause", flush=True)
            time.sleep(120 * passe)
    raise SystemExit(f"{len(restants)} blocs en échec : {', '.join(restants)}")


# --- Assemblage ---------------------------------------------------------------------

def assembler() -> bool:
    """Index et échantillon national : la release publiée (si la construction la complète)
    plus les blocs construits. Les blocs qui manquent encore sont listés, pas bloquants.
    Renvoie False si rien n'a été construit (rien à publier)."""
    liste = json.loads((SORTIE / "liste.json").read_text(encoding="utf-8"))
    base = publie() if liste["incremental"] else None
    metas = dict(base["blocs"]) if base else {}
    vides = set(base.get("vides", [])) if base else set()
    nouveaux = []
    for nom in liste["a_construire"]:
        f = SORTIE / "meta" / f"{nom}.json"
        if f.exists():
            m = json.loads(f.read_text(encoding="utf-8"))
            metas[nom] = {"n_foret": m["n_foret"], "protections": m["protections"]}
            nouveaux.append(nom)
        elif (SORTIE / "vides" / nom).exists():
            vides.add(nom)
            nouveaux.append(nom)
    if not nouveaux or not metas:
        print("::error::aucun bloc construit : rien à publier")
        return False
    manquants = [nom for nom in liste["blocs"] if nom not in metas and nom not in vides]
    index = {
        "construit_le": time.strftime("%Y-%m-%d"), "format": FORMAT,
        "bloc": BLOC, "pas": PAS_FIN, "cote": COTE, "altitude_decalage": ALTITUDE_DECALAGE,
        "blocs": dict(sorted(metas.items())), "vides": sorted(vides), "manquants": manquants,
    }
    # Échantillon : celui de la release (ses blocs ne sont jamais refaits en incrémental),
    # plus celui des blocs construits.
    parties = [dict(np.load(SORTIE / "echantillon.npz"))] if base else []
    parties += [dict(np.load(SORTIE / "echantillon" / f"{nom}.npz")) for nom in nouveaux
                if (SORTIE / "echantillon" / f"{nom}.npz").exists()]
    national = {k: np.concatenate([p[k] for p in parties]) for k in parties[0]}
    np.savez_compressed(SORTIE / "echantillon.npz", **national)
    (SORTIE / "blocs.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n = sum(m["n_foret"] for m in metas.values())
    print(f"{len(metas)} blocs boisés, {n / 1e6:.1f} M cases boisées, échantillon {len(national['lat']) / 1e6:.2f} M")
    if manquants:
        print(f"::warning title=habitat incomplet::{len(manquants)} blocs manquants, complétés à la "
              f"prochaine construction : {', '.join(manquants[:30])}")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sous = ap.add_subparsers(dest="action", required=True)
    p = sous.add_parser("preparer")
    p.add_argument("--groupes", type=int, default=40)
    p.add_argument("--tout", action="store_true", help="ignorer la release publiée, tout reconstruire")
    sous.add_parser("groupe").add_argument("n", type=int)
    sous.add_parser("bloc").add_argument("noms", nargs="+")
    sous.add_parser("assembler")
    a = ap.parse_args()
    if a.action == "preparer":
        print(json.dumps(preparer(a.groupes, a.tout)))
    elif a.action == "groupe":
        groupe(a.n)
    elif a.action == "bloc":
        idx = _index_communes()
        for nom in a.noms:
            t = time.time()
            m = construire_bloc(nom, idx)
            print(nom, m and m["n_foret"], f"{time.time() - t:.0f} s")
    elif not assembler():
        raise SystemExit(1)
