"""
DIAGNOSTIC DES ALERTES TRAFIC TCL (data.grandlyon.com)
======================================================
Cherche, dans le catalogue du Grand Lyon, les jeux de données liés aux
perturbations TCL, puis affiche quelques alertes en exemple
(jamais les identifiants).

Lancement : uv run python -m src.ingestion.test_tcl_access
"""

import json
import re

import httpx

from src.ingestion.fetch_grandlyon import URL_WFS_GRANDLYON, lire_identifiants

if __name__ == "__main__":
    identifiants = lire_identifiants()
    print("Identifiants trouvés :", "oui" if identifiants else "NON")
    with httpx.Client(auth=identifiants, timeout=90, follow_redirects=True) as client:
        # 1. Catalogue : couches dont le nom évoque les TCL ou les alertes
        reponse = client.get(URL_WFS_GRANDLYON, params={"SERVICE": "WFS", "REQUEST": "GetCapabilities"})
        print("GetCapabilities :", reponse.status_code, len(reponse.text), "caractères")
        couches = sorted(set(re.findall(r"<(?:wfs:)?Name>([^<]+)</(?:wfs:)?Name>", reponse.text)))
        tcl = [c for c in couches if re.search(r"tcl|alerte|perturb|sytral", c, re.I)]
        print(f"{len(couches)} couches, dont {len(tcl)} liées aux TCL :")
        for c in tcl:
            print("  ", c)

        # 2. Exemples de contenu pour les couches d'alertes
        candidates = [c for c in tcl if re.search(r"alerte|perturb", c, re.I)] or ["sytral:tcl_sytral.tclalertetrafic_2"]
        for couche in candidates:
            r = client.get(URL_WFS_GRANDLYON, params={
                "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
                "typename": couche, "outputFormat": "application/json"})
            print(f"\n=== {couche} : {r.status_code}")
            if r.status_code != 200:
                print(r.text[:300])
                continue
            try:
                features = r.json().get("features", [])
            except ValueError:
                print(r.text[:300])
                continue
            print(f"{len(features)} alertes")
            for f in features[:6]:
                print(json.dumps(f.get("properties"), ensure_ascii=False)[:700])

        # 3. Ancienne interface JSON du portail
        for nom in ("tcl_sytral.tclalertetrafic_2", "tcl_sytral.tclalertetrafic"):
            url = f"https://download.data.grandlyon.com/ws/rdata/{nom}/all.json"
            r = client.get(url, params={"maxfeatures": 5})
            print(f"\n=== {url} : {r.status_code}")
            print(r.text[:1500])
