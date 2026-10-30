"""Paramètres partagés : chemins, département, résolution des grilles."""
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DATA = RACINE / "data"            # versionné : habitat statique, caches de validation
CACHE = RACINE / "cache"          # non versionné : téléchargements bruts
SITE = RACINE / "site"
SITE_DATA = SITE / "data"         # généré chaque jour, jamais versionné

DEPARTEMENT = "74"
NOM_DEPARTEMENT = "Haute-Savoie"

# Grille de calcul : 72 m en Web Mercator, soit 50 m au sol à 46° N.
# La grille publiée regroupe 5 × 5 cases (≈ 250 m) : on publie des zones, pas des coins.
PAS_FIN = 72.0
FACTEUR_PUBLIE = 5
PAS_PUBLIE = PAS_FIN * FACTEUR_PUBLIE

# Marge autour du département, pour que les cases du bord aient leurs voisines.
MARGE_M = 1500.0

USER_AGENT = "Mushrooms_map/0.1 (+https://github.com/baptistesoulard/Mushrooms_map)"
