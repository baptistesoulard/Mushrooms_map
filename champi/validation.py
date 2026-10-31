"""Le modèle face aux observations : les règles, réglées d'avance, sont-elles vérifiées ?

    python -m champi.validation observations   # GBIF seul (réseau, ~1 h la 1re fois)
    python -m champi.validation                # tout : GBIF, météo passée, tests

Demande l'habitat national dans `site/habitat/` (asset de la release « habitat »).

Aucun paramètre n'est ajusté ici : on mesure. Deux questions, deux plans d'expérience, sur
la France entière et, à part, sur les régions dont les règles sont les moins sûres.

1. HABITAT. Les zones où l'espèce a été observée sont-elles mieux notées que les zones où
   d'AUTRES champignons ont été observés ? Le fond « groupe cible » (Phillips et al. 2009)
   neutralise le biais d'observation : mêmes observateurs, mêmes sentiers. Référence
   naïve : la seule part de forêt de la zone. Une région se compare à son propre fond.

2. MÉTÉO. Le jour d'une observation, l'indice météo était-il meilleur que les autres jours
   au même endroit ? Plan cas-croisé (Maclure 1991) : chaque observation est comparée à
   des jours témoins du même lieu, de la même année et du MÊME JOUR DE LA SEMAINE (les
   observateurs sortent surtout le week-end). Deux jeux de témoins :
   - même mois : la météo apporte-t-elle quelque chose à saison égale ?
   - toute la saison : l'indice complet bat-il le seul calendrier ?

Mesure : l'AUC, probabilité qu'un cas tiré au hasard soit mieux noté qu'un témoin tiré au
hasard (0,5 = pas mieux que le hasard). Intervalles à 95 % par rééchantillonnage.

Limites, publiées avec les chiffres : observations peu nombreuses et ponctuelles (une
sortie mycologique est souvent fixée d'avance, quelle que soit la météo), coordonnées
parfois approximatives, météo passée issue de réanalyses (ERA5-Land, ~9 km ; pluie d'ERA5,
~25 km) et non des prévisions utilisées en direct.
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

import numpy as np
import omfiles
import pandas as pd
import requests
from PIL import Image

from . import especes as E
from . import modele as M
from .config import CACHE, DATA, PAS_FIN, USER_AGENT
from .depot import decalage_paris
from .export import COUVERTURE_PLEINE
from .export_france import HABITAT
from .france import ALTITUDE_DECALAGE, BLOC, COTE, Bloc
from .grille import lonlat_vers_merc
from .sources import http_get

DOSSIER = CACHE / "validation"     # caches nationaux (observations, météo passée) : hors git
GBIF = "https://api.gbif.org/v1"
PAYS = "FR"
ANNEES = (1995, 2026)
# Habitat : une zone de 250 m autour du point ; une position à plus d'1 km n'y dit rien.
# Météo : la réanalyse a une maille de 9 km ; 10 km suffisent pour être dans le bon secteur.
# Seules comptent les incertitudes DÉCLARÉES : sans elle, une donnée peut être le centre d'une
# maille de 10 km (inventaires), et le filtre se fait chez GBIF, pour les cas comme pour le fond.
INCERTITUDE_HABITAT_M = 1000
INCERTITUDE_METEO_M = 10000
GROUPES = {
    "cepe": ["Boletus edulis", "Boletus pinophilus", "Boletus aereus", "Boletus reticulatus"],
    "girolle": ["Cantharellus cibarius", "Cantharellus pallens", "Cantharellus friesii"],
    "trompette": ["Craterellus cornucopioides"],
    "pied_de_mouton": ["Hydnum repandum", "Hydnum rufescens"],
    "morille": ["Morchella"],
}
# Les règles du Midi (pin d'Alep, chênes verts, pin maritime) sont les moins sûres : elles
# sont vérifiées à part, chaque région face à son propre fond. La Haute-Savoie reste comme
# point de comparaison avec la première validation.
REGIONS = {
    "france": ("France métropolitaine", None),
    "mediterranee": ("Pourtour méditerranéen",
                     {"06", "13", "83", "84", "30", "34", "11", "66", "2A", "2B"}),
    "landes": ("Landes de Gascogne", {"33", "40", "47"}),
    "haute_savoie": ("Haute-Savoie", {"74"}),
}
MIN_CAS = 20          # en dessous, on publie le nombre, pas l'AUC
TIRAGES = 1000
GRAINE = 20261030
MAX_PAGINATION = 8_000    # observations par requête paginée (voir `_pages`)


# --- Observations GBIF --------------------------------------------------------------

def cle_taxon(nom: str) -> int:
    r = http_get(f"{GBIF}/species/match", {"name": nom, "kingdom": "Fungi"}).json()
    if r.get("matchType") != "EXACT":
        raise ValueError(f"taxon GBIF introuvable : {nom}")
    return int(r["usageKey"])


def _pages(cles: list[int], incertitude_max: float):
    """Toutes les occurrences, par périodes de moins de MAX_PAGINATION : au-delà d'environ
    10 000, GBIF met plusieurs minutes à rendre une page (mesuré le 2026-10-31). Une période
    trop chargée est coupée en deux (les bornes de `eventDate` sont incluses)."""
    base = [("country", PAYS), ("hasCoordinate", "true"), ("hasGeospatialIssue", "false"),
            ("coordinateUncertaintyInMeters", f"0,{incertitude_max:.0f}")] + [("taxonKey", c) for c in cles]

    def periode(d0: date, d1: date):
        p = base + [("eventDate", f"{d0.isoformat()},{d1.isoformat()}")]
        n = http_get(f"{GBIF}/occurrence/search", p + [("limit", 0)], delai=60).json()["count"]
        if n > MAX_PAGINATION and d1 > d0:
            milieu = d0 + (d1 - d0) // 2
            yield from periode(d0, milieu)
            yield from periode(milieu + timedelta(days=1), d1)
            return
        debut = 0
        while debut < n:
            r = http_get(f"{GBIF}/occurrence/search", p + [("limit", 300), ("offset", debut)], delai=60).json()
            yield from r["results"]
            debut += 300
            if r.get("endOfRecords"):
                break

    for annee in range(ANNEES[0], ANNEES[1] + 1):
        yield from periode(date(annee, 1, 1), date(annee, 12, 31))


def telecharger(cles: list[int], nom: str, incertitude_max: float) -> pd.DataFrame:
    """Occurrences de France datées au jour, position connue à `incertitude_max` près."""
    chemin = DOSSIER / f"gbif_{nom}.csv.gz"
    if chemin.exists():
        return pd.read_csv(chemin, parse_dates=["date"])
    lignes = []
    for o in _pages(cles, incertitude_max):
        if not o.get("day"):
            continue
        lignes.append({
            "lat": o["decimalLatitude"], "lon": o["decimalLongitude"],
            "date": f"{o['year']:04d}-{o['month']:02d}-{o['day']:02d}",
            "taxon": o.get("speciesKey") or o.get("taxonKey"), "jeu": o.get("datasetKey"),
            "incertitude": o.get("coordinateUncertaintyInMeters"),
        })
        if len(lignes) % 10_000 == 0:
            print(f"    {nom} : {len(lignes)} observations", flush=True)
    df = pd.DataFrame(lignes)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    DOSSIER.mkdir(parents=True, exist_ok=True)
    df.to_csv(chemin, index=False, compression="gzip")
    return df


def _cles() -> dict[str, list[int]]:
    chemin = DATA / "validation_taxons.json"
    if chemin.exists():
        return json.loads(chemin.read_text(encoding="utf-8"))
    cles = {g: [cle_taxon(n) for n in noms] for g, noms in GROUPES.items()}
    chemin.write_text(json.dumps(cles, indent=1), encoding="utf-8")
    return cles


def observations_especes() -> dict[str, pd.DataFrame]:
    return {g: telecharger(c, g, INCERTITUDE_METEO_M) for g, c in _cles().items()}


def observations() -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    cles = _cles()
    par_espece = observations_especes()
    fond = telecharger([5], "fond_champignons", INCERTITUDE_HABITAT_M)   # 5 = règne Fungi
    exclus = {k for c in cles.values() for k in c}
    # Le fond exclut les cinq groupes (genre Morchella compris : ses espèces ont d'autres clés).
    exclus_especes = set(pd.concat(par_espece.values())["taxon"].dropna().astype(int))
    fond = fond[~fond["taxon"].isin(exclus | exclus_especes)]
    return par_espece, fond


# --- Habitat ------------------------------------------------------------------------

DEMI_ZONE = 2                        # zone de 5 × 5 cases (250 m) centrée sur l'observation
COTE_ZONE = 2 * DEMI_ZONE + 1
CASES_ZONE = COTE_ZONE ** 2


class Blocs:
    """Les blocs d'habitat de la release (`site/habitat/`), décodés à la demande."""

    def __init__(self, dossier=HABITAT):
        self.dossier = dossier
        self.presents = set(json.loads((dossier / "blocs.json").read_text(encoding="utf-8"))["blocs"])
        communes = json.loads((dossier / "communes.json").read_text(encoding="utf-8"))
        self.dep_commune = np.array([""] + [c["dep"] for c in communes], dtype=object)

    def lire(self, nom: str) -> dict:
        """Les trois PNG d'un bloc (format en tête de `france.py`)."""
        a, b, c = (np.asarray(Image.open(self.dossier / "blocs" / f"{nom}_{lettre}.png").convert("RGB"),
                              dtype=np.int32) for lettre in "abc")
        commune = (c[..., 0] << 8) | c[..., 1]
        essence = a[..., 2] & 15
        return {
            "altitude": ((a[..., 0] << 8) | a[..., 1]) - ALTITUDE_DECALAGE,
            "essence": essence, "ouverte": (a[..., 2] >> 4) & 1,
            "pente": b[..., 0], "ensoleillement": (b[..., 1] - 100) / 100, "roche": b[..., 2] & 3,
            "commune": commune, "foret": (essence > 0) & (commune > 0),
        }


def _somme_zone(v: np.ndarray, lig: np.ndarray, col: np.ndarray) -> np.ndarray:
    """Somme de `v` sur la zone centrée en chaque (lig, col), coupée au bord du bloc."""
    s = np.zeros((BLOC + 1, BLOC + 1))
    s[1:, 1:] = np.asarray(v, dtype=np.float64).cumsum(0).cumsum(1)
    l0, l1 = np.clip(lig - DEMI_ZONE, 0, BLOC), np.clip(lig + DEMI_ZONE + 1, 0, BLOC)
    c0, c1 = np.clip(col - DEMI_ZONE, 0, BLOC), np.clip(col + DEMI_ZONE + 1, 0, BLOC)
    return s[l1, c1] - s[l0, c1] - s[l1, c0] + s[l0, c0]


def lieux(df: pd.DataFrame, blocs: Blocs) -> pd.DataFrame:
    """Ce que l'habitat dit de chaque observation : département, case (forêt, altitude,
    ensoleillement), zone de 250 m (part de forêt, indice d'habitat de chaque espèce). Les
    observations hors des blocs construits ou à moitié hors de France sont écartées."""
    df = df.reset_index(drop=True)
    x, y = lonlat_vers_merc(df["lon"].to_numpy(), df["lat"].to_numpy())
    bx, by = np.floor(x / COTE).astype(int), np.floor(y / COTE).astype(int)
    col = np.floor((x - bx * COTE) / PAS_FIN).astype(int)
    lig = np.floor(((by + 1) * COTE - y) / PAS_FIN).astype(int)
    noms = np.array([f"{a}_{b}" for a, b in zip(bx, by)])
    n = len(df)
    cols = {k: np.full(n, np.nan) for k in ("foret_zone", "france_zone", "altitude", "ensoleillement")}
    cols.update({e.code: np.full(n, np.nan) for e in E.ESPECES})
    cols["foret_case"] = np.zeros(n, dtype=bool)
    cols["dep"] = np.full(n, "", dtype=object)
    uniques = [nom for nom in np.unique(noms) if nom in blocs.presents]
    t0 = time.time()
    for k, nom in enumerate(uniques, 1):
        sel = np.nonzero(noms == nom)[0]
        l, c = lig[sel], col[sel]
        b = blocs.lire(nom)
        foret = b["foret"]
        n_f = _somme_zone(foret, l, c)
        cols["foret_zone"][sel] = np.minimum(1.0, n_f / CASES_ZONE)
        cols["france_zone"][sel] = _somme_zone(b["commune"] > 0, l, c) / CASES_ZONE
        cols["foret_case"][sel] = foret[l, c]
        cols["altitude"][sel] = b["altitude"][l, c]
        cols["ensoleillement"][sel] = b["ensoleillement"][l, c]
        cols["dep"][sel] = blocs.dep_commune[b["commune"][l, c]]
        couverture = np.minimum(1.0, n_f / CASES_ZONE / COUVERTURE_PLEINE)
        lat = Bloc.depuis_nom(nom).grille().latitudes()[:, None]
        for e in E.ESPECES:
            h = np.where(foret, M.facteur_habitat(e, b["essence"], b["ouverte"], b["roche"],
                                                  b["altitude"], b["pente"], lat), 0)
            moy = np.divide(_somme_zone(h, l, c), n_f, out=np.zeros(len(sel)), where=n_f > 0)
            cols[e.code][sel] = moy * couverture
        if k % 100 == 0:
            print(f"    habitat : {k}/{len(uniques)} blocs ({time.time() - t0:.0f} s)", flush=True)
    garde = ~np.isnan(cols["foret_zone"]) & (cols["france_zone"] >= 0.5)
    lignes = df.assign(bloc=noms, zl=lig // COTE_ZONE, zc=col // COTE_ZONE, **cols)
    return lignes[garde].reset_index(drop=True)


def auc(cas: np.ndarray, temoins: np.ndarray) -> float:
    """P(cas > témoin) + ½ P(égalité), par les rangs (Mann-Whitney)."""
    tout = np.concatenate([cas, temoins])
    ordre = tout.argsort(kind="mergesort")
    rangs = np.empty(len(tout))
    tri = tout[ordre]
    # rangs moyens en cas d'égalité
    _, debut, compte = np.unique(tri, return_index=True, return_counts=True)
    moyen = debut + (compte + 1) / 2
    rangs[ordre] = np.repeat(moyen, compte)
    n1, n0 = len(cas), len(temoins)
    return float((rangs[:n1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def intervalle(fonction, n: int, rng) -> tuple[float, float]:
    valeurs = [fonction(rng.integers(0, n, n)) for _ in range(TIRAGES)]
    return float(np.percentile(valeurs, 2.5)), float(np.percentile(valeurs, 97.5))


def sorties(d: pd.DataFrame) -> pd.DataFrame:
    """Une zone et un jour ne comptent qu'une fois : une sortie (ou un inventaire de cent
    espèces au même endroit) ne pèse pas comme cent observations indépendantes."""
    return d.drop_duplicates(subset=["bloc", "zl", "zc", "date"])


def test_habitat(esp: E.Espece, cas: pd.DataFrame, fond: pd.DataFrame, rng) -> dict:
    cas, fond = sorties(cas), sorties(fond)
    if len(cas) < MIN_CAS:
        return {"n": int(len(cas))}
    m_cas, m_tem = cas[esp.code].to_numpy(), fond[esp.code].to_numpy()
    f_cas, f_tem = cas["foret_zone"].to_numpy(), fond["foret_zone"].to_numpy()
    a_mod = auc(m_cas, m_tem)
    a_naif = auc(f_cas, f_tem)
    ic_mod = intervalle(lambda i: auc(m_cas[i], m_tem), len(cas), rng)
    ic_naif = intervalle(lambda i: auc(f_cas[i], f_tem), len(cas), rng)
    # Écart apparié : mêmes cas tirés pour le modèle et pour la référence.
    ic_ecart = intervalle(lambda i: auc(m_cas[i], m_tem) - auc(f_cas[i], f_tem), len(cas), rng)
    return {
        "n": int(len(cas)), "n_fond": int(len(fond)),
        "auc": round(a_mod, 3), "ic": [round(v, 3) for v in ic_mod],
        "auc_foret": round(a_naif, 3), "ic_foret": [round(v, 3) for v in ic_naif],
        "ic_ecart": [round(v, 3) for v in ic_ecart],
        "part_bonnes_zones": round(float((m_cas >= 0.4).mean()), 3),
        "part_bonnes_zones_fond": round(float((m_tem >= 0.4).mean()), 3),
        "part_hors_foret": round(float((f_cas < 0.16).mean()), 3),
    }


# --- Météo passée -------------------------------------------------------------------
# Les réanalyses de Copernicus, lues dans le dépôt public d'Open-Meteo (les données de son
# API, sans quota), à distance et par morceaux : seuls les points utiles sont téléchargés.
# Températures de l'air et du sol d'ERA5-Land (0,1°) ; pluie d'ERA5 (0,25°) : le dépôt n'a
# pas la pluie d'ERA5-Land, qui n'est d'ailleurs que celle d'ERA5 ramenée sur sa grille.

DEPOT = "https://openmeteo.s3.amazonaws.com/data"
TERRE = ("copernicus_era5_land", 0.1)
ERA5 = ("copernicus_era5", 0.25)
LECTURES = (  # variable du dépôt, modèle, opération, nom de la série
    ("precipitation", ERA5, "somme", "precipitation_sum"),
    ("temperature_2m", TERRE, "min", "temperature_2m_min"),
    ("soil_temperature_0_to_7cm", TERRE, "moyenne", "soil_temperature_0_to_7cm_mean"),
)
MORCEAU_H = 504       # heures par morceau (chunk_time_length) des fichiers récents
FILS = 24
_local = threading.local()


def _session() -> requests.Session:
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers["User-Agent"] = USER_AGENT
    return _local.session


class Distant:
    """Ce qu'omfiles demande pour lire un fichier à distance : sa taille et des plages d'octets."""

    def cat_file(self, path, start=None, end=None, **_):
        entete = {} if start is None else {"Range": f"bytes={start}-{'' if end is None else end - 1}"}
        for essai in range(5):
            try:
                r = _session().get(path, headers=entete, timeout=120)
                r.raise_for_status()
                return r.content
            except requests.RequestException:
                if essai == 4:
                    raise
                time.sleep(2 * (essai + 1))

    def size(self, path):
        r = _session().head(path, timeout=60)
        if r.status_code == 404:
            raise FileNotFoundError(path)
        r.raise_for_status()
        return int(r.headers["Content-Length"])


def _existe(chemin: str) -> bool:
    """Le dépôt a-t-il ce fichier ? Retenu par fil, une requête par fichier."""
    connus = getattr(_local, "existe", None)
    if connus is None:
        connus = _local.existe = {}
    if chemin not in connus:
        connus[chemin] = _session().head(f"{DEPOT}/{chemin}", timeout=60).status_code == 200
    return connus[chemin]


def _lecteur(chemin: str):
    """Lecteur d'un fichier du dépôt, gardé par fil (l'ouvrir coûte deux requêtes)."""
    cache = getattr(_local, "lecteurs", None)
    if cache is None:
        cache = _local.lecteurs = {}
    if chemin not in cache:
        if len(cache) > 64:
            cache.pop(next(iter(cache)))
        cache[chemin] = omfiles.OmFileReader.from_fsspec(Distant(), f"{DEPOT}/{chemin}")
    return cache[chemin]


def _indices(modele: tuple[str, float], lat: float, lon: float) -> tuple[int, int]:
    _, pas = modele
    return int(round((lat + 90) / pas)), int(round((lon + 180) / pas))


def horaire(variable: str, modele: tuple[str, float], annee: int, lat: float, lon: float) -> np.ndarray:
    """Valeurs horaires (UTC) d'une année au point de grille le plus proche ; NaN si absentes.
    Un fichier par année jusqu'en 2021, des morceaux de trois semaines ensuite."""
    dossier, _ = modele
    i, j = _indices(modele, lat, lon)
    h0 = int(datetime(annee, 1, 1, tzinfo=timezone.utc).timestamp()) // 3600
    h1 = int(datetime(annee + 1, 1, 1, tzinfo=timezone.utc).timestamp()) // 3600
    annuel = f"{dossier}/{variable}/year_{annee}.om"
    if _existe(annuel):
        return _lecteur(annuel)[i, j, :].ravel()[: h1 - h0].astype(np.float32)
    sortie = np.full(h1 - h0, np.nan, dtype=np.float32)
    for c in range(h0 // MORCEAU_H, (h1 - 1) // MORCEAU_H + 1):
        morceau = f"{dossier}/{variable}/chunk_{c}.om"
        if not _existe(morceau):
            continue   # pas encore publié
        v = _lecteur(morceau)[i, j, :].ravel()
        a, b = max(h0, c * MORCEAU_H), min(h1, (c + 1) * MORCEAU_H)
        sortie[a - h0:b - h0] = v[a - c * MORCEAU_H:b - c * MORCEAU_H]
    return sortie


@lru_cache(maxsize=64)
def _jours_paris(annee: int) -> tuple[np.ndarray, int]:
    """Rang du jour de Paris (0 = 1er janvier) de chaque heure UTC de l'année, et nombre de jours."""
    h0 = int(datetime(annee, 1, 1, tzinfo=timezone.utc).timestamp())
    h1 = int(datetime(annee + 1, 1, 1, tzinfo=timezone.utc).timestamp())
    debut = date(annee, 1, 1).toordinal()
    rang = np.array([datetime.fromtimestamp(t + decalage_paris(t), timezone.utc).date().toordinal() - debut
                     for t in range(h0, h1, 3600)])
    return rang, (date(annee + 1, 1, 1) - date(annee, 1, 1)).days


def quotidien(valeurs: np.ndarray, annee: int, operation: str) -> np.ndarray:
    """« somme », « min » ou « moyenne » par jour de Paris ; un jour dont une heure manque vaut
    NaN (le 1er janvier, toujours : il commence la veille en UTC)."""
    rang, n = _jours_paris(annee)
    dans = rang < n
    r, v = rang[dans], valeurs[dans]
    attendu = np.bincount(r, minlength=n)
    ok = ~np.isnan(v)
    compte = np.bincount(r[ok], minlength=n)
    if operation == "min":
        sortie = np.full(n, np.inf)
        np.minimum.at(sortie, r[ok], v[ok])
    else:
        sortie = np.bincount(r[ok], weights=v[ok], minlength=n)
        if operation == "moyenne":
            sortie = sortie / np.maximum(compte, 1)
    attendu[0] += 1   # l'heure de la veille au soir, qu'on n'a pas lue
    return np.where(compte == attendu, sortie, np.nan).astype(np.float32)


def serie(cle: tuple[float, float, int]) -> dict:
    lat, lon, annee = cle
    i, j = _indices(TERRE, lat, lon)
    relief = _lecteur(f"{TERRE[0]}/static/HSURF.om")[i:i + 1, j:j + 1]
    sortie = {"altitude": float(np.asarray(relief).ravel()[0]), "debut": date(annee, 1, 1).isoformat()}
    for variable, modele, operation, nom in LECTURES:
        sortie[nom] = quotidien(horaire(variable, modele, annee, lat, lon), annee, operation)
    return sortie


def meteo_passee(cles: set[tuple[float, float, int]]) -> dict:
    """Séries quotidiennes par (lat, lon arrondies au 0,1°, année), en cache dans
    cache/validation/ ; le cache est réécrit régulièrement : une interruption perd peu."""
    chemin = DOSSIER / "meteo_passee.npz"
    series: dict = {}
    if chemin.exists():
        z = np.load(chemin, allow_pickle=False)
        for k, alt, v in zip(z["cles"], z["altitudes"], z["valeurs"]):
            la, lo, an = k.split("|")
            n = (date(int(an) + 1, 1, 1) - date(int(an), 1, 1)).days
            series[(float(la), float(lo), int(an))] = {
                "altitude": float(alt), "debut": f"{an}-01-01",
                **{nom: v[q][:n] for q, (_, _, _, nom) in enumerate(LECTURES)}}

    def ecrire():
        liste = list(series)
        temporaire = DOSSIER / "meteo_passee.tmp.npz"
        np.savez_compressed(
            temporaire,
            cles=np.array([f"{la:.1f}|{lo:.1f}|{an}" for la, lo, an in liste]),
            altitudes=np.array([series[k]["altitude"] for k in liste], dtype=np.float32),
            valeurs=np.array([[np.pad(series[k][nom], (0, 366 - len(series[k][nom])), constant_values=np.nan)
                               for _, _, _, nom in LECTURES] for k in liste], dtype=np.float32))
        temporaire.replace(chemin)

    manquantes = sorted(cles - set(series))
    print(f"  météo passée : {len(series)} séries en cache, {len(manquantes)} à lire", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(FILS) as ex:
        for k, (cle, s) in enumerate(zip(manquantes, ex.map(serie, manquantes)), 1):
            series[cle] = s
            if k % 100 == 0 or k == len(manquantes):
                ecrire()
                print(f"    {k}/{len(manquantes)} ({time.time() - t0:.0f} s)", flush=True)
    return series


def indices_meteo(esp: E.Espece, serie: dict, altitude: float, ensoleillement: float, lat: float):
    """Indice météo (saison × pluie × sol × gel) de chaque jour de la série, à la case."""
    debut = date.fromisoformat(serie["debut"])
    pluie = np.asarray(serie["precipitation_sum"], dtype=np.float32)
    tmin = np.asarray(serie["temperature_2m_min"], dtype=np.float32)
    tsol = np.asarray(serie["soil_temperature_0_to_7cm_mean"], dtype=np.float32)
    ecart = serie["altitude"] - altitude
    tmin = tmin + E.GRADIENT_AIR * ecart
    tsol = tsol + E.GRADIENT_SOL * ecart + E.SOLEIL_SOL * ensoleillement
    sortie = {}
    for k in range(max(esp.pluie_jours[1], 7), len(pluie)):
        jour = debut + timedelta(days=k)
        s = M.facteur_saison(esp, jour, lat)
        p, t, g = M.entrees_meteo(esp, k, pluie, tmin, tsol, ensoleillement)
        if np.isnan(p) or np.isnan(t):
            continue
        f = M.facteurs_meteo(esp, p, t, g)
        sortie[jour] = (s, float(M.indice(1.0, s, f)))
    return sortie


def cas_meteo(esp: E.Espece, d: pd.DataFrame) -> pd.DataFrame:
    """Un cas = une espèce, un jour, une maille de 0,1° (une sortie, pas dix spécimens), sur
    une case boisée, en saison, et assez ancien pour que la réanalyse le couvre."""
    d = d[d["foret_case"]]
    d = d.assign(lat1=d["lat"].round(1), lon1=d["lon"].round(1))
    d = d.drop_duplicates(subset=["date", "lat1", "lon1"])
    d = d[d["date"] <= pd.Timestamp(date.today() - timedelta(days=14))]
    if not len(d):
        return d
    return d[[M.facteur_saison(esp, t.date(), la) > 0 for t, la in zip(d["date"], d["lat"])]]


def test_meteo(esp: E.Espece, d: pd.DataFrame, series: dict, rng) -> dict:
    if len(d) < MIN_CAS:
        return {"n": int(len(d))}
    mois, saison_m, saison_s = [], [], []
    for _, o in d.iterrows():
        jour = o["date"].date()
        s = series.get((float(o["lat1"]), float(o["lon1"]), jour.year))
        if s is None:
            continue
        ind = indices_meteo(esp, s, float(o["altitude"]), float(o["ensoleillement"]), float(o["lat"]))
        if jour not in ind:
            continue
        s_cas, w_cas = ind[jour]
        meme_jour = [j for j in ind if j != jour and j.weekday() == jour.weekday()]
        t_mois = [ind[j][1] for j in meme_jour if j.month == jour.month]
        t_saison = [ind[j] for j in meme_jour if ind[j][0] > 0]
        if not t_mois or not t_saison:
            continue
        mois.append(_paire(w_cas, np.array(t_mois)))
        saison_m.append(_paire(w_cas, np.array([w for _, w in t_saison])))
        saison_s.append(_paire(s_cas, np.array([s for s, _ in t_saison])))

    n = len(mois)
    if n < MIN_CAS:
        return {"n": n}
    mois, saison_m, saison_s = map(np.array, (mois, saison_m, saison_s))
    ic = lambda v: [round(x, 3) for x in intervalle(lambda i: v[i].mean(), n, rng)]
    return {
        "n": n,
        "auc_mois": round(float(mois.mean()), 3), "ic_mois": ic(mois),
        "auc_saison": round(float(saison_m.mean()), 3), "ic_saison": ic(saison_m),
        "auc_calendrier": round(float(saison_s.mean()), 3), "ic_calendrier": ic(saison_s),
        "ic_ecart": [round(x, 3) for x in intervalle(lambda i: (saison_m[i] - saison_s[i]).mean(), n, rng)],
    }


def _paire(cas: float, temoins: np.ndarray) -> float:
    """Part des témoins que le cas dépasse (égalités comptées pour moitié)."""
    return float(((cas > temoins).sum() + 0.5 * (cas == temoins).sum()) / len(temoins))


# --- Orchestration ------------------------------------------------------------------

def dans_region(d: pd.DataFrame, deps) -> pd.DataFrame:
    return d if deps is None else d[d["dep"].isin(deps)]


def series_des_cas(cas_m: dict[str, pd.DataFrame]) -> dict:
    return meteo_passee({(float(a), float(b), int(t.year)) for d in cas_m.values()
                         for a, b, t in zip(d["lat1"], d["lon1"], d["date"])})


def valider() -> dict:
    t0 = time.time()
    par_espece, fond = observations()
    # Un seul passage sur les blocs pour les cinq espèces et le fond.
    tous = pd.concat([fond.assign(groupe="fond")] + [d.assign(groupe=g) for g, d in par_espece.items()])
    tous = lieux(tous, Blocs())
    lieux_fond = tous[tous["groupe"] == "fond"]
    lieux_esp = {g: tous[tous["groupe"] == g] for g in par_espece}
    print(f"Observations : {', '.join(f'{g} {len(d)}' for g, d in lieux_esp.items())} ; "
          f"fond {len(lieux_fond)}  ({time.time() - t0:.0f} s)", flush=True)

    cas_m = {e.code: cas_meteo(e, lieux_esp[e.code]) for e in E.ESPECES}
    series = series_des_cas(cas_m)

    rng = np.random.default_rng(GRAINE)
    resultats = {}
    for code, (nom, deps) in REGIONS.items():
        fond_r = dans_region(lieux_fond, deps)
        resultats[code] = {"nom": nom, "fond": int(len(sorties(fond_r))), "especes": {}}
        for esp in E.ESPECES:
            d = dans_region(lieux_esp[esp.code], deps)
            resultats[code]["especes"][esp.code] = {
                "nom": esp.nom,
                "observations": int(len(d)),
                "habitat": test_habitat(esp, d[d["incertitude"] <= INCERTITUDE_HABITAT_M], fond_r, rng),
                "meteo": test_meteo(esp, dans_region(cas_m[esp.code], deps), series, rng),
            }
            print(f"  {nom} — {esp.nom} : {resultats[code]['especes'][esp.code]}", flush=True)
    sortie = {
        "calcule_le": date.today().isoformat(),
        "periode": list(ANNEES),
        "incertitude_habitat_m": INCERTITUDE_HABITAT_M,
        "incertitude_meteo_m": INCERTITUDE_METEO_M,
        "min_cas": MIN_CAS,
        "regions": resultats,
    }
    (DATA / "validation.json").write_text(json.dumps(sortie, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Écrit data/validation.json en {time.time() - t0:.0f} s")
    return sortie


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["observations"]:
        par_espece, fond = observations()
        print({g: len(d) for g, d in par_espece.items()}, "fond", len(fond))
    elif sys.argv[1:] == ["meteo"]:     # la météo passée des cas, sans attendre le fond
        especes = observations_especes()
        tous = lieux(pd.concat([d.assign(groupe=g) for g, d in especes.items()]), Blocs())
        series_des_cas({e.code: cas_meteo(e, tous[tous["groupe"] == e.code]) for e in E.ESPECES})
    else:
        valider()
