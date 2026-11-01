"""Le navigateur calcule l'indice (site/modele.js) : il doit trouver exactement ce que trouve
l'export (champi.export_france.CalculChamps + champi.modele), case par case."""
import json
import shutil
import subprocess
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from champi import especes as E
from champi import modele as M
from champi.export import JOURS_FUTURS
from champi.export_france import PREMIER_GEL, CalculChamps, fenetres_de_pluie

SITE = Path(__file__).resolve().parent.parent / "site"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node absent")

COUREUR = """
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const [, , modele, entree, sortie] = process.argv;
const M = await import(pathToFileURL(modele).href);
const f = JSON.parse(readFileSync(entree, "utf8"));
const champs = Object.fromEntries(Object.entries(f.champs).map(([n, v]) => [n, Float32Array.from(v, (x) => x / 10)]));
const meteo = { lats: f.lats, lons: f.lons, champ: (n) => champs[n] };
const res = {}, bloc = {};
let ecartParts = 0;      // le produit des facteurs de la fenêtre d'une case = l'habitat calculé
const colonnes = Object.fromEntries(Object.keys(f.cases[0]).map((k) => [k, f.cases.map((c) => c[k])]));
const prep = M.preparer(colonnes, meteo);
for (const esp of f.regles.especes) {
  res[esp.code] = f.jours.map((j) => f.cases.map((c) => {
    const r = M.evaluer(esp, c, meteo, j, f.regles.communs);
    const p = r.parts;
    ecartParts = Math.max(ecartParts, Math.abs(p.essence * p.sol * p.altitude * p.pente * p.ouverte - r.habitat));
    return r.indice;
  }));
  bloc[esp.code] = f.jours.map((j) => Array.from(M.indices(esp, prep, meteo, j, f.regles.communs)));
}
writeFileSync(sortie, JSON.stringify({ res, bloc, ecartParts }));
"""


def _fixture(rng, debut: date, lat0: float):
    lats = np.round(lat0 + np.arange(12) * 0.025, 4)
    lons = np.round(5.0 + np.arange(15) * 0.025, 4)
    champs = {}
    for jmin, jmax in fenetres_de_pluie():
        for k in range(JOURS_FUTURS):
            champs[f"pluie_{jmin}_{jmax}_{k}"] = rng.integers(0, 900, (12, 15))
    for k in range(JOURS_FUTURS):
        champs[f"tsol_{k}"] = rng.integers(20, 260, (12, 15))
    for d in range(PREMIER_GEL, JOURS_FUTURS):
        champs[f"tmin_{d}"] = rng.integers(-60, 160, (12, 15))
    champs = {n: v.astype(np.int16) for n, v in champs.items()}
    n = 300
    cases = {
        "lat": rng.uniform(lats[0], lats[-1], n), "lon": rng.uniform(lons[0], lons[-1], n),
        "altitude": rng.integers(0, 2600, n).astype(np.float32),
        "ensoleillement": (rng.integers(-100, 101, n) / 100).astype(np.float32),
        "pente": rng.integers(0, 60, n).astype(np.uint8), "essence": rng.integers(0, 15, n).astype(np.uint8),
        "ouverte": rng.random(n) < 0.2, "roche": rng.integers(0, 4, n).astype(np.uint8),
        # pH × 10 du sol, 0 (inconnu) une fois sur cinq : la roche reprend alors la main.
        "ph": np.where(rng.random(n) < 0.2, 0, rng.integers(35, 85, n)).astype(np.uint8),
    }
    jours = [debut + timedelta(days=k) for k in range(JOURS_FUTURS)]
    return lats, lons, champs, cases, jours


@pytest.mark.parametrize("sol_ph", [False, True], ids=["roche", "ph"])
@pytest.mark.parametrize("debut, lat0", [(date(2026, 10, 25), 44.0), (date(2026, 3, 28), 46.0),
                                         (date(2026, 12, 30), 41.6)],
                         ids=["automne", "printemps", "nouvel-an-en-corse"])
def test_navigateur_egal_export(tmp_path, debut, lat0, sol_ph):
    """Le dernier cas passe le 1er janvier : la saison du pied-de-mouton déborde en Corse."""
    rng = np.random.default_rng(debut.toordinal())
    lats, lons, champs, c, jours = _fixture(rng, debut, lat0)
    calcul = CalculChamps(champs, lats, lons, c["lat"], c["lon"], c["altitude"], c["ensoleillement"])
    # Toutes les espèces avec ou sans le pH du sol, quel que soit leur réglage publié.
    especes = [replace(e, sol_ph=sol_ph) for e in E.ESPECES]
    attendu = {}
    for esp in especes:
        hab = M.facteur_habitat(esp, c["essence"], c["ouverte"], c["roche"], c["altitude"], c["pente"], c["lat"],
                                ph=c["ph"])
        attendu[esp.code] = []
        for k, jour in enumerate(jours):
            pluie, tsol, gel = calcul.entrees(esp, k)
            ind = M.indice(hab, M.facteur_saison(esp, jour, c["lat"]), M.facteurs_meteo(esp, pluie, tsol, gel))
            attendu[esp.code].append(ind)

    regles = E.en_json()
    for e in regles["especes"]:
        e["sol_ph"] = sol_ph
    entree = {
        "regles": regles, "lats": lats.tolist(), "lons": lons.tolist(),
        "champs": {n: v.ravel().tolist() for n, v in champs.items()},
        "jours": [{"annee": j.year, "num": (j - date(1970, 1, 1)).days, "k": k} for k, j in enumerate(jours)],
        "cases": [{k: (bool(v[i]) if v.dtype == bool else float(v[i])) for k, v in c.items()} for i in range(len(c["lat"]))],
    }
    (tmp_path / "entree.json").write_text(json.dumps(entree), encoding="utf-8")
    (tmp_path / "coureur.mjs").write_text(COUREUR, encoding="utf-8")
    subprocess.run([NODE, str(tmp_path / "coureur.mjs"), str(SITE / "modele.js"), str(tmp_path / "entree.json"),
                    str(tmp_path / "sortie.json")], check=True, encoding="utf-8")
    obtenu = json.loads((tmp_path / "sortie.json").read_text(encoding="utf-8"))
    n_positifs = 0
    for code, jours_esp in attendu.items():
        for k, ind in enumerate(jours_esp):
            np.testing.assert_allclose(obtenu["res"][code][k], ind, atol=2e-4, err_msg=f"{code}, jour {k}")
            np.testing.assert_allclose(obtenu["bloc"][code][k], ind, atol=2e-4, err_msg=f"{code}, jour {k} (bloc)")
            n_positifs += int((ind > 0.01).sum())
    assert n_positifs > 10, "le cas de test doit contenir des indices non nuls"
    assert obtenu["ecartParts"] < 1e-12, "les facteurs de la fenêtre d'une case ne refont plus l'habitat"
