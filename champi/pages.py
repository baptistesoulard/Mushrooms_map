"""Socle des pages réécrites chaque matin par l'export : accueil, « en ce moment », fiches
espèces, départements. En-tête, pied, dates et listes en français, état de la France.

Ces pages ne lisent aucune donnée : elles reçoivent les résumés déjà calculés
(`export_france`) et rendent du HTML lisible sans JavaScript, ce que lisent les moteurs de
recherche et les aperçus de partage. Aucune ne montre de coin. Indexées depuis le 2026-11-06, quand
la carte publique est passée aux zones de 250 m (`zones.py`) : `INDEXER` ouvre les pages, écrit le
plan du site et `robots.txt`. Le repasser à faux referme tout.
"""
from __future__ import annotations

import html
import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .climatologie import en_mots
from .config import ADRESSE
from .icones import svg_marque
from .depot import decalage_paris
from .redaction import JOURS, MOIS, NBSP

INDEXER = True
NOM = "Champimétéo"
NIVEAUX_COURTS = ["hors saison", "défavorable", "possible", "par endroits", "bon"]
JOURS_COURTS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
# Le plan du pied de page, en chemins depuis la racine du site.
PLAN = [("./", "Accueil"), ("carte/", "La carte"), ("en-ce-moment.html", "En ce moment"),
        ("especes/", "Les espèces"), ("departements/", "Par département"),
        ("methode.html", "Méthode"), ("validation.html", "Face aux observations"),
        ("avant-de-partir.html", "Avant de partir"), ("a-propos.html", "À propos")]

# La barre du haut, sur toutes les pages, la carte comprise : les rubriques, en chemins depuis la
# racine ; le menu des écrans étroits y ajoute les pages de référence.
BARRE = [("carte/", "La carte"), ("en-ce-moment.html", "En ce moment"), ("especes/", "Les espèces"),
         ("departements/", "Départements"), ("avant-de-partir.html", "Avant de partir"),
         ("methode.html", "Méthode")]
MENU = BARRE + [("validation.html", "Face aux observations"), ("a-propos.html", "À propos")]
# Les pages écrites à la main, dont `python -m champi.pages barre` réécrit la barre. La page 404
# (servie par GitHub Pages à toute adresse inconnue) a `<base href="/">` et n'est jamais indexée.
STATIQUES = ["a-propos.html", "avant-de-partir.html", "methode.html", "validation.html", "carte/index.html",
             "404.html"]
INTROUVABLE = "404.html"
DEBUT_BARRE, FIN_BARRE = "<!-- barre -->", "<!-- /barre -->"
# Le pied de page commun, réécrit de même entre ses marqueurs, sauf sur la carte (plein écran).
DEBUT_PIED, FIN_PIED = "<!-- pied -->", "<!-- /pied -->"
SANS_PIED = {"carte/index.html"}

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


def noms_especes(especes: list[dict]) -> str:
    """« cèpe, bolet bai, … et morille » : les espèces des règles, jamais une liste écrite à la main."""
    return enumerer([x["nom"][:1].lower() + x["nom"][1:] for x in especes])


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


def habituel(x: dict) -> str:
    """« Météo favorable 7 années sur 10 à cette date » : ce qui est ordinaire pour l'espèce ce
    jour-là (`climatologie`, que l'export attache sous « habituel ») ; vide sans mesure."""
    t = en_mots(x.get("habituel"))
    return f"{t[:1].upper()}{t[1:]}" if t else ""


def calcule_pour(jours: list[date]) -> str:
    """L'attribut qui date une page, sur sa ligne « Calculé le » : `pages.js` prévient en tête
    quand la mise à jour de la nuit n'a pas eu lieu (« aujourd'hui » y est alors un jour passé)."""
    return f' data-premier-jour="{jours[0].isoformat()}"'


# « en Vendée », « dans les Landes », « à Paris » : la préposition de chaque département, comme on
# le dit (et comme on le tape dans un moteur de recherche). Les autres prennent « en ».
_PREPOSITIONS = {"dans le ": "14 15 18 25 29 30 32 39 41 45 46 56 59 62 63 67 68 69 81 83 84 90 94 95",
                 "dans la ": "26 42 50 51 55 58 72 80 86",
                 "dans l'": "01 02 03 10 11 27 34 36 60 61 89 91",
                 "dans les ": "04 05 06 08 13 22 40 64 65 66 78 79 88 92",
                 "à ": "75"}
PREPOSITION = {code: p for p, codes in _PREPOSITIONS.items() for code in codes.split()}


def slug(texte: str) -> str:
    """« Côte-d'Or » → « cote-d-or » : minuscules sans accents, mots séparés par des tirets."""
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def chemin_departement(code: str, nom: str) -> str:
    """L'adresse de la page d'un département, depuis la racine : « departements/vendee/ ». Avant le
    2026-11-07 : « departements/85.html », qui renvoie depuis (`renvoi`)."""
    return f"departements/{slug(nom)}/"


def chemin_espece(code: str) -> str:
    """« especes/pied-de-mouton/ » : des tirets, que les moteurs lisent comme des espaces."""
    return f"especes/{code.replace('_', '-')}/"


def renvoi(vers: str, canonique: str, titre: str) -> str:
    """La page laissée à une ancienne adresse : elle renvoie aussitôt (`vers`, relatif) et dit aux
    moteurs où est la page (`canonique`, depuis la racine). Les liens déjà partagés, les alertes et
    les applis installées continuent de marcher."""
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex, follow">
<title>{e(titre)}</title>
<link rel="canonical" href="{ADRESSE}{canonique}">
<meta http-equiv="refresh" content="0; url={vers}">
<script>location.replace("{vers}" + location.search + location.hash);</script>
</head>
<body>
<p>Cette page a changé d'adresse : <a href="{vers}">{e(titre)}</a>.</p>
</body>
</html>
"""


def dans(code: str, nom: str) -> str:
    """« en Vendée », « dans les Landes », « dans l'Ain », « à Paris »."""
    return PREPOSITION.get(code, "en ") + nom


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


# --- Données structurées (schema.org, JSON-LD) : ce que lisent les moteurs et leurs résumés ---

def donnees_structurees(*objets: dict) -> str:
    """Les blocs JSON-LD d'une page, à mettre dans l'en-tête (`tete(..., ld=...)`). `<`, `>` et `&`
    sont échappés en JSON : un texte (un nom de commune) ne peut ni fermer le script ni y glisser
    de balise."""
    graphe = {"@context": "https://schema.org", "@graph": list(objets)}
    texte = json.dumps(graphe, ensure_ascii=False, separators=(",", ":"))
    texte = texte.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return f'\n<script type="application/ld+json">{texte}</script>'


def site_web() -> dict:
    """Le site lui-même, et qui le publie : l'accueil le déclare, les autres pages s'y rattachent."""
    return {"@type": "WebSite", "@id": f"{ADRESSE}#site", "url": ADRESSE, "name": NOM, "inLanguage": "fr-FR",
            "publisher": {"@type": "Organization", "@id": f"{ADRESSE}#editeur", "name": NOM, "url": ADRESSE,
                          "logo": f"{ADRESSE}icone-512.png"}}


def fil_ariane(etapes: list[tuple[str, str]]) -> dict:
    """`etapes` : (chemin depuis la racine, nom), de l'accueil à la page."""
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": k + 1, "name": nom, "item": ADRESSE + (chemin if chemin != "./" else "")}
        for k, (chemin, nom) in enumerate(etapes)]}


def page_web(titre: str, chemin: str, genere_le: str, description: str = "") -> dict:
    """Une page du matin : son adresse, sa date de mise à jour, son site."""
    d = {"@type": "WebPage", "@id": ADRESSE + chemin, "url": ADRESSE + chemin, "name": titre, "inLanguage": "fr-FR",
         "dateModified": genere_le, "isPartOf": {"@id": f"{ADRESSE}#site"}}
    return d | ({"description": description} if description else {})


def faq(questions: list[tuple[str, str]]) -> dict:
    """Questions et réponses en texte brut : les mêmes que celles écrites dans la page."""
    return {"@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": r}} for q, r in questions]}


def tete(titre: str, description: str, racine: str, chemin: str, image: str | None = None,
         plus: str = "", large: bool = False, ld: list[dict] | None = None) -> str:
    """Le haut d'une page : `chemin` depuis la racine (adresse canonique), `image` de partage
    depuis la racine aussi, `plus` ajouté en fin d'en-tête, `ld` ses données structurées."""
    robots = "index, follow" if INDEXER else "noindex, nofollow"
    canonique = f'\n<link rel="canonical" href="{ADRESSE}{chemin}">' if INDEXER else ""
    plus = (donnees_structurees(*ld) if ld else "") + plus
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
<link rel="icon" href="{racine}icone-192.png" sizes="192x192" type="image/png">
<link rel="stylesheet" href="{racine}style.css">{plus}
</head>
<body>
{barre(racine, chemin)}
<div class="page{" large" if large else ""}">
"""


def barre(racine: str, chemin: str) -> str:
    """La barre du haut : le nom du site vers l'accueil, les rubriques (la rubrique de `chemin`
    marquée), et sur écran étroit un menu qui s'ouvre sans JavaScript."""
    def liens(liste, retrait):
        return "\n".join(
            f'{retrait}<a href="{lien(racine, c)}"'
            f'{" aria-current=\"page\"" if chemin == c or (c.endswith("/") and chemin.startswith(c)) else ""}>{t}</a>'
            for c, t in liste)
    return f"""{DEBUT_BARRE}
<header class="barre">
  <a class="marque" href="{lien(racine, "./")}" aria-label="{NOM}, l'accueil">{svg_marque(30)}<span class="marque-nom">Champi<span>météo</span></span></a>
  <nav class="barre-liens" aria-label="Rubriques">
{liens(BARRE, "    ")}
  </nav>
  <details class="barre-menu">
    <summary>Menu</summary>
    <nav aria-label="Rubriques">
{liens([("./", "Accueil")] + MENU, "      ")}
    </nav>
  </details>
</header>
{FIN_BARRE}"""


def ecrire_barres_statiques(site: Path) -> list[str]:
    """Réécrit la barre et le pied des pages écrites à la main (entre leurs marqueurs) ; rend celles
    qui ont changé. La carte a `<base href="../">` : ses liens partent de la racine, comme ceux d'ici."""
    changees = []
    for chemin in STATIQUES:
        p = site / chemin
        s = p.read_text(encoding="utf-8")
        debut, fin = s.index(DEBUT_BARRE), s.index(FIN_BARRE) + len(FIN_BARRE)
        nouveau = s[:debut] + barre("", chemin) + s[fin:]
        if chemin not in SANS_PIED:
            debut, fin = nouveau.index(DEBUT_PIED), nouveau.index(FIN_PIED) + len(FIN_PIED)
            nouveau = nouveau[:debut] + pied_site("") + nouveau[fin:]
        if nouveau != s:
            p.write_text(nouveau, encoding="utf-8")
            changees.append(chemin)
    return changees


# --- Les saisons, l'icône et la photo d'une espèce ------------------------------------------

MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def mois_saison(saison: list[str]) -> list[str]:
    """La saison mois par mois, à la latitude de référence : « plein » quand un tiers du mois au
    moins tombe dans la pleine saison, « possible » dans la saison entière, sinon « »."""
    jours = [date(2026, *map(int, s.split("-"))) for s in saison]
    sortie = []
    for m in range(1, 13):
        debut = date(2026, m, 1)
        fin = date(2026, m + 1, 1) if m < 12 else date(2027, 1, 1)
        n = (fin - debut).days
        dans = lambda a, b: max(0, (min(fin, b + timedelta(days=1)) - max(debut, a)).days)   # noqa: E731
        sortie.append("plein" if dans(jours[1], jours[2]) * 3 >= n else
                      "possible" if dans(jours[0], jours[3]) * 3 >= n else "")
    return sortie


def calendrier_mois(saison: list[str], mois_actuel: int, classe: str = "mois") -> str:
    """Douze cases, une par mois, colorées selon la saison ; le mois en cours entouré."""
    cases = "".join(f'<span class="{c}{" actuel" if k + 1 == mois_actuel else ""}" title="{MOIS_COURTS[k]}">'
                    f"{MOIS_COURTS[k][0].upper()}</span>" for k, c in enumerate(mois_saison(saison)))
    return f'<span class="{classe}" aria-hidden="true">{cases}</span>'


def icone(racine: str, code: str, taille: int = 40) -> str:
    return f'<img class="icone" src="{racine}img/especes/{code}.svg" alt="" width="{taille}" height="{taille}">'


def credit_photo(c: dict) -> str:
    """« Photo : auteur, licence, Wikimedia Commons », avec les liens que la licence demande."""
    licence = f'<a href="{e(c["lien_licence"])}">{e(c["licence"])}</a>' if c.get("lien_licence") else e(c["licence"])
    return f'Photo : {e(c["auteur"])}, {licence}, <a href="{e(c["source"])}">Wikimedia Commons</a>'


def bandeau(sur_titre: str, titre: str, contenu: list[str] | None = None, fil: str = "") -> list[str]:
    """L'en-tête d'une page, dans la direction artistique de la une : fond chaud, sous-bois dessiné
    (style.css), sur-titre de rubrique, grand titre (`titre` : du HTML déjà échappé), puis
    `contenu` (lignes HTML : chapeau, date du calcul, phrase du jour, boutons)."""
    return (['  <header class="bandeau">'] + ([f"  {fil}"] if fil else [])
            + [f'  <p class="sur-titre">{e(sur_titre)}</p>', f"  <h1>{titre}</h1>"] + (contenu or [])
            + ["  </header>"])


# Le seul soutien du site : un lien simple, jamais le bouton ni le script de Buy Me a Coffee.
CAFE = "https://buymeacoffee.com/baptistesoulard"


def pied_site(racine: str) -> str:

    """Le pied de page commun à toutes les pages sauf la carte : le logo, ce que fait le site, le
    plan ; le sous-bois en fond (style.css). Entre marqueurs : les pages écrites à la main le
    reçoivent de `python -m champi.pages barre`."""
    plan = "\n".join(f'      <a href="{lien(racine, c)}">{t}</a>' for c, t in PLAN)
    return f"""{DEBUT_PIED}
<footer class="pied-site">
  <div class="pied-contenu">
    <a class="marque" href="{lien(racine, "./")}" aria-label="{NOM}, l'accueil">{svg_marque(34)}<span class="marque-nom">Champi<span>météo</span></span></a>
    <p class="pied-devise">Où les conditions sont réunies pour les champignons, forêt par forêt, d'après la
    pluie, le sol et la saison. Le site dit où chercher, jamais quoi manger.</p>
    <p class="pied-cafe">Sans publicité : <a href="{CAFE}">offrir un café</a> à son auteur.</p>
    <nav class="pied-plan" aria-label="Plan du site">
{plan}
    </nav>
  </div>
</footer>
{FIN_PIED}"""


def pied(racine: str) -> str:
    """Avertissement, pied de page commun, et `pages.js` (bouton Partager, département mémorisé)."""
    return f"""  <p class="alerte">Ne consommez jamais un champignon sans identification certaine : faites
  contrôler votre récolte par un pharmacien ou une société mycologique.
  <a href="{racine}avant-de-partir.html">Avant de partir</a>.</p>
</div>
{pied_site(racine)}
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


def chemins_statiques() -> list[str]:
    """Les pages écrites à la main qui vont au plan du site (la 404 n'y va pas), depuis la racine."""
    return [c.removesuffix("index.html") for c in STATIQUES if c != INTROUVABLE]


def ecrire_plan(site: Path, chemins: list[str], jour: date | None = None) -> None:
    """`sitemap.xml` et `robots.txt` quand le site est indexé ; sinon, ni plan ni robots.txt (les
    anciens s'effacent) : les balises `noindex` suffisent. Les couches d'habitat ne s'explorent pas.
    Les pages du matin (`chemins`) portent le `jour` de leur calcul ; les pages écrites à la main
    suivent, sans date (elles changent rarement)."""
    plan, robots = site / "sitemap.xml", site / "robots.txt"
    if INDEXER:
        date_maj = f"<lastmod>{jour.isoformat()}</lastmod>" if jour else ""
        plan.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                        + "".join(f"  <url><loc>{ADRESSE}{c}</loc>{date_maj}</url>\n" for c in chemins)
                        + "".join(f"  <url><loc>{ADRESSE}{c}</loc></url>\n"
                                  for c in chemins_statiques() if c not in chemins)
                        + "</urlset>\n", encoding="utf-8")
        robots.write_text(f"User-agent: *\nDisallow: /habitat/\n\nSitemap: {ADRESSE}sitemap.xml\n", encoding="utf-8")
    else:
        for f in (plan, robots):
            if f.exists():
                f.unlink()


if __name__ == "__main__":
    import sys
    from .config import SITE
    if sys.argv[1:] == ["barre"]:
        print("Barre réécrite :", ", ".join(ecrire_barres_statiques(SITE)) or "rien à changer")
    else:
        raise SystemExit("python -m champi.pages barre")

