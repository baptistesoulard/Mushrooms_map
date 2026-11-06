"""La carte fine (cases de 50 m), chiffrée : seul qui a le mot de passe la voit (décision du 2026-11-06).

La carte publique est en zones de 250 m (`zones.py`). Les couches d'habitat qui permettraient
de refaire le 50 m (a : altitude, essence, forêt publique ; b : pente, ensoleillement, roche ;
d : pH, zones urbanisées) sont publiées chiffrées, et leurs PNG en clair retirés du site avant
la mise en ligne. La couche c (communes, zones protégées) reste en clair : elle ne dit rien des
forêts, et la carte publique en a besoin (département de la position, hachures).

Le site n'a pas de serveur : le navigateur déchiffre lui-même (`site/fin.js`, WebCrypto).
- Clé : PBKDF2-HMAC-SHA256 du mot de passe (secret du dépôt `CARTE_FINE_MOT_DE_PASSE`, créé
  par l'utilisateur, jamais dans git ni dans la conversation), sel et itérations de `config`.
- Chaque fichier : AES-256-GCM, le nom du PNG en données associées (un fichier ne passe pas
  pour un autre). Le vecteur d'initialisation est tiré du contenu (HMAC) : même bloc, même
  fichier chiffré d'une nuit à l'autre, les copies du navigateur restent bonnes.
- `carte.json` « fine » : l'identifiant de la clé (12 premiers chiffres hexadécimaux de son
  SHA-256), qui nomme aussi le dossier (`habitat/fin/<id>/`) : un nouveau mot de passe change
  d'adresse, aucune copie ancienne ne sert. Le navigateur s'en sert pour reconnaître un bon
  mot de passe.

Sans mot de passe (secret absent), les couches en clair sont retirées quand même : pas de
carte fine, jamais de 50 m en clair. Le mot de passe se devine hors ligne si on le prend court :
une longue phrase.

    python -m champi.chiffre        # après `python -m champi.zones`, avant la mise en ligne
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import FINE_ITERATIONS, FINE_SEL, SITE, SITE_DATA
from .sources import ecrire_json

HABITAT = SITE / "habitat"
COUCHES_FINES = ("a", "b", "d")        # la couche c reste en clair


def deriver(mot_de_passe: str, sel: str = FINE_SEL, iterations: int = FINE_ITERATIONS) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"), sel.encode("utf-8"), iterations, 32)


def identifiant(cle: bytes) -> str:
    return hashlib.sha256(cle).hexdigest()[:12]


def chiffrer(cle: bytes, nom: str, donnees: bytes) -> bytes:
    """Vecteur (12 octets) + chiffré + étiquette ; `nom` en données associées."""
    iv = hmac.new(cle, nom.encode("utf-8") + b"\0" + donnees, hashlib.sha256).digest()[:12]
    return iv + AESGCM(cle).encrypt(iv, donnees, nom.encode("utf-8"))


def dechiffrer(cle: bytes, nom: str, contenu: bytes) -> bytes:
    return AESGCM(cle).decrypt(contenu[:12], contenu[12:], nom.encode("utf-8"))


def fines(dossier: Path) -> list[Path]:
    return sorted(p for c in COUCHES_FINES for p in dossier.glob(f"*_{c}.png"))


def tout(mot_de_passe: str | None) -> dict | None:
    blocs = HABITAT / "blocs"
    a_chiffrer = fines(blocs)
    fine = None
    if mot_de_passe:
        cle = deriver(mot_de_passe)
        fine = {"id": identifiant(cle), "sel": FINE_SEL, "iterations": FINE_ITERATIONS}
        sortie = HABITAT / "fin" / fine["id"]
        if sortie.parent.exists():
            shutil.rmtree(sortie.parent)
        sortie.mkdir(parents=True)
        for p in a_chiffrer:
            (sortie / f"{p.stem}.bin").write_bytes(chiffrer(cle, p.name, p.read_bytes()))
    # Jamais de 50 m en clair en ligne, carte fine ou non.
    for p in a_chiffrer:
        p.unlink()
    for p in HABITAT.glob("echantillon*"):
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    chemin = SITE_DATA / "carte.json"
    carte = json.loads(chemin.read_text(encoding="utf-8"))
    carte["fine"] = fine
    ecrire_json(chemin, carte)
    print(f"Carte fine : {len(a_chiffrer)} couches " + (f"chiffrées (clé {fine['id']})" if fine
                                                          else "retirées, sans mot de passe (pas de carte fine)"))
    return fine


if __name__ == "__main__":
    tout(os.environ.get("CARTE_FINE_MOT_DE_PASSE") or None)
