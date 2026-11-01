"""Fiches espèces (`site/especes/`), réécrites chaque matin par l'export : où et quand chercher,
à quoi l'espèce ressemble (jamais assez pour l'identifier : la page le dit d'abord), ce que la
vérification dit de la carte pour elle, et où les conditions sont bonnes aujourd'hui.

Tout vient des règles (`especes.en_json`) et de la validation : aucune valeur en dur ici, pour
qu'un seuil changé dans `especes.py` ne laisse jamais une fiche en retard.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .pages import (MOIS_COURTS, NIVEAUX_COURTS, PARTAGER, calendrier_mois, credit_photo, date_courte,
                    departements_de, e, icone, image_partage, instant_paris, meilleur_niveau, mois_saison,
                    national, noms_especes, ordre_saison, pct, pied, tete)
from .photos import charger as charger_photos
from .pages_accueil import etat_espece
from .prairies import NOMS_MILIEUX
from .redaction import NBSP, fiabilite, lieux, nombre

DOSSIER = "especes"


def fr(x: float) -> str:
    """6.5 → « 6,5 », 4.0 → « 4 »."""
    return nombre(x, 0 if float(x).is_integer() else 1)


def pronom(x: dict) -> str:
    feminin = x.get("feminin")
    return "elle" if (x["de"].startswith("de la") if feminin is None else feminin) else "il"


def essences_entre(x: dict, noms: dict, mini: float, maxi: float, cle: str = "essences") -> str:
    """Les essences (ou les milieux des prés) dont l'affinité est dans [mini, maxi[, les plus
    favorables d'abord."""
    retenues = sorted(((v, int(k)) for k, v in x[cle].items() if int(k) > 0 and mini <= v < maxi),
                      key=lambda t: (-t[0], t[1]))
    return ", ".join(noms[k].lower() for _, k in retenues)


def sol(x: dict, roches: dict) -> str:
    if x["sol_ph"]:
        return (f"Sol acide de préférence, pH de {fr(x['ph'][1])} à {fr(x['ph'][2])} au mieux : pour cette "
                "espèce, la carte lit le pH du sol (SoilGrids) plutôt que la roche, là où il est connu.")
    groupes: dict[str, list[str]] = {"favorable": [], "possible": [], "plus rare": []}
    for k in sorted(x["roches"], key=int):
        if int(k) > 0:
            a = x["roches"][k]
            groupes["favorable" if a >= 0.9 else "possible" if a >= 0.5 else "plus rare"].append(roches[int(k)].lower())
    return "Roche " + " ; ".join(f"{mot} : {', '.join(qui)}" for mot, qui in groupes.items() if qui) + "."


def ce_que_la_carte_en_sait(x: dict, v: dict | None) -> list[str]:
    if not v:
        return ["  <p>Pas encore vérifiée face aux observations.</p>"]
    h, m = v["habitat"], v["meteo"]
    lignes = []
    if x.get("milieu") == "pre":
        lignes.append("  <p><strong>Le bon endroit.</strong> Pas vérifié : la carte ne note pas les prés un "
                      "par un, seulement les départements et les communes.</p>")
    elif "auc" in h:
        bas, haut = h["ic_ecart"]
        verdict = ("Ses forêts font mieux que la seule présence de forêt." if bas > 0 else
                   "Ses forêts font moins bien que la seule présence de forêt." if haut < 0 else
                   "Ses forêts ne font pas nettement mieux que la seule présence de forêt.")
        lignes.append(f"  <p><strong>Le bon endroit.</strong> Sur {nombre(h['n'])} lieux d'observation précis, "
                      f"la carte note plus haut le lieu de l'espèce que celui d'un autre champignon dans "
                      f"{pct(h['auc'])} des paires (la seule présence de forêt : {pct(h['auc_foret'])} ; le "
                      f"hasard : 50{NBSP}%). {verdict}</p>")
    else:
        lignes.append("  <p><strong>Le bon endroit.</strong> Trop peu de lieux d'observation précis pour "
                      "conclure.</p>")
    chiffres = (f" Sur {nombre(m['n'])} observations datées, {pct(m['auc_saison'])} des paires de jours "
                f"bien triées (le seul calendrier : {pct(m['auc_calendrier'])}).") if "auc_saison" in m else ""
    lignes.append(f"  <p><strong>Le bon moment.</strong> {e(fiabilite(m)['texte'])}{chiffres}</p>")
    return lignes


def figure_photo(x: dict, photo: dict | None, racine: str = "../", classe: str = "photo",
                 paresseuse: bool = True, credit: bool = True) -> str:
    """La photo de l'espèce et son crédit ; son dessin quand elle n'en a pas. Les photos du haut de
    page se chargent tout de suite, les autres à l'approche. Sans crédit (`credit=False`) dans une
    fiche qui est elle-même un lien : un lien dans un lien casse la page (le navigateur coupe la
    fiche en morceaux) ; les crédits sont alors en bas de page."""
    if not photo:
        return f'<figure class="{classe} dessin">{icone(racine, x["code"], 120)}</figure>'
    return (f'<figure class="{classe}"><img src="{racine}img/especes/{x["code"]}.jpg" alt="{e(x["nom"])}" '
            f'width="{photo["largeur"]}" height="{photo["hauteur"]}"{' loading="lazy"' if paresseuse else ""}>'
            + (f"<figcaption>{credit_photo(photo)}</figcaption>" if credit else "") + "</figure>")


def page_espece(x: dict, communs: dict, legendes: dict, niv: list[dict], jours: list[date], noms: dict,
                validation: dict | None, genere_le: str, photo: dict | None = None) -> str:
    """`x` : règles de l'espèce (`especes.en_json`) ; `niv` : son état national, jour par jour
    (`pages.national`) ; `noms` : noms des départements ; `validation` : son bloc France."""
    code, nom = x["code"], x["nom"]
    il = pronom(x)
    pre = x.get("milieu") == "pre"
    s0, s1, s2, s3 = x["saison"]
    jmin, jmax = x["pluie_jours"]
    p0, p1 = x["pluie_mm"]
    t0, t1, t2, t3 = x["sol"]
    a1, a2 = x["altitude"]
    lat = fr(communs["latitude_ref"])
    haut = tete(f"{nom} ({x['latin']}) : où et quand le chercher en France",
                f"{nom} : les forêts, l'altitude, la saison et la météo qui lui conviennent, à quoi "
                f"{il} ressemble et ses sosies, et les départements où les conditions sont bonnes "
                "aujourd'hui.", "../", f"{DOSSIER}/{code}.html", image=image_partage("france", genere_le))
    carte = "../carte/" if pre else f"../carte/?espece={code}"
    lignes = [f'  <p class="fil"><a href="./">Les espèces</a> › {e(nom)}</p>',
              f'  <h1>{e(nom)} <span class="latin">{e(x["latin"])}</span></h1>',
              f'  <div class="tete-espece">{figure_photo(x, photo, paresseuse=False)}<div>',
              f'  <p class="chapeau">{e(x["habitat_texte"])}</p>',
              f'  <p class="saison-mois"><strong>Saison</strong> {calendrier_mois(x["saison"], jours[0].month)}</p>',
              '  <p class="muet">Une photo aide à chercher, jamais à identifier.</p></div></div>',
              "  <h2>En ce moment</h2>",
              f'  <p class="muet">Calculé le {instant_paris(genere_le)}, sur {lieux(x)} de chaque département.</p>']
    j0 = niv[0]
    if meilleur_niveau(j0) in (0, None):
        lignes.append(f"  <p>Hors saison partout aujourd'hui : la saison {e(x['de'])} court en gros du "
                      f"{date_courte(s0)} au {date_courte(s3)}.</p>")
    elif not j0[4] and not j0[3]:
        t = etat_espece(niv, jours, noms, "../")
        lignes.append(f"  <p>{t[:1].upper()}{t[1:]}.</p>")
    else:
        for n, quoi in ((4, "Bonnes conditions aujourd'hui"), (3, "Bonnes conditions par endroits")):
            if j0[n]:
                lignes.append(f"  <p><strong>{quoi}</strong> ({departements_de(len(j0[n]))}, le plus de "
                              f"{'prés favorables' if pre else 'forêt favorable'} d'abord) : "
                              + ", ".join(f'<a href="../departements/{c}.html">{e(noms.get(c, c))}</a>'
                                          for c in j0[n]) + ".</p>")
    # Une espèce des champs n'a pas de carte fine : la semaine en France d'abord.
    semaine = f'<a class="bouton{" principal" if pre else ""}" href="../en-ce-moment.html#{code}">La semaine en France</a>'
    voir = "" if pre else f'<a class="bouton principal" href="{carte}">Voir la carte {e(x["de"])}</a>'
    lignes += [f'  <p class="actions">{voir}{semaine}{PARTAGER}</p>',
               "  <h2>Où le chercher</h2>",
               "  <ul>"]
    if pre:
        favorables = essences_entre(x, NOMS_MILIEUX, 0.8, 2, "prairies")
        possibles = essences_entre(x, NOMS_MILIEUX, 0.4, 0.8, "prairies")
        quoi = "Milieux"
    else:
        favorables = essences_entre(x, legendes["essences"], 0.8, 2)
        possibles = essences_entre(x, legendes["essences"], 0.4, 0.8)
        quoi = "Forêts"
    if favorables:
        lignes.append(f"    <li>{quoi} favorables : {e(favorables)}.</li>")
    if possibles:
        lignes.append(f"    <li>{quoi} possibles : {e(possibles)}.</li>")
    b0, b1 = x["plancher"]
    if b1 > 0:      # une espèce de montagne
        altitude = (f"    <li>Altitude : favorable de {nombre(b1)} à {nombre(a1)}{NBSP}m, plus du tout sous "
                    f"{nombre(b0)}{NBSP}m ni au-dessus de {nombre(a2)}{NBSP}m, à {lat}°{NBSP}N (la Haute-Savoie) ; "
                    f"plancher et plafond montent d'environ {nombre(communs['hopkins_metres'])}{NBSP}m par degré "
                    "vers le sud.</li>")
    else:
        altitude = (f"    <li>Altitude : favorable jusqu'à {nombre(a1)}{NBSP}m, plus du tout au-dessus de "
                    f"{nombre(a2)}{NBSP}m à {lat}°{NBSP}N (la Haute-Savoie) ; ce plafond monte d'environ "
                    f"{nombre(communs['hopkins_metres'])}{NBSP}m par degré vers le sud. Pas de plancher : {il} "
                    "pousse jusqu'au niveau de la mer.</li>")
    if pre:
        lignes += [altitude, "    <li>Pas de carte des prés, case par case : ils sont presque tous privés. Les "
                   "conditions se lisent par département et par commune, d'après les prairies et pelouses "
                   "de Corine Land Cover.</li>", "  </ul>"]
    else:
        lignes += [f"    <li>{e(sol(x, legendes['roches']))}</li>", altitude, "  </ul>"]
    if x.get("repere"):
        lignes.append(f"  <p><strong>Repère de terrain.</strong> {e(x['repere'])}</p>")
    lignes += ["  <h2>Quand</h2>",
               f"  <p>{e(x['meteo_texte'])}</p>",
               "  <ul>",
               f"    <li>Saison : pleine du {date_courte(s1)} au {date_courte(s2)}, possible du {date_courte(s0)} "
               f"au {date_courte(s3)}, à {lat}°{NBSP}N. Plus au sud, les dates de printemps avancent et celles "
               f"d'automne reculent d'environ {fr(communs['hopkins_jours'])} jours par degré.</li>",
               f"    <li>Pluie : la carte compte la pluie tombée du {jmax}e au {jmin}e jour avant : rien sous "
               f"{fr(p0)}{NBSP}mm, pleine pousse au-delà de {fr(p1)}{NBSP}mm.</li>",
               f"    <li>Sol : au mieux entre {fr(t1)} et {fr(t2)}{NBSP}°C en moyenne sur les 7 jours "
               f"précédents ; rien sous {fr(t0)}{NBSP}°C ni au-dessus de {fr(t3)}{NBSP}°C.</li>",
               f"    <li>Gel : chaque jour de gel de la semaine multiplie l'indice par {fr(x['gel'])}.</li>",
               "  </ul>",
               "  <h2>À quoi " + il + " ressemble</h2>",
               '  <div class="alerte"><p><strong>Ces lignes aident à chercher, jamais à identifier.</strong> Ne '
               "consommez jamais un champignon sans identification certaine : faites contrôler votre récolte "
               'par un pharmacien ou une société mycologique. <a href="../avant-de-partir.html">Avant de '
               "partir</a>.</p></div>",
               f"  <p>{e(x['description'])}</p>"]
    if x.get("confusions"):
        lignes.append(f"  <p><strong>Sosies.</strong> {e(x['confusions'])}</p>")
    if x.get("avertissement"):
        lignes.append(f"  <p><strong>{e(x['avertissement'])}</strong></p>")
    lignes += ["  <h2>Ce que la carte en sait</h2>"] + ce_que_la_carte_en_sait(x, validation)
    lignes += [f'  <p class="muet">Limite : {e(lim)}</p>' for lim in x.get("limites") or []]
    lignes.append('  <p><a href="../validation.html">Le détail de la vérification</a> · '
                  '<a href="../methode.html">Toutes les règles du calcul</a></p>')
    return haut + "\n".join(lignes) + "\n" + pied("../")


def page_index(especes: list[dict], nat: dict, jours: list[date], noms: dict, genere_le: str,
               photos: dict | None = None) -> str:
    """Toutes les espèces d'un coup d'œil : celle du moment, une fiche illustrée par espèce avec
    ses mois de saison, le calendrier complet, les crédits des photos."""
    photos = photos or {}
    foret = [x for x in especes if x.get("milieu", "foret") == "foret"]
    pres = [x for x in especes if x.get("milieu") == "pre"]
    haut = tete("Les champignons de la carte : saisons, milieux, où les chercher",
                f"{noms_especes(especes)[:1].upper()}{noms_especes(especes)[1:]} : leurs milieux, leur "
                "saison mois par mois, leurs sosies, et où les conditions sont bonnes aujourd'hui en France.",
                "../", f"{DOSSIER}/", image=image_partage("france", genere_le), large=True)
    mois = jours[0].month
    ordre = ordre_saison(especes, nat)
    lignes = ["  <h1>Les champignons de la carte</h1>",
              f'  <p class="chapeau">{len(foret)} espèces de forêt, sur la carte case par case, et {len(pres)} '
              "des prés, commune par commune : leur saison mois par mois, leurs milieux, à quoi elles "
              "ressemblent, et où les conditions sont bonnes aujourd'hui.</p>"]

    # L'espèce du moment : la mieux placée aujourd'hui en France.
    vedette = ordre[0]
    n = meilleur_niveau(nat[vedette["code"]][0])
    if n not in (0, None):
        t = etat_espece(nat[vedette["code"]], jours, noms, "../")
        lignes += ['  <section class="vedette">',
                   f"  {figure_photo(vedette, photos.get(vedette['code']), classe='photo vedette-photo', paresseuse=False)}",
                   '  <div class="vedette-texte">',
                   f'  <p class="sur-titre">En ce moment · {MOIS_COURTS[mois - 1].rstrip(".")} {jours[0].year}</p>',
                   f'  <h2><a href="{vedette["code"]}.html">{e(vedette["nom"])}</a> '
                   f'<span class="latin">{e(vedette["latin"])}</span></h2>',
                   f"  <p>{t[:1].upper()}{t[1:]}.</p>",
                   f'  <p class="muet">{e(vedette["habitat_texte"])}</p>',
                   f'  <p class="actions"><a class="bouton principal" href="{vedette["code"]}.html">La fiche</a>'
                   f'<a class="bouton" href="../en-ce-moment.html#{vedette["code"]}">La semaine en France</a></p>',
                   "  </div></section>"]

    def fiche(x):
        j0 = nat[x["code"]][0]
        n = meilleur_niveau(j0)
        etat = ("hors saison" if n in (0, None) else "défavorable partout" if n == 1 else
                f"{NIVEAUX_COURTS[n]} dans {departements_de(len(j0[n]))}")
        milieu = "Prés" if x.get("milieu") == "pre" else "Forêt"
        return (f'    <li data-milieu="{x.get("milieu", "foret")}" data-saison="{"non" if n in (0, None) else "oui"}">'
                f'<a href="{x["code"]}.html">'
                f'{figure_photo(x, photos.get(x["code"]), classe="photo vignette-espece", credit=False)}'
                f'<span class="badges"><span class="badge">{milieu}</span>'
                f'<span class="badge n{n or 0}">{e(etat)}</span></span>'
                f'<strong>{e(x["nom"])}</strong><span class="latin">{e(x["latin"])}</span>'
                f'{calendrier_mois(x["saison"], mois)}</a></li>')

    lignes += ["  <h2>Toutes les espèces</h2>",
               '  <p class="muet">Les mieux placées aujourd\'hui d\'abord. Sous chaque nom, ses mois : '
               '<span class="mois legende-mois"><span class="plein">J</span></span> pleine saison, '
               '<span class="mois legende-mois"><span class="possible">J</span></span> possible, le mois en cours '
               "entouré (à 46° N, la Haute-Savoie : plus au sud, le printemps avance et l'automne recule "
               "d'environ quatre jours par degré).</p>",
               # Les filtres : cachés sans JavaScript (toutes les fiches restent visibles).
               '  <p class="filtres" data-filtres hidden>'
               '<button type="button" data-filtre="tout" aria-pressed="true">Toutes</button>'
               '<button type="button" data-filtre="saison" aria-pressed="false">En saison</button>'
               '<button type="button" data-filtre="foret" aria-pressed="false">Forêt</button>'
               '<button type="button" data-filtre="pre" aria-pressed="false">Prés</button></p>',
               '  <ul class="fiches-especes">'] + [fiche(x) for x in ordre] + ["  </ul>"]

    # Le calendrier : toutes les espèces, mois par mois.
    tete_mois = "".join(f'<th scope="col"{" class=\"actuel\"" if k + 1 == mois else ""}>{m}</th>'
                        for k, m in enumerate(MOIS_COURTS))
    rangs = []
    for x in sorted(especes, key=lambda x: (x.get("milieu") == "pre", x["saison"][1])):
        cases = "".join(f'<td class="{c}{" actuel" if k + 1 == mois else ""}"></td>'
                        for k, c in enumerate(mois_saison(x["saison"])))
        rangs.append(f'<tr><th scope="row"><a href="{x["code"]}.html">{icone("../", x["code"], 24)}'
                     f'{e(x["nom"])}</a></th>{cases}</tr>')
    lignes += ["  <h2>Le calendrier des saisons</h2>",
               '  <p class="muet">Dans l\'ordre où les saisons commencent ; les espèces des prés à la fin. '
               "La carte suit chaque jour la pluie et la température du sol : une saison dit quand chercher, "
               "pas si ça pousse.</p>",
               '  <div class="tableau"><table class="calendrier">',
               f"  <thead><tr><th></th>{tete_mois}</tr></thead>",
               f"  <tbody>{''.join(rangs)}</tbody>",
               "  </table></div>",
               '  <div class="legende-semaine"><span><span class="pastille cal-plein"></span>pleine saison</span>'
               '<span><span class="pastille cal-possible"></span>possible</span></div>']
    if photos:
        lignes += ["  <h2>Crédits des photos</h2>", '  <ul class="credits">']
        lignes += [f"    <li>{e(x['nom'])} : {credit_photo(photos[x['code']])[len('Photo : '):]}</li>"
                   for x in especes if x["code"] in photos]
        lignes += ["  </ul>"]
    return haut + "\n".join(lignes) + "\n" + pied("../")


def ecrire(site: Path, departements: list[dict], regles: dict, legendes: dict, resumes: dict,
           jours: list[date], genere_le: str, validation: dict | None) -> list[str]:
    """Écrit les fiches et leur sommaire ; rend leurs chemins depuis la racine."""
    especes = regles["especes"]
    nat = national(especes, departements, resumes, len(jours))
    noms = {d["code"]: d["nom"] for d in departements}
    par_espece = (validation or {}).get("regions", {}).get("france", {}).get("especes", {})
    photos = charger_photos()
    dossier = site / DOSSIER
    dossier.mkdir(parents=True, exist_ok=True)
    for x in especes:
        (dossier / f"{x['code']}.html").write_text(
            page_espece(x, regles["communs"], legendes, nat[x["code"]], jours, noms, par_espece.get(x["code"]),
                        genere_le, photos.get(x["code"])), encoding="utf-8")
    (dossier / "index.html").write_text(page_index(especes, nat, jours, noms, genere_le, photos), encoding="utf-8")
    return [f"{DOSSIER}/"] + [f"{DOSSIER}/{x['code']}.html" for x in especes]
