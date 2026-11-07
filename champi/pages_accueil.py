"""L'accueil (la racine du site) et « En ce moment », réécrits chaque matin par l'export.

L'accueil répond d'abord à la question du visiteur, où chercher cette semaine, puis dit comment
la carte calcule, ce que vaut sa vérification, ce qu'on peut y faire, les espèces et les
départements. La carte est sous /carte/ depuis le 2026-11-01 ; les anciens liens de la racine
(`?departement=…`, lien de groupe `#depot=…`, appli installée avant cette date) y sont renvoyés
par un script en tête de page, avant tout affichage.

Ne lit aucune donnée : reçoit les résumés (`export_france`) et la validation, rend du HTML.
"""
from __future__ import annotations

import json
from datetime import date
from math import cos, radians
from pathlib import Path

from .carte_departements import cadre_une, charger as charger_contours
from .config import PAS_FIN
from .pages import (JOURS_COURTS, NIVEAUX_COURTS, NOM, PARTAGER, article, calcule_pour, cle_departement,
                    date_courte, date_longue, departements_de, e, enumerer, habituel, icone, image_partage,
                    instant_paris,
                    meilleur_niveau, national, noms_especes, ordre_saison, pct, pied, tete)
from .partage import LARGEUR_UNE
from .photos import charger as charger_photos
from .redaction import NBSP, NIVEAUX, nombre

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

# Petits dessins au trait (24 × 24, couleur du texte) des fonctions et des étapes.
TRAITS = {
    "carte": '<path d="M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2z"/><path d="M9 4v14M15 6v14"/>',
    "semaine": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>'
               '<path d="M7 14h2M11 14h2M15 14h2M7 17h2M11 17h2"/>',
    "alerte": '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>',
    "coin": '<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    "explorer": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/>'
                '<circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "hors_ligne": '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M12 7v7M9 11l3 3 3-3M11 18h2"/>',
    "foret": '<path d="M12 3l5 7h-3l4 6H6l4-6H7z"/><path d="M12 16v5"/>',
    "meteo": '<path d="M7 15a4 4 0 0 1 .5-8A5 5 0 0 1 17 8a3.5 3.5 0 0 1 0 7z"/><path d="M8 18l-1 3M12 18l-1 3M16 18l-1 3"/>',
    "saison": '<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1'
              'M4.9 19.1L7 17M17 7l2.1-2.1"/>',
}


def trait(nom: str) -> str:
    return (f'<svg class="trait" viewBox="0 0 24 24" width="28" height="28" aria-hidden="true" fill="none" '
            f'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
            f"{TRAITS[nom]}</svg>")


FONCTIONS = [
    ("carte", "La carte à 250 m", "Chaque zone de forêt, du pâle au foncé, pour l'espèce et le jour choisis. "
     "Les zones protégées sont hachurées ; un clic sur une zone dit pourquoi elle est notée ainsi."),
    ("semaine", "Les 7 prochains jours", "La pluie déjà tombée et les prévisions : la carte dit si la pousse "
     "arrive, dure ou s'arrête, jour par jour."),
    ("alerte", "Mes alertes", "Une notification quand une espèce que vous suivez devient favorable dans votre "
     "département au cours de la semaine. Pour l'instant, avec un lien de groupe."),
    ("coin", "Mes coins", "Vos trouvailles notées d'un appui long sur la carte. Elles restent sur votre "
     "appareil, ou se partagent avec vos proches par un lien privé."),
    ("explorer", "Explorer les forêts", "Sans météo ni saison : les forêts qui répondent à vos critères "
     "(essences, roche, altitude, exposition, forêts publiques)."),
    ("hors_ligne", "Sans réseau", "Installée sur le téléphone, la carte s'ouvre en forêt sans réseau, avec les "
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


def en_bref(especes: list[dict], nat: dict) -> str:
    """La réponse du jour en une phrase : les trois espèces aux bonnes conditions dans le plus de
    départements, sinon la mieux placée, sinon la saison."""
    bonnes = sorted(((len(nat[x["code"]][0][4]), k, x) for k, x in enumerate(especes) if nat[x["code"]][0][4]),
                    key=lambda t: (-t[0], t[1]))[:3]
    if bonnes:
        morceaux = [f'{article(x["de"])} dans {departements_de(n)}' if k == 0 else f'{article(x["de"])} dans {n}'
                    for k, (n, _, x) in enumerate(bonnes)]
        return f"Aujourd'hui, bonnes conditions pour {enumerer(morceaux)}."
    meilleure = ordre_saison(especes, nat)[0]
    n = meilleur_niveau(nat[meilleure["code"]][0])
    if n in (0, None):
        return "Aujourd'hui, toutes les espèces de la carte sont hors saison."
    return (f"Aujourd'hui, aucune espèce n'est en bonnes conditions ; au mieux, {NIVEAUX_COURTS[n]} "
            f"pour {article(meilleure['de'])}.")


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
    # Chaque compte sur les espèces que ce test a pu juger : assez de cas datés pour le moment ;
    # pour le lieu, assez de lieux précis, et une carte fine (pas les espèces des prés).
    au_moment = [x for x in testees if "auc_saison" in v[x["code"]]["meteo"]]
    au_lieu = [x for x in testees if "auc" in v[x["code"]]["habitat"]]
    moment = [x for x in au_moment if v[x["code"]]["meteo"]["ic_ecart"][0] > 0]
    lieu = [x for x in au_lieu if v[x["code"]]["habitat"]["ic_ecart"][0] > 0]
    observations = sum(v[x["code"]]["observations"] for x in testees)
    lignes = [f"  <p>Les règles de la carte ont été écrites avant de regarder les observations, puis "
              f"vérifiées sur {nombre(observations)} observations datées de toute la France (GBIF, "
              f"{validation['periode'][0]} à {validation['periode'][1]}). Pour {len(moment)} "
              f"espèce{'s' if len(moment) > 1 else ''} sur "
              f"{len(au_moment)}, la météo de la carte repère mieux les jours de pousse que le seul calendrier ; "
              f"pour {len(lieu)} sur {len(au_lieu)} (les espèces de forêt aux lieux assez précis), ses forêts "
              "distinguent mieux les lieux que la seule présence de forêt.</p>",
              '  <div class="tableau"><table>',
              '  <thead><tr><th>Espèce</th><th>Le bon endroit</th><th>Le bon moment</th></tr></thead><tbody>']
    for x in testees:
        h, m = v[x["code"]]["habitat"], v[x["code"]]["meteo"]
        endroit = (f"{pct(h['auc'])} (forêt seule : {pct(h['auc_foret'])})" if "auc" in h
                   else "pas de carte des prés" if h.get("sans_carte") else "trop peu de cas")
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


# --- La carte de la une -----------------------------------------------------------------

UNE_MAX = 6                      # boutons d'espèce de la une, au plus (« Toutes » en plus)


def especes_de_la_une(especes: list[dict], nat: dict) -> list[dict]:
    """Les espèces proposées sur la carte de la une : celles aux bonnes conditions quelque part
    aujourd'hui, au moins par endroits, les mieux placées d'abord ; à défaut, les trois premières
    en saison ; aucune si tout est hors saison."""
    en_saison = [x for x in ordre_saison(especes, nat) if meilleur_niveau(nat[x["code"]][0]) not in (0, None)]
    return [x for x in en_saison if meilleur_niveau(nat[x["code"]][0]) >= 3][:UNE_MAX] or en_saison[:3]


def niveaux_du_jour(nat_espece: list[dict]) -> dict[str, int]:
    """Le niveau de chaque département aujourd'hui, pour une espèce."""
    return {c: n for n, codes in nat_espece[0].items() for c in codes}


# Le côté d'un carré de la carte de la une, m Mercator : celui de « Que chercher ici ? »
# (`export_france`, APERCU × VUE cases de 50 m ; test).
CARRE_UNE_M = PAS_FIN * 16 * 8


def carre_km() -> int:
    """Le côté au sol d'un carré de la carte de la une, en km arrondi, au milieu de la France."""
    return round(CARRE_UNE_M * cos(radians(46.5)) / 1000)


def une_carte(especes: list[dict], nat: dict, departements: list[dict], genere_le: str,
              contours: dict | None) -> list[str]:
    """La carte de France de la une : l'espèce la mieux placée d'abord (lisible sans JavaScript),
    des boutons pour en voir une autre ou toutes, et les contours des départements par-dessus,
    chacun menant à la carte de l'espèce sur ce département. Les images : `partage.carte_cadre`."""
    choix = especes_de_la_une(especes, nat)
    km = f"{carre_km()}{NBSP}km"
    avec_contours = bool(contours and "cadre" in contours)
    clic = " Un clic sur un département l'ouvre sur la carte." if avec_contours else ""
    par_numero = sorted(departements, key=lambda d: cle_departement(d["code"]))
    ordre = [d["code"] for d in par_numero if avec_contours and d["code"] in contours["traces"]]
    noms = {d["code"]: d["nom"] for d in par_numero}

    def vue(x: dict | None) -> dict:
        if x is None:                          # toutes espèces : le meilleur niveau de chaque département
            niv: dict[str, int] = {}
            for y in especes:
                for c, n in niveaux_du_jour(nat[y["code"]]).items():
                    niv[c] = max(n, niv.get(c, 0))
            return {"espece": "", "image": image_partage("carte-france", genere_le),
                    "alt": f"Carte de France du jour, toutes espèces : chaque carré de {km} au meilleur verdict "
                           "de ses espèces, de « hors saison » à « bon »",
                    "legende": f"Aujourd'hui, toutes espèces : le meilleur verdict de chaque carré de {km}.{clic}",
                    "niveaux": "".join(str(niv[c]) if c in niv else "x" for c in ordre)}
        niv = niveaux_du_jour(nat[x["code"]])
        pre = x.get("milieu") == "pre"
        return {"espece": x["code"], "image": image_partage(f"carte-france-{x['code']}", genere_le),
                "alt": f"Carte de France du jour pour {article(x['de'])} : chaque carré de {km} au verdict de ses "
                       f"{'prés' if pre else 'forêts'}, de « hors saison » à « bon »",
                "legende": (f"Aujourd'hui, {article(x['de'])} : le verdict des {'prés' if pre else 'forêts'} de chaque "
                            f"carré de {km}, comme pour les départements"
                            + (", jamais un pré." if pre else ".") + clic),
                "niveaux": "".join(str(niv[c]) if c in niv else "x" for c in ordre)}

    vues = {x["code"]: vue(x) for x in choix}
    vues["toutes"] = vue(None)
    defaut = choix[0]["code"] if choix else "toutes"
    v = vues[defaut]
    suffixe = f"espece={v['espece']}" if v["espece"] else ""
    carte = f"carte/?{suffixe}" if suffixe else "carte/"
    lignes = ['  <figure class="une-carte">']
    if choix:
        boutons = "".join(
            f'<button type="button" data-une="{x["code"]}" aria-pressed="{str(x["code"] == defaut).lower()}">'
            f'{icone("", x["code"], 24)}<span>{e(x["nom"])}</span></button>' for x in choix)
        boutons += (f'<button type="button" data-une="toutes" aria-pressed="{str(defaut == "toutes").lower()}">'
                    "<span>Toutes</span></button>")
        # Cachés sans JavaScript : la carte montre alors l'espèce la mieux placée.
        lignes.append(f'  <div class="especes-dep une-especes" role="group" aria-label="Espèce de la carte" '
                      f'data-une-especes hidden>{boutons}</div>')
    vue_box = cadre_une(contours)[0] if avec_contours else [0, 0, 1, 1]
    lignes.append(f'  <div class="une-carte-cadre"><a class="une-fond" href="{carte}"><img src="{v["image"]}" '
                  f'alt="{e(v["alt"])}" width="{LARGEUR_UNE}" height="{round(LARGEUR_UNE * vue_box[3] / vue_box[2])}">'
                  "</a>")
    if avec_contours:
        chemins = "".join(
            f'<a href="carte/?departement={c}{"&amp;" + suffixe if suffixe else ""}" data-dep="{c}">'
            f'<path d="{contours["traces"][c]}"><title>{e(noms[c])} : '
            f'{e(NIVEAUX[int(n)].lower() if (n := v["niveaux"][k]) != "x" else "rien de calculé")}</title></path></a>'
            for k, c in enumerate(ordre))
        lignes.append(f'  <svg viewBox="{" ".join(f"{v:g}" for v in vue_box)}" role="group" '
                      f'aria-label="Départements">{chemins}</svg>')
    lignes.append("  </div>")
    # Les verdicts, comme la carte des départements ; un carré blanc n'a pas assez de forêt.
    lignes += ['  <div class="legende-semaine une-legende">'
               + "".join(f'<span><span class="pastille n{n}"></span>{mot}</span>' for n, mot in
                         ((4, "bon"), (3, "par endroits"), (2, "possible"), (1, "défavorable"), (0, "hors saison")))
               + "</div>",
               f"  <figcaption>{e(v['legende'])}</figcaption>",
               "  </figure>"]
    if choix:
        donnees = {"defaut": defaut, "ordre": ordre, "noms": {c: noms[c] for c in ordre}, "vues": vues}
        lignes.append(f'  <script type="application/json" id="une-donnees">{json.dumps(donnees, ensure_ascii=False)}'
                      "</script>")
    return lignes


# --- Pages ------------------------------------------------------------------------------

def page_accueil(departements: list[dict], especes: list[dict], nat: dict, phases: dict, jours: list[date],
                 validation: dict | None, genere_le: str, photos: dict | None = None,
                 contours: dict | None = None) -> str:
    noms = {d["code"]: d["nom"] for d in departements}
    photos = photos or {}
    haut = tete(f"{NOM} : où chercher cette semaine",
                f"Où les conditions sont favorables aux champignons ({noms_especes(especes)}), aujourd'hui "
                "et pour les sept prochains jours, forêt par forêt, d'après la pluie, la température du sol "
                "et la saison.",
                "", "", image=image_partage("france", genere_le), plus=APPLI + RENVOI, large=True)
    par_numero = sorted(departements, key=lambda d: cle_departement(d["code"]))
    choix = "".join(f'<option value="{d["code"]}">{d["code"]} – {e(d["nom"])}</option>' for d in par_numero)

    # 1. La réponse du jour, la carte de France, et les trois chemins : la carte, autour de soi,
    #    son département (un choix ; sans JavaScript, la liste des départements).
    lignes = ['  <div class="accueil">',
              '  <section class="une">',
              '  <div class="une-texte">',
              f'  <p class="sur-titre">Ce matin, {date_longue(jours[0])}</p>',
              "  <h1>Où chercher les champignons cette semaine</h1>",
              '  <p class="chapeau">Les forêts de France case par case, et les prés commune par commune, selon '
              "la pluie des dernières semaines et la météo des 7 prochains jours.</p>",
              f'  <p class="en-bref">{e(en_bref(especes, nat))}</p>',
              '  <p class="actions"><a class="bouton principal" href="carte/" data-une-lien>Voir la carte</a>'
              '<a class="bouton" href="carte/?autour" data-une-lien>Autour de moi</a>'
              '<a class="bouton" href="departements/" id="mon-departement">Mon département</a></p>',
              '  <form class="aller-departement" action="departements/" data-aller-departement>',
              '  <label for="aller-departement">Un département</label>',
              f'  <select id="aller-departement" name="d"><option value="">Choisir…</option>{choix}</select>',
              '  <button type="submit" class="bouton">Voir</button>',
              "  </form>",
              "  </div>"]
    lignes += une_carte(especes, nat, departements, genere_le, contours)
    lignes.append("  </section>")

    # 2. Les espèces en saison, illustrées : leur état aujourd'hui, ce que la semaine change.
    en_saison = [x for x in ordre_saison(especes, nat) if meilleur_niveau(nat[x["code"]][0]) not in (0, None)]
    hors = [article(x["de"]) for x in especes if x not in en_saison]
    lignes += ['  <section class="bloc">',
               "  <h2>En saison cette semaine</h2>",
               f'  <p class="muet"{calcule_pour(jours)}>Calculé le {instant_paris(genere_le)}, sur les forêts '
               "(les prés pour les espèces "
               "des champs) de chaque département. Les mieux placées d'abord.</p>",
               '  <ul class="saison-cartes">']
    for x in en_saison:
        j0 = nat[x["code"]][0]
        n = meilleur_niveau(j0)
        etiquette = ("défavorable partout" if n == 1 else f"{NIVEAUX_COURTS[n]} dans {departements_de(len(j0[n]))}")
        t = etat_espece(nat[x["code"]], jours, noms)
        photo = (f'<img src="img/especes/{x["code"]}.jpg" alt="" width="480" height="360" loading="lazy">'
                 if x["code"] in photos else icone("", x["code"], 96))
        tags = [f'<span class="badge n{n}">{e(etiquette)}</span>']
        if x.get("milieu") == "pre":
            tags.append('<span class="badge">des prés</span>')
        if phases.get(x["code"]):
            tags.append(f'<span class="badge">{e(phases[x["code"]].rstrip("."))}</span>')
        h = habituel(x)
        lignes.append(f'    <li><a class="saison-photo" href="especes/{x["code"]}.html" tabindex="-1">{photo}</a>'
                      f'<div><h3><a href="especes/{x["code"]}.html">{e(x["nom"])}</a></h3>'
                      f'<p class="badges">{"".join(tags)}</p>'
                      f'<p class="etat">{t[:1].upper()}{t[1:]}.</p>'
                      + (f'<p class="habituel">{e(h)}.</p>' if h else "") + "</div></li>")
    lignes.append("  </ul>")
    if hors:
        lignes.append(f'  <p class="muet">Hors saison partout : {e(enumerer(hors))}.</p>')
    lignes += [f'  <p class="actions"><a class="bouton" href="especes/">Toutes les espèces et leur calendrier</a>'
               f"{PARTAGER}</p>",
               "  </section>"]

    # 3. La semaine en France, d'un coup d'œil.
    lignes += ['  <section class="bloc">',
               "  <h2>La semaine en France</h2>",
               '  <p class="muet">Dans chaque case, le nombre de départements aux bonnes conditions, au moins par '
               "endroits ; sa couleur, celle du mieux placé. Un clic ouvre la carte de l'espèce ce jour-là.</p>"]
    lignes += tableau_national(especes, nat, jours)
    lignes += ['  <p><a href="en-ce-moment.html">Les départements, espèce par espèce</a></p>',
               "  </section>"]

    # 4. Comment ça marche, et ce qu'on peut y faire.
    lignes += ['  <section class="bloc">',
               "  <h2>Comment ça marche</h2>",
               '  <ol class="etapes-cartes">',
               f"    <li>{trait('foret')}<strong>La forêt</strong> Pour chaque case de 50 m : l'essence des "
               "arbres, la roche ou le pH du sol, l'altitude, la pente et l'exposition. Chaque espèce a ses "
               "préférences ; la carte réunit les cases en zones de 250 m.</li>",
               f"    <li>{trait('meteo')}<strong>La météo</strong> Chaque matin, la pluie des dernières semaines, "
               "la température du sol et le gel, d'après Météo-France et le Centre européen, puis leurs "
               "prévisions pour 7 jours.</li>",
               f"    <li>{trait('saison')}<strong>La saison</strong> Chaque espèce a sa période, plus précoce au "
               "sud au printemps et plus tardive à l'automne.</li>",
               "  </ol>",
               "  <p>L'indice multiplie les trois : un seul facteur contraire (le gel, la sécheresse, la "
               "saison) suffit à l'éteindre. Il dit où les conditions sont réunies, pas ce que vous "
               'trouverez. <a href="methode.html">La méthode en détail</a>.</p>',
               "  <h2>Ce que vous pouvez faire</h2>",
               '  <ul class="fonctions">']
    lignes += [f"    <li>{trait(i)}<strong>{e(t)}</strong> {e(d)}</li>" for i, t, d in FONCTIONS]
    lignes += ["  </ul>",
               '  <p><a class="bouton principal" href="carte/">Ouvrir la carte</a></p>',
               "  </section>"]

    # 5. Ce que vaut la carte : la phrase ; le tableau sur demande.
    preuves = preuve(especes, validation)
    lignes += ['  <section class="bloc">', "  <h2>Ce que vaut la carte</h2>", preuves[0]]
    if len(preuves) > 1:
        lignes += ['  <details class="detail"><summary>Le détail, espèce par espèce</summary>'] + preuves[1:] + \
                  ["  </details>"]
    lignes += ["  <p>Ce qu'elle ne sait pas faire : voir chaque arbre (les cartes forestières décrivent "
               "des peuplements, souvent « en mélange »), l'humus, les coupes récentes ou les années "
               "sans champignons, ni dire ce qui se mange.</p>",
               "  </section>"]

    # 6. Les départements (la liste, repliée : le choix du haut suffit le plus souvent), les questions.
    lignes += ['  <section class="bloc">',
               "  <h2>Par département</h2>",
               f'  <details class="detail"><summary>Les {len(departements)} départements</summary>',
               '  <ul class="liste-departements">']
    lignes += [f'    <li><a href="departements/{d["code"]}.html" data-departement="{d["code"]}">'
               f'{d["code"]} {e(d["nom"])}</a></li>' for d in par_numero]
    lignes += ["  </ul></details>",
               "  <h2>Questions fréquentes</h2>"]
    lignes += faq(especes)
    lignes += ["  </section>", "  </div>"]
    return haut + "\n".join(lignes) + "\n" + pied("")


def page_en_ce_moment(departements: list[dict], especes: list[dict], nat: dict, phases: dict,
                      jours: list[date], genere_le: str) -> str:
    noms = {d["code"]: d["nom"] for d in departements}
    haut = tete("Champignons en ce moment en France : les conditions de la semaine",
                f"Où les conditions sont bonnes en ce moment, département par département, pour "
                f"aujourd'hui et les sept jours suivants : {noms_especes(especes)}.", "", "en-ce-moment.html",
                image=image_partage("france", genere_le))
    lignes = ["  <h1>Les champignons en ce moment</h1>",
              f'  <p class="muet"{calcule_pour(jours)}>Calculé le {instant_paris(genere_le)}, pour aujourd\'hui '
              "et les sept jours "
              "suivants, sur les forêts de chaque département.</p>",
              '  <ul class="ce-matin">']
    lignes += [f"    <li>{x}</li>" for x in ce_matin(especes, nat, phases, jours, noms)]
    lignes += ["  </ul>",
               f'  <p class="actions"><a class="bouton principal" href="carte/">Voir la carte</a>{PARTAGER}</p>',
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
        page_accueil(departements, especes, nat, phases, jours, validation, genere_le, charger_photos(),
                     charger_contours()),
        encoding="utf-8")
    (site / "en-ce-moment.html").write_text(
        page_en_ce_moment(departements, especes, nat, phases, jours, genere_le), encoding="utf-8")
    return ["", "en-ce-moment.html"]
