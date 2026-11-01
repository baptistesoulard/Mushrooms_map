"""Alertes ntfy : ce qui sonne, et ce qui ne re-sonne pas."""
from datetime import date, timedelta

from champi import alertes as A

J = [date(2026, 11, 1) + timedelta(days=k) for k in range(8)]
ESPECES = [{"code": "cepe", "nom": "Cèpe", "de": "du cèpe"}, {"code": "bolet_bai", "nom": "Bolet bai", "de": "du bolet bai"}]


def jours(*niveaux):
    return [{"niveau": n} for n in niveaux]


def test_premier_bon_jour_dans_la_fenetre():
    r = {"cepe": jours(2, 3, 4, 4, 4, 4, 4, 4), "bolet_bai": jours(2, 2, 2, 2, 4, 4, 4, 4)}
    assert A.bons(r, J) == {"cepe": J[2]}          # le bolet bai n'est bon qu'au 5e jour : trop loin


def test_seul_ce_qui_devient_bon_sonne():
    hier = A.bons({"cepe": jours(4, 4, 4, 4), "bolet_bai": jours(1, 1, 1, 1)}, [d - timedelta(days=1) for d in J])
    aujourdhui = A.bons({"cepe": jours(4, 4, 4, 4), "bolet_bai": jours(1, 1, 3, 4)}, J)
    assert A.nouveautes(aujourdhui, hier) == {"bolet_bai": J[3]}


def test_message():
    titre, texte = A.message("Vendée", {"bolet_bai": J[3]}, ESPECES, J[0])
    assert titre == "Vendée : c'est le moment pour le bolet bai"
    assert texte == "Bolet bai : bonnes conditions dès mercredi 4 novembre."
    titre, texte = A.message("Vendée", {"cepe": J[0], "bolet_bai": J[1]}, ESPECES, J[0])
    assert titre == "Vendée : 2 espèces au rendez-vous"
    assert texte.splitlines() == ["Cèpe : bonnes conditions aujourd'hui.", "Bolet bai : bonnes conditions demain."]


def test_sans_canal_rien_n_est_envoye(monkeypatch, capsys):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.setattr(A, "envoyer", lambda *a: (_ for _ in ()).throw(AssertionError("envoi")))
    A.main()
    assert "rien à envoyer" in capsys.readouterr().out
