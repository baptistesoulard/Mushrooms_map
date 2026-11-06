"""La carte fine chiffrée (champi/chiffre.py, site/fin.js) : jamais de 50 m en clair en ligne,
et le navigateur déchiffre exactement ce que Python a chiffré."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from champi import chiffre as C

SITE = Path(__file__).resolve().parent.parent / "site"
NODE = shutil.which("node")


def test_aller_retour_et_determinisme():
    cle = C.deriver("une longue phrase de passe", iterations=1000)
    x = C.chiffrer(cle, "18_156_a.png", b"\x89PNG des octets")
    assert x == C.chiffrer(cle, "18_156_a.png", b"\x89PNG des octets"), "même bloc, même fichier chiffré"
    assert C.dechiffrer(cle, "18_156_a.png", x) == b"\x89PNG des octets"
    with pytest.raises(InvalidTag):
        C.dechiffrer(cle, "18_156_b.png", x)          # un fichier ne passe pas pour un autre
    with pytest.raises(InvalidTag):
        C.dechiffrer(C.deriver("autre chose", iterations=1000), "18_156_a.png", x)


@pytest.mark.parametrize("mot", ["phrase de passe", None], ids=["avec", "sans"])
def test_rien_de_fin_en_clair(tmp_path, monkeypatch, mot):
    habitat, data = tmp_path / "habitat", tmp_path / "data"
    (habitat / "blocs").mkdir(parents=True)
    for l in "abcd":
        (habitat / "blocs" / f"1_2_{l}.png").write_bytes(f"couche {l}".encode())
    (habitat / "echantillon.npz").write_bytes(b"x")
    data.mkdir()
    (data / "carte.json").write_text(json.dumps({"blocs": {}}), encoding="utf-8")
    monkeypatch.setattr(C, "HABITAT", habitat)
    monkeypatch.setattr(C, "SITE_DATA", data)
    monkeypatch.setattr(C, "FINE_ITERATIONS", 1000)
    monkeypatch.setattr(C, "deriver", lambda m: C.hashlib.pbkdf2_hmac("sha256", m.encode(), b"sel", 1000, 32))
    fine = C.tout(mot)
    restants = sorted(p.name for p in (habitat / "blocs").iterdir())
    assert restants == ["1_2_c.png"], "seule la couche c (communes, zones protégées) reste en clair"
    assert not (habitat / "echantillon.npz").exists()
    carte = json.loads((data / "carte.json").read_text(encoding="utf-8"))
    assert carte["fine"] == fine
    if mot is None:
        assert fine is None and not (habitat / "fin").exists()
        return
    cle = C.deriver(mot)
    assert fine["id"] == C.identifiant(cle)
    chiffres = sorted(p.name for p in (habitat / "fin" / fine["id"]).iterdir())
    assert chiffres == ["1_2_a.bin", "1_2_b.bin", "1_2_d.bin"]
    assert C.dechiffrer(cle, "1_2_b.png", (habitat / "fin" / fine["id"] / "1_2_b.bin").read_bytes()) == b"couche b"


COUREUR = """
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const [, , module, entree, sortie] = process.argv;
const F = await import(pathToFileURL(module).href);
const f = JSON.parse(readFileSync(entree, "utf8"));
const res = {};
for (const essai of f.essais) {
  const { brut, id } = await F.deriver(essai.mot, f.fine);
  let clair = null;
  if (id === f.fine.id) {
    const cle = await F.importer(brut);
    clair = Buffer.from(await F.dechiffrer(cle, f.nom, Buffer.from(f.chiffre, "base64"))).toString("base64");
  }
  res[essai.mot] = { id, clair };
}
writeFileSync(sortie, JSON.stringify(res));
"""


@pytest.mark.skipif(NODE is None, reason="Node absent")
def test_le_navigateur_dechiffre(tmp_path):
    import base64
    fine = {"sel": "champimeteo/essai", "iterations": 2000}
    cle = C.deriver("Cèpes sous les hêtres, 2026 !", fine["sel"], fine["iterations"])
    fine["id"] = C.identifiant(cle)
    contenu = bytes(range(256)) * 40
    entree = {"fine": fine, "nom": "18_156_a.png",
              "chiffre": base64.b64encode(C.chiffrer(cle, "18_156_a.png", contenu)).decode(),
              "essais": [{"mot": "Cèpes sous les hêtres, 2026 !"}, {"mot": "cèpes"}]}
    (tmp_path / "entree.json").write_text(json.dumps(entree), encoding="utf-8")
    (tmp_path / "coureur.mjs").write_text(COUREUR, encoding="utf-8")
    subprocess.run([NODE, str(tmp_path / "coureur.mjs"), str(SITE / "fin.js"), str(tmp_path / "entree.json"),
                    str(tmp_path / "sortie.json")], check=True)
    res = json.loads((tmp_path / "sortie.json").read_text(encoding="utf-8"))
    bon = res["Cèpes sous les hêtres, 2026 !"]
    assert bon["id"] == fine["id"] and base64.b64decode(bon["clair"]) == contenu
    assert res["cèpes"]["id"] != fine["id"] and res["cèpes"]["clair"] is None
