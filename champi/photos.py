"""Les photos des espèces : l'image principale de l'article de Wikipédia en français, tirée de
Wikimedia Commons, réduite à 480 pixels de large (`site/img/especes/<code>.jpg`), avec son auteur
et sa licence (`data/photos.json`, versionné) : chaque page qui montre une photo la crédite.

    python -m champi.photos            # réseau, quelques secondes ; à relancer pour une espèce ajoutée

Seules les licences libres sont retenues (Creative Commons BY ou BY-SA, CC0, domaine public) :
une autre licence, et l'espèce garde son seul dessin. Une photo aide à chercher, jamais à
identifier : les pages le disent à côté.
"""
from __future__ import annotations

import html
import io
import json
import re

from PIL import Image

from . import especes as E
from .config import DATA, SITE
from .sources import http_get

FICHIER = DATA / "photos.json"
DOSSIER = SITE / "img" / "especes"
LARGEUR = 480
WIKIPEDIA = "https://fr.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
# L'article de chaque espèce ; l'image de son infobox a été choisie par les rédacteurs.
ARTICLES = {
    "cepe": "Cèpe de Bordeaux", "bolet_bai": "Bolet bai", "girolle": "Girolle",
    "trompette": "Trompette de la mort", "pied_de_mouton": "Hydnum repandum",
    "lactaire": "Lactaire délicieux", "morille": "Morchella esculenta",
    "chanterelle_tube": "Chanterelle en tube", "oronge": "Amanite des Césars",
    "hygrophore_mars": "Hygrophore de mars", "coulemelle": "Coulemelle", "rose_pres": "Rosé des prés",
}
LIBRES = re.compile(r"^(CC[ -]BY(-SA)?( \d\.\d)?|CC0|Public domain|Domaine public)", re.I)


def image_de_l_article(titre: str) -> str | None:
    r = http_get(WIKIPEDIA, {"action": "query", "prop": "pageimages", "piprop": "name", "titles": titre,
                             "redirects": 1, "format": "json", "formatversion": 2}, attendre_json=True)
    pages = r["query"]["pages"]
    return pages[0].get("pageimage") if pages else None


def texte(valeur: str) -> str:
    """Un champ de Commons (souvent du HTML) en texte simple."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", valeur or ""))).strip()


def recuperer(code: str, titre: str) -> dict | None:
    nom = image_de_l_article(titre)
    if not nom:
        print(f"  {code} : pas d'image dans l'article « {titre} »")
        return None
    r = http_get(COMMONS, {"action": "query", "prop": "imageinfo", "iiprop": "url|extmetadata|mime",
                           "iiurlwidth": LARGEUR, "titles": f"File:{nom}", "format": "json", "formatversion": 2},
                 attendre_json=True)
    info = r["query"]["pages"][0]["imageinfo"][0]
    meta = info.get("extmetadata", {})
    licence = texte(meta.get("LicenseShortName", {}).get("value", ""))
    if not LIBRES.match(licence):
        print(f"  {code} : licence « {licence} » écartée ({nom})")
        return None
    image = Image.open(io.BytesIO(http_get(info["thumburl"]).content)).convert("RGB")
    DOSSIER.mkdir(parents=True, exist_ok=True)
    image.save(DOSSIER / f"{code}.jpg", quality=78, optimize=True, progressive=True)
    return {"fichier": nom, "auteur": texte(meta.get("Artist", {}).get("value", "")) or "auteur inconnu",
            "licence": licence, "lien_licence": meta.get("LicenseUrl", {}).get("value", ""),
            "source": info["descriptionurl"], "largeur": image.width, "hauteur": image.height}


def construire() -> dict:
    connues = json.loads(FICHIER.read_text(encoding="utf-8")) if FICHIER.exists() else {}
    for e in E.ESPECES:
        if e.code in connues and (DOSSIER / f"{e.code}.jpg").exists():
            continue
        credit = recuperer(e.code, ARTICLES[e.code])
        if credit:
            connues[e.code] = credit
            print(f"  {e.code} : {credit['fichier']} ({credit['auteur']}, {credit['licence']})")
    FICHIER.write_text(json.dumps(connues, ensure_ascii=False, indent=1), encoding="utf-8")
    return connues


def charger() -> dict:
    return json.loads(FICHIER.read_text(encoding="utf-8")) if FICHIER.exists() else {}


if __name__ == "__main__":
    construire()
