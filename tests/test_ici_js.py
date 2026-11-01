"""« Que chercher ici ? » : la grille de 9,2 km publiée par l'export (`export_france.Vue`) et sa
lecture dans le navigateur (`site/ici.js`) rendent le verdict des départements (`redaction.niveau`)."""
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from champi import redaction
from champi.export_france import KM2_PAR, PARTS_PAR, VUE, Vue

SITE = Path(__file__).resolve().parent.parent / "site"
NODE = shutil.which("node")

COUREUR = """
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const [, , module, entree, sortie] = process.argv;
const I = await import(pathToFileURL(module).href);
const f = JSON.parse(readFileSync(entree, "utf8"));
const { surface, parts } = I.partsZone(Uint8Array.from(f.v), f.V, f.zone);
const niveaux = Object.fromEntries(f.V.especes.map((c) => [c, I.niveau(1, parts[c].bon, parts[c].moyen, f.seuils)]));
writeFileSync(sortie, JSON.stringify({ surface, parts, niveaux }));
"""


def _vue(rng, nx=40, ny=24, n=6000, especes=3):
    """Un aperçu fabriqué (grille, pixel de chaque case, cases libres) et des indices par espèce."""
    apercu = SimpleNamespace(grille=SimpleNamespace(nx=nx, ny=ny), pixel=rng.integers(0, nx * ny, n),
                             libre=rng.random(n) > 0.1)
    km2 = rng.uniform(0.02, 0.06, n)
    v = Vue(apercu, km2)
    indices = [rng.random(n) * (1, 0.5, 0.42, 0.3)[e % 4] for e in range(especes)]   # des verdicts variés
    for ind in indices:
        v.ajouter(ind)
    return apercu, km2, v, indices


def test_parts_d_un_pixel_comme_un_departement():
    """Sur un pixel de 9,2 km, les parts sont celles qu'`export_france.faits` calculerait."""
    rng = np.random.default_rng(3)
    apercu, km2, v, indices = _vue(rng)
    image = v.image()
    assert image.shape == (v.ny * (1 + 2 * len(indices)), v.nx)
    lig, col = np.divmod(apercu.pixel, apercu.grille.nx)
    p = (lig // VUE) * v.nx + col // VUE
    sel = (p == 7) & apercu.libre
    assert image.reshape(-1, v.ny * v.nx)[0][7] == round(km2[sel].sum() * KM2_PAR)
    for e, ind in enumerate(indices):
        bon = km2[sel & (ind >= 0.40)].sum() / km2[sel].sum()
        moyen = km2[sel & (ind >= 0.25)].sum() / km2[sel].sum()
        assert image.reshape(-1, v.ny * v.nx)[1 + 2 * e][7] == round(bon * PARTS_PAR)
        assert image.reshape(-1, v.ny * v.nx)[2 + 2 * e][7] == round(moyen * PARTS_PAR)


@pytest.mark.skipif(NODE is None, reason="Node absent")
def test_le_navigateur_rend_le_verdict_des_departements(tmp_path):
    rng = np.random.default_rng(4)
    _, _, v, indices = _vue(rng, especes=4)
    codes = ["cepe", "girolle", "morille", "lactaire"]
    V = {"facteur": VUE, "nx": v.nx, "ny": v.ny, "especes": codes, "km2_par": KM2_PAR, "parts_par": PARTS_PAR}
    zone = {"l0": 0, "l1": 2, "c0": 1, "c1": 3}          # déborde à droite de la grille (5 × 3 pixels)
    image = v.image().astype(float).reshape(-1, v.ny * v.nx)
    pix = [l * v.nx + c for l in range(0, 3) for c in range(1, min(4, v.nx))]
    s = image[0][pix] / KM2_PAR
    attendu = {}
    for e, code in enumerate(codes):
        bon = (s * image[1 + 2 * e][pix]).sum() / PARTS_PAR / s.sum()
        moyen = (s * image[2 + 2 * e][pix]).sum() / PARTS_PAR / s.sum()
        attendu[code] = (bon, moyen, redaction.niveau({"saison": 1, "part_bon": bon, "part_moyen": moyen}))

    entree = {"v": v.image().ravel().tolist(), "V": V, "zone": zone, "seuils": redaction.SEUILS_NIVEAU}
    (tmp_path / "entree.json").write_text(json.dumps(entree), encoding="utf-8")
    (tmp_path / "coureur.mjs").write_text(COUREUR, encoding="utf-8")
    subprocess.run([NODE, str(tmp_path / "coureur.mjs"), str(SITE / "ici.js"), str(tmp_path / "entree.json"),
                    str(tmp_path / "sortie.json")], check=True, encoding="utf-8")
    obtenu = json.loads((tmp_path / "sortie.json").read_text(encoding="utf-8"))
    assert obtenu["surface"] == pytest.approx(s.sum())
    for code, (bon, moyen, n) in attendu.items():
        assert obtenu["parts"][code]["bon"] == pytest.approx(bon)
        assert obtenu["parts"][code]["moyen"] == pytest.approx(moyen)
        assert obtenu["niveaux"][code] == n
    assert len({n for _, _, n in attendu.values()}) > 1, "le cas de test doit donner plusieurs verdicts"
