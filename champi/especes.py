"""Les règles, espèce par espèce. C'est le seul fichier à modifier pour changer un seuil.

Chaque valeur est un ORDRE DE GRANDEUR tiré des guides de terrain et de la littérature
générale sur la fructification (références dans `REFERENCES`), pas un paramètre ajusté
sur les observations : avec une centaine de cèpes observés dans le département, les régler
sur les données serait du surapprentissage. Les observations servent à VÉRIFIER
(`validation.py`), jamais à régler.

Codes d'essence : `habitat.ESSENCES` ; codes de roche : `habitat.ROCHES`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Espece:
    code: str
    nom: str
    de: str          # « du cèpe », « de la girolle » : pour accorder les phrases
    latin: str
    # Saison : (début de la montée, début du plein, fin du plein, fin), en « MM-JJ ».
    saison: tuple[str, str, str, str]
    # Affinité (0-1) pour chaque essence dominante de la BD Forêt.
    essences: dict[int, float]
    # Affinité (0-1) pour la réaction de la roche : 1 calcaire, 2 siliceuse, 3 mixte, 0 inconnue.
    roches: dict[int, float]
    # Altitude (m) : nulle sous a0, pleine de a1 à a2, nulle au-dessus de a3.
    altitude: tuple[float, float, float, float]
    # Pluie déclenchante : cumul entre `pluie_jours[1]` et `pluie_jours[0]` jours avant.
    pluie_jours: tuple[int, int]
    # Nulle sous pluie_mm[0], pleine au-delà de pluie_mm[1].
    pluie_mm: tuple[float, float]
    # Température du sol (0-7 cm), moyenne des 7 jours précédents, en trapèze (°C).
    sol: tuple[float, float, float, float]
    # Facteur appliqué par jour de gel (Tmin < GEL_SEUIL) dans les 7 derniers jours.
    gel: float
    habitat_texte: str
    meteo_texte: str
    # Fiche du panneau : à quoi il ressemble. Jamais suffisant pour identifier (le site le dit).
    description: str = ""
    confusions: str = ""
    avertissement: str = ""
    limites: list[str] = field(default_factory=list)


# --- Paramètres communs à toutes les espèces ---------------------------------------

GRADIENT_AIR = 0.0065   # °C perdus par mètre d'altitude, air (valeur standard)
GRADIENT_SOL = 0.005    # °C par mètre, sol superficiel (un peu moins pentu que l'air)
SOLEIL_SOL = 2.0        # °C gagnés par le sol sur un versant plein sud à 90° (indice = 1)
SECHERESSE_SUD = 0.25   # part de la pluie « perdue » sur un versant plein sud (indice = 1)
GEL_SEUIL = -1.0        # °C, température minimale de l'air qui compte comme un jour de gel
FORET_OUVERTE = 0.8     # facteur pour une forêt ouverte (couvert clairsemé)
PENTE_DEBUT, PENTE_FIN, PENTE_PLANCHER = 30.0, 45.0, 0.2   # sols minces, terrain dangereux

ESPECES: list[Espece] = [
    Espece(
        code="cepe", nom="Cèpe", de="du cèpe", latin="Boletus edulis et cèpes proches",
        saison=("06-01", "07-15", "10-20", "11-30"),
        essences={0: 0.0, 1: 0.6, 2: 0.9, 3: 0.9, 4: 0.9, 5: 0.3, 6: 0.05, 7: 0.85, 8: 1.0,
                  9: 0.4, 10: 0.8, 11: 0.5, 12: 0.85, 13: 0.1, 14: 0.1},
        roches={0: 0.8, 1: 0.6, 2: 1.0, 3: 0.8},
        altitude=(200, 400, 1600, 2000),
        pluie_jours=(6, 20), pluie_mm=(15, 45),
        sol=(8, 12, 18, 23), gel=0.5,
        habitat_texte="Pessières et sapinières, hêtraies, chênaies et châtaigneraies ; sols "
                      "plutôt acides et bien drainés. Sur calcaire, il reste présent sous les "
                      "épicéas, dont les aiguilles acidifient l'humus.",
        meteo_texte="Une bonne pluie (40 à 50 mm sur deux semaines), puis une dizaine de "
                    "jours de douceur : la pousse suit la pluie d'une à trois semaines. "
                    "Le froid l'arrête, les premières gelées la terminent.",
        description="Chapeau brun clair à brun foncé, de 8 à 25 cm, épais, souvent bordé de "
                    "blanc. Dessous : des tubes (une éponge, pas de lames), blancs puis jaunes "
                    "puis vert olive. Pied ventru, blanchâtre à beige, couvert en haut d'un fin "
                    "réseau blanc. Chair blanche qui ne change pas de couleur à la coupe.",
        confusions="Bolet amer (Tylopilus felleus) : pores rosés, réseau brun foncé sur le "
                   "pied, saveur très amère. Bolets à pores rouges, dont certains toxiques "
                   "(bolet de Satan), et bolets dont la chair bleuit.",
    ),
    Espece(
        code="girolle", nom="Girolle", de="de la girolle", latin="Cantharellus cibarius et proches",
        saison=("06-01", "07-01", "10-01", "11-10"),
        essences={0: 0.0, 1: 0.6, 2: 0.9, 3: 0.9, 4: 0.9, 5: 0.3, 6: 0.05, 7: 0.9, 8: 0.9,
                  9: 0.4, 10: 0.7, 11: 0.5, 12: 0.8, 13: 0.1, 14: 0.1},
        roches={0: 0.8, 1: 0.5, 2: 1.0, 3: 0.8},
        altitude=(150, 300, 1500, 1900),
        pluie_jours=(7, 25), pluie_mm=(10, 35),
        sol=(9, 13, 20, 25), gel=0.5,
        habitat_texte="Hêtraies, chênaies, pessières et sapinières moussues, sur sols acides. "
                      "Elle revient aux mêmes endroits d'une année à l'autre.",
        meteo_texte="Moins exigeante que le cèpe : une pluie modérée suffit, et elle tient "
                    "plusieurs semaines quand le sol reste frais.",
        description="Jaune d'œuf à orangé, de 3 à 10 cm, en forme d'entonnoir à bord ondulé. "
                    "Dessous : des plis épais et fourchus qui descendent sur le pied, pas de "
                    "vraies lames. Chair blanche à jaunâtre, ferme, à l'odeur fruitée "
                    "(abricot). Pousse dans la mousse ou la litière, jamais sur le bois.",
        confusions="Clitocybe de l'olivier (Omphalotus), toxique : orange vif, vraies lames "
                   "fines, en touffes sur souches ou racines de feuillus. Fausse girolle "
                   "(Hygrophoropsis) : vraies lames orangées serrées, chair molle, sur débris "
                   "de résineux.",
    ),
    Espece(
        code="trompette", nom="Trompette de la mort", de="de la trompette", latin="Craterellus cornucopioides",
        saison=("07-15", "08-25", "11-01", "12-01"),
        essences={0: 0.0, 1: 0.7, 2: 1.0, 3: 0.7, 4: 0.5, 5: 0.3, 6: 0.05, 7: 0.7, 8: 0.35,
                  9: 0.1, 10: 0.2, 11: 0.2, 12: 0.3, 13: 0.05, 14: 0.05},
        roches={0: 0.8, 1: 1.0, 2: 0.6, 3: 0.85},
        altitude=(150, 300, 1200, 1600),
        pluie_jours=(7, 25), pluie_mm=(20, 50),
        sol=(6, 9, 16, 21), gel=0.5,
        habitat_texte="Hêtraies surtout, parfois chênaies, sur sols calcaires à neutres, "
                      "frais et argileux ; en troupes dans la litière des versants ombragés.",
        meteo_texte="Il lui faut beaucoup d'eau : elle sort tard, après les grosses pluies "
                    "de fin d'été, et supporte la fraîcheur d'automne.",
        description="Une trompette ou une corne d'abondance de 3 à 10 cm, creuse jusqu'à la "
                    "base, gris-noir à brun-noir à l'intérieur. Extérieur gris cendré, lisse ou "
                    "à peine ridé, sans lames. Chair mince et souple. Pousse en troupes, et se "
                    "confond avec les feuilles mortes : on la cherche à genoux.",
        confusions="Peu de sosies dangereux. La chanterelle sinueuse (Pseudocraterellus), "
                   "plus petite et plissée, est comestible ; un champignon noir à lames, à "
                   "pied plein ou poussant sur le bois n'est pas une trompette.",
        limites=["La BD Forêt n'isole le hêtre que sur une petite part du département ; "
                 "la plupart des hêtraies sont classées « feuillus en mélange » ou « forêt "
                 "mixte ». La carte de la trompette est donc plus floue que les autres."],
    ),
    Espece(
        code="pied_de_mouton", nom="Pied-de-mouton", de="du pied-de-mouton", latin="Hydnum repandum et H. rufescens",
        saison=("08-01", "09-01", "11-15", "12-20"),
        essences={0: 0.0, 1: 0.7, 2: 0.9, 3: 0.8, 4: 0.7, 5: 0.4, 6: 0.1, 7: 0.9, 8: 0.9,
                  9: 0.5, 10: 0.7, 11: 0.5, 12: 0.8, 13: 0.1, 14: 0.1},
        roches={0: 0.9, 1: 1.0, 2: 0.85, 3: 1.0},
        altitude=(150, 300, 1500, 1900),
        pluie_jours=(7, 25), pluie_mm=(15, 40),
        sol=(3, 6, 14, 20), gel=0.75,
        habitat_texte="Presque toutes les forêts, feuillus comme conifères, sur sols calcaires "
                      "comme acides ; souvent en cercles ou en lignes.",
        meteo_texte="L'espèce de l'arrière-saison : elle résiste aux premières gelées et "
                    "pousse encore quand le sol est descendu sous 8 °C.",
        description="Chapeau crème à orangé pâle, de 4 à 15 cm, charnu et bosselé. Dessous : "
                    "des aiguillons (petites pointes serrées) qui se détachent sous le doigt, "
                    "ni lames ni tubes. Pied court, blanc, souvent décentré. Chair blanche et "
                    "cassante, qui jaunit au toucher. L'hydne roussissant (H. rufescens) est "
                    "plus petit et plus roux.",
        confusions="Peu de sosies grâce aux aiguillons. Les hydnes bruns ou écailleux "
                   "(Sarcodon), plus foncés et souvent amers, ne sont pas des pieds-de-mouton.",
    ),
    Espece(
        code="morille", nom="Morille", de="de la morille", latin="Morchella spp.",
        saison=("03-01", "04-01", "05-20", "06-30"),
        essences={0: 0.0, 1: 0.8, 2: 0.3, 3: 0.4, 4: 0.2, 5: 0.6, 6: 1.0, 7: 0.5, 8: 0.5,
                  9: 0.6, 10: 0.4, 11: 0.4, 12: 0.5, 13: 0.2, 14: 0.8},
        roches={0: 0.7, 1: 1.0, 2: 0.4, 3: 0.8},
        altitude=(150, 300, 1300, 1800),
        pluie_jours=(3, 21), pluie_mm=(10, 30),
        sol=(5, 8, 13, 17), gel=0.6,
        habitat_texte="Bords de rivières, frênaies, peupleraies et vergers en plaine ; "
                      "en montagne, clairières, coupes et lisières de résineux, souvent sur "
                      "calcaire. Elle suit les perturbations (coupes, chantiers, brûlis).",
        meteo_texte="Au printemps, quand le sol se réchauffe vers 8 à 12 °C après la fonte "
                    "des neiges, avec de l'humidité ; un retour du gel la stoppe.",
        description="Chapeau conique à arrondi, de 5 à 15 cm, creusé d'alvéoles comme une "
                    "éponge, séparées par des côtes ; beige, jaune, gris ou brun noir selon "
                    "l'espèce. Pied blanchâtre et granuleux, soudé au chapeau. Coupée en deux, "
                    "elle est entièrement creuse : une seule cavité du sommet à la base.",
        confusions="Gyromitre (Gyromitra esculenta), MORTELLE : chapeau brun-rouge en "
                   "circonvolutions de cerveau, sans alvéoles, intérieur cloisonné en plusieurs "
                   "cavités. Verpe ou morillon : chapeau posé comme une cloche, libre du pied. "
                   "La morille elle-même est toxique crue ou mal cuite.",
        limites=["Ses milieux de prédilection (frênes, ripisylves, coupes récentes, brûlis) "
                 "sont mal décrits par la BD Forêt : l'habitat de la morille est le moins "
                 "fiable des cinq."],
    ),
]

PAR_CODE = {e.code: e for e in ESPECES}

REFERENCES = [
    "Courtecuisse R. et Duhem B., Guide des champignons de France et d'Europe, Delachaux et Niestlé.",
    "Eyssartier G. et Roux P., Le guide des champignons France et Europe, Belin.",
    "Kauserud H. et al. (2008), Mushroom fruiting and climate change, PNAS 105(10).",
    "Boddy L. et al. (2014), Climate variation effects on fungal fruiting, Fungal Ecology 10.",
    "Phillips S. J. et al. (2009), Sample selection bias and presence-only distribution models, "
    "Ecological Applications 19(1) : fond « groupe cible » de la validation.",
    "Maclure M. (1991), The case-crossover design, American Journal of Epidemiology 133(2) : "
    "plan « cas-croisé » de la validation météo.",
]


def en_json() -> dict:
    """Les règles telles que le site les affiche (page Méthode, fenêtre d'une case)."""
    return {
        "especes": [asdict(e) for e in ESPECES],
        "communs": {
            "gradient_air": GRADIENT_AIR, "gradient_sol": GRADIENT_SOL,
            "soleil_sol": SOLEIL_SOL, "secheresse_sud": SECHERESSE_SUD,
            "gel_seuil": GEL_SEUIL, "foret_ouverte": FORET_OUVERTE,
            "pente": [PENTE_DEBUT, PENTE_FIN, PENTE_PLANCHER],
        },
        "references": REFERENCES,
    }
