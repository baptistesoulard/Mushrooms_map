"""Pages par département, réécrites chaque matin par l'export : la semaine de chaque espèce,
lisible sans JavaScript (ce que lisent les moteurs de recherche et les aperçus de partage).

Elles ne montrent aucun coin : le département, les tranches d'altitude et les communes, comme
le panneau de la carte. Non indexées tant que le site ne l'est pas : le jour où il le sera,
`INDEXER` ouvre les pages et écrit le plan du site (`sitemap.xml`).

Ne lit aucune donnée : reçoit les résumés déjà calculés (`export_france`), rend du HTML.
"""
from __future__ import annotations

import html
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .depot import decalage_paris
from .redaction import JOURS, MOIS

INDEXER = False
ADRESSE = "https://baptistesoulard.github.io/Mushrooms_map/"
DOSSIER = "departements"                  # sous site/, à côté de la carte
NIVEAUX_COURTS = ["hors saison", "défavorable", "possible", "par endroits", "bon"]
JOURS_COURTS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]

e = html.escape


def article(de: str) -> str:
    """« du cèpe » → « le cèpe », « de la girolle » → « la girolle »."""
    for prefixe, art in (("du ", "le "), ("de la ", "la "), ("de l'", "l'")):
        if de.startswith(prefixe):
            return art + de[len(prefixe):]
    return de


def enumerer(mots: list[str]) -> str:
    return mots[0] if len(mots) == 1 else f"{', '.join(mots[:-1])} et {mots[-1]}"


def date_longue(d: date) -> str:
    return f"{JOURS[d.weekday()]} {'1er' if d.day == 1 else d.day} {MOIS[d.month - 1]}"


def instant_paris(iso: str) -> str:
    """« 2026-11-01T05:20+00:00 » → « dimanche 1er novembre 2026 à 6 h 20 »."""
    t = datetime.fromisoformat(iso).astimezone(timezone.utc)
    t = t + timedelta(seconds=decalage_paris(int(t.timestamp())))
    return f"{date_longue(t.date())} {t.year} à {t.hour} h {t.minute:02d}"


def cle_departement(code: str) -> str:
    """Tri par numéro, la Corse (2A, 2B) à la place du 20."""
    return code.replace("2A", "20A").replace("2B", "20B")


def _niveau(resumes: dict, code: str, k: int) -> int | None:
    jours = resumes.get(code) or []
    return jours[k]["niveau"] if k < len(jours) else None


def synthese(especes: list[dict], resumes: dict, jours: list[date]) -> list[str]:
    """Les phrases de tête : ce qui est bon aujourd'hui, ce qui le devient dans la semaine, ce
    qui est hors saison toute la semaine."""
    n = len(jours)
    bon = [x for x in especes if _niveau(resumes, x["code"], 0) == 4]
    endroits = [x for x in especes if _niveau(resumes, x["code"], 0) == 3]
    phrases = []
    if bon:
        phrases.append(f"Aujourd'hui, bonnes conditions pour {enumerer([article(x['de']) for x in bon])}.")
    elif endroits:
        phrases.append("Aujourd'hui, bonnes conditions par endroits pour "
                       f"{enumerer([article(x['de']) for x in endroits])}.")
    else:
        phrases.append("Aujourd'hui, aucune espèce n'a de bonnes conditions dans le département.")
    plus_tard = []
    for x in especes:
        if x in bon:
            continue
        k = next((k for k in range(1, n) if _niveau(resumes, x["code"], k) == 4), None)
        if k is not None:
            plus_tard.append(f"{article(x['de'])} (dès {date_longue(jours[k])})")
    if plus_tard:
        phrases.append(f"Dans la semaine, bonnes conditions aussi pour {enumerer(plus_tard)}.")
    hors = [article(x["de"]) for x in especes
            if all(_niveau(resumes, x["code"], k) in (0, None) for k in range(n))]
    if hors:
        phrases.append(f"Hors saison toute la semaine : {enumerer(hors)}.")
    return phrases


def _tete(titre: str, description: str, racine: str, chemin: str) -> str:
    robots = "index, follow" if INDEXER else "noindex, nofollow"
    canonique = f'\n<link rel="canonical" href="{ADRESSE}{chemin}">' if INDEXER else ""
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="{robots}">
<title>{e(titre)}</title>
<meta name="description" content="{e(description)}">
<meta property="og:title" content="{e(titre)}">
<meta property="og:description" content="{e(description)}">{canonique}
<link rel="icon" href="{racine}favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{racine}style.css">
</head>
<body>
<div class="page">
"""


PIED = """  <p class="alerte">Ne consommez jamais un champignon sans identification certaine : faites
  contrôler votre récolte par un pharmacien ou une société mycologique.
  <a href="../avant-de-partir.html">Avant de partir</a>.</p>
  <nav class="pied">
    <a href="../">La carte</a>
    <a href="./">Par département</a>
    <a href="../methode.html">Méthode</a>
    <a href="../validation.html">Face aux observations</a>
    <a href="../a-propos.html">À propos</a>
  </nav>
</div>
</body>
</html>
"""

LEGENDE = """  <div class="legende-semaine">
    <span><span class="pastille n4"></span>bon</span>
    <span><span class="pastille n3"></span>par endroits</span>
    <span><span class="pastille n2"></span>possible</span>
    <span><span class="pastille vide"></span>défavorable</span>
    <span>– hors saison</span>
  </div>
"""


def page_departement(dep: dict, especes: list[dict], resumes: dict, jours: list[date], genere_le: str) -> str:
    """`dep` : {code, nom} ; `especes` : règles (code, nom, de, latin) ; `resumes` : par espèce,
    un résumé par jour (`export_france.faits` + `redaction.rediger`) ; `jours` : les dates."""
    code, nom = dep["code"], dep["nom"]
    carte = f"../?departement={code}"
    noms = ", ".join(x["nom"].lower() for x in especes[:4])
    tete = _tete(f"Champignons en {nom} ({code}) : les conditions de la semaine",
                 f"Où en sont les champignons en {nom} cette semaine ? {noms}… : les conditions jour "
                 "par jour, d'après la météo, les forêts et la saison.", "../", f"{DOSSIER}/{code}.html")
    lignes = [f'  <header><a href="{carte}">← La carte : {e(nom)}</a> · <a href="./">Tous les départements</a></header>',
              f"  <h1>Champignons en {e(nom)} cette semaine</h1>",
              f'  <p class="muet">Calculé le {instant_paris(genere_le)}, pour aujourd\'hui et les sept jours '
              "suivants, sur les forêts du département.</p>"]
    lignes += [f"  <p>{e(p)}</p>" for p in synthese(especes, resumes, jours)]

    actuel = ' class="actuel"'
    entete = "".join(f'<th scope="col"{actuel if k == 0 else ""}>{JOURS_COURTS[d.weekday()]}<br>{d.day}</th>'
                     for k, d in enumerate(jours))
    corps = []
    for x in especes:
        jours_x = resumes.get(x["code"]) or []
        cases = []
        for k, d in enumerate(jours):
            r = jours_x[k] if k < len(jours_x) else None
            n = r["niveau"] if r else None
            texte = f"{x['nom']}, {date_longue(d)} : {r['verdict'].lower() if r else 'pas de forêt calculée'}"
            lien = f"{carte}&amp;espece={x['code']}&amp;jour={d.isoformat()}"
            cases.append(f'<td><a class="niveau n{"x" if n is None else n}" href="{lien}" title="{e(texte)}" '
                         f'aria-label="{e(texte)}">{"–" if n == 0 else ""}</a></td>')
        corps.append(f'<tr><th scope="row">{e(x["nom"])}</th>{"".join(cases)}</tr>')
    lignes += ["  <h2>La semaine, espèce par espèce</h2>",
               '  <div class="tableau-semaine"><table class="semaine">',
               f"  <thead><tr><th></th>{entete}</tr></thead>",
               f"  <tbody>{''.join(corps)}</tbody>",
               "  </table></div>", LEGENDE.rstrip("\n"),
               '  <p class="muet">Chaque case résume les forêts du département ce jour-là. Un clic '
               "l'affiche sur la carte, forêt par forêt.</p>"]

    for x in especes:
        jours_x = resumes.get(x["code"]) or []
        lignes.append(f'  <section class="carte-espece"><h3>{e(x["nom"])} <span class="latin">{e(x["latin"])}</span></h3>')
        if not jours_x:
            lignes.append("  <p>Pas de forêt calculée dans ce département.</p></section>")
            continue
        r0 = jours_x[0]
        lignes.append(f"  <p><strong>Aujourd'hui : {e(r0['verdict'])}.</strong> {e(' '.join(r0['phrases']))}</p>")
        if all(r["niveau"] == 0 for r in jours_x):
            lignes.append("  <p>Hors saison toute la semaine.</p>")
        elif max(r["niveau"] for r in jours_x) <= 1:
            lignes.append("  <p>Aucun jour favorable cette semaine.</p>")
        else:
            k = max(range(len(jours_x)), key=lambda k: (jours_x[k]["niveau"], jours_x[k]["indice_moyen"], -k))
            lignes.append(f"  <p>Meilleur jour de la semaine : {date_longue(jours[k])} "
                          f"({NIVEAUX_COURTS[jours_x[k]['niveau']]}).</p>")
        if r0["niveau"] >= 2 and r0["communes"]:
            lignes.append("  <p>Communes les mieux placées aujourd'hui : "
                          f"{e(enumerer([c['nom'] for c in r0['communes'][:4]]))}.</p>")
        lignes.append("  </section>")
    return tete + "\n".join(lignes) + "\n" + PIED


def page_index(departements: list[dict], especes: list[dict], resumes: dict, genere_le: str) -> str:
    """La liste des départements, par numéro, avec ce qui est favorable aujourd'hui."""
    tete = _tete("Champignons par département : les conditions de la semaine",
                 "Les conditions de pousse des champignons dans chaque département de France "
                 "métropolitaine, espèce par espèce, pour aujourd'hui et les sept jours suivants.",
                 "../", f"{DOSSIER}/")
    lignes = ['  <header><a href="../">← La carte</a></header>',
              "  <h1>Champignons par département</h1>",
              f'  <p class="muet">Calculé le {instant_paris(genere_le)}. Pour chaque département, les '
              "espèces aux meilleures conditions aujourd'hui ; sa page donne la semaine.</p>",
              '  <ul class="communes departements">']
    for d in sorted(departements, key=lambda d: cle_departement(d["code"])):
        r = resumes.get(d["code"], {})
        meilleur = max((_niveau(r, x["code"], 0) or 0 for x in especes), default=0)
        if meilleur >= 2:
            quoi = [x["nom"].lower() for x in especes if _niveau(r, x["code"], 0) == meilleur]
            etat = f"{NIVEAUX_COURTS[meilleur]} : {enumerer(quoi)}"
        else:
            etat = "rien de favorable aujourd'hui"
        lignes.append(f'    <li><a href="{d["code"]}.html">{d["code"]} – {e(d["nom"])}'
                      f'<span class="cl">{e(etat)}</span></a></li>')
    lignes.append("  </ul>")
    return tete + "\n".join(lignes) + "\n" + PIED


def ecrire(site: Path, departements: list[dict], especes: list[dict], resumes: dict,
           jours: list[date], genere_le: str) -> None:
    dossier = site / DOSSIER
    dossier.mkdir(parents=True, exist_ok=True)
    for d in departements:
        (dossier / f"{d['code']}.html").write_text(
            page_departement(d, especes, resumes.get(d["code"], {}), jours, genere_le), encoding="utf-8")
    (dossier / "index.html").write_text(page_index(departements, especes, resumes, genere_le), encoding="utf-8")
    plan = site / "sitemap.xml"
    if INDEXER:
        urls = [f"{ADRESSE}{DOSSIER}/"] + [f"{ADRESSE}{DOSSIER}/{d['code']}.html" for d in departements]
        plan.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                        + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    elif plan.exists():
        plan.unlink()
