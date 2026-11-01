from datetime import date

import numpy as np
import pytest

from champi import especes as E
from champi import modele as M
from champi.grille import Grille, grille_englobante, lonlat_vers_merc, merc_vers_lonlat

CEPE = E.PAR_CODE["cepe"]


def test_trapeze():
    v = M.trapeze([0, 5, 10, 15, 20, 25, 30], 5, 10, 20, 30)
    assert v.tolist() == pytest.approx([0, 0, 1, 1, 1, 0.5, 0])


def test_saison_nulle_hors_saison_pleine_au_coeur():
    assert M.facteur_saison(CEPE, date(2026, 2, 1), 46.0) == 0
    assert M.facteur_saison(CEPE, date(2026, 9, 15), 46.0) == 1
    assert 0 < M.facteur_saison(CEPE, date(2026, 6, 20), 46.0) < 1


def test_loi_de_hopkins_sur_la_saison():
    """Vers le sud, la morille sort plus tôt et le cèpe finit plus tard ; 4 jours par degré."""
    morille = E.PAR_CODE["morille"]
    assert M.facteur_saison(morille, date(2026, 3, 10), 43.0) > M.facteur_saison(morille, date(2026, 3, 10), 46.0)
    assert M.facteur_saison(CEPE, date(2026, 11, 25), 43.0) > M.facteur_saison(CEPE, date(2026, 11, 25), 49.0)
    nord = M.dates_saison(CEPE, 2026, 47.0)
    ref = M.dates_saison(CEPE, 2026, 46.0)
    assert nord[0] - ref[0] == pytest.approx(E.HOPKINS_JOURS)      # juin : plus tard au nord
    assert nord[1] == ref[1]                                       # juillet : immobile
    assert nord[3] - ref[3] == pytest.approx(-E.HOPKINS_JOURS)     # novembre : plus tôt au nord


def test_saison_qui_deborde_sur_janvier():
    """Le pied-de-mouton, au sud, court jusqu'en janvier : l'année précédente compte."""
    pdm = E.PAR_CODE["pied_de_mouton"]
    assert M.facteur_saison(pdm, date(2027, 1, 2), 42.0) > 0
    assert M.facteur_saison(pdm, date(2027, 1, 2), 46.0) == 0


def test_saison_par_case():
    lats = np.array([43.0, 46.0, 50.0])
    f = M.facteur_saison(CEPE, date(2026, 11, 25), lats)
    assert f.shape == (3,) and f[0] > f[1] > f[2]


def test_un_facteur_nul_ferme_la_porte():
    f = {"pluie": np.array([1.0]), "sol": np.array([1.0]), "gel": np.array([0.0])}
    assert M.indice(np.array([1.0]), 1.0, f)[0] == 0


def test_versant_sud_plus_sec_et_plus_chaud():
    assert M.pluie_efficace(40, 0.5) < 40 < M.pluie_efficace(40, -0.5)
    sud = M.temperature_locale(15, 1000, E.GRADIENT_SOL, 0.5, E.SOLEIL_SOL)
    nord = M.temperature_locale(15, 1000, E.GRADIENT_SOL, -0.5, E.SOLEIL_SOL)
    assert sud > nord


def test_temperature_baisse_avec_l_altitude():
    assert M.temperature_locale(15, 2000, E.GRADIENT_AIR) == pytest.approx(15 - 13)


def test_fenetre_de_pluie():
    """Pour le cèpe, la pluie compte de 20 à 6 jours avant, pas la veille."""
    n = 40
    k = 30
    pluie = np.zeros(n)
    pluie[k - 10] = 50       # dans la fenêtre
    pluie[k - 2] = 100       # trop récent : la pousse n'a pas encore suivi
    t = np.full(n, 15.0)
    p, t_sol, gel = M.entrees_meteo(CEPE, k, pluie, t, t, 0.0)
    assert p == pytest.approx(50)
    assert t_sol == pytest.approx(15)
    assert gel == 0


def test_gel_compte_les_sept_derniers_jours():
    n, k = 40, 30
    tmin = np.full(n, 5.0)
    tmin[[k, k - 3, k - 6, k - 7]] = -3   # k-7 sort de la fenêtre
    _, _, gel = M.entrees_meteo(CEPE, k, np.zeros(n), tmin, np.full(n, 10.0), 0.0)
    assert gel == 3


def test_historique_insuffisant_refuse():
    with pytest.raises(ValueError):
        M.entrees_meteo(CEPE, 5, np.zeros(10), np.zeros(10), np.zeros(10), 0.0)


def test_habitat_hors_foret_nul_et_pente_penalisee():
    h = M.facteur_habitat(CEPE, np.array([0, 8, 8]), np.array([False] * 3), np.array([2, 2, 2]),
                          np.array([1000, 1000, 1000]), np.array([10, 10, 50]), 46.0)
    assert h[0] == 0 and h[1] == pytest.approx(1.0) and h[2] == pytest.approx(E.PENTE_PLANCHER)


def test_pas_de_plancher_et_plafond_plus_haut_au_sud():
    """Une chênaie des Landes à 30 m n'est pas exclue ; à 2 000 m, Corse oui, Vosges non."""
    un = np.ones(1)
    plaine = M.facteur_habitat(CEPE, np.array([3]), np.array([False]), np.array([2]), np.array([30]), un * 10, 44.0)
    assert plaine[0] == pytest.approx(CEPE.essences[3])
    haut = [float(M.facteur_habitat(CEPE, np.array([8]), np.array([False]), np.array([2]), np.array([1900]),
                                    un * 10, lat)[0]) for lat in (42.0, 46.0, 48.0)]
    assert haut[0] == pytest.approx(1.0) and 0 < haut[1] < 1 and haut[2] == 0


def test_ph_remplace_la_roche_la_ou_il_est_connu():
    """Bolet bai : plein en sol acide, à son plancher en sol calcaire ; pH inconnu → la roche."""
    bai = E.PAR_CODE["bolet_bai"]
    ph = np.array([45, 80, 0])                                  # pH × 10 ; 0 = inconnu
    assert M.facteur_ph(bai, ph[:2]).tolist() == pytest.approx([1.0, bai.ph_plancher])
    un = np.ones(3)
    h = M.facteur_habitat(bai, np.array([8, 8, 8]), np.zeros(3, bool), np.array([1, 1, 1]), un * 500, un * 10, 46.0, ph=ph)
    assert h.tolist() == pytest.approx([1.0, bai.ph_plancher, bai.roches[1]])
    sans = M.facteur_habitat(bai, np.array([8]), np.zeros(1, bool), np.array([1]), un[:1] * 500, un[:1] * 10, 46.0)
    assert sans[0] == pytest.approx(bai.roches[1])              # sans pH : la roche, comme avant
    trompette = E.PAR_CODE["trompette"]                         # pas `sol_ph` : le pH est ignoré
    assert not trompette.sol_ph
    t = M.facteur_habitat(trompette, np.array([2]), np.zeros(1, bool), np.array([2]), un[:1] * 500, un[:1] * 10,
                          46.0, ph=np.array([80]))
    assert t[0] == pytest.approx(trompette.roches[2])


@pytest.mark.parametrize("esp", E.ESPECES, ids=lambda e: e.code)
def test_regle_du_ph(esp):
    """Le pH remplace la roche pour les espèces des sols acides, et elles seules (especes.PH_ACIDE_MAX)."""
    assert esp.sol_ph == (esp.ph[2] <= E.PH_ACIDE_MAX), \
        f"{esp.nom} : optimum de pH jusqu'à {esp.ph[2]}, donc sol_ph={esp.ph[2] <= E.PH_ACIDE_MAX}"


def test_classes_croissantes():
    seuils = [s for s, _ in M.CLASSES]
    assert seuils == sorted(seuils)
    assert M.classe(0.0) == 0 and M.classe(1.0) == len(M.CLASSES) - 1


def test_plancher_d_une_espece_de_montagne():
    """L'hygrophore de mars : rien sous son plancher, plein au-dessus ; il monte vers le sud."""
    h = E.PAR_CODE["hygrophore_mars"]
    f = M.facteur_altitude(h, np.array([100.0, 450.0, 800.0]), 46.0)
    assert f.tolist() == pytest.approx([0.0, 0.5, 1.0])
    assert float(M.facteur_altitude(h, 800.0, 43.0)) < 1.0          # 3° plus au sud : plancher plus haut
    assert float(M.facteur_altitude(E.PAR_CODE["cepe"], 0.0, 46.0)) == 1.0      # pas de plancher


def test_habitat_des_pres():
    """Une espèce des champs : l'affinité de son milieu sous le plafond, rien hors des prés."""
    rose = E.PAR_CODE["rose_pres"]
    h = M.facteur_habitat_pre(rose, np.array([0, 1, 2, 5, 1]), np.array([100.0, 100.0, 100.0, 100.0, 1900.0]), 46.0)
    assert h.tolist() == pytest.approx([0.0, 1.0, 0.5, 0.0, 0.0])


# --- Règles des espèces ---------------------------------------------------------------

@pytest.mark.parametrize("esp", E.ESPECES, ids=lambda e: e.code)
def test_regles_coherentes(esp):
    from champi.habitat import ESSENCES, ROCHES
    from champi.prairies import NOMS_MILIEUX
    assert esp.milieu in ("foret", "pre")
    if esp.milieu == "foret":
        assert set(esp.essences) == set(ESSENCES), "une affinité par essence, ni plus ni moins"
        assert set(esp.roches) == set(ROCHES)
        assert all(0 <= v <= 1 for v in [*esp.essences.values(), *esp.roches.values()])
        assert esp.essences[0] == 0, "hors forêt : pas d'indice"
        assert not esp.prairies
    else:   # une espèce des champs : les milieux des prés, ni essence ni roche
        assert set(esp.prairies) == set(NOMS_MILIEUX), "une affinité par milieu, ni plus ni moins"
        assert all(0 <= v <= 1 for v in esp.prairies.values())
        assert not esp.essences and not esp.roches and not esp.sol_ph
        assert esp.avertissement, "un pré a un propriétaire : la fiche le dit"
    assert list(esp.altitude) == sorted(esp.altitude)
    assert list(esp.plancher) == sorted(esp.plancher) and esp.plancher[1] < esp.altitude[0]
    assert list(esp.sol) == sorted(esp.sol)
    assert esp.pluie_mm[0] < esp.pluie_mm[1]
    assert 0 <= esp.pluie_jours[0] < esp.pluie_jours[1] <= 29, "le job ne garde que 30 jours passés"
    jours = [date(2026, *map(int, s.split("-"))) for s in esp.saison]
    assert jours == sorted(jours)
    assert 0 < esp.gel <= 1
    assert len(esp.description) > 120, "la fiche du panneau a besoin d'un portrait"
    assert esp.confusions, "chaque fiche dit avec quoi on peut confondre l'espèce"


# --- Grille ---------------------------------------------------------------------------

def test_mercator_aller_retour():
    x, y = lonlat_vers_merc(6.5, 46.0)
    lon, lat = merc_vers_lonlat(x, y)
    assert (float(lon), float(lat)) == pytest.approx((6.5, 46.0))


def test_grille_calee_et_grossie():
    g = grille_englobante(5.8, 45.68, 7.05, 46.41, 72.0, 360.0, 1500.0)
    assert g.x0 % 360 == 0 and g.y1 % 360 == 0
    assert g.nx % 5 == 0 and g.ny % 5 == 0
    p = g.grossir(5)
    assert (p.x1, p.y0) == (g.x1, g.y0)
    b = g.bornes_lonlat()
    assert b["ouest"] < 5.8 and b["est"] > 7.05 and b["sud"] < 45.68 and b["nord"] > 46.41


def test_pas_au_sol_vers_50_m():
    g = Grille(*lonlat_vers_merc(6.0, 46.0), 72.0, 10, 10)
    assert g.pas_au_sol().mean() == pytest.approx(50, abs=1)
