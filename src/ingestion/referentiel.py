"""
RÉFÉRENTIELS HISTORISÉS (stations Vélo'v, parkings, parcs relais)
==================================================================

OBJECTIF MÉTIER :
Le nom, la position GPS et l'altitude d'une station ne changent presque jamais.
Les répéter dans chaque relevé (467 stations × 96 relevés par jour) gonflait
inutilement les fichiers. On les range donc une seule fois dans un
« référentiel », et les relevés ne gardent que l'identifiant.

HISTORISATION (choix validé) :
Chaque ligne du référentiel a une période de validité :
  - valid_from : date et heure (UTC) du relevé où cette version est apparue,
  - valid_to   : 2099-12-31 tant que rien n'a changé (version « en cours »).
Si un nom ou une position change un jour, on ne réécrit pas le passé :
la version en cours est fermée (valid_to = heure du relevé) et une nouvelle
version est ouverte. On peut ainsi toujours retrouver le nom ou la position
valable au moment de n'importe quel relevé.

DEUX PRÉCAUTIONS :
  - Les coordonnées GPS sont comparées au millionième de degré (environ 10 cm) :
    un simple arrondi différent dans le flux ne crée pas de fausse version.
  - Une information qui était inconnue et devient connue (ex. altitude pas encore
    calculée) complète la version en cours au lieu d'en créer une nouvelle.
"""

import csv
from pathlib import Path

# Date de fin d'une version encore valable aujourd'hui
FIN_OUVERTE = "2099-12-31 00:00:00+00:00"

# Colonnes arrondies au millionième de degré avant comparaison
COLONNES_GPS = {"lat", "lon"}


def normaliser(colonne: str, valeur) -> str:
    """Écrire une valeur sous une forme stable (texte), pour pouvoir la comparer."""
    if valeur is None or valeur == "":
        return ""
    if colonne in COLONNES_GPS:
        return f"{float(valeur):.6f}"
    return str(valeur)


def appliquer_releve(
    referentiel: list[dict], cle: str, attributs: list[str], elements: list[dict], horodatage: str
) -> int:
    """
    Mettre à jour (sur place) un référentiel avec les éléments d'un relevé.
    Renvoie le nombre de lignes ajoutées ou modifiées.

    referentiel : lignes existantes (clé, attributs, valid_from, valid_to)
    cle         : nom de la colonne identifiant (ex. « station_id »)
    attributs   : colonnes suivies (ex. nom, lat, lon, altitude)
    elements    : éléments du relevé (dictionnaires contenant la clé et les attributs)
    horodatage  : heure du relevé (texte UTC), qui sert de date de début ou de fin
    """
    en_cours = {ligne[cle]: ligne for ligne in referentiel if ligne["valid_to"] == FIN_OUVERTE}
    nb_changements = 0

    for element in elements:
        identifiant = normaliser(cle, element.get(cle))
        if not identifiant:
            continue
        nouvelle = {colonne: normaliser(colonne, element.get(colonne)) for colonne in attributs}
        actuelle = en_cours.get(identifiant)

        # Cas 1 : élément jamais vu → première version
        if actuelle is None:
            ligne = {cle: identifiant, **nouvelle, "valid_from": horodatage, "valid_to": FIN_OUVERTE}
            referentiel.append(ligne)
            en_cours[identifiant] = ligne
            nb_changements += 1
            continue

        # Cas 2 : on compare attribut par attribut
        vrai_changement = False
        completee = False
        for colonne in attributs:
            ancienne_valeur, nouvelle_valeur = actuelle[colonne], nouvelle[colonne]
            if ancienne_valeur == nouvelle_valeur or nouvelle_valeur == "":
                continue  # identique, ou information manquante dans ce relevé : on garde l'ancienne
            if ancienne_valeur == "":
                actuelle[colonne] = nouvelle_valeur  # information enfin connue : on complète
                completee = True
            else:
                vrai_changement = True

        # Cas 3 : vrai changement → on ferme la version en cours et on en ouvre une nouvelle
        if vrai_changement:
            actuelle["valid_to"] = horodatage
            fusion = {colonne: nouvelle[colonne] or actuelle[colonne] for colonne in attributs}
            ligne = {cle: identifiant, **fusion, "valid_from": horodatage, "valid_to": FIN_OUVERTE}
            referentiel.append(ligne)
            en_cours[identifiant] = ligne
            nb_changements += 1
        elif completee:
            nb_changements += 1

    return nb_changements


def lire_referentiel(fichier: Path) -> list[dict]:
    """Lire un fichier référentiel (liste vide s'il n'existe pas encore)."""
    if not fichier.exists():
        return []
    with fichier.open(encoding="utf-8") as flux:
        return list(csv.DictReader(flux))


def ecrire_referentiel(fichier: Path, cle: str, attributs: list[str], referentiel: list[dict]) -> None:
    """Écrire le référentiel, trié par identifiant puis par date de début de version."""
    fichier.parent.mkdir(parents=True, exist_ok=True)
    lignes = sorted(referentiel, key=lambda ligne: (ligne[cle], ligne["valid_from"]))
    with fichier.open("w", newline="", encoding="utf-8") as flux:
        ecrivain = csv.DictWriter(flux, fieldnames=[cle, *attributs, "valid_from", "valid_to"])
        ecrivain.writeheader()
        ecrivain.writerows(lignes)


def mettre_a_jour_fichier(
    fichier: Path, cle: str, attributs: list[str], elements: list[dict], horodatage: str
) -> int:
    """Mettre à jour un fichier référentiel avec un relevé (réécrit seulement s'il y a du nouveau)."""
    referentiel = lire_referentiel(fichier)
    nb_changements = appliquer_releve(referentiel, cle, attributs, elements, horodatage)
    if nb_changements:
        ecrire_referentiel(fichier, cle, attributs, referentiel)
    return nb_changements
