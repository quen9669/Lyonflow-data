"""
COLLECTE DES ÉVÉNEMENTS ET DE LA POLLUTION (Couche Bronze)
===========================================================

OBJECTIF MÉTIER :
Un concert à la LDLC Arena, un match au Groupama Stadium ou un pic de pollution
changent l'usage des Vélo'v. Pour que l'IA apprenne ces effets, on archive,
plusieurs fois par jour (à chaque démarrage du robot, environ toutes les 5h30) :
  - les ÉVÉNEMENTS des 14 prochains jours autour de Lyon (concerts, matchs,
    spectacles), avec leur lieu, leur date et leur heure ;
  - l'INDICE DE QUALITÉ DE L'AIR de Lyon (aujourd'hui et demain) et les
    ÉPISODES DE POLLUTION annoncés (vigilance jaune, orange ou rouge).
On garde chaque relevé : une annonce peut changer (report, annulation),
et l'historique des annonces sert aussi à l'apprentissage.

SOURCES (comptes gratuits, clés rangées dans les « secrets » GitHub) :
  - Ticketmaster Discovery API (TICKETMASTER_API_KEY) : grandes salles et stades ;
  - OpenAgenda (OPENAGENDA_API_KEY) : agendas culturels publics, ajouté après
    le choix des agendas à suivre ;
  - Atmo Data, fédération Atmo France (ATMO_LOGIN / ATMO_PASSWORD) : indice ATMO
    par commune (publié chaque jour vers 14h) et épisodes de pollution.
Une source sans clé ou en panne est simplement ignorée : la collecte Vélo'v
n'est jamais bloquée.

RANGEMENT (même principe que les stations) :
  - data/bronze/events/AAAA-MM-JJ.csv    : un relevé des événements à venir,
  - data/bronze/air_quality/AAAA-MM-JJ.csv : indice et épisodes de pollution,
  - data/reference/lieux_evenements.csv  : nom et position de chaque lieu,
    historisés (date de début, fin 2099), pour ne pas les répéter à chaque relevé.

Lancement : uv run python -m src.ingestion.fetch_events
"""

import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from src.ingestion.referentiel import mettre_a_jour_fichier

# --- Paramètres --------------------------------------------------------------
# Centre de Lyon (place Bellecour) et rayon de recherche : 25 km couvre
# Décines (Groupama Stadium), Villeurbanne, Gerland, Vaulx-en-Velin…
CENTRE_LYON = "45.7578,4.8320"
RAYON_KM = 25
JOURS_A_VENIR = 14

URL_TICKETMASTER = "https://app.ticketmaster.com/discovery/v2/events.json"
URL_ATMO = "https://admindata.atmo-france.org/api"
CODE_INSEE_LYON = "69123"

DELAI_ATTENTE_MAX_SECONDES = 60

DOSSIER_EVENEMENTS = Path("data/bronze/events")
DOSSIER_AIR = Path("data/bronze/air_quality")
FICHIER_LIEUX = Path("data/reference/lieux_evenements.csv")

COLONNES_EVENEMENTS = [
    "ingestion_timestamp", "source", "event_id", "venue_id", "event_name",
    "category", "genre", "start_utc", "start_local", "status",
]
COLONNES_AIR = [
    "ingestion_timestamp", "type", "date_echeance", "zone", "polluant", "indice", "niveau",
]


# --- Ticketmaster ------------------------------------------------------------
def extraire_evenements_ticketmaster(reponse: dict) -> tuple[list[dict], list[dict]]:
    """
    Transformer une page de réponse Ticketmaster en (événements, lieux).
    Un événement sans lieu géolocalisé est gardé, mais sans lieu.
    """
    evenements, lieux = [], []
    for evenement in reponse.get("_embedded", {}).get("events", []):
        debut = evenement.get("dates", {}).get("start", {})
        classement = (evenement.get("classifications") or [{}])[0]
        lieu = (evenement.get("_embedded", {}).get("venues") or [{}])[0]
        position = lieu.get("location") or {}
        venue_id = f"tm:{lieu['id']}" if lieu.get("id") else ""
        if venue_id and position.get("latitude"):
            lieux.append({
                "venue_id": venue_id, "venue_name": lieu.get("name"),
                "lat": position.get("latitude"), "lon": position.get("longitude"),
            })
        heure_locale = debut.get("localTime") or ""
        evenements.append({
            "source": "ticketmaster",
            "event_id": f"tm:{evenement.get('id')}",
            "venue_id": venue_id,
            "event_name": evenement.get("name"),
            "category": (classement.get("segment") or {}).get("name"),
            "genre": (classement.get("genre") or {}).get("name"),
            "start_utc": debut.get("dateTime") or "",
            "start_local": f"{debut.get('localDate', '')} {heure_locale}".strip(),
            "status": evenement.get("dates", {}).get("status", {}).get("code"),
        })
    return evenements, lieux


def collecter_ticketmaster(cle: str, maintenant: datetime) -> tuple[list[dict], list[dict]]:
    """Tous les événements des 14 prochains jours dans un rayon de 25 km (page par page)."""
    parametres = {
        "apikey": cle,
        "latlong": CENTRE_LYON,
        "radius": RAYON_KM,
        "unit": "km",
        "size": 200,
        "sort": "date,asc",
        "startDateTime": maintenant.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endDateTime": (maintenant + timedelta(days=JOURS_A_VENIR)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    evenements, lieux = [], []
    with httpx.Client(timeout=DELAI_ATTENTE_MAX_SECONDES) as client:
        # Ticketmaster ne donne pas plus de 1 000 résultats (5 pages de 200) : largement assez
        for page in range(5):
            reponse = client.get(URL_TICKETMASTER, params={**parametres, "page": page})
            reponse.raise_for_status()
            contenu = reponse.json()
            nouveaux, nouveaux_lieux = extraire_evenements_ticketmaster(contenu)
            evenements += nouveaux
            lieux += nouveaux_lieux
            if page + 1 >= contenu.get("page", {}).get("totalPages", 0):
                break
    return evenements, lieux


# --- Atmo Data ---------------------------------------------------------------
def jeton_atmo(client: httpx.Client, login: str, mot_de_passe: str) -> str:
    """Se connecter à Atmo Data et obtenir un jeton d'accès (valable quelques heures)."""
    reponse = client.post(f"{URL_ATMO}/login", json={"username": login, "password": mot_de_passe})
    reponse.raise_for_status()
    return reponse.json()["token"]


def extraire_indices_atmo(reponse: dict) -> list[dict]:
    """Indice ATMO de Lyon : 1 (bon) à 6 (extrêmement mauvais), pour chaque jour publié."""
    lignes = []
    for element in reponse.get("features", []):
        infos = element.get("properties", {})
        lignes.append({
            "type": "indice",
            "date_echeance": infos.get("date_ech"),
            "zone": infos.get("lib_zone") or infos.get("code_zone"),
            "polluant": "",
            "indice": infos.get("code_qual"),
            "niveau": infos.get("lib_qual"),
        })
    return lignes


def extraire_episodes_atmo(reponse: dict) -> list[dict]:
    """Épisodes de pollution annoncés ou constatés (niveau : information, alerte…)."""
    lignes = []
    for element in reponse.get("features", []):
        infos = element.get("properties", {})
        lignes.append({
            "type": "episode",
            "date_echeance": infos.get("date_ech"),
            "zone": infos.get("lib_zone"),
            "polluant": infos.get("lib_pol"),
            "indice": infos.get("code_etat") or infos.get("code_pol"),
            "niveau": infos.get("etat"),
        })
    return lignes


def collecter_atmo(login: str, mot_de_passe: str, maintenant: datetime) -> list[dict]:
    """Indice de Lyon pour aujourd'hui et demain + épisodes des 3 derniers / prochains jours."""
    with httpx.Client(timeout=DELAI_ATTENTE_MAX_SECONDES) as client:
        entetes = {"Authorization": f"Bearer {jeton_atmo(client, login, mot_de_passe)}"}
        lignes = []
        for jour in (maintenant.date(), maintenant.date() + timedelta(days=1)):
            reponse = client.get(
                f"{URL_ATMO}/v2/data/indices/atmo",
                params={"format": "geojson", "date": jour.isoformat(), "code_zone": CODE_INSEE_LYON},
                headers=entetes,
            )
            reponse.raise_for_status()
            lignes += extraire_indices_atmo(reponse.json())
        reponse = client.get(
            f"{URL_ATMO}/v2/data/episodes/3jours", params={"format": "geojson"}, headers=entetes
        )
        reponse.raise_for_status()
        # On ne garde que les épisodes qui concernent le bassin lyonnais
        lignes += [e for e in extraire_episodes_atmo(reponse.json()) if "lyon" in str(e["zone"]).lower()]
    return lignes


# --- Écriture ----------------------------------------------------------------
def ajouter_au_fichier_du_jour(dossier: Path, colonnes: list[str], lignes: list[dict], maintenant: datetime) -> None:
    """Ajouter des lignes au fichier CSV du jour (créé avec son en-tête s'il n'existe pas)."""
    if not lignes:
        return
    dossier.mkdir(parents=True, exist_ok=True)
    fichier = dossier / f"{maintenant:%Y-%m-%d}.csv"
    nouveau = not fichier.exists()
    with fichier.open("a", newline="", encoding="utf-8") as flux:
        ecrivain = csv.DictWriter(flux, fieldnames=colonnes, extrasaction="ignore")
        if nouveau:
            ecrivain.writeheader()
        ecrivain.writerows({"ingestion_timestamp": str(maintenant), **ligne} for ligne in lignes)


def collecter_evenements_et_pollution() -> None:
    """Relever toutes les sources configurées. Une source en panne n'empêche pas les autres."""
    maintenant = datetime.now(timezone.utc)

    cle_ticketmaster = os.environ.get("TICKETMASTER_API_KEY")
    if cle_ticketmaster:
        try:
            evenements, lieux = collecter_ticketmaster(cle_ticketmaster, maintenant)
            mettre_a_jour_fichier(FICHIER_LIEUX, "venue_id", ["venue_name", "lat", "lon"], lieux, str(maintenant))
            ajouter_au_fichier_du_jour(DOSSIER_EVENEMENTS, COLONNES_EVENEMENTS, evenements, maintenant)
            print(f"Ticketmaster : {len(evenements)} événements à venir, {len({l['venue_id'] for l in lieux})} lieux")
        except (httpx.HTTPError, KeyError, ValueError) as erreur:
            print(f"⚠️  Ticketmaster indisponible : {erreur}")
    else:
        print("Ticketmaster : pas de clé, ignoré")

    login, mot_de_passe = os.environ.get("ATMO_LOGIN"), os.environ.get("ATMO_PASSWORD")
    if login and mot_de_passe:
        try:
            lignes = collecter_atmo(login, mot_de_passe, maintenant)
            ajouter_au_fichier_du_jour(DOSSIER_AIR, COLONNES_AIR, lignes, maintenant)
            print(f"Atmo : {len(lignes)} lignes (indices et épisodes)")
        except (httpx.HTTPError, KeyError, ValueError) as erreur:
            print(f"⚠️  Atmo indisponible : {erreur}")
    else:
        print("Atmo : pas d'identifiants, ignoré")


if __name__ == "__main__":
    collecter_evenements_et_pollution()
