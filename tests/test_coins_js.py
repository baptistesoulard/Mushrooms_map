"""Mes coins (site/coins.js) : regroupement des trouvailles en coins, sous Node."""
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
const [, , module, entree] = process.argv;
const C = await import(pathToFileURL(module).href);
const groupes = C.regrouper(JSON.parse(entree));
console.log(JSON.stringify(groupes.map((g) => g.trouvailles.map((t) => t.id))));
"""


def regrouper(trouvailles, tmp_path):
    script = tmp_path / "coureur.mjs"
    script.write_text(COUREUR, encoding="utf-8")
    r = subprocess.run([NODE, str(script), str(SITE / "coins.js"), json.dumps(trouvailles)],
                       capture_output=True, encoding="utf-8", check=True)
    return json.loads(r.stdout)


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
