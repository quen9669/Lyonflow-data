"""
COLLECTE DES GRANDES SALLES ET STADES (Couche Bronze, une fois par semaine)
============================================================================

OBJECTIF MÉTIER :
Les événements qui font le plus bouger les Vélo'v (matchs de l'OL, concerts
à la LDLC Arena ou à la Halle Tony Garnier, rugby à Gerland) ne sont pas dans
OpenAgenda. On relève donc chaque semaine le programme publié par ces salles,
avec la date et l'heure exactes, pour tenir le calendrier à jour tout seul
(reports, nouvelles dates, horaires enfin publiés).

SOURCES (vérifiées depuis le robot le 20/10/2026) :
  - LDLC Arena, site officiel : chaque page du calendrier décrit ses événements
    en « données structurées » (format JSON-LD publié pour Google). Concerts,
    spectacles et matchs de l'ASVEL dans la salle.
  - OL Vallée, calendrier officiel du Groupama Stadium et de la LDLC Arena :
    on y prend les matchs de l'OL et de l'OL Lyonnes (liens vers la billetterie
    de l'OL). Les événements de la LDLC Arena viennent déjà de son site.
  - JamBase, agenda de concerts : la Halle Tony Garnier (son site ne publie pas
    de dates lisibles) et les concerts au Groupama Stadium.
  - LOU Rugby, site officiel : les prochains matchs à Gerland (Matmut Stadium).
Le site de l'ASVEL et Infoconcert refusent les robots (code 403) : non utilisés.

ATTENTION AUX HEURES :
Le site de la LDLC Arena indique « +02:00 » (heure d'été) même en hiver.
On lit donc toujours l'heure affichée comme une heure de Lyon, sans tenir
compte du décalage annoncé : 20:00 reste 20:00 à Lyon, été comme hiver.

RANGEMENT (même format que les événements OpenAgenda) :
  - data/bronze/events_salles/AAAA-MM-JJ.csv : un relevé par semaine,
    mêmes colonnes que data/bronze/events/, source « salles » ;
  - data/reference/lieux_evenements.csv : les salles y sont ajoutées
    (identifiant « salle:… »), avec leur position.
L'identifiant d'un événement est « salle:<lieu>:<date et heure> » : un même
événement trouvé sur deux sites n'est compté qu'une fois.

Lancement : uv run python -m src.ingestion.fetch_venues
Essai sans rien enregistrer : uv run python -m src.ingestion.fetch_venues --essai
"""

import html
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from src.ingestion.fetch_events import COLONNES_EVENEMENTS, FICHIER_LIEUX, ajouter_au_fichier_du_jour
from src.ingestion.referentiel import mettre_a_jour_fichier

DOSSIER_SALLES = Path("data/bronze/events_salles")
HEURE_LYON = ZoneInfo("Europe/Paris")

# Les salles suivies : identifiant → (nom, latitude, longitude)
SALLES = {
    "groupama-stadium": ("Groupama Stadium", 45.7653, 4.9822),
    "ldlc-arena": ("LDLC Arena", 45.7668, 4.9870),
    "halle-tony-garnier": ("Halle Tony Garnier", 45.7323, 4.8243),
    "matmut-stadium-gerland": ("Matmut Stadium de Gerland", 45.7239, 4.8322),
}

URL_LDLC_ARENA = "https://www.ldlcarena.com/calendrier/page/{page}/"
URL_OL_VALLEE = "https://www.olvallee.fr/calendrier/"
URL_JAMBASE = "https://www.jambase.com/venue/{salle}"
URL_LOU = "https://www.lourugby.fr/"
PAGES_MAX = 10

# Un navigateur ordinaire : certains sites refusent les requêtes sans nom
ENTETES = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

MOIS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
        "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
        "décembre": 12, "decembre": 12}


# --- Outils -------------------------------------------------------------------
def heure_de_lyon_en_utc(texte: str) -> datetime:
    """
    Lire « 2026-12-09T20:30:00+02:00 » ou « 2026-12-09T20:30:00 » comme une heure
    affichée à Lyon (le décalage annoncé est ignoré, voir plus haut) et la passer en UTC.
    """
    sans_decalage = datetime.fromisoformat(texte[:19])
    return sans_decalage.replace(tzinfo=HEURE_LYON).astimezone(timezone.utc)


def nettoyer(texte: str) -> str:
    """Enlever les balises HTML, les codes (&amp;…) et les espaces en trop."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", texte))).strip()


def evenements_json_ld(page_html: str) -> list[dict]:
    """Tous les objets de type Event (ou MusicEvent…) décrits en JSON-LD dans une page."""
    trouves = []
    for bloc in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page_html, re.S | re.I):
        try:
            pile = [json.loads(bloc.strip())]
        except ValueError:
            continue
        while pile:
            objet = pile.pop()
            if isinstance(objet, list):
                pile += objet
            elif isinstance(objet, dict):
                if "Event" in str(objet.get("@type")):
                    trouves.append(objet)
                pile += [objet[k] for k in ("@graph", "itemListElement", "item") if k in objet]
    return trouves


def ligne(salle: str, nom: str, categorie: str, debut_utc: datetime, origine: str, statut: str = "programme") -> dict:
    """Une ligne au format des événements (mêmes colonnes qu'OpenAgenda)."""
    return {
        "source": "salles",
        "event_id": f"salle:{salle}:{debut_utc:%Y%m%d%H%M}",
        "venue_id": f"salle:{salle}",
        "event_name": nom,
        "category": categorie,
        "genre": origine,
        "start_utc": str(debut_utc),
        "end_utc": "",  # rarement publiée : 3 heures par défaut dans le projet d'analyse
        "status": statut,
    }


# --- Lecture de chaque source (fonctions testables sans Internet) ------------
def lire_ldlc_arena(page_html: str) -> list[dict]:
    """Événements d'une page du calendrier officiel de la LDLC Arena."""
    lignes = []
    for e in evenements_json_ld(page_html):
        if not e.get("startDate"):
            continue
        nom = nettoyer(str(e.get("name", "")))
        categorie = "match" if "ASVEL" in nom.upper() else "concert"
        lignes.append(ligne("ldlc-arena", nom, categorie, heure_de_lyon_en_utc(e["startDate"]), "ldlcarena.com"))
    return lignes


def lire_ol_vallee(page_html: str) -> list[dict]:
    """
    Matchs de l'OL et de l'OL Lyonnes (cartes du calendrier OL Vallée dont le lien
    mène à la billetterie de l'OL). Format de date : « 28 octobre 2026 - 21:00 ».
    """
    lignes = []
    for carte in page_html.split('class="event-card__link')[1:]:
        lien = re.search(r'href="([^"]+)"', carte)
        titre = re.search(r'event-card__title">(.*?)</div>', carte, re.S)
        date = re.search(r'event-card__desc">\s*(\d{1,2})\s+(\w+)\s+(\d{4})\s*-\s*(\d{1,2}):(\d{2})', carte)
        if not (lien and titre and date) or "billetterie.ol.fr" not in lien.group(1):
            continue
        jour, mois, annee, heure, minute = date.groups()
        if mois.lower() not in MOIS:
            continue
        debut = datetime(int(annee), MOIS[mois.lower()], int(jour), int(heure), int(minute), tzinfo=HEURE_LYON)
        nom = nettoyer(titre.group(1))
        lignes.append(ligne("groupama-stadium", nom, "match", debut.astimezone(timezone.utc), "olvallee.fr"))
    return lignes


def lire_jambase(page_html: str, salle: str) -> list[dict]:
    """Concerts d'une salle sur JamBase (« Artiste - Ville - Salle - date » → « Artiste »)."""
    lignes = []
    for e in evenements_json_ld(page_html):
        if not e.get("startDate") or len(e["startDate"]) < 16:
            continue  # date sans heure : on ne saurait pas quand placer l'effet
        nom = nettoyer(str(e.get("name", ""))).split(" - ")[0]
        lignes.append(ligne(salle, nom, "concert", heure_de_lyon_en_utc(e["startDate"]), "jambase.com"))
    return lignes


def liens_matchs_lou(page_html: str) -> dict[str, str]:
    """Liens des prochains matchs du LOU à domicile (« lyon-<adversaire>-JJ-MM-AAAA »)."""
    liens = re.findall(r'https://www\.lourugby\.fr/match/(lyon-[a-z0-9-]+?-\d{2}-\d{2}-\d{4})/', page_html)
    return {cle: f"https://www.lourugby.fr/match/{cle}/" for cle in liens}


def lire_match_lou(cle: str, page_html: str) -> dict:
    """
    Un match du LOU à Gerland. La date vient du lien ; l'heure de la page du match
    (« 16h35 » ou « 16:35 »). Sans heure publiée, on note 16h00 et le statut
    « heure_a_confirmer ».
    """
    adversaire, jour, mois, annee = re.match(r"lyon-(.+)-(\d{2})-(\d{2})-(\d{4})", cle).groups()
    texte = nettoyer(page_html)
    date_affichee = f"{jour}/{mois}/{annee}"
    autour = texte[max(0, texte.find(date_affichee) - 200):texte.find(date_affichee) + 300] if date_affichee in texte else texte
    horaire = re.search(r"\b([01]?\d|2[0-3])\s*[h:]\s*([0-5]\d)\b", autour)
    heure, minute, statut = (int(horaire.group(1)), int(horaire.group(2)), "programme") if horaire else (16, 0, "heure_a_confirmer")
    debut = datetime(int(annee), int(mois), int(jour), heure, minute, tzinfo=HEURE_LYON)
    nom = f"LOU Rugby - {adversaire.replace('-', ' ').title()}"
    return ligne("matmut-stadium-gerland", nom, "match", debut.astimezone(timezone.utc), "lourugby.fr", statut)


# --- Collecte -----------------------------------------------------------------
def collecter_salles(maintenant: datetime) -> tuple[list[dict], dict[str, str]]:
    """
    Relever toutes les sources. Renvoie (événements à venir, bilan par source).
    Une source en panne est notée dans le bilan et n'empêche pas les autres.
    """
    lignes, bilan = [], {}
    with httpx.Client(timeout=60, follow_redirects=True, headers=ENTETES) as client:
        def essayer(nom_source, fonction):
            try:
                trouvees = fonction()
                lignes.extend(trouvees)
                bilan[nom_source] = f"{len(trouvees)} événements"
            except (httpx.HTTPError, ValueError, KeyError, AttributeError) as erreur:
                bilan[nom_source] = f"ÉCHEC : {erreur!r}"

        def ldlc_arena():
            trouvees = []
            for page in range(1, PAGES_MAX + 1):
                reponse = client.get(URL_LDLC_ARENA.format(page=page))
                if reponse.status_code == 404:
                    break
                reponse.raise_for_status()
                nouvelles = lire_ldlc_arena(reponse.text)
                if not nouvelles:
                    break
                trouvees += nouvelles
            return trouvees

        def ol_vallee():
            reponse = client.get(URL_OL_VALLEE)
            reponse.raise_for_status()
            return lire_ol_vallee(reponse.text)

        def jambase(salle):
            reponse = client.get(URL_JAMBASE.format(salle=salle))
            reponse.raise_for_status()
            return lire_jambase(reponse.text, salle)

        def lou():
            accueil = client.get(URL_LOU)
            accueil.raise_for_status()
            matchs = []
            for cle, url in liens_matchs_lou(accueil.text).items():
                page = client.get(url)
                page.raise_for_status()
                matchs.append(lire_match_lou(cle, page.text))
            return matchs

        essayer("LDLC Arena (site officiel)", ldlc_arena)
        essayer("OL Vallée (matchs de l'OL)", ol_vallee)
        essayer("JamBase Halle Tony Garnier", lambda: jambase("halle-tony-garnier"))
        essayer("JamBase Groupama Stadium", lambda: jambase("groupama-stadium"))
        essayer("LOU Rugby", lou)

    # Seulement l'avenir, et une seule fois chaque événement (même salle, même heure)
    a_venir = {l["event_id"]: l for l in lignes if datetime.fromisoformat(l["start_utc"]) >= maintenant}
    return sorted(a_venir.values(), key=lambda l: l["start_utc"]), bilan


def lieux_des_salles() -> list[dict]:
    """Les salles au format du référentiel des lieux."""
    return [{"venue_id": f"salle:{cle}", "venue_name": nom, "lat": lat, "lon": lon}
            for cle, (nom, lat, lon) in SALLES.items()]


if __name__ == "__main__":
    maintenant = datetime.now(timezone.utc)
    evenements, bilan = collecter_salles(maintenant)
    for source, resultat in bilan.items():
        print(f"{source} : {resultat}")
    print(f"Total : {len(evenements)} événements à venir, par salle : "
          f"{dict(Counter(e['venue_id'] for e in evenements))}")
    if "--essai" in sys.argv:
        for e in evenements[:60]:
            debut = datetime.fromisoformat(e["start_utc"]).astimezone(HEURE_LYON)
            print(f"  {debut:%d/%m/%Y %H:%M}  {e['venue_id']:<30} {e['category']:<8} {e['event_name']}  [{e['status']}]")
        sys.exit(0)
    mettre_a_jour_fichier(FICHIER_LIEUX, "venue_id", ["venue_name", "lat", "lon"], lieux_des_salles(), str(maintenant))
    ajouter_au_fichier_du_jour(DOSSIER_SALLES, COLONNES_EVENEMENTS, evenements, maintenant)
    # Le passage est rouge si une source est en panne, pour être prévenu
    if any(r.startswith("ÉCHEC") for r in bilan.values()):
        sys.exit(1)
