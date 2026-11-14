"""Les portraits des départements, pour leur page (`pages_departements.py`) : leurs forêts, les
espèces de la carte qui y poussent, où chercher et ce qu'il faut savoir (demande du 2026-11-14 :
un texte qui ne change pas d'un jour à l'autre, propre à chaque département, pour les dix
départements où l'on cherche le plus de champignons).

Faute de chiffres de recherche publiés par département, les dix ont été choisis parmi les grandes
régions à champignons (Limousin, Périgord, Vosges, Jura, Alpes, Landes), en tenant compte de leur
population ; la Search Console dira lesquels ajouter. Toujours l'échelle d'un massif ou d'une
grande forêt publique, jamais un coin ; rien de réglementaire au cas par cas (la page ajoute une
ligne commune : arrêtés, mairie). Rien ici ne sert au calcul.
"""
from __future__ import annotations

from dataclasses import dataclass

U = " "            # espace insécable : avant les unités, et dans les milliers


@dataclass(frozen=True)
class Terroir:
    forets: str          # le relief, les forêts, les sols
    especes: str         # les espèces de la carte qui y poussent, et quand
    ou: str              # où chercher, à l'échelle des massifs
    savoir: str          # ce qu'il faut savoir avant de partir (propriété, limites de la carte)


TERROIRS: dict[str, Terroir] = {
    "74": Terroir(
        forets="Des forêts étagées du lac Léman au pied du Mont-Blanc : chênaies et châtaigneraies dans les "
               "basses vallées et le Genevois, hêtraies-sapinières à mi-pente, pessières en altitude, "
               f"jusque vers 2{U}000{U}m.",
        especes="Le cèpe et la girolle dans les pessières et les hêtraies-sapinières, l'été et au début de "
                "l'automne ; le pied-de-mouton et la chanterelle en tube jusqu'aux premières neiges. Au "
                "printemps, la morille en basse altitude et l'hygrophore de mars à la fonte des neiges.",
        ou=f"La moyenne montagne, entre 800 et 1{U}600{U}m environ, réunit les forêts de la plupart des espèces "
           "de la carte : versants frais et moussus du Chablais, des Bornes-Aravis et du Faucigny.",
        savoir="En montagne, la saison suit l'altitude : elle monte avec l'été et redescend à l'automne, et la "
               "carte la calcule forêt par forêt. Forêts communales, domaniales et privées s'y côtoient.",
    ),
    "38": Terroir(
        forets="Trois visages : les massifs calcaires de la Chartreuse et du Vercors, couverts de "
               "hêtraies-sapinières et de pessières ; les massifs cristallins de Belledonne et de l'Oisans, "
               "aux sols plus acides ; au nord-ouest, les collines du Bas-Dauphiné et la forêt de Chambaran, "
               "ses chênes et ses châtaigniers sur sols acides.",
        especes="Cèpes, girolles et bolets bais dans les forêts acides de Belledonne et de Chambaran ; "
                "trompettes et pieds-de-mouton dans les hêtraies calcaires de Chartreuse et du Vercors ; au "
                "printemps, morilles et, en montagne, hygrophores de mars à la fonte des neiges.",
        ou="Les versants frais de moyenne montagne en été et au début de l'automne, puis les collines en "
           "arrière-saison : la saison redescend avec le froid.",
        savoir="Le Vercors compte une grande réserve naturelle, celle des Hauts-Plateaux, aux règles propres : "
               "la carte hachure les zones protégées et n'y calcule pas d'indice.",
    ),
    "39": Terroir(
        forets="Du vignoble et de la Bresse, à l'ouest, aux plateaux et à la haute chaîne, à l'est : "
               "chênaies sur sols argileux en plaine, puis hêtraies, sapinières et pessières en montant, "
               "presque partout sur calcaire. Le département compte de grandes forêts publiques, comme la "
               "forêt de Chaux, l'un des plus vastes massifs de feuillus de France, et la sapinière de la Joux.",
        especes="Le Jura est un pays de morilles au printemps. À l'automne, trompettes et pieds-de-mouton "
                "dans les hêtraies calcaires ; cèpes, girolles et chanterelles en tube sous les sapins et les "
                "épicéas, dont les aiguilles acidifient le sol.",
        ou=f"Les plateaux et la montagne, de 500 à 1{U}300{U}m environ, pour la plupart des espèces ; la forêt "
           "de Chaux et les bois de plaine pour celles des chênaies.",
        savoir="Le calcaire domine : la carte en tient compte, et les espèces des sols acides n'y trouvent leur "
               "place que sous les résineux ou sur les terrains décalcifiés.",
    ),
    "25": Terroir(
        forets="De la vallée du Doubs aux plateaux puis au Haut-Doubs, vers la frontière suisse : hêtraies et "
               "chênaies dans les vallées, sapinières et pessières en altitude, souvent en pré-bois sur les "
               "hauts plateaux, presque partout sur calcaire.",
        especes="Morilles au printemps ; à l'automne, cèpes et girolles sous les épicéas, trompettes et "
                "pieds-de-mouton dans les hêtraies, chanterelles en tube dans les sapinières moussues en fin "
                "de saison.",
        ou=f"Les sapinières et pessières du Haut-Doubs et les hêtraies des plateaux, de 600 à 1{U}200{U}m "
           "environ.",
        savoir="Les forêts communales y sont nombreuses, et une commune peut encadrer la cueillette dans les "
               "siennes.",
    ),
    "88": Terroir(
        forets="L'un des départements les plus boisés de France : sapinières, pessières et hêtraies sur le grès et "
               "le granite du massif, aux sols acides ; chênaies et hêtraies dans la plaine, à l'ouest.",
        especes="Des sols acides qui conviennent au cèpe, au bolet bai et à la girolle ; la chanterelle en tube "
                "est commune dans les sapinières moussues en fin de saison, et le pied-de-mouton tient "
                "jusqu'en décembre.",
        ou="Les forêts du massif, des basses Vosges gréseuses aux sapinières d'altitude, avec leurs grandes "
           "forêts publiques, domaniales et communales.",
        savoir="Les forêts publiques y sont nombreuses : le tableau plus bas dit chaque jour lesquelles ont les "
               "meilleures conditions.",
    ),
    "19": Terroir(
        forets="Un département très boisé, du plateau de Millevaches, au nord-est, aux gorges de la Dordogne "
               "et au bassin de Brive, au sud-ouest : chênaies, châtaigneraies et hêtraies, et de vastes "
               "plantations de douglas et d'épicéas, sur des sols granitiques et acides.",
        especes="Le pays du cèpe, qui y trouve sols acides et chênaies, de la fin de l'été à la Toussaint ; "
                "bolets bais, girolles et chanterelles en tube complètent le panier, surtout sur le plateau.",
        ou="Les chênaies et châtaigneraies des pentes et des vallées pour le cèpe ; les hêtraies et les "
           "plantations de résineux du plateau de Millevaches pour le bolet bai et la chanterelle en tube.",
        savoir="La forêt corrézienne est en grande majorité privée : sans l'accord du propriétaire, les "
               "champignons ne sont pas à vous. Les forêts publiques, plus rares, sont nommées plus bas.",
    ),
    "63": Terroir(
        forets="Autour de la plaine de la Limagne, peu boisée, des massifs forestiers sur roches volcaniques "
               "et granitiques : hêtraies et sapinières de la chaîne des Puys et des monts Dore, forêts du "
               "Livradois et du Forez à l'est, des Combrailles à l'ouest.",
        especes="Cèpes, bolets bais et girolles sur ces sols acides, en été puis à l'automne ; chanterelles en "
                "tube et pieds-de-mouton en fin de saison ; morilles au printemps.",
        ou=f"Les hêtraies-sapinières de moyenne montagne, entre 800 et 1{U}300{U}m environ, et les forêts du "
           "Livradois-Forez.",
        savoir="Le massif du Sancy compte des réserves naturelles (vallée de Chaudefour, Chastreix-Sancy), aux "
               "règles propres : la carte hachure les zones protégées et n'y calcule pas d'indice.",
    ),
    "24": Terroir(
        forets="L'un des départements les plus boisés de France : châtaigneraies et chênaies du Périgord vert, "
               "au nord, sur des sols plutôt acides ; chênes pubescents et pins sur les causses calcaires du "
               "Périgord blanc et noir ; pins maritimes de la Double et du Landais, à l'ouest.",
        especes="Le Périgord est une terre de cèpes : châtaigneraies et chênaies en donnent de la fin de l'été "
                "à novembre. Girolles et bolets bais dans les bois acides, lactaires délicieux sous les pins.",
        ou="Les châtaigneraies du Périgord vert et les bois de chênes et de châtaigniers des vallées, sur sols "
           "acides, pour le cèpe et la girolle ; la Double et le Landais pour les espèces des pinèdes.",
        savoir="La forêt périgourdine est presque toute privée : demandez l'accord du propriétaire, et "
               "respectez les panneaux de cueillette interdite.",
    ),
    "40": Terroir(
        forets="La forêt des Landes de Gascogne, plantée de pins maritimes sur le sable, couvre la plus grande "
               "partie du département ; des chênes en lisière, le long des cours d'eau et autour des airiaux. "
               "Au sud de l'Adour, la Chalosse, plus vallonnée et agricole, garde des bois de chênes.",
        especes="Le cèpe sous les chênes et en bordure des pinèdes, surtout à l'automne après les pluies ; le "
                "lactaire délicieux dans les jeunes pins et les forêts du littoral.",
        ou="Les lisières de chênes des pinèdes, les airiaux et les bords de cours d'eau pour le cèpe ; les "
           "forêts dunaires du littoral pour le lactaire délicieux.",
        savoir="Le massif landais est très majoritairement privé. Et les observations y sont trop rares pour "
               "vérifier la carte : ses affinités pour le pin maritime sont moins sûres qu'ailleurs.",
    ),
    "33": Terroir(
        forets="Au sud et à l'ouest, les pins maritimes des Landes girondines et du Médoc ; le long de "
               "l'océan, les forêts dunaires, en grande partie domaniales ; à l'est, l'Entre-deux-Mers et le "
               "Libournais, surtout viticoles, gardent des bois de chênes et de châtaigniers.",
        especes="Le cèpe, dit « cèpe de Bordeaux », sous les chênes et en lisière des pinèdes, de septembre à "
                "novembre ; le lactaire délicieux dans les pinèdes du littoral et les jeunes pins.",
        ou="Les lisières de chênes des pinèdes et les bois de feuillus de l'est pour le cèpe ; les forêts "
           "dunaires du littoral pour le lactaire délicieux.",
        savoir="Dans les forêts dunaires, restez sur les chemins : la dune est fragile. Comme dans les Landes, "
               "l'indice est moins sûr dans les pinèdes de pins maritimes.",
    ),
}
