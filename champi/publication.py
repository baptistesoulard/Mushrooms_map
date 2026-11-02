"""La carte du jour est-elle déjà en ligne ? La garde des départs programmés du workflow quotidien.

GitHub ne tient pas l'heure de ses départs programmés : il les crée « au mieux », et depuis la fin
de l'été 2026 souvent avec plusieurs heures de retard (6 h le 31 octobre et 7 h le 1er novembre pour
un rendez-vous à 5 h 20, le 2 novembre toujours rien à 7 h 15). Le workflow prend donc plusieurs
rendez-vous par nuit : le premier qui part publie la carte du jour, les suivants passent ici, la
trouvent en ligne et s'arrêtent.

    python3 -m champi.publication      # écrit a_faire=oui|non dans $GITHUB_OUTPUT

Bibliothèque standard seulement : la garde tourne avant l'installation des dépendances.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import date, datetime, timezone

from .config import ADRESSE, USER_AGENT


def jour_de_la_carte(instant: float | None = None) -> date:
    """Le premier jour d'une carte calculée à cet instant : la date à Paris en heure d'hiver
    (UTC + 1 h), toute l'année. La carte de la nuit se calcule donc après 0 h l'hiver, 1 h l'été."""
    t = time.time() if instant is None else instant
    return datetime.fromtimestamp(t + 3600, timezone.utc).date()


def jour_en_ligne(adresse: str = ADRESSE) -> date | None:
    """Le premier jour de la carte publiée, ou None si le site ne répond pas."""
    # Le cache des pages GitHub garde un fichier dix minutes : une adresse jamais vue le contourne.
    url = f"{adresse}data/carte.json?garde={int(time.time())}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}),
                                    timeout=30) as r:
            return date.fromisoformat(json.load(r)["jours"][0]["date"])
    except Exception as err:
        print(f"Carte en ligne illisible ({err}).")
        return None


def a_faire(en_ligne: date | None, aujourdhui: date) -> bool:
    """Calculer, sauf si la carte publiée commence déjà aujourd'hui. Un site muet : calculer."""
    return en_ligne is None or en_ligne < aujourdhui


def main() -> None:
    aujourdhui, en_ligne = jour_de_la_carte(), jour_en_ligne()
    oui = a_faire(en_ligne, aujourdhui)
    print(f"Carte du {aujourdhui.isoformat()} : "
          + ("à calculer" if oui else "déjà en ligne, rien à refaire")
          + f" (en ligne : {en_ligne.isoformat() if en_ligne else 'rien de lisible'}).")
    sortie = os.environ.get("GITHUB_OUTPUT")
    if sortie:
        with open(sortie, "a", encoding="utf-8") as f:
            f.write(f"a_faire={'oui' if oui else 'non'}\n")


if __name__ == "__main__":
    main()
