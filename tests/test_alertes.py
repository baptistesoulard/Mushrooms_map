"""Alertes personnalisées : ce qui sonne, ce qui ne re-sonne pas, et ce que dit le message."""
from datetime import date, timedelta

from champi import alertes as A

J = [date(2026, 11, 2) + timedelta(days=k) for k in range(8)]          # lundi 2 novembre → lundi 9
ESPECES = [{"code": "cepe", "nom": "Cèpe", "de": "du cèpe"}, {"code": "girolle", "nom": "Girolle", "de": "de la girolle"},
           {"code": "bolet_bai", "nom": "Bolet bai", "de": "du bolet bai"}]


def jours(*niveaux, tranche=(200, 400), communes=("Pouzauges", "Mauléon", "Cerizay")):
    return [{"niveau": n, "meilleure_tranche": list(tranche), "communes": [{"nom": c} for c in communes]} for n in niveaux]


def test_premier_jour_favorable_dans_les_7_jours():
    r = {"cepe": jours(2, 3, 4, 4, 4, 4, 4, 4), "girolle": jours(1, 1, 1, 1, 1, 1, 1, 4),
         "bolet_bai": jours(3, 3, 3, 3, 3, 3, 3, 3)}
    assert A.premiers(r, J, 4) == {"cepe": J[2]}                          # la girolle n'est bonne qu'au 8e jour
    assert A.premiers(r, J, 3) == {"cepe": J[1], "bolet_bai": J[0]}       # seuil « par endroits »


def test_nouveau_et_rappel_la_veille():
    avant = {"cepe": J[1], "girolle": J[4]}
    maintenant = {"cepe": J[1], "girolle": J[4], "bolet_bai": J[5]}
    # Le cèpe, déjà annoncé, est bon demain : rappel. Le bolet bai devient favorable : nouveau.
    # La girolle, déjà annoncée et pas encore demain : rien.
    assert A.evenements(maintenant, avant, demain=J[1]) == [("cepe", J[1], "rappel"), ("bolet_bai", J[5], "nouveau")]


def test_message_d_une_espece_nouvelle():
    r = {"cepe": jours(1, 1, 4, 4, 4, 4, 4, 4)}
    titre, texte = A.message("Vendée", [("cepe", J[2], "nouveau")], ESPECES, J[0], r, J, 4)
    assert titre == "Vendée : bonnes conditions pour le cèpe dès mercredi 4 novembre"
    assert texte == "Cèpe : bonnes conditions dès mercredi 4 novembre, surtout entre 200 et 400 m, vers Pouzauges et Mauléon."


def test_au_dela_de_3_jours_a_confirmer():
    assert A.quand(J[3], J[0]) == "dès jeudi 5 novembre"
    assert A.quand(J[4], J[0]) == "dès vendredi 6 novembre (à confirmer)"
    assert A.quand(J[1], J[0]) == "demain"


def test_message_de_rappel_seul_et_seuil_par_endroits():
    r = {"girolle": jours(1, 3, 3, 3, 3, 3, 3, 3, communes=())}
    titre, texte = A.message("Vendée", [("girolle", J[1], "rappel")], ESPECES, J[0], r, J, 3)
    assert titre == "Demain en Vendée : bonnes conditions par endroits pour la girolle"
    assert texte == "Rappel : Girolle : bonnes conditions par endroits demain, surtout entre 200 et 400 m."


def test_sans_reglages_rien_n_est_envoye(monkeypatch, capsys):
    for v in ("ALERTES_DEPOT", "ALERTES_JETON", "VAPID_PRIVEE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(A, "envoyer", lambda *a: (_ for _ in ()).throw(AssertionError("envoi")))
    A.main([])
    assert "rien à envoyer" in capsys.readouterr().out
