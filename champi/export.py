"""Job quotidien : météo du jour → indice par espèce, d'aujourd'hui à J+7 → `site/data/`.

    python -m champi.export

Écrit, pour la carte :
- `indice/<espèce>_<k>.png` (k = 0 à 7) : R = indice × 200 (ou un code), G = pluie de la
  fenêtre (mm), B = température du sol ((°C + 10) × 5), sur la grille publiée de 250 m ;
- `attributs.png`, `lieux.png` : ce qui ne change pas (altitude, forêt, roche, commune) ;
- `carte.json` : jours, légendes, et pour chaque espèce et chaque jour les faits et les
  phrases du panneau ; `especes.json` : les règles, pour la page Méthode.
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
from .config import DATA, DEPARTEMENT, FACTEUR_PUBLIE, NOM_DEPARTEMENT, SITE_DATA
from .grille import Grille
from .meteo import Interpolateur, Meteo, previsions
from .sources import ecrire_json

JOURS_FUTURS = 8
TRANCHE_M = 200
ECHELLE = 200                        # indice publié = round(indice × 200)
HORS_DEPARTEMENT, HORS_FORET, PROTEGE = 255, 251, 252
COUVERTURE_PLEINE = 0.3              # une zone à 30 % boisée ou plus garde tout son indice
MIN_CASES_FORET = 4                  # sur 25 : en dessous, la zone est « hors forêt »


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
    bloc: np.ndarray            # index de la zone publiée (250 m) qui contient la case


def charger_habitat() -> tuple[Grille, dict, dict]:
    h = dict(np.load(DATA / f"habitat_{DEPARTEMENT}.npz"))
    meta = json.loads((DATA / f"habitat_{DEPARTEMENT}.json").read_text(encoding="utf-8"))
    return Grille.depuis_dict(meta["grille"]), h, meta


def cases_de_foret(grille: Grille, h: dict) -> Cases:
    lig, col = np.nonzero((h["commune"] > 0) & (h["essence"] > 0))
    publie = grille.grossir(FACTEUR_PUBLIE)
    return Cases(
        lignes=lig, colonnes=col,
        lat=grille.latitudes()[lig], lon=grille.longitudes()[col],
        altitude=h["altitude"][lig, col].astype(np.float32),
        ensoleillement=h["ensoleillement"][lig, col].astype(np.float32) / 100,
        pente=h["pente"][lig, col], essence=h["essence"][lig, col], ouverte=h["ouverte"][lig, col],
        roche=h["roche"][lig, col], protege=h["protege"][lig, col], commune=h["commune"][lig, col],
        bloc=(lig // FACTEUR_PUBLIE) * publie.nx + col // FACTEUR_PUBLIE,
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

    def _gele(self, d: int) -> np.ndarray:
        if d not in self._gel:
            tmin = M.temperature_locale(self.interp(self.meteo.tmin_mer[d]), self.cases.altitude, E.GRADIENT_AIR)
            self._gel[d] = tmin < E.GEL_SEUIL
        return self._gel[d]

    def entrees(self, esp: E.Espece, k: int):
        """Mêmes sorties que `modele.entrees_meteo`, calculées par la voie rapide."""
        c, m = self.cases, self.meteo
        j_min, j_max = esp.pluie_jours
        pluie = self.interp(m.pluie[k - j_max:k - j_min + 1].sum(axis=0))
        t_sol = M.temperature_locale(self.interp(m.tsol_mer[k - 7:k].mean(axis=0)), c.altitude,
                                     E.GRADIENT_SOL, c.ensoleillement, E.SOLEIL_SOL)
        gel = np.zeros(len(c.lat), dtype=np.int8)
        for d in range(k - 6, k + 1):
            gel += self._gele(d)
        return M.pluie_efficace(pluie, c.ensoleillement), t_sol, gel


# --- Agrégation vers la grille publiée ---------------------------------------------

class Agregat:
    def __init__(self, grille: Grille, h: dict, cases: Cases):
        f = FACTEUR_PUBLIE
        self.publie = grille.grossir(f)
        nb = self.publie.nx * self.publie.ny
        self.nb, self.cases = nb, cases
        dans = h["commune"] > 0
        self.n_dept = dans.reshape(self.publie.ny, f, self.publie.nx, f).sum(axis=(1, 3)).ravel()
        self.n_foret = np.bincount(cases.bloc, minlength=nb)
        libre = cases.protege == 0
        self.libre = libre
        self.n_libre = np.bincount(cases.bloc[libre], minlength=nb)
        self.couverture = np.minimum(1.0, self.n_foret / (f * f) / COUVERTURE_PLEINE)
        code = np.zeros(nb, dtype=np.uint8)
        code[self.n_foret < MIN_CASES_FORET] = HORS_FORET
        code[(self.n_foret >= MIN_CASES_FORET) & (2 * (self.n_foret - self.n_libre) >= self.n_foret)] = PROTEGE
        code[self.n_dept < (f * f) / 2] = HORS_DEPARTEMENT
        self.code_fixe = code

    def _moyenne(self, valeurs, masque=None) -> np.ndarray:
        b = self.cases.bloc if masque is None else self.cases.bloc[masque]
        v = valeurs if masque is None else valeurs[masque]
        n = np.bincount(b, minlength=self.nb)
        s = np.bincount(b, weights=v, minlength=self.nb)
        return np.divide(s, n, out=np.zeros(self.nb), where=n > 0)

    def indice(self, indice_cases) -> np.ndarray:
        """Indice publié par zone : moyenne des cases libres, réduite si la zone est peu boisée."""
        moy = self._moyenne(indice_cases, self.libre) * self.couverture
        code = np.clip(np.round(moy * ECHELLE), 0, ECHELLE).astype(np.uint8)
        return np.where(self.code_fixe > 0, self.code_fixe, code)

    def image_jour(self, indice_cases, pluie_cases, tsol_cases) -> np.ndarray:
        r = self.indice(indice_cases)
        g = np.clip(np.round(self._moyenne(pluie_cases)), 0, 255).astype(np.uint8)
        b = np.clip(np.round((self._moyenne(tsol_cases) + 10) * 5), 0, 255).astype(np.uint8)
        return np.dstack([v.reshape(self.publie.ny, self.publie.nx) for v in (r, g, b)])

    def images_fixes(self, grille: Grille, h: dict) -> tuple[np.ndarray, np.ndarray]:
        """attributs : R altitude/20, G essence | publique<<4 | ouverte<<5, B roche | orientation<<2.
        lieux : R, G commune (16 bits), B zone protégée."""
        f, p, c = FACTEUR_PUBLIE, self.publie, self.cases
        forme = (p.ny, f, p.nx, f)
        dans = (h["commune"] > 0)
        alt = np.where(dans, h["altitude"], 0).reshape(forme).sum(axis=(1, 3)).ravel()
        alt = np.divide(alt, self.n_dept, out=np.zeros(self.nb), where=self.n_dept > 0)

        def dominante(valeurs, classes):
            n = np.bincount(c.bloc * classes + valeurs.astype(np.int64), minlength=self.nb * classes)
            return n.reshape(self.nb, classes).argmax(axis=1)

        essence = np.where(self.n_foret > 0, dominante(c.essence, 16), 0)
        publique = self._moyenne(h["public"][c.lignes, c.colonnes].astype(float)) >= 0.5
        ouverte = self._moyenne(c.ouverte.astype(float)) >= 0.5
        orientation = np.where(self.n_foret > 0, dominante(h["orientation"][c.lignes, c.colonnes], 9), 0)
        centre = (slice(f // 2, None, f), slice(f // 2, None, f))
        roche = h["roche"][centre].ravel()
        commune = h["commune"][centre].ravel().astype(np.int64)
        protege = h["protege"].reshape(forme).max(axis=(1, 3)).ravel()

        attributs = np.dstack([
            np.clip(np.round(alt / 20), 0, 255).astype(np.uint8),
            (essence | (publique.astype(int) << 4) | (ouverte.astype(int) << 5)).astype(np.uint8),
            (roche | (orientation << 2)).astype(np.uint8),
        ]).reshape(p.ny, p.nx, 3)
        lieux = np.dstack([(commune & 255).astype(np.uint8), (commune >> 8).astype(np.uint8),
                           protege.astype(np.uint8)]).reshape(p.ny, p.nx, 3)
        return attributs, lieux


def ecrire_png(chemin, rgb: np.ndarray) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, "RGB").save(chemin, optimize=True)


# --- Faits du jour ------------------------------------------------------------------

def faits_du_jour(esp: E.Espece, jour: date, saison: float, habitat, indice_cases, facteurs,
                  pluie, tsol, cases: Cases, codes_publies: np.ndarray, noms_communes: list[str]) -> dict:
    libre = cases.protege == 0
    poids = habitat[libre]
    total = float(poids.sum()) or 1.0

    def moy(v):
        return float((v[libre] * poids).sum() / total)

    # Classes, sur les zones publiées boisées : ce que le lecteur voit sur la carte.
    visibles = codes_publies[codes_publies <= ECHELLE] / ECHELLE
    parts = [0.0] * len(M.CLASSES)
    for v in visibles:
        parts[M.classe(v)] += 1
    parts = [p / max(len(visibles), 1) for p in parts]

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
    agregat = Agregat(grille, h, cases)
    if meteo is None:
        meteo = previsions(grille, jours_futurs=JOURS_FUTURS)
    print(f"Météo : {len(meteo.lats) * len(meteo.lons)} points, {meteo.dates[0]} → {meteo.dates[-1]} "
          f"({time.time() - t0:.0f} s)")
    k0 = len(meteo.dates) - JOURS_FUTURS
    aujourdhui = meteo.dates[k0]
    calcul = Calcul(meteo, cases)

    attributs, lieux = agregat.images_fixes(grille, h)
    ecrire_png(SITE_DATA / "attributs.png", attributs)
    ecrire_png(SITE_DATA / "lieux.png", lieux)

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
            image = agregat.image_jour(ind, pluie, tsol)
            ecrire_png(SITE_DATA / "indice" / f"{esp.code}_{k}.png", image)
            faits = faits_du_jour(esp, jour, saison, habitat, ind, facteurs, pluie, tsol, cases,
                                  image[..., 0].ravel(), meta["communes"])
            texte = redaction.rediger(next(e for e in regles["especes"] if e["code"] == esp.code), faits)
            resumes[esp.code].append({**faits, **texte})
        print(f"  {esp.nom} : {[r['niveau'] for r in resumes[esp.code]]}  ({time.time() - t0:.0f} s)")

    # Validation calculée à la main, rarement (champi.validation) : relue, jamais recalculée ici.
    chemin_validation = DATA / "validation.json"
    validation = (json.loads(chemin_validation.read_text(encoding="utf-8"))
                  if chemin_validation.exists() else None)
    fiabilite = ({code: redaction.fiabilite(r["meteo"]) for code, r in validation["especes"].items()}
                 if validation else {})

    publie = agregat.publie
    carte = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "departement": DEPARTEMENT, "nom": NOM_DEPARTEMENT,
        "bornes": publie.bornes_lonlat(), "taille": [publie.nx, publie.ny],
        "grille": publie.en_dict(),
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
