# Champignons en France

Carte des forêts de France métropolitaine où les conditions sont favorables aux champignons
(cèpe, bolet bai, girolle, trompette de la mort, pied-de-mouton, lactaire délicieux, morille,
chanterelle en tube, oronge, hygrophore de mars), aujourd'hui et pour les sept jours suivants,
case par case de 50 m ; et, par département et par commune seulement, deux champignons des prés
(coulemelle, rosé des prés). Recalculée chaque matin, à partir de données publiques uniquement.

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
champi/pages*.py         (chaque jour) les pages lisibles sans JavaScript : accueil, « en ce moment »,
                         fiches espèces, une page par département
champi/partage.py        (chaque jour) images de partage : l'aperçu des liens dans les messageries
champi/alertes.py        (chaque jour) notifications des alertes personnalisées (Web Push), envoyées depuis GitHub Actions
site/modele.js           le calcul de l'indice dans le navigateur, case par case
site/sw.js               l'appli hors ligne : copie du site, des données consultées et de l'habitat
site/partage.js          le bouton Partager : feuille de partage du téléphone, sinon lien copié
site/itineraire.js       « Y aller » : Google Maps, Waze ou Plans, depuis une case ou un coin
site/ici.js              « Que chercher ici ? » : les espèces de la zone affichée (grille de 9 km)
site/feuille.js          sur téléphone, le panneau qui glisse du bas
site/guide.js            la présentation de la première visite
site/img/especes/        un dessin (SVG) et une photo (Wikimedia Commons, crédits dans data/photos.json) par espèce
champi/photos.py         (rarement) les photos des espèces, depuis Wikipédia et Wikimedia Commons
champi/carte_departements.py  (rarement) les contours des départements de la page des départements (IGN)
site/alertes.js          mes alertes : département, espèces, seuil ; abonnement de l'appareil par le lien de groupe
site/coins.js            mes coins : trouvailles gardées dans le navigateur, partage par fichier, synchro par un dépôt GitHub privé
champi/sol.py            couche « d » des blocs : pH du sol (SoilGrids) et zones urbanisées (Corine)
champi/prairies.py       (rarement) les prés de France (Corine) : data/prairies.npz, pour les espèces des champs
champi/especes.py        les règles, espèce par espèce : le seul fichier à toucher pour changer un seuil
champi/modele.py         le même calcul en Python (export, validation), sans entrée-sortie
champi/redaction.py      les phrases du panneau, à partir de faits
champi/validation.py     (à la main) GBIF + météo passée → data/validation.json (France, régions)
champi/climatologie.py   (à la main, après) ce qui est habituel à chaque date → data/climatologie.json
site/                    le site statique (HTML, CSS, JS, Leaflet servi localement) ; la carte est sous site/carte/
```

Le navigateur calcule l'indice des blocs qu'il affiche : chaque matin, le site ne publie que
la météo (quelques dizaines de Mo), et l'habitat (~250 Mo) ne change qu'à la reconstruction.

## Commandes

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -q                 # le test Python/JS du calcul demande Node
python -m champi.depot                    # réseau : météo de la France, ~3 min, ~500 Mo lus
python -m champi.export_france            # demande site/habitat/ (release « habitat ») ; écrit site/data/
python -m http.server 8765 --directory site   # la carte : http://localhost:8765/carte/
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
- `.github/workflows/carte.yml` (chaque nuit et à chaque poussée sur `main`) : tests,
  habitat, météo du jour, publication sur GitHub Pages. Aucune donnée du jour n'est commitée.
  GitHub lance ses départs programmés avec parfois des heures de retard : trois rendez-vous par
  nuit, et le premier qui part publie (les suivants voient la carte du jour en ligne et s'arrêtent).

## Licences des données

IGN (RGE ALTI, BD Forêt, BD TOPO, ADMIN EXPRESS, fonds de carte) et BRGM : Licence
Ouverte. INPN / PatriNat pour les zones protégées. Météo : Météo-France et ECMWF via
Open-Meteo, CC BY 4.0. GBIF : licences propres à chaque jeu de données.
