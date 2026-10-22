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

MÉTÉO OBSERVÉE ET MÉTÉO PRÉVUE (décision n°31) :
- collecter_meteo_actuelle() : le temps qu'il fait au moment du relevé ;
- collecter_meteo_prevue()   : le temps annoncé pour les prochaines heures,
  quart d'heure par quart d'heure.
Pour prévoir les vélos dans 1h ou 3h, le modèle a besoin de la pluie ANNONCÉE
à ce moment-là, car la pluie qui tombera vraiment n'est pas encore connue quand
on fait la prévision. Une prévision qui n'est pas enregistrée sur le moment
est perdue pour toujours : on l'archive donc à chaque relevé.

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

# Nombre de quarts d'heure de prévision gardés à chaque relevé :
# 24 quarts d'heure = les 6 prochaines heures (le modèle prévoit à +1h et +3h)
NB_QUARTS_HEURE_PREVUS = 24

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


def collecter_meteo_prevue() -> list[dict]:
    """
    Récupérer la météo annoncée au centre de Lyon pour les prochaines heures.

    RÉSULTAT :
    Une liste avec une ligne par quart d'heure à venir (le premier est le quart
    d'heure en cours) : l'heure visée par la prévision et les 4 mesures annoncées.
    L'heure du relevé (« ingestion_timestamp ») est ajoutée par collect_bronze.py.
    """
    # « minutely_15 » : prévisions au pas de 15 minutes (modèles haute résolution
    # de Météo-France sur la France) ; « forecast_minutely_15 » : combien en garder,
    # en partant du quart d'heure en cours.
    parametres = {
        "latitude": LATITUDE_LYON,
        "longitude": LONGITUDE_LYON,
        "minutely_15": MESURES_DEMANDEES,
        "forecast_minutely_15": NB_QUARTS_HEURE_PREVUS,
        "timezone": "GMT",
    }
    with httpx.Client(timeout=DELAI_ATTENTE_MAX_SECONDES) as client:
        reponse = client.get(URL_API_METEO, params=parametres)
        reponse.raise_for_status()

    # L'API renvoie une colonne par mesure ; on la remet en une ligne par quart d'heure
    prevues = reponse.json()["minutely_15"]
    return [
        {
            "forecast_time_api": datetime.fromisoformat(heure).replace(tzinfo=timezone.utc),
            "forecast_temp_c": prevues["temperature_2m"][i],
            "forecast_precipitation_mm": prevues["precipitation"][i],
            "forecast_rain_mm": prevues["rain"][i],
            "forecast_wind_kmh": prevues["wind_speed_10m"][i],
        }
        for i, heure in enumerate(prevues["time"])
    ]


# Lancement direct pour vérification : uv run python -m src.ingestion.fetch_weather
if __name__ == "__main__":
    meteo = collecter_meteo_actuelle()
    print(f"Météo mesurée à {meteo['weather_time_api']:%H:%M} (UTC) place Bellecour :")
    print(f"  Température : {meteo['weather_temp_c']} °C")
    print(f"  Pluie       : {meteo['weather_rain_mm']} mm sur 15 min")
    print(f"  Vent        : {meteo['weather_wind_kmh']} km/h")
    prevues = collecter_meteo_prevue()
    print(f"Météo prévue ({len(prevues)} quarts d'heure) :")
    for p in prevues:
        print(f"  {p['forecast_time_api']:%H:%M} : {p['forecast_temp_c']} °C, "
              f"pluie {p['forecast_rain_mm']} mm, vent {p['forecast_wind_kmh']} km/h")
