"""Les phrases du site. Ne lit aucune donnée : reçoit des faits, rend du texte.

Testable sur des faits fabriqués (`tests/test_redaction.py`).
"""
from __future__ import annotations

from datetime import date

NBSP = " "
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

NIVEAUX = {
    0: "Hors saison",
    1: "Conditions défavorables",
    2: "Pousse possible, sans plus",
    3: "Bonnes conditions par endroits",
    4: "Bonnes conditions",
}


def nombre(x: float, decimales: int = 0) -> str:
    s = f"{x:,.{decimales}f}".replace(",", NBSP).replace(".", ",")
    if s.startswith("-") and set(s[1:]) <= set("0,"):
        s = s[1:]   # jamais de zéro signé
    return s


def altitude(m: float) -> str:
    return f"{nombre(m)}{NBSP}m"


def libelle_jour(jour: date, aujourdhui: date) -> str:
    ecart = (jour - aujourdhui).days
    premier = "1er" if jour.day == 1 else str(jour.day)
    complet = f"{JOURS[jour.weekday()]} {premier} {MOIS[jour.month - 1]}"
    if ecart == 0:
        return f"aujourd'hui, {complet}"
    if ecart == 1:
        return f"demain, {complet}"
    return complet


# Le verdict : parts de la forêt à l'indice « bon » (≥ 0,40) et « moyen » (≥ 0,25). Publiés dans
# carte.json (« niveaux ») : « Que chercher ici ? » rend le même verdict pour la zone affichée.
# « Bon » dès 30 % de la forêt depuis le 2026-11-07 (15 % avant) : à 15 %, un département ou un
# carré de l'accueil était « bon » avec quelques massifs (66 départements pour la chanterelle en
# tube le 7 novembre, 50 à 30 %). Un choix de rédaction, pas une règle d'espèce : il ne change
# aucun indice, seulement le mot qui les résume.
SEUILS_NIVEAU = {"bon": 0.30, "endroits": 0.05, "possible": 0.05}


def niveau(faits: dict) -> int:
    if faits["saison"] <= 0:
        return 0
    bon = faits["part_bon"]
    if bon >= SEUILS_NIVEAU["bon"]:
        return 4
    if bon >= SEUILS_NIVEAU["endroits"]:
        return 3
    if faits["part_moyen"] >= SEUILS_NIVEAU["possible"]:
        return 2
    return 1


def lieux(esp: dict) -> str:
    """« les forêts », ou « les prés » pour une espèce des champs."""
    return "les prés" if esp.get("milieu") == "pre" else "les forêts"


def rediger(esp: dict, faits: dict) -> dict:
    """`esp` : règles de l'espèce (dict) ; `faits` : sortie de `export.faits_du_jour`."""
    n = niveau(faits)
    phrases: list[str] = []

    if n == 0:
        debut, _, _, fin = esp["saison"]
        phrases.append(f"La saison {esp['de']} court en gros du {_date_courte(debut)} au "
                       f"{_date_courte(fin)}.")
        return {"niveau": n, "verdict": NIVEAUX[n], "phrases": phrases}

    meilleure = faits.get("meilleure_tranche")
    if meilleure and n >= 2:
        phrases.append(f"Les meilleures conditions se situent entre {altitude(meilleure[0])} et "
                       f"{altitude(meilleure[1])}.")

    lim = faits["limitant"]
    j_min, j_max = esp["pluie_jours"]
    if lim == "pluie":
        phrases.append(
            f"Il a trop peu plu entre {j_max} et {j_min} jours avant : {nombre(faits['pluie_moy'])}{NBSP}mm "
            f"en moyenne sur {lieux(esp)}, quand il en faut environ {nombre(esp['pluie_mm'][1])}.")
    elif lim == "sol_froid":
        seuil = esp["sol"][1]
        if faits.get("froid_au_dessus") is not None:
            phrases.append(f"Le sol est trop froid au-dessus de {altitude(faits['froid_au_dessus'])} "
                           f"(moins de {nombre(seuil)}{NBSP}°C en moyenne sur la semaine).")
        elif n >= 3:   # le sol freine sans fermer la porte : « trop » contredirait le verdict
            phrases.append(f"Le sol est frais presque partout (moins de {nombre(seuil)}{NBSP}°C) : "
                           f"c'est ce qui limite l'indice.")
        else:
            phrases.append(f"Le sol est trop froid presque partout (moins de {nombre(seuil)}{NBSP}°C).")
    elif lim == "sol_chaud":
        seuil = esp["sol"][2]
        if faits.get("chaud_en_dessous") is not None:
            phrases.append(f"Le sol est trop chaud en dessous de {altitude(faits['chaud_en_dessous'])} "
                           f"(plus de {nombre(seuil)}{NBSP}°C) : la pousse remonte en altitude.")
        elif n >= 3:
            phrases.append(f"Le sol est chaud presque partout (plus de {nombre(seuil)}{NBSP}°C) : "
                           f"c'est ce qui limite l'indice.")
        else:
            phrases.append(f"Le sol est trop chaud (plus de {nombre(seuil)}{NBSP}°C).")
    elif lim == "gel":
        phrases.append(f"Des gelées ont touché {lieux(esp)} ces derniers jours : la pousse s'arrête.")
    elif lim == "saison":
        phrases.append("Début de saison : les premières pousses restent rares." if faits["debut_saison"]
                       else "Fin de saison : les pousses se raréfient.")
    else:
        phrases.append("La pluie des dernières semaines et la température du sol sont favorables.")

    return {"niveau": n, "verdict": NIVEAUX[n], "phrases": phrases}


def fiabilite(meteo: dict) -> dict:
    """Ce que la validation dit de l'indice météo d'une espèce, face au seul calendrier.

    `meteo` : le bloc « meteo » d'une espèce dans data/validation.json.
    """
    if "ic_ecart" not in meteo:
        return {"sens": "inconnu",
                "texte": "Trop peu d'observations datées pour vérifier l'indice météo de cette espèce."}
    bas, haut = meteo["ic_ecart"]
    if bas > 0:
        return {"sens": "mieux",
                "texte": "Vérifié sur les observations passées : l'indice météo repère mieux les jours "
                         "de pousse que le seul calendrier."}
    if haut < 0:
        return {"sens": "moins",
                "texte": "Attention : sur les observations passées, l'indice météo repère moins bien "
                         "les jours de pousse que le seul calendrier. Fiez-vous d'abord à la saison."}
    return {"sens": "pareil",
            "texte": "Sur les observations passées, l'indice météo ne fait pas nettement mieux que le "
                     "seul calendrier."}


def _date_courte(mmjj: str) -> str:
    m, j = (int(v) for v in mmjj.split("-"))
    return f"{'1er' if j == 1 else j} {MOIS[m - 1]}"
