# CLAUDE.md — ce qu'il faut savoir avant de toucher au dépôt

État courant et règles. Pas de chiffre qui bouge avec les données ici : les résultats de
validation vivent dans `data/validation.json`, les décisions datées dans les commits.

## Le projet

**Champimétéo** (nom du site depuis le 2026-11-06 : `pages.NOM`, titres des pages écrites à la
main, manifeste), sur champimeteo.fr : carte des forêts de France métropolitaine favorables aux
champignons (`especes.ESPECES`), aujourd'hui et à J+7. **Indice = habitat × météo** (`champi/modele.py`),
calculé par cases de 50 m, montré au public par zones de 250 m (cases de 50 m avec mot de passe). Né en Haute-Savoie (2026-10-30), étendu à la France le 2026-10-31 ; bolet
bai et lactaire délicieux ajoutés le même jour (bois acides du bocage, pinèdes du littoral) ;
chanterelle en tube, oronge et hygrophore de mars le 2026-11-01, avec deux espèces des champs
(coulemelle, rosé des prés) calculées par département et par commune seulement.

```
champi.france (habitat.yml, rarement) → release « habitat » (blocs PNG, échantillon) — jamais dans git
champi.depot + champi.export_france (carte.yml, chaque nuit) → site/data/ + pages du matin
  → champi.zones (data/zones/, 250 m) → champi.chiffre (habitat/fin/, 50 m chiffré) → GitHub Pages (+ hébergeur à soi)
site/modele.js : le navigateur calcule l'indice des blocs affichés (zones, ou cases déchiffrées par site/fin.js)
champi.validation (à la main, France et trois régions) → data/validation.json (versionné) → copié par l'export
```

## Règles

- **Les seuils vivent dans `champi/especes.py` et nulle part ailleurs.** Le site les relit
  depuis `especes.json` (calcul, fiche, fenêtre d'une case) : aucun seuil en dur en JS.
- **Le calcul existe deux fois, en Python (`modele.py`, `export_france.CalculChamps`) et
  en JS (`site/modele.js`)** : `tests/test_modele_js.py` vérifie l'égalité case par case
  (Node). Toute modification de l'un passe par l'autre et par ce test.
- **Les règles ne se règlent pas sur les observations.** Elles sont trop peu nombreuses
  (une centaine par espèce au mieux) : on vérifie, on ne règle pas. Changer un seuil exige
  une raison mycologique, pas un meilleur AUC. L'étalonnage d'un instrument (la pluie face
  aux pluviomètres) n'est pas un réglage : il se valide hors échantillon.
- **Indice, pas probabilité.** Ne jamais écrire « probabilité » ni « chance de trouver ».
- **Un produit, pas une moyenne** : chaque facteur peut fermer la porte (gel, hors saison).
- **Classes à seuils fixes** (`modele.CLASSES`), jamais des quantiles : un jour sans pousse
  doit donner une carte pâle. Six classes en marches de 15 points depuis le 2026-11-02
  (« Excellent » dès 0,70) ; une couleur `--classe-k` par classe visible, reprise par
  `partage.CLASSES` (tests). Le verdict d'un département compte les forêts à 0,40 et plus
  (`redaction.SEUILS_NIVEAU`) : « bon » dès 30 % de sa forêt depuis le 2026-11-07 (15 % avant ;
  choix de rédaction, mesuré sur l'export du jour : chanterelle en tube de 66 à 50 départements,
  pied-de-mouton de 91 à 86, sa forêt dépassant 0,40 aux trois quarts presque partout).
- **Ce qui est habituel à cette date** (`climatologie.py` → `data/climatologie.json`, versionné,
  recalculé à la main après la validation) : par espèce et par décade, la part des jours où sa
  météo (indice sans l'habitat) atteint 0,5, sur la météo passée de la validation. Affiché à côté
  du verdict (vignettes, accueil, fiches : « météo favorable 7 années sur 10 à cette date »), parce
  qu'un verdict ne dit pas s'il est ordinaire (le pied-de-mouton « bon » dans 95 départements début
  novembre, question de l'utilisateur du 2026-11-02). Un repère pour le lecteur : aucune règle ni
  aucun seuil n'en dépend.
- **Public à 250 m, fin à 50 m sous mot de passe (décision du 2026-11-06, remplace « site
  personnel à 50 m, non indexé » du 2026-10-31)** : une carte publique à 50 m enverrait tout le
  monde aux mêmes coins. Le site est indexé (`pages.INDEXER`, `robots.txt`, plan du site) et la
  carte de tous est en ZONES de 5 × 5 cases (`zones.py` → `data/zones/<bloc>.png`) : par espèce,
  l'habitat le PLUS FAVORABLE de la zone (forêts hors urbain et zones protégées), l'altitude et
  l'ensoleillement moyens, deux drapeaux ; le navigateur y multiplie la saison et la météo
  (`modele.js`, `cases.habitat`, test Python/JS). Jamais rien de plus fin en clair : les couches
  a, b, d des blocs sont chiffrées chaque nuit (`chiffre.py`, AES-256-GCM, clé PBKDF2 du secret
  `CARTE_FINE_MOT_DE_PASSE` créé par l'utilisateur, jamais dans git ni la conversation) puis
  retirées en clair, secret ou non ; la couche c (communes, zones protégées) reste en clair. Le
  navigateur déchiffre (`site/fin.js`, WebCrypto) et garde la clé (`champi-carte-fine`), pas le
  mot de passe. Un seul mot de passe partagé : le changer = changer le secret, l'adresse des
  fichiers change (`habitat/fin/<id>/`), chacun le redonne. Exploration et fenêtre d'une case
  (essence, roche, pente) : carte fine seulement. Limite assumée : la release « habitat » (données
  ouvertes retraitées) et le code restent publics ; la protection vise la carte affichée, pas un
  développeur décidé. Aucune observation publique ponctuelle n'est affichée. Un passage éventuel
  en service payant est décidé ailleurs : voir `CLAUDE.local.md` s'il existe.
- **Mes coins (`site/coins.js`) : les trouvailles de l'utilisateur restent dans SON
  navigateur** (`champi-coins`). Pas de serveur, pas de carte communautaire (décision du
  2026-10-31) : elle demanderait comptes, modération et données personnelles, et
  enverrait tout le monde aux mêmes coins, souvent en forêt privée. Le partage passe par un
  fichier que l'utilisateur envoie lui-même, et ne contient que SES coins : jamais ceux
  qu'un ami lui a confiés (la sauvegarde, elle, garde tout).
- **Synchro de ses coins entre SES appareils : un dépôt GitHub privé à lui**, lu et écrit par
  le navigateur (API « contents », fichier `coins.json`), ouvert par un lien
  `#depot=compte/dépôt&jeton=…` gardé dans `champi-synchro` puis retiré de l'adresse. Le
  jeton est créé par l'utilisateur, limité à ce dépôt (Contents, lecture et écriture) ; il ne
  passe jamais par la conversation ni par le dépôt du site. Fusion par id, la version la plus
  récente (`maj`) gagne, effacements gardés (`champi-coins-effaces`) pour qu'un coin effacé
  ne revienne pas d'un autre appareil (`coins.fusionner`, testé sous Node). Pas de serveur à
  nous : ce n'est pas un pas vers la carte communautaire.
- **Groupe = ceux à qui l'utilisateur donne le lien** (décision du 2026-10-31), jamais
  l'adresse du site ni un dépôt public. Chacun signe ses coins de son prénom (`champi-nom`,
  `auteur`), demandé avant toute synchro : pas de coin non signé dans le dépôt. On n'efface
  que les siens. Ne partent jamais au dépôt (`coins.aEnvoyer`) : les coins confiés par
  fichier (`de`) et ceux gardés pour soi (`prive`, choisi en rejoignant ou en notant). Un
  jeton en lecture seule (403 à l'écriture) donne un lien qui lit sans écrire.
- **La position est demandée à l'ouverture** (choix de l'utilisateur, 2026-10-31) pour se
  placer sur son département, sauf si le navigateur l'a déjà refusée (`navigator.permissions`) :
  on n'insiste pas, le bouton dit comment réautoriser. Elle est suivie tant que la page est
  visible, ne change jamais un département choisi entre-temps et ne quitte pas l'appareil.
  Le département vient de la commune de la case (blocs d'habitat).
- **Pages du matin** (`pages.py` pour le socle : en-tête, pied, état national) : l'accueil et
  « en ce moment » (`pages_accueil.py`), les fiches espèces (`pages_especes.py`), les
  départements (`pages_departements.py`). Réécrites chaque matin par l'export, hors git
  (`site/index.html`, `en-ce-moment.html`, `especes/`, `departements/`), lisibles sans
  JavaScript, testées sur des résumés fabriqués (`tests/test_pages_accueil.py`, liens compris).
  Aucun coin : départements, altitudes, communes, comme le panneau. Rien en dur : seuils et
  saisons viennent des règles, les chiffres de fiabilité de `validation.json`. Indexées
  (`INDEXER`, vrai depuis le 2026-11-06 : il ouvre les pages, écrit `sitemap.xml` et
  `robots.txt` ; les pages écrites à la main suivent, test).
- **Référencement (2026-11-07)** : chaque page a une adresse canonique (pages écrites à la main
  comprises : la carte en a UNE, sans paramètres ; ses liens datés depuis les tableaux sont
  `nofollow`) et ses données structurées JSON-LD (`pages.donnees_structurees` : `WebSite` sur
  l'accueil, fil d'Ariane, `WebPage` daté, `FAQPage` des départements). Le plan du site date les
  pages du matin (`lastmod`) et liste les pages écrites à la main, jamais `404.html` (servie par
  GitHub Pages à toute adresse inconnue, `<base href="/">`, `noindex, follow`). Une page
  département répond à la recherche qu'on tape : « Où trouver des champignons en Vendée (85) : la
  semaine du 7 novembre » (préposition de chaque département : `pages.dans`), chiffres de tête,
  questions fréquentes répondues avec les chiffres du jour (le texte du JSON-LD est celui de la
  page, test), départements voisins (`carte_departements.voisins`, tirés des contours versionnés).
- **Forêts publiques nommées (décision du 2026-11-07)** : la page d'un département nomme ses forêts
  publiques d'au moins 100 ha (`forets.py` → `data/forets_publiques.json.gz`, versionné, refait par
  `python -m champi.forets` : BD TOPO `foret_publique`, d'après l'ONF, contours simplifiés à 100 m),
  chacune jugée chaque nuit sur ses cases libres de l'échantillon comme un département
  (`export_france.verdict_foret`, `redaction.niveau`) : tableau « Où chercher : les forêts
  publiques », questions fréquentes, description. Toujours la forêt entière, jamais une parcelle ;
  jamais une forêt privée ; les zones protégées restent hors calcul, et la page rappelle qu'une
  forêt publique peut avoir sa réserve ou son arrêté. Remplace « aucun coin » pour ces seules forêts.
- **Adresses lisibles (2026-11-07)** : `departements/vendee/` (`pages.chemin_departement`, nom sans
  accents), `especes/pied-de-mouton/` (`pages.chemin_espece`, des tirets). Les anciennes adresses
  (`departements/85.html`, `especes/pied_de_mouton.html`) restent écrites chaque matin en pages de
  renvoi (`pages.renvoi` : refresh immédiat, canonical, `noindex, follow`) : liens partagés, alertes
  et applis installées continuent de marcher. `carte.json` donne la page de chaque département
  (`page`), l'accueil la met sur ses options (`data-page`) : le JavaScript ne fabrique pas d'adresse.
- **Images de partage** (`partage.py` → `data/partage/`) : l'aperçu des liens dans les
  messageries (`og:image`, 1200 × 630), la carte du jour (la meilleure espèce de chaque pixel
  de 1,15 km, jamais plus fin) et la semaine. Leur adresse change à chaque export
  (`pages.image_partage`) : les messageries gardent longtemps l'image d'une adresse déjà vue.
  Couleurs = jetons de `style.css` (test). Police DejaVu sur les serveurs de GitHub, repli sur
  celle de Pillow. Le bouton Partager (`site/partage.js`) : la feuille de partage du téléphone,
  sinon le lien copié.
- **Classement national « surtout … »** : par surface de forêt aux bonnes conditions
  (`pages.surface_bonne`), pas par indice moyen, qui met en tête Paris et la petite couronne
  (quelques bois suffisent à la moyenne). « Où chercher en France » sur la carte garde l'indice
  moyen, et le dit.
- **La carte vit sous `/carte/` depuis le 2026-11-01**, avec `<base href="../">` : tout ce
  qu'elle charge (scripts, données, habitat, `sw.js`) reste à la racine, où est l'accueil. Les
  anciens liens de la racine (`?departement=…`, lien de groupe `#depot=…`, appli installée
  avant, figée sur la racine sur iPhone) sont renvoyés à la carte par le script de tête de
  l'accueil (`pages_accueil.RENVOI`). Le manifeste démarre sur `carte/` et garde l'identité
  d'avant (`"id": "/Mushrooms_map/"`) pour que les applis installées se mettent à jour. La
  carte lit `?departement=&espece=&jour=` (une date) et `?autour` (centrer sur la position).
- **Espèces des prés** (`Espece.milieu == "pre"` : coulemelle, rosé des prés) : jamais de carte
  case par case, les prés sont presque tous privés (décision du 2026-11-01). Calculées chaque
  matin sur l'échantillon des prés (`prairies.py` → `data/prairies.npz`, versionné : un point
  tous les 576 m dans les prairies, pelouses et mosaïques agricoles de Corine Land Cover, avec
  altitude et commune), publiées dans les résumés par département et par commune comme les
  autres (pages, semaine, alertes, images). Affinités par milieu (`prairies.MILIEUX`), pas
  d'essence, de roche ni de pente. Sur la carte, COMMUNE PAR COMMUNE (jamais un pré) : l'indice
  moyen des prés de chaque commune (`export_france.indices_communes`, rien sous 25 ha de prés),
  publié en table (`data/communes/<espèce>_<k>.png`, peinte de près avec la couche « c » des
  blocs) et en aperçu (chaque pixel prend sa commune) ; un bandeau le dit. Vérifiées
  sur le seul moment (pas d'habitat à 50 m à tester). Le fichier porte l'empreinte des communes
  de l'habitat : un habitat refait avec une autre liste oblige à relancer `python -m champi.prairies`
  (sinon l'export saute ces espèces et le dit).
- **La carte, lot B (2026-11-01)** : la fenêtre d'une case en tuiles, l'indice sur 100 avec sa
  jauge aux seuils des classes et « ce qui limite » (`modele.partsHabitat`, dont le produit refait
  l'habitat : test) ; « Y aller » (`itineraire.js`, Google Maps, Waze, Plans : rien ne part avant le
  toucher) ; « Forêts publiques seulement ». « Que chercher ici ? » classe les espèces pour la zone
  affichée au même verdict que les départements (`export_france.Vue` → `data/vue/<jour>.png`, grille
  de 9,2 km, `ici.js` : test Python/JS). Sur téléphone, la carte plein écran et le panneau en feuille
  qui glisse du bas (`feuille.js`), une case touchée s'y ouvre. Présentation de première visite
  (`guide.js`, `champi-guide`).
- **Identité visuelle (2026-11-07)** : le logo est un cèpe en réserve dans une goutte de pluie (`icones.py`,
  une seule géométrie) : en ligne dans la barre, la goutte à l'accent et le cèpe aux couleurs du creux
  (le fond de la barre en mode sombre, classes `marque-*`), et en fichiers
  (`favicon.svg`, `favicon.ico`, icônes de l'appli) refaits par `python -m champi.icones` (test). Plus de
  champignon rouge à pois : il évoquait l'amanite tue-mouches. Le nom s'écrit « Champi » + « météo » à
  l'accent. Titres en garalde des systèmes (`--police-titre` : Palatino, Iowan, Noto Serif), aucune
  police téléchargée ni tierce. Sous la une, un sous-bois dessiné (`pages_accueil.SOUS_BOIS`, jetons
  `--decor-*`). La hauteur de la barre est `--hauteur-barre` ; `--barre` est la couleur des tranches
  d'altitude (le même nom pour les deux vidait la carte sur téléphone en mode sombre).
- **Barre du haut, sur toutes les pages** (`pages.barre`, rubriques `pages.BARRE`) : les pages du
  matin l'écrivent ; celles écrites à la main (`pages.STATIQUES`, la carte comprise) la portent
  entre `<!-- barre -->` et `<!-- /barre -->`, réécrite par `python -m champi.pages barre` (test).
  Sur écran étroit, un menu qui s'ouvre sans JavaScript.
- **Dessins et photos des espèces** : un dessin SVG par espèce (`site/img/especes/<code>.svg`, fait
  main : liste de la carte, pages) ; une photo de Wikimedia Commons, l'image de l'article de
  Wikipédia (`python -m champi.photos` → `<code>.jpg` et `data/photos.json`), licences libres
  seulement et CRÉDITÉE partout où elle paraît. Une photo aide à chercher, jamais à identifier.
- **Accueil** (`pages_accueil.page_accueil`) : la une (la réponse du jour en une phrase,
  `en_bref`, la carte de France, la carte, autour de moi, un département au choix), les espèces
  en saison en fiches illustrées, la semaine, puis comment ça marche, les fonctions, la
  vérification (détail replié), les départements (repliés) et les questions.
  La carte de la une (2026-11-07) : l'espèce la mieux placée d'abord, des boutons pour les espèces
  aux bonnes conditions au moins par endroits (`especes_de_la_une`, six au plus) et « Toutes »,
  cachés sans JavaScript (`pages.js`, `uneCarte` : l'espèce de `champi-espece` d'abord) ; les
  images `partage/carte-france[-<espèce>].png` sont peintes sur le cadre Mercator des contours
  (`carte_departements.cadre_une`, `partage.carte_cadre`) et les départements s'y posent en SVG,
  chacun menant à `carte/?departement=…&espece=…`. Le cadre de `departements_carte.json` (absent
  du fichier d'origine) a été recalé le 2026-11-07 sur les communes des blocs ; `construire` l'écrit.
- **Page des départements** : une carte de France cliquable (`carte_departements.py` →
  `data/departements_carte.json`, contours ADMIN EXPRESS simplifiés à ~2 km, versionnés), chaque
  département au verdict de l'espèce et du jour choisis (dessins des espèces pour choisir, l'espèce
  vue sur la carte d'abord) ; sans JavaScript, l'espèce du moment aujourd'hui. Le classement à côté
  suit l'ordre de « surtout » (`pages.national`).
- **Jamais un lien dans un lien** : le navigateur coupe alors l'élément en morceaux (bug du
  2026-11-01, le crédit d'une photo dans une fiche cliquable). Une photo dans un lien n'a pas son
  crédit à côté (`figure_photo(..., credit=False)`), il est en bas de page ; le test d'intégration
  des pages générées le contrôle.
- **Les niveaux de la carte (2026-11-07)**, chacun avec son rôle : sous le zoom 8 (`SYNTHESE`),
  la vue France, chaque carré au verdict des départements, de 18,4 km au zoom 5 (`CARRES_GROS` :
  quatre carrés de 9,2 km regroupés dans le navigateur, pondérés par leur forêt), de 9,2 km au zoom 6
  (`data/vue`, comme la carte de l'accueil et « Que chercher ici ? ») puis de 4,6 km au zoom 7 (`CARRES_FINS`,
  `data/vue_fine`, `export_france.VUE_FINE`), rien sous `carre_min_km2` de forêt (5 % du carré) ;
  les espèces des prés gardent leurs communes ; Leaflet choisit ses tuiles au zoom ARRONDI et les
  retire au zoom exact : les seuils suivent le zoom arrondi ; du zoom 8 à 10,5, l'aperçu de 1,15 km, la MEILLEURE case de chaque
  pixel (`export_france.Apercu`, la règle des zones ; la moyenne diluée d'avant foncissait d'un
  coup au zoom 11) ; dès le zoom 11 (`DETAIL`), les zones de 250 m ou les cases de 50 m. La légende
  de l'onglet Ici suit le niveau. Rien de plus fin que 250 m en clair.
- **Le panneau de la carte** : l'espèce (bouton illustré, liste en boîte de dialogue, en saison
  d'abord), le jour, puis quatre onglets — Ici (que chercher ici, légende), Département (verdict,
  semaine, altitude, communes, France), L'espèce (fiche), Mes outils (coins, alertes, exploration).
  Fonds : plan IGN grisé par défaut (l'indice ressort), relief (estompage IGN), photos ; le choix
  est gardé (`champi-fond`). L'indice a son calque (« indice ») en mode produit sur le plan et le relief
  (pas sur les photos) ; par-dessus, les contours des départements (calque « contours »,
  `departements_carte.json` publié par l'export) : les limites ENTRE départements seulement
  (`carte_departements.frontieres`, sans le littoral ni les frontières, qui doublaient le plan avec
  l'écart de la simplification), en trait fin, blanc sur les carrés de la vue France, sombre sur les
  pixels de la vue régionale ; le département choisi, côte comprise, en trait sombre épais. Deux
  précisions : ~2 km jusqu'au zoom 8,5 ; ~250 m dès le zoom 9 et jusqu'au zoom 13
  (`data/departements_fin.json`, versionné, tiré des communes des blocs d'habitat par
  `python -m champi.carte_departements fin`, sans réseau ; publié en `contours_fins/`, la carte ne
  charge que les limites et le département choisi). Le tracé à ~2 km s'arrête au zoom 11 :
  simplifiés à ~2 km, ils s'écarteraient des vraies limites de plus près), puis les marques
  (position, coins). Les noms de lieux de l'IGN (`GEOGRAPHICALNAMES.NAMES`) ont été essayés
  par-dessus le 2026-11-07, puis retirés : doublés par ceux du plan, peu satisfaisants.
- **Alertes réservées au groupe (décision du 2026-11-07)** : sans lien de groupe sur l'appareil, la
  section « Mes alertes » de la carte reste cachée (sauf alertes encore à retirer) ; ni l'accueil ni le
  guide ne les annoncent. Une version publique gratuite passerait par un petit service (Worker
  Cloudflare) pour ranger les abonnements : écartée pour l'instant.
- **Alertes personnalisées** (`site/alertes.js` → `alertes.json` du dépôt privé du lien de groupe
  → `alertes.py`, étape de `carte.yml` avant le déploiement) : un département, des espèces, un
  seuil (« bon » ou « par endroits ») ; notification Web Push quand une espèce DEVIENT favorable
  dans les 7 jours (par différence avec la publication en ligne, sans état gardé), rappel la
  veille, « à confirmer » au-delà de 3 jours. Clé publique dans `config.VAPID_PUBLIQUE`, clé privée
  en secret `VAPID_PRIVEE` (jamais dans git ; la changer oblige à se réabonner) ; lecture du dépôt
  par `ALERTES_JETON` et `ALERTES_DEPOT`. L'envoi (pywebpush) ne tourne que dans Actions : ce poste
  bloque la DLL de `cryptography`. `continue-on-error` : une alerte manquée n'empêche jamais la
  carte de paraître. Plus de ntfy (décision du 2026-11-01). Le rappel ne sonne qu'à la première
  publication du jour (le workflow peut en faire plusieurs).
- **GitHub part en retard, ou pas du tout** : ses départs programmés sont « au mieux » (6 et 7 h
  de retard les 31 octobre et 1er novembre 2026, rien à 7 h 15 le 2 novembre). `carte.yml` prend
  donc trois rendez-vous par nuit, tous après 23 h UTC (avant, `publication.jour_de_la_carte`
  donnerait encore la veille, que la garde trouverait en ligne), et le job `verifier`
  (`champi/publication.py`, bibliothèque standard seulement) arrête en quelques secondes ceux qui
  trouvent la carte du jour déjà publiée. La concurrence se règle par job, pas par workflow : un
  départ qui s'arrête n'annule jamais un calcul en attente. Si le retard dépasse encore la nuit,
  le remède est un déclencheur extérieur (`workflow_dispatch` appelé par un service de cron, avec
  un jeton que l'utilisateur crée lui-même).
- **Domaine `champimeteo.fr` (2026-11-06)**, servi par GitHub Pages (domaine déclaré dans les
  réglages Pages, pas de fichier CNAME : le déploiement passe par Actions ; DNS chez OVH). L'ancienne
  adresse `baptistesoulard.github.io/Mushrooms_map/` y renvoie ; le bandeau de déménagement est
  retiré. `config.ADRESSE` vaut le domaine (la variable `SITE_ADRESSE` peut la remplacer) : un
  site injoignable fait comparer les alertes à vide, donc tout renvoyer. Un hébergeur en France
  plus tard ne change que le DNS : l'adresse, donc ce que gardent les navigateurs, reste la même.
- **Hébergeur à soi** (job `heberger` de `carte.yml`, en plus de GitHub Pages) : `rsync` par SSH du
  site déployé, rien ne tourne tant que la variable `DEPLOI_HOTE` est vide (`DEPLOI_COMPTE`,
  `DEPLOI_DOSSIER`, `DEPLOI_CONNU` = ligne de `ssh-keyscan` ; secret `DEPLOI_CLE`, créé par
  l'utilisateur). `SITE_ADRESSE` (→ `CHAMPI_ADRESSE` → `config.ADRESSE`) se renseigne en même temps :
  la garde, les alertes et les aperçus regardent cette adresse. Changer d'adresse remet chaque
  navigateur à zéro (coins, lien de groupe, alertes : le stockage suit l'adresse du site). Zones
  publiques et couches chiffrées ne changent pas avec l'hébergeur. Mentions légales (`a-propos.html`) : nom
  et adresse de l'hébergeur effectif.
- **Une page du jour porte sa date** (`pages.calcule_pour`, sur sa ligne « Calculé le ») : quand
  la mise à jour de la nuit manque, `pages.js` le dit en tête de page, comme `carte.js` sur la carte.
- **Appli installable et hors ligne** (`manifest.webmanifest`, `sw.js`) : le site et les données
  du jour en « réseau d'abord » (copie au-delà de 5 s), l'habitat en « copie d'abord ». Changer
  le format des blocs (`france.FORMAT`) oblige à incrémenter `sw.VERSION`, sinon les anciennes
  copies restent. Ni fonds IGN, ni GitHub, ni coins dans ces caches.
- **Zones protégées : hachurées, sans indice** (réserves, arrêtés de biotope, cœurs de parcs
  nationaux). Leur règlement varie ; le site ne dit jamais qu'on peut y cueillir.
- **La rédaction ne lit pas de données** : `redaction.rediger(espèce, faits)`, testable sur
  des faits fabriqués. Typographie : espace insécable avant les unités, jamais de « -0 ».
- **Le site ne dit jamais quoi manger.** Avertissement d'identification sur chaque page
  utile ; les huit centres antipoison (`avant-de-partir.html`, `carte.js` pour le plus
  proche), vérifiés sur centres-antipoison.net.
- **Aucun script tiers** : Leaflet est servi depuis `site/vendor/`. Seuls les fonds de carte
  IGN sont appelés depuis le navigateur, plus `api.github.com` si la synchro des coins est
  active (déclarés dans `a-propos.html`). Toute nouvelle clé `localStorage` se déclare dans
  `a-propos.html` (test).

## Calcul

- **Couche « d » des blocs** (`sol.py`, ajoutée après coup par `sol.yml`, d'emblée par
  `france.construire_bloc`) : bits 0-6 = pH du sol × 10 (SoilGrids, copie versionnée
  `data/ph_sol.npz`), bit 7 = zone urbanisée (Corine Land Cover 2018, classes 1xx). Ses bois ne
  sont pas de la forêt : ni indice, ni exploration, ni échantillon, ni validation. Une release
  sans couche « d » reste lisible (rien d'exclu, pH inconnu).
- **Le pH remplace la roche pour les espèces `sol_ph` seulement** (cèpe, bolet bai, girolle) :
  SoilGrids tasse les sols calcaires vers 6, une règle calcicole n'y trouve pas son seuil
  (mesuré : la trompette y perdait). La validation publie toujours les deux variantes.

- **Tout est en Web Mercator** (`grille.py`) : les images se posent sur Leaflet sans
  reprojection. Pas de PROJ/pyproj : bloqué ou mal configuré sur ce poste Windows (DLL
  bloquée, `proj.db` de PostGIS). Les services renvoient du 3857 ou du WGS84.
- **Grille de 72 m Mercator ≈ 50 m au sol**, calée sur l'origine du Mercator ; blocs de
  512 × 512 cases (36 864 m). Format des trois PNG d'un bloc : en tête de `france.py`, lu
  par `carte.js` et `export_france.py`.
- **L'habitat se construit par complément** : `habitat.yml` (poussée de `france.py`,
  `habitat.py` ou `sources.py`, et chaque dimanche) ne construit que les blocs qui manquent
  à la release, et publie même si des groupes échouent (`blocs.json` liste les
  `manquants`). Changer le format ou le calcul d'un bloc = incrémenter `france.FORMAT`,
  sinon les blocs publiés restent à l'ancien calcul.
- **Relief** : lu en latitude/longitude puis interpolé (`sources.wms_bil_lonlat`), lissé
  3 × 3 avant la pente. Demandé en Mercator, le service double une ligne sur trois : stries.
- **Roche** : lue dans `data/lithologie_1m.geojson.gz`, copie versionnée de la couche du
  BRGM (`python -m champi.habitat lithologie` la refait, depuis le poste). Le pare-feu du
  BRGM rejette les serveurs de GitHub ; et sur une emprise sans roche, le service renvoie un
  corps vide, pas un JSON vide. Ne pas revenir au service dans la construction.
- **Météo** (`depot.py`) : le dépôt AWS d'Open-Meteo (pas l'API, pas de quota). AROME
  2,5 km, puis ARPEGE, puis IFS, point par point ; température du sol d'IFS. Températures
  ramenées au niveau de la mer avec le relief de chaque modèle, puis redescendues à la case
  (`GRADIENT_AIR`, `GRADIENT_SOL`), plus l'effet du versant. Pas de correction de pluie :
  mesurée inutile hors échantillon sur 1 801 pluviomètres.
- **Ce que publie l'export** : par bloc, les champs météo déjà cumulés aux points AROME
  (pluie de chaque fenêtre, sol sur 7 jours, Tmin de chaque jour), en dixièmes ; le panneau
  et l'aperçu sont calculés sur l'échantillon (une case sur 16) avec ces MÊMES champs
  arrondis, pour dire la même chose que la carte.
- **Voie rapide** (`export.Calcul`) : pluie cumulée et température moyenne sont linéaires,
  donc cumulées aux points PUIS interpolées ; le gel est compté case par case.
  `tests/test_export.py` vérifie l'égalité avec `modele.entrees_meteo` (que la validation
  utilise).
- **Latitude** : saisons et plafonds d'altitude sont écrits à 46° N (la Haute-Savoie) et
  décalés ailleurs par la loi de Hopkins (`modele.dates_saison`, `modele.plafond_altitude`) :
  jamais de dates ou d'altitudes régionales en dur. Un plancher d'altitude (`Espece.plancher`,
  décalé de même) pour les seules espèces de montagne : l'hygrophore de mars. Les autres
  poussent jusqu'au niveau de la mer.
- **GBIF** : paginer par périodes de moins de 8 000 observations, coupées en deux tant
  qu'il le faut (`validation._pages`) : au-delà d'environ 10 000, une page met plusieurs
  minutes à venir. Seules les incertitudes
  DÉCLARÉES comptent, filtrées chez GBIF, pour les cas comme pour le fond : sans elle, une
  donnée peut être le centre d'une maille de 10 km.
- **Météo passée de la validation** : le dépôt AWS d'Open-Meteo, lu à distance par plages
  d'octets (`validation.Distant`, `omfiles.from_fsspec`) : seuls les points utiles sont
  téléchargés. Températures d'ERA5-Land (0,1°), pluie d'ERA5 (0,25° ; le dépôt n'a pas celle
  d'ERA5-Land). Un fichier par année jusqu'en 2021, des morceaux de 21 jours ensuite. Relief
  du modèle (`static/HSURF.om`) pour ramener les températures à la case. Caches dans
  `cache/validation/` (hors git) ; la validation ne passe plus par l'API (quota).
- **Régions de la validation** (`validation.REGIONS`) : chacune face à son propre fond. Le
  département vient de la commune de la case, dans les blocs de la release.

## Limites connues (dites sur le site)

- BD Forêt : beaucoup de forêts sont « feuillus en mélange » ou « mixtes » ; le hêtre est
  souvent invisible. Trompette et morille en pâtissent. Une seule classe « Pins », sans âge :
  le lactaire délicieux voit toutes les pinèdes pareilles.
- Affinités pour les essences du Midi (pin d'Alep, chênes verts, pin maritime) : moins sûres ;
  vérifiées à part (pourtour méditerranéen) ; les Landes de Gascogne, trop peu observées,
  ne se jugent pas.
- Roche au 1/1 000 000 : la BD Charm-50 (1/50 000) demande un formulaire, pas scriptable.
- Observations GBIF : la plupart sont localisées à la maille de 10 km (INPN) ; seules les
  positions de précision déclarée à moins d'1 km servent au test d'habitat, à moins de
  10 km au test météo.

## Commandes

```bash
python -m pytest tests -q
python -m champi.depot                  # réseau ~3 min ; gardé 3 h dans cache/
python -m champi.export_france          # demande site/habitat/ (asset de la release « habitat »)
python -m champi.zones                  # après l'export : data/zones/ (carte publique, 250 m)
python -m champi.chiffre                # ensuite : chiffre a, b, d (CARTE_FINE_MOT_DE_PASSE), retire le clair
python -m champi.france bloc 18_156     # un bloc, pour essayer (habitat/)
python -m champi.validation meteo       # réseau ; la météo passée des cas, sans attendre le fond
python -m champi.validation             # réseau (~1 h la 1re fois) ; demande site/habitat/ ; caches dans cache/validation/
python -m champi.climatologie           # après la validation, ~5 min : data/climatologie.json (ce qui est habituel)
python -m champi.prairies               # réseau, ~10 min : data/prairies.npz (les prés), à refaire avec l'habitat
python -m champi.carte_departements     # réseau, quelques secondes : data/departements_carte.json (contours)
python -m champi.forets                 # réseau, quelques minutes : data/forets_publiques.json.gz (forêts publiques nommées)
python -m champi.carte_departements fin # demande site/habitat/, ~30 s : data/departements_fin.json (contours fins)
python -m champi.photos                 # réseau : les photos des espèces (Wikimedia Commons), avec leurs crédits
python -m champi.icones                 # le logo : favicon.svg, favicon.ico, icônes de l'appli
python -m http.server 8765 --directory site   # la carte : /carte/ ; les pages du matin demandent l'export
```

## Pièges du poste (Windows)

- Console en cp1252 : `PYTHONIOENCODING=utf-8` pour les accents dans les sorties.
- Un `cd` en tête de commande persiste : chemins absolus.
- Disque C: presque plein : l'habitat se construit dans GitHub Actions, et `cache/depot/`
  (~1 Go de grilles météo) se vide sans risque.
- Le panneau navigateur masqué suspend `Image.decode()` : `carte.js` décode par
  `createImageBitmap`.

## Branches

Une seule branche, `main`, poussée directement. Chaque poussée redéploie le site.
