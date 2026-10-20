"""
DIAGNOSTIC DE L'ACCÈS AUX SOURCES D'ÉVÉNEMENTS ET DE POLLUTION
===============================================================
Pour chaque source : le code de réponse du serveur (jamais les clés),
puis un aperçu de ce qu'elle renvoie, pour vérifier les noms des champs
avant de lancer la collecte régulière.
  200 = accès accordé ; 401 / 403 = clé ou identifiants refusés.

Lancement : uv run python -m src.ingestion.test_events_access
"""

import json
import os
from datetime import datetime, timezone

import httpx

from src.ingestion.fetch_events import (
    CODE_INSEE_LYON,
    URL_ATMO,
)


def apercu(texte: str, taille: int = 1500) -> str:
    return texte[:taille].replace("\n", " ")


def tester_ticketmaster() -> None:
    cle = os.environ.get("TICKETMASTER_API_KEY")
    print("\n=== Ticketmaster : clé", "trouvée" if cle else "ABSENTE")
    if not cle:
        return
    url = "https://app.ticketmaster.com/discovery/v2/events.json"
    for nom, parametres in (
        ("rayon 25 km autour de Lyon", {"latlong": "45.7578,4.8320", "radius": 25, "unit": "km"}),
        ("pays France", {"countryCode": "FR"}),
        ("ville Lyon", {"city": "Lyon"}),
        ("mot-clé Lyon", {"keyword": "Lyon"}),
        ("lieux à Lyon", None),
    ):
        if parametres is None:
            reponse = httpx.get("https://app.ticketmaster.com/discovery/v2/venues.json",
                                params={"apikey": cle, "keyword": "Lyon", "size": 20}, timeout=60)
        else:
            reponse = httpx.get(url, params={"apikey": cle, "size": 5, **parametres}, timeout=60)
        contenu = reponse.json() if reponse.status_code == 200 else {}
        total = contenu.get("page", {}).get("totalElements")
        print(f"{nom} : {reponse.status_code}, {total} résultats")
        for element in list(contenu.get("_embedded", {}).values())[0][:5] if contenu.get("_embedded") else []:
            lieu = (element.get("_embedded", {}).get("venues") or [element])[0]
            print("   ", element.get("name"), "|", lieu.get("name"), "|", (lieu.get("city") or {}).get("name"))


def tester_openagenda() -> None:
    cle = os.environ.get("OPENAGENDA_API_KEY")
    print("\n=== OpenAgenda : clé", "trouvée" if cle else "ABSENTE")
    if not cle:
        return
    for recherche in ("Lyon", "Ville de Lyon", "Métropole de Lyon", "concerts Lyon"):
        reponse = httpx.get("https://api.openagenda.com/v2/agendas",
                            params={"key": cle, "search": recherche, "size": 20, "official": 1}, timeout=60)
        agendas = reponse.json().get("agendas", []) if reponse.status_code == 200 else []
        print(f"Agendas officiels « {recherche} » :", [(a.get("uid"), a.get("title")) for a in agendas])
    # Événements à venir de quelques agendas candidats
    for uid in (482183, 9969608, 1168665, 28050806):
        reponse = httpx.get(f"https://api.openagenda.com/v2/agendas/{uid}/events",
                            params={"key": cle, "size": 5, "relative[]": "upcoming", "detailed": 1}, timeout=60)
        print(f"\nAgenda {uid} : {reponse.status_code}")
        if reponse.status_code != 200:
            print("  ", apercu(reponse.text, 300))
            continue
        contenu = reponse.json()
        print("  événements à venir :", contenu.get("total"))
        for evenement in contenu.get("events", [])[:3]:
            lieu = evenement.get("location") or {}
            print("   ", apercu(json.dumps({
                "titre": evenement.get("title"), "debut": (evenement.get("firstTiming") or {}).get("begin"),
                "lieu": lieu.get("name"), "ville": lieu.get("city"), "lat": lieu.get("latitude"),
                "lon": lieu.get("longitude"), "cles": list(evenement)[:40],
            }, ensure_ascii=False), 900))


def tester_atmo() -> None:
    login, mot_de_passe = os.environ.get("ATMO_LOGIN"), os.environ.get("ATMO_PASSWORD")
    print("\n=== Atmo Data : identifiants", "trouvés" if login and mot_de_passe else "ABSENTS")
    if not (login and mot_de_passe):
        return
    with httpx.Client(timeout=60) as client:
        reponse = client.post(f"{URL_ATMO}/login", json={"username": login, "password": mot_de_passe})
        print("Connexion :", reponse.status_code)
        if reponse.status_code != 200:
            print(apercu(reponse.text, 300))
            return
        entetes = {"Authorization": f"Bearer {reponse.json()['token']}"}
        aujourdhui = datetime.now(timezone.utc).date().isoformat()
        for chemin, parametres in (
            ("/v2/data/indices/atmo", {"format": "geojson", "date": aujourdhui, "code_zone": CODE_INSEE_LYON}),
            ("/v2/data/episodes/3jours", {"format": "geojson"}),
            ("/v2/data/episodes/historique", {"format": "geojson", "date": aujourdhui}),
        ):
            reponse = client.get(f"{URL_ATMO}{chemin}", params=parametres, headers=entetes)
            print(f"{chemin} : {reponse.status_code}")
            try:
                contenu = reponse.json()
                elements = contenu.get("features", [])
                print(f"  {len(elements)} éléments ; premier :",
                      apercu(json.dumps(elements[0].get("properties") if elements else contenu, ensure_ascii=False)))
            except ValueError:
                print("  ", apercu(reponse.text, 300))


def tester_atmo_aura_ouvert() -> None:
    """Flux ouverts (sans compte) d'Atmo Auvergne-Rhône-Alpes : un exemple de chaque couche utile."""
    print("\n=== Atmo Auvergne-Rhône-Alpes, flux ouverts (sans compte)")
    url = "https://sig.atmo-auvergnerhonealpes.fr/geoserver/wfs"
    essais = [
        ("ind_aura:agol_indices_2021_7J", None),
        ("alrt3j_aura:new_alerte_3j", None),
        ("aura:vigilances_today", None),
        ("aura:vigilances_tomorrow", None),
    ]
    for couche, filtre in essais:
        parametres = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "typeNames": couche,
                      "outputFormat": "application/json", "count": 2}
        if filtre:
            parametres["CQL_FILTER"] = filtre
        print(f"\n--- {couche} ({filtre or 'sans filtre'})")
        try:
            reponse = httpx.get(url, params=parametres, timeout=120)
            contenu = reponse.json()
        except (httpx.HTTPError, ValueError) as erreur:
            print("  erreur :", erreur)
            continue
        print("  code :", reponse.status_code, "; total :", contenu.get("totalFeatures") or contenu.get("numberMatched"))
        for element in contenu.get("features", [])[:2]:
            print("  ", apercu(json.dumps(element.get("properties"), ensure_ascii=False), 600))
        if couche != "ind_aura:agol_indices_2021_7J":
            parametres.pop("count")
            tout = httpx.get(url, params=parametres, timeout=120).json().get("features", [])
            zones = sorted({str(e["properties"].get("lib_zone") or e["properties"].get("lib_court_zone")) for e in tout})
            print("  zones :", zones)
            for e in tout:
                zone = str(e["properties"].get("lib_zone") or e["properties"].get("lib_court_zone"))
                if "lyon" in zone.lower():
                    print("   LYON :", apercu(json.dumps(e["properties"], ensure_ascii=False), 400))


if __name__ == "__main__":
    tester_ticketmaster()
    tester_openagenda()
    tester_atmo()
