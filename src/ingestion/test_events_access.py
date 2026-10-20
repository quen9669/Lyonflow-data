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
    collecter_ticketmaster,
)


def apercu(texte: str, taille: int = 1500) -> str:
    return texte[:taille].replace("\n", " ")


def tester_ticketmaster() -> None:
    cle = os.environ.get("TICKETMASTER_API_KEY")
    print("\n=== Ticketmaster : clé", "trouvée" if cle else "ABSENTE")
    if not cle:
        return
    try:
        evenements, lieux = collecter_ticketmaster(cle, datetime.now(timezone.utc))
    except httpx.HTTPStatusError as erreur:
        print(f"Refusé : {erreur.response.status_code} → {apercu(erreur.response.text, 300)}")
        return
    print(f"{len(evenements)} événements, {len({l['venue_id'] for l in lieux})} lieux")
    comptes = {}
    for lieu in lieux:
        comptes[lieu["venue_name"]] = comptes.get(lieu["venue_name"], 0) + 1
    for nom, nombre in sorted(comptes.items(), key=lambda x: -x[1])[:25]:
        print(f"  {nombre:>4}  {nom}")
    for evenement in evenements[:5]:
        print("  exemple :", evenement)


def tester_openagenda() -> None:
    cle = os.environ.get("OPENAGENDA_API_KEY")
    print("\n=== OpenAgenda : clé", "trouvée" if cle else "ABSENTE")
    if not cle:
        return
    reponse = httpx.get(
        "https://api.openagenda.com/v2/agendas",
        params={"key": cle, "search": "Lyon", "size": 50, "sort": "recentlyAddedEvents.desc"},
        timeout=60,
    )
    print("Liste des agendas « Lyon » :", reponse.status_code)
    if reponse.status_code != 200:
        print(apercu(reponse.text, 300))
        return
    contenu = reponse.json()
    print("Total :", contenu.get("total"))
    for agenda in contenu.get("agendas", []):
        print(f"  uid={agenda.get('uid')}  officiel={agenda.get('official')}  {agenda.get('title')}")


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
        ("ind_aura:agol_indices_2021_7J", "code_zone='69123'"),
        ("alrt3j_aura:new_alerte_3j", None),
        ("aura:vigilances_today", None),
        ("aura:vigilances_tomorrow", None),
    ]
    for couche, filtre in essais:
        parametres = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "typeNames": couche,
                      "outputFormat": "application/json", "count": 10}
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
        for element in contenu.get("features", [])[:4]:
            print("  ", apercu(json.dumps(element.get("properties"), ensure_ascii=False), 600))


if __name__ == "__main__":
    tester_ticketmaster()
    tester_openagenda()
    tester_atmo()
    tester_atmo_aura_ouvert()
