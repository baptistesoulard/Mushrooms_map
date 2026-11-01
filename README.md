# Champignons en France

Carte des forêts de France métropolitaine où les conditions sont favorables à sept
champignons (cèpe, bolet bai, girolle, trompette de la mort, pied-de-mouton, lactaire
délicieux, morille), aujourd'hui et
pour les sept jours suivants, case par case de 50 m. Recalculée chaque matin, à partir de
données publiques uniquement.

**Indice = habitat × météo**, entre 0 et 1 :

- **habitat** (fixe) : essence dominante (BD Forêt, IGN), roche (BRGM), altitude, pente,
  exposition (RGE ALTI, IGN), zones protégées (INPN) ;
- **météo** (quotidienne) : saison de l'espèce, pluie tombée entre quelques jours et trois
  semaines avant, température du sol de la semaine, jours de gel (AROME et ARPEGE de
  Météo-France, IFS de l'ECMWF, via le dépôt public d'Open-Meteo), corrigées case par case
  de l'altitude et de l'exposition ; saisons et plafonds d'altitude décalés avec la latitude
  (loi de Hopkins).

C'est un indice de conditions favorables, pas une probabilité, et la page « Face aux
observations » mesure s'il fait mieux que le hasard et que des références naïves, avec
les observations publiques de GBIF, sur toute la France et à part dans le Midi.

## Organisation

```
champi/france.py         (GitHub Actions, rarement) habitat par blocs de 25 km → release « habitat »
champi/depot.py          (chaque jour) météo de la France sur la grille AROME (2,5 km)
champi/export_france.py  (chaque jour) champs météo par bloc, aperçu national, résumés → site/data/
champi/pages_departements.py  (chaque jour) une page par département, la semaine de chaque espèce
champi/alertes.py        (chaque jour) notification ntfy quand une espèce passe à « bon » (départements suivis)
site/modele.js           le calcul de l'indice dans le navigateur, case par case
site/sw.js               l'appli hors ligne : copie du site, des données consultées et de l'habitat
site/coins.js            mes coins : trouvailles gardées dans le navigateur, partage par fichier, synchro par un dépôt GitHub privé
champi/especes.py        les règles, espèce par espèce : le seul fichier à toucher pour changer un seuil
champi/modele.py         le même calcul en Python (export, validation), sans entrée-sortie
champi/redaction.py      les phrases du panneau, à partir de faits
champi/validation.py     (à la main) GBIF + météo passée → data/validation.json (France, régions)
site/                    le site statique (HTML, CSS, JS, Leaflet servi localement)
```

Le navigateur calcule l'indice des blocs qu'il affiche : chaque matin, le site ne publie que
la météo (quelques dizaines de Mo), et l'habitat (~250 Mo) ne change qu'à la reconstruction.

## Commandes

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -q                 # le test Python/JS du calcul demande Node
python -m champi.depot                    # réseau : météo de la France, ~3 min, ~500 Mo lus
python -m champi.export_france            # demande site/habitat/ (release « habitat ») ; écrit site/data/
python -m http.server 8765 --directory site
python -m champi.france bloc 18_156       # réseau : construit un bloc (essai) dans habitat/
python -m champi.validation               # réseau : GBIF et météo passée, ~1 h la première fois
```

Pour travailler en local, récupérer l'habitat publié :

```bash
gh release download habitat -p habitat.tar && mkdir -p site/habitat && tar -xf habitat.tar -C site/habitat
```

## Publication

- `.github/workflows/habitat.yml` (à la poussée du code de l'habitat, et chaque dimanche) :
  les blocs qui manquent à l'asset `habitat.tar` de la release `habitat` (984 en tout, en
  40 tâches au plus), ajoutés à ceux déjà publiés. `champi.france.FORMAT` changé : tout.
- `.github/workflows/carte.yml` (chaque matin et à chaque poussée sur `main`) : tests,
  habitat, météo du jour, publication sur GitHub Pages. Aucune donnée du jour n'est commitée.

## Licences des données

IGN (RGE ALTI, BD Forêt, BD TOPO, ADMIN EXPRESS, fonds de carte) et BRGM : Licence
Ouverte. INPN / PatriNat pour les zones protégées. Météo : Météo-France et ECMWF via
Open-Meteo, CC BY 4.0. GBIF : licences propres à chaque jeu de données.
