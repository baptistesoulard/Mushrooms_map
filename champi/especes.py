"""Les règles, espèce par espèce. C'est le seul fichier à modifier pour changer un seuil.

Chaque valeur est un ORDRE DE GRANDEUR tiré des guides de terrain et de la littérature
générale sur la fructification (références dans `REFERENCES`), pas un paramètre ajusté
sur les observations : avec une centaine de cèpes observés dans le département, les régler
sur les données serait du surapprentissage. Les observations servent à VÉRIFIER
(`validation.py`), jamais à régler.

Codes d'essence : `habitat.ESSENCES` ; codes de roche : `habitat.ROCHES` ; milieux des prés :
`prairies.MILIEUX`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Espece:
    code: str
    nom: str
    de: str          # « du cèpe », « de la girolle » : pour accorder les phrases
    latin: str
    # Saison : (début de la montée, début du plein, fin du plein, fin), en « MM-JJ », à la
    # latitude de référence ; décalée ailleurs par la loi de Hopkins (`modele.dates_saison`).
    saison: tuple[str, str, str, str]
    # Affinité (0-1) pour chaque essence dominante de la BD Forêt.
    essences: dict[int, float]
    # Affinité (0-1) pour la réaction de la roche : 1 calcaire, 2 siliceuse, 3 mixte, 0 inconnue.
    roches: dict[int, float]
    # Plafond d'altitude (m) à la latitude de référence : pleine jusqu'à altitude[0], nulle
    # au-dessus de altitude[1] ; il monte vers le sud (`modele.plafond_altitude`). Le plancher
    # (`plancher`, plus bas) ne sert qu'aux espèces montagnardes.
    altitude: tuple[float, float]
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
    # Repère de terrain tiré des guides : un indice pour chercher, jamais une règle du calcul.
    repere: str = ""
    avertissement: str = ""
    limites: list[str] = field(default_factory=list)
    # pH du sol (0-5 cm, SoilGrids) : trapèze (nul sous [0], plein de [1] à [2], nul au-dessus
    # de [3]) relevé à `ph_plancher` : hors de ses préférences, une espèce se raréfie sans
    # disparaître. Avec `sol_ph`, il remplace l'affinité pour la roche là où il est connu.
    ph: tuple[float, float, float, float] = (0.0, 0.0, 14.0, 14.0)
    ph_plancher: float = 1.0
    sol_ph: bool = False
    # Plancher d'altitude (m) à la latitude de référence, pour une espèce de montagne : nulle sous
    # plancher[0], pleine dès plancher[1] ; il monte vers le sud comme le plafond. (0, 0) : aucun,
    # l'espèce pousse jusqu'au niveau de la mer (Landes, Sologne, Bretagne).
    plancher: tuple[float, float] = (0.0, 0.0)
    # Le genre, quand l'article élidé ne le dit pas (« de l'oronge ») ; sinon « de la » = féminin.
    feminin: bool | None = None
    # « foret » : la carte à 50 m. « pre » : une espèce des champs, calculée sur l'échantillon des
    # prés (`prairies.py`) et publiée par département et par commune seulement, jamais case par
    # case (les prés sont presque tous privés). Ses affinités vont aux milieux de Corine Land
    # Cover (`prairies.MILIEUX`, codes 1 à 5) au lieu des essences et des roches.
    milieu: str = "foret"
    prairies: dict[int, float] = field(default_factory=dict)


# --- Paramètres communs à toutes les espèces ---------------------------------------

GRADIENT_AIR = 0.0065   # °C perdus par mètre d'altitude, air (valeur standard)
GRADIENT_SOL = 0.005    # °C par mètre, sol superficiel (un peu moins pentu que l'air)
SOLEIL_SOL = 2.0        # °C gagnés par le sol sur un versant plein sud à 90° (indice = 1)
SECHERESSE_SUD = 0.25   # part de la pluie « perdue » sur un versant plein sud (indice = 1)
GEL_SEUIL = -1.0        # °C, température minimale de l'air qui compte comme un jour de gel
FORET_OUVERTE = 0.8     # facteur pour une forêt ouverte (couvert clairsemé)
PENTE_DEBUT, PENTE_FIN, PENTE_PLANCHER = 30.0, 45.0, 0.2   # sols minces, terrain dangereux
# pH du sol (SoilGrids) à la place de la roche : pour les espèces des sols acides seulement
# (`sol_ph`). SoilGrids distingue bien les sols acides mais tasse les calcaires vers 6 : une règle
# calcicole n'y atteint pas son seuil, l'espèce garde la roche. Mesuré le 2026-11-01 (validation,
# « pH du sol au lieu de la roche ») : gain pour le cèpe, le bolet bai et la girolle, perte pour
# la trompette, rien de net pour les autres.
# RÈGLE pour toute espèce, nouvelle comprise : `sol_ph` si son optimum de pH s'arrête à
# PH_ACIDE_MAX ou en dessous (ph[2]), la roche sinon. Elle redonne les sept décisions mesurées et
# vaut pour SoilGrids seulement (tests/test_modele.py la vérifie fiche par fiche).
PH_ACIDE_MAX = 6.5

# Les saisons et les plafonds d'altitude ont été écrits pour la Haute-Savoie (46° N). Ailleurs,
# la loi bioclimatique de Hopkins (1918) : un degré de latitude vaut environ 4 jours de
# décalage des saisons et 122 m (400 pieds) d'altitude. Ordre de grandeur, pas un réglage.
LATITUDE_REF = 46.0
HOPKINS_JOURS = 4.0     # jours par degré : printemps plus tard, automne plus tôt vers le nord
HOPKINS_METRES = 122.0  # mètres par degré : plafond plus haut vers le sud

ESPECES: list[Espece] = [
    Espece(
        code="cepe", nom="Cèpe", de="du cèpe", latin="Boletus edulis et cèpes proches",
        saison=("06-01", "07-15", "10-20", "11-30"),
        essences={0: 0.0, 1: 0.6, 2: 0.9, 3: 0.9, 4: 0.9, 5: 0.3, 6: 0.05, 7: 0.85, 8: 1.0,
                  9: 0.4, 10: 0.8, 11: 0.5, 12: 0.85, 13: 0.1, 14: 0.1},
        roches={0: 0.8, 1: 0.6, 2: 1.0, 3: 0.8},
        altitude=(1600, 2000),
        pluie_jours=(6, 20), pluie_mm=(15, 45),
        sol=(8, 12, 18, 23), gel=0.5,
        ph=(3.5, 4.0, 6.5, 7.8), ph_plancher=0.5, sol_ph=True,
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
        repere="L'amanite tue-mouches (chapeau rouge à flocons blancs, toxique) vit avec les "
               "mêmes bouleaux, épicéas et pins, et sort en même temps à l'automne : visible de "
               "loin, elle signale un coin où chercher. Sous les chênes, sur calcaire et pour le "
               "cèpe d'été, où elle est rare, son absence ne dit rien. La BD Forêt n'a pas de "
               "classe « bouleau » : la carte note ces bois comme des feuillus en mélange.",
    ),
    Espece(
        code="bolet_bai", nom="Bolet bai", de="du bolet bai", latin="Imleria badia",
        saison=("07-15", "09-01", "11-10", "12-10"),
        essences={0: 0.0, 1: 0.6, 2: 0.7, 3: 0.8, 4: 0.9, 5: 0.3, 6: 0.05, 7: 0.9, 8: 1.0,
                  9: 0.4, 10: 0.9, 11: 0.6, 12: 0.9, 13: 0.1, 14: 0.1},
        roches={0: 0.8, 1: 0.2, 2: 1.0, 3: 0.6},
        altitude=(1600, 2000),
        pluie_jours=(7, 25), pluie_mm=(15, 40),
        sol=(6, 10, 17, 22), gel=0.6,
        ph=(3.0, 3.5, 5.5, 7.0), ph_plancher=0.2, sol_ph=True,
        habitat_texte="Bois acides de résineux comme de feuillus : épicéas, pins, châtaigniers, "
                      "chênes, hêtres ; souvent dans la mousse, au pied des souches. Il fuit le "
                      "calcaire.",
        meteo_texte="Plus tardif et moins frileux que le cèpe : il suit les pluies de fin d'été "
                    "et tient jusqu'aux premières gelées, en grosses poussées les automnes humides.",
        description="Chapeau brun châtain à brun chocolat, de 4 à 15 cm, mat et velouté par temps "
                    "sec, collant et luisant par temps humide. Dessous : des tubes (une éponge), "
                    "crème puis jaune verdâtre, qui bleuissent quand on appuie. Pied brun clair "
                    "strié de fibrilles brunes, sans réseau. Chair blanchâtre à jaunâtre, qui "
                    "bleuit un peu à la coupe.",
        confusions="Les autres bolets à pores jaunes (bolets à chair jaune) : moins bons, sans "
                   "danger grave. Bolet amer (Tylopilus felleus) : pores rosés, réseau brun sur "
                   "le pied. Comme pour le cèpe, écarter les bolets à pores rouges.",
        limites=["Il fuit le calcaire, mais la carte lit la roche, pas le sol : un limon acide "
                 "posé sur du calcaire lui convient, et la carte l'y sous-estime."],
    ),
    Espece(
        code="girolle", nom="Girolle", de="de la girolle", latin="Cantharellus cibarius et proches",
        saison=("06-01", "07-01", "10-01", "11-10"),
        essences={0: 0.0, 1: 0.6, 2: 0.9, 3: 0.9, 4: 0.9, 5: 0.3, 6: 0.05, 7: 0.9, 8: 0.9,
                  9: 0.4, 10: 0.7, 11: 0.5, 12: 0.8, 13: 0.1, 14: 0.1},
        roches={0: 0.8, 1: 0.5, 2: 1.0, 3: 0.8},
        altitude=(1500, 1900),
        pluie_jours=(7, 25), pluie_mm=(10, 35),
        sol=(9, 13, 20, 25), gel=0.5,
        ph=(3.5, 4.0, 6.0, 7.5), ph_plancher=0.3, sol_ph=True,
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
        altitude=(1200, 1600),
        pluie_jours=(7, 25), pluie_mm=(20, 50),
        sol=(6, 9, 16, 21), gel=0.5,
        ph=(4.5, 6.0, 8.0, 8.5), ph_plancher=0.4,
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
        altitude=(1500, 1900),
        pluie_jours=(7, 25), pluie_mm=(15, 40),
        sol=(3, 6, 14, 20), gel=0.75,
        ph=(3.5, 4.5, 8.0, 8.5), ph_plancher=0.8,
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
        code="lactaire", nom="Lactaire délicieux", de="du lactaire délicieux",
        latin="Lactarius deliciosus et lactaires sanguins",
        saison=("08-01", "09-10", "11-15", "12-15"),
        essences={0: 0.0, 1: 0.05, 2: 0.0, 3: 0.05, 4: 0.0, 5: 0.05, 6: 0.0, 7: 0.4, 8: 0.1,
                  9: 0.05, 10: 1.0, 11: 0.05, 12: 0.6, 13: 0.3, 14: 0.1},
        roches={0: 0.8, 1: 1.0, 2: 0.6, 3: 0.9},
        altitude=(1600, 2000),
        pluie_jours=(7, 25), pluie_mm=(15, 40),
        sol=(6, 10, 17, 22), gel=0.5,
        ph=(5.0, 6.5, 8.5, 9.0), ph_plancher=0.4,
        habitat_texte="Sous les pins seulement (sylvestre, maritime, noir, d'Alep), souvent dans "
                      "l'herbe des jeunes pinèdes, des lisières et des dunes boisées ; de "
                      "préférence sur calcaire ou sable coquillier, plus rare sur sol acide.",
        meteo_texte="Une espèce d'arrière-saison qui attend les pluies : sur le littoral "
                    "atlantique et en Méditerranée, il sort tard, d'octobre à décembre, tant que "
                    "le sol reste doux.",
        description="Chapeau orange carotte, de 4 à 12 cm, creusé au centre et marqué de cercles "
                    "plus foncés ; il se tache de vert en vieillissant. Dessous : des lames "
                    "serrées, orange. Pied court, creux, orange, souvent piqué de petites "
                    "fossettes. À la cassure, un lait orange carotte (rouge vineux d'emblée chez "
                    "les lactaires sanguins) ; les blessures verdissent. Il colore l'urine en "
                    "rouge : c'est sans danger.",
        confusions="Lactaire à toison (Lactarius torminosus), toxique : chapeau rose saumon à "
                   "marge laineuse, lait BLANC, sous les bouleaux. Tout lactaire à lait blanc "
                   "est à écarter. Le lactaire de l'épicéa (L. deterrimus), lait orange lui "
                   "aussi, est sans danger mais médiocre.",
        repere="Il aime l'herbe sous les jeunes pins, les bords d'allées et les lisières plus "
               "que la litière épaisse des vieilles futaies.",
        limites=["La BD Forêt ne distingue ni les pins entre eux, ni les jeunes plantations des "
                 "vieilles futaies : la carte voit toutes les pinèdes pareilles.",
                 "Sous les épicéas des montagnes, le lactaire à lait orange est surtout le "
                 "lactaire de l'épicéa, moins recherché : la carte ne le suit pas."],
    ),
    Espece(
        code="morille", nom="Morille", de="de la morille", latin="Morchella spp.",
        saison=("03-01", "04-01", "05-20", "06-30"),
        essences={0: 0.0, 1: 0.8, 2: 0.3, 3: 0.4, 4: 0.2, 5: 0.6, 6: 1.0, 7: 0.5, 8: 0.5,
                  9: 0.6, 10: 0.4, 11: 0.4, 12: 0.5, 13: 0.2, 14: 0.8},
        roches={0: 0.7, 1: 1.0, 2: 0.4, 3: 0.8},
        altitude=(1300, 1800),
        pluie_jours=(3, 21), pluie_mm=(10, 30),
        sol=(5, 8, 13, 17), gel=0.6,
        ph=(5.0, 6.5, 8.5, 9.0), ph_plancher=0.3,
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
                 "fiable de la carte."],
    ),
    Espece(
        code="chanterelle_tube", nom="Chanterelle en tube", de="de la chanterelle en tube",
        latin="Craterellus tubaeformis",
        saison=("08-15", "09-15", "11-30", "12-31"),
        essences={0: 0.0, 1: 0.6, 2: 0.8, 3: 0.6, 4: 0.6, 5: 0.3, 6: 0.05, 7: 0.9, 8: 1.0,
                  9: 0.5, 10: 0.8, 11: 0.7, 12: 0.9, 13: 0.1, 14: 0.1},
        roches={0: 0.8, 1: 0.2, 2: 1.0, 3: 0.6},
        altitude=(1700, 2100),
        pluie_jours=(7, 25), pluie_mm=(20, 50),
        sol=(2, 5, 13, 18), gel=0.8,
        ph=(3.0, 3.5, 5.5, 7.0), ph_plancher=0.2, sol_ph=True,
        habitat_texte="Bois acides et humides, de résineux surtout (épicéas, sapins, pins), mais aussi "
                      "hêtraies et chênaies : en troupes nombreuses dans la mousse, près du bois pourri "
                      "et des myrtilles. Elle fuit le calcaire.",
        meteo_texte="La dernière de l'automne : elle attend des sols détrempés et frais, tient sous les "
                    "premières gelées et pousse jusqu'en décembre en plaine.",
        description="Chapeau brun-gris à brun-jaune, de 2 à 6 cm, en entonnoir souvent percé au centre, "
                    "à bord enroulé puis ondulé. Dessous : des plis gris et fourchus qui descendent sur "
                    "le pied, pas de vraies lames. Pied creux, jaune grisâtre, souvent aplati et "
                    "sillonné. Chair mince et élastique.",
        confusions="Chanterelle jaunissante (Craterellus lutescens), comestible : presque sans plis, "
                   "pied orange, plutôt sur calcaire. Dans les mêmes mousses poussent de petits "
                   "champignons bruns à vraies lames, dont des cortinaires MORTELS aux lames rouille : "
                   "un champignon à lames n'est pas une chanterelle.",
        limites=["Elle aime les sols gorgés d'eau et moussus : la carte lit la pluie tombée, pas "
                 "l'eau du sol, et ne voit ni la mousse ni le bois pourri."],
    ),
    Espece(
        code="oronge", nom="Oronge", de="de l'oronge", feminin=True,
        latin="Amanita caesarea (amanite des Césars)",
        saison=("07-01", "08-01", "09-30", "10-31"),
        essences={0: 0.0, 1: 0.5, 2: 0.2, 3: 1.0, 4: 1.0, 5: 0.3, 6: 0.0, 7: 0.6, 8: 0.05,
                  9: 0.05, 10: 0.4, 11: 0.1, 12: 0.2, 13: 0.2, 14: 0.1},
        roches={0: 0.8, 1: 0.6, 2: 1.0, 3: 0.8},
        altitude=(900, 1300),
        pluie_jours=(6, 20), pluie_mm=(20, 50),
        sol=(13, 17, 23, 27), gel=0.3,
        ph=(4.0, 5.0, 7.0, 8.0), ph_plancher=0.4,
        habitat_texte="Chênaies et châtaigneraies chaudes et claires, sur sols bien drainés, souvent "
                      "acides ; versants au soleil des plaines et des collines du Sud-Ouest, du Centre "
                      "et du pourtour méditerranéen. Rare au nord de la Loire.",
        meteo_texte="Il lui faut un été chaud, puis des orages : elle sort après les pluies d'août et de "
                    "septembre tant que le sol reste chaud ; le premier froid l'arrête.",
        description="Chapeau orange vif à rouge orangé, de 8 à 20 cm, lisse, à marge striée. Dessous : "
                    "des lames JAUNE d'or, serrées. Pied jaune, à anneau jaune, sortant d'une grande "
                    "volve blanche en sac. Jeune, elle est enfermée dans un œuf blanc : coupé en deux, "
                    "il montre le chapeau orange et les lames jaunes.",
        confusions="Amanite tue-mouches (Amanita muscaria), toxique : chapeau rouge à flocons blancs "
                   "(la pluie peut les laver), lames et pied BLANCS, volve en bourrelets. À l'état "
                   "d'œuf, l'oronge se confond avec les œufs d'amanites MORTELLES (phalloïde, vireuse).",
        avertissement="C'est une amanite, la famille des champignons les plus mortels : ne jamais la "
                      "ramasser sans avoir vu les lames et le pied jaunes et la volve blanche, et jamais "
                      "à l'état d'œuf fermé.",
        limites=["Espèce rare et dispersée : au nord de la Loire, elle reste exceptionnelle même quand "
                 "l'indice est bon. La carte dit où les conditions sont réunies, pas où elle a été vue."],
    ),
    Espece(
        code="hygrophore_mars", nom="Hygrophore de mars", de="de l'hygrophore de mars",
        latin="Hygrophorus marzuolus",
        saison=("02-15", "03-10", "05-10", "06-15"),
        essences={0: 0.0, 1: 0.3, 2: 0.7, 3: 0.2, 4: 0.2, 5: 0.1, 6: 0.0, 7: 0.9, 8: 1.0,
                  9: 0.4, 10: 0.5, 11: 0.4, 12: 0.8, 13: 0.0, 14: 0.05},
        roches={0: 0.8, 1: 0.7, 2: 1.0, 3: 0.9},
        altitude=(1600, 2000), plancher=(300, 600),
        pluie_jours=(3, 21), pluie_mm=(10, 30),
        sol=(0.5, 2, 7, 11), gel=0.9,
        ph=(4.0, 4.5, 7.0, 8.0), ph_plancher=0.5,
        habitat_texte="Sapinières et pessières de montagne, hêtraies-sapinières, de 500 à 1 600 m "
                      "environ : à demi enterré sous la mousse et les aiguilles, souvent au bord des "
                      "plaques de neige qui fondent.",
        meteo_texte="Le champignon de la fonte des neiges : il sort de fin février à mai selon "
                    "l'altitude, dans un sol encore froid (2 à 7 °C) et gorgé d'eau ; les gelées de "
                    "printemps le freinent à peine.",
        description="Chapeau charnu, de 4 à 12 cm, blanc puis gris à gris noirâtre par plages, souvent "
                    "bosselé et sali de terre. Dessous : des lames épaisses, espacées, cireuses, blanches "
                    "puis grisâtres, qui descendent un peu sur le pied. Pied court et épais, blanc à "
                    "grisâtre. Chair blanche et ferme.",
        confusions="Au printemps, peu de champignons à lames en forêt de montagne ; un champignon à "
                   "lames fines et serrées, ou rosées, n'est pas un hygrophore. Les lames épaisses, "
                   "espacées et cireuses sont le repère.",
        limites=["La carte ne connaît pas la neige : sous une couche épaisse, le sol reste à 0 °C et "
                 "l'indice est nul, ce qui est juste, mais elle ne voit pas les plaques qui fondent, "
                 "où il pousse justement."],
    ),
    Espece(
        code="coulemelle", nom="Coulemelle", de="de la coulemelle", latin="Macrolepiota procera",
        # Clairières et friches (324) à 0,4 seulement : Corine y range aussi les jeunes pins des Landes.
        milieu="pre", prairies={1: 0.8, 2: 1.0, 3: 0.6, 4: 0.7, 5: 0.4},
        essences={}, roches={},
        saison=("06-15", "08-01", "10-15", "11-20"),
        altitude=(1600, 2000),
        pluie_jours=(6, 20), pluie_mm=(15, 40),
        sol=(10, 13, 21, 25), gel=0.4,
        habitat_texte="Prés maigres, pelouses, lisières et clairières, bords de chemins et bois clairs ; "
                      "souvent en lignes ou en ronds.",
        meteo_texte="Après les pluies de fin d'été et du début de l'automne, tant que le sol reste doux ; "
                    "les premières gelées l'arrêtent.",
        description="Grande : chapeau de 10 à 30 cm, d'abord en baguette de tambour puis étalé en "
                    "ombrelle, brun clair couvert d'écailles brunes, avec un mamelon central plus foncé. "
                    "Dessous : des lames blanches, libres. Pied haut et creux, chiné de brun en zigzag, "
                    "avec un anneau double qui coulisse. Pas de volve.",
        confusions="Petites lépiotes MORTELLES (lépiote brun-rose et proches) : chapeau de moins de "
                   "10 cm. Amanite panthère, toxique : chapeau brun à flocons blancs, pied lisse, volve "
                   "en bourrelet. Lépiotes déguenillées (Chlorophyllum), parfois mal tolérées : pied "
                   "lisse, sans chinure, chair qui rougit à la coupe.",
        avertissement="Ne ramassez que de grands exemplaires, au pied chiné et à l'anneau qui coulisse : "
                      "les petites lépiotes sont mortelles. Dans un pré, les champignons appartiennent "
                      "au propriétaire du terrain : demandez son accord.",
        limites=["Pas de carte des prés : ils sont presque tous privés. La carte en donne les "
                 "conditions par département et par commune, d'après les prairies et pelouses de Corine "
                 "Land Cover (parcelles de 25 ha et plus).",
                 "Elle pousse aussi en lisière et en clairière, que ces prés ne comptent qu'en partie."],
    ),
    Espece(
        code="rose_pres", nom="Rosé des prés", de="du rosé des prés", latin="Agaricus campestris",
        milieu="pre", prairies={1: 1.0, 2: 0.5, 3: 0.5, 4: 0.4, 5: 0.0},
        essences={}, roches={},
        saison=("07-15", "08-20", "10-20", "11-30"),
        altitude=(1400, 1800),
        pluie_jours=(6, 20), pluie_mm=(15, 40),
        sol=(10, 14, 22, 26), gel=0.3,
        habitat_texte="Pâtures et prés pâturés, fumés par les chevaux, les vaches ou les moutons ; aussi "
                      "les pelouses rases. Jamais en forêt.",
        meteo_texte="Après une bonne pluie de fin d'été, quand le sol est encore chaud : il sort vite, "
                    "souvent en ronds, et disparaît au premier froid.",
        description="Chapeau blanc, parfois un peu brunâtre, de 4 à 10 cm, soyeux. Dessous : des lames "
                    "libres, ROSES chez le jeune puis brun chocolat à noires, jamais blanches. Pied blanc, "
                    "court, avec un anneau fragile, SANS volve à la base. Chair blanche, à odeur agréable "
                    "de champignon.",
        confusions="Amanites blanches MORTELLES (vireuse, printanière, phalloïde pâle) : lames BLANCHES "
                   "qui le restent, volve en sac à la base du pied ; elles poussent en lisière et peuvent "
                   "déborder dans les prés. Agaric jaunissant (Agaricus xanthodermus), toxique : la base "
                   "du pied jaunit vivement à la coupe, odeur d'encre. Petites lépiotes, dont des "
                   "mortelles.",
        avertissement="Dans un pré, les champignons appartiennent au propriétaire du terrain, souvent un "
                      "éleveur : demandez son accord et refermez les barrières. Ne ramassez jamais un "
                      "champignon blanc sans avoir vu ses lames roses ou brunes et l'absence de volve.",
        limites=["Pas de carte des prés : ils sont presque tous privés. La carte en donne les "
                 "conditions par département et par commune, d'après les prairies et pelouses de Corine "
                 "Land Cover, qui ne distingue ni la fumure ni le pâturage.",
                 "Peu d'observations précises : sa vérification reste indicative."],
    ),
]

PAR_CODE = {e.code: e for e in ESPECES}
DE_FORET = [e for e in ESPECES if e.milieu == "foret"]
DES_PRES = [e for e in ESPECES if e.milieu == "pre"]

REFERENCES = [
    "Courtecuisse R. et Duhem B., Guide des champignons de France et d'Europe, Delachaux et Niestlé.",
    "Eyssartier G. et Roux P., Le guide des champignons France et Europe, Belin.",
    "Kauserud H. et al. (2008), Mushroom fruiting and climate change, PNAS 105(10).",
    "Boddy L. et al. (2014), Climate variation effects on fungal fruiting, Fungal Ecology 10.",
    "Phillips S. J. et al. (2009), Sample selection bias and presence-only distribution models, "
    "Ecological Applications 19(1) : fond « groupe cible » de la validation.",
    "Maclure M. (1991), The case-crossover design, American Journal of Epidemiology 133(2) : "
    "plan « cas-croisé » de la validation météo.",
    "Hopkins A. D. (1918), Periodical events and natural law as guides to agricultural research "
    "and practice, Monthly Weather Review, supplément 9 : loi bioclimatique (latitude, saison, altitude).",
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
            "latitude_ref": LATITUDE_REF, "hopkins_jours": HOPKINS_JOURS,
            "hopkins_metres": HOPKINS_METRES,
        },
        "references": REFERENCES,
    }
