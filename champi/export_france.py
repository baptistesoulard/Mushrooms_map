"""Job quotidien, France entière : météo du jour → données du site, dans `site/data/`.

    python -m champi.export_france

Le site calcule lui-même l'indice à 50 m, bloc par bloc (`site/modele.js`), à partir de
l'habitat (release « habitat », copié dans `site/habitat/`) et de la météo du jour. Ce job
écrit donc surtout de la météo, plus ce que le navigateur ne peut pas calculer seul :

- `meteo/<bloc>.bin` : pour chaque bloc, les champs météo du jour aux points AROME qui le
  couvrent (entiers 16 bits en dixièmes ; en-tête [lignes, colonnes, i0, j0] ; ordre des
  champs dans `carte.json` → `meteo.champs`) ;
- `apercu/<espèce>_<k>.png` : l'indice de toute la France par pixels de 1,15 km (vue large) ;
- `resumes/<département>.json` : faits et phrases du panneau, par espèce et par jour ;
- `carte.json` (jours, classement des départements, légendes), `especes.json`, `validation.json`.

Puis les pages lisibles sans JavaScript, à côté de la carte (`site/carte/`) : l'accueil et « en
ce moment » (`pages_accueil`), les fiches espèces (`pages_especes`), les départements
(`pages_departements`).

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

from . import depot
from . import especes as E
from . import modele as M
from . import pages
from . import pages_accueil
from . import pages_departements
from . import pages_especes
from . import redaction
from .config import DATA, PAS_FIN, RACINE, SITE, SITE_DATA, VAPID_PUBLIQUE
from .export import COUVERTURE_PLEINE, ECHELLE, HORS_FORET, JOURS_FUTURS, TRANCHE_M, ecrire_png
from .france import BLOC, COTE, ECHANTILLON, Bloc
from .grille import Grille, lonlat_vers_merc
from .habitat import ESSENCES, ORIENTATIONS, ROCHES
from .meteo import Interpolateur, Meteo
from .sources import ecrire_json

HABITAT = RACINE / "site" / "habitat"
APERCU = 16                          # cases de 50 m par pixel d'aperçu (1 152 m Mercator)
HORS_FRANCE = 255
PREMIER_GEL = -6                     # le gel compte sur les 7 jours finissant au jour affiché


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


class Apercu:
    """Moyenne de l'échantillon par pixel de 1,15 km, réduite là où la forêt est clairsemée."""

    def __init__(self, grille: Grille, ech: Echantillon):
        self.grille = grille
        x, y = lonlat_vers_merc(ech.lon, ech.lat)
        col = np.floor((x - grille.x0) / grille.pas).astype(np.int64)
        lig = np.floor((grille.y1 - y) / grille.pas).astype(np.int64)
        self.pixel = lig * grille.nx + col
        self.nb = grille.nx * grille.ny
        self.libre = ~ech.protege
        n = np.bincount(self.pixel, minlength=self.nb)
        par_pixel = (APERCU // ECHANTILLON) ** 2                       # 16 cases d'échantillon
        self.couverture = np.minimum(1.0, n / par_pixel / COUVERTURE_PLEINE)
        self.vide = np.bincount(self.pixel[self.libre], minlength=self.nb) == 0

    def image(self, indice: np.ndarray) -> np.ndarray:
        n = np.bincount(self.pixel[self.libre], minlength=self.nb)
        s = np.bincount(self.pixel[self.libre], weights=indice[self.libre], minlength=self.nb)
        moy = np.divide(s, n, out=np.zeros(self.nb), where=n > 0) * self.couverture
        code = np.clip(np.round(moy * ECHELLE), 0, ECHELLE).astype(np.uint8)
        return np.where(self.vide, HORS_FORET, code).astype(np.uint8).reshape(self.grille.ny, self.grille.nx)


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
    for esp in E.ESPECES:
        habitat = M.facteur_habitat(esp, ech.essence, ech.ouverte, ech.roche, ech.altitude, ech.pente, ech.lat,
                                    ph=ech.ph)
        regle = next(e for e in regles["especes"] if e["code"] == esp.code)
        classement[esp.code] = []
        for k in range(JOURS_FUTURS):
            jour = meteo.dates[k0 + k]
            saison = M.facteur_saison(esp, jour, ech.lat)
            pluie, tsol, gel = calcul.entrees(esp, k)
            facteurs = M.facteurs_meteo(esp, pluie, tsol, gel)
            ind = M.indice(habitat, saison, facteurs)
            ecrire_png(SITE_DATA / "apercu" / f"{esp.code}_{k}.png", apercu.image(ind))
            jour_classement = []
            for dep, sel in zip(departements, par_dep):
                if not sel.any():
                    continue
                f = faits(esp, jour, sel, ech, km2, habitat, ind, facteurs, pluie, tsol, noms_communes)
                resumes[dep["code"]].setdefault(esp.code, []).append({**f, **redaction.rediger(regle, f)})
                jour_classement.append((dep["code"], f["indice_moyen"], f["part_bon"]))
            jour_classement.sort(key=lambda t: -t[1])
            classement[esp.code].append([{"dep": d, "indice": i, "part_bon": p} for d, i, p in jour_classement[:12]])
        print(f"  {esp.nom} ({time.time() - t0:.0f} s)")

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
    departements = [d for d in departements if "centre" in d]

    chemin_validation = DATA / "validation.json"
    validation = (json.loads(chemin_validation.read_text(encoding="utf-8"))
                  if chemin_validation.exists() else None)
    # La fiabilité affichée est celle de la France entière ; les régions sont sur la page.
    fiabilite = ({code: redaction.fiabilite(r["meteo"])
                  for code, r in validation["regions"]["france"]["especes"].items()}
                 if validation else {})
    b = g_apercu.bornes_lonlat()
    carte = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "echelle": ECHELLE,
        "codes": {"hors_foret": HORS_FORET, "hors_france": HORS_FRANCE},
        "classes": [{"seuil": s, "nom": n} for s, n in M.CLASSES],
        "jours": [{"date": meteo.dates[k0 + k].isoformat(),
                   "libelle": redaction.libelle_jour(meteo.dates[k0 + k], aujourdhui)}
                  for k in range(JOURS_FUTURS)],
        "especes": [{"code": e.code, "nom": e.nom, "latin": e.latin} for e in E.ESPECES],
        "apercu": {"grille": g_apercu.en_dict(), "bornes": b},
        "blocs": {"cote": COTE, "taille": BLOC, "pas": PAS_FIN, "altitude_decalage": index["altitude_decalage"],
                  "liste": noms_blocs},
        "meteo": {"lat0": float(meteo.lats[0]), "lon0": float(meteo.lons[0]),
                  "pas": float(meteo.lats[1] - meteo.lats[0]), "champs": ordre, "premier_gel": PREMIER_GEL,
                  "modeles": modeles},
        "departements": departements,
        "legendes": {"essences": ESSENCES, "roches": ROCHES, "orientations": ORIENTATIONS},
        "classement": classement,
        "fiabilite": fiabilite,
        "habitat_construit_le": index["construit_le"],
        # Alertes : la clé publique des notifications, et si l'envoi est branché (secrets posés).
        "alertes": {"cle_push": VAPID_PUBLIQUE, "actives": os.environ.get("ALERTES_ACTIVES") == "true"},
        "blocs_manquants": len(index.get("manquants", [])),
    }
    ecrire_json(SITE_DATA / "carte.json", carte)
    ecrire_json(SITE_DATA / "especes.json", regles)
    if validation:
        ecrire_json(SITE_DATA / "validation.json", validation)
    jours = [meteo.dates[k0 + k] for k in range(JOURS_FUTURS)]
    chemins = pages_departements.ecrire(SITE, departements, regles["especes"], resumes, jours, carte["genere_le"])
    chemins += pages_accueil.ecrire(SITE, departements, regles["especes"], resumes, jours, carte["genere_le"],
                                    validation)
    chemins += pages_especes.ecrire(SITE, departements, regles, carte["legendes"], resumes, jours,
                                    carte["genere_le"], validation)
    pages.ecrire_plan(SITE, chemins)
    print(f"Écrit site/data/ et {len(chemins)} pages en {time.time() - t0:.0f} s")
    return carte


if __name__ == "__main__":
    exporter()
