"""
COLLECTE COMPLÈTE D'UN RELEVÉ ET SAUVEGARDE EN COUCHE BRONZE
=============================================================

OBJECTIF MÉTIER :
C'est le script lancé pile à chaque quart d'heure (voir collect_loop.py).
À chaque passage, il :
  1. photographie l'état de toutes les stations Vélo'v (fetch_velov.py),
  2. ajoute à chaque station son altitude (fichier de référence de fetch_elevation.py),
  3. relève la météo du moment et la météo prévue pour les 6 prochaines heures
     (fetch_weather.py),
  4. ajoute les lignes Vélo'v au fichier du jour, UNE ligne météo au fichier
     météo du jour et 24 lignes (une par quart d'heure à venir) au fichier des
     prévisions du jour.

TROIS TABLES RELIÉES PAR UNE CLÉ (choix validés au Sprint 2) :
Certaines informations sont les mêmes pour toutes les stations d'un relevé
(la météo, la date de génération du flux Vélo'v). Plutôt que de les répéter
466 fois, on les enregistre une seule fois par quart d'heure dans leur propre
table. Toutes les tables partagent la colonne « ingestion_timestamp »
(l'heure exacte du relevé) : c'est la clé qui permet de les relier.
  - data/bronze/velov/AAAA-MM-JJ.csv   → 466 lignes par relevé (une par station)
  - data/bronze/weather/AAAA-MM-JJ.csv → 1 ligne par relevé (météo)
  - data/bronze/weather_forecast/AAAA-MM-JJ.csv → 24 lignes par relevé (météo prévue
                                       pour chaque quart d'heure des 6 prochaines heures)
  - data/bronze/feed/AAAA-MM-JJ.csv    → 1 ligne par relevé (infos sur le flux Vélo'v)
  - data/bronze/park_and_ride/AAAA-MM-JJ.csv → 1 ligne par parc relais TCL et par relevé
  - data/bronze/parking/AAAA-MM-JJ.csv       → 1 ligne par parking et par relevé
  - data/bronze/traffic/AAAA-MM-JJ.csv       → 1 ligne par état du trafic et par relevé
  - data/bronze/tcl_feed/AAAA-MM-JJ.csv      → 1 ligne par relevé (résumé des alertes TCL ;
                                               le détail est dans data/reference/tcl_alertes.csv)
  (ces quatre dernières uniquement si un compte data.grandlyon.com est configuré,
   voir fetch_grandlyon.py)

RÉFÉRENTIELS (choix validé) :
Le nom, la position GPS et l'altitude des stations (et le nom et la position
des parkings et P+R) ne sont pas répétés dans chaque relevé : ils sont rangés
une seule fois, avec leur période de validité, dans data/reference/
(velov_stations.csv, parkings.csv, parcs_relais.csv). Voir referentiel.py.

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
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.ingestion.fetch_elevation import FICHIER_ALTITUDES
from src.ingestion.fetch_grandlyon import collecter_mobilite_grandlyon
from src.ingestion.fetch_tcl import COLONNES_RESUME as COLONNES_TCL
from src.ingestion.fetch_tcl import DOSSIER_RESUME as DOSSIER_BRONZE_TCL
from src.ingestion.fetch_tcl import collecter_alertes_tcl
from src.ingestion.referentiel import mettre_a_jour_fichier
from src.ingestion.fetch_velov import collecter_etat_stations
from src.ingestion.fetch_weather import collecter_meteo_actuelle, collecter_meteo_prevue

# Dossiers où sont rangés les fichiers CSV quotidiens de la couche Bronze
DOSSIER_BRONZE_VELOV = Path("data/bronze/velov")
DOSSIER_BRONZE_METEO = Path("data/bronze/weather")
DOSSIER_BRONZE_METEO_PREVUE = Path("data/bronze/weather_forecast")
DOSSIER_BRONZE_FLUX = Path("data/bronze/feed")

# Données de mobilité du Grand Lyon : pour chaque source, son dossier et ses colonnes
SOURCES_GRANDLYON = {
    "parcs_relais": (
        Path("data/bronze/park_and_ride"),
        ["ingestion_timestamp", "parc_id", "capacity", "available_places_raw", "last_update_api"],
    ),
    "parkings": (
        Path("data/bronze/parking"),
        ["ingestion_timestamp", "parking_id", "capacity", "available_places_raw", "status_raw",
         "last_update_api"],
    ),
    "trafic": (
        Path("data/bronze/traffic"),
        ["ingestion_timestamp", "traffic_status_raw", "nb_segments", "total_length_m"],
    ),
}

# Référentiels historisés : pour chaque source, (fichier, identifiant, informations suivies)
REFERENTIELS = {
    "velov": (Path("data/reference/velov_stations.csv"), "station_id",
              ["station_name", "lat", "lon", "altitude_m"]),
    "parcs_relais": (Path("data/reference/parcs_relais.csv"), "parc_id", ["parc_name", "lat", "lon"]),
    "parkings": (Path("data/reference/parkings.csv"), "parking_id", ["parking_name", "lat", "lon"]),
}


def mettre_a_jour_referentiel(source: str, elements: list[dict], heure_releve) -> None:
    """Enregistrer dans le référentiel les éléments nouveaux ou modifiés de ce relevé."""
    fichier, cle, attributs = REFERENTIELS[source]
    nb_changements = mettre_a_jour_fichier(fichier, cle, attributs, elements, str(heure_releve))
    if nb_changements:
        print(f"📒 Référentiel {fichier.name} : {nb_changements} ligne(s) ajoutée(s) ou mise(s) à jour")

# Ordre fixe des colonnes dans les fichiers CSV.
# Le fixer explicitement garantit que tous les fichiers ont la même structure,
# même si l'ordre des informations renvoyées par les API change un jour.
COLONNES_VELOV = [
    # Quand (clé commune avec la météo) et quelle station
    "ingestion_timestamp",
    "station_id",
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

COLONNES_METEO_PREVUE = [
    # Quand la prévision a été relevée (clé commune) et pour quel quart d'heure elle vaut
    "ingestion_timestamp",
    "forecast_time_api",
    "forecast_temp_c",
    "forecast_precipitation_mm",
    "forecast_rain_mm",
    "forecast_wind_kmh",
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


# Vélo'v : si le serveur du Grand Lyon ne répond pas, on réessaie dans le même
# quart d'heure (choix validé le 28/10/2026, après 11h de panne la nuit du 27 au 28/10).
# Pauses en secondes : 2e essai 2 min après le 1er, 3e essai 3 min après le 2e.
# Le dernier essai se termine donc vers +7 min, bien avant le quart d'heure suivant.
PAUSES_ENTRE_ESSAIS_VELOV = [120, 180]


def collecter_velov_avec_essais() -> list[dict]:
    """
    Récupérer l'état des stations Vélo'v, en réessayant si le serveur ne répond pas.
    Une petite coupure de quelques minutes ne fait ainsi plus perdre le relevé.
    Si tous les essais échouent, l'erreur du dernier essai est renvoyée.
    """
    nb_essais = len(PAUSES_ENTRE_ESSAIS_VELOV) + 1
    for numero_essai in range(1, nb_essais + 1):
        try:
            return collecter_etat_stations()
        except (httpx.HTTPError, ValueError) as erreur:
            print(f"⚠️  Vélo'v ne répond pas (essai {numero_essai}/{nb_essais}) : {erreur}")
            if numero_essai == nb_essais:
                raise
            pause = PAUSES_ENTRE_ESSAIS_VELOV[numero_essai - 1]
            print(f"   Nouvel essai dans {pause // 60} min.")
            time.sleep(pause)


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


def enregistrer_meteo(heure_releve, jour: str) -> None:
    """
    Relever et enregistrer la météo du moment et la météo prévue.
    Une panne de l'une ou l'autre ne bloque rien : on note simplement un avertissement.
    """
    meteo = lire_meteo_sans_bloquer()
    if meteo is not None:
        meteo["ingestion_timestamp"] = heure_releve
        fichier_meteo = ajouter_au_fichier_du_jour(DOSSIER_BRONZE_METEO, jour, COLONNES_METEO, [meteo])
        print(f"✅ Météo ajoutée à {fichier_meteo}")

    try:
        prevues = collecter_meteo_prevue()
    except (httpx.HTTPError, KeyError, ValueError) as erreur:
        prevues = []
        print(f"⚠️  Météo prévue indisponible pour ce relevé : {erreur}")
    for ligne in prevues:
        ligne["ingestion_timestamp"] = heure_releve
    if prevues:
        fichier = ajouter_au_fichier_du_jour(DOSSIER_BRONZE_METEO_PREVUE, jour, COLONNES_METEO_PREVUE, prevues)
        print(f"✅ {len(prevues)} quarts d'heure de météo prévue ajoutés à {fichier}")


def collecter_et_sauvegarder() -> Path:
    """
    Réaliser un relevé complet et l'ajouter aux fichiers CSV du jour.
    Renvoie le chemin du fichier Vélo'v mis à jour.
    """
    # Étape 1 : Vélo'v, avec plusieurs essais dans le quart d'heure.
    # Vélo'v est indispensable : si son API reste en panne, le script s'arrête en erreur
    # (le passage apparaîtra en rouge dans GitHub Actions, ce qui nous alertera).
    # Mais la météo vient d'un autre serveur : on l'enregistre quand même avant de
    # s'arrêter, pour ne pas la perdre aussi (choix validé le 28/10/2026).
    try:
        stations = collecter_velov_avec_essais()
    except Exception:
        heure_releve = datetime.now(tz=timezone.utc)
        print("❌ Vélo'v injoignable : on enregistre quand même la météo de ce quart d'heure.")
        enregistrer_meteo(heure_releve, heure_releve.date().isoformat())
        raise
    altitudes = lire_altitudes()

    # Étape 2 : On complète chaque ligne station avec son altitude
    for station in stations:
        station["altitude_m"] = altitudes.get(station["station_id"])

    # Étape 3 : L'heure du relevé Vélo'v sert de clé commune aux deux tables
    heure_releve = stations[0]["ingestion_timestamp"]
    jour = heure_releve.date().isoformat()

    # Étape 4 : On met à jour le référentiel des stations (nom, position, altitude),
    # puis on enregistre les relevés, la ligne « flux » et la météo (si disponible)
    mettre_a_jour_referentiel("velov", stations, heure_releve)
    fichier_velov = ajouter_au_fichier_du_jour(DOSSIER_BRONZE_VELOV, jour, COLONNES_VELOV, stations)
    print(f"✅ {len(stations)} stations ajoutées à {fichier_velov}")

    ligne_flux = {
        "ingestion_timestamp": heure_releve,
        "feed_last_updated_api": stations[0]["feed_last_updated_api"],
        "nb_stations": len(stations),
    }
    ajouter_au_fichier_du_jour(DOSSIER_BRONZE_FLUX, jour, COLONNES_FLUX, [ligne_flux])

    enregistrer_meteo(heure_releve, jour)

    # Étape 5 : Les données de mobilité du Grand Lyon (si un compte est configuré)
    mobilite = collecter_mobilite_grandlyon()
    for source, lignes in (mobilite or {}).items():
        dossier, colonnes = SOURCES_GRANDLYON[source]
        for ligne in lignes:
            ligne["ingestion_timestamp"] = heure_releve
        if source in REFERENTIELS:
            mettre_a_jour_referentiel(source, lignes, heure_releve)
        if lignes:
            fichier = ajouter_au_fichier_du_jour(dossier, jour, colonnes, lignes)
            print(f"✅ {len(lignes)} lignes « {source} » ajoutées à {fichier}")

    # Étape 6 : Le journal des alertes TCL (une panne de ce flux ne bloque pas le relevé)
    try:
        resume_tcl = collecter_alertes_tcl(heure_releve)
    except Exception as erreur:
        resume_tcl = None
        print(f"⚠️ Alertes TCL indisponibles : {erreur}")
    if resume_tcl is not None:
        ajouter_au_fichier_du_jour(DOSSIER_BRONZE_TCL, jour, COLONNES_TCL, [resume_tcl])
        print(f"✅ Alertes TCL : {resume_tcl['nb_alertes']} en cours")

    return fichier_velov


# Lancement : uv run python -m src.ingestion.collect_bronze
if __name__ == "__main__":
    collecter_et_sauvegarder()
