"""
DIAGNOSTIC DES SOURCES D'ÉVÉNEMENTS ET DE POLLUTION
====================================================
Lance une vraie collecte, sans rien enregistrer, et affiche ce qu'elle trouve :
nombre de séances par agenda, lieux les plus fréquents, exemples, et niveau de
pollution de la zone lyonnaise. Jamais les clés.

Lancement : uv run python -m src.ingestion.test_events_access
"""

import os
from collections import Counter
from datetime import datetime, timezone

from src.ingestion.fetch_events import collecter_openagenda, collecter_pollution

if __name__ == "__main__":
    maintenant = datetime.now(timezone.utc)
    cle = os.environ.get("OPENAGENDA_API_KEY")
    print("=== OpenAgenda : clé", "trouvée" if cle else "ABSENTE")
    if cle:
        seances, lieux = collecter_openagenda(cle, maintenant)
        noms_lieux = {l["venue_id"]: l["venue_name"] for l in lieux}
        print(f"{len(seances)} séances dans les 14 prochains jours, {len(noms_lieux)} lieux")
        print("Par agenda :", Counter(s["category"] for s in seances).most_common())
        print("Par statut :", Counter(s["status"] for s in seances).most_common())
        print("Lieux les plus fréquents :")
        for venue_id, nombre in Counter(s["venue_id"] for s in seances).most_common(30):
            print(f"  {nombre:>4}  {noms_lieux.get(venue_id)}")
        for seance in seances[:5]:
            print("  exemple :", seance)

    print("\n=== Atmo Auvergne-Rhône-Alpes (sans compte)")
    for ligne in collecter_pollution(maintenant):
        print("  ", ligne)
