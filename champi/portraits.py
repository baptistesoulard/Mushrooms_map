"""Les portraits des espèces, pour leurs fiches (`pages_especes.py`) : où chacune pousse, des
astuces pour la trouver, sa réputation en cuisine et une recette (demande du 2026-11-08).

Rien ici ne sert au calcul : les règles restent dans `especes.py`, et `especes.json` (chargé par
la carte) n'en reçoit rien. Les textes viennent des guides de terrain (`especes.REFERENCES`) ;
la saveur dit la réputation d'une espèce dans les guides, jamais si une récolte se mange.

L'oronge n'a ni note ni recette : c'est une amanite, la famille des champignons les plus
mortels, et le site ne pousse pas un débutant vers elle (décision du 2026-11-08).
"""
from __future__ import annotations

from dataclasses import dataclass

U = " "            # espace insécable, avant les unités


@dataclass(frozen=True)
class Recette:
    titre: str
    pour: str
    ingredients: tuple[str, ...]
    etapes: tuple[str, ...]


@dataclass(frozen=True)
class Portrait:
    ou_pousse: str
    astuces: tuple[str, ...]
    saveur: int                   # 1 (médiocre) à 5 (excellent) ; 0 : pas de note
    saveur_texte: str
    cuisine: str                  # le geste propre à l'espèce, dit avant la recette
    recette: Recette | None = None


# La note de saveur, en mots (comme dans les guides).
SAVEURS = {5: "excellent", 4: "très bon", 3: "bon", 2: "moyen", 1: "médiocre"}

PORTRAITS: dict[str, Portrait] = {
    "cepe": Portrait(
        ou_pousse="Le cèpe vit associé aux racines des arbres : hêtres, chênes, châtaigniers, épicéas, "
                  "pins. Il aime les sols acides qui se ressuient vite et les forêts assez claires, et "
                  "sort volontiers là où la lumière touche le sol : lisières, bords de chemins forestiers, "
                  "talus, clairières herbeuses. Un même coin produit souvent d'une année à l'autre.",
        astuces=(
            "Marchez les lisières et les bords de chemins forestiers : le sol s'y réchauffe plus vite, "
            "et le cèpe y sort souvent le premier.",
            "Avancez lentement en regardant sous les fougères, dans la mousse et les feuilles : le "
            "chapeau brun s'y confond.",
            "Un cèpe trouvé en annonce souvent d'autres à quelques mètres : fouillez les alentours "
            "avant de repartir.",
            "Passez tôt, dans les premiers jours de la pousse : les limaces et les vers vont vite.",
            "Notez vos coins sur la carte (« Mes coins ») : un bon coin revient d'une année à l'autre.",
        ),
        saveur=5, saveur_texte="la référence des bolets, ferme et parfumé",
        cuisine="Gardez les exemplaires jeunes et fermes ; chez les plus grands, retirez les tubes s'ils "
                "sont mous ou verdâtres. Brossez-les sans les laver.",
        recette=Recette(
            titre="Cèpes à la bordelaise", pour="4 personnes",
            ingredients=(f"500{U}g de cèpes", "2 gousses d'ail (ou 1 échalote)", "1 petit bouquet de persil",
                         "3 cuillerées à soupe de graisse de canard ou d'huile", "sel, poivre"),
            etapes=(
                "Brossez et essuyez les cèpes. Séparez les pieds des chapeaux ; coupez les chapeaux en "
                "tranches épaisses, hachez les pieds.",
                "Faites dorer les chapeaux dans la graisse bien chaude, à feu vif, une dizaine de minutes, "
                "en les retournant.",
                "Ajoutez les pieds hachés, l'ail et le persil, et poursuivez 5 minutes à feu moyen.",
                "Salez, poivrez, servez aussitôt, avec une viande grillée ou des pommes de terre sautées.",
            )),
    ),
    "bolet_bai": Portrait(
        ou_pousse="Le bolet bai accompagne surtout les conifères (épicéas, pins, sapins), mais aussi les "
                  "châtaigniers, chênes et hêtres, toujours sur sols acides. Il aime la mousse, les tapis "
                  "d'aiguilles et le pied des souches, et pousse souvent en nombre là où le cèpe se fait "
                  "rare. Il revient fidèlement aux mêmes endroits.",
        astuces=(
            "Fouillez la mousse au pied des épicéas et des pins, et autour des vieilles souches : il s'y "
            "cache souvent à moitié.",
            "Il prend le relais du cèpe en fin de saison : quand les cèpes s'arrêtent, retournez dans "
            "les mêmes bois.",
            "Par temps humide, son chapeau luisant accroche la lumière sous les arbres.",
            "Il fait souvent plusieurs poussées : revenez après chaque grosse pluie d'automne.",
        ),
        saveur=4, saveur_texte="proche du cèpe, un peu plus tendre",
        cuisine="Retirez les tubes des exemplaires âgés, spongieux. Sa chair bleuit un peu à la coupe : "
                "elle redevient pâle à la cuisson.",
        recette=Recette(
            titre="Omelette aux bolets bais", pour="3 personnes",
            ingredients=(f"300{U}g de bolets bais", "6 œufs", "1 échalote", f"20{U}g de beurre",
                         "quelques brins de persil", "sel, poivre"),
            etapes=(
                "Brossez les bolets et coupez-les en lamelles.",
                "Faites-les revenir dans le beurre, à feu vif, 10 à 15 minutes, jusqu'à ce que leur eau "
                "soit évaporée et qu'ils dorent ; ajoutez l'échalote hachée les 3 dernières minutes.",
                "Battez les œufs avec le persil, le sel et le poivre, versez-les sur les bolets et faites "
                "cuire l'omelette à feu moyen, encore baveuse au centre.",
            )),
    ),
    "girolle": Portrait(
        ou_pousse="La girolle vit en symbiose avec les hêtres, les chênes, les châtaigniers et les "
                  "conifères, sur sols acides. On la trouve dans la mousse, sur les talus et le long des "
                  "chemins creux, en groupes, parfois en lignes. Elle grossit lentement et reste longtemps "
                  "fraîche : une même place peut donner plusieurs semaines.",
        astuces=(
            "Cherchez les talus moussus et les bords de chemins en sous-bois : son jaune d'œuf se voit "
            "de loin.",
            "Elle revient aux mêmes places chaque année : notez-les et repassez après chaque bonne pluie.",
            "Laissez les toutes petites : elles seront encore là, plus grandes, la semaine suivante.",
            "Dans les hêtraies et chênaies, suivez les zones de mousse plutôt que la litière épaisse.",
        ),
        saveur=5, saveur_texte="parfumée, à la chair ferme",
        cuisine="Brossez-la sans la tremper. Elle rend beaucoup d'eau : faites-la évaporer à feu vif avant "
                "d'ajouter le beurre.",
        recette=Recette(
            titre="Girolles poêlées à l'échalote", pour="4 personnes",
            ingredients=(f"400{U}g de girolles", "2 échalotes", f"30{U}g de beurre", "quelques brins de persil",
                         "sel, poivre"),
            etapes=(
                "Brossez les girolles ; coupez les plus grosses en deux.",
                "Mettez-les dans une poêle chaude, sans matière grasse, 5 minutes, puis égouttez l'eau "
                "qu'elles ont rendue.",
                "Ajoutez le beurre et les échalotes hachées, et poursuivez 10 minutes à feu moyen, jusqu'à "
                "ce qu'elles dorent.",
                "Salez, poivrez, parsemez de persil ; c'est parfait avec une volaille ou des œufs brouillés.",
            )),
    ),
    "trompette": Portrait(
        ou_pousse="La trompette de la mort vit avec les hêtres, plus rarement les chênes, sur des sols "
                  "frais et argileux, plutôt calcaires ou neutres. Elle pousse en troupes serrées dans les "
                  "feuilles mortes, souvent sur les versants ombragés et dans les creux humides, et une "
                  "bonne place en donne en abondance.",
        astuces=(
            "Regardez à vos pieds, à genoux s'il le faut : grise et noire, elle disparaît dans la litière "
            "de hêtre.",
            "Quand vous en voyez une, il y en a d'autres : examinez chaque mètre carré autour.",
            "Cherchez les creux et les versants frais des hêtraies, là où les feuilles restent humides.",
            "Elle sort tard, après les grosses pluies de fin d'été : inutile de la chercher par sécheresse.",
        ),
        saveur=4, saveur_texte="un goût puissant, qui parfume tout un plat, et elle se sèche très bien",
        cuisine="Creuse, elle abrite terre et insectes : fendez-la en deux dans la longueur et rincez-la "
                "rapidement.",
        recette=Recette(
            titre="Tagliatelles aux trompettes et à la crème", pour="4 personnes",
            ingredients=(f"300{U}g de tagliatelles", f"250{U}g de trompettes (ou 30{U}g séchées, "
                         "réhydratées 20 minutes dans l'eau tiède)", "1 échalote", f"20{U}g de beurre",
                         f"20{U}cl de crème", "parmesan, sel, poivre"),
            etapes=(
                "Fendez, rincez et égouttez les trompettes ; coupez les plus grandes en lanières.",
                "Faites suer l'échalote hachée dans le beurre, ajoutez les trompettes et laissez cuire 10 "
                "minutes à feu moyen, jusqu'à ce que leur eau soit évaporée.",
                "Versez la crème, salez, poivrez, laissez réduire 5 minutes.",
                "Mêlez aux tagliatelles cuites et égouttées, servez avec du parmesan râpé.",
            )),
    ),
    "pied_de_mouton": Portrait(
        ou_pousse="Le pied-de-mouton pousse dans presque toutes les forêts, feuillus comme conifères, sur "
                  "sols calcaires comme acides. Il forme souvent des cercles ou de longues lignes dans la "
                  "litière et la mousse, et continue de sortir quand les autres espèces ont cessé, "
                  "jusqu'aux premiers froids sérieux.",
        astuces=(
            "Suivez la ligne : un pied-de-mouton trouvé, cherchez dans son prolongement, ils poussent en "
            "arcs et en ronds.",
            "Il tient au froid : en novembre et décembre, quand les cèpes sont finis, c'est lui qu'on "
            "cherche.",
            "Sa couleur crème ressort sur les feuilles brunes : balayez le sol du regard, de loin.",
            "Les vers l'épargnent souvent : même tard dans la saison, il reste en bon état.",
        ),
        saveur=3, saveur_texte="bon jeune, ferme ; il devient amer en vieillissant",
        cuisine="Gardez les jeunes exemplaires. Retirez les aiguillons des plus grands, qui s'effritent, "
                "et faites-les blanchir 2 minutes à l'eau bouillante s'ils sont amers.",
        recette=Recette(
            titre="Pieds-de-mouton à la crème", pour="4 personnes",
            ingredients=(f"500{U}g de pieds-de-mouton", "1 échalote", f"20{U}g de beurre", f"20{U}cl de crème",
                         "quelques brins de persil", "sel, poivre"),
            etapes=(
                "Brossez les pieds-de-mouton et coupez-les en morceaux.",
                "Faites-les revenir dans le beurre avec l'échalote hachée, 10 à 15 minutes à feu moyen, "
                "jusqu'à évaporation de leur eau.",
                "Ajoutez la crème, salez, poivrez, laissez réduire 5 minutes et parsemez de persil. Avec "
                "une volaille ou du riz.",
            )),
    ),
    "lactaire": Portrait(
        ou_pousse="Le lactaire délicieux vit uniquement avec les pins. Il préfère les jeunes pinèdes "
                  "claires et herbeuses, les lisières, les talus et les dunes boisées, sur sols calcaires "
                  "ou sableux, plutôt que la litière épaisse des vieilles futaies. Sur le littoral et en "
                  "Méditerranée, il sort tard, souvent d'octobre à décembre.",
        astuces=(
            "Cherchez dans l'herbe sous les jeunes pins, le long des allées et des pare-feu.",
            "Son orange carotte se voit entre les aiguilles ; les vieux exemplaires se tachent de vert.",
            "Il sort souvent en groupes : parcourez lentement les bords de la pinède.",
            "Sur le littoral et en Méditerranée, attendez les premières grosses pluies d'automne.",
        ),
        saveur=2, saveur_texte="chair granuleuse, meilleure grillée ; malgré son nom, loin du cèpe",
        cuisine="Gardez les exemplaires jeunes et sains, sans vers. Il colore l'urine en rouge : c'est sans "
                "danger.",
        recette=Recette(
            titre="Lactaires grillés à l'ail et au persil", pour="4 personnes",
            ingredients=("12 chapeaux de lactaires délicieux", "4 cuillerées à soupe d'huile d'olive",
                         "2 gousses d'ail", "quelques brins de persil", "sel"),
            etapes=(
                "Retirez les pieds, essuyez les chapeaux.",
                "Mélangez l'huile, l'ail et le persil hachés, et le sel.",
                "Faites griller les chapeaux à la plancha ou au gril, lames vers le haut, en les "
                "badigeonnant du mélange, 10 à 12 minutes en tout, en les retournant à mi-cuisson, "
                "jusqu'à ce que la chair soit tendre.",
            )),
    ),
    "morille": Portrait(
        ou_pousse="La morille aime les sols remués et plutôt calcaires : bords de rivières, frênaies et "
                  "peupleraies, vieux vergers, parcs, talus, coupes forestières et places à feu. En "
                  "montagne, elle sort à la fonte des neiges dans les clairières et les lisières de "
                  "résineux. Elle est capricieuse : abondante une année, absente la suivante.",
        astuces=(
            "Cherchez au pied des frênes, des ormes morts et des vieux pommiers, et le long des cours "
            "d'eau.",
            "Les coupes et les brûlis de l'année précédente peuvent en donner beaucoup, une ou deux "
            "saisons seulement.",
            "Brune ou grise, elle se fond dans les feuilles mortes : avancez lentement, le regard au sol.",
            "Suivez la saison qui monte : d'abord les plaines et les rivières, puis les collines, puis la "
            "montagne à la fonte des neiges.",
        ),
        saveur=5, saveur_texte="le grand champignon du printemps, très parfumé",
        cuisine="Toxique crue ou mal cuite : au moins 20 minutes de cuisson, et en quantité raisonnable. "
                "Fendez-la en deux pour en chasser terre et insectes, et rincez-la à plusieurs eaux.",
        recette=Recette(
            titre="Morilles à la crème", pour="4 personnes",
            ingredients=(f"300{U}g de morilles fraîches (ou 40{U}g séchées)", "1 échalote",
                         f"20{U}g de beurre", f"25{U}cl de crème", "sel, poivre"),
            etapes=(
                "Morilles fraîches : fendez-les en deux, rincez-les à plusieurs eaux, égouttez. Séchées : "
                "réhydratez-les 30 minutes dans l'eau tiède, filtrez et gardez cette eau.",
                "Faites suer l'échalote hachée dans le beurre, ajoutez les morilles (et un peu de leur eau "
                "filtrée) et laissez cuire 15 minutes à couvert, à feu doux.",
                "Versez la crème, salez, poivrez et laissez réduire encore 10 minutes, à découvert.",
                "Servez avec une volaille ou des pâtes fraîches.",
            )),
    ),
    "chanterelle_tube": Portrait(
        ou_pousse="La chanterelle en tube vit dans les bois acides et humides, surtout de conifères "
                  "(épicéas, sapins, pins), mais aussi de hêtres et de chênes. Elle pousse en troupes de "
                  "dizaines, voire de centaines, dans la mousse et les myrtilles, près du bois pourri et des "
                  "souches, sur les sols qui restent gorgés d'eau.",
        astuces=(
            "Cherchez les tapis de mousse humides et les bordures de myrtilles, près des souches et du bois "
            "pourri.",
            "Brune et grise, elle se voit mal : repérez d'abord son pied jaune, puis regardez autour, elle "
            "est rarement seule.",
            "C'est la dernière de la saison : après les premières gelées, quand le reste est fini, elle "
            "continue.",
            "Une troupe trouvée, revenez-y : elle produit souvent plusieurs semaines de suite.",
        ),
        saveur=3, saveur_texte="parfumée, et excellente séchée",
        cuisine="Brossez-la et rincez-la à peine. Elle rend son eau à la cuisson : laissez-la s'évaporer.",
        recette=Recette(
            titre="Chanterelles en tube aux lardons", pour="4 personnes",
            ingredients=(f"400{U}g de chanterelles en tube", f"100{U}g de lardons", "1 échalote",
                         "quelques brins de persil", "poivre"),
            etapes=(
                "Nettoyez les chanterelles ; fendez les plus grosses en deux.",
                "Mettez-les dans une poêle chaude, sans matière grasse, 5 minutes, puis égouttez l'eau "
                "qu'elles ont rendue.",
                "Faites dorer les lardons, ajoutez l'échalote hachée et les chanterelles, et poursuivez 10 "
                "minutes à feu moyen.",
                "Poivrez (les lardons salent assez) et parsemez de persil.",
            )),
    ),
    "oronge": Portrait(
        ou_pousse="L'oronge vit associée aux chênes et aux châtaigniers, dans les bois clairs et chauds, "
                  "sur sols bien drainés : versants ensoleillés, lisières, bords de chemins. Elle a besoin "
                  "d'un été chaud suivi d'orages, et reste exceptionnelle au nord de la Loire.",
        astuces=(
            "Cherchez les chênaies et châtaigneraies claires des versants au soleil, après les orages de "
            "fin d'été.",
            "Elle revient aux mêmes places les étés chauds : une place connue vaut mieux qu'une longue "
            "recherche.",
            "Son orange vif se voit de loin dans la litière : admirez-la, photographiez-la ; la ramasser "
            "demande l'œil d'un mycologue.",
        ),
        saveur=0, saveur_texte="",
        cuisine="Pas de note ni de recette pour l'oronge : c'est une amanite, la famille des champignons "
                "les plus mortels. Laissez-la aux mycologues confirmés.",
    ),
    "hygrophore_mars": Portrait(
        ou_pousse="L'hygrophore de mars vit dans les sapinières et pessières de montagne et les "
                  "hêtraies-sapinières, entre 500 et 1 600 m environ. Il pousse à demi enterré sous la "
                  "mousse et les aiguilles, souvent au bord des plaques de neige qui fondent, et ne montre "
                  "parfois qu'une bosse dans le tapis forestier.",
        astuces=(
            "Suivez la fonte des neiges : cherchez au bord des plaques qui reculent, sur les versants qui "
            "se découvrent.",
            "Repérez les petites bosses dans la mousse et les aiguilles : il est souvent caché dessous, "
            "sali de terre.",
            "Dégagez-le doucement à la main, sans râteau : la mousse et le mycélium restent en place.",
            "Il pousse en groupes : là où il y en a un, sondez les alentours.",
        ),
        saveur=4, saveur_texte="chair ferme et fine, le premier bon champignon de l'année",
        cuisine="Brossez la terre et les aiguilles collées : il pousse à demi enterré.",
        recette=Recette(
            titre="Omelette aux hygrophores de mars", pour="3 personnes",
            ingredients=(f"250{U}g d'hygrophores de mars", "6 œufs", f"20{U}g de beurre", "un peu de ciboulette",
                         "sel, poivre"),
            etapes=(
                "Brossez les hygrophores et coupez-les en lamelles.",
                "Faites-les revenir dans le beurre, 10 à 15 minutes à feu moyen, jusqu'à ce qu'ils dorent.",
                "Battez les œufs avec la ciboulette ciselée, le sel et le poivre, versez sur les "
                "champignons et faites cuire l'omelette.",
            )),
    ),
    "coulemelle": Portrait(
        ou_pousse="La coulemelle n'est liée à aucun arbre : elle décompose la matière organique des prés "
                  "maigres, des pelouses, des lisières et des clairières. Elle pousse en lignes ou en ronds "
                  "qui reviennent chaque année, et sa grande ombrelle se voit de loin, au bord des chemins "
                  "comme au milieu des prés.",
        astuces=(
            "Parcourez les lisières, les bords de chemins et les clairières herbeuses : on la repère de "
            "loin, en ombrelle ou en « baguette de tambour ».",
            "Ses ronds reviennent aux mêmes places : un rond trouvé une année se retrouve l'année suivante.",
            "Ne gardez que les grands exemplaires, ouverts en ombrelle : les petits ressemblent trop aux "
            "lépiotes mortelles.",
            "Elle sort vite après les pluies de fin d'été : passez dans les jours qui suivent, avant les "
            "limaces.",
        ),
        saveur=4, saveur_texte="le chapeau, au léger goût de noisette",
        cuisine="Seul le chapeau se mange : le pied, fibreux, se jette.",
        recette=Recette(
            titre="Coulemelles panées", pour="4 personnes",
            ingredients=("4 chapeaux de coulemelles", "2 œufs", "3 cuillerées à soupe de farine",
                         f"80{U}g de chapelure", f"30{U}g de beurre et un filet d'huile", "sel, poivre"),
            etapes=(
                "Retirez les pieds, essuyez les chapeaux sans les laver.",
                "Passez chaque chapeau dans la farine, puis dans les œufs battus salés et poivrés, puis dans "
                "la chapelure.",
                "Faites-les dorer dans le beurre et l'huile, 5 minutes de chaque côté au moins, à feu moyen, "
                "jusqu'à ce que la chair soit tendre. Avec une salade verte.",
            )),
    ),
    "rose_pres": Portrait(
        ou_pousse="Le rosé des prés vit dans les pâtures et les prés pâturés, enrichis par le fumier des "
                  "chevaux, des vaches ou des moutons, et sur les pelouses rases ; jamais en forêt. Il "
                  "apparaît souvent en ronds ou en arcs, parfois en grand nombre, quelques jours après une "
                  "bonne pluie de fin d'été.",
        astuces=(
            "Cherchez les prés pâturés depuis longtemps, surtout par les chevaux, plutôt que les prairies "
            "labourées ou très engraissées.",
            "Il sort en quelques jours après la pluie : passez tôt le matin.",
            "Ses ronds se devinent parfois à un anneau d'herbe plus verte : regardez-y après la pluie.",
        ),
        saveur=4, saveur_texte="plus parfumé que le champignon de Paris",
        cuisine="Évitez les bords de routes et les terrains traités : les agarics concentrent les métaux "
                "lourds. Retirez les lames noires des vieux exemplaires.",
        recette=Recette(
            titre="Tartines aux rosés des prés", pour="4 personnes",
            ingredients=(f"400{U}g de rosés des prés", "4 tranches de pain de campagne", "1 gousse d'ail",
                         f"20{U}g de beurre", f"10{U}cl de crème", "quelques brins de persil", "sel, poivre"),
            etapes=(
                "Essuyez les rosés et émincez-les.",
                "Faites-les revenir dans le beurre, à feu vif, une dizaine de minutes, jusqu'à évaporation "
                "de leur eau.",
                "Ajoutez la moitié de l'ail haché, le persil et la crème, salez, poivrez, laissez épaissir "
                "3 minutes.",
                "Servez sur le pain grillé frotté avec le reste de l'ail.",
            )),
    ),
}
