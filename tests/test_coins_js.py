"""Mes coins (site/coins.js), sous Node : regroupement en coins, fusion de deux appareils."""
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
const C = await import(pathToFileURL(module).href);
console.log(JSON.stringify(C[fonction](...JSON.parse(entree))));
"""


def appeler(fonction, args, tmp_path):
    script = tmp_path / "coureur.mjs"
    script.write_text(COUREUR, encoding="utf-8")
    r = subprocess.run([NODE, str(script), str(SITE / "coins.js"), fonction, json.dumps(args)],
                       capture_output=True, encoding="utf-8", check=True)
    return json.loads(r.stdout)


def regrouper(trouvailles, tmp_path):
    return [[t["id"] for t in g["trouvailles"]] for g in appeler("regrouper", [trouvailles], tmp_path)]


def t(id_, lat, lon, date):
    return {"id": id_, "lat": lat, "lon": lon, "espece": "cepe", "date": date}


def test_trouvailles_voisines_font_un_coin(tmp_path):
    # 0,0005° de latitude ≈ 56 m : même coin ; 0,002° ≈ 220 m : un autre.
    groupes = regrouper([t("a", 45.9, 6.1, "2024-10-01"), t("b", 45.9005, 6.1, "2026-10-03"),
                         t("c", 45.902, 6.1, "2025-09-12")], tmp_path)
    assert groupes == [["b", "a"], ["c"]]   # le plus récent d'abord, il donne la position du coin


def test_coin_suit_la_trouvaille_la_plus_recente(tmp_path):
    # « a » est à 89 m de « b » mais à 167 m de « c » : il rejoint le coin de « b », pas celui de « c ».
    groupes = regrouper([t("c", 45.9015, 6.1, "2023-10-01"), t("b", 45.9, 6.1, "2026-10-01"),
                         t("a", 45.9008, 6.1, "2025-10-01")], tmp_path)
    assert groupes == [["b", "a"], ["c"]]


def coin(id_, maj=None):
    c = t(id_, 45.9, 6.1, "2026-10-01")
    if maj:
        c["maj"] = maj
    return c


def fusionner(a, b, tmp_path):
    f = appeler("fusionner", [a, b], tmp_path)
    return sorted(c["id"] for c in f["coins"]), f["effaces"]


def test_fusion_reunit_deux_appareils(tmp_path):
    tel = {"coins": [coin("a", "2026-10-01T10:00Z"), coin("b", "2026-10-02T10:00Z")], "effaces": {}}
    pc = {"coins": [coin("a", "2026-10-01T10:00Z"), coin("c", "2026-10-03T10:00Z")], "effaces": {}}
    assert fusionner(tel, pc, tmp_path) == (["a", "b", "c"], {})


def test_un_coin_efface_ne_revient_pas_d_un_autre_appareil(tmp_path):
    tel = {"coins": [coin("b", "2026-10-02T10:00Z")], "effaces": {"a": "2026-10-05T10:00Z"}}
    pc = {"coins": [coin("a", "2026-10-01T10:00Z"), coin("b", "2026-10-02T10:00Z")], "effaces": {}}
    ids, effaces = fusionner(pc, tel, tmp_path)
    assert ids == ["b"] and effaces == {"a": "2026-10-05T10:00Z"}
    # Un coin d'avant la synchronisation (sans date de mise à jour) s'efface aussi.
    assert fusionner({"coins": [coin("a")], "effaces": {}}, tel, tmp_path)[0] == ["b"]


def test_un_import_posterieur_fait_revenir_un_coin_efface(tmp_path):
    tel = {"coins": [], "effaces": {"a": "2026-10-05T10:00Z"}}
    pc = {"coins": [coin("a", "2026-10-06T08:00Z")], "effaces": {}}
    assert fusionner(tel, pc, tmp_path) == (["a"], {})


def test_base64_garde_les_accents(tmp_path):
    texte = "Sous les châtaigniers, près de l'étang — 3 cèpes"
    b64 = appeler("versBase64", [texte], tmp_path)
    # GitHub coupe le base64 en lignes : les retours à la ligne sont ignorés.
    assert appeler("depuisBase64", [b64[:10] + "\n" + b64[10:]], tmp_path) == texte


def test_seuls_ses_coins_partent_au_depot(tmp_path):
    coins = [coin("a"), {**coin("b"), "de": "Paul"}, {**coin("c"), "prive": True}, {**coin("d"), "auteur": "Léa"}]
    envoyes = [c["id"] for c in coins if appeler("aEnvoyer", [c], tmp_path)]
    assert envoyes == ["a", "d"]   # ni le coin confié par fichier, ni celui gardé pour soi


def test_signer_ne_touche_ni_aux_coins_confies_ni_aux_coins_signes(tmp_path):
    coins = [coin("a", "2026-10-01T10:00Z"), {**coin("b"), "de": "Paul"}, {**coin("c"), "auteur": "Léa"}]
    signes = {c["id"]: c for c in appeler("signer", [coins, "Baptiste", "2026-10-31T21:00Z"], tmp_path)}
    assert signes["a"]["auteur"] == "Baptiste" and signes["a"]["maj"] == "2026-10-31T21:00Z"
    assert "auteur" not in signes["b"] and signes["c"]["auteur"] == "Léa"
