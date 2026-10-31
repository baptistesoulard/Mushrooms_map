"""Le modèle face aux observations : les règles, réglées d'avance, sont-elles vérifiées ?

    python -m champi.validation            # GBIF + météo passée (réseau, ~15 min la 1re fois)

Aucun paramètre n'est ajusté ici : on mesure. Deux questions, deux plans d'expérience.

1. HABITAT. Les zones où l'espèce a été observée sont-elles mieux notées que les zones où
   d'AUTRES champignons ont été observés ? Le fond « groupe cible » (Phillips et al. 2009)
   neutralise le biais d'observation : mêmes observateurs, mêmes sentiers. Référence
   naïve : la seule part de forêt de la zone.

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
parfois approximatives, météo passée issue d'une réanalyse (ERA5-Land, ~9 km) et non des
prévisions utilisées en direct.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import especes as E
from . import modele as M
from .config import DATA, FACTEUR_ZONE
from .export import Agregat, cases_de_foret, charger_habitat
from .grille import lonlat_vers_merc
from .meteo import ARCHIVE, VARIABLES
from .sources import http_get

DOSSIER = DATA / "validation"
GBIF = "https://api.gbif.org/v1"
GADM_HAUTE_SAVOIE = "FRA.1.7_1"
ANNEES = (1995, 2026)
# Habitat : la carte raisonne par zones de 250 m, une position à plus d'1 km n'y dit rien.
# Météo : la réanalyse a une maille de 9 km ; 10 km suffisent pour être dans le bon secteur.
INCERTITUDE_HABITAT_M = 1000
INCERTITUDE_METEO_M = 10000
GROUPES = {
    "cepe": ["Boletus edulis", "Boletus pinophilus", "Boletus aereus", "Boletus reticulatus"],
    "girolle": ["Cantharellus cibarius", "Cantharellus pallens", "Cantharellus friesii"],
    "trompette": ["Craterellus cornucopioides"],
    "pied_de_mouton": ["Hydnum repandum", "Hydnum rufescens"],
    "morille": ["Morchella"],
}
MIN_CAS = 20          # en dessous, on publie le nombre, pas l'AUC
TIRAGES = 1000
GRAINE = 20261030


# --- Observations GBIF --------------------------------------------------------------

def cle_taxon(nom: str) -> int:
    r = http_get(f"{GBIF}/species/match", {"name": nom, "kingdom": "Fungi"}).json()
    if r.get("matchType") != "EXACT":
        raise ValueError(f"taxon GBIF introuvable : {nom}")
    return int(r["usageKey"])


def _pages(cles: list[int]):
    """Toutes les occurrences, année par année : GBIF se bloque quand on pagine loin dans une
    grosse requête, alors qu'une année tient en quelques pages rapides."""
    for annee in range(ANNEES[0], ANNEES[1] + 1):
        debut = 0
        while True:
            p = [("gadmGid", GADM_HAUTE_SAVOIE), ("hasCoordinate", "true"), ("hasGeospatialIssue", "false"),
                 ("year", annee), ("limit", 300), ("offset", debut)]
            p += [("taxonKey", c) for c in cles]
            r = http_get(f"{GBIF}/occurrence/search", p, delai=60).json()
            yield from r["results"]
            debut += 300
            if r.get("endOfRecords") or debut >= r.get("count", 0):
                break


def telecharger(cles: list[int], nom: str, incertitude_max: float) -> pd.DataFrame:
    """Occurrences datées au jour en Haute-Savoie, position connue à `incertitude_max` près."""
    chemin = DOSSIER / f"gbif_{nom}.csv.gz"
    if chemin.exists():
        return pd.read_csv(chemin, parse_dates=["date"])
    lignes = []
    for o in _pages(cles):
        inc = o.get("coordinateUncertaintyInMeters")
        if not o.get("day") or (inc is not None and inc > incertitude_max):
            continue
        lignes.append({
            "lat": o["decimalLatitude"], "lon": o["decimalLongitude"],
            "date": f"{o['year']:04d}-{o['month']:02d}-{o['day']:02d}",
            "taxon": o.get("speciesKey") or o.get("taxonKey"), "jeu": o.get("datasetKey"),
            "incertitude": inc,
        })
    df = pd.DataFrame(lignes)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    DOSSIER.mkdir(parents=True, exist_ok=True)
    df.to_csv(chemin, index=False, compression="gzip")
    return df


def observations() -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    chemin_cles = DOSSIER / "taxons.json"
    if chemin_cles.exists():
        cles = json.loads(chemin_cles.read_text(encoding="utf-8"))
    else:
        cles = {g: [cle_taxon(n) for n in noms] for g, noms in GROUPES.items()}
        DOSSIER.mkdir(parents=True, exist_ok=True)
        chemin_cles.write_text(json.dumps(cles, indent=1), encoding="utf-8")
    par_espece = {g: telecharger(c, g, INCERTITUDE_METEO_M) for g, c in cles.items()}
    fond = telecharger([5], "fond_champignons", INCERTITUDE_HABITAT_M)   # 5 = règne Fungi
    exclus = {k for c in cles.values() for k in c}
    # Le fond exclut les cinq groupes (genre Morchella compris : ses espèces ont d'autres clés).
    exclus_especes = set(pd.concat(par_espece.values())["taxon"].dropna().astype(int))
    fond = fond[~fond["taxon"].isin(exclus | exclus_especes)]
    return par_espece, fond


# --- Habitat ------------------------------------------------------------------------

def zones(df: pd.DataFrame, publie, n_dept) -> np.ndarray:
    """Index de la zone publiée (250 m) de chaque observation ; -1 hors département."""
    x, y = lonlat_vers_merc(df["lon"].to_numpy(), df["lat"].to_numpy())
    col = np.floor((x - publie.x0) / publie.pas).astype(int)
    lig = np.floor((publie.y1 - y) / publie.pas).astype(int)
    ok = (col >= 0) & (col < publie.nx) & (lig >= 0) & (lig < publie.ny)
    idx = np.where(ok, lig * publie.nx + col, -1)
    idx[ok] = np.where(n_dept[idx[ok]] >= (FACTEUR_ZONE ** 2) / 2, idx[ok], -1)
    return idx


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


def test_habitat(esp: E.Espece, df: pd.DataFrame, fond: pd.DataFrame, contexte) -> dict:
    agregat, cases, rng = contexte["agregat"], contexte["cases"], contexte["rng"]
    h = M.facteur_habitat(esp, cases.essence, cases.ouverte, cases.roche, cases.altitude, cases.pente)
    indice_zone = agregat._moyenne(h) * agregat.couverture
    foret_zone = np.minimum(1.0, agregat.n_foret / FACTEUR_ZONE ** 2)

    # Une zone et un jour ne comptent qu'une fois : une sortie (ou un inventaire de cent
    # espèces au même endroit) ne pèse pas comme cent observations indépendantes.
    def sorties(d: pd.DataFrame) -> np.ndarray:
        z = zones(d, agregat.publie, agregat.n_dept)
        u = pd.DataFrame({"z": z, "j": d["date"].to_numpy()})
        return u[u["z"] >= 0].drop_duplicates()["z"].to_numpy()

    precis = df["incertitude"].isna() | (df["incertitude"] <= INCERTITUDE_HABITAT_M)
    cas, tem = sorties(df[precis]), sorties(fond)
    if len(cas) < MIN_CAS:
        return {"n": int(len(cas))}
    m_cas, m_tem = indice_zone[cas], indice_zone[tem]
    f_cas, f_tem = foret_zone[cas], foret_zone[tem]
    a_mod = auc(m_cas, m_tem)
    a_naif = auc(f_cas, f_tem)
    ic_mod = intervalle(lambda i: auc(m_cas[i], m_tem), len(cas), rng)
    ic_naif = intervalle(lambda i: auc(f_cas[i], f_tem), len(cas), rng)
    # Écart apparié : mêmes cas tirés pour le modèle et pour la référence.
    ic_ecart = intervalle(lambda i: auc(m_cas[i], m_tem) - auc(f_cas[i], f_tem), len(cas), rng)
    return {
        "n": int(len(cas)), "n_fond": int(len(tem)),
        "auc": round(a_mod, 3), "ic": [round(v, 3) for v in ic_mod],
        "auc_foret": round(a_naif, 3), "ic_foret": [round(v, 3) for v in ic_naif],
        "ic_ecart": [round(v, 3) for v in ic_ecart],
        "part_bonnes_zones": round(float((m_cas >= 0.4).mean()), 3),
        "part_bonnes_zones_fond": round(float((m_tem >= 0.4).mean()), 3),
        "part_hors_foret": round(float((agregat.n_foret[cas] < 4).mean()), 3),
    }


# --- Météo passée -------------------------------------------------------------------

def _fenetre(esp: E.Espece, annee: int) -> tuple[date, date]:
    """Période de météo à télécharger : commune à toutes les espèces de printemps, ou à toutes
    celles d'automne (moins de périodes distinctes = moins de requêtes), plus 40 jours avant
    pour la fenêtre de pluie."""
    printemps = esp.saison[0] < "05"
    groupe = [e for e in E.ESPECES if (e.saison[0] < "05") == printemps]
    jour = lambda s: date(annee, *map(int, s.split("-")))
    return min(jour(e.saison[0]) for e in groupe) - timedelta(days=40), max(jour(e.saison[3]) for e in groupe)


class Budget:
    """Limites d'Open-Meteo (gratuit) : 600 appels pondérés par minute, 5 000 par heure.

    Un appel pondéré = un point × deux semaines de données. On attend AVANT de dépasser,
    plutôt que d'essuyer des refus : une longue série de reprises finit par échouer.
    """

    def __init__(self, par_minute=550, par_heure=4500):
        self.journal: list[tuple[float, float]] = []
        self.par_minute, self.par_heure = par_minute, par_heure

    def attendre(self, poids: float) -> None:
        while True:
            t = time.time()
            minute = sum(p for d, p in self.journal if t - d < 60)
            heure = sum(p for d, p in self.journal if t - d < 3600)
            if minute + poids <= self.par_minute and heure + poids <= self.par_heure:
                self.journal.append((t, poids))
                return
            time.sleep(20)


def meteo_passee(besoins: dict[tuple[float, float, int], tuple[date, date]]) -> dict:
    """Séries ERA5-Land par (lat, lon arrondies au 0,1°, année), en cache dans data/validation/.

    Le cache est réécrit après chaque requête : une interruption ne perd rien.
    """
    import gzip
    chemin = DOSSIER / "era5_points.json.gz"
    cache: dict = {}
    if chemin.exists():
        cache = json.loads(gzip.decompress(chemin.read_bytes()).decode("utf-8"))
    manquants = [k for k in besoins if f"{k[0]:.1f}|{k[1]:.1f}|{k[2]}" not in cache]
    # Regrouper par fenêtre identique (l'API prend une seule période par requête).
    par_fenetre = defaultdict(list)
    for k in manquants:
        par_fenetre[besoins[k]].append(k)
    budget = Budget()
    for (debut, fin), cles in par_fenetre.items():
        semaines = ((fin - debut).days + 1) / 14
        lot = max(1, int(500 // max(semaines, 1)))
        for i in range(0, len(cles), lot):
            paquet = cles[i:i + lot]
            budget.attendre(len(paquet) * max(semaines, 1))
            p = {"latitude": ",".join(f"{k[0]:.1f}" for k in paquet),
                 "longitude": ",".join(f"{k[1]:.1f}" for k in paquet),
                 "start_date": debut.isoformat(), "end_date": fin.isoformat(),
                 "daily": ",".join(VARIABLES), "timezone": "Europe/Paris"}
            for essai in range(12):
                try:
                    r = http_get(ARCHIVE, p, essais=3, delai=180).json()
                    break
                except Exception as e:   # quota horaire atteint : attendre qu'il se libère
                    print(f"    Open-Meteo refuse ({e}) : pause de 5 min", flush=True)
                    time.sleep(300)
            else:
                raise RuntimeError("Open-Meteo refuse toujours après une heure d'attente")
            for k, rep in zip(paquet, r if isinstance(r, list) else [r]):
                cache[f"{k[0]:.1f}|{k[1]:.1f}|{k[2]}"] = {
                    "altitude": rep.get("elevation"), "debut": debut.isoformat(),
                    **{v: rep["daily"][v] for v in VARIABLES}}
            chemin.write_bytes(gzip.compress(json.dumps(cache, separators=(",", ":")).encode("utf-8")))
            print(f"    météo passée : {len(cache)} séries", flush=True)
    return cache


def indices_meteo(esp: E.Espece, serie: dict, altitude: float, ensoleillement: float):
    """Indice météo (saison × pluie × sol × gel) de chaque jour de la série, à la case."""
    debut = date.fromisoformat(serie["debut"])
    pluie = np.array([np.nan if v is None else v for v in serie["precipitation_sum"]], dtype=np.float32)
    tmin = np.array([np.nan if v is None else v for v in serie["temperature_2m_min"]], dtype=np.float32)
    tsol = np.array([np.nan if v is None else v for v in serie["soil_temperature_0_to_7cm_mean"]], dtype=np.float32)
    ecart = (serie["altitude"] or altitude) - altitude
    tmin = tmin + E.GRADIENT_AIR * ecart
    tsol = tsol + E.GRADIENT_SOL * ecart + E.SOLEIL_SOL * ensoleillement
    sortie = {}
    for k in range(max(esp.pluie_jours[1], 7), len(pluie)):
        jour = debut + timedelta(days=k)
        s = M.facteur_saison(esp, jour)
        p, t, g = M.entrees_meteo(esp, k, pluie, tmin, tsol, ensoleillement)
        if np.isnan(p) or np.isnan(t):
            continue
        f = M.facteurs_meteo(esp, p, t, g)
        sortie[jour] = (s, float(M.indice(1.0, s, f)))
    return sortie


def test_meteo(esp: E.Espece, df: pd.DataFrame, contexte) -> dict:
    h, grille, rng = contexte["habitat"], contexte["grille"], contexte["rng"]
    x, y = lonlat_vers_merc(df["lon"].to_numpy(), df["lat"].to_numpy())
    col = np.clip(np.floor((x - grille.x0) / grille.pas).astype(int), 0, grille.nx - 1)
    lig = np.clip(np.floor((grille.y1 - y) / grille.pas).astype(int), 0, grille.ny - 1)
    d = df.assign(alt=h["altitude"][lig, col], ens=h["ensoleillement"][lig, col] / 100,
                  lat1=df["lat"].round(1), lon1=df["lon"].round(1))
    d = d[d["alt"] > 0]
    # Un cas = une espèce, un jour, une maille de 0,1° (une sortie, pas dix spécimens).
    d = d.drop_duplicates(subset=["date", "lat1", "lon1"])
    d = d[[M.facteur_saison(esp, t.date()) > 0 for t in d["date"]]] if len(d) else d
    n_total = int(len(df.drop_duplicates(subset=["date"])))
    if len(d) < MIN_CAS:
        return {"n": int(len(d)), "n_brut": n_total}

    series = contexte["meteo"]
    mois, saison_m, saison_s = [], [], []
    for _, o in d.iterrows():
        jour = o["date"].date()
        serie = series.get(f"{o['lat1']:.1f}|{o['lon1']:.1f}|{jour.year}")
        if serie is None:
            continue
        ind = indices_meteo(esp, serie, float(o["alt"]), float(o["ens"]))
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
        return {"n": n, "n_brut": n_total}
    mois, saison_m, saison_s = map(np.array, (mois, saison_m, saison_s))
    ic = lambda v: [round(x, 3) for x in intervalle(lambda i: v[i].mean(), n, rng)]
    return {
        "n": n, "n_brut": n_total,
        "auc_mois": round(float(mois.mean()), 3), "ic_mois": ic(mois),
        "auc_saison": round(float(saison_m.mean()), 3), "ic_saison": ic(saison_m),
        "auc_calendrier": round(float(saison_s.mean()), 3), "ic_calendrier": ic(saison_s),
        "ic_ecart": [round(x, 3) for x in intervalle(lambda i: (saison_m[i] - saison_s[i]).mean(), n, rng)],
    }


def _paire(cas: float, temoins: np.ndarray) -> float:
    """Part des témoins que le cas dépasse (égalités comptées pour moitié)."""
    return float(((cas > temoins).sum() + 0.5 * (cas == temoins).sum()) / len(temoins))


# --- Orchestration ------------------------------------------------------------------

def valider() -> dict:
    t0 = time.time()
    grille, h, meta = charger_habitat()
    cases = cases_de_foret(grille, h)
    agregat = Agregat(grille, h, cases, FACTEUR_ZONE)   # le test d'habitat raisonne en zones de 250 m
    par_espece, fond = observations()
    print(f"Observations : {', '.join(f'{g} {len(d)}' for g, d in par_espece.items())} ; "
          f"fond {len(fond)}  ({time.time() - t0:.0f} s)")

    besoins: dict = {}
    for esp in E.ESPECES:
        df = par_espece[esp.code]
        uniques = df.assign(a=df["lat"].round(1), b=df["lon"].round(1), y=df["date"].dt.year)
        for _, o in uniques.drop_duplicates(subset=["a", "b", "y"]).iterrows():
            annee = o["date"].year
            if annee > ANNEES[1] or o["date"].date() > date.today() - timedelta(days=10):
                continue
            k = (float(o["a"]), float(o["b"]), annee)
            a, b = _fenetre(esp, annee)
            b = min(b, date.today() - timedelta(days=7))   # l'archive s'arrête quelques jours avant
            if k in besoins:
                a, b = min(a, besoins[k][0]), max(b, besoins[k][1])
            besoins[k] = (a, b)
    print(f"  {len(besoins)} séries météo nécessaires", flush=True)
    series = meteo_passee(besoins)

    contexte = {"agregat": agregat, "cases": cases, "habitat": h, "grille": grille,
                "meteo": series, "rng": np.random.default_rng(GRAINE)}
    resultats = {}
    for esp in E.ESPECES:
        df = par_espece[esp.code]
        resultats[esp.code] = {
            "nom": esp.nom,
            "observations": int(len(df)),
            "habitat": test_habitat(esp, df, fond, contexte),
            "meteo": test_meteo(esp, df, contexte),
        }
        print(f"  {esp.nom} : {resultats[esp.code]}")
    sortie = {
        "calcule_le": date.today().isoformat(),
        "periode": list(ANNEES),
        "incertitude_habitat_m": INCERTITUDE_HABITAT_M,
        "incertitude_meteo_m": INCERTITUDE_METEO_M,
        "fond": int(len(fond)),
        "min_cas": MIN_CAS,
        "especes": resultats,
    }
    (DATA / "validation.json").write_text(json.dumps(sortie, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Écrit data/validation.json en {time.time() - t0:.0f} s")
    return sortie


if __name__ == "__main__":
    valider()
