"""
COLLECTE DES DONNÉES DE MOBILITÉ DU GRAND LYON EN DIRECT (Couche Bronze)
=========================================================================

OBJECTIF MÉTIER :
Le vélo n'est qu'un des moyens de se déplacer. Pour comprendre (et plus tard
prédire) l'usage des Vélo'v, on garde à chaque quart d'heure une photo de ce
qui se passe à côté :
  - PARCS RELAIS TCL (P+R) : places libres dans chaque parc. Un P+R plein
    signale de nombreux automobilistes qui finissent leur trajet en transports
    ou à vélo.
  - PARKINGS de la Métropole : places libres. Révèle la pression sur la voiture
    en centre-ville.
  - TRAFIC ROUTIER : état de chaque tronçon (fluide, dense, saturé…). On n'en
    garde qu'un résumé par quart d'heure (nombre de tronçons et kilomètres dans
    chaque état), car le détail représenterait des milliers de lignes à chaque fois.

SOURCE DES DONNÉES :
La plateforme data.grandlyon.com (service WFS). Ces trois jeux de données
demandent un compte gratuit : l'identifiant et le mot de passe sont lus dans
les variables d'environnement GRANDLYON_LOGIN et GRANDLYON_PASSWORD (des
« secrets » GitHub, jamais écrits dans le code ni visibles dans le dépôt).
Sans identifiants, ces données sont simplement ignorées.
"""

import os
from collections import defaultdict

import httpx

URL_WFS_GRANDLYON = "https://download.data.grandlyon.com/wfs/rdata"

COUCHE_PARCS_RELAIS = "sytral:tcl_sytral.tclparcrelaistr"
COUCHE_PARKINGS = "metropole-de-lyon:parkings-de-la-metropole-de-lyon-disponibilites-temps-reel-v2"
COUCHE_TRAFIC = "metropole-de-lyon:pvo_patrimoine_voirie.pvotrafic"

# Délai d'attente maximum (en secondes) avant d'abandonner un appel bloqué
DELAI_ATTENTE_MAX_SECONDES = 60


def lire_identifiants() -> httpx.BasicAuth | None:
    """Lire le compte data.grandlyon.com dans les variables d'environnement (ou None)."""
    login = os.environ.get("GRANDLYON_LOGIN")
    mot_de_passe = os.environ.get("GRANDLYON_PASSWORD")
    if not login or not mot_de_passe:
        return None
    return httpx.BasicAuth(login, mot_de_passe)


def telecharger_couche(client: httpx.Client, couche: str, colonnes: str | None = None) -> list[dict]:
    """
    Télécharger tous les éléments d'une couche WFS, au format GeoJSON,
    avec des coordonnées GPS classiques (EPSG:4326, comme Vélo'v).
    « colonnes » permet de ne demander que certaines informations (plus léger).
    """
    parametres = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "typename": couche,
        "outputFormat": "application/json",
        "SRSNAME": "EPSG:4326",
    }
    if colonnes:
        parametres["propertyName"] = colonnes
    reponse = client.get(URL_WFS_GRANDLYON, params=parametres)
    reponse.raise_for_status()
    return reponse.json()["features"]


def coordonnees(element: dict) -> tuple[float | None, float | None]:
    """
    Extraire (latitude, longitude) d'un élément GeoJSON.
    Un point s'écrit [lon, lat] ; un « multipoint » est une liste de points
    (on garde le premier).
    """
    geometrie = element.get("geometry") or {}
    points = geometrie.get("coordinates")
    if geometrie.get("type") == "MultiPoint" and points:
        points = points[0]
    if not points:
        return None, None
    return points[1], points[0]


def extraire_parcs_relais(elements: list[dict]) -> list[dict]:
    """Une ligne par parc relais : capacité et places libres."""
    lignes = []
    for element in elements:
        infos = element["properties"]
        lat, lon = coordonnees(element)
        lignes.append({
            "parc_id": infos.get("id"),
            "parc_name": infos.get("nom"),
            "lat": lat,
            "lon": lon,
            "capacity": infos.get("capacite"),
            "available_places_raw": infos.get("nb_tot_place_dispo"),
            "last_update_api": infos.get("last_update"),
        })
    return lignes


def extraire_parkings(elements: list[dict]) -> list[dict]:
    """Une ligne par parking : nombre de places, places libres et état (ouvert, complet…)."""
    lignes = []
    for element in elements:
        infos = element["properties"]
        lat, lon = coordonnees(element)
        lignes.append({
            "parking_id": infos.get("id"),
            "parking_name": infos.get("nom"),
            "lat": lat,
            "lon": lon,
            "capacity": infos.get("nb_places"),
            "available_places_raw": infos.get("places_disponibles"),
            "status_raw": infos.get("etat"),
            "last_update_api": infos.get("last_update"),
        })
    return lignes


def resumer_trafic(elements: list[dict]) -> list[dict]:
    """
    Résumer l'état du trafic : pour chaque état renvoyé par la Métropole
    (tel quel, sans traduction), le nombre de tronçons et leur longueur totale.
    Seuls les tronçons dont la mesure est à jour sont comptés.
    """
    resume = defaultdict(lambda: {"nb_segments": 0, "total_length_m": 0})
    for element in elements:
        infos = element["properties"]
        if infos.get("est_a_jour") is False:
            continue
        etat = infos.get("etat") or "INCONNU"
        resume[etat]["nb_segments"] += 1
        resume[etat]["total_length_m"] += infos.get("longueur") or 0
    return [{"traffic_status_raw": etat, **valeurs} for etat, valeurs in sorted(resume.items())]


def collecter_mobilite_grandlyon() -> dict[str, list[dict]] | None:
    """
    Relever les P+R, les parkings et le trafic.
    Renvoie un dictionnaire {source: lignes}, ou None si aucun compte n'est configuré.
    Une source en panne n'empêche pas de relever les autres.
    """
    identifiants = lire_identifiants()
    if identifiants is None:
        return None

    sources = {
        "parcs_relais": lambda client: extraire_parcs_relais(telecharger_couche(client, COUCHE_PARCS_RELAIS)),
        "parkings": lambda client: extraire_parkings(telecharger_couche(client, COUCHE_PARKINGS)),
        # Pour le trafic, on ne demande ni la géométrie ni les noms : seulement de quoi faire le résumé
        "trafic": lambda client: resumer_trafic(
            telecharger_couche(client, COUCHE_TRAFIC, colonnes="etat,longueur,est_a_jour")
        ),
    }
    resultats = {}
    with httpx.Client(auth=identifiants, timeout=DELAI_ATTENTE_MAX_SECONDES) as client:
        for nom, collecter in sources.items():
            try:
                resultats[nom] = collecter(client)
            except (httpx.HTTPError, KeyError, ValueError) as erreur:
                print(f"⚠️  Grand Lyon « {nom} » indisponible pour ce relevé : {erreur}")
    return resultats
