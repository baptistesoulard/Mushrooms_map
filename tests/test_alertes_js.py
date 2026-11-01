"""Mes alertes (site/alertes.js), sous Node : ce qu'un appareil écrit dans le fichier du groupe."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node absent")

COUREUR = """
import { pathToFileURL } from "node:url";
const [, , module, fonction, entree] = process.argv;
const A = await import(pathToFileURL(module).href);
console.log(JSON.stringify(A[fonction](...JSON.parse(entree))));
"""


def appeler(fonction, args, tmp_path):
    script = tmp_path / "coureur.mjs"
    script.write_text(COUREUR, encoding="utf-8")
    r = subprocess.run([NODE, str(script), str(SITE / "alertes.js"), fonction, json.dumps(args)],
                       capture_output=True, encoding="utf-8", check=True)
    return json.loads(r.stdout)


def abonne(id_, *deps):
    return {"id": id_, "alertes": [{"departement": d, "especes": ["cepe"], "seuil": "bon"} for d in deps]}


def test_un_appareil_ne_touche_que_son_entree(tmp_path):
    doc = {"format": "champi-alertes", "version": 1, "abonnes": [abonne("a", "74"), abonne("b", "85")]}
    apres = appeler("fusionnerAbonne", [doc, "a", abonne("a", "74", "01")], tmp_path)
    assert [x["id"] for x in apres["abonnes"]] == ["b", "a"]
    assert [x["departement"] for x in apres["abonnes"][1]["alertes"]] == ["74", "01"]
    # Sans alerte, l'appareil sort du fichier ; un fichier absent se crée.
    assert [x["id"] for x in appeler("fusionnerAbonne", [doc, "a", abonne("a")], tmp_path)["abonnes"]] == ["b"]
    assert appeler("fusionnerAbonne", [None, "c", abonne("c", "29")], tmp_path)["abonnes"][0]["id"] == "c"


def test_une_alerte_par_departement(tmp_path):
    avant = abonne("a", "85", "74")["alertes"]
    nouvelle = {"departement": "74", "especes": ["girolle"], "seuil": "endroits"}
    apres = appeler("ajouterAlerte", [avant, nouvelle], tmp_path)
    assert [(x["departement"], x["especes"]) for x in apres] == [("74", ["girolle"]), ("85", ["cepe"])]
