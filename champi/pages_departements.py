"""Pages par département, réécrites chaque matin par l'export : la semaine de chaque espèce,
lisible sans JavaScript (ce que lisent les moteurs de recherche et les aperçus de partage).

Elles ne montrent aucun coin : le département, les tranches d'altitude et les communes, comme
le panneau de la carte. En-tête, pied et indexation : `pages.py`.

Ne lit aucune donnée : reçoit les résumés déjà calculés (`export_france`), rend du HTML.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .pages import (JOURS_COURTS, LEGENDE, NIVEAUX_COURTS, PARTAGER, article, cle_departement, date_longue, e,
                    enumerer, image_partage, instant_paris, pied, tete)

DOSSIER = "departements"                  # sous site/, à côté de la carte


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


def page_departement(dep: dict, especes: list[dict], resumes: dict, jours: list[date], genere_le: str) -> str:
    """`dep` : {code, nom} ; `especes` : règles (code, nom, de, latin) ; `resumes` : par espèce,
    un résumé par jour (`export_france.faits` + `redaction.rediger`) ; `jours` : les dates."""
    code, nom = dep["code"], dep["nom"]
    carte = f"../carte/?departement={code}"
    noms = ", ".join(x["nom"].lower() for x in especes[:4])
    haut = tete(f"Champignons en {nom} ({code}) : les conditions de la semaine",
                f"Où en sont les champignons en {nom} cette semaine ? {noms}… : les conditions jour "
                "par jour, d'après la météo, les forêts et la saison.", "../", f"{DOSSIER}/{code}.html",
                image=image_partage(code, genere_le))
    lignes = [f'  <p class="fil"><a href="./">Départements</a> › {e(nom)}</p>',
              f"  <h1>Champignons en {e(nom)} cette semaine</h1>",
              f'  <p class="muet">Calculé le {instant_paris(genere_le)}, pour aujourd\'hui et les sept jours '
              "suivants, sur les forêts du département (sur ses prés, pour les espèces des champs).</p>"]
    lignes += [f"  <p>{e(p)}</p>" for p in synthese(especes, resumes, jours)]
    lignes.append(f'  <p class="actions"><a class="bouton principal" href="{carte}">Voir sur la carte</a>{PARTAGER}</p>')

    actuel = ' class="actuel"'
    colonnes = "".join(f'<th scope="col"{actuel if k == 0 else ""}>{JOURS_COURTS[d.weekday()]}<br>{d.day}</th>'
                     for k, d in enumerate(jours))
    corps = []
    for x in especes:
        jours_x = resumes.get(x["code"]) or []
        cases = []
        for k, d in enumerate(jours):
            r = jours_x[k] if k < len(jours_x) else None
            n = r["niveau"] if r else None
            texte = f"{x['nom']}, {date_longue(d)} : {r['verdict'].lower() if r else 'rien de calculé ici'}"
            lien = f"{carte}&amp;espece={x['code']}&amp;jour={d.isoformat()}"
            cases.append(f'<td><a class="niveau n{"x" if n is None else n}" href="{lien}" title="{e(texte)}" '
                         f'aria-label="{e(texte)}">{"–" if n == 0 else ""}</a></td>')
        corps.append(f'<tr><th scope="row">{e(x["nom"])}</th>{"".join(cases)}</tr>')
    lignes += ["  <h2>La semaine, espèce par espèce</h2>",
               '  <div class="tableau-semaine"><table class="semaine">',
               f"  <thead><tr><th></th>{colonnes}</tr></thead>",
               f"  <tbody>{''.join(corps)}</tbody>",
               "  </table></div>", LEGENDE.rstrip("\n"),
               '  <p class="muet">Chaque case résume les forêts du département ce jour-là, ou ses prés pour '
               "les espèces des champs. Un clic l'affiche sur la carte, forêt par forêt ; les prés n'ont pas "
               "de carte fine, ils sont presque tous privés.</p>"]

    for x in especes:
        jours_x = resumes.get(x["code"]) or []
        lignes.append(f'  <section class="carte-espece"><h3>{e(x["nom"])} <span class="latin">{e(x["latin"])}</span></h3>')
        if not jours_x:
            lignes.append(f"  <p>Pas de {'pré' if x.get('milieu') == 'pre' else 'forêt'} calculé"
                          f"{'' if x.get('milieu') == 'pre' else 'e'} dans ce département.</p></section>")
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
    return haut + "\n".join(lignes) + "\n" + pied("../")


def page_index(departements: list[dict], especes: list[dict], resumes: dict, genere_le: str) -> str:
    """La liste des départements, par numéro, avec ce qui est favorable aujourd'hui."""
    haut = tete("Champignons par département : les conditions de la semaine",
                "Les conditions de pousse des champignons dans chaque département de France "
                "métropolitaine, espèce par espèce, pour aujourd'hui et les sept jours suivants.",
                "../", f"{DOSSIER}/", image=image_partage("france", genere_le))
    lignes = ["  <h1>Champignons par département</h1>",
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
    return haut + "\n".join(lignes) + "\n" + pied("../")


def ecrire(site: Path, departements: list[dict], especes: list[dict], resumes: dict,
           jours: list[date], genere_le: str) -> list[str]:
    """Écrit les pages ; rend leurs chemins depuis la racine, pour le plan du site."""
    dossier = site / DOSSIER
    dossier.mkdir(parents=True, exist_ok=True)
    for d in departements:
        (dossier / f"{d['code']}.html").write_text(
            page_departement(d, especes, resumes.get(d["code"], {}), jours, genere_le), encoding="utf-8")
    (dossier / "index.html").write_text(page_index(departements, especes, resumes, genere_le), encoding="utf-8")
    return [f"{DOSSIER}/"] + [f"{DOSSIER}/{d['code']}.html" for d in departements]
