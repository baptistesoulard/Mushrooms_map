# CLAUDE.md — ce qu'il faut savoir avant de toucher au dépôt

État courant et règles. Pas de chiffre qui bouge avec les données ici : les résultats de
validation vivent dans `data/validation.json`, les décisions datées dans les commits.

## Le projet

Site personnel : carte des forêts de France métropolitaine favorables à sept champignons
(`especes.ESPECES`), aujourd'hui et à J+7. **Indice = habitat × météo** (`champi/modele.py`),
par cases de 50 m. Né en Haute-Savoie (2026-10-30), étendu à la France le 2026-10-31 ; bolet
bai et lactaire délicieux ajoutés le même jour (bois acides du bocage, pinèdes du littoral).

```
champi.france (habitat.yml, rarement) → release « habitat » (blocs PNG, échantillon) — jamais dans git
champi.depot + champi.export_france (carte.yml, chaque matin) → site/data/ → GitHub Pages
site/modele.js : le navigateur calcule l'indice des blocs affichés
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
  doit donner une carte pâle.
- **Site à usage personnel (décision du 2026-10-31) : l'indice est publié à 50 m**, la
  résolution de calcul, et le site n'est pas indexé (`noindex`). Le repasser en public
  (partage, indexation) obligerait à revenir à des zones de 250 m au moins : une carte
  publique à 50 m enverrait tout le monde aux mêmes coins. Aucune observation publique
  ponctuelle n'est affichée.
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
  jamais de dates ou d'altitudes régionales en dur. Pas de plancher d'altitude.
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
python -m champi.france bloc 18_156     # un bloc, pour essayer (habitat/)
python -m champi.validation meteo       # réseau ; la météo passée des cas, sans attendre le fond
python -m champi.validation             # réseau (~1 h la 1re fois) ; demande site/habitat/ ; caches dans cache/validation/
python -m http.server 8765 --directory site
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
