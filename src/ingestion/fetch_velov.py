"""
COLLECTE DE L'ÉTAT DES STATIONS VÉLO'V (Couche Bronze)
=======================================================

OBJECTIF MÉTIER :
Photographier, à un instant donné, l'état de toutes les stations Vélo'v de la
Métropole de Lyon : combien de vélos sont disponibles, combien de places sont
libres, combien de bornes ou de vélos sont déclarés hors service.
Ce script sera lancé automatiquement toutes les 15 minutes (étape 1.3).

SOURCE DES DONNÉES :
Le flux officiel GBFS (« General Bikeshare Feed Specification ») publié par la
Métropole de Lyon. C'est le standard international utilisé par la plupart des
réseaux de vélos en libre-service dans le monde. Il se compose de deux fichiers :
  1. « station_status »      : l'état EN DIRECT de chaque station (change souvent).
  2. « station_information » : la FICHE d'identité de chaque station
                                (nom, adresse, position GPS, capacité). Change rarement.
On télécharge les deux et on les croise grâce au numéro de station (station_id).

POURQUOI CE CHOIX (et pas l'API « Data Grand Lyon ») :
Seul le flux GBFS indique le nombre de bornes et de vélos hors service,
une information indispensable à la règle de qualité DQ_04 (cohérence de la capacité).

PRINCIPE « BRONZE » :
On enregistre les valeurs TELLES QUE l'API les envoie, sans rien corriger,
même si elles semblent fausses. Les contrôles et réparations viendront plus tard
(Sprints 2 et 3). Seule exception : la date de dernière mise à jour, envoyée par
l'API sous forme d'un nombre de secondes, est convertie en date lisible.
"""

from datetime import datetime, timezone

import httpx

# Adresses officielles des deux fichiers du flux GBFS Vélo'v
URL_ETAT_STATIONS = (
    "https://download.data.grandlyon.com/files/rdata/jcd_jcdecaux.jcdvelov/station_status.json"
)
URL_FICHE_STATIONS = (
    "https://download.data.grandlyon.com/files/rdata/jcd_jcdecaux.jcdvelov/station_information.json"
)

# Délai d'attente maximum (en secondes) pour une réponse de l'API.
# Au-delà, on abandonne plutôt que de bloquer la collecte automatique.
DELAI_ATTENTE_MAX_SECONDES = 30


def telecharger_json(client: httpx.Client, url: str) -> dict:
    """
    Télécharger un fichier JSON depuis une adresse web.
    Si le serveur répond par une erreur (page introuvable, panne...),
    le script s'arrête avec un message clair au lieu d'enregistrer des données vides.
    """
    reponse = client.get(url)
    # Déclenche une erreur explicite si le code de réponse n'est pas « 200 OK »
    reponse.raise_for_status()
    return reponse.json()


def convertir_date_api(secondes_depuis_1970: int | None) -> datetime | None:
    """
    Le flux GBFS donne les dates sous forme d'un nombre de secondes écoulées
    depuis le 1er janvier 1970 (format « timestamp Unix »), par exemple 1792426764.
    On le convertit en vraie date avec fuseau horaire UTC, lisible par un humain.
    Si l'information est absente, on renvoie « None » (valeur vide).
    """
    if secondes_depuis_1970 is None:
        return None
    return datetime.fromtimestamp(secondes_depuis_1970, tz=timezone.utc)


def collecter_etat_stations() -> list[dict]:
    """
    Télécharger l'état en direct et la fiche de chaque station, puis les croiser.

    RÉSULTAT :
    Une liste avec une ligne par station, contenant :
    - l'heure exacte de notre collecte (identique pour toutes les stations),
    - l'identité de la station (numéro, nom, position GPS, capacité),
    - son état brut (vélos disponibles, places libres, éléments hors service),
    - la date à laquelle la station a envoyé ses chiffres pour la dernière fois
      (indispensable pour repérer les « bornes zombies » figées).
    """
    # Étape 1 : On note l'heure de collecte une seule fois, pour que toutes les
    # stations d'un même relevé partagent exactement le même horodatage.
    heure_collecte = datetime.now(tz=timezone.utc)

    # Étape 2 : On télécharge les deux fichiers du flux GBFS
    with httpx.Client(timeout=DELAI_ATTENTE_MAX_SECONDES) as client:
        etat = telecharger_json(client, URL_ETAT_STATIONS)
        fiches = telecharger_json(client, URL_FICHE_STATIONS)

    # Étape 3 : On range les fiches dans un « annuaire » indexé par numéro de station,
    # pour retrouver instantanément la fiche d'une station à partir de son numéro.
    annuaire_stations = {
        fiche["station_id"]: fiche for fiche in fiches["data"]["stations"]
    }

    # Étape 4 : On note la date à laquelle la Métropole a généré le fichier d'état.
    # Contrairement à la date propre à chaque station (qui n'avance que de temps
    # en temps), elle est rafraîchie en continu : c'est elle qui mesure la
    # fraîcheur du flux (règle DQ_02, choix validé au Sprint 2).
    date_generation_flux = convertir_date_api(etat.get("last_updated"))

    # Étape 5 : Pour chaque station en direct, on assemble une ligne complète
    lignes = []
    for station in etat["data"]["stations"]:
        # Si une station n'a pas de fiche (incohérence de l'API), on la garde quand
        # même avec des champs vides : en Bronze, on ne cache aucune anomalie.
        fiche = annuaire_stations.get(station["station_id"], {})

        lignes.append(
            {
                "ingestion_timestamp": heure_collecte,
                "station_id": station["station_id"],
                "station_name": fiche.get("name"),
                "lat": fiche.get("lat"),
                "lon": fiche.get("lon"),
                "total_stands": fiche.get("capacity"),
                "available_bikes_raw": station.get("num_bikes_available"),
                "available_stands_raw": station.get("num_docks_available"),
                "disabled_bikes_raw": station.get("num_bikes_disabled"),
                "disabled_stands_raw": station.get("num_docks_disabled"),
                # Les 3 indicateurs d'ouverture de la station envoyés par l'API :
                # installée sur le terrain ? location possible ? retour possible ?
                "is_installed_raw": station.get("is_installed"),
                "is_renting_raw": station.get("is_renting"),
                "is_returning_raw": station.get("is_returning"),
                "last_update_api": convertir_date_api(station.get("last_reported")),
                # Identique pour toutes les stations : rangée à part par collect_bronze.py
                "feed_last_updated_api": date_generation_flux,
            }
        )

    return lignes


# Ce bloc ne s'exécute que si on lance le script directement
# (commande : uv run python -m src.ingestion.fetch_velov).
# Il affiche un résumé pour vérifier à l'œil que la collecte fonctionne.
if __name__ == "__main__":
    stations = collecter_etat_stations()
    sans_fiche = sum(1 for s in stations if s["station_name"] is None)
    total_velos = sum(s["available_bikes_raw"] or 0 for s in stations)

    print(f"Collecte réalisée le {stations[0]['ingestion_timestamp']:%d/%m/%Y à %H:%M} (UTC)")
    print(f"Nombre de stations reçues     : {len(stations)}")
    print(f"Stations sans fiche d'identité : {sans_fiche}")
    print(f"Vélos disponibles sur le réseau : {total_velos}")
    print("Exemple de ligne :", stations[0])
