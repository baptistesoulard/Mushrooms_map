"""Job quotidien, France entière : météo du jour → données du site, dans `site/data/`.

    python -m champi.export_france

Le site calcule lui-même l'indice à 50 m, bloc par bloc (`site/modele.js`), à partir de
l'habitat (release « habitat », copié dans `site/habitat/`) et de la météo du jour. Ce job
écrit donc surtout de la météo, plus ce que le navigateur ne peut pas calculer seul :

- `meteo/<bloc>.bin` : pour chaque bloc, les champs météo du jour aux points AROME qui le
  couvrent (entiers 16 bits en dixièmes ; en-tête [lignes, colonnes, i0, j0] ; ordre des
  champs dans `carte.json` → `meteo.champs`) ;
- `apercu/<espèce>_<k>.png` : l'indice de toute la France par pixels de 1,15 km (vue régionale de la
  carte) : la meilleure forêt de chaque pixel, comme les zones de 250 m de plus près ;
- `vue/<k>.png` : « Que chercher ici ? », les parts de forêt aux bonnes conditions par pixel de
  9,2 km et par espèce (`Vue`) ; la vue France de la carte en tire le verdict de chaque carré ;
- `vue_fine/<k>.png` : le même par carré de 4,6 km, pour le niveau intermédiaire de la carte ;
- pour une espèce des prés, ni case ni point : l'indice moyen des prés de chaque COMMUNE,
  `communes/<espèce>_<k>.png` (une valeur par numéro de commune, 256 par ligne, 255 sans prés
  assez étendus) que le navigateur peint avec la couche « c » des blocs, et le même indice en
  aperçu (`apercu/<espèce>_<k>.png`, chaque pixel prend celui de sa commune) ;
- `resumes/<département>.json` : faits et phrases du panneau, par espèce et par jour ;
- `carte.json` (jours, classement des départements, légendes), `especes.json`, `validation.json`.

Puis les pages lisibles sans JavaScript, à côté de la carte (`site/carte/`) : l'accueil et « en
ce moment » (`pages_accueil`), les fiches espèces (`pages_especes`), les départements
(`pages_departements`) ; et leurs images de partage, `partage/<département>.png`, `france.png`
`carte-france.png` et `carte-france-<espèce>.png`, les cartes de l'accueil (`partage`) : le
verdict des départements sur chaque carré de 9,2 km (`verdicts_carres`).

Les calculs de ce job (aperçu, résumés) se font sur l'échantillon de l'habitat (une case sur
16), avec les MÊMES champs arrondis que le navigateur : le panneau et la carte disent la même chose.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

import numpy as np
from PIL import Image

from . import carte_departements
from . import climatologie
from . import depot
from . import especes as E
from . import modele as M
from . import pages
from . import pages_accueil
from . import partage
from . import pages_departements
from . import pages_especes
from . import prairies
from . import redaction
from .config import DATA, PAS_FIN, RACINE, SITE, SITE_DATA, VAPID_PUBLIQUE
from .export import ECHELLE, HORS_FORET, JOURS_FUTURS, TRANCHE_M, ecrire_png
from .france import BLOC, COTE, ECHANTILLON, Bloc
from .grille import Grille, lonlat_vers_merc
from .habitat import ESSENCES, ORIENTATIONS, ROCHES
from .meteo import Interpolateur, Meteo
from .sources import ecrire_json

HABITAT = RACINE / "site" / "habitat"
APERCU = 16                          # cases de 50 m par pixel d'aperçu (1 152 m Mercator)
HORS_FRANCE = 255
PREMIER_GEL = -6                     # le gel compte sur les 7 jours finissant au jour affiché
VUE = 8                              # pixels d'aperçu par pixel de « Que chercher ici ? » (9,2 km)
VUE_FINE = 4                         # … par carré du niveau intermédiaire de la carte (4,6 km, zoom 7)
PRES_COMMUNE_KM2 = 0.25              # en dessous (une ou deux parcelles de Corine), pas d'indice de commune
LARGEUR_TABLE = 256                  # valeurs par ligne de la table des communes
KM2_PAR, PARTS_PAR = 3, 250          # un octet : la forêt en km² × 3, les parts × 250
CARRE_MIN_KM2 = 2.0                  # carte de l'accueil : moins de forêt (de prés) dans un carré, pas de verdict


# --- Habitat ------------------------------------------------------------------------

@dataclass
class Echantillon:
    """Les cases boisées de l'échantillon national (une sur 16), à plat."""

    lat: np.ndarray
    lon: np.ndarray
    altitude: np.ndarray
    ensoleillement: np.ndarray
    pente: np.ndarray
    essence: np.ndarray
    ouverte: np.ndarray
    roche: np.ndarray
    protege: np.ndarray
    commune: np.ndarray
    departement: np.ndarray       # rang dans la liste des départements
    ph: np.ndarray                # pH du sol × 10 (0 = inconnu, ou release d'avant la couche « d »)


def charger_habitat() -> tuple[dict, list[dict], list[dict], Echantillon]:
    index = json.loads((HABITAT / "blocs.json").read_text(encoding="utf-8"))
    communes = json.loads((HABITAT / "communes.json").read_text(encoding="utf-8"))
    deps = sorted({c["dep"] for c in communes})
    rang = {d: k for k, d in enumerate(deps)}
    dep_de_commune = np.array([0] + [rang[c["dep"]] for c in communes], dtype=np.int16)
    e = dict(np.load(HABITAT / "echantillon.npz"))
    # Bois en zone urbanisée (couche « d », champi.sol) : pas de la forêt pour la carte.
    if "urbain" in e:
        garde = ~e.pop("urbain")
        e = {k: v[garde] for k, v in e.items()}
    ech = Echantillon(
        lat=e["lat"].astype(np.float64), lon=e["lon"].astype(np.float64),
        altitude=e["altitude"].astype(np.float32),
        ensoleillement=e["ensoleillement"].astype(np.float32) / 100, pente=e["pente"],
        essence=e["essence"], ouverte=e["ouverte"], roche=e["roche"], protege=e["protege"],
        commune=e["commune"], departement=dep_de_commune[e["commune"]],
        ph=e["ph"] if "ph" in e else np.zeros(len(e["lat"]), dtype=np.uint8),
    )
    departements = [{"code": d} for d in deps]
    return index, communes, departements, ech


def charger_pres(communes: list[dict], departements: list[dict]) -> tuple[Echantillon, np.ndarray] | None:
    """L'échantillon des prés (`prairies.py`) et le milieu de chaque point, pour les espèces des
    champs ; None s'il manque, ou s'il a été construit sur une autre liste de communes que
    l'habitat (les numéros de commune ne voudraient plus rien dire)."""
    if not prairies.FICHIER.exists():
        print("  pas de data/prairies.npz : les espèces des prés sont sautées")
        return None
    z = prairies.charger()
    if z["communes"] != prairies.empreinte_communes(communes):
        print("  data/prairies.npz vient d'une autre liste de communes : relancer python -m champi.prairies ; "
              "les espèces des prés sont sautées")
        return None
    rang = {d["code"]: k for k, d in enumerate(departements)}
    dep_de_commune = np.array([0] + [rang[c["dep"]] for c in communes], dtype=np.int16)
    n = len(z["lat"])
    zero = np.zeros(n, dtype=np.uint8)
    pres = Echantillon(lat=z["lat"], lon=z["lon"], altitude=z["altitude"], ensoleillement=np.zeros(n, np.float32),
                       pente=zero, essence=zero, ouverte=zero.astype(bool), roche=zero, protege=zero.astype(bool),
                       commune=z["commune"], departement=dep_de_commune[z["commune"]], ph=zero)
    return pres, z["milieu"]


# --- Champs météo du jour -----------------------------------------------------------

def fenetres_de_pluie() -> list[tuple[int, int]]:
    return sorted({tuple(e.pluie_jours) for e in E.ESPECES})


def champs_du_jour(meteo: Meteo, k0: int) -> dict[str, np.ndarray]:
    """Tout ce dont le calcul a besoin, déjà cumulé aux points météo, en dixièmes (int16).

    Mêmes sommes et moyennes que `export.Calcul.entrees` : la pluie de chaque fenêtre, la
    température du sol moyenne des 7 jours précédents, la température minimale de chaque jour
    qui peut compter pour le gel.
    """
    sortie = {}
    for jmin, jmax in fenetres_de_pluie():
        for k in range(JOURS_FUTURS):
            kk = k0 + k
            sortie[f"pluie_{jmin}_{jmax}_{k}"] = meteo.pluie[kk - jmax:kk - jmin + 1].sum(axis=0)
    for k in range(JOURS_FUTURS):
        sortie[f"tsol_{k}"] = meteo.tsol_mer[k0 + k - 7:k0 + k].mean(axis=0)
    for d in range(PREMIER_GEL, JOURS_FUTURS):
        sortie[f"tmin_{d}"] = meteo.tmin_mer[k0 + d]
    return {n: np.clip(np.round(v * 10), -32768, 32767).astype(np.int16) for n, v in sortie.items()}


class CalculChamps:
    """Les entrées météo de chaque case à partir des champs publiés : le calcul du navigateur."""

    def __init__(self, champs: dict, lats, lons, lat_cases, lon_cases, altitude, ensoleillement):
        self.champs = champs
        self.interp = Interpolateur(lats, lons, lat_cases, lon_cases)
        self.altitude, self.ensoleillement = altitude, ensoleillement
        self._gel: dict[int, np.ndarray] = {}

    def _v(self, nom: str) -> np.ndarray:
        return self.interp(self.champs[nom].astype(np.float32) / 10)

    def entrees(self, esp: E.Espece, k: int):
        jmin, jmax = esp.pluie_jours
        pluie = M.pluie_efficace(self._v(f"pluie_{jmin}_{jmax}_{k}"), self.ensoleillement)
        tsol = M.temperature_locale(self._v(f"tsol_{k}"), self.altitude, E.GRADIENT_SOL,
                                    self.ensoleillement, E.SOLEIL_SOL)
        gel = np.zeros(len(self.altitude), dtype=np.int8)
        for d in range(k - 6, k + 1):
            if d not in self._gel:
                t = M.temperature_locale(self._v(f"tmin_{d}"), self.altitude, E.GRADIENT_AIR)
                self._gel[d] = t < E.GEL_SEUIL
            gel += self._gel[d]
        return pluie, tsol, gel


def ecrire_meteo_blocs(champs: dict, meteo: Meteo, noms_blocs) -> list[str]:
    """Un fichier par bloc : les points AROME qui couvrent le bloc, plus un de chaque côté."""
    ordre = list(champs)
    pas = float(meteo.lats[1] - meteo.lats[0])
    pile = np.stack([champs[n] for n in ordre])                      # champs × lat × lon
    dossier = SITE_DATA / "meteo"
    dossier.mkdir(parents=True, exist_ok=True)
    for nom in noms_blocs:
        g = Bloc.depuis_nom(nom).grille()
        b = g.bornes_lonlat()
        i0 = max(int(np.floor((b["sud"] - meteo.lats[0]) / pas)), 0)
        i1 = min(int(np.floor((b["nord"] - meteo.lats[0]) / pas)) + 1, len(meteo.lats) - 1)
        j0 = max(int(np.floor((b["ouest"] - meteo.lons[0]) / pas)), 0)
        j1 = min(int(np.floor((b["est"] - meteo.lons[0]) / pas)) + 1, len(meteo.lons) - 1)
        morceau = pile[:, i0:i1 + 1, j0:j1 + 1]
        entete = np.array([i1 - i0 + 1, j1 - j0 + 1, i0, j0], dtype=np.int16)
        (dossier / f"{nom}.bin").write_bytes(entete.astype("<i2").tobytes() + morceau.astype("<i2").tobytes())
    return ordre


# --- Aperçu national ----------------------------------------------------------------

def grille_apercu(noms_blocs) -> Grille:
    bx = [Bloc.depuis_nom(n).bx for n in noms_blocs]
    by = [Bloc.depuis_nom(n).by for n in noms_blocs]
    par_bloc = BLOC // APERCU
    return Grille(min(bx) * COTE, (max(by) + 1) * COTE, PAS_FIN * APERCU,
                  (max(bx) - min(bx) + 1) * par_bloc, (max(by) - min(by) + 1) * par_bloc)


def communes_apercu(grille: Grille, noms_blocs) -> np.ndarray:
    """La commune (numéro national, 0 = aucune) du centre de chaque pixel de l'aperçu, lue dans la
    couche « c » des blocs : pour peindre les espèces des prés commune par commune en vue large."""
    sortie = np.zeros((grille.ny, grille.nx), dtype=np.uint16)
    par_bloc, demi = BLOC // APERCU, APERCU // 2
    for nom in noms_blocs:
        b = Bloc.depuis_nom(nom)
        c = np.asarray(Image.open(HABITAT / "blocs" / f"{nom}_c.png").convert("RGB"), dtype=np.uint16)
        commune = ((c[..., 0] << 8) | c[..., 1])[demi::APERCU, demi::APERCU]
        lig = round((grille.y1 - (b.by + 1) * COTE) / grille.pas)
        col = round((b.bx * COTE - grille.x0) / grille.pas)
        sortie[lig:lig + par_bloc, col:col + par_bloc] = commune
    return sortie


def indices_communes(commune: np.ndarray, km2: np.ndarray, indice: np.ndarray, n_communes: int) -> np.ndarray:
    """L'indice moyen des prés de chaque commune, en code d'aperçu (0 à ECHELLE ; HORS_FORET là où
    ses prés font moins de PRES_COMMUNE_KM2)."""
    n = np.bincount(commune, weights=km2, minlength=n_communes + 1)
    s = np.bincount(commune, weights=indice * km2, minlength=n_communes + 1)
    moy = np.divide(s, n, out=np.zeros(len(n)), where=n > 0)
    codes = np.clip(np.round(moy * ECHELLE), 0, ECHELLE).astype(np.uint8)
    codes[n < PRES_COMMUNE_KM2] = HORS_FORET
    codes[0] = HORS_FORET
    return codes


def table_communes(codes: np.ndarray) -> np.ndarray:
    """Les codes des communes en image de LARGEUR_TABLE colonnes (le navigateur lit le numéro i en
    ligne i // LARGEUR_TABLE, colonne i % LARGEUR_TABLE)."""
    lignes = -(-len(codes) // LARGEUR_TABLE)
    t = np.full(lignes * LARGEUR_TABLE, HORS_FORET, dtype=np.uint8)
    t[:len(codes)] = codes
    return t.reshape(lignes, LARGEUR_TABLE)


class Apercu:
    """La meilleure case de l'échantillon par pixel de 1,15 km (hors zones protégées) : la règle des
    zones de 250 m (`zones.py`, l'habitat le plus favorable de la zone), pour qu'en zoomant les
    couleurs s'affinent sans changer de ton. Jusqu'au 2026-11-07, la moyenne réduite là où la forêt
    est clairsemée : plus pâle, la carte foncissait d'un coup au passage aux zones."""

    def __init__(self, grille: Grille, ech: Echantillon):
        self.grille = grille
        x, y = lonlat_vers_merc(ech.lon, ech.lat)
        col = np.floor((x - grille.x0) / grille.pas).astype(np.int64)
        lig = np.floor((grille.y1 - y) / grille.pas).astype(np.int64)
        self.pixel = lig * grille.nx + col
        self.nb = grille.nx * grille.ny
        self.libre = ~ech.protege
        self.vide = np.bincount(self.pixel[self.libre], minlength=self.nb) == 0

    def image(self, indice: np.ndarray) -> np.ndarray:
        meilleur = np.zeros(self.nb)
        np.maximum.at(meilleur, self.pixel[self.libre], indice[self.libre])
        code = np.clip(np.round(meilleur * ECHELLE), 0, ECHELLE).astype(np.uint8)
        return np.where(self.vide, HORS_FORET, code).astype(np.uint8).reshape(self.grille.ny, self.grille.nx)


class Vue:
    """« Que chercher ici ? » : par pixel de 9,2 km (VUE pixels d'aperçu), la forêt hors zones
    protégées (km²) et, pour chaque espèce, sa part à l'indice « bon » (≥ 0,40) et « moyen »
    (≥ 0,25) : les parts du verdict des départements (`redaction.niveau`), qui s'additionnent sur
    la zone affichée. Une image par jour, `vue/<k>.png` : les couches empilées en hauteur (la
    forêt, puis bon et moyen de chaque espèce), un octet par pixel. `facteur` : pixels d'aperçu par
    pixel (VUE ; VUE_FINE pour le niveau intermédiaire de la carte, `vue_fine/<k>.png`)."""

    def __init__(self, apercu: Apercu, km2: np.ndarray, facteur: int = VUE):
        g = apercu.grille
        self.nx, self.ny = -(-g.nx // facteur), -(-g.ny // facteur)
        lig, col = np.divmod(apercu.pixel, g.nx)
        self.pixel = (lig // facteur) * self.nx + col // facteur
        self.libre, self.km2 = apercu.libre, km2
        self.surface = self._somme(self.libre)
        self.couches = [np.clip(np.round(self.surface * KM2_PAR), 0, 255)]

    def _somme(self, sel: np.ndarray) -> np.ndarray:
        return np.bincount(self.pixel[sel], weights=self.km2[sel], minlength=self.nx * self.ny)

    def ajouter(self, indice: np.ndarray) -> None:
        for seuil in (M.CLASSES[2][0], M.CLASSES[1][0]):            # « bon », puis « moyen »
            part = np.divide(self._somme(self.libre & (indice >= seuil)), self.surface,
                             out=np.zeros(self.nx * self.ny), where=self.surface > 0)
            self.couches.append(np.round(part * PARTS_PAR))

    def image(self) -> np.ndarray:
        return np.concatenate([c.reshape(self.ny, self.nx) for c in self.couches]).astype(np.uint8)


def pixels_vue(grille: Grille, lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, int, int]:
    """Le carré de la grille de « Que chercher ici ? » (VUE pixels d'aperçu de `grille`) de chaque
    point, et la taille de cette grille (nx, ny)."""
    x, y = lonlat_vers_merc(lon, lat)
    pas = grille.pas * VUE
    nx, ny = -(-grille.nx // VUE), -(-grille.ny // VUE)
    col = np.clip(np.floor((x - grille.x0) / pas).astype(np.int64), 0, nx - 1)
    lig = np.clip(np.floor((grille.y1 - y) / pas).astype(np.int64), 0, ny - 1)
    return lig * nx + col, nx, ny


def verdicts_carres(pixel: np.ndarray, nx: int, ny: int, km2: np.ndarray, libre: np.ndarray,
                    indice: np.ndarray, saison: np.ndarray) -> np.ndarray:
    """Le verdict des départements (`redaction.niveau`, mêmes seuils) sur chaque carré de 9,2 km,
    pour la carte de l'accueil : 0 hors saison, 1 défavorable, 2 possible, 3 par endroits, 4 bon ;
    -1 sous CARRE_MIN_KM2 de forêt (de prés) hors zones protégées, pour qu'un bosquet ne colore
    pas un carré. Les parts : la forêt à 0,40 et plus (« bon »), à 0,25 et plus (« moyen »)."""
    n = nx * ny
    p, k = pixel[libre], km2[libre]
    surface = np.bincount(p, weights=k, minlength=n)
    part = {nom: np.divide(np.bincount(p, weights=k * (indice[libre] >= seuil), minlength=n), surface,
                           out=np.zeros(n), where=surface > 0)
            for nom, seuil in (("bon", M.CLASSES[2][0]), ("moyen", M.CLASSES[1][0]))}
    en_saison = np.bincount(p, weights=(saison[libre] > 0).astype(np.float64), minlength=n) > 0
    s = redaction.SEUILS_NIVEAU
    niv = np.where(part["bon"] >= s["bon"], 4, np.where(part["bon"] >= s["endroits"], 3,
                   np.where(part["moyen"] >= s["possible"], 2, 1)))
    niv = np.where(en_saison, niv, 0)
    return np.where(surface >= CARRE_MIN_KM2, niv, -1).astype(np.int8).reshape(ny, nx)


# --- Faits du panneau, par département ------------------------------------------------

def faits(esp: E.Espece, jour: date, sel: np.ndarray, ech: Echantillon, km2: np.ndarray,
          habitat, indice, facteurs, pluie, tsol, noms_communes: list[str]) -> dict:
    """Les faits d'un département (cases `sel` de l'échantillon) : mêmes clés que
    `export.faits_du_jour`, que `redaction.rediger` met en phrases."""
    libre = sel & ~ech.protege
    poids = habitat[libre]
    total = float(poids.sum()) or 1.0

    def moy(v):
        return float((v[libre] * poids).sum() / total)

    lat_moy = float(ech.lat[sel].mean())
    saison = float(M.facteur_saison(esp, jour, lat_moy))
    seuils = np.array([s for s, _ in M.CLASSES])
    k = np.minimum(np.searchsorted(seuils, indice[libre], side="right"), len(seuils) - 1)
    parts = (np.bincount(k, weights=km2[libre], minlength=len(seuils)) / max(km2[libre].sum(), 1e-9)).tolist()

    tranche = (ech.altitude[libre] // TRANCHE_M).astype(int)
    tranches = []
    for t in np.unique(tranche):
        s = tranche == t
        surface = float(km2[libre][s].sum())
        if surface < 5:                     # moins de 5 km² de forêt : trop peu pour en parler
            continue
        tranches.append({"de": int(t * TRANCHE_M), "a": int((t + 1) * TRANCHE_M),
                         "indice": round(float(indice[libre][s].mean()), 4),
                         "sol": round(float(tsol[libre][s].mean()), 1), "km2": round(surface, 1)})
    meilleure = max(tranches, key=lambda t: t["indice"], default=None)
    froid = [t for t in tranches if t["sol"] < esp.sol[1]]
    chaud = [t for t in tranches if t["sol"] > esp.sol[2]]

    moyens = {n: moy(v) for n, v in facteurs.items()}
    candidats = dict(moyens, saison=saison)
    limitant = min(candidats, key=candidats.get)
    if candidats[limitant] >= 0.7:
        limitant = "aucun"
    elif limitant == "sol":
        limitant = ("sol_froid" if moy((tsol < esp.sol[1]).astype(np.float32))
                    >= moy((tsol > esp.sol[2]).astype(np.float32)) else "sol_chaud")

    a, b, c_, d = M.dates_saison(esp, jour.year, lat_moy)
    com = ech.commune[libre]
    n = np.bincount(com, weights=km2[libre], minlength=len(noms_communes) + 1)
    s = np.bincount(com, weights=indice[libre] * km2[libre], minlength=len(noms_communes) + 1)
    moyenne_c = np.divide(s, n, out=np.zeros_like(s), where=n >= 0.25)     # au moins 25 ha boisés
    clat = np.bincount(com, weights=ech.lat[libre] * km2[libre], minlength=len(noms_communes) + 1)
    clon = np.bincount(com, weights=ech.lon[libre] * km2[libre], minlength=len(noms_communes) + 1)
    par_commune = [{"nom": noms_communes[i - 1], "indice": round(float(moyenne_c[i]), 4),
                    "classe": M.classe(float(moyenne_c[i])),
                    "centre": [round(float(clat[i] / n[i]), 4), round(float(clon[i] / n[i]), 4)]}
                   for i in np.argsort(-moyenne_c)[:8] if moyenne_c[i] > 0]
    return {
        "saison": round(saison, 3),
        "debut_saison": bool(jour.toordinal() < (b + c_) / 2),
        "indice_moyen": round(float(indice[libre].mean()) if libre.any() else 0.0, 4),
        "km2": round(float(km2[libre].sum()), 1),       # forêt hors zones protégées

        "part_bon": round(sum(parts[3:]), 4),
        "part_moyen": round(sum(parts[2:]), 4),
        "classes": [round(p, 4) for p in parts],
        "facteurs": {k_: round(v, 3) for k_, v in moyens.items()},
        "limitant": limitant,
        "pluie_moy": round(moy(pluie), 1),
        "tranches": tranches,
        "meilleure_tranche": [meilleure["de"], meilleure["a"]] if meilleure and meilleure["indice"] >= 0.1 else None,
        "froid_au_dessus": min(t["de"] for t in froid) if froid and len(froid) < len(tranches) else None,
        "chaud_en_dessous": max(t["a"] for t in chaud) if chaud and len(chaud) < len(tranches) else None,
        "communes": par_commune,
    }


# --- Orchestration ------------------------------------------------------------------

def exporter(meteo: Meteo | None = None) -> dict:
    t0 = time.time()
    index, communes, departements, ech = charger_habitat()
    noms_blocs = sorted(index["blocs"])
    print(f"Habitat : {len(noms_blocs)} blocs, échantillon {len(ech.lat) / 1e6:.2f} M cases ({time.time() - t0:.0f} s)")
    modeles = {}
    if meteo is None:
        meteo = depot.meteo_france(jours_futurs=JOURS_FUTURS)
        modeles = depot.sources()
    k0 = len(meteo.dates) - JOURS_FUTURS
    aujourdhui = meteo.dates[k0]
    print(f"Météo : {len(meteo.lats)} × {len(meteo.lons)} points, {meteo.dates[0]} → {meteo.dates[-1]} "
          f"({time.time() - t0:.0f} s)")

    champs = champs_du_jour(meteo, k0)
    ordre = ecrire_meteo_blocs(champs, meteo, noms_blocs)
    print(f"  météo de {len(noms_blocs)} blocs ({time.time() - t0:.0f} s)")

    calcul = CalculChamps(champs, meteo.lats, meteo.lons, ech.lat, ech.lon, ech.altitude, ech.ensoleillement)
    g_apercu = grille_apercu(noms_blocs)
    apercu = Apercu(g_apercu, ech)
    km2 = (PAS_FIN * ECHANTILLON * np.cos(np.radians(ech.lat))) ** 2 / 1e6   # surface représentée
    noms_communes = [c["nom"] for c in communes]
    regles = E.en_json()
    par_dep = [ech.departement == k for k in range(len(departements))]
    resumes = {d["code"]: {} for d in departements}
    classement = {}
    meilleure = None
    une = {}                         # le verdict de chaque carré aujourd'hui : les cartes de l'accueil
    carres, nx_c, ny_c = pixels_vue(g_apercu, ech.lat, ech.lon)
    vues = [Vue(apercu, km2) for _ in range(JOURS_FUTURS)]
    vues_fines = [Vue(apercu, km2, VUE_FINE) for _ in range(JOURS_FUTURS)]
    # Les prés (espèces des champs) : leur propre échantillon, jamais publié point par point.
    lus = charger_pres(communes, departements)
    if lus:
        pres, milieux = lus
        carres_pres = pixels_vue(g_apercu, pres.lat, pres.lon)[0]
        calcul_pres = CalculChamps(champs, meteo.lats, meteo.lons, pres.lat, pres.lon, pres.altitude,
                                   pres.ensoleillement)
        km2_pres = (prairies.PAS * np.cos(np.radians(pres.lat))) ** 2 / 1e6
        par_dep_pres = [pres.departement == k for k in range(len(departements))]
        print(f"  prés : {len(pres.lat) / 1e6:.2f} M points ({time.time() - t0:.0f} s)")
    especes = [e for e in E.ESPECES if e.milieu == "foret" or lus]
    if lus:
        communes_px = communes_apercu(g_apercu, noms_blocs)
        print(f"  communes de l'aperçu ({time.time() - t0:.0f} s)")
    regles["especes"] = [x for x in regles["especes"] if x["code"] in {e.code for e in especes}]
    for esp in especes:
        foret = esp.milieu == "foret"
        if foret:
            e_, calc, surf, selections = ech, calcul, km2, par_dep
            habitat = M.facteur_habitat(esp, ech.essence, ech.ouverte, ech.roche, ech.altitude, ech.pente, ech.lat,
                                        ph=ech.ph)
        else:
            e_, calc, surf, selections = pres, calcul_pres, km2_pres, par_dep_pres
            habitat = M.facteur_habitat_pre(esp, milieux, pres.altitude, pres.lat)
        regle = next(e for e in regles["especes"] if e["code"] == esp.code)
        classement[esp.code] = []
        for k in range(JOURS_FUTURS):
            jour = meteo.dates[k0 + k]
            saison = M.facteur_saison(esp, jour, e_.lat)
            pluie, tsol, gel = calc.entrees(esp, k)
            facteurs = M.facteurs_meteo(esp, pluie, tsol, gel)
            ind = M.indice(habitat, saison, facteurs)
            if foret:
                image = apercu.image(ind)
                ecrire_png(SITE_DATA / "apercu" / f"{esp.code}_{k}.png", image)
                vues[k].ajouter(ind)
                vues_fines[k].ajouter(ind)
                if k == 0:   # l'image de partage : la meilleure espèce de chaque pixel, aujourd'hui
                    meilleure = image if meilleure is None else np.maximum(meilleure, image)
                    une[esp.code] = verdicts_carres(carres, nx_c, ny_c, km2, ~ech.protege, ind, saison)
            else:            # les prés, commune par commune : jamais point par point
                codes = indices_communes(pres.commune, km2_pres, ind, len(communes))
                ecrire_png(SITE_DATA / "communes" / f"{esp.code}_{k}.png", table_communes(codes))
                ecrire_png(SITE_DATA / "apercu" / f"{esp.code}_{k}.png", codes[communes_px])
                if k == 0:   # des carrés de 9,2 km : jamais un pré
                    une[esp.code] = verdicts_carres(carres_pres, nx_c, ny_c, km2_pres, ~pres.protege, ind, saison)
            jour_classement = []
            for dep, sel in zip(departements, selections):
                if not sel.any():
                    continue
                f = faits(esp, jour, sel, e_, surf, habitat, ind, facteurs, pluie, tsol, noms_communes)
                resumes[dep["code"]].setdefault(esp.code, []).append({**f, **redaction.rediger(regle, f)})
                jour_classement.append((dep["code"], f["indice_moyen"], f["part_bon"]))
            jour_classement.sort(key=lambda t: -t[1])
            classement[esp.code].append([{"dep": d, "indice": i, "part_bon": p} for d, i, p in jour_classement[:12]])
        print(f"  {esp.nom} ({time.time() - t0:.0f} s)")
    for k, v in enumerate(vues_fines):
        ecrire_png(SITE_DATA / "vue_fine" / f"{k}.png", v.image())
    for k, v in enumerate(vues):
        ecrire_png(SITE_DATA / "vue" / f"{k}.png", v.image())

    noms_dep = json.loads((DATA / "departements.json").read_text(encoding="utf-8"))
    for dep in departements:
        sel = ech.departement == departements.index(dep)
        dep["nom"] = noms_dep.get(dep["code"], dep["code"])
        if sel.any():
            dep["centre"] = [round(float(np.median(ech.lat[sel])), 4), round(float(np.median(ech.lon[sel])), 4)]
            dep["bornes"] = [round(float(ech.lat[sel].min()), 3), round(float(ech.lon[sel].min()), 3),
                             round(float(ech.lat[sel].max()), 3), round(float(ech.lon[sel].max()), 3)]
            ecrire_json(SITE_DATA / "resumes" / f"{dep['code']}.json", resumes[dep["code"]])
    # Un « département » sans forêt échantillonnée n'est pas à proposer : Saint-Pierre-et-
    # Miquelon (« NR » dans ADMIN EXPRESS) dans les listes de communes d'avant le 2026-10-31.
    rang = {d["code"]: k for k, d in enumerate(departements)}      # celui de `ech.departement`
    departements = [d for d in departements if "centre" in d]

    chemin_validation = DATA / "validation.json"
    validation = (json.loads(chemin_validation.read_text(encoding="utf-8"))
                  if chemin_validation.exists() else None)
    # La fiabilité affichée est celle de la France entière ; les régions sont sur la page.
    fiabilite = ({code: redaction.fiabilite(r["meteo"])
                  for code, r in validation["regions"]["france"]["especes"].items()}
                 if validation else {})
    clim = climatologie.charger()        # « météo favorable 7 années sur 10 à cette date »
    b = g_apercu.bornes_lonlat()
    carte = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "echelle": ECHELLE,
        "codes": {"hors_foret": HORS_FORET, "hors_france": HORS_FRANCE},
        "classes": [{"seuil": s, "nom": n} for s, n in M.CLASSES],
        "jours": [{"date": meteo.dates[k0 + k].isoformat(),
                   "libelle": redaction.libelle_jour(meteo.dates[k0 + k], aujourdhui)}
                  for k in range(JOURS_FUTURS)],
        "especes": [{"code": e.code, "nom": e.nom, "latin": e.latin, "milieu": e.milieu} for e in especes],
        "apercu": {"grille": g_apercu.en_dict(), "bornes": b},
        "communes_table": LARGEUR_TABLE,
        "vue": {"facteur": VUE, "nx": vues[0].nx, "ny": vues[0].ny, "especes": [e.code for e in E.DE_FORET],
                "km2_par": KM2_PAR, "parts_par": PARTS_PAR, "carre_min_km2": CARRE_MIN_KM2},
        # Le niveau intermédiaire de la carte : la même chose par carré de 4,6 km ; le minimum de forêt
        # garde la même part du carré (5 %).
        "vue_fine": {"facteur": VUE_FINE, "nx": vues_fines[0].nx, "ny": vues_fines[0].ny,
                     "carre_min_km2": CARRE_MIN_KM2 * (VUE_FINE / VUE) ** 2},
        "niveaux": redaction.SEUILS_NIVEAU,
        "blocs": {"cote": COTE, "taille": BLOC, "pas": PAS_FIN, "altitude_decalage": index["altitude_decalage"],
                  "liste": noms_blocs},
        "meteo": {"lat0": float(meteo.lats[0]), "lon0": float(meteo.lons[0]),
                  "pas": float(meteo.lats[1] - meteo.lats[0]), "champs": ordre, "premier_gel": PREMIER_GEL,
                  "modeles": modeles},
        # Chaque département avec l'adresse de sa page (carte.js : « La semaine … sur une page à part »).
        "departements": [dict(d, page=pages.chemin_departement(d["code"], d["nom"])) for d in departements],
        "legendes": {"essences": ESSENCES, "roches": ROCHES, "orientations": ORIENTATIONS},
        "classement": classement,
        "fiabilite": fiabilite,
        "habituel": {"seuil": clim["seuil"], "periode": clim["periode"]} if clim else None,
        "habitat_construit_le": index["construit_le"],
        # Alertes : la clé publique des notifications, et si l'envoi est branché (secrets posés).
        "alertes": {"cle_push": VAPID_PUBLIQUE, "actives": os.environ.get("ALERTES_ACTIVES") == "true"},
        "blocs_manquants": len(index.get("manquants", [])),
    }
    ecrire_json(SITE_DATA / "carte.json", carte)
    ecrire_json(SITE_DATA / "especes.json", regles)
    if validation:
        ecrire_json(SITE_DATA / "validation.json", validation)
    # Les contours des départements, pour la carte (versionnés dans data/, publiés à côté des données).
    if (contours_deps := carte_departements.charger()):
        ecrire_json(SITE_DATA / "departements_carte.json", contours_deps)
    # Et leurs tracés fins (~250 m), pour la carte de près : les limites d'un fichier, le contour de
    # chaque département à part (la carte ne charge que celui du département choisi).
    if (fins := carte_departements.charger_fin()):
        tete = {"origine": fins["origine"], "unite": fins["unite"]}
        ecrire_json(SITE_DATA / "contours_fins" / "frontieres.json", {**tete, "frontieres": fins["frontieres"]})
        for code, trace in fins["departements"].items():
            ecrire_json(SITE_DATA / "contours_fins" / f"{code}.json", {**tete, "trace": trace})
    jours = [meteo.dates[k0 + k] for k in range(JOURS_FUTURS)]
    # Pour les pages seulement (especes.json reste les règles) : ce qui est habituel aujourd'hui.
    for x in regles["especes"]:
        x["habituel"] = climatologie.frequence(clim, x["code"], jours[0])
    chemins = pages_departements.ecrire(SITE, departements, regles["especes"], resumes, jours, carte["genere_le"])
    chemins += pages_accueil.ecrire(SITE, departements, regles["especes"], resumes, jours, carte["genere_le"],
                                    validation)
    chemins += pages_especes.ecrire(SITE, departements, regles, carte["legendes"], resumes, jours,
                                    carte["genere_le"], validation)
    pages.ecrire_plan(SITE, chemins, jours[0])
    pixel_dep = np.full(apercu.nb, -1, dtype=np.int16)
    pixel_dep[apercu.pixel] = ech.departement
    contours = carte_departements.charger() or {}
    partage.ecrire(SITE_DATA / "partage", departements, rang, regles["especes"], resumes,
                   pages.national(regles["especes"], departements, resumes, len(jours)), jours,
                   meilleure, pixel_dep, ECHELLE, [s for s, _ in M.CLASSES],
                   une=une, grille=Grille(g_apercu.x0, g_apercu.y1, g_apercu.pas * VUE, nx_c, ny_c),
                   cadre=carte_departements.cadre_une(contours)[1] if "cadre" in contours else None)
    print(f"Écrit site/data/ et {len(chemins)} pages en {time.time() - t0:.0f} s")
    return carte


if __name__ == "__main__":
    exporter()
