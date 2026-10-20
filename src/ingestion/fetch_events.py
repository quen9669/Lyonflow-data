"""
COLLECTE DES ÉVÉNEMENTS ET DE LA POLLUTION (Couche Bronze)
===========================================================

OBJECTIF MÉTIER :
Un concert, une soirée, un spectacle ou un pic de pollution changent l'usage des
Vélo'v. Pour que l'IA apprenne ces effets, on archive à chaque démarrage du robot
(environ toutes les 5h30) :
  - les ÉVÉNEMENTS des 14 prochains jours autour de Lyon, avec leur lieu,
    leur date et leur heure ;
  - la VIGILANCE POLLUTION du bassin lyonnais (aujourd'hui et demain) et les
    DÉPASSEMENTS DE SEUIL annoncés par polluant (hier, aujourd'hui, demain).
On garde chaque relevé : une annonce peut changer (report, annulation),
et l'historique des annonces sert aussi à l'apprentissage.

SOURCES (vérifiées depuis le robot le 20/10/2026) :
  - OpenAgenda (clé gratuite OPENAGENDA_API_KEY) : agendas publics. On suit
    l'agenda officiel de Lyon, Shotgun (billetterie de concerts et soirées),
    l'agenda culturel de Villeurbanne et « Événements à Lyon ».
    Ticketmaster a été testé puis écarté : son service ne contient aucun
    événement à Lyon (seulement 32 en France, presque tous à Paris).
  - Atmo Auvergne-Rhône-Alpes, flux ouverts sans compte : niveau de vigilance
    (vert, jaune, orange, rouge) et dépassements de seuil de la zone
    « Bassin Lyon Nord-Isère ». C'est ce niveau qui déclenche les mesures de la
    préfecture (circulation différenciée, conseils de limiter l'effort physique).
Une source en panne ou sans clé est simplement ignorée : la collecte Vélo'v
n'est jamais bloquée.

RANGEMENT (même principe que les stations) :
  - data/bronze/events/AAAA-MM-JJ.csv      : un relevé des événements à venir,
  - data/bronze/air_quality/AAAA-MM-JJ.csv : vigilance et dépassements de seuil,
  - data/reference/lieux_evenements.csv    : nom et position de chaque lieu,
    historisés (date de début, fin 2099), pour ne pas les répéter à chaque relevé.

Lancement : uv run python -m src.ingestion.fetch_events
"""

import csv
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from src.ingestion.referentiel import mettre_a_jour_fichier

# --- Paramètres --------------------------------------------------------------
# Centre de Lyon (place Bellecour) et rayon gardé : 25 km couvre Décines
# (Groupama Stadium, LDLC Arena), Villeurbanne, Gerland, Vaulx-en-Velin…
CENTRE_LYON = (45.7578, 4.8320)
RAYON_KM = 25
JOURS_A_VENIR = 14

URL_OPENAGENDA = "https://api.openagenda.com/v2/agendas/{uid}/events"
# Agendas suivis : identifiant → nom lisible (sert aussi de « catégorie » de l'événement)
AGENDAS_SUIVIS = {
    84768140: "Ville de Lyon",
    9969608: "Shotgun (concerts et soirées)",
    1168665: "Villeurbanne culturel",
    482183: "Événements à Lyon",
}
# OpenAgenda donne au plus 300 événements par page ; 20 pages suffisent largement
TAILLE_PAGE = 300
PAGES_MAX = 20

URL_ATMO_AURA = "https://sig.atmo-auvergnerhonealpes.fr/geoserver/wfs"
ZONE_LYON = 2003  # « Bassin Lyon Nord-Isère »

DELAI_ATTENTE_MAX_SECONDES = 120
HEURE_LYON = ZoneInfo("Europe/Paris")

DOSSIER_EVENEMENTS = Path("data/bronze/events")
DOSSIER_AIR = Path("data/bronze/air_quality")
FICHIER_LIEUX = Path("data/reference/lieux_evenements.csv")

COLONNES_EVENEMENTS = [
    "ingestion_timestamp", "source", "event_id", "venue_id", "event_name",
    "category", "genre", "start_utc", "end_utc", "status",
]
COLONNES_AIR = [
    "ingestion_timestamp", "type", "date_echeance", "zone", "polluant", "indice", "niveau",
]

# Statuts OpenAgenda (documentation officielle) traduits en mots
STATUTS_OPENAGENDA = {1: "programme", 2: "reporte_date", 3: "en_ligne", 4: "reporte", 5: "complet", 6: "annule"}


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance à vol d'oiseau en kilomètres (formule de haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def texte(valeur) -> str:
    """OpenAgenda écrit les textes par langue ({"fr": "…"}) : on garde le français."""
    if isinstance(valeur, dict):
        return valeur.get("fr") or next(iter(valeur.values()), "")
    return valeur or ""


# --- OpenAgenda --------------------------------------------------------------
def extraire_evenements_openagenda(
    evenements_api: list[dict], agenda: str, debut: datetime, fin: datetime
) -> tuple[list[dict], list[dict]]:
    """
    Transformer des événements OpenAgenda en (séances, lieux).
    Un même événement peut avoir plusieurs séances (horaires) : une ligne par séance
    comprise dans la période, et seulement si le lieu est à moins de 25 km de Lyon.
    """
    seances, lieux = [], []
    for evenement in evenements_api:
        lieu = evenement.get("location") or {}
        if lieu.get("latitude") is None or lieu.get("longitude") is None:
            continue
        if distance_km(*CENTRE_LYON, lieu["latitude"], lieu["longitude"]) > RAYON_KM:
            continue
        venue_id = f"oa:{lieu.get('uid')}"
        lieux.append({"venue_id": venue_id, "venue_name": lieu.get("name"),
                      "lat": lieu["latitude"], "lon": lieu["longitude"]})
        mots_cles = evenement.get("keywords") or {}
        mots_cles = mots_cles.get("fr", []) if isinstance(mots_cles, dict) else mots_cles
        for horaire in evenement.get("timings") or []:
            commence = datetime.fromisoformat(horaire["begin"]).astimezone(timezone.utc)
            if not debut <= commence <= fin:
                continue
            seances.append({
                "source": "openagenda",
                "event_id": f"oa:{evenement.get('uid')}:{commence:%Y%m%d%H%M}",
                "venue_id": venue_id,
                "event_name": texte(evenement.get("title")),
                "category": agenda,
                "genre": ", ".join(mots_cles[:3]),
                "start_utc": str(commence),
                "end_utc": str(datetime.fromisoformat(horaire["end"]).astimezone(timezone.utc)) if horaire.get("end") else "",
                "status": STATUTS_OPENAGENDA.get(evenement.get("status"), evenement.get("status") or ""),
            })
    return seances, lieux


def collecter_openagenda(cle: str, maintenant: datetime) -> tuple[list[dict], list[dict]]:
    """Séances des 14 prochains jours dans un rayon de 25 km, pour chaque agenda suivi."""
    fin = maintenant + timedelta(days=JOURS_A_VENIR)
    # Petit « rectangle » autour de Lyon pour que le serveur ne renvoie que la région
    ecart_lat, ecart_lon = RAYON_KM / 111, RAYON_KM / 78
    seances, lieux = [], []
    with httpx.Client(timeout=DELAI_ATTENTE_MAX_SECONDES) as client:
        for uid, nom_agenda in AGENDAS_SUIVIS.items():
            parametres = {
                "key": cle, "size": TAILLE_PAGE, "detailed": 1,
                "timings[gte]": maintenant.isoformat(), "timings[lte]": fin.isoformat(),
                "geo[northEast][lat]": CENTRE_LYON[0] + ecart_lat, "geo[northEast][lng]": CENTRE_LYON[1] + ecart_lon,
                "geo[southWest][lat]": CENTRE_LYON[0] - ecart_lat, "geo[southWest][lng]": CENTRE_LYON[1] - ecart_lon,
            }
            suite = None
            for _ in range(PAGES_MAX):
                reponse = client.get(URL_OPENAGENDA.format(uid=uid), params=[
                    *parametres.items(), *(("after[]", v) for v in (suite or []))
                ])
                reponse.raise_for_status()
                contenu = reponse.json()
                nouvelles, nouveaux_lieux = extraire_evenements_openagenda(
                    contenu.get("events", []), nom_agenda, maintenant, fin)
                seances += nouvelles
                lieux += nouveaux_lieux
                suite = contenu.get("after")
                if not suite or not contenu.get("events"):
                    break
    # Un même événement peut être publié dans plusieurs agendas : on le garde une fois
    uniques = {seance["event_id"]: seance for seance in seances}
    return list(uniques.values()), lieux


# --- Atmo Auvergne-Rhône-Alpes (flux ouverts) --------------------------------
def lire_couche_atmo(client: httpx.Client, couche: str) -> list[dict]:
    """Télécharger une couche du serveur cartographique d'Atmo AURA (format GeoJSON)."""
    reponse = client.get(URL_ATMO_AURA, params={
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
        "typeNames": couche, "outputFormat": "application/json",
    })
    reponse.raise_for_status()
    return [element["properties"] for element in reponse.json()["features"]]


def extraire_vigilance(proprietes: list[dict], jour: str) -> list[dict]:
    """Niveau de vigilance de la zone lyonnaise : 1 = vert, 2 = jaune, 3 = orange, 4 = rouge."""
    return [{
        "type": "vigilance", "date_echeance": jour, "zone": p.get("lib_court_zone"),
        "polluant": p.get("polluant_id") or "", "indice": p.get("niveau_id"), "niveau": p.get("niveau_vigilance"),
    } for p in proprietes if p.get("id_zone") == ZONE_LYON]


def extraire_depassements(proprietes: list[dict]) -> list[dict]:
    """État de chaque polluant pour la zone lyonnaise (« PAS DE DEPASSEMENT » ou procédure en cours)."""
    return [{
        "type": "depassement", "date_echeance": str(p.get("date_ech", ""))[:10], "zone": p.get("lib_zone"),
        "polluant": p.get("lib_pol"), "indice": p.get("code_pol"), "niveau": p.get("etat"),
    } for p in proprietes if p.get("code_zone") == ZONE_LYON]


def collecter_pollution(maintenant: datetime) -> list[dict]:
    """Vigilance d'aujourd'hui et de demain + dépassements de seuil sur 3 jours (zone de Lyon)."""
    aujourdhui = maintenant.astimezone(HEURE_LYON).date()
    with httpx.Client(timeout=DELAI_ATTENTE_MAX_SECONDES) as client:
        lignes = extraire_vigilance(lire_couche_atmo(client, "aura:vigilances_today"), str(aujourdhui))
        lignes += extraire_vigilance(lire_couche_atmo(client, "aura:vigilances_tomorrow"),
                                     str(aujourdhui + timedelta(days=1)))
        lignes += extraire_depassements(lire_couche_atmo(client, "alrt3j_aura:new_alerte_3j"))
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
    """Relever toutes les sources. Une source en panne n'empêche pas les autres."""
    maintenant = datetime.now(timezone.utc)

    cle = os.environ.get("OPENAGENDA_API_KEY")
    if cle:
        try:
            seances, lieux = collecter_openagenda(cle, maintenant)
            mettre_a_jour_fichier(FICHIER_LIEUX, "venue_id", ["venue_name", "lat", "lon"], lieux, str(maintenant))
            ajouter_au_fichier_du_jour(DOSSIER_EVENEMENTS, COLONNES_EVENEMENTS, seances, maintenant)
            print(f"OpenAgenda : {len(seances)} séances à venir, {len({l['venue_id'] for l in lieux})} lieux")
        except (httpx.HTTPError, KeyError, ValueError) as erreur:
            print(f"⚠️  OpenAgenda indisponible : {erreur}")
    else:
        print("OpenAgenda : pas de clé, ignoré")

    try:
        lignes = collecter_pollution(maintenant)
        ajouter_au_fichier_du_jour(DOSSIER_AIR, COLONNES_AIR, lignes, maintenant)
        print(f"Atmo AURA : {len(lignes)} lignes (vigilance et dépassements)")
    except (httpx.HTTPError, KeyError, ValueError) as erreur:
        print(f"⚠️  Atmo AURA indisponible : {erreur}")


if __name__ == "__main__":
    collecter_evenements_et_pollution()
