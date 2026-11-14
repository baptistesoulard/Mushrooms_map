"""Le calendrier des champignons (`site/calendrier/`), réécrit chaque matin par l'export : une page
par mois (« Quels champignons chercher en novembre ? ») et leur sommaire (demande du 2026-11-14 :
des pages qui répondent aux recherches qu'on tape, et qui servent toute l'année).

Rien n'y est écrit à la main : un mois retient les espèces dont la saison des règles le couvre
(`pages.mois_saison`, comme le calendrier de la page des espèces), « en pleine saison » ou « en
début ou fin de saison », avec leur portrait (`portraits.py`). Les dates sont celles du centre de
la France, la page le dit.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from . import especes as E
from .modele import dates_saison
from .pages import (NOM, article, bandeau, chemin_espece, chemin_mois, date_courte, de_mois, e, enumerer,
                    fil_ariane, image_partage, mois_saison, page_web, pied, tete)
from .pages_especes import CENTRE, SUD, figure_photo, note_saveur, tableau_saisons
from .photos import charger as charger_photos
from .portraits import PORTRAITS
from .redaction import MOIS

DOSSIER = "calendrier"
# Le sud du continent (Perpignan) : la saison d'automne y finit le plus tard (loi de Hopkins,
# `modele.dates_saison`). Sert à dire, pour un mois creux, ce qui y dure encore.
LAT_SUD = 42.7


def especes_du_mois(especes: list[dict], m: int) -> tuple[list[dict], list[dict]]:
    """Les espèces en pleine saison ce mois-là, puis celles en début ou fin de saison."""
    plein = [x for x in especes if mois_saison(x["saison"])[m - 1] == "plein"]
    possible = [x for x in especes if mois_saison(x["saison"])[m - 1] == "possible"]
    cle = lambda x: (x.get("milieu") == "pre", -(PORTRAITS[x["code"]].saveur if x["code"] in PORTRAITS else 0))  # noqa: E731
    return sorted(plein, key=cle), sorted(possible, key=cle)


def finissent_au_sud(especes: list[dict], m: int) -> list[dict]:
    """Les espèces dont la saison, finie avant le mois `m` au centre de la France, déborde encore
    sur ce mois au sud (`LAT_SUD`), d'après la règle des saisons du modèle."""
    debut = date(2026, m, 1).toordinal()
    sortie = []
    for x in especes:
        esp = E.PAR_CODE[x["code"]]
        if any(dates_saison(esp, annee, E.LATITUDE_REF)[3] < debut <= dates_saison(esp, annee, LAT_SUD)[3]
               for annee in (2025, 2026)):
            sortie.append(x)
    return sortie


def _noms(liste: list[dict]) -> str:
    return enumerer([article(x["de"]) for x in liste])


def _carte(x: dict, R: str) -> str:
    return f"{R}carte/" if x.get("milieu") == "pre" else f"{R}carte/?espece={x['code']}"


def page_mois(m: int, especes: list[dict], jours: list[date], genere_le: str, photos: dict) -> str:
    R = "../../"                                   # la page est dans calendrier/<mois>/
    nom, chemin = MOIS[m - 1], chemin_mois(m)
    plein, possible = especes_du_mois(especes, m)
    avant, apres = (m - 2) % 12 + 1, m % 12 + 1
    titre = f"Quels champignons chercher en {nom} ? Le calendrier de la cueillette"
    if plein or possible:
        noms = enumerer([x["nom"].lower() for x in (plein + possible)[:4]])
        description = (f"Les champignons à chercher en {nom} en France ({noms}…) : où ils poussent, des astuces "
                       "pour les trouver, leur saveur et la carte des conditions du jour.")
    else:
        description = (f"En {nom}, la saison des champignons de la carte est finie en France : ce qui revient "
                       f"en {MOIS[apres - 1]}, et la carte des conditions du jour.")
    haut = tete(titre, description, R, chemin, image=image_partage("france", genere_le),
                ld=[page_web(titre, chemin, genere_le, description),
                    fil_ariane([("./", NOM), (f"{DOSSIER}/", "Calendrier"), (chemin, nom.capitalize())])])

    if plein:
        chapeau = (f"En {nom}, {_noms(plein)} {'sont' if len(plein) > 1 else 'est'} en pleine saison"
                   + (f" ; {_noms(possible)} {'commencent ou finissent' if len(possible) > 1 else 'commence ou finit'}"
                      if possible else "") + f", {CENTRE}.")
    elif possible:
        chapeau = (f"En {nom}, aucune espèce de la carte n'est en pleine saison {CENTRE} ; {_noms(possible)} "
                   f"{'commencent ou finissent' if len(possible) > 1 else 'commence ou finit'}.")
    else:
        chapeau = f"En {nom}, aucune espèce de la carte n'est de saison {CENTRE}."
    actuel = m == jours[0].month
    lignes = bandeau(
        "Calendrier", f"Les champignons {e(de_mois(m))}",
        [f'  <p class="chapeau">{e(chapeau)}</p>',
         f'  <p class="actions"><a class="bouton principal" href="{R}en-ce-moment.html">'
         f'{"Où chercher cette semaine" if actuel else "Où chercher en ce moment"}</a>'
         f'<a class="bouton" href="{R}carte/">Voir la carte</a></p>'],
        fil=f'<p class="fil"><a href="../">Calendrier</a> › {e(nom.capitalize())}</p>')

    if plein:
        lignes.append("  <h2>En pleine saison</h2>")
        for k, x in enumerate(plein):
            p = PORTRAITS.get(x["code"])
            note = note_saveur(p)
            lignes += ['  <section class="mois-espece">',
                       f"  {figure_photo(x, photos.get(x['code']), racine=R, paresseuse=k > 0)}",
                       "  <div>",
                       f'  <h3><a href="{R}{chemin_espece(x["code"])}">{e(x["nom"])}</a> '
                       f'<span class="latin">{e(x["latin"])}</span></h3>']
            if note:
                lignes.append(f'  <p class="saveur"><strong>Saveur</strong> {note}</p>')
            lignes.append(f"  <p>{e(x['habitat_texte'])}</p>")
            if p and p.astuces:
                lignes.append(f"  <p><strong>Astuce.</strong> {e(p.astuces[0])}</p>")
            lignes += [f'  <p><a href="{R}{chemin_espece(x["code"])}">La fiche {e(x["de"])}</a> · '
                       f'<a href="{_carte(x, R)}">la carte</a></p>',
                       "  </div>", "  </section>"]
    if possible:
        lignes += ["  <h2>En début ou en fin de saison</h2>", "  <ul>"]
        for x in possible:
            s0, s1, s2, _ = x["saison"]
            phase = "début" if m < int(s1[:2]) else "fin"
            lignes.append(f'    <li><a href="{R}{chemin_espece(x["code"])}">{e(x["nom"])}</a> : {phase} de saison '
                          f"(pleine du {date_courte(s1)} au {date_courte(s2)}).</li>")
        lignes.append("  </ul>")
    if not plein and not possible:
        # Un mois creux : ce qui finit au sud en début de mois, ce qui revient le mois suivant.
        finissent = finissent_au_sud(especes, m)
        reviennent = [x for x in especes if int(x["saison"][0][:2]) == apres]
        if finissent:
            lignes.append(f"  <p>Au sud, la saison d'automne dure plus longtemps : {e(_noms(finissent))} "
                          f"{'peuvent' if len(finissent) > 1 else 'peut'} encore y sortir en début de mois.</p>")
        if reviennent:
            lignes.append(f"  <p>En {MOIS[apres - 1]}, {e(_noms(reviennent))} "
                          f"{'reviennent' if len(reviennent) > 1 else 'revient'} : "
                          f'<a href="../{slug_mois(apres)}/">les champignons '
                          f"{e(de_mois(apres))}</a>.</p>")
    lignes.append(f'  <p class="muet">Dates {CENTRE} ; {SUD}. Une saison dit quand chercher ; la carte dit si '
                  "les conditions sont réunies.</p>")
    lignes.append(f'  <p class="mois-suite"><a href="../{slug_mois(avant)}/">‹ Les champignons '
                  f'{e(de_mois(avant))}</a> · <a href="../">Toute l\'année</a> · '
                  f'<a href="../{slug_mois(apres)}/">Les champignons {e(de_mois(apres))} ›</a></p>')
    return haut + "\n".join(lignes) + "\n" + pied(R)


def page_index(especes: list[dict], jours: list[date], genere_le: str) -> str:
    R = "../"
    titre = "Le calendrier des champignons : quoi chercher mois par mois en France"
    description = ("Mois par mois, les champignons à chercher en France : ceux en pleine saison, ceux qui "
                   "commencent ou finissent, et la carte des conditions du jour.")
    haut = tete(titre, description, R, f"{DOSSIER}/", image=image_partage("france", genere_le),
                ld=[page_web(titre, f"{DOSSIER}/", genere_le, description),
                    fil_ariane([("./", NOM), (f"{DOSSIER}/", "Calendrier")])])
    actuel = jours[0].month
    lignes = bandeau("Calendrier", "Le calendrier des champignons",
                     [f'  <p class="chapeau">Mois par mois, les espèces de la carte en pleine saison, et celles '
                      f"qui commencent ou finissent, {CENTRE}.</p>"])
    lignes += ["  <h2>Mois par mois</h2>", '  <ul class="mois-liste">']
    for m in range(1, 13):
        plein, possible = especes_du_mois(especes, m)
        quoi = (enumerer([x["nom"].lower() for x in plein]) if plein else
                f"début ou fin de saison : {enumerer([x['nom'].lower() for x in possible])}" if possible else
                "rien de la carte")
        lignes.append(f'    <li{" class=\"actuel\"" if m == actuel else ""}><a href="{slug_mois(m)}/">'
                      f"{e(MOIS[m - 1].capitalize())}</a> : {e(quoi)}</li>")
    lignes += ["  </ul>", "  <h2>Le tableau de l'année</h2>"] + tableau_saisons(especes, actuel, R)
    return haut + "\n".join(lignes) + "\n" + pied(R)


def slug_mois(m: int) -> str:
    return chemin_mois(m).split("/")[1]


def ecrire(site: Path, especes: list[dict], jours: list[date], genere_le: str) -> list[str]:
    """Écrit les douze mois et leur sommaire ; rend leurs chemins depuis la racine."""
    photos = charger_photos()
    (site / DOSSIER).mkdir(parents=True, exist_ok=True)
    (site / DOSSIER / "index.html").write_text(page_index(especes, jours, genere_le), encoding="utf-8")
    chemins = [f"{DOSSIER}/"]
    for m in range(1, 13):
        chemin = chemin_mois(m)
        (site / chemin).mkdir(parents=True, exist_ok=True)
        (site / chemin / "index.html").write_text(page_mois(m, especes, jours, genere_le, photos), encoding="utf-8")
        chemins.append(chemin)
    return chemins
