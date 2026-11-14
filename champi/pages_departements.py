"""Pages par département, réécrites chaque matin par l'export : la semaine de chaque espèce,
lisible sans JavaScript (ce que lisent les moteurs de recherche et les aperçus de partage).

Elles ne montrent aucun coin : le département, les tranches d'altitude et les communes, comme
le panneau de la carte. En-tête, pied et indexation : `pages.py`.

Ne lit aucune donnée : reçoit les résumés déjà calculés (`export_france`), rend du HTML.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import json
import re

from .carte_departements import charger as charger_contours, voisins as voisins_de
from .pages import (JOURS_COURTS, LEGENDE, NIVEAUX_COURTS, NOM, PARTAGER, article, bandeau, calcule_pour, chemin_departement,
                    chemin_espece, cle_departement, renvoi, slug,
                    dans, date_longue, e, enumerer, faq, fil_ariane, icone, image_partage, instant_paris,
                    meilleur_niveau, national, ordre_saison, page_web, pct, pied, surface_bonne, tete)
from .redaction import MOIS, NBSP, NIVEAUX, altitude, nombre

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


def meilleure_espece(especes: list[dict], resumes: dict, k: int = 0) -> dict | None:
    """L'espèce la mieux placée le jour `k` : le niveau, puis la forêt aux bonnes conditions, puis
    l'indice ; l'ordre des règles départage. None sans aucun calcul."""
    cands = [((r[k]["niveau"], surface_bonne(r[k]), r[k]["indice_moyen"], -i), x)
             for i, x in enumerate(especes) if k < len(r := resumes.get(x["code"]) or [])]
    return max(cands, key=lambda c: c[0])[1] if cands else None


def meilleur_moment(especes: list[dict], resumes: dict, n_jours: int) -> tuple[dict | None, int]:
    """L'espèce et le jour les mieux placés de la semaine, le plus tôt à égalité."""
    cands = [((r["niveau"], surface_bonne(r), r["indice_moyen"], -k, -i), x, k)
             for i, x in enumerate(especes) for k, r in enumerate((resumes.get(x["code"]) or [])[:n_jours])]
    if not cands:
        return None, 0
    _, x, k = max(cands, key=lambda c: c[0])
    return x, k


def _annees_sur_10(f: float) -> str:
    """La part des années favorables (`climatologie`), dite comme sur les fiches."""
    if f < 0.05:
        return "Rarement"
    if f >= 0.95:
        return "Presque chaque année"
    n = int(f * 10 + 0.5)
    return f"{n} année{'s' if n > 1 else ''} sur 10"


def _majuscule(t: str) -> str:
    return t[:1].upper() + t[1:]


def chiffres(especes: list[dict], resumes: dict, jours: list[date]) -> list[tuple[str, str, str]]:
    """Les chiffres de tête, (titre, valeur, précision) : l'espèce la mieux placée aujourd'hui, la
    part de forêt aux bonnes conditions, le meilleur jour de la semaine, et ce qui est habituel à
    cette date (en France, `climatologie`)."""
    x = meilleure_espece(especes, resumes)
    if x is None:
        return []
    r0 = resumes[x["code"]][0]
    n = r0["niveau"]
    sortie = []
    if n >= 2:
        sortie.append(("Le mieux placé aujourd'hui", x["nom"], NIVEAUX[n]))
        if r0.get("km2") and "part_bon" in r0:
            lieu = "prés" if x.get("milieu") == "pre" else "forêt"
            sortie.append((f"{_majuscule(lieu)} aux bonnes conditions", pct(r0["part_bon"]),
                           f"des {nombre(r0['km2'])}{NBSP}km² de {lieu}, pour {article(x['de'])}"))
    else:
        sortie.append(("Aujourd'hui", "Hors saison" if n == 0 else "Rien de favorable",
                       "pour toutes les espèces suivies" if n == 0 else "aucune espèce au-dessus de « défavorable »"))
    y, k = meilleur_moment(especes, resumes, len(jours))
    ny = resumes[y["code"]][k]["niveau"] if y else 0
    if ny >= 2:
        quand = "Aujourd'hui" if k == 0 else _majuscule(date_longue(jours[k]))
        sortie.append(("Meilleur jour de la semaine", quand, f"{y['nom']} : {NIVEAUX_COURTS[ny]}"))
    h = x if n >= 2 or not y else y
    if h.get("habituel") is not None:
        sortie.append(("D'habitude à cette date", _annees_sur_10(h["habituel"]),
                       f"en France, la météo {h['de']} est favorable"))
    return sortie


# --- Les forêts publiques nommées (décision du 2026-11-07, `forets.py`) --------------------

FORETS_MAX = 10           # les forêts montrées sur la page d'un département


def _avec_article(nom: str) -> str:
    """« Forêt domaniale de Mervent » au milieu d'une phrase : « la forêt domaniale de Mervent »."""
    if nom.startswith("Forêt"):
        return "la f" + nom[1:]
    if nom.startswith("Bois "):
        return "le b" + nom[1:]
    return nom


def _statut(f: dict) -> str:
    """« domaniale » ou « publique », quand le nom de la forêt ne le dit pas déjà."""
    nom = f["nom"].lower()
    if f["nature"] == "domaniale":
        return "" if "domaniale" in nom else "domaniale"
    return "" if re.search(r"communale|départementale|sectionale|indivise|régionale|syndicale", nom) else "publique"


def nom_court(nom: str) -> str:
    """« Forêt domaniale des Pays de Monts » → « des Pays de Monts » (pour « les forêts de Mervent,
    des Pays de Monts… ») ; un nom sans « Forêt … de » reste entier."""
    m = re.match(r"^(?:Forêt|Bois)(?: [a-zéèê]+)? ((?:de la |de l'|des |du |de |d')\S.*)$", nom)
    return m.group(1) if m else nom


def classer_forets(forets: list[dict], especes: list[dict]) -> list[tuple[dict, dict | None, int]]:
    """Les forêts du département, (forêt, espèce la mieux placée aujourd'hui, niveau), les mieux
    placées d'abord : le niveau, puis la surface aux bonnes conditions, puis la surface."""
    sortie = []
    for f in forets:
        meilleure, cle_m = None, (0, 0.0)
        for x in especes:
            j = (f.get("especes", {}).get(x["code"]) or [None])[0]
            if j and (j["niveau"], j["part_bon"]) > cle_m:
                meilleure, cle_m = x, (j["niveau"], j["part_bon"])
        sortie.append((f, meilleure, cle_m[0]))
    sortie.sort(key=lambda t: (-t[2], -(t[0]["especes"][t[1]["code"]][0]["part_bon"] * t[0]["ha"] if t[1] else 0),
                               -t[0]["ha"]))
    return sortie


def section_forets(forets: list[dict], especes: list[dict], jours: list[date], lieu: str) -> list[str]:
    """« Où chercher : les forêts publiques » : un tableau des plus grandes forêts publiques du
    département, chacune avec son espèce la mieux placée aujourd'hui et son meilleur jour."""
    classees = classer_forets(forets, especes)[:FORETS_MAX]
    if not classees:
        return []
    lignes = [f"  <h2>Où chercher {e(lieu)} : les forêts publiques</h2>",
              f"  <p>Les {len(classees)} forêts publiques les mieux placées aujourd'hui parmi celles de plus de "
              "100 ha (domaniales, communales, départementales), où une cueillette familiale est en général "
              "tolérée, dans la limite des règles locales. Chaque forêt est jugée sur l'ensemble de ses bois, "
              "hors zones protégées.</p>",
              '  <div class="tableau"><table class="forets">',
              "  <thead><tr><th scope=\"col\">Forêt</th><th scope=\"col\">Aujourd'hui</th>"
              "<th scope=\"col\">Meilleur jour</th></tr></thead>",
              "  <tbody>"]
    for f, x, n in classees:
        auj = f"{x['nom']} : {NIVEAUX_COURTS[n]}" if x and n >= 2 else (
            "hors saison" if n == 0 else "rien de favorable")
        cands = [(j["niveau"], j["part_bon"], -k, z, k) for z in especes
                 for k, j in enumerate((f.get("especes", {}).get(z["code"]) or [])[:len(jours)])]
        semaine = "—"
        if cands and (b := max(cands, key=lambda c: c[:3]))[0] >= 2:
            d = jours[b[4]]
            semaine = f"{JOURS_COURTS[d.weekday()]} {d.day} : {b[3]['nom'].lower()}, {NIVEAUX_COURTS[b[0]]}"
        statut = f" · {_statut(f)}" if _statut(f) else ""
        lignes.append(f'    <tr><th scope="row">{e(f["nom"])}<span class="cl">{nombre(f["ha"])} ha{statut}</span></th>'
                      f"<td>{e(auj)}</td><td>{e(semaine)}</td></tr>")
    lignes += ["  </tbody></table></div>",
               '  <p class="muet">Une forêt publique peut avoir sa réserve ou son arrêté : renseignez-vous auprès '
               "de l'ONF ou de la mairie. Forêts : IGN, BD TOPO.</p>"]
    return lignes


def questions(dep: dict, especes: list[dict], resumes: dict, jours: list[date], genere_le: str,
              forets: list[dict] | None = None) -> list[tuple[str, str]]:
    """Les questions fréquentes du département, répondues avec les chiffres du jour, en texte brut :
    écrites dans la page et reprises telles quelles dans ses données structurées (FAQPage)."""
    lieu = dans(dep["code"], dep["nom"])
    x = meilleure_espece(especes, resumes)
    r0 = resumes[x["code"]][0] if x else None
    y, k = meilleur_moment(especes, resumes, len(jours))
    sortie = [(f"Y a-t-il des champignons en ce moment {lieu} ?",
               f"{' '.join(synthese(especes, resumes, jours))} Calculé le {instant_paris(genere_le)}.")]

    carte = ("Sur la carte, le filtre « Forêts publiques seulement » garde les forêts où une cueillette "
             "familiale est en général tolérée.")
    bonnes = [(f, z, n) for f, z, n in classer_forets(forets or [], especes) if n >= 2][:3]
    if bonnes:
        carte = ("Parmi les forêts publiques, les mieux placées aujourd'hui sont "
                 + enumerer([f"{_avec_article(f['nom'])} ({z['nom'].lower()}, {NIVEAUX_COURTS[n]})"
                             for f, z, n in bonnes]) + ". " + carte)
    if r0 and r0["niveau"] >= 2:
        ou = []
        if r0.get("communes"):
            ou.append(f"Pour {article(x['de'])}, les communes les mieux placées aujourd'hui sont "
                      f"{enumerer([c['nom'] for c in r0['communes'][:4]])}.")
        if r0.get("meilleure_tranche"):
            a, b = r0["meilleure_tranche"]
            ou.append(f"Surtout entre {altitude(a)} et {altitude(b)} d'altitude.")
        if x.get("milieu") == "pre":
            ou.append("Les prés sont presque tous privés : la carte les montre commune par commune, jamais pré par pré.")
        sortie.append((f"Où chercher des champignons {lieu} ?", " ".join(ou + [carte])))
    else:
        quand = ""
        if y and resumes[y["code"]][k]["niveau"] >= 2:
            quand = (f" Le meilleur moment de la semaine : {date_longue(jours[k])}, pour {article(y['de'])} "
                     f"({NIVEAUX_COURTS[resumes[y['code']][k]['niveau']]}).")
        sortie.append((f"Où chercher des champignons {lieu} ?",
                       f"Aucune espèce n'a de bonnes conditions aujourd'hui {lieu}.{quand} {carte}"))

    semaine = []
    for z in especes:
        r = (resumes.get(z["code"]) or [])[:len(jours)]
        if r and max(j["niveau"] for j in r) >= 3:
            kk = max(range(len(r)), key=lambda i: (r[i]["niveau"], r[i]["indice_moyen"], -i))
            semaine.append(f"{article(z['de'])} ({NIVEAUX_COURTS[r[kk]['niveau']]} {date_longue(jours[kk])})")
    if semaine:
        reponse = f"Cette semaine, les conditions sont bonnes au moins par endroits pour {enumerer(semaine)}."
    elif any(j["niveau"] > 0 for z in especes for j in (resumes.get(z["code"]) or [])[:len(jours)]):
        reponse = "Aucune espèce suivie n'atteint de bonnes conditions cette semaine."
    else:
        reponse = "Toutes les espèces suivies sont hors saison cette semaine."
    sortie.append((f"Quels champignons chercher {lieu} cette semaine ?", reponse))

    sortie.append((f"A-t-on le droit de ramasser des champignons {lieu} ?",
                   "Les champignons appartiennent au propriétaire du terrain : en forêt publique, une cueillette "
                   "familiale est en général tolérée ; en forêt privée, il faut son accord. Sans autorisation, "
                   "c'est une contravention sous 10 litres, un délit au-delà. Beaucoup de préfectures limitent la "
                   "cueillette par arrêté : renseignez-vous en mairie ou auprès de l'ONF."))
    return sortie


def page_departement(dep: dict, especes: list[dict], resumes: dict, jours: list[date], genere_le: str,
                     voisins: list[tuple[dict, dict]] | None = None, forets: list[dict] | None = None) -> str:
    """`dep` : {code, nom} ; `especes` : règles (code, nom, de, latin, habituel) ; `resumes` : par
    espèce, un résumé par jour (`export_france.faits` + `redaction.rediger`) ; `jours` : les dates ;
    `voisins` : les départements qui le touchent, avec leurs résumés ; `forets` : ses forêts
    publiques nommées, avec leur verdict par espèce et par jour (`export_france.verdict_foret`)."""
    code, nom = dep["code"], dep["nom"]
    lieu = dans(code, nom)
    chemin = chemin_departement(code, nom)
    R = "../../"                                   # la page est dans departements/<nom>/
    carte = f"{R}carte/?departement={code}"
    noms = ", ".join(x["nom"].lower() for x in especes[:4])
    jour = f"{'1er' if jours[0].day == 1 else jours[0].day} {MOIS[jours[0].month - 1]}"
    titre = f"Où trouver des champignons {lieu} ({code}) : la semaine du {jour}"
    grandes = sorted(forets or [], key=lambda f: -f["ha"])
    if grandes:     # les plus grandes forêts publiques : ce que l'on tape (« forêt de Mervent champignons »)
        quoi = "les forêts " + enumerer([nom_court(f["nom"]) for f in grandes[:3]]) + ("…" if len(grandes) > 3 else "")
        description = (f"Où chercher les champignons {lieu} cette semaine : {quoi} ({noms}…), jour par jour, "
                       "d'après la pluie, la température du sol et la saison. Mis à jour chaque matin.")
    else:
        description = (f"Où chercher les champignons {lieu} cette semaine ({noms}…) : jour par jour, les communes "
                       "les mieux placées, d'après la pluie, la température du sol et la saison. Mis à jour chaque matin.")
    qr = questions(dep, especes, resumes, jours, genere_le, forets)
    web = page_web(titre, chemin, genere_le, description)
    if grandes:
        web["mentions"] = [{"@type": "Place", "name": f["nom"]} for f in grandes[:FORETS_MAX]]
    haut = tete(titre, description, R, chemin, image=image_partage(code, genere_le),
                ld=[web, fil_ariane([("./", NOM), (f"{DOSSIER}/", "Départements"), (chemin, nom)]), faq(qr)])
    phrases = synthese(especes, resumes, jours)
    lignes = bandeau(
        f"Département · {code}", f"Où trouver des champignons {e(lieu)} cette semaine",
        [f'  <p class="muet"{calcule_pour(jours)}>Calculé le {instant_paris(genere_le)}.</p>',
         f'  <p class="en-bref">{e(phrases[0])}</p>']
        # Les espèces hors saison : en bas de page, avec celles qui n'ont aucun jour favorable.
        + [f"  <p>{e(p)}</p>" for p in phrases[1:] if not p.startswith("Hors saison")]
        + [f'  <p class="actions"><a class="bouton principal" href="{carte}">Voir sur la carte</a>{PARTAGER}</p>'],
        fil=f'<p class="fil"><a href="../">Départements</a> › {e(nom)}</p>')
    if (cles := chiffres(especes, resumes, jours)):
        lignes.append('  <div class="chiffres">' + "".join(
            f'<div class="chiffre"><span>{e(t)}</span><strong>{e(v)}</strong><span>{e(p)}</span></div>'
            for t, v, p in cles) + "</div>")

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
            # nofollow : ces adresses de la carte changent chaque jour, la carte a une seule adresse canonique.
            cases.append(f'<td><a class="niveau n{"x" if n is None else n}" href="{lien}" title="{e(texte)}" '
                         f'aria-label="{e(texte)}" rel="nofollow">{"–" if n == 0 else ""}</a></td>')
        corps.append(f'<tr><th scope="row">{e(x["nom"])}</th>{"".join(cases)}</tr>')
    lignes += ["  <h2>La semaine, espèce par espèce</h2>",
               '  <div class="tableau-semaine"><table class="semaine">',
               f"  <thead><tr><th></th>{colonnes}</tr></thead>",
               f"  <tbody>{''.join(corps)}</tbody>",
               "  </table></div>", LEGENDE.rstrip("\n"),
               '  <p class="muet">Un clic ouvre ce jour sur la carte.</p>']

    # Un bloc par espèce qui a au moins un jour favorable ; les autres tiennent en une phrase (le
    # tableau de la semaine les montre toutes).
    rien, hors, absentes = [], [], []
    for x in especes:
        jours_x = resumes.get(x["code"]) or []
        lien_x = f'<a href="{R}{chemin_espece(x["code"])}">{e(article(x["de"]))}</a>'
        if not jours_x:
            absentes.append(lien_x)
            continue
        if all(r["niveau"] == 0 for r in jours_x):
            hors.append(lien_x)
            continue
        if max(r["niveau"] for r in jours_x) <= 1:
            rien.append(lien_x)
            continue
        lignes.append(f'  <section class="carte-espece"><h3><a href="{R}{chemin_espece(x["code"])}">{e(x["nom"])}</a> '
                      f'<span class="latin">{e(x["latin"])}</span></h3>')
        r0 = jours_x[0]
        k = max(range(len(jours_x)), key=lambda k: (jours_x[k]["niveau"], jours_x[k]["indice_moyen"], -k))
        # Le meilleur jour, seulement s'il n'est pas aujourd'hui.
        mieux = (f" Meilleur jour : {date_longue(jours[k])} ({NIVEAUX_COURTS[jours_x[k]['niveau']]})."
                 if k > 0 and jours_x[k]["niveau"] > r0["niveau"] else "")
        lignes.append(f"  <p><strong>Aujourd'hui : {e(r0['verdict'])}.</strong> {e(' '.join(r0['phrases']))}"
                      f"{e(mieux)}</p>")
        if r0["niveau"] >= 2 and r0["communes"]:
            lignes.append("  <p>Communes les mieux placées : "
                          f"{e(enumerer([c['nom'] for c in r0['communes'][:4]]))}.</p>")
        lignes.append("  </section>")
    for liste, quoi in ((rien, "Aucun jour favorable cette semaine"), (hors, "Hors saison toute la semaine"),
                        (absentes, "Pas de forêt ni de pré calculé ici")):
        if liste:
            lignes.append(f'  <p class="muet">{quoi} : {enumerer(liste)}.</p>')

    # Les forêts publiques après les champignons de la semaine (demande du 2026-11-14).
    lignes += section_forets(forets or [], especes, jours, lieu)

    lignes += ['  <section class="faq">', "  <h2>Questions fréquentes</h2>"]
    for q, r in qr:
        lignes += [f"  <h3>{e(q)}</h3>", f"  <p>{e(r)}</p>"]
    lignes += ["  </section>"]

    if voisins:
        lignes += ["  <h2>Les départements voisins</h2>", '  <ul class="voisins">']
        for d, r in voisins:
            y = meilleure_espece(especes, r)
            n = r[y["code"]][0]["niveau"] if y else 0
            etat = f"{NIVEAUX_COURTS[n]} pour {article(y['de'])}" if n >= 2 else "rien de favorable aujourd'hui"
            lignes.append(f'    <li><a href="../{slug(d["nom"])}/">{e(d["nom"])} ({d["code"]})</a> : {e(etat)}</li>')
        lignes.append("  </ul>")
    return haut + "\n".join(lignes) + "\n" + pied(R)


def page_index(departements: list[dict], especes: list[dict], resumes: dict, jours: list[date],
               genere_le: str, contours: dict | None = None) -> str:
    """La carte des départements : l'espèce la mieux placée aujourd'hui d'abord (lisible sans
    JavaScript) ; avec, le choix de l'espèce et du jour repeint la carte et le classement."""
    haut = tete("Champignons par département : la carte des conditions de la semaine",
                "Les conditions de pousse des champignons dans chaque département de France "
                "métropolitaine, espèce par espèce, pour aujourd'hui et les sept jours suivants.",
                "../", f"{DOSSIER}/", image=image_partage("france", genere_le), large=True,
                ld=[fil_ariane([("./", NOM), (f"{DOSSIER}/", "Départements")])])
    par_numero = sorted(departements, key=lambda d: cle_departement(d["code"]))
    nat = national(especes, departements, resumes, len(jours))
    ordre = ordre_saison(especes, nat)
    defaut = ordre[0]

    def niveau(code, esp, k):
        n = _niveau(resumes.get(code, {}), esp, k)
        return "x" if n is None else str(n)

    lignes = bandeau("Départements", "Champignons par département", [
        '  <p class="chapeau">Choisissez une espèce et un jour ; un clic sur un département ouvre sa '
        "semaine.</p>",

        f'  <p class="muet"{calcule_pour(jours)}>Calculé le {instant_paris(genere_le)}.</p>'])
    if contours:
        # Les choix (cachés sans JavaScript : la carte montre alors l'espèce du moment, aujourd'hui).
        boutons = "".join(
            f'<button type="button" class="espece-dep{" hors" if meilleur_niveau(nat[x["code"]][0]) in (0, None) else ""}" '
            f'data-espece="{x["code"]}" aria-pressed="{str(x is defaut).lower()}">{icone("../", x["code"], 36)}'
            f'<span>{e(x["nom"])}</span></button>' for x in ordre)
        jours_boutons = "".join(
            f'<button type="button" data-jour="{k}" aria-pressed="{str(k == 0).lower()}">'
            f'{"Aujourd’hui" if k == 0 else "Demain" if k == 1 else f"{JOURS_COURTS[d.weekday()]} {d.day}"}</button>'
            for k, d in enumerate(jours))
        chemins = "\n".join(
            f'    <a href="{slug(d["nom"])}/" data-dep="{d["code"]}"><path class="n{niveau(d["code"], defaut["code"], 0)}" '
            f'd="{contours["traces"][d["code"]]}"><title>{e(d["nom"])} : '
            f'{e(NIVEAUX.get(int(n), "") if (n := niveau(d["code"], defaut["code"], 0)) != "x" else "rien de calculé")}'
            f"</title></path></a>"
            for d in par_numero if d["code"] in contours["traces"])
        donnees = {
            "defaut": defaut["code"],
            "ordre": [d["code"] for d in par_numero if d["code"] in contours["traces"]],
            "noms": {d["code"]: d["nom"] for d in par_numero},
            "pages": {d["code"]: f"{slug(d['nom'])}/" for d in par_numero},
            "especes": {x["code"]: {"nom": x["nom"], "de": x["de"],
                                    "niveaux": ["".join(niveau(c, x["code"], k) for c in
                                                        [d["code"] for d in par_numero if d["code"] in contours["traces"]])
                                                for k in range(len(jours))],
                                    "tete": [[nat[x["code"]][k][4], nat[x["code"]][k][3]] for k in range(len(jours))]}
                        for x in especes},
            "jours": [date_longue(d) for d in jours],
        }
        lignes += ['  <div class="choix-carte" data-carte-deps hidden>',
                   f'  <div class="especes-dep" role="group" aria-label="Espèce">{boutons}</div>',
                   f'  <div class="jours-dep" role="group" aria-label="Jour">{jours_boutons}</div>',
                   "  </div>",
                   '  <div class="carte-deps-bloc">',
                   f'  <figure class="carte-deps"><svg viewBox="0 0 {contours["largeur"]} {contours["hauteur"]}" '
                   f'role="group" aria-label="Carte des départements : {e(defaut["nom"])}, aujourd\'hui">',
                   chemins,
                   "  </svg></figure>",
                   '  <div class="carte-deps-cote">',
                   f'  <h2 id="titre-carte-deps">{e(defaut["nom"])}, {e(date_longue(jours[0]))}</h2>',
                   '  <div class="legende-semaine">',
                   '    <span><span class="pastille n4"></span>bon</span>',
                   '    <span><span class="pastille n3"></span>par endroits</span>',
                   '    <span><span class="pastille n2"></span>possible</span>',
                   '    <span><span class="pastille n1"></span>défavorable</span>',
                   '    <span><span class="pastille n0"></span>hors saison</span>',
                   "  </div>",
                   '  <div id="classement-deps">']
        lignes += _classement(defaut, nat[defaut["code"]][0], {d["code"]: d["nom"] for d in par_numero})
        lignes += ["  </div>",
                   '  <p class="muet">Survolez un département pour son verdict ; un clic ouvre sa semaine.</p>',
                   "  </div>",
                   "  </div>",
                   f'  <script type="application/json" id="niveaux-deps">{json.dumps(donnees, ensure_ascii=False)}</script>']

    # La liste par numéro, repliée : l'espèce la mieux placée de chaque département aujourd'hui.
    lignes += ["  <h2>Tous les départements</h2>",
               f'  <details class="detail"><summary>Les {len(par_numero)} départements, par numéro</summary>',
               '  <ul class="communes departements">']
    for d in par_numero:
        r = resumes.get(d["code"], {})
        meilleur = max((_niveau(r, x["code"], 0) or 0 for x in especes), default=0)
        if meilleur >= 2:
            quoi = [x["nom"].lower() for x in especes if _niveau(r, x["code"], 0) == meilleur]
            etat = f"{NIVEAUX_COURTS[meilleur]} : {enumerer(quoi)}"
        else:
            etat = "rien de favorable aujourd'hui"
        lignes.append(f'    <li><a href="{slug(d["nom"])}/">{d["code"]} – {e(d["nom"])}'
                      f'<span class="cl">{e(etat)}</span></a></li>')
    lignes += ["  </ul></details>"]
    return haut + "\n".join(lignes) + "\n" + pied("../")


def _classement(x: dict, jour: dict, noms: dict) -> list[str]:
    """Les départements aux bonnes conditions, puis par endroits, ceux qui ont le plus de forêt
    favorable d'abord (`pages.national`) ; la même liste que repeint pages.js."""
    lignes = []
    for n, quoi in ((4, "Bonnes conditions"), (3, "Par endroits")):
        if jour[n]:
            lignes.append(f"  <p><strong>{quoi}</strong> ({len(jour[n])}) : "
                          + ", ".join(f'<a href="{slug(noms.get(c, c))}/">{e(noms.get(c, c))}</a>' for c in jour[n]) + ".</p>")
    if not jour[4] and not jour[3]:
        lignes.append(f"  <p>Aucun département aux bonnes conditions pour {e(article(x['de']))} ce jour-là.</p>")
    return lignes


def ecrire(site: Path, departements: list[dict], especes: list[dict], resumes: dict,
           jours: list[date], genere_le: str, forets: dict[str, list[dict]] | None = None) -> list[str]:
    """Écrit les pages ; rend leurs chemins depuis la racine, pour le plan du site."""
    dossier = site / DOSSIER
    dossier.mkdir(parents=True, exist_ok=True)
    contours = charger_contours()
    adjacents = voisins_de(contours["traces"]) if contours else {}
    par_code = {d["code"]: d for d in departements}
    for d in departements:
        proches = [(par_code[c], resumes.get(c, {})) for c in adjacents.get(d["code"], []) if c in par_code]
        chemin = chemin_departement(d["code"], d["nom"])
        (site / chemin).mkdir(parents=True, exist_ok=True)
        (site / chemin / "index.html").write_text(
            page_departement(d, especes, resumes.get(d["code"], {}), jours, genere_le, proches,
                             (forets or {}).get(d["code"])), encoding="utf-8")
        # L'ancienne adresse (avant le 2026-11-07) renvoie à la nouvelle.
        (dossier / f"{d['code']}.html").write_text(
            renvoi(f"{slug(d['nom'])}/", chemin, f"Champignons {dans(d['code'], d['nom'])}"), encoding="utf-8")
    (dossier / "index.html").write_text(page_index(departements, especes, resumes, jours, genere_le,
                                                   contours), encoding="utf-8")
    return [f"{DOSSIER}/"] + [chemin_departement(d["code"], d["nom"]) for d in departements]
