"""Accueil, « en ce moment » et fiches espèces : phrases et garde-fous, sur des résumés fabriqués."""
import json
import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from champi import especes as E
from champi import pages
from champi import pages_accueil as A
from champi import carte_departements, pages_departements, pages_especes, partage
from champi.grille import Grille
from champi.habitat import ESSENCES, ROCHES
from champi.modele import CLASSES
from champi.redaction import NBSP

ROBOTS = "index, follow" if pages.INDEXER else "noindex, nofollow"

SITE = Path(__file__).resolve().parent.parent / "site"
JOURS = [date(2026, 11, 1) + timedelta(days=k) for k in range(8)]
REGLES = E.en_json()
ESPECES = REGLES["especes"]
LEGENDES = {"essences": ESSENCES, "roches": ROCHES}
DEPS = [{"code": "85", "nom": "Vendée"}, {"code": "2A", "nom": "Corse-du-Sud"}, {"code": "01", "nom": "Ain"}]
GENERE_LE = "2026-11-01T05:20+00:00"


def jour(niveau, indice=0.5, saison=1.0, debut=False):
    return {"niveau": niveau, "verdict": "Verdict", "phrases": ["Une phrase."], "indice_moyen": indice,
            "communes": [], "saison": saison, "debut_saison": debut}


def resumes(par_dep: dict) -> dict:
    """`{département: {espèce: [niveaux des 8 jours]}}` ; une espèce absente est hors saison."""
    return {d["code"]: {x["code"]: [jour(n, indice=0.9 if d["code"] == "85" else 0.3)
                                    for n in par_dep.get(d["code"], {}).get(x["code"], [0] * 8)]
                        for x in ESPECES} for d in DEPS}


NOMS = {d["code"]: d["nom"] for d in DEPS}


def test_national_par_niveau_les_mieux_places_d_abord():
    r = resumes({"01": {"cepe": [4] * 8}, "85": {"cepe": [4] * 8}, "2A": {"cepe": [3] * 8}})
    nat = pages.national(ESPECES, DEPS, r, 8)
    assert nat["cepe"][0][4] == ["85", "01"]          # sans surface : Vendée (indice 0,9), puis l'Ain (0,3)
    assert nat["cepe"][0][3] == ["2A"] and nat["morille"][0][0] == ["85", "01", "2A"]
    # Avec la surface : le plus de forêt aux bonnes conditions d'abord, pas le meilleur indice
    # moyen (un département à peine boisé le gagne avec quelques bois).
    for k in range(8):
        r["85"]["cepe"][k].update(part_bon=0.9, km2=40.0)        # 36 km² bons
        r["01"]["cepe"][k].update(part_bon=0.3, km2=1500.0)      # 450 km² bons
    assert pages.national(ESPECES, DEPS, r, 8)["cepe"][0][4] == ["01", "85"]


def test_etat_espece():
    r = resumes({"85": {"cepe": [4] * 8}, "01": {"cepe": [4, 4, 4, 4, 4, 4, 4, 4]},
                 "2A": {"cepe": [1, 1, 1, 4, 4, 1, 1, 1], "girolle": [1, 1, 2, 4, 4, 4, 1, 1]}})
    nat = pages.national(ESPECES, DEPS, r, 8)
    cepe = A.etat_espece(nat["cepe"], JOURS, NOMS)
    assert cepe.startswith('bonnes conditions dans 2 départements ('       # « surtout » au-delà de trois
                           '<a href="departements/85.html">Vendée</a> et <a href="departements/01.html">Ain</a>)')
    assert cepe.endswith(", et jusqu'à 3 mercredi 4 novembre")
    girolle = A.etat_espece(nat["girolle"], JOURS, NOMS)
    assert girolle == "conditions défavorables partout aujourd'hui ; bonnes conditions dès mercredi 4 novembre " \
                      "dans 1 département"
    assert A.etat_espece(nat["morille"], JOURS, NOMS) == "hors saison partout"


def test_ce_matin_les_mieux_placees_d_abord():
    r = resumes({"85": {"girolle": [3] * 8, "cepe": [4] * 8}, "01": {"trompette": [2] * 8}})
    lignes = A.ce_matin(ESPECES, pages.national(ESPECES, DEPS, r, 8), {"cepe": "Fin de saison."}, JOURS, NOMS)
    assert lignes[0].startswith('<a href="especes/cepe.html">Cèpe</a> : bonnes conditions dans 1 département')
    assert lignes[0].endswith(". Fin de saison.")
    assert lignes[1].startswith('<a href="especes/girolle.html">Girolle</a> : bonnes conditions par endroits')
    assert "pousse possible dans 1 département, sans plus" in lignes[2]
    assert lignes[-1].startswith("Hors saison partout : le bolet bai, ") and "la morille" in lignes[-1]


def test_phase_de_saison():
    pleine = [jour(4)] * 3
    fin = [jour(3, saison=0.4)] * 2 + [jour(4)]
    debut = [jour(2, saison=0.5, debut=True)] * 3
    assert A.phase(pleine) is None and A.phase([]) is None
    assert A.phase(fin) == "Fin de saison." and A.phase(debut) == "Début de saison."


def test_preuve_chiffres_de_la_validation():
    v = {"periode": [1995, 2026], "regions": {"france": {"especes": {
        "cepe": {"observations": 1200, "habitat": {"auc": 0.633, "auc_foret": 0.61, "ic_ecart": [0.01, 0.04]},
                 "meteo": {"auc_saison": 0.646, "auc_calendrier": 0.578, "ic_ecart": [0.05, 0.08]}},
        "morille": {"observations": 500, "habitat": {"n": 12},
                    "meteo": {"auc_saison": 0.678, "auc_calendrier": 0.701, "ic_ecart": [-0.06, 0.02]}}}}}}
    html = "\n".join(A.preuve(ESPECES, v))
    assert "vérifiées sur 1\u00a0700 observations datées de toute la France (GBIF, 1995 à 2026)" in html
    assert "Pour 1 espèce sur 2, la météo" in html and "pour 1 sur 1 (les espèces de forêt" in html
    assert "63 % (forêt seule : 61 %)" in html and "65 % (calendrier seul : 58 %)" in html
    assert "trop peu de cas" in html                            # la morille, sans test d'habitat
    assert A.preuve(ESPECES, None) == ["  <p>La vérification face aux observations n'est pas encore publiée.</p>"]


def test_faq_fenetres_de_pluie_des_regles():
    texte = " ".join(A.faq(ESPECES))
    assert "du 20e au 6e jour avant pour le cèpe" in texte
    assert "du 21e au 3e jour avant pour la morille" in texte


def test_accueil():
    r = resumes({"85": {"cepe": [4] * 8}})
    nat = pages.national(ESPECES, DEPS, r, 8)
    page = A.page_accueil(DEPS, ESPECES, nat, {}, JOURS, None, GENERE_LE)
    assert f'<meta name="robots" content="{ROBOTS}">' in page
    assert "<h1>Où chercher les champignons cette semaine</h1>" in page
    tete, corps = page.split("</head>")
    assert "l.replace(\"carte/\" + l.search + l.hash)" in tete           # anciens liens : vers la carte
    assert '<link rel="manifest" href="manifest.webmanifest">' in tete
    assert '<a class="bouton principal" href="carte/" data-une-lien>Voir la carte</a>' in corps
    assert re.findall(r'data-departement="(\w+)"', corps) == ["01", "2A", "85"]   # par numéro


def test_carte_de_la_une():
    """La une propose les espèces aux bonnes conditions (au moins par endroits), la mieux placée
    d'abord et montrée sans JavaScript, puis « Toutes » ; les contours mènent à la carte de
    l'espèce sur chaque département."""
    r = resumes({"85": {"cepe": [4] * 8, "girolle": [3] * 8, "trompette": [2] * 8}, "01": {"cepe": [4] * 8}})
    nat = pages.national(ESPECES, DEPS, r, 8)
    assert [x["code"] for x in A.especes_de_la_une(ESPECES, nat)] == ["cepe", "girolle"]
    contours = carte_departements.charger()
    page = A.page_accueil(DEPS, ESPECES, nat, {}, JOURS, None, GENERE_LE, contours=contours)
    assert A.carre_km() == 6
    assert f"le verdict des forêts de chaque carré de 6{NBSP}km, comme pour les départements." in page
    assert re.findall(r'<span class="pastille n(\d)"></span>', page.split('class="une-carte"')[1])[:5] == list("43210")
    une = page.split('<figure class="une-carte">')[1].split("</figure>")[0]
    assert re.findall(r'data-une="(\w+)" aria-pressed="(\w+)"', une) == [
        ("cepe", "true"), ("girolle", "false"), ("toutes", "false")]
    assert "data-une-especes hidden" in une
    assert re.search(r'<a class="une-fond" href="carte/\?espece=cepe"><img src="data/partage/carte-france-cepe\.png\?v=\d+"',
                     une)
    assert re.findall(r'<a href="carte/\?departement=(\w+)&amp;espece=cepe" data-dep', une) == ["01", "2A", "85"]
    assert "<title>Vendée : bonnes conditions</title>" in une and "<title>Corse-du-Sud : hors saison</title>" in une
    box = carte_departements.cadre_une(contours)[0]
    assert f'height="{round(partage.LARGEUR_UNE * box[3] / box[2])}"' in une
    assert f'<svg viewBox="-16 -16 {contours["largeur"] + 32} {contours["hauteur"] + 32}"' in une
    assert not liens_imbriques(une)
    donnees = json.loads(re.search(r'<script type="application/json" id="une-donnees">(.+?)</script>', page).group(1))
    assert donnees["defaut"] == "cepe" and donnees["ordre"] == ["01", "2A", "85"]
    assert donnees["vues"]["cepe"]["niveaux"] == "404" and donnees["vues"]["girolle"]["niveaux"] == "003"
    assert donnees["vues"]["toutes"]["niveaux"] == "404" and donnees["vues"]["toutes"]["espece"] == ""
    assert donnees["vues"]["toutes"]["image"].startswith("data/partage/carte-france.png?v=")
    # Sans contours (ancien fichier, sans cadre) : la carte et les boutons, sans dessin par-dessus.
    sans = A.page_accueil(DEPS, ESPECES, nat, {}, JOURS, None, GENERE_LE, contours=None)
    assert "<svg" not in sans.split('<figure class="une-carte">')[1].split("</figure>")[0]
    assert "data-une-especes" in sans


def test_une_hors_saison_partout():
    """Tout hors saison : pas de boutons, la carte de toutes les espèces."""
    nat = pages.national(ESPECES, DEPS, resumes({}), 8)
    page = A.page_accueil(DEPS, ESPECES, nat, {}, JOURS, None, GENERE_LE, contours=carte_departements.charger())
    assert "data-une-especes" not in page and "une-donnees" not in page
    assert '<img src="data/partage/carte-france.png?v=' in page


def test_renvoi_des_anciens_liens():
    """La règle du script de l'accueil, rejouée : les paramètres de la carte et le lien de
    groupe partent vers carte/, pas un paramètre ajouté par un réseau social."""
    script = A.RENVOI
    carte = re.search(r"/\[\?&\]\((.+?)\)=/", script).group(1).split("|")
    groupe = re.search(r"/\(\^#\|&\)\((.+?)\)=/", script).group(1).split("|")
    assert set(carte) == {"departement", "espece", "jour"} and set(groupe) == {"depot", "jeton"}


def test_fiches_especes():
    r = resumes({"85": {"cepe": [4] * 8}})
    nat = pages.national(ESPECES, DEPS, r, 8)
    cepe = next(x for x in ESPECES if x["code"] == "cepe")
    page = pages_especes.page_espece(cepe, REGLES["communs"], LEGENDES, nat["cepe"], JOURS, NOMS, None, GENERE_LE)
    assert "<title>Cèpe (Boletus edulis et cèpes proches) : où et quand le chercher en France</title>" in page
    assert "Ces lignes aident à chercher, jamais à identifier." in page
    assert "pleine du 15 juillet au 20 octobre, possible du 1er juin au 30 novembre" in page
    assert "du 20e au 6e jour avant" in page and "pH de 4 à 6,5 au mieux" in page
    assert 'href="../carte/?espece=cepe"' in page and 'href="../departements/85.html"' in page
    trompette = next(x for x in ESPECES if x["code"] == "trompette")
    page = pages_especes.page_espece(trompette, REGLES["communs"], LEGENDES, nat["trompette"], JOURS, NOMS, None,
                                     GENERE_LE)
    assert "Roche favorable : calcaire" in page and "Hors saison partout aujourd'hui" in page
    assert "Forêts favorables : hêtre." in page


def test_ce_qui_est_habituel_a_cote_du_verdict():
    """« Météo favorable 7 années sur 10 à cette date » sur la vignette, l'accueil et la fiche ;
    rien pour une espèce hors saison, ni sans mesure."""
    r = resumes({"85": {"cepe": [4] * 8, "pied_de_mouton": [4] * 8}})
    nat = pages.national(ESPECES, DEPS, r, 8)
    mesure = {"cepe": 0.14, "pied_de_mouton": 0.74, "morille": 0.0}
    especes = [dict(x, habituel=mesure.get(x["code"])) for x in ESPECES]
    index = pages_especes.page_index(especes, nat, JOURS, NOMS, GENERE_LE)
    assert '<span class="habituel">Météo favorable 7 années sur 10 à cette date</span>' in index
    assert '<span class="habituel">Météo favorable 1 année sur 10 à cette date</span>' in index
    assert "rarement favorable" not in index                    # la morille, hors saison : rien
    accueil = A.page_accueil(DEPS, especes, nat, {}, JOURS, None, GENERE_LE)
    assert '<p class="habituel">Météo favorable 7 années sur 10 à cette date.</p>' in accueil
    cepe = next(x for x in especes if x["code"] == "cepe")
    fiche = pages_especes.page_espece(cepe, REGLES["communs"], LEGENDES, nat["cepe"], JOURS, NOMS, None, GENERE_LE)
    assert "Météo favorable 1 année sur 10 à cette date, d'après trente ans de météo passée" in fiche
    assert 'href="../methode.html#habituel"' in fiche
    assert "habituel" not in pages_especes.page_index(ESPECES, nat, JOURS, NOMS, GENERE_LE)


def test_fiche_d_une_espece_des_pres():
    """Pas de carte fine : ni bouton vers la carte, ni essences ; ses milieux, le propriétaire."""
    r = resumes({"85": {"rose_pres": [4] * 8}})
    nat = pages.national(ESPECES, DEPS, r, 8)
    rose = next(x for x in ESPECES if x["code"] == "rose_pres")
    page = pages_especes.page_espece(rose, REGLES["communs"], LEGENDES, nat["rose_pres"], JOURS, NOMS, None, GENERE_LE)
    assert "../carte/?espece=rose_pres" not in page and "Forêts favorables" not in page
    assert "Milieux favorables : prairies." in page and "Pas de carte des prés" in page
    assert "le plus de prés favorables d'abord" in page and "demandez son accord" in page
    assert '<a class="bouton principal" href="../en-ce-moment.html#rose_pres">' in page
    oronge = next(x for x in ESPECES if x["code"] == "oronge")
    assert pages_especes.pronom(oronge) == "elle"
    hygrophore = next(x for x in ESPECES if x["code"] == "hygrophore_mars")
    page = pages_especes.page_espece(hygrophore, REGLES["communs"], LEGENDES, nat["hygrophore_mars"], JOURS, NOMS,
                                     None, GENERE_LE)
    assert "plus du tout sous 300" in page and "Pas de plancher" not in page


def test_pages_generees_completes_et_liens_valides(tmp_path):
    """Toutes les pages du matin et leurs images, écrites à côté du site : chaque lien mène à
    une page ou une image écrite, ou à un fichier du site, et aucune page n'est indexée."""
    r = resumes({"85": {"cepe": [4] * 8, "girolle": [3] * 8}, "01": {"bolet_bai": [2] * 8}})
    chemins = pages_departements.ecrire(tmp_path, DEPS, ESPECES, r, JOURS, GENERE_LE)
    chemins += A.ecrire(tmp_path, DEPS, ESPECES, r, JOURS, GENERE_LE, None)
    chemins += pages_especes.ecrire(tmp_path, DEPS, REGLES, LEGENDES, r, JOURS, GENERE_LE, None)
    assert len(chemins) == (1 + len(DEPS)) + 2 + (1 + len(ESPECES))
    codes = np.full((30, 30), 100, dtype=np.uint8)                # une bande de forêt par département
    pixel_dep = np.repeat(np.arange(3, dtype=np.int16), 300)
    cadre = carte_departements.charger()["cadre"]
    grille = Grille(cadre[0], cadre[3], (cadre[2] - cadre[0]) / 30, 30, 30)
    niveaux = np.full((30, 30), 3, dtype=np.int8)
    partage.ecrire(tmp_path / "data" / "partage", DEPS, {d["code"]: k for k, d in enumerate(DEPS)}, ESPECES, r,
                   pages.national(ESPECES, DEPS, r, 8), JOURS, codes, pixel_dep, 200, [s for s, _ in CLASSES],
                   une={x["code"]: niveaux for x in ESPECES}, grille=grille, cadre=cadre)
    for page in tmp_path.rglob("*.html"):
        html = page.read_text(encoding="utf-8")
        assert f'<meta name="robots" content="{ROBOTS}">' in html, page
        assert not re.search(r'<script[^>]+src="https?://', html)
        image = re.search(rf'<meta property="og:image" content="{re.escape(pages.ADRESSE)}([^"?]+)\?v=\d+">', html)
        assert image and (tmp_path / image.group(1)).exists(), page
        for cible in re.findall(r'(?:href|src)="([^"#:?]+)["#?]', html):
            chemin = (page.parent / cible).resolve()
            rel = chemin.relative_to(tmp_path.resolve())
            assert chemin.exists() or (SITE / rel).exists(), f"{page.relative_to(tmp_path)} → {cible}"
        assert not liens_imbriques(html), f"{page.relative_to(tmp_path)} : un lien dans un lien"
    # Les pages du jour se datent : pages.js prévient quand la mise à jour de la nuit manque.
    for nom in ("index.html", "en-ce-moment.html", "departements/index.html", "departements/85.html"):
        html = (tmp_path / nom).read_text(encoding="utf-8")
        assert html.count(f'data-premier-jour="{JOURS[0].isoformat()}"') == 1, nom


def liens_imbriques(html: str) -> list[str]:
    """Les liens ouverts dans un lien : le navigateur coupe alors la fiche en morceaux (bug du
    2026-11-01 sur la page des espèces, le crédit d'une photo dans une fiche cliquable)."""
    from html.parser import HTMLParser

    class Lecteur(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ouverts, self.fautes = 0, []

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                if self.ouverts:
                    self.fautes.append(dict(attrs).get("href", ""))
                self.ouverts += 1

        def handle_endtag(self, tag):
            if tag == "a":
                self.ouverts = max(0, self.ouverts - 1)

    lecteur = Lecteur()
    lecteur.feed(html)
    return lecteur.fautes


def test_le_controle_des_liens_imbriques_marche():
    assert liens_imbriques('<a href="x"><figure><a href="y">licence</a></figure></a>') == ["y"]
    assert liens_imbriques('<a href="x">un</a> <a href="y">deux</a>') == []
