"""
CALENDRIER DES VACANCES SCOLAIRES DE LYON (Données de référence)
=================================================================

OBJECTIF MÉTIER :
Pendant les vacances scolaires, les déplacements changent complètement :
moins de trajets domicile-école et domicile-travail, plus de balades.
L'IA de prédiction doit donc savoir si un relevé tombe en période de vacances,
sinon elle confondrait « mardi normal » et « mardi de vacances ».

SOURCE DES DONNÉES :
Le calendrier scolaire officiel publié par le ministère de l'Éducation nationale
(data.education.gouv.fr, jeu de données « fr-en-calendrier-scolaire »),
gratuit et sans inscription. On garde l'académie de Lyon (zone A).

RYTHME :
Le calendrier change rarement : il est relu à chaque démarrage du robot de
collecte (environ toutes les 5h30) et le fichier n'est modifié que si le
ministère a publié du nouveau.

Lancement : uv run python -m src.ingestion.fetch_school_holidays
"""

import csv
from pathlib import Path

import httpx

URL_CALENDRIER = (
    "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/"
    "fr-en-calendrier-scolaire/exports/json"
)

FICHIER_VACANCES = Path("data/reference/school_holidays.csv")

# Colonnes du fichier de référence. Les dates sont celles du ministère, en heure UTC :
# les vacances couvrent la période [start_date ; end_date[ (fin exclue).
# Exemple : Toussaint 2026 → du 17/10 à 0h (heure de Lyon) au 02/11 à 0h.
COLONNES_VACANCES = ["annee_scolaire", "description", "start_date", "end_date"]


def selectionner_vacances_lyon(enregistrements: list[dict]) -> list[dict]:
    """
    Garder une ligne par période de vacances pour l'académie de Lyon.
    Le ministère publie parfois une ligne « élèves » et une ligne « enseignants »
    pour la même période : seules comptent les dates des élèves.
    """
    vacances = {}
    for enregistrement in enregistrements:
        if enregistrement.get("location") != "Lyon":
            continue
        if enregistrement.get("population") not in ("-", "Élèves", None):
            continue
        if not enregistrement.get("start_date") or not enregistrement.get("end_date"):
            continue
        ligne = {colonne: enregistrement.get(colonne) for colonne in COLONNES_VACANCES}
        # Une seule ligne par période (même début et même description)
        vacances[(ligne["start_date"], ligne["description"])] = ligne
    # Tri par date de début : le fichier reste identique tant que rien ne change
    return sorted(vacances.values(), key=lambda ligne: ligne["start_date"])


def mettre_a_jour_calendrier() -> int:
    """
    Télécharger le calendrier et réécrire le fichier de référence.
    Renvoie le nombre de périodes de vacances enregistrées.
    """
    # Étape 1 : Téléchargement (on filtre déjà sur Lyon côté serveur pour limiter le volume)
    reponse = httpx.get(URL_CALENDRIER, params={"where": 'location="Lyon"'}, timeout=60)
    reponse.raise_for_status()
    vacances = selectionner_vacances_lyon(reponse.json())

    # Étape 2 : Sécurité : on n'écrase jamais un calendrier existant par un fichier vide
    if not vacances:
        raise RuntimeError("Le ministère n'a renvoyé aucune période de vacances pour Lyon.")

    FICHIER_VACANCES.parent.mkdir(parents=True, exist_ok=True)
    with FICHIER_VACANCES.open("w", newline="", encoding="utf-8") as fichier:
        ecrivain = csv.DictWriter(fichier, fieldnames=COLONNES_VACANCES)
        ecrivain.writeheader()
        ecrivain.writerows(vacances)
    return len(vacances)


if __name__ == "__main__":
    print(f"Vacances scolaires de Lyon : {mettre_a_jour_calendrier()} périodes enregistrées.")
