"""
DIAGNOSTIC DES SITES DES GRANDES SALLES (lancé à la main depuis GitHub)
=======================================================================
Pour chaque page candidate : code de réponse, taille, et événements décrits en
« données structurées » (balises JSON-LD de type Event, que les sites publient
pour Google). Rien n'est enregistré.

Lancement : uv run python -m src.ingestion.test_venues_access
"""

import json
import re

import httpx

PAGES = [
    "https://www.ldlcarena.com/calendrier/",
    "https://www.ldlcarena.com/calendrier/page/2/",
    "https://www.ldlcarena.com/wp-json/wp/v2/types",
    "https://www.halle-tony-garnier.com/",
    "https://www.halle-tony-garnier.com/fr/programmation",
    "https://billetterie.ol.fr/fr/calendrier",
    "https://www.ol.fr/fr/football/masculin/calendrier",
    "https://www.olvallee.fr/calendrier/",
    "https://www.lourugby.fr/",
    "https://www.lourugby.fr/calendrier/",
    "https://ldlcasvel.com/calendrier/",
    "https://www.infoconcert.com/salle/ldlc-arena-a-lyon-68389/concerts",
    "https://www.infoconcert.com/salle/halle-tony-garnier-htg-876/concerts",
    "https://www.jds.fr/lyon/decines-charpieu/terrain-de-sport/ldlc-arena-17541_L",
    "https://www.jambase.com/venue/ldlc-arena",
    "https://www.jambase.com/venue/halle-tony-garnier",
]
ENTETES = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "Accept-Language": "fr-FR,fr;q=0.9"}


def objets_json_ld(html: str) -> list:
    objets = []
    for bloc in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            contenu = json.loads(bloc.strip())
        except ValueError:
            continue
        pile = [contenu]
        while pile:
            o = pile.pop()
            if isinstance(o, list):
                pile += o
            elif isinstance(o, dict):
                objets.append(o)
                pile += [v for k, v in o.items() if k in ("@graph", "itemListElement", "item", "subEvent")]
    return objets


if __name__ == "__main__":
    with httpx.Client(timeout=30, follow_redirects=True, headers=ENTETES) as client:
        for url in PAGES:
            try:
                r = client.get(url)
            except httpx.HTTPError as e:
                print(f"\n### {url}\n  ERREUR {e!r}")
                continue
            texte = r.text
            objets = objets_json_ld(texte)
            types = sorted({str(o.get("@type")) for o in objets})
            evenements = [o for o in objets if "Event" in str(o.get("@type"))]
            print(f"\n### {url}\n  statut {r.status_code}, {len(texte)} caractères, url finale {r.url}")
            print(f"  JSON-LD : {len(objets)} objets, types {types[:15]}, {len(evenements)} événements")
            for e in evenements[:4]:
                lieu = e.get("location")
                lieu = lieu.get("name") if isinstance(lieu, dict) else lieu
                print(f"    - {e.get('name')!r} | {e.get('startDate')} → {e.get('endDate')} | {lieu}")
            if not evenements:
                dates = re.findall(r'\b\d{1,2}[ /.-](?:\d{2}|janv|févr|mars|avr|mai|juin|juil|août|sept|oct|nov|déc)\w*[ /.-]20\d{2}', texte)
                print(f"  dates trouvées dans le texte : {len(dates)} ex. {dates[:5]}")
                print(f"  extrait : {re.sub(r'\\s+', ' ', re.sub(r'<[^>]+>', ' ', texte))[2000:2600]!r}")
