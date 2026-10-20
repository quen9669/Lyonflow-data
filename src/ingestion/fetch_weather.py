"""
COLLECTE DE LA MÉTÉO LYONNAISE EN DIRECT (Couche Bronze)
=========================================================

OBJECTIF MÉTIER :
La météo change fortement l'usage du vélo : sous la pluie ou par grand vent,
les locations chutent ; par beau temps, elles explosent. Pour que l'IA puisse
anticiper ces variations, chaque relevé Vélo'v est accompagné de la météo
observée au même moment.

SOURCE DES DONNÉES :
L'API gratuite Open-Meteo (sans inscription ni clé d'accès), qui s'appuie
notamment sur les modèles de Météo-France. Elle actualise ses valeurs
« en direct » toutes les 15 minutes, ce qui correspond à notre rythme de collecte.

CHOIX D'UN POINT UNIQUE :
On interroge la météo en un seul point, la place Bellecour (centre de Lyon).
Le territoire Vélo'v est assez compact pour que la pluie ou la température
y soient quasiment identiques partout au même instant. Ce choix limite le
nombre d'appels et pourra être affiné plus tard si une analyse montre le contraire.
"""

from datetime import datetime, timezone

import httpx

URL_API_METEO = "https://api.open-meteo.com/v1/forecast"

# Coordonnées GPS de la place Bellecour, au centre de Lyon
LATITUDE_LYON = 45.7578
LONGITUDE_LYON = 4.8320

# Les mesures demandées à l'API (noms imposés par Open-Meteo) :
# - temperature_2m : température de l'air à 2 mètres du sol (°C)
# - precipitation  : quantité totale d'eau tombée (pluie + neige) sur les 15 dernières minutes (mm)
# - rain           : quantité de pluie seule sur les 15 dernières minutes (mm)
# - wind_speed_10m : vitesse du vent à 10 mètres du sol (km/h)
MESURES_DEMANDEES = "temperature_2m,precipitation,rain,wind_speed_10m"

# Délai d'attente maximum (en secondes) avant d'abandonner un appel bloqué
DELAI_ATTENTE_MAX_SECONDES = 30


def collecter_meteo_actuelle() -> dict:
    """
    Récupérer la météo observée en ce moment au centre de Lyon.

    RÉSULTAT :
    Un dictionnaire contenant l'heure de notre collecte, l'heure de la mesure
    météo (arrondie au quart d'heure par l'API) et les 4 mesures demandées.
    """
    # Étape 1 : On note l'heure de collecte
    heure_collecte = datetime.now(tz=timezone.utc)

    # Étape 2 : On interroge l'API en précisant le lieu et les mesures voulues.
    # « timezone=GMT » : toutes les heures sont renvoyées en temps universel (UTC),
    # comme pour les données Vélo'v, afin de pouvoir les comparer sans décalage.
    parametres = {
        "latitude": LATITUDE_LYON,
        "longitude": LONGITUDE_LYON,
        "current": MESURES_DEMANDEES,
        "timezone": "GMT",
    }
    with httpx.Client(timeout=DELAI_ATTENTE_MAX_SECONDES) as client:
        reponse = client.get(URL_API_METEO, params=parametres)
        # Arrêt immédiat avec un message clair si l'API répond par une erreur
        reponse.raise_for_status()

    # Étape 3 : On extrait la partie « current » (valeurs en direct) de la réponse
    actuel = reponse.json()["current"]

    # Étape 4 : On renvoie les valeurs brutes, sans aucune correction (principe Bronze)
    return {
        "ingestion_timestamp": heure_collecte,
        # L'API donne l'heure sous la forme « 2026-10-19T20:00 » : on la convertit
        # en vraie date et on précise qu'il s'agit du temps universel (UTC).
        "weather_time_api": datetime.fromisoformat(actuel["time"]).replace(tzinfo=timezone.utc),
        "weather_temp_c": actuel.get("temperature_2m"),
        "weather_precipitation_mm": actuel.get("precipitation"),
        "weather_rain_mm": actuel.get("rain"),
        "weather_wind_kmh": actuel.get("wind_speed_10m"),
    }


# Lancement direct pour vérification : uv run python -m src.ingestion.fetch_weather
if __name__ == "__main__":
    meteo = collecter_meteo_actuelle()
    print(f"Météo mesurée à {meteo['weather_time_api']:%H:%M} (UTC) place Bellecour :")
    print(f"  Température : {meteo['weather_temp_c']} °C")
    print(f"  Pluie       : {meteo['weather_rain_mm']} mm sur 15 min")
    print(f"  Vent        : {meteo['weather_wind_kmh']} km/h")
