"""
COLLECTE COMPLÈTE D'UN RELEVÉ ET SAUVEGARDE EN COUCHE BRONZE
=============================================================

OBJECTIF MÉTIER :
C'est le script lancé pile à chaque quart d'heure (voir collect_loop.py).
À chaque passage, il :
  1. photographie l'état de toutes les stations Vélo'v (fetch_velov.py),
  2. ajoute à chaque station son altitude (fichier de référence de fetch_elevation.py),
  3. relève la météo du moment (fetch_weather.py),
  4. ajoute les lignes Vélo'v au fichier du jour, et UNE ligne météo au fichier
     météo du jour.

TROIS TABLES RELIÉES PAR UNE CLÉ (choix validés au Sprint 2) :
Certaines informations sont les mêmes pour toutes les stations d'un relevé
(la météo, la date de génération du flux Vélo'v). Plutôt que de les répéter
466 fois, on les enregistre une seule fois par quart d'heure dans leur propre
table. Toutes les tables partagent la colonne « ingestion_timestamp »
(l'heure exacte du relevé) : c'est la clé qui permet de les relier.
  - data/bronze/velov/AAAA-MM-JJ.csv   → 466 lignes par relevé (une par station)
  - data/bronze/weather/AAAA-MM-JJ.csv → 1 ligne par relevé (météo)
  - data/bronze/feed/AAAA-MM-JJ.csv    → 1 ligne par relevé (infos sur le flux Vélo'v)
  - data/bronze/park_and_ride/AAAA-MM-JJ.csv → 1 ligne par parc relais TCL et par relevé
  - data/bronze/parking/AAAA-MM-JJ.csv       → 1 ligne par parking et par relevé
  - data/bronze/traffic/AAAA-MM-JJ.csv       → 1 ligne par état du trafic et par relevé
  (ces trois dernières uniquement si un compte data.grandlyon.com est configuré,
   voir fetch_grandlyon.py)

ORGANISATION DES FICHIERS :
Chaque passage AJOUTE ses lignes à la fin des fichiers du jour, sans jamais
modifier les lignes déjà écrites. Git n'enregistre donc que les nouvelles
lignes, et le dépôt grossit lentement.
DuckDB lit ensuite tous ces fichiers comme des tables (voir build_database.py).

LE JOUR EST CELUI DU TEMPS UNIVERSEL (UTC) :
Toutes les heures du projet sont en UTC pour éviter les pièges du passage
à l'heure d'été / d'hiver.
"""

import csv
from pathlib import Path

import httpx

from src.ingestion.fetch_elevation import FICHIER_ALTITUDES
from src.ingestion.fetch_grandlyon import collecter_mobilite_grandlyon
from src.ingestion.fetch_velov import collecter_etat_stations
from src.ingestion.fetch_weather import collecter_meteo_actuelle

# Dossiers où sont rangés les fichiers CSV quotidiens de la couche Bronze
DOSSIER_BRONZE_VELOV = Path("data/bronze/velov")
DOSSIER_BRONZE_METEO = Path("data/bronze/weather")
DOSSIER_BRONZE_FLUX = Path("data/bronze/feed")

# Données de mobilité du Grand Lyon : pour chaque source, son dossier et ses colonnes
SOURCES_GRANDLYON = {
    "parcs_relais": (
        Path("data/bronze/park_and_ride"),
        ["ingestion_timestamp", "parc_id", "parc_name", "lat", "lon", "capacity",
         "available_places_raw", "last_update_api"],
    ),
    "parkings": (
        Path("data/bronze/parking"),
        ["ingestion_timestamp", "parking_id", "parking_name", "lat", "lon", "capacity",
         "available_places_raw", "status_raw", "last_update_api"],
    ),
    "trafic": (
        Path("data/bronze/traffic"),
        ["ingestion_timestamp", "traffic_status_raw", "nb_segments", "total_length_m"],
    ),
}

# Ordre fixe des colonnes dans les fichiers CSV.
# Le fixer explicitement garantit que tous les fichiers ont la même structure,
# même si l'ordre des informations renvoyées par les API change un jour.
COLONNES_VELOV = [
    # Quand (clé commune avec la météo) et quelle station
    "ingestion_timestamp",
    "station_id",
    "station_name",
    "lat",
    "lon",
    "altitude_m",
    "total_stands",
    # État brut envoyé par la station
    "available_bikes_raw",
    "available_stands_raw",
    "disabled_bikes_raw",
    "disabled_stands_raw",
    "is_installed_raw",
    "is_renting_raw",
    "is_returning_raw",
    "last_update_api",
]

COLONNES_FLUX = [
    "ingestion_timestamp",
    # Date à laquelle la Métropole a généré le fichier d'état (sert à DQ_02)
    "feed_last_updated_api",
    # Nombre de stations reçues dans ce relevé (repère simple en cas de flux tronqué)
    "nb_stations",
]

COLONNES_METEO = [
    "ingestion_timestamp",
    "weather_time_api",
    "weather_temp_c",
    "weather_precipitation_mm",
    "weather_rain_mm",
    "weather_wind_kmh",
]


def lire_altitudes() -> dict:
    """
    Lire le fichier de référence des altitudes et le ranger dans un « annuaire »
    indexé par numéro de station.
    Si le fichier n'existe pas encore, on renvoie un annuaire vide : la collecte
    continue quand même, et la colonne altitude restera vide (principe Bronze :
    mieux vaut une donnée incomplète qu'une donnée perdue).
    """
    if not FICHIER_ALTITUDES.exists():
        print(f"⚠️  Fichier d'altitudes absent ({FICHIER_ALTITUDES}) : altitude laissée vide.")
        return {}
    with FICHIER_ALTITUDES.open(encoding="utf-8") as fichier:
        return {ligne["station_id"]: ligne["altitude_m"] for ligne in csv.DictReader(fichier)}


def lire_meteo_sans_bloquer() -> dict | None:
    """
    Récupérer la météo du moment.
    Si l'API météo est en panne, on ne veut PAS perdre le relevé Vélo'v pour autant :
    on affiche un avertissement et on renvoie « None ». Aucune ligne météo ne sera
    écrite pour ce quart d'heure (ce trou sera repéré au Sprint 2).
    """
    try:
        return collecter_meteo_actuelle()
    except httpx.HTTPError as erreur:
        print(f"⚠️  Météo indisponible pour ce relevé : {erreur}")
        return None


def ajouter_au_fichier_du_jour(dossier: Path, jour: str, colonnes: list[str], lignes: list[dict]) -> Path:
    """
    Ajouter des lignes à la fin du fichier CSV du jour (mode « a » = append).
    La ligne d'en-tête (noms des colonnes) n'est écrite qu'à la création du fichier.
    """
    dossier.mkdir(parents=True, exist_ok=True)
    fichier_du_jour = dossier / f"{jour}.csv"
    fichier_est_nouveau = not fichier_du_jour.exists()
    with fichier_du_jour.open("a", newline="", encoding="utf-8") as fichier:
        ecrivain = csv.DictWriter(fichier, fieldnames=colonnes, extrasaction="ignore")
        if fichier_est_nouveau:
            ecrivain.writeheader()
        ecrivain.writerows(lignes)
    return fichier_du_jour


def collecter_et_sauvegarder() -> Path:
    """
    Réaliser un relevé complet et l'ajouter aux fichiers CSV du jour.
    Renvoie le chemin du fichier Vélo'v mis à jour.
    """
    # Étape 1 : Les trois sources de données.
    # Vélo'v est indispensable : si son API est en panne, le script s'arrête en erreur
    # (le passage apparaîtra en rouge dans GitHub Actions, ce qui nous alertera).
    stations = collecter_etat_stations()
    meteo = lire_meteo_sans_bloquer()
    altitudes = lire_altitudes()

    # Étape 2 : On complète chaque ligne station avec son altitude
    for station in stations:
        station["altitude_m"] = altitudes.get(station["station_id"])

    # Étape 3 : L'heure du relevé Vélo'v sert de clé commune aux deux tables
    heure_releve = stations[0]["ingestion_timestamp"]
    jour = heure_releve.date().isoformat()

    # Étape 4 : On enregistre les stations, la ligne « flux », puis la météo (si disponible)
    fichier_velov = ajouter_au_fichier_du_jour(DOSSIER_BRONZE_VELOV, jour, COLONNES_VELOV, stations)
    print(f"✅ {len(stations)} stations ajoutées à {fichier_velov}")

    ligne_flux = {
        "ingestion_timestamp": heure_releve,
        "feed_last_updated_api": stations[0]["feed_last_updated_api"],
        "nb_stations": len(stations),
    }
    ajouter_au_fichier_du_jour(DOSSIER_BRONZE_FLUX, jour, COLONNES_FLUX, [ligne_flux])

    if meteo is not None:
        meteo["ingestion_timestamp"] = heure_releve
        fichier_meteo = ajouter_au_fichier_du_jour(DOSSIER_BRONZE_METEO, jour, COLONNES_METEO, [meteo])
        print(f"✅ Météo ajoutée à {fichier_meteo}")

    # Étape 5 : Les données de mobilité du Grand Lyon (si un compte est configuré)
    mobilite = collecter_mobilite_grandlyon()
    for source, lignes in (mobilite or {}).items():
        dossier, colonnes = SOURCES_GRANDLYON[source]
        for ligne in lignes:
            ligne["ingestion_timestamp"] = heure_releve
        if lignes:
            fichier = ajouter_au_fichier_du_jour(dossier, jour, colonnes, lignes)
            print(f"✅ {len(lignes)} lignes « {source} » ajoutées à {fichier}")

    return fichier_velov


# Lancement : uv run python -m src.ingestion.collect_bronze
if __name__ == "__main__":
    collecter_et_sauvegarder()
