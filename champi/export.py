"""Job quotidien : météo du jour → indice par espèce, d'aujourd'hui à J+7 → `site/data/`.

    python -m champi.export

Le site, à usage personnel, publie la grille de calcul de 50 m. Fichiers écrits :
- `indice/<espèce>_<k>.png` (k = 0 à 7 ; niveaux de gris ; 50 m) : indice × 200, ou un
  code (251 hors forêt, 252 zone protégée, 255 hors département) ;
- `sol_<k>.png` (50 m) : température du sol de la case, (°C + 10) × 5, 255 hors forêt ;
- `pluie/<espèce>_<k>.png` (zones de 250 m) : pluie de la fenêtre de l'espèce, mm ;
- `attributs.png`, `lieux.png` (50 m, RVB) : altitude, forêt, roche, exposition, commune,
  zone protégée ;
- `carte.json` (jours, légendes, faits et phrases du panneau), `especes.json` (règles),
  `validation.json`.
Seuls `carte.json` et l'indice affiché se chargent d'emblée ; le reste au premier clic.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

import numpy as np
from PIL import Image

from . import especes as E
from . import modele as M
from . import redaction
from .config import DATA, DEPARTEMENT, FACTEUR_ZONE, NOM_DEPARTEMENT, SITE_DATA
from .grille import Grille
from .meteo import Interpolateur, Meteo, previsions
from .sources import ecrire_json

JOURS_FUTURS = 8
TRANCHE_M = 200
ECHELLE = 200                        # indice publié = round(indice × 200)
HORS_DEPARTEMENT, HORS_FORET, PROTEGE = 255, 251, 252
COUVERTURE_PLEINE = 0.3              # une zone à 30 % boisée ou plus garde tout son indice
PART_FORET_MIN = 0.16                # en dessous, la zone est « hors forêt » (4 cases sur 25)


def code_sol(t):
    """Température du sol (°C) codée sur 0-254 : (t + 10) × 5, de -10 à 40,8 °C."""
    return (np.asarray(t) + 10) * 5


@dataclass
class Cases:
    """Les cases de 50 m boisées (ou en lande) du département, à plat."""

    lignes: np.ndarray
    colonnes: np.ndarray
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


def charger_habitat() -> tuple[Grille, dict, dict]:
    h = dict(np.load(DATA / f"habitat_{DEPARTEMENT}.npz"))
    meta = json.loads((DATA / f"habitat_{DEPARTEMENT}.json").read_text(encoding="utf-8"))
    return Grille.depuis_dict(meta["grille"]), h, meta


def cases_de_foret(grille: Grille, h: dict) -> Cases:
    lig, col = np.nonzero((h["commune"] > 0) & (h["essence"] > 0))
    return Cases(
        lignes=lig, colonnes=col,
        lat=grille.latitudes()[lig], lon=grille.longitudes()[col],
        altitude=h["altitude"][lig, col].astype(np.float32),
        ensoleillement=h["ensoleillement"][lig, col].astype(np.float32) / 100,
        pente=h["pente"][lig, col], essence=h["essence"][lig, col], ouverte=h["ouverte"][lig, col],
        roche=h["roche"][lig, col], protege=h["protege"][lig, col], commune=h["commune"][lig, col],
    )


# --- Calcul -------------------------------------------------------------------------

class Calcul:
    """Toutes les grandeurs d'un jour, pour toutes les cases, sans recopier 38 jours de météo.

    La pluie cumulée et la température moyenne sont linéaires : on les cumule aux points
    météo, puis on interpole (identique à interpoler chaque jour puis cumuler, en bien
    moins de mémoire ; vérifié par `tests/test_export.py`). Le gel, non linéaire, est
    compté case par case.
    """

    def __init__(self, meteo: Meteo, cases: Cases):
        self.meteo, self.cases = meteo, cases
        self.interp = Interpolateur(meteo.lats, meteo.lons, cases.lat, cases.lon)
        self._gel: dict[int, np.ndarray] = {}
        self._sol: dict[int, np.ndarray] = {}

    def _gele(self, d: int) -> np.ndarray:
        if d not in self._gel:
            tmin = M.temperature_locale(self.interp(self.meteo.tmin_mer[d]), self.cases.altitude, E.GRADIENT_AIR)
            self._gel[d] = tmin < E.GEL_SEUIL
        return self._gel[d]

    def sol(self, k: int) -> np.ndarray:
        """Température du sol de chaque case, moyenne des 7 jours précédant le jour k."""
        if k not in self._sol:
            c, m = self.cases, self.meteo
            self._sol[k] = M.temperature_locale(self.interp(m.tsol_mer[k - 7:k].mean(axis=0)), c.altitude,
                                                E.GRADIENT_SOL, c.ensoleillement, E.SOLEIL_SOL)
        return self._sol[k]

    def entrees(self, esp: E.Espece, k: int):
        """Mêmes sorties que `modele.entrees_meteo`, calculées par la voie rapide."""
        c, m = self.cases, self.meteo
        j_min, j_max = esp.pluie_jours
        pluie = self.interp(m.pluie[k - j_max:k - j_min + 1].sum(axis=0))
        gel = np.zeros(len(c.lat), dtype=np.int8)
        for d in range(k - 6, k + 1):
            gel += self._gele(d)
        return M.pluie_efficace(pluie, c.ensoleillement), self.sol(k), gel


# --- Passage aux grilles publiées ---------------------------------------------------

class Agregat:
    """Des cases de 50 m vers une grille de `facteur` × `facteur` cases (1 : la grille même)."""

    def __init__(self, grille: Grille, h: dict, cases: Cases, facteur: int):
        f = self.facteur = facteur
        self.publie = grille.grossir(f)
        nb = self.nb = self.publie.nx * self.publie.ny
        self.cases = cases
        self.bloc = (cases.lignes // f) * self.publie.nx + cases.colonnes // f
        dans = h["commune"] > 0
        self.n_dept = dans.reshape(self.publie.ny, f, self.publie.nx, f).sum(axis=(1, 3)).ravel()
        self.n_foret = np.bincount(self.bloc, minlength=nb)
        self.libre = cases.protege == 0
        self.n_libre = np.bincount(self.bloc[self.libre], minlength=nb)
        self.couverture = np.minimum(1.0, self.n_foret / (f * f) / COUVERTURE_PLEINE)
        min_foret = max(1, round(PART_FORET_MIN * f * f))
        code = np.zeros(nb, dtype=np.uint8)
        code[self.n_foret < min_foret] = HORS_FORET
        code[(self.n_foret >= min_foret) & (2 * (self.n_foret - self.n_libre) >= self.n_foret)] = PROTEGE
        code[self.n_dept < (f * f) / 2] = HORS_DEPARTEMENT
        self.code_fixe = code

    def _moyenne(self, valeurs, masque=None) -> np.ndarray:
        b = self.bloc if masque is None else self.bloc[masque]
        v = valeurs if masque is None else valeurs[masque]
        n = np.bincount(b, minlength=self.nb)
        s = np.bincount(b, weights=v, minlength=self.nb)
        return np.divide(s, n, out=np.zeros(self.nb), where=n > 0)

    def _image(self, valeurs: np.ndarray) -> np.ndarray:
        return valeurs.reshape(self.publie.ny, self.publie.nx)

    def indice(self, indice_cases) -> np.ndarray:
        """Indice publié : moyenne des cases libres, réduite si la zone est peu boisée."""
        moy = self._moyenne(indice_cases, self.libre) * self.couverture
        code = np.clip(np.round(moy * ECHELLE), 0, ECHELLE).astype(np.uint8)
        return self._image(np.where(self.code_fixe > 0, self.code_fixe, code))

    def valeurs(self, valeurs_cases, codage=lambda v: v) -> np.ndarray:
        """Moyenne par zone d'une grandeur, codée sur 0-254 ; 255 là où il n'y a pas de forêt."""
        code = np.clip(np.round(codage(self._moyenne(valeurs_cases))), 0, 254).astype(np.uint8)
        return self._image(np.where(self.n_foret > 0, code, 255).astype(np.uint8))


def images_fixes(h: dict) -> tuple[np.ndarray, np.ndarray]:
    """attributs : R altitude/20, G essence | publique<<4 | ouverte<<5, B roche | orientation<<2.
    lieux : R, G commune (16 bits), B zone protégée."""
    def u8(a):
        return np.asarray(a).astype(np.uint8)

    attributs = np.dstack([
        u8(np.clip(np.round(np.maximum(h["altitude"], 0) / 20), 0, 255)),
        u8(h["essence"]) | (u8(h["public"]) << 4) | (u8(h["ouverte"]) << 5),
        u8(h["roche"]) | (u8(h["orientation"]) << 2),
    ])
    commune = h["commune"].astype(np.int64)
    lieux = np.dstack([u8(commune & 255), u8(commune >> 8), u8(h["protege"])])
    return attributs, lieux


def ecrire_png(chemin, image: np.ndarray) -> None:
    """Niveaux de gris pour une grille 2D, RVB pour une grille à trois canaux."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, "L" if image.ndim == 2 else "RGB").save(chemin, optimize=True)


# --- Faits du jour ------------------------------------------------------------------

def faits_du_jour(esp: E.Espece, jour: date, saison: float, habitat, indice_cases, facteurs,
                  pluie, tsol, cases: Cases, codes_publies: np.ndarray, noms_communes: list[str]) -> dict:
    libre = cases.protege == 0
    poids = habitat[libre]
    total = float(poids.sum()) or 1.0

    def moy(v):
        return float((v[libre] * poids).sum() / total)

    # Classes, sur les cases publiées boisées : ce que le lecteur voit sur la carte.
    visibles = codes_publies[codes_publies <= ECHELLE] / ECHELLE
    seuils = np.array([seuil for seuil, _ in M.CLASSES])
    k = np.minimum(np.searchsorted(seuils, visibles, side="right"), len(seuils) - 1)
    parts = (np.bincount(k, minlength=len(seuils)) / max(len(visibles), 1)).tolist()

    tranche = (cases.altitude[libre] // TRANCHE_M).astype(int)
    tranches = []
    for t in np.unique(tranche):
        sel = tranche == t
        if sel.sum() < 2000:           # moins de 5 km² de forêt : trop peu pour en parler
            continue
        tranches.append({
            "de": int(t * TRANCHE_M), "a": int((t + 1) * TRANCHE_M),
            "indice": round(float(indice_cases[libre][sel].mean()), 4),
            "sol": round(float(tsol[libre][sel].mean()), 1),
            "km2": round(float(sel.sum()) * 0.0025, 1),
        })

    meilleure = max(tranches, key=lambda t: t["indice"], default=None)
    froid = [t for t in tranches if t["sol"] < esp.sol[1]]
    chaud = [t for t in tranches if t["sol"] > esp.sol[2]]
    froid_au_dessus = min(t["de"] for t in froid) if froid and len(froid) < len(tranches) else None
    chaud_en_dessous = max(t["a"] for t in chaud) if chaud and len(chaud) < len(tranches) else None

    moyens = {k: moy(v) for k, v in facteurs.items()}
    candidats = dict(moyens, saison=saison)
    limitant = min(candidats, key=candidats.get)
    if candidats[limitant] >= 0.7:
        limitant = "aucun"
    elif limitant == "sol":
        trop_froid = moy((tsol < esp.sol[1]).astype(np.float32))
        trop_chaud = moy((tsol > esp.sol[2]).astype(np.float32))
        limitant = "sol_froid" if trop_froid >= trop_chaud else "sol_chaud"

    a, b, c_, d = (M._jour(s, jour.year) for s in esp.saison)
    par_commune = []
    sel = libre & (cases.commune > 0)
    n = np.bincount(cases.commune[sel], minlength=len(noms_communes) + 1)
    s = np.bincount(cases.commune[sel], weights=indice_cases[sel], minlength=len(noms_communes) + 1)
    for i in np.argsort(-np.divide(s, n, out=np.zeros_like(s), where=n >= 100))[:8]:
        if n[i] >= 100 and s[i] > 0:
            v = float(s[i] / n[i])
            par_commune.append({"nom": noms_communes[i - 1], "indice": round(v, 4), "classe": M.classe(v)})

    return {
        "saison": round(saison, 3),
        "debut_saison": jour.toordinal() < (b + c_) / 2,
        "part_bon": round(sum(parts[3:]), 4),
        "part_moyen": round(sum(parts[2:]), 4),
        "classes": [round(p, 4) for p in parts],
        "facteurs": {k: round(v, 3) for k, v in moyens.items()},
        "limitant": limitant,
        "pluie_moy": round(moy(pluie), 1),
        "tranches": tranches,
        "meilleure_tranche": [meilleure["de"], meilleure["a"]] if meilleure and meilleure["indice"] >= 0.1 else None,
        "froid_au_dessus": froid_au_dessus,
        "chaud_en_dessous": chaud_en_dessous,
        "communes": par_commune,
    }


# --- Orchestration ------------------------------------------------------------------

def exporter(meteo: Meteo | None = None) -> dict:
    t0 = time.time()
    grille, h, meta = charger_habitat()
    cases = cases_de_foret(grille, h)
    publie = Agregat(grille, h, cases, 1)
    zones = Agregat(grille, h, cases, FACTEUR_ZONE)
    if meteo is None:
        meteo = previsions(grille, jours_futurs=JOURS_FUTURS)
    print(f"Météo : {len(meteo.lats) * len(meteo.lons)} points, {meteo.dates[0]} → {meteo.dates[-1]} "
          f"({time.time() - t0:.0f} s)")
    k0 = len(meteo.dates) - JOURS_FUTURS
    aujourdhui = meteo.dates[k0]
    calcul = Calcul(meteo, cases)

    attributs, lieux = images_fixes(h)
    ecrire_png(SITE_DATA / "attributs.png", attributs)
    ecrire_png(SITE_DATA / "lieux.png", lieux)
    for k in range(JOURS_FUTURS):
        ecrire_png(SITE_DATA / f"sol_{k}.png", publie.valeurs(calcul.sol(k0 + k), code_sol))
    print(f"  fonds fixes et sol  ({time.time() - t0:.0f} s)")

    regles = E.en_json()
    resumes: dict[str, list] = {}
    for esp in E.ESPECES:
        habitat = M.facteur_habitat(esp, cases.essence, cases.ouverte, cases.roche, cases.altitude, cases.pente)
        resumes[esp.code] = []
        for k in range(JOURS_FUTURS):
            jour = meteo.dates[k0 + k]
            saison = M.facteur_saison(esp, jour)
            pluie, tsol, gel = calcul.entrees(esp, k0 + k)
            facteurs = M.facteurs_meteo(esp, pluie, tsol, gel)
            ind = M.indice(habitat, saison, facteurs)
            image = publie.indice(ind)
            ecrire_png(SITE_DATA / "indice" / f"{esp.code}_{k}.png", image)
            ecrire_png(SITE_DATA / "pluie" / f"{esp.code}_{k}.png", zones.valeurs(pluie))
            faits = faits_du_jour(esp, jour, saison, habitat, ind, facteurs, pluie, tsol, cases,
                                  image.ravel(), meta["communes"])
            texte = redaction.rediger(next(e for e in regles["especes"] if e["code"] == esp.code), faits)
            resumes[esp.code].append({**faits, **texte})
        print(f"  {esp.nom} : {[r['niveau'] for r in resumes[esp.code]]}  ({time.time() - t0:.0f} s)")

    # Validation calculée à la main, rarement (champi.validation) : relue, jamais recalculée ici.
    chemin_validation = DATA / "validation.json"
    validation = (json.loads(chemin_validation.read_text(encoding="utf-8"))
                  if chemin_validation.exists() else None)
    fiabilite = ({code: redaction.fiabilite(r["meteo"]) for code, r in validation["especes"].items()}
                 if validation else {})

    carte = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "departement": DEPARTEMENT, "nom": NOM_DEPARTEMENT,
        "bornes": grille.bornes_lonlat(),
        "grille": grille.en_dict(),
        "grille_zone": zones.publie.en_dict(),
        "echelle": ECHELLE,
        "codes": {"hors_departement": HORS_DEPARTEMENT, "hors_foret": HORS_FORET, "protege": PROTEGE},
        "classes": [{"seuil": s, "nom": n} for s, n in M.CLASSES],
        "jours": [{"date": meteo.dates[k0 + k].isoformat(),
                   "libelle": redaction.libelle_jour(meteo.dates[k0 + k], aujourdhui)}
                  for k in range(JOURS_FUTURS)],
        "especes": [{"code": e.code, "nom": e.nom, "latin": e.latin} for e in E.ESPECES],
        "resumes": resumes,
        "fiabilite": fiabilite,
        "legendes": {k: meta[k] for k in ("essences", "roches", "orientations", "communes", "protections")},
        "sources": meta["sources"],
        "habitat_construit_le": meta["construit_le"],
    }
    ecrire_json(SITE_DATA / "carte.json", carte)
    ecrire_json(SITE_DATA / "especes.json", regles)
    if validation:
        ecrire_json(SITE_DATA / "validation.json", validation)
    print(f"Écrit site/data/ en {time.time() - t0:.0f} s")
    return carte


if __name__ == "__main__":
    exporter()
