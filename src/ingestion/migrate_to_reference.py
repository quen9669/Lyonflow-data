"""
MIGRATION UNIQUE : SORTIR NOM / POSITION / ALTITUDE DES RELEVÉS
================================================================

OBJECTIF MÉTIER :
Appliquer à l'historique déjà collecté le nouveau rangement (référentiels
historisés, voir referentiel.py) :
  1. on rejoue tous les relevés, du plus ancien au plus récent, pour construire
     les référentiels (une version par changement réel, depuis le premier relevé) ;
  2. on réécrit chaque fichier quotidien sans les colonnes déplacées.
Aucune autre valeur n'est modifiée.

Le script peut être relancé sans risque : un fichier déjà allégé n'est pas retouché
et le référentiel est reconstruit à l'identique.

Lancement (une seule fois) : uv run python -m src.ingestion.migrate_to_reference
"""

import csv
from itertools import groupby
from pathlib import Path

from src.ingestion.collect_bronze import COLONNES_VELOV, DOSSIER_BRONZE_VELOV, REFERENTIELS, SOURCES_GRANDLYON
from src.ingestion.referentiel import appliquer_releve, ecrire_referentiel

# Pour chaque référentiel : le dossier des relevés et les colonnes à garder après migration
DOSSIERS_ET_COLONNES = {
    "velov": (DOSSIER_BRONZE_VELOV, COLONNES_VELOV),
    "parcs_relais": SOURCES_GRANDLYON["parcs_relais"],
    "parkings": SOURCES_GRANDLYON["parkings"],
}


def migrer_source(source: str) -> tuple[int, int]:
    """
    Construire le référentiel d'une source et alléger ses fichiers.
    Renvoie (nombre de versions dans le référentiel, nombre de fichiers allégés).
    """
    fichier_referentiel, cle, attributs = REFERENTIELS[source]
    dossier, colonnes_gardees = DOSSIERS_ET_COLONNES[source]
    referentiel: list[dict] = []
    nb_fichiers_alleges = 0

    for chemin in sorted(dossier.glob("*.csv")):
        with chemin.open(encoding="utf-8") as fichier:
            lecteur = csv.DictReader(fichier)
            colonnes_actuelles = lecteur.fieldnames or []
            lignes = list(lecteur)

        # Étape 1 : On rejoue les relevés du fichier, dans l'ordre, pour le référentiel
        if set(attributs) & set(colonnes_actuelles):
            for horodatage, releve in groupby(lignes, key=lambda ligne: ligne["ingestion_timestamp"]):
                appliquer_releve(referentiel, cle, attributs, list(releve), horodatage)

        # Étape 2 : On réécrit le fichier sans les colonnes déplacées (si ce n'est pas déjà fait)
        if colonnes_actuelles != colonnes_gardees:
            with chemin.open("w", newline="", encoding="utf-8") as fichier:
                ecrivain = csv.DictWriter(fichier, fieldnames=colonnes_gardees, extrasaction="ignore")
                ecrivain.writeheader()
                ecrivain.writerows(lignes)
            nb_fichiers_alleges += 1

    if referentiel:
        ecrire_referentiel(fichier_referentiel, cle, attributs, referentiel)
    return len(referentiel), nb_fichiers_alleges


if __name__ == "__main__":
    for source in DOSSIERS_ET_COLONNES:
        nb_versions, nb_fichiers = migrer_source(source)
        print(f"{source} : {nb_versions} lignes de référentiel, {nb_fichiers} fichier(s) allégé(s)")
