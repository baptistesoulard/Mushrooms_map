"""Socle des pages réécrites chaque matin par l'export : accueil, « en ce moment », fiches
espèces, départements. En-tête, pied, dates et listes en français, état de la France.

Ces pages ne lisent aucune donnée : elles reçoivent les résumés déjà calculés
(`export_france`) et rendent du HTML lisible sans JavaScript, ce que lisent les moteurs de
recherche et les aperçus de partage. Aucune ne montre de coin. Non indexées tant que le site ne
l'est pas : le jour où il le sera, `INDEXER` ouvre les pages et écrit le plan du site.
"""
from __future__ import annotations

import html
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .depot import decalage_paris
from .redaction import JOURS, MOIS, NBSP

INDEXER = False
ADRESSE = "https://baptistesoulard.github.io/Mushrooms_map/"
NOM = "Champignons en France"
NIVEAUX_COURTS = ["hors saison", "défavorable", "possible", "par endroits", "bon"]
JOURS_COURTS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
# Le plan du pied de page, en chemins depuis la racine du site.
PLAN = [("./", "Accueil"), ("carte/", "La carte"), ("en-ce-moment.html", "En ce moment"),
        ("especes/", "Les espèces"), ("departements/", "Par département"),
        ("methode.html", "Méthode"), ("validation.html", "Face aux observations"),
        ("avant-de-partir.html", "Avant de partir"), ("a-propos.html", "À propos")]

# Le bouton Partager : caché sans JavaScript (pages.js le montre), la page reste lisible.
PARTAGER = '<button type="button" class="bouton" data-partager hidden>Partager</button>'

e = html.escape


def image_partage(nom: str, genere_le: str) -> str:
    """L'image de partage d'une page (`partage.py`), depuis la racine. L'heure du calcul change
    l'adresse à chaque export : les messageries gardent longtemps l'image d'une adresse vue."""
    return f"data/partage/{nom}.png?v={''.join(c for c in genere_le[:16] if c.isdigit())}"


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


def date_courte(mmjj: str) -> str:
    """« 07-15 » (une borne de saison des règles) → « 15 juillet »."""
    m, j = (int(v) for v in mmjj.split("-"))
    return f"{'1er' if j == 1 else j} {MOIS[m - 1]}"


def instant_paris(iso: str) -> str:
    """« 2026-11-01T05:20+00:00 » → « dimanche 1er novembre 2026 à 6 h 20 »."""
    t = datetime.fromisoformat(iso).astimezone(timezone.utc)
    t = t + timedelta(seconds=decalage_paris(int(t.timestamp())))
    return f"{date_longue(t.date())} {t.year} à {t.hour} h {t.minute:02d}"


def cle_departement(code: str) -> str:
    """Tri par numéro, la Corse (2A, 2B) à la place du 20."""
    return code.replace("2A", "20A").replace("2B", "20B")


def pct(v: float) -> str:
    return f"{round(v * 100)}{NBSP}%"


def departements_de(n: int) -> str:
    return f"{n} département{'s' if n > 1 else ''}"


def lien(racine: str, chemin: str) -> str:
    """Un chemin pris depuis la racine du site, vu d'une page dont la racine est `racine`
    (« » à la racine, « ../ » dans un dossier)."""
    return racine + chemin if chemin != "./" else racine or "./"


def tete(titre: str, description: str, racine: str, chemin: str, image: str | None = None,
         plus: str = "") -> str:
    """Le haut d'une page : `chemin` depuis la racine (adresse canonique), `image` de partage
    depuis la racine aussi, `plus` ajouté en fin d'en-tête."""
    robots = "index, follow" if INDEXER else "noindex, nofollow"
    canonique = f'\n<link rel="canonical" href="{ADRESSE}{chemin}">' if INDEXER else ""
    apercu = (f'\n<meta property="og:image" content="{ADRESSE}{image}">'
              '\n<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">'
              '\n<meta name="twitter:card" content="summary_large_image">') if image else ""
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="{robots}">
<title>{e(titre)}</title>
<meta name="description" content="{e(description)}">
<meta property="og:title" content="{e(titre)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:type" content="website">{apercu}{canonique}
<link rel="icon" href="{racine}favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{racine}style.css">{plus}
</head>
<body>
<div class="page">
"""


def entete(racine: str, *liens: tuple[str, str]) -> str:
    """La ligne du haut : le nom du site vers l'accueil, puis les liens donnés (adresse, texte)."""
    morceaux = [f'<a href="{lien(racine, "./")}">{NOM}</a>'] + [f'<a href="{h}">{e(t)}</a>' for h, t in liens]
    return f"  <header>{' · '.join(morceaux)}</header>"


def pied(racine: str) -> str:
    """Avertissement, plan du site, et `pages.js` (bouton Partager, département mémorisé)."""
    plan = "\n".join(f'    <a href="{lien(racine, c)}">{t}</a>' for c, t in PLAN)
    return f"""  <p class="alerte">Ne consommez jamais un champignon sans identification certaine : faites
  contrôler votre récolte par un pharmacien ou une société mycologique.
  <a href="{racine}avant-de-partir.html">Avant de partir</a>.</p>
  <nav class="pied">
{plan}
  </nav>
</div>
<script type="module" src="{racine}pages.js"></script>
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


# --- La France entière ------------------------------------------------------------------

def surface_bonne(r: dict) -> float:
    """km² de forêt aux bonnes conditions dans un département : ce qui compte pour choisir où
    aller. L'indice moyen, lui, met en tête les départements à peine boisés (Paris, petite
    couronne), où quelques bois suffisent à faire la moyenne. Avant le 2026-11-01, les résumés
    n'avaient pas de surface : l'indice départage seul."""
    return r["part_bon"] * r.get("km2", 0.0) if "part_bon" in r else 0.0


def national(especes: list[dict], departements: list[dict], resumes: dict, n_jours: int) -> dict:
    """Par espèce et par jour, les départements de chaque niveau (0 à 4), ceux qui ont le plus de
    forêt aux bonnes conditions d'abord : `{code: [{niveau: [départements]}, …]}`."""
    sortie = {}
    for x in especes:
        par_jour = []
        for k in range(n_jours):
            niveaux: dict[int, list] = {n: [] for n in range(5)}
            for d in departements:
                r = (resumes.get(d["code"]) or {}).get(x["code"]) or []
                if k < len(r):
                    niveaux[r[k]["niveau"]].append((-surface_bonne(r[k]), -r[k]["indice_moyen"],
                                                    cle_departement(d["code"]), d["code"]))
            par_jour.append({n: [c for *_, c in sorted(v)] for n, v in niveaux.items()})
        sortie[x["code"]] = par_jour
    return sortie


def meilleur_niveau(jour: dict) -> int | None:
    """Le meilleur niveau atteint en France ce jour-là ; None sans aucun département."""
    return max((n for n, v in jour.items() if v), default=None)


def ordre_saison(especes: list[dict], nat: dict) -> list[dict]:
    """Les espèces aux meilleures conditions aujourd'hui d'abord, à niveau égal les plus
    répandues ; l'ordre des règles départage, les espèces hors saison partout ferment la liste."""
    def cle(x):
        auj = nat[x["code"]][0]
        n = meilleur_niveau(auj) or 0
        return (-n, -len(auj.get(n, [])))
    return sorted(especes, key=cle)


def ecrire_plan(site: Path, chemins: list[str]) -> None:
    """`sitemap.xml` quand le site est indexé ; sinon, aucun plan (et l'ancien s'efface)."""
    plan = site / "sitemap.xml"
    if INDEXER:
        plan.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                        + "".join(f"  <url><loc>{ADRESSE}{c}</loc></url>\n" for c in chemins)
                        + "</urlset>\n", encoding="utf-8")
    elif plan.exists():
        plan.unlink()
