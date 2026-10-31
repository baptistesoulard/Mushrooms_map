# Champignons en Haute-Savoie

Carte des forêts de Haute-Savoie où les conditions sont favorables à cinq champignons
(cèpe, girolle, trompette de la mort, pied-de-mouton, morille), aujourd'hui et pour les
sept jours suivants. Recalculée chaque matin, à partir de données publiques uniquement.

**Indice = habitat × météo**, entre 0 et 1, sur des cases de 50 m (le site, à usage
personnel, les publie telles quelles) :

- **habitat** (fixe) : essence dominante (BD Forêt, IGN), roche (BRGM), altitude, pente
  (RGE ALTI, IGN) ;
- **météo** (quotidienne) : saison de l'espèce, pluie tombée entre quelques jours et trois
  semaines avant, température du sol de la semaine, jours de gel (Open-Meteo), corrigées
  case par case de l'altitude et de l'exposition.

C'est un indice de conditions favorables, pas une probabilité, et la page « Face aux
observations » mesure s'il fait mieux que le hasard et que des références naïves, avec
les observations publiques de GBIF.

## Organisation

```
champi/habitat.py     (à la main, rarement) relief, forêts, roche, zones protégées → data/habitat_74.npz
champi/export.py      (chaque jour)         météo → indice par espèce et par jour → site/data/
champi/validation.py  (à la main)           GBIF + météo passée → data/validation.json
champi/especes.py     les règles, espèce par espèce : le seul fichier à toucher pour changer un seuil
champi/modele.py      le calcul, sans entrée-sortie
champi/redaction.py   les phrases du panneau, à partir de faits
site/                 le site statique (HTML, CSS, JS, Leaflet servi localement)
```

## Commandes

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -q
python -m champi.export          # réseau : météo du jour, ~2 min ; écrit site/data/
python -m http.server 8765 --directory site
python -m champi.habitat         # réseau : reconstruit l'habitat (cache/ garde les téléchargements)
python -m champi.validation      # réseau : GBIF et météo passée, ~15 min la première fois
```

## Publication

Le workflow `.github/workflows/carte.yml` tourne chaque matin (et à chaque poussée sur
`main`) : tests, calcul, publication sur GitHub Pages. Aucune donnée du jour n'est
commitée. À activer une fois : *Settings → Pages → Source : GitHub Actions*.

## Licences des données

IGN (RGE ALTI, BD Forêt, BD TOPO, ADMIN EXPRESS, fonds de carte) et BRGM : Licence
Ouverte. INPN / PatriNat pour les zones protégées. Open-Meteo : CC BY 4.0, usage non
commercial gratuit. GBIF : licences propres à chaque jeu de données.
