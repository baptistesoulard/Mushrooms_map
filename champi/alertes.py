"""Alertes par ntfy : chaque matin, après l'export, une notification par département suivi quand
une espèce PASSE à « bonnes conditions » dans les jours qui viennent.

    NTFY_TOPIC=… ALERTES=85,74 python -m champi.alertes

« Passe » : par différence avec la publication précédente (le site en ligne, lu avant que le
nouveau ne le remplace), comme un journal des changements. Une espèce déjà bonne hier ne
re-sonne pas ; pas de seuil à régler, pas d'état à garder.

Le canal ntfy est un secret du dépôt (qui connaît son nom reçoit les alertes) ; la liste des
départements, une variable. Sans canal, rien n'est envoyé.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import date

from .config import SITE_DATA, USER_AGENT
from .pages_departements import ADRESSE, article, date_longue

FENETRE = 4                     # aujourd'hui et les trois jours suivants : de quoi s'organiser
SERVEUR = "https://ntfy.sh"


def bons(resumes_dep: dict, dates: list[date]) -> dict[str, date]:
    """Pour chaque espèce, le premier jour « bonnes conditions » (niveau 4) de la fenêtre."""
    premiers = {}
    for code, jours in resumes_dep.items():
        for d, r in zip(dates[:FENETRE], jours[:FENETRE]):
            if r["niveau"] == 4:
                premiers[code] = d
                break
    return premiers


def nouveautes(maintenant: dict[str, date], avant: dict[str, date]) -> dict[str, date]:
    """Ce qui est bon dans la fenêtre d'aujourd'hui et ne l'était pas dans celle d'avant."""
    return {code: d for code, d in maintenant.items() if code not in avant}


def quand(d: date, aujourdhui: date) -> str:
    ecart = (d - aujourdhui).days
    return "aujourd'hui" if ecart == 0 else "demain" if ecart == 1 else f"dès {date_longue(d)}"


def message(nom_dep: str, nouveau: dict[str, date], especes: list[dict], aujourdhui: date) -> tuple[str, str]:
    """(titre, texte) de la notification d'un département."""
    lignes = [f"{x['nom']} : bonnes conditions {quand(nouveau[x['code']], aujourdhui)}."
              for x in especes if x["code"] in nouveau]
    noms = [article(x["de"]) for x in especes if x["code"] in nouveau]
    titre = f"{nom_dep} : c'est le moment pour {noms[0]}" if len(noms) == 1 else f"{nom_dep} : {len(noms)} espèces au rendez-vous"
    return titre, "\n".join(lignes)


def _lire(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def envoyer(sujet: str, titre: str, texte: str, lien: str) -> None:
    """Publication JSON (l'en-tête HTTP ne supporte pas les accents)."""
    corps = json.dumps({"topic": sujet, "title": titre, "message": texte, "click": lien,
                        "tags": ["mushroom"]}).encode("utf-8")
    req = urllib.request.Request(SERVEUR, data=corps, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    urllib.request.urlopen(req, timeout=30).close()


def main() -> None:
    sujet = os.environ.get("NTFY_TOPIC", "").strip()
    deps = [d.strip() for d in os.environ.get("ALERTES", "").split(",") if d.strip()]
    if not sujet or not deps:
        print("Alertes : pas de canal ntfy ou pas de département (NTFY_TOPIC, ALERTES) — rien à envoyer.")
        return
    carte = json.loads((SITE_DATA / "carte.json").read_text(encoding="utf-8"))
    especes = json.loads((SITE_DATA / "especes.json").read_text(encoding="utf-8"))["especes"]
    noms = {d["code"]: d["nom"] for d in carte["departements"]}
    dates = [date.fromisoformat(j["date"]) for j in carte["jours"]]
    try:
        avant_carte = _lire(f"{ADRESSE}data/carte.json")
        dates_avant = [date.fromisoformat(j["date"]) for j in avant_carte["jours"]]
    except Exception as err:          # première publication, ou site injoignable : tout est nouveau
        print(f"Alertes : publication précédente illisible ({err}) — comparaison à vide.")
        dates_avant = None
    for dep in deps:
        if dep not in noms:
            print(f"Alertes : département inconnu {dep!r}, ignoré.")
            continue
        resumes = json.loads((SITE_DATA / "resumes" / f"{dep}.json").read_text(encoding="utf-8"))
        avant = {}
        if dates_avant:
            try:
                avant = bons(_lire(f"{ADRESSE}data/resumes/{dep}.json"), dates_avant)
            except Exception as err:
                print(f"Alertes : résumés précédents de {dep} illisibles ({err}).")
        nouveau = nouveautes(bons(resumes, dates), avant)
        if not nouveau:
            print(f"Alertes : rien de nouveau en {noms[dep]}.")
            continue
        titre, texte = message(noms[dep], nouveau, especes, dates[0])
        envoyer(sujet, titre, texte, f"{ADRESSE}departements/{dep}.html")
        print(f"Alertes : envoyé pour {noms[dep]} ({', '.join(nouveau)}).")


if __name__ == "__main__":
    main()
