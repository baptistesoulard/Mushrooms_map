"""Paramètres partagés : chemins, département, résolution des grilles."""
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DATA = RACINE / "data"            # versionné : habitat statique, caches de validation
CACHE = RACINE / "cache"          # non versionné : téléchargements bruts
SITE = RACINE / "site"
SITE_DATA = SITE / "data"         # généré chaque jour, jamais versionné

DEPARTEMENT = "74"
NOM_DEPARTEMENT = "Haute-Savoie"

# Grille de calcul : 72 m en Web Mercator, soit 50 m au sol à 46° N. Le site, à usage
# personnel (décision du 2026-10-31), publie l'indice à cette résolution.
PAS_FIN = 72.0
# Zones de 250 m (5 × 5 cases) : pluie de la fenêtre dans la fenêtre d'une case, et test
# d'habitat de la validation (positions connues à 1 km près). Les bords de grille sont
# calés sur ce pas pour que le regroupement tombe juste.
FACTEUR_ZONE = 5
PAS_ZONE = PAS_FIN * FACTEUR_ZONE

# Marge autour du département, pour que les cases du bord aient leurs voisines.
MARGE_M = 1500.0

USER_AGENT = "Mushrooms_map/0.1 (+https://github.com/baptistesoulard/Mushrooms_map)"
# Le site publié. Chez un hébergeur à soi (`carte.yml`, job « heberger »), la variable du dépôt
# SITE_ADRESSE la donne à tout le workflow (CHAMPI_ADRESSE) : la garde de la nuit, les alertes et
# les aperçus de partage regardent alors cette adresse-là.
ADRESSE = (os.environ.get("CHAMPI_ADRESSE") or "https://baptistesoulard.github.io/Mushrooms_map/").rstrip("/") + "/"

# Alertes : clé publique des notifications (Web Push, courbe P-256). La clé privée assortie est le
# secret VAPID_PRIVEE du dépôt, jamais dans git : la changer oblige chacun à se réabonner.
VAPID_PUBLIQUE = "BFhHLkWa6-ucIftTKmUxfKv8oDjIOkywthD2EoqzDpmw28akKzUaVOtmgOtvUGeB4H6Dy3x6vQNfXS6ZoxLBQiY"
