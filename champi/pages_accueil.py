"""L'accueil (la racine du site) et « En ce moment », réécrits chaque matin par l'export.

L'accueil répond d'abord à la question du visiteur, où chercher cette semaine, puis dit comment
la carte calcule, ce que vaut sa vérification, ce qu'on peut y faire, les espèces et les
départements. La carte est sous /carte/ depuis le 2026-11-01 ; les anciens liens de la racine
(`?departement=…`, lien de groupe `#depot=…`, appli installée avant cette date) y sont renvoyés
par un script en tête de page, avant tout affichage.

Ne lit aucune donnée : reçoit les résumés (`export_france`) et la validation, rend du HTML.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .pages import (JOURS_COURTS, NIVEAUX_COURTS, NOM, article, cle_departement, date_courte, date_longue,
                    departements_de, e, entete, enumerer, instant_paris, meilleur_niveau, national,
                    ordre_saison, pct, pied, tete)
from .redaction import NBSP, nombre

# Avant tout affichage : la carte reçoit ses anciens liens, et l'appli installée quand la carte
# était à la racine (iPhone : l'adresse de départ y est figée à l'installation).
RENVOI = """
<script>
  (function () {
    var l = location, appli = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
    if (/[?&](departement|espece|jour)=/.test(l.search) || /(^#|&)(depot|jeton)=/.test(l.hash)
        || (appli && document.referrer.indexOf(l.origin + "/") !== 0)) {
      l.replace("carte/" + l.search + l.hash);
    }
  })();
</script>"""
APPLI = """
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icone-180.png">
<meta name="theme-color" content="#9c3510">"""

FONCTIONS = [
    ("La carte à 50 m", "Chaque case de forêt, du pâle au foncé, pour l'espèce et le jour choisis. "
     "Les zones protégées sont hachurées ; un clic sur une case dit pourquoi elle est notée ainsi."),
    ("Les 7 prochains jours", "La pluie déjà tombée et les prévisions : la carte dit si la pousse "
     "arrive, dure ou s'arrête, jour par jour."),
    ("Mes alertes", "Une notification quand une espèce que vous suivez devient favorable dans votre "
     "département au cours de la semaine. Pour l'instant, avec un lien de groupe."),
    ("Mes coins", "Vos trouvailles notées d'un appui long sur la carte. Elles restent sur votre "
     "appareil, ou se partagent avec vos proches par un lien privé."),
    ("Explorer les forêts", "Sans météo ni saison : les forêts qui répondent à vos critères "
     "(essences, roche, altitude, exposition, forêts publiques)."),
    ("Sans réseau", "Installée sur le téléphone, la carte s'ouvre en forêt sans réseau, avec les "
     "données de votre dernier passage en ligne."),
]


# --- Phrases ----------------------------------------------------------------------------

def _lien_dep(code: str, noms: dict, racine: str) -> str:
    return f'<a href="{racine}departements/{code}.html">{e(noms.get(code, code))}</a>'


def etat_espece(niv: list[dict], jours: list[date], noms: dict, racine: str = "") -> str:
    """L'état d'une espèce en France aujourd'hui, puis ce que la semaine change, en HTML :
    « bonnes conditions dans 41 départements (surtout Landes, Gironde et Dordogne), et jusqu'à
    52 jeudi 5 novembre »."""
    auj = niv[0]

    def tete_de(codes):
        liste = enumerer([_lien_dep(c, noms, racine) for c in codes[:3]])
        return f"surtout {liste}" if len(codes) > 3 else liste

    if auj[4]:
        t = f"bonnes conditions dans {departements_de(len(auj[4]))} ({tete_de(auj[4])})"
    elif auj[3]:
        t = f"bonnes conditions par endroits dans {departements_de(len(auj[3]))} ({tete_de(auj[3])})"
    elif auj[2]:
        t = f"pousse possible dans {departements_de(len(auj[2]))}, sans plus"
    elif auj[1]:
        t = "conditions défavorables partout aujourd'hui"
    else:
        return "hors saison partout"
    # La semaine : le premier jour de « bon » s'il n'y en a pas aujourd'hui, sinon le jour où les
    # départements en « bon » sont le plus nombreux, s'il en compte davantage.
    bons = [len(j[4]) for j in niv]
    if not bons[0]:
        k = next((k for k in range(1, len(niv)) if bons[k]), None)
        if k is not None:
            t += f" ; bonnes conditions dès {date_longue(jours[k])} dans {departements_de(bons[k])}"
    else:
        k = max(range(len(niv)), key=lambda k: (bons[k], -k))
        if bons[k] > bons[0]:
            t += f", et jusqu'à {bons[k]} {date_longue(jours[k])}"
    return t


def phase(resumes_jour: list[dict]) -> str | None:
    """« Début de saison » ou « fin de saison » quand la saison freine la plupart des
    départements où l'espèce pousse ; rien en pleine saison. `resumes_jour` : les faits du jour
    de chaque département en saison."""
    freine = [r for r in resumes_jour if r["saison"] < 0.95]
    if not resumes_jour or len(freine) * 2 <= len(resumes_jour):
        return None
    debut = sum(r["debut_saison"] for r in freine)
    return "Début de saison." if debut * 2 > len(freine) else "Fin de saison."


def ce_matin(especes: list[dict], nat: dict, phases: dict, jours: list[date], noms: dict,
             racine: str = "") -> list[str]:
    """Une ligne par espèce en saison, les mieux placées d'abord ; les espèces hors saison
    partout ferment la liste, ensemble."""
    lignes, hors = [], []
    for x in ordre_saison(especes, nat):
        if meilleur_niveau(nat[x["code"]][0]) in (0, None):
            hors.append(article(x["de"]))
            continue
        fin = f" {phases[x['code']]}" if phases.get(x["code"]) else ""
        lignes.append(f'<a href="{racine}especes/{x["code"]}.html">{e(x["nom"])}</a> : '
                      f'{etat_espece(nat[x["code"]], jours, noms, racine)}.{fin}')
    if hors:
        lignes.append(f"Hors saison partout : {e(enumerer(hors))}.")
    return lignes


def tableau_national(especes: list[dict], nat: dict, jours: list[date], racine: str = "") -> list[str]:
    """La semaine en France : par espèce et par jour, le nombre de départements aux bonnes
    conditions, au moins par endroits ; la couleur est celle du meilleur d'entre eux."""
    actuel = ' class="actuel"'
    colonnes = "".join(f'<th scope="col"{actuel if k == 0 else ""}>{JOURS_COURTS[d.weekday()]}<br>{d.day}</th>'
                       for k, d in enumerate(jours))
    corps = []
    for x in especes:
        cases = []
        for k, d in enumerate(jours):
            j = nat[x["code"]][k]
            n = meilleur_niveau(j)
            compte = len(j[4]) + len(j[3])
            texte = (f"{x['nom']}, {date_longue(d)} : hors saison partout" if n in (0, None) else
                     f"{x['nom']}, {date_longue(d)} : {departements_de(compte)} aux bonnes conditions, "
                     f"au moins par endroits" if compte else
                     f"{x['nom']}, {date_longue(d)} : {NIVEAUX_COURTS[n]} au mieux")
            contenu = "–" if n in (0, None) else str(compte) if compte else ""
            cases.append(f'<td><a class="niveau n{"x" if n is None else n}" href="{racine}carte/?espece={x["code"]}'
                         f'&amp;jour={d.isoformat()}" title="{e(texte)}" aria-label="{e(texte)}">{contenu}</a></td>')
        corps.append(f'<tr><th scope="row"><a href="{racine}especes/{x["code"]}.html">{e(x["nom"])}</a></th>'
                     f'{"".join(cases)}</tr>')
    return ['  <div class="tableau-semaine"><table class="semaine nationale">',
            f"  <thead><tr><th></th>{colonnes}</tr></thead>",
            f"  <tbody>{''.join(corps)}</tbody>",
            "  </table></div>"]


def preuve(especes: list[dict], validation: dict | None, racine: str = "") -> list[str]:
    """Ce que vaut la carte, espèce par espèce, d'après la validation publiée."""
    if not validation:
        return ["  <p>La vérification face aux observations n'est pas encore publiée.</p>"]
    v = validation["regions"]["france"]["especes"]
    testees = [x for x in especes if x["code"] in v]
    moment = [x for x in testees if v[x["code"]]["meteo"].get("ic_ecart", [0])[0] > 0]
    lieu = [x for x in testees if v[x["code"]]["habitat"].get("ic_ecart", [0])[0] > 0]
    observations = sum(v[x["code"]]["observations"] for x in testees)
    lignes = [f"  <p>Les règles de la carte ont été écrites avant de regarder les observations, puis "
              f"vérifiées sur {nombre(observations)} observations datées de toute la France (GBIF, "
              f"{validation['periode'][0]} à {validation['periode'][1]}). Pour {len(moment)} "
              f"espèce{'s' if len(moment) > 1 else ''} sur "
              f"{len(testees)}, la météo de la carte repère mieux les jours de pousse que le seul calendrier ; "
              f"pour {len(lieu)} sur {len(testees)}, ses forêts distinguent mieux les lieux que la seule "
              "présence de forêt.</p>",
              '  <div class="tableau"><table>',
              '  <thead><tr><th>Espèce</th><th>Le bon endroit</th><th>Le bon moment</th></tr></thead><tbody>']
    for x in testees:
        h, m = v[x["code"]]["habitat"], v[x["code"]]["meteo"]
        endroit = f"{pct(h['auc'])} (forêt seule : {pct(h['auc_foret'])})" if "auc" in h else "trop peu de cas"
        quand = (f"{pct(m['auc_saison'])} (calendrier seul : {pct(m['auc_calendrier'])})"
                 if "auc_saison" in m else "trop peu de cas")
        lignes.append(f'  <tr><th scope="row"><a href="{racine}especes/{x["code"]}.html">{e(x["nom"])}</a></th>'
                      f"<td>{endroit}</td><td>{quand}</td></tr>")
    lignes += ["  </tbody></table></div>",
               '  <p class="muet">Chaque chiffre compte, sur des paires tirées des observations, combien de '
               "fois la carte note plus haut le bon des deux : le lieu où l'espèce a été vue plutôt qu'un lieu "
               "où d'autres champignons l'ont été ; le jour où elle a été vue plutôt qu'un autre jour de sa "
               f"saison, au même endroit. 50{NBSP}% : le hasard. <a href=\"{racine}validation.html\">Le détail, "
               "avec les intervalles et les régions</a>.</p>"]
    return lignes


def faq(especes: list[dict]) -> list[str]:
    """Les questions fréquentes ; les fenêtres de pluie viennent des règles."""
    fenetres: dict[tuple, list[str]] = {}
    for x in especes:
        fenetres.setdefault(tuple(x["pluie_jours"]), []).append(article(x["de"]))
    pluie = "; ".join(f"du {jmax}e au {jmin}e jour avant pour {enumerer(qui)}"
                      for (jmin, jmax), qui in fenetres.items())
    qr = [
        ("Combien de temps après la pluie ?",
         "Une à trois semaines, selon l'espèce et la chaleur du sol. La carte compte la pluie tombée "
         f"{pluie}. Un sol trop froid ou trop chaud, ou une gelée, peut tout arrêter."),
        ("A-t-on le droit de cueillir partout ?",
         "Non. Les champignons appartiennent au propriétaire du terrain. En forêt publique (domaniale "
         "ou communale), une cueillette familiale est en général tolérée dans la limite des règles "
         "locales ; en forêt privée, et dans un pré, il faut l'accord du propriétaire. Un clic sur une "
         "case de la carte dit si la forêt est publique."),
        ("Combien peut-on ramasser ?",
         "Cela dépend du département et de la commune : beaucoup de préfectures limitent la cueillette "
         "par arrêté (quantité par personne et par jour, jours autorisés). Sans autorisation du "
         "propriétaire, ramasser est une contravention en dessous de 10 litres, un délit au-delà. "
         "Renseignez-vous en mairie, en préfecture ou auprès de l'ONF."),
        ("La carte dit-elle ce qui se mange ?",
         "Non. Elle dit où les conditions sont réunies pour qu'une espèce pousse, jamais ce que vous "
         "avez trouvé. Toutes les espèces de la carte ont des sosies toxiques : faites contrôler votre "
         "récolte par un pharmacien ou une société mycologique."),
    ]
    return [f"  <details class=\"question\"><summary>{e(q)}</summary><p>{e(r)}</p></details>" for q, r in qr]


# --- Pages ------------------------------------------------------------------------------

def page_accueil(departements: list[dict], especes: list[dict], nat: dict, phases: dict, jours: list[date],
                 validation: dict | None, genere_le: str) -> str:
    noms = {d["code"]: d["nom"] for d in departements}
    haut = tete(f"{NOM} : où chercher cette semaine",
                "Les forêts de France où les conditions sont favorables aux cèpes, girolles, trompettes, "
                "pieds-de-mouton, lactaires délicieux et morilles, aujourd'hui et pour les sept prochains "
                "jours, case par case de 50 m, d'après la pluie, la température du sol et la saison.",
                "", "", plus=APPLI + RENVOI)
    lignes = [entete("", ("carte/", "La carte"), ("en-ce-moment.html", "En ce moment"),
                     ("especes/", "Les espèces"), ("departements/", "Par département")),
              '  <div class="accueil">',
              "  <h1>Où chercher les champignons cette semaine</h1>",
              '  <p class="chapeau">Les forêts de France case par case, selon la pluie des dernières '
              "semaines et la météo des 7 prochains jours.</p>",
              '  <p class="actions"><a class="bouton principal" href="carte/">Voir la carte</a>'
              '<a class="bouton" href="carte/?autour">Autour de moi</a>'
              '<a class="bouton" href="departements/" id="mon-departement">Mon département</a></p>',
              "  <h2>Ce matin</h2>",
              f'  <p class="muet">Calculé le {instant_paris(genere_le)}, sur les forêts de chaque département.</p>',
              '  <ul class="ce-matin">']
    lignes += [f"    <li>{x}</li>" for x in ce_matin(especes, nat, phases, jours, noms)]
    lignes += ["  </ul>",
               '  <p><a href="en-ce-moment.html">Toute la semaine en France, espèce par espèce</a></p>',
               "  <h2>Comment ça marche</h2>",
               '  <ol class="etapes">',
               "    <li><strong>La forêt.</strong> Pour chaque case de 50 m : l'essence des arbres, la "
               "roche ou le pH du sol, l'altitude, la pente et l'exposition. Chaque espèce a ses "
               "préférences.</li>",
               "    <li><strong>La météo.</strong> Chaque matin, la pluie des dernières semaines, la "
               "température du sol et le gel, d'après les modèles de Météo-France et du Centre européen, "
               "puis leurs prévisions pour 7 jours.</li>",
               "    <li><strong>La saison.</strong> Chaque espèce a sa période, plus précoce au sud au "
               "printemps et plus tardive à l'automne.</li>",
               "  </ol>",
               "  <p>L'indice multiplie les trois : un seul facteur contraire (le gel, la sécheresse, la "
               "saison) suffit à l'éteindre. Il dit où les conditions sont réunies, pas ce que vous "
               'trouverez. <a href="methode.html">La méthode en détail</a>.</p>',
               "  <h2>Ce que vaut la carte</h2>"]
    lignes += preuve(especes, validation)
    lignes += ["  <p>Ce qu'elle ne sait pas faire : voir chaque arbre (les cartes forestières décrivent "
               "des peuplements, souvent « en mélange »), l'humus, les coupes récentes ou les années "
               "sans champignons, ni dire ce qui se mange.</p>",
               "  <h2>Ce que vous pouvez faire</h2>",
               '  <ul class="fonctions">']
    lignes += [f"    <li><strong>{e(t)}</strong> {e(d)}</li>" for t, d in FONCTIONS]
    lignes += ["  </ul>",
               '  <p><a class="bouton principal" href="carte/">Ouvrir la carte</a></p>',
               "  <h2>Les espèces</h2>",
               '  <ul class="especes">']
    for x in ordre_saison(especes, nat):
        j0 = nat[x["code"]][0]
        n = meilleur_niveau(j0)
        etat = ("hors saison" if n in (0, None) else "défavorable partout" if n == 1 else
                f"{NIVEAUX_COURTS[n]} dans {departements_de(len(j0[n]))}")
        lignes.append(f'    <li><a href="especes/{x["code"]}.html"><strong>{e(x["nom"])}</strong> '
                      f'<span class="latin">{e(x["latin"])}</span><span class="cl">{e(etat)}</span></a></li>')
    lignes += ["  </ul>",
               "  <h2>Par département</h2>",
               '  <ul class="liste-departements">']
    lignes += [f'    <li><a href="departements/{d["code"]}.html" data-departement="{d["code"]}">'
               f'{d["code"]} {e(d["nom"])}</a></li>'
               for d in sorted(departements, key=lambda d: cle_departement(d["code"]))]
    lignes += ["  </ul>",
               "  <h2>Questions fréquentes</h2>"]
    lignes += faq(especes)
    lignes += ["  </div>"]
    return haut + "\n".join(lignes) + "\n" + pied("")


def page_en_ce_moment(departements: list[dict], especes: list[dict], nat: dict, phases: dict,
                      jours: list[date], genere_le: str) -> str:
    noms = {d["code"]: d["nom"] for d in departements}
    haut = tete("Champignons en ce moment en France : les conditions de la semaine",
                "Où les conditions sont bonnes pour les cèpes, girolles, trompettes, pieds-de-mouton, "
                "lactaires délicieux et morilles en ce moment, département par département, pour "
                "aujourd'hui et les sept jours suivants.", "", "en-ce-moment.html")
    lignes = [entete("", ("carte/", "La carte"), ("especes/", "Les espèces"), ("departements/", "Par département")),
              "  <h1>Les champignons en ce moment</h1>",
              f'  <p class="muet">Calculé le {instant_paris(genere_le)}, pour aujourd\'hui et les sept jours '
              "suivants, sur les forêts de chaque département.</p>",
              '  <ul class="ce-matin">']
    lignes += [f"    <li>{x}</li>" for x in ce_matin(especes, nat, phases, jours, noms)]
    lignes += ["  </ul>",
               "  <h2>La semaine en France</h2>"]
    lignes += tableau_national(especes, nat, jours)
    lignes += ['  <p class="muet">Dans chaque case, le nombre de départements aux bonnes conditions, au '
               "moins par endroits ; sa couleur, celle du mieux placé d'entre eux (même échelle que les "
               "pages des départements). Un clic ouvre la carte de l'espèce ce jour-là. Ci-dessous, "
               "aujourd'hui : les départements qui ont le plus de forêt aux bonnes conditions d'abord.</p>"]
    for x in ordre_saison(especes, nat):
        j0 = nat[x["code"]][0]
        lignes.append(f'  <section class="carte-espece" id="{x["code"]}"><h2>{e(x["nom"])} '
                      f'<span class="latin">{e(x["latin"])}</span></h2>')
        if meilleur_niveau(j0) in (0, None):
            debut, _, _, fin = x["saison"]
            lignes.append(f"  <p>Hors saison partout aujourd'hui : la saison {e(x['de'])} court en gros du "
                          f"{date_courte(debut)} au {date_courte(fin)}.</p>")
        else:
            for n, quoi in ((4, "Bonnes conditions"), (3, "Bonnes conditions par endroits")):
                if j0[n]:
                    lignes.append(f"  <p><strong>{quoi}</strong> ({departements_de(len(j0[n]))}) : "
                                  f"{', '.join(_lien_dep(c, noms, '') for c in j0[n])}.</p>")
            if not j0[4] and not j0[3]:
                t = etat_espece(nat[x["code"]], jours, noms)
                lignes.append(f"  <p>{t[:1].upper()}{t[1:]}.</p>")
        lignes.append(f'  <p><a href="carte/?espece={x["code"]}">{e(x["nom"])} sur la carte</a> · '
                      f'<a href="especes/{x["code"]}.html">Où et quand le chercher</a></p></section>')
    return haut + "\n".join(lignes) + "\n" + pied("")


def phases_du_jour(especes: list[dict], departements: list[dict], resumes: dict) -> dict:
    """La phase de saison de chaque espèce aujourd'hui, sur les départements où elle est en saison."""
    sortie = {}
    for x in especes:
        jour0 = [r[0] for d in departements if (r := (resumes.get(d["code"]) or {}).get(x["code"]))
                 and r[0]["niveau"] >= 1]
        sortie[x["code"]] = phase(jour0)
    return sortie


def ecrire(site: Path, departements: list[dict], especes: list[dict], resumes: dict, jours: list[date],
           genere_le: str, validation: dict | None) -> list[str]:
    """Écrit l'accueil et « en ce moment » ; rend leurs chemins depuis la racine."""
    nat = national(especes, departements, resumes, len(jours))
    phases = phases_du_jour(especes, departements, resumes)
    (site / "index.html").write_text(
        page_accueil(departements, especes, nat, phases, jours, validation, genere_le), encoding="utf-8")
    (site / "en-ce-moment.html").write_text(
        page_en_ce_moment(departements, especes, nat, phases, jours, genere_le), encoding="utf-8")
    return ["", "en-ce-moment.html"]
