"""Blocs de la France : géométrie calée sur la grille de 72 m, noms réversibles."""
from champi.config import PAS_FIN
from champi.france import BLOC, COTE, Bloc, bloc_de
from champi.grille import lonlat_vers_merc


def test_bloc_cale_sur_la_grille_fine():
    g = Bloc(18, 156).grille()
    assert (g.nx, g.ny, g.pas) == (BLOC, BLOC, PAS_FIN)
    assert g.x0 % PAS_FIN == 0 and g.y1 % PAS_FIN == 0
    assert g.x1 == Bloc(19, 156).grille().x0 and g.y0 == Bloc(18, 155).grille().y1


def test_bloc_d_un_point_et_nom():
    x, y = lonlat_vers_merc(6.13, 45.90)   # Annecy
    b = bloc_de(float(x), float(y))
    g = b.grille()
    assert g.x0 <= x < g.x1 and g.y0 <= y < g.y1
    assert Bloc.depuis_nom(b.nom) == b and b.nom == "18_156"
    assert COTE == BLOC * PAS_FIN


def test_construction_incrementale(tmp_path, monkeypatch):
    """Une construction interrompue publie ce qu'elle a fait ; la suivante ne refait que le
    reste, avec la liste de communes publiée (les index des blocs faits y renvoient)."""
    import json

    import numpy as np

    from champi import france as F

    monkeypatch.setattr(F, "SORTIE", tmp_path)
    monkeypatch.setattr(F, "blocs_de_france", lambda: ["1_1", "1_2", "1_3"])
    monkeypatch.setattr(F, "communes_nationales", lambda: [{"insee": "01001", "nom": "A", "dep": "01"}])

    def construit(nom, n):
        (tmp_path / "meta").mkdir(exist_ok=True)
        (tmp_path / "echantillon").mkdir(exist_ok=True)
        (tmp_path / "meta" / f"{nom}.json").write_text(json.dumps({"nom": nom, "n_foret": n, "protections": []}))
        np.savez_compressed(tmp_path / "echantillon" / f"{nom}.npz", lat=np.full(n, 45.0, np.float32))

    assert F.preparer(40) == [0, 1, 2]
    construit("1_1", 3)
    (tmp_path / "vides").mkdir()
    (tmp_path / "vides" / "1_2").write_text("")
    assert F.assembler()
    index = json.loads((tmp_path / "blocs.json").read_text())
    assert index["format"] == F.FORMAT and list(index["blocs"]) == ["1_1"]
    assert index["vides"] == ["1_2"] and index["manquants"] == ["1_3"]

    # Construction suivante : la release publiée est extraite, seuls les blocs à refaire restent.
    for d in ("meta", "echantillon", "vides"):
        for f in (tmp_path / d).iterdir():
            f.unlink()
    monkeypatch.setattr(F, "communes_nationales", lambda: (_ for _ in ()).throw(AssertionError("relue")))
    assert F.preparer(40) == [0]
    assert json.loads((tmp_path / "liste.json").read_text())["a_construire"] == ["1_3"]
    construit("1_3", 2)
    assert F.assembler()
    index = json.loads((tmp_path / "blocs.json").read_text())
    assert list(index["blocs"]) == ["1_1", "1_3"] and index["manquants"] == []
    assert len(np.load(tmp_path / "echantillon.npz")["lat"]) == 5

    # Rien de construit : rien à publier, l'index publié reste tel quel.
    assert F.preparer(40) == [] and not F.assembler()
    assert json.loads((tmp_path / "blocs.json").read_text())["manquants"] == []
