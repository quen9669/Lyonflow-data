"""
DIAGNOSTIC DES ALERTES TRAFIC TCL (data.grandlyon.com)
======================================================
Télécharge toutes les alertes TCL en cours et affiche un résumé chiffré
(par type, cause, mode, gravité) pour préparer leur collecte
(jamais les identifiants).

Lancement : uv run python -m src.ingestion.test_tcl_access
"""

import collections
import json

import httpx

from src.ingestion.fetch_grandlyon import lire_identifiants

URL_ALERTES = "https://download.data.grandlyon.com/ws/rdata/tcl_sytral.tclalertetrafic_2/all.json"

if __name__ == "__main__":
    with httpx.Client(auth=lire_identifiants(), timeout=90, follow_redirects=True) as client:
        reponse = client.get(URL_ALERTES, params={"maxfeatures": 1000})
        print("Statut :", reponse.status_code, len(reponse.content), "octets")
        alertes = reponse.json()["values"]
        print(len(alertes), "alertes")
        for champ in ("type", "cause", "mode", "typeseverite", "niveauseverite", "typeobjet", "n"):
            print(f"\n{champ} :", collections.Counter(a.get(champ) for a in alertes).most_common(15))
        print("\nlignes :", collections.Counter(a.get("ligne_com") for a in alertes).most_common(60))
        print("\nlongueur message moyenne :", sum(len(a.get("message") or "") for a in alertes) // max(len(alertes), 1))
        print("last_update_fme :", sorted({a.get("last_update_fme") for a in alertes})[-3:])
        # Alertes « fortes » (interruptions, perturbations) en exemple
        fortes = [a for a in alertes if a.get("type") != "Information"]
        print(f"\n{len(fortes)} alertes hors « Information », exemples :")
        for a in fortes[:15]:
            a = {k: v for k, v in a.items() if k != "message"}
            print(json.dumps(a, ensure_ascii=False)[:400])
        # Plusieurs lignes pour une même alerte ?
        print("\nlisteobjet à plusieurs valeurs :", [a["listeobjet"] for a in alertes if "," in (a.get("listeobjet") or "")][:10])
