"""
COLLECTE DE L'ALTITUDE DE CHAQUE STATION VÉLO'V (Couche Bronze)
================================================================

OBJECTIF MÉTIER :
Lyon est une ville de collines (Croix-Rousse, Fourvière, Sainte-Foy, La Duchère).
Les usagers descendent volontiers ces pentes à vélo, mais les remontent rarement :
les stations en hauteur se vident, celles en plaine saturent.
Pour mesurer cet « effet gravité », on a besoin de l'altitude (en mètres)
de chaque station.

SOURCE DES DONNÉES :
L'API d'altitude gratuite d'Open-Meteo (sans clé d'accès). Elle s'appuie sur le
relief numérique « Copernicus » de l'Agence spatiale européenne, précis à environ
90 mètres près au sol. On passe par la même API que pour la météo, ce qui évite
de dépendre d'un service supplémentaire.

FRÉQUENCE :
Contrairement à l'état des stations, l'altitude ne change jamais.
Ce script n'a donc pas besoin de tourner toutes les 15 minutes : il suffit de le
relancer quand de nouvelles stations apparaissent sur le réseau.
"""

import csv
from pathlib import Path

import httpx

from src.ingestion.fetch_velov import URL_FICHE_STATIONS, telecharger_json

URL_API_ALTITUDE = "https://api.open-meteo.com/v1/elevation"

# L'API accepte au maximum 100 positions GPS par appel.
# Avec environ 470 stations, on fera donc 5 appels successifs.
TAILLE_MAX_PAR_APPEL = 100

DELAI_ATTENTE_MAX_SECONDES = 30

# Fichier de référence où l'on range l'altitude de chaque station.
# Il est relu à chaque collecte de 15 minutes pour ajouter l'altitude aux relevés.
FICHIER_ALTITUDES = Path("data/reference/stations_altitude.csv")


def collecter_altitudes_stations() -> list[dict]:
    """
    Récupérer l'altitude en mètres de chaque station Vélo'v.

    RÉSULTAT :
    Une liste avec une ligne par station : son numéro, son nom, sa position GPS
    et son altitude en mètres au-dessus du niveau de la mer.
    """
    with httpx.Client(timeout=DELAI_ATTENTE_MAX_SECONDES) as client:
        # Étape 1 : On récupère la liste des stations et leur position GPS
        # (même fichier « fiche d'identité » que dans fetch_velov.py)
        fiches = telecharger_json(client, URL_FICHE_STATIONS)["data"]["stations"]

        resultats = []

        # Étape 2 : On découpe la liste en paquets de 100 stations maximum
        for debut in range(0, len(fiches), TAILLE_MAX_PAR_APPEL):
            paquet = fiches[debut : debut + TAILLE_MAX_PAR_APPEL]

            # Étape 3 : L'API attend toutes les latitudes séparées par des virgules,
            # puis toutes les longitudes dans le même ordre.
            parametres = {
                "latitude": ",".join(str(f["lat"]) for f in paquet),
                "longitude": ",".join(str(f["lon"]) for f in paquet),
            }
            reponse = client.get(URL_API_ALTITUDE, params=parametres)
            reponse.raise_for_status()
            altitudes = reponse.json()["elevation"]

            # Étape 4 : L'API renvoie les altitudes dans le même ordre que les
            # positions envoyées : on associe donc chaque altitude à sa station.
            for fiche, altitude in zip(paquet, altitudes, strict=True):
                resultats.append(
                    {
                        "station_id": fiche["station_id"],
                        "station_name": fiche.get("name"),
                        "lat": fiche["lat"],
                        "lon": fiche["lon"],
                        "altitude_m": altitude,
                    }
                )

    return resultats


def sauvegarder_altitudes(stations: list[dict]) -> None:
    """
    Enregistrer les altitudes dans le fichier de référence (format CSV,
    lisible dans Excel). Le fichier est entièrement réécrit à chaque lancement,
    puisque l'altitude d'une station ne change pas.
    """
    FICHIER_ALTITUDES.parent.mkdir(parents=True, exist_ok=True)
    with FICHIER_ALTITUDES.open("w", newline="", encoding="utf-8") as fichier:
        ecrivain = csv.DictWriter(fichier, fieldnames=list(stations[0].keys()))
        ecrivain.writeheader()
        ecrivain.writerows(stations)


# Lancement direct : uv run python -m src.ingestion.fetch_elevation
# Récupère les altitudes, les enregistre et affiche un résumé pour vérification.
if __name__ == "__main__":
    stations = collecter_altitudes_stations()
    sauvegarder_altitudes(stations)
    print(f"Fichier enregistré : {FICHIER_ALTITUDES}")
    stations_triees = sorted(stations, key=lambda s: s["altitude_m"])

    print(f"Altitude récupérée pour {len(stations)} stations")
    print("3 stations les plus basses :")
    for s in stations_triees[:3]:
        print(f"  {s['altitude_m']:>5.0f} m  {s['station_name']}")
    print("3 stations les plus hautes :")
    for s in stations_triees[-3:]:
        print(f"  {s['altitude_m']:>5.0f} m  {s['station_name']}")
