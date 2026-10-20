"""
DIAGNOSTIC DE L'ACCÈS AUX DONNÉES DU GRAND LYON
================================================
Affiche, pour chaque jeu de données, le code de réponse du serveur
et le message d'erreur éventuel (jamais les identifiants).
  200 = accès accordé ; 401 = identifiants refusés ; 403 = accès au jeu non accordé.

Lancement : uv run python -m src.ingestion.test_grandlyon_access
"""

import httpx

from src.ingestion.fetch_grandlyon import (
    COUCHE_PARCS_RELAIS,
    COUCHE_PARKINGS,
    COUCHE_TRAFIC,
    URL_WFS_GRANDLYON,
    lire_identifiants,
)

if __name__ == "__main__":
    identifiants = lire_identifiants()
    print("Identifiants trouvés :", "oui" if identifiants else "NON (secrets absents ou vides)")
    for couche in (COUCHE_PARCS_RELAIS, COUCHE_PARKINGS, COUCHE_TRAFIC):
        reponse = httpx.get(
            URL_WFS_GRANDLYON,
            params={"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
                    "typename": couche, "outputFormat": "application/json", "count": 1},
            auth=identifiants,
            timeout=60,
        )
        detail = "" if reponse.status_code == 200 else f" → {reponse.text[:200]}"
        print(f"{couche} : {reponse.status_code}{detail}")
