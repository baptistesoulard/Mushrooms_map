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
