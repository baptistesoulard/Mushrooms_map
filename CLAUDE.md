# CLAUDE.md — ce qu'il faut savoir avant de toucher au dépôt

État courant et règles. Pas de chiffre qui bouge avec les données ici : les résultats de
validation vivent dans `data/validation.json`, les décisions datées dans les commits.

## Le projet

Site public : carte des forêts de Haute-Savoie favorables à cinq champignons, aujourd'hui
et à J+7. **Indice = habitat × météo** (`champi/modele.py`), publié par cases de 50 m.

```
champi.habitat (à la main) → data/habitat_74.npz (versionné, 8 Mo)
champi.export (chaque jour, GitHub Actions) → site/data/ (jamais versionné) → GitHub Pages
champi.validation (à la main) → data/validation.json (versionné) → copié par l'export
```

## Règles

- **Les seuils vivent dans `champi/especes.py` et nulle part ailleurs.** Le site les relit
  depuis `especes.json` (page Méthode, fiche et fenêtre d'une case) : aucun seuil en dur en JS.
- **Les règles ne se règlent pas sur les observations.** Elles sont trop peu nombreuses
  (une centaine par espèce au mieux) : on vérifie, on ne règle pas. Changer un seuil exige
  une raison mycologique, pas un meilleur AUC.
- **Indice, pas probabilité.** Ne jamais écrire « probabilité » ni « chance de trouver ».
- **Un produit, pas une moyenne** : chaque facteur peut fermer la porte (gel, hors saison).
- **Classes à seuils fixes** (`modele.CLASSES`), jamais des quantiles : un jour sans pousse
  doit donner une carte pâle.
- **Site à usage personnel (décision du 2026-10-31) : l'indice est publié à 50 m**, la
  résolution de calcul, et le site n'est pas indexé (`noindex`). Le repasser en public
  (partage, indexation) obligerait à revenir aux zones de 250 m : une carte publique à 50 m
  enverrait tout le monde aux mêmes coins. Aucune observation ponctuelle n'est affichée (le
  cache GBIF de `data/validation/` ne contient que des données déjà publiques).
- **Zones protégées : hachurées, sans indice.** Leur règlement varie ; le site ne dit
  jamais qu'on peut y cueillir.
- **La rédaction ne lit pas de données** : `redaction.rediger(espèce, faits)`, testable sur
  des faits fabriqués. Typographie : espace insécable avant les unités, jamais de « -0 ».
- **Le site ne dit jamais quoi manger.** Avertissement d'identification sur chaque page
  utile ; centre antipoison de Lyon (compétent pour la Haute-Savoie).
- **Aucun script tiers** : Leaflet est servi depuis `site/vendor/`. Seuls les fonds de carte
  IGN sont appelés depuis le navigateur (déclaré dans `a-propos.html`). Toute nouvelle clé
  `localStorage` se déclare dans `a-propos.html` (test).

## Calcul

- **Tout est en Web Mercator** (`grille.py`) : les images se posent sur Leaflet sans
  reprojection. Pas de PROJ/pyproj : bloqué ou mal configuré sur ce poste Windows (DLL
  bloquée, `proj.db` de PostGIS). Les services renvoient du 3857 ou du WGS84.
- **Grille fine 72 m Mercator ≈ 50 m au sol** ; publiée ×5. Les bords sont calés sur
  360 m pour que le regroupement tombe juste.
- **Voie rapide de l'export** : pluie cumulée et température moyenne sont linéaires, donc
  cumulées aux points météo PUIS interpolées ; le gel est compté case par case.
  `tests/test_export.py` vérifie l'égalité avec le calcul direct (`modele.entrees_meteo`,
  que la validation utilise). Toute nouvelle entrée météo passe par les deux.
- **Températures** : ramenées au niveau de la mer avec l'altitude qu'Open-Meteo a utilisée,
  puis redescendues à la case (`GRADIENT_AIR`, `GRADIENT_SOL`), plus l'effet du versant.
- **Habitat de la France** (`champi/france.py`) : blocs de 512 × 512 cases (25 km),
  construits par `.github/workflows/habitat.yml` (jamais sur le poste : ~20 Go de sources)
  et publiés comme asset de la release `habitat`. Le format des trois PNG est documenté en
  tête du module ; le site et l'export le lisent tous deux. Un bloc refait sur la
  Haute-Savoie retombe sur `habitat_74` à 99,98 % des cases.
- **Latitude** : saisons et plafonds d'altitude sont écrits à 46° N (la Haute-Savoie) et
  décalés ailleurs par la loi de Hopkins (`modele.dates_saison`, `modele.plafond_altitude`) :
  jamais de dates ou d'altitudes régionales en dur. Pas de plancher d'altitude (les cinq
  espèces poussent jusqu'au niveau de la mer).
- **Codage des PNG** (`export.py`, lu par `carte.js`) : indice R = valeur × 200, codes
  251 hors forêt, 252 protégé, 255 hors département ; G pluie, B sol. Changer un code =
  changer les deux fichiers.
- **Open-Meteo** : limites 600 appels pondérés/min, 5 000/h, 10 000/jour ; le job en
  consomme ~1 100. Usage non commercial gratuit : ne pas monétiser le site sans passer à
  l'offre payante.
- **GBIF** : paginer année par année ; une pagination profonde sur une grosse requête se
  bloque plusieurs minutes.

## Limites connues (dites sur le site)

- BD Forêt : la plupart des forêts sont « feuillus en mélange » ou « mixtes » ; le hêtre
  n'est isolé que sur une petite part. Trompette et morille en pâtissent.
- Roche au 1/1 000 000 : la BD Charm-50 (1/50 000) demande un formulaire, pas scriptable.
- Observations GBIF : la plupart sont localisées à la maille de 10 km (INPN) ; seules les
  positions à moins d'1 km servent au test d'habitat, à moins de 10 km au test météo.

## Commandes

```bash
python -m pytest tests -q
python -m champi.export            # réseau ~2 min
python -m champi.habitat           # réseau ; cache/ garde les téléchargements (~360 Mo)
python -m champi.validation        # réseau ; caches dans data/validation/
python -m http.server 8765 --directory site
```

## Pièges du poste (Windows)

- Console en cp1252 : `PYTHONIOENCODING=utf-8` pour les accents dans les sorties.
- Un `cd` en tête de commande persiste : chemins absolus.

## Branches

Une seule branche, `main`, poussée directement. Chaque poussée redéploie le site.
