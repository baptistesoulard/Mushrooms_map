"""La garde des départs programmés : la carte du jour déjà en ligne arrête le job de la nuit."""
import re
from datetime import date, datetime, timezone

from champi import publication as P
from champi.config import RACINE


def instant(texte: str) -> float:
    return datetime.fromisoformat(texte).replace(tzinfo=timezone.utc).timestamp()


def test_le_jour_de_la_carte_change_a_23_h_utc():
    assert P.jour_de_la_carte(instant("2026-11-01T22:59")) == date(2026, 11, 1)
    assert P.jour_de_la_carte(instant("2026-11-01T23:20")) == date(2026, 11, 2)    # 0 h 20 à Paris
    assert P.jour_de_la_carte(instant("2026-07-01T23:20")) == date(2026, 7, 2)     # 1 h 20 l'été


def test_rien_a_refaire_quand_la_carte_du_jour_est_en_ligne():
    j = date(2026, 11, 2)
    assert P.a_faire(date(2026, 11, 1), j)        # celle d'hier : à calculer
    assert not P.a_faire(j, j)
    assert P.a_faire(None, j)                     # site muet : calculer plutôt que rien


def test_chaque_rendez_vous_de_la_nuit_calcule_le_bon_jour():
    """Plusieurs rendez-vous (GitHub en saute ou en retarde), tous après 23 h UTC et avant le
    matin : un départ à 22 h UTC calculerait encore la veille, et la garde l'arrêterait."""
    yml = (RACINE / ".github" / "workflows" / "carte.yml").read_text(encoding="utf-8")
    heures = [int(h) for h in re.findall(r'cron: "\d+ (\d+) \* \* \*"', yml)]
    assert len(heures) >= 3
    assert all(h == 23 or h <= 5 for h in heures)
    assert "python3 -m champi.publication" in yml
