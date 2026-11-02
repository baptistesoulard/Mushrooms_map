"""Météo de la France entière depuis le dépôt public d'Open-Meteo (AWS Open Data, CC-BY 4.0).

Ce sont les données mêmes que sert l'API d'Open-Meteo, en grilles complètes et sans quota :

- AROME France (Météo-France, 2,5 km) : les jours passés et les deux prochains ;
- ARPEGE Europe (Météo-France, 0,1°) : jusqu'au quatrième jour ;
- IFS (ECMWF, 0,25°) : au-delà, et la température du sol (0-7 cm) de tous les jours,
  qu'AROME et ARPEGE ne publient pas.

Chaque jour prend, point par point, le modèle le plus fin qui le couvre entièrement. Tout est
ramené sur la grille d'AROME (0,025°) : la pluie telle quelle, les températures après passage
au niveau de la mer avec le relief propre à chaque modèle. Mesuré le 2026-10-31 sur 1 801
pluviomètres Météo-France : AROME n'est pas biaisé en moyenne, et aucune correction (nationale,
par département, par altitude) ne fait mieux que rien hors échantillon.

Format des fichiers (`omfiles`) : `data/<modèle>/<variable>/chunk_<n>.om`, tableau
(lat, lon, temps) ; le pas i du morceau n est l'instant
(n × chunk_time_length + i) × temporal_resolution_seconds depuis 1970 (UTC). Une valeur de
pluie est le cumul du pas qui la précède.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import cached_property

import numpy as np
import omfiles
import requests

from . import especes as E
from .config import CACHE, USER_AGENT
from .meteo import Interpolateur, Meteo
from .publication import jour_de_la_carte

DEPOT = "https://openmeteo.s3.amazonaws.com/data"

# Emprise de la France métropolitaine (Corse comprise), avec une marge.
SUD, NORD, OUEST, EST = 41.0, 51.5, -5.6, 10.0


@dataclass(frozen=True)
class Modele:
    nom: str
    dossier: str
    lat0: float      # centre de la première ligne (sud)
    lon0: float
    pas: float
    # Variables du dépôt pour la pluie, la température minimale et celle du sol (None : absente).
    pluie: str | None = "precipitation"
    tmin: str | None = "temperature_2m"
    tsol: str | None = None

    @cached_property
    def meta(self) -> dict:
        return _http(f"{DEPOT}/{self.dossier}/static/meta.json").json()

    @cached_property
    def relief(self) -> np.ndarray:
        return omfiles.OmFileReader(str(_fichier(self, "static/HSURF.om", definitif=True)))[:]

    def fenetre(self) -> tuple[slice, slice, np.ndarray, np.ndarray]:
        """Lignes et colonnes couvrant la France, et leurs latitudes / longitudes."""
        i0 = int(np.floor((SUD - self.lat0) / self.pas))
        i1 = int(np.ceil((NORD - self.lat0) / self.pas)) + 1
        j0 = int(np.floor((OUEST - self.lon0) / self.pas))
        j1 = int(np.ceil((EST - self.lon0) / self.pas)) + 1
        lats = np.round(self.lat0 + np.arange(i0, i1) * self.pas, 4)
        lons = np.round(self.lon0 + np.arange(j0, j1) * self.pas, 4)
        return slice(i0, i1), slice(j0, j1), lats, lons


AROME = Modele("AROME France", "meteofrance_arome_france0025", 37.5, -12.0, 0.025)
ARPEGE = Modele("ARPEGE Europe", "meteofrance_arpege_europe", 20.0, -32.0, 0.1)
IFS = Modele("IFS (ECMWF)", "ecmwf_ifs025", -90.0, -180.0, 0.25,
             tmin="temperature_2m_min", tsol="soil_temperature_0_to_7cm")
MODELES = (AROME, ARPEGE, IFS)    # du plus fin au plus grossier


def _http(url: str, essais: int = 5) -> requests.Response:
    for essai in range(1, essais + 1):
        try:
            r = requests.get(url, timeout=300, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            pas_encore = isinstance(e, requests.HTTPError) and e.response is not None \
                and e.response.status_code in (403, 404)
            if essai == essais or pas_encore:
                raise
            time.sleep(10 * essai)
    raise AssertionError("inatteignable")


def _fichier(modele: Modele, chemin: str, definitif: bool):
    """Copie locale d'un fichier du dépôt. Un morceau entièrement passé ne change plus :
    il est gardé ; les autres sont relus à chaque fois."""
    local = CACHE / "depot" / modele.dossier / chemin
    if local.exists() and definitif:
        return local
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(_http(f"{DEPOT}/{modele.dossier}/{chemin}").content)
    return local


# --- Jours locaux --------------------------------------------------------------------

def _dernier_dimanche(annee: int, mois: int) -> date:
    d = date(annee, mois + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def decalage_paris(instant: int) -> int:
    """Heure de Paris moins heure UTC (s) : +2 h de fin mars à fin octobre, +1 h sinon."""
    t = datetime.fromtimestamp(instant, timezone.utc)
    ete0 = datetime.combine(_dernier_dimanche(t.year, 3), datetime.min.time(), timezone.utc) + timedelta(hours=1)
    ete1 = datetime.combine(_dernier_dimanche(t.year, 10), datetime.min.time(), timezone.utc) + timedelta(hours=1)
    return 7200 if ete0 <= t < ete1 else 3600


def jour_local(instants) -> np.ndarray:
    """Date locale (Paris) de chaque instant (s, UTC), en ordinal."""
    return np.array([datetime.fromtimestamp(int(t) + decalage_paris(int(t)), timezone.utc).date().toordinal()
                     for t in instants])


def quotidien(modele: Modele, variable: str, jours: list[date], operation: str) -> np.ndarray:
    """Valeurs quotidiennes (jours de Paris) de la fenêtre France : « somme », « min » ou « moyenne ».

    Lu morceau par morceau (un mois d'AROME horaire ne tient pas en mémoire). Un jour dont un
    pas de temps manque en un point vaut NaN en ce point.
    """
    dt = modele.meta["temporal_resolution_seconds"]
    n = modele.meta["chunk_time_length"]
    li, co, _, _ = modele.fenetre()
    t0 = int(datetime.combine(jours[0], datetime.min.time(), timezone.utc).timestamp()) - 7200
    t1 = int(datetime.combine(jours[-1] + timedelta(days=1), datetime.min.time(), timezone.utc).timestamp())
    tous = np.arange(t0 // dt, t1 // dt + 1)
    loc_tous = jour_local(tous * dt)
    rang = {j.toordinal(): k for k, j in enumerate(jours)}
    attendu = np.array([np.sum(loc_tous == j.toordinal()) for j in jours])
    forme = (len(jours), li.stop - li.start, co.stop - co.start)
    acc = np.full(forme, np.inf if operation == "min" else 0.0, dtype=np.float32)
    nb = np.zeros(forme, dtype=np.int16)
    maintenant = time.time()
    for c in range(tous[0] // n, tous[-1] // n + 1):
        try:
            f = _fichier(modele, f"{variable}/chunk_{c}.om", definitif=(c + 1) * n * dt < maintenant - 2 * 86400)
        except requests.HTTPError:
            continue   # morceau pas encore écrit : ces jours restent incomplets
        bloc = omfiles.OmFileReader(str(f))[li, co, :]          # (lat, lon, n)
        k = np.arange(c * n, (c + 1) * n)
        for i in np.nonzero((k >= tous[0]) & (k <= tous[-1]))[0]:
            d = rang.get(int(loc_tous[k[i] - tous[0]]))
            if d is None:
                continue
            v = bloc[:, :, i]
            ok = ~np.isnan(v)
            if operation == "min":
                acc[d] = np.where(ok, np.minimum(acc[d], v), acc[d])
            else:
                acc[d] += np.where(ok, v, 0)
            nb[d] += ok
    if operation == "moyenne":
        acc = acc / np.maximum(nb, 1)
    return np.where(nb >= attendu[:, None, None], acc, np.nan).astype(np.float32)


# --- Assemblage ----------------------------------------------------------------------

def _regrille(modele: Modele, champ: np.ndarray, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Champs (jours × lat × lon) d'un modèle vers les points (lats × lons) de la grille cible."""
    _, _, la, lo = modele.fenetre()
    LA, LO = np.meshgrid(lats, lons, indexing="ij")
    interp = Interpolateur(la, lo, LA.ravel(), LO.ravel())
    return np.stack([interp(c).reshape(LA.shape) for c in champ])


def meteo_france(jour: date | None = None, jours_passes: int = 30, jours_futurs: int = 8,
                 journal=print) -> Meteo:
    """Météo quotidienne de `jour` - jours_passes à `jour` + jours_futurs - 1, grille AROME.

    Le résultat est gardé trois heures dans `cache/` : relancer l'export ne retélécharge rien.
    """
    jour = jour or jour_de_la_carte()
    jours = [jour + timedelta(days=k) for k in range(-jours_passes, jours_futurs)]
    li, co, lats, lons = AROME.fenetre()
    memo = CACHE / f"meteo_france_{jour.isoformat()}_{jours_passes}_{jours_futurs}.npz"
    if memo.exists() and time.time() - memo.stat().st_mtime < 3 * 3600:
        z = np.load(memo)
        return Meteo(dates=jours, lats=z["lats"], lons=z["lons"], altitude=z["altitude"],
                     pluie=z["pluie"], tmin_mer=z["tmin_mer"], tsol_mer=z["tsol_mer"])
    debut = time.time()

    def champ(variable: str, operation: str, gradient: float | None) -> np.ndarray:
        """Le champ quotidien sur la grille AROME, chaque point pris au modèle le plus fin."""
        sortie = np.full((len(jours), len(lats), len(lons)), np.nan, dtype=np.float32)
        for m in MODELES:
            v = getattr(m, variable)
            if v is None:
                continue
            q = quotidien(m, v, jours, operation)
            if gradient is not None:    # au niveau de la mer, avec le relief du modèle
                mi, mc, _, _ = m.fenetre()
                q = q + gradient * m.relief[mi, mc][None]
            if m is not AROME:
                q = _regrille(m, q, lats, lons)
            pris = np.isnan(sortie) & ~np.isnan(q)
            jours_pris = [j.isoformat()[5:] for j, p in zip(jours, pris) if p.mean() > 0.5]
            journal(f"  {variable} : {m.nom} pour {len(jours_pris)} jours "
                    f"{jours_pris[:1] + ['…'] + jours_pris[-1:] if len(jours_pris) > 2 else jours_pris} "
                    f"({time.time() - debut:.0f} s)")
            sortie = np.where(pris, q, sortie)
        vides = [j.isoformat() for j, x in zip(jours, sortie) if np.isnan(x).all()]
        if vides:
            raise RuntimeError(f"météo incomplète ({variable}) : aucun modèle pour {', '.join(vides)}")
        # Quelques points de bord de domaine : la moyenne du jour.
        return np.where(np.isnan(sortie), np.nanmean(sortie, axis=(1, 2), keepdims=True), sortie)

    pluie = champ("pluie", "somme", None)
    tmin = champ("tmin", "min", E.GRADIENT_AIR)
    tsol = champ("tsol", "moyenne", E.GRADIENT_SOL)
    m = Meteo(dates=jours, lats=lats, lons=lons, altitude=AROME.relief[li, co].astype(np.float32),
              pluie=np.maximum(pluie, 0).astype(np.float32), tmin_mer=tmin.astype(np.float32),
              tsol_mer=tsol.astype(np.float32))
    np.savez(memo, lats=m.lats, lons=m.lons, altitude=m.altitude, pluie=m.pluie, tmin_mer=m.tmin_mer,
             tsol_mer=m.tsol_mer)
    return m


def sources() -> dict:
    """Ce que le site affiche : modèles et heure de leur dernier calcul (UTC)."""
    return {m.nom: datetime.fromtimestamp(m.meta["last_run_initialisation_time"], timezone.utc)
            .isoformat(timespec="minutes") for m in MODELES}


if __name__ == "__main__":
    t = time.time()
    m = meteo_france()
    print(f"{len(m.dates)} jours, {len(m.lats)} × {len(m.lons)} points, {time.time() - t:.0f} s")
    print(json.dumps(sources(), indent=1))
