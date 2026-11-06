"""Alertes personnalisées, chaque matin après l'export : chaque abonné reçoit une notification sur
son appareil (Web Push) quand une espèce de sa liste DEVIENT favorable dans son département au
cours des 7 prochains jours, puis un rappel la veille.

    ALERTES_DEPOT=compte/champi-coins ALERTES_JETON=… VAPID_PRIVEE=… python -m champi.alertes
    python -m champi.alertes --essai        # une notification d'essai à chaque abonné

Les abonnements vivent dans alertes.json, dans le dépôt privé du lien de groupe : la carte les y
écrit (site/alertes.js), ce job les lit. « Devient » : par différence avec la publication encore en
ligne, lue avant que la nouvelle ne la remplace ; aucun état à garder. Sans dépôt, jeton ou clé
privée, rien n'est envoyé. Le contenu d'une notification est chiffré de bout en bout : le service
de notification du navigateur (Google, Apple, Mozilla) ne le lit pas.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date

from .config import SITE_DATA, USER_AGENT
from .pages import ADRESSE, article, date_longue, enumerer

FENETRE = 7                      # jours à venir surveillés, aujourd'hui compris
CONFIRMER_APRES = 3              # au-delà de 3 jours, la prévision se dit « à confirmer »
SEUILS = {"bon": 4, "endroits": 3}
FORMULES = {4: "bonnes conditions", 3: "bonnes conditions par endroits"}
API = "https://api.github.com"
FICHIER = "alertes.json"
FORMAT = "champi-alertes"


def premiers(resumes_dep: dict, dates: list[date], seuil: int) -> dict[str, date]:
    """Pour chaque espèce, le premier jour de la fenêtre où le niveau atteint le seuil."""
    out = {}
    for code, jours in resumes_dep.items():
        for d, r in zip(dates[:FENETRE], jours[:FENETRE]):
            if r["niveau"] >= seuil:
                out[code] = d
                break
    return out


def evenements(maintenant: dict[str, date], avant: dict[str, date], demain: date,
               rappels: bool = True) -> list[tuple[str, date, str]]:
    """Ce qui mérite un message : les espèces qui DEVIENNENT favorables (« nouveau »), et celles
    déjà annoncées dont le premier jour favorable est demain (« rappel »). Le rappel ne sonne
    qu'une fois par jour : `rappels` est faux quand la publication précédente est déjà du jour
    (le workflow peut publier plusieurs fois, un départ en retard ou un commit)."""
    evts = []
    for code, d in maintenant.items():
        if code not in avant:
            evts.append((code, d, "nouveau"))
        elif d == demain and rappels:
            evts.append((code, d, "rappel"))
    return sorted(evts, key=lambda e: (e[1], e[0]))


def quand(d: date, aujourdhui: date) -> str:
    ecart = (d - aujourdhui).days
    if ecart <= 0:
        return "aujourd'hui"
    if ecart == 1:
        return "demain"
    return f"dès {date_longue(d)}" + (" (à confirmer)" if ecart > CONFIRMER_APRES else "")


def precision(resume_jour: dict | None) -> str:
    """Où chercher dans le département : la meilleure tranche d'altitude et deux communes."""
    if not resume_jour:
        return ""
    bouts = []
    t = resume_jour.get("meilleure_tranche")
    if t:
        bouts.append(f"surtout entre {t[0]} et {t[1]} m")
    communes = [c["nom"] for c in resume_jour.get("communes", [])[:2]]
    if communes:
        bouts.append(f"vers {enumerer(communes)}")
    return ", ".join(bouts)


def message(nom_dep: str, evts: list[tuple[str, date, str]], especes: list[dict], aujourdhui: date,
            resumes_dep: dict, dates: list[date], seuil: int) -> tuple[str, str]:
    """(titre, texte) de la notification d'un département pour un abonné."""
    par_code = {x["code"]: x for x in especes}
    formule = FORMULES[seuil]
    lignes = []
    for code, d, nature in evts:
        x = par_code[code]
        jours_x = resumes_dep.get(code) or []
        k = dates.index(d) if d in dates else None
        ou = precision(jours_x[k] if k is not None and k < len(jours_x) else None)
        lignes.append(f"{'Rappel : ' if nature == 'rappel' else ''}{x['nom']} : {formule} {quand(d, aujourdhui)}"
                      + (f", {ou}" if ou else "") + ".")
    nouveaux = [e for e in evts if e[2] == "nouveau"]
    if len(nouveaux) == 1:
        code, d, _ = nouveaux[0]
        titre = f"{nom_dep} : {formule} pour {article(par_code[code]['de'])} {quand(d, aujourdhui)}"
    elif nouveaux:
        titre = f"{nom_dep} : {len(nouveaux)} espèces au rendez-vous"
    else:
        noms = [article(par_code[c]["de"]) for c, _, _ in evts]
        titre = f"Demain en {nom_dep} : {formule} pour {enumerer(noms)}"
    return titre, "\n".join(lignes)


def _get(url: str, jeton: str | None = None):
    entetes = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if jeton:
        entetes["Authorization"] = f"Bearer {jeton}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=entetes), timeout=30) as r:
        return json.load(r)


def lire_abonnes(depot: str, jeton: str) -> list[dict]:
    """Les abonnés du fichier alertes.json du dépôt privé (liste vide s'il n'existe pas)."""
    try:
        j = _get(f"{API}/repos/{depot}/contents/{FICHIER}", jeton)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return []
        raise
    doc = json.loads(base64.b64decode(j["content"]).decode("utf-8"))
    if doc.get("format") != FORMAT:
        raise ValueError(f"{FICHIER} n'est pas un fichier d'alertes")
    return [a for a in doc.get("abonnes", []) if a.get("push", {}).get("endpoint") and a.get("alertes")]


def envoyer(push: dict, titre: str, texte: str, lien: str, cle_privee: str, tag: str) -> bool:
    """Une notification Web Push ; False si l'abonnement n'existe plus (appareil désinscrit)."""
    from pywebpush import WebPushException, webpush      # chiffrement : sous Linux, dans Actions
    try:
        webpush(subscription_info=push, data=json.dumps({"titre": titre, "texte": texte, "lien": lien, "tag": tag}),
                vapid_private_key=cle_privee, vapid_claims={"sub": ADRESSE}, ttl=24 * 3600)
        return True
    except WebPushException as err:
        if err.response is not None and err.response.status_code in (404, 410):
            return False
        raise


def main(argv: list[str]) -> None:
    depot = os.environ.get("ALERTES_DEPOT", "").strip()
    jeton = os.environ.get("ALERTES_JETON", "").strip()
    cle = os.environ.get("VAPID_PRIVEE", "").strip()
    if not (depot and jeton and cle):
        print("Alertes : dépôt, jeton ou clé privée absents (ALERTES_DEPOT, ALERTES_JETON, VAPID_PRIVEE) — rien à envoyer.")
        return
    abonnes = lire_abonnes(depot, jeton)
    print(f"Alertes : {len(abonnes)} appareil(s) abonné(s).")
    if "--essai" in argv:
        for a in abonnes:
            envoyer(a["push"], "Champimétéo : notification d'essai",
                    "Si tu lis ceci, les alertes arrivent bien sur cet appareil.", ADRESSE, cle, "essai")
        return

    carte = json.loads((SITE_DATA / "carte.json").read_text(encoding="utf-8"))
    especes = json.loads((SITE_DATA / "especes.json").read_text(encoding="utf-8"))["especes"]
    noms = {d["code"]: d["nom"] for d in carte["departements"]}
    dates = [date.fromisoformat(j["date"]) for j in carte["jours"]]
    try:
        dates_avant = [date.fromisoformat(j["date"]) for j in _get(f"{ADRESSE}data/carte.json")["jours"]]
    except Exception as err:            # première publication, ou site injoignable : tout est nouveau
        print(f"Alertes : publication précédente illisible ({err}) — comparaison à vide.")
        dates_avant = None
    resumes, avant = {}, {}
    expires = 0
    for a in abonnes:
        for alerte in a["alertes"]:
            dep, seuil = alerte.get("departement"), SEUILS.get(alerte.get("seuil"), 4)
            if dep not in noms:
                continue
            if dep not in resumes:
                resumes[dep] = json.loads((SITE_DATA / "resumes" / f"{dep}.json").read_text(encoding="utf-8"))
                try:
                    avant[dep] = _get(f"{ADRESSE}data/resumes/{dep}.json") if dates_avant else {}
                except Exception:
                    avant[dep] = {}
            liste = set(alerte.get("especes", []))
            maintenant = {c: d for c, d in premiers(resumes[dep], dates, seuil).items() if c in liste}
            precedent = {c: d for c, d in premiers(avant[dep], dates_avant or [], seuil).items() if c in liste}
            evts = evenements(maintenant, precedent, dates[1] if len(dates) > 1 else dates[0],
                              rappels=not dates_avant or dates_avant[0] < dates[0])
            if not evts:
                continue
            titre, texte = message(noms[dep], evts, especes, dates[0], resumes[dep], dates, seuil)
            if not envoyer(a["push"], titre, texte, f"{ADRESSE}departements/{dep}.html", cle, f"alerte-{dep}"):
                expires += 1
                break
            print(f"Alertes : envoyé à {a.get('nom') or 'un appareil'} pour {noms[dep]} ({len(evts)} espèce(s)).")
    if expires:
        print(f"Alertes : {expires} appareil(s) désinscrit(s) depuis, ignoré(s).")


if __name__ == "__main__":
    main(sys.argv[1:])
