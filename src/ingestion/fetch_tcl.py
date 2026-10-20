"""
JOURNAL DES ALERTES TRAFIC TCL (travaux, déviations, interruptions…)
=====================================================================

OBJECTIF MÉTIER :
Quand un métro, un tram ou un funiculaire est coupé ou perturbé, une partie
des voyageurs se reporte sur Vélo'v près des stations concernées. Ce script
garde la trace de toutes les alertes publiées par TCL, pour que l'IA puisse
relier ces reports aux variations de vélos.

SOURCE :
Jeu « Alertes trafic TCL » de data.grandlyon.com (compte Grand Lyon, mêmes
secrets que les P+R). Environ 380 alertes en cours le 20/10/2026, dont 368
concernent des bus (surtout des déviations pour travaux).

FORMAT « JOURNAL » (choix proposé le 20/10/2026) :
Plutôt que de recopier les 380 alertes toutes les 15 minutes (36 000 lignes
par jour), on tient un journal : UNE ligne par alerte, dans
data/reference/tcl_alertes.csv, avec :
  - premiere_vue : l'heure du premier relevé où l'alerte est apparue,
  - disparue_le  : l'heure du premier relevé où elle n'était plus publiée
                   (vide tant qu'elle est en cours).
Le fichier ne change que lorsqu'une alerte apparaît, disparaît ou change de
dates. En plus, chaque relevé ajoute UNE ligne de résumé dans
data/bronze/tcl_feed/AAAA-MM-JJ.csv (nombre d'alertes, heure de mise à jour
du flux) : c'est ce qui prouve à la surveillance que le flux a bien été lu.

IDENTIFIANT DES ALERTES :
Le flux ne donne pas d'identifiant stable (son numéro « n » n'est qu'un rang).
On en fabrique un à partir de la ligne, du titre et de la date de début.

HEURES :
Le flux donne les heures de Lyon ; elles sont converties en UTC, comme
partout dans le projet.

Lancement (essai, sans rien enregistrer) : uv run python -m src.ingestion.fetch_tcl
"""

import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from src.ingestion.fetch_grandlyon import DELAI_ATTENTE_MAX_SECONDES, lire_identifiants

URL_ALERTES_TCL = "https://download.data.grandlyon.com/ws/rdata/tcl_sytral.tclalertetrafic_2/all.json"
FICHIER_JOURNAL = Path("data/reference/tcl_alertes.csv")
DOSSIER_RESUME = Path("data/bronze/tcl_feed")

HEURE_DE_LYON = ZoneInfo("Europe/Paris")

COLONNES_JOURNAL = [
    "alert_id", "mode", "ligne", "type", "cause", "severite", "niveau_severite",
    "titre", "message", "debut_utc", "fin_utc", "premiere_vue", "disparue_le",
]
# Informations qui, si elles changent, mettent à jour la ligne du journal
COLONNES_SUIVIES = ["type", "cause", "severite", "niveau_severite", "titre", "message", "fin_utc"]
COLONNES_RESUME = ["ingestion_timestamp", "nb_alertes", "nb_perturbations", "flux_mis_a_jour_utc"]


def heure_de_lyon_en_utc(texte: str | None) -> str:
    """« 2026-10-21 21:15:00 » (heure de Lyon) → « 2026-10-21 19:15:00+00:00 »."""
    if not texte:
        return ""
    heure = datetime.fromisoformat(texte).replace(tzinfo=HEURE_DE_LYON)
    return str(heure.astimezone(timezone.utc))


def identifiant_alerte(ligne: str, titre: str, debut: str) -> str:
    """Identifiant stable : empreinte courte de (ligne, titre, début)."""
    return hashlib.sha1(f"{ligne}|{titre}|{debut}".encode()).hexdigest()[:12]


def lire_alerte(brute: dict) -> dict:
    """Une alerte du flux → une ligne du journal (sans les dates de suivi)."""
    ligne = brute.get("ligne_com") or ""
    titre = " ".join((brute.get("titre") or "").split())
    debut_utc = heure_de_lyon_en_utc(brute.get("debut"))
    return {
        "alert_id": identifiant_alerte(ligne, titre, debut_utc),
        "mode": brute.get("mode") or "",
        "ligne": ligne,
        "type": brute.get("type") or "",
        "cause": brute.get("cause") or "",
        # NO_SERVICE = ne circule pas ; SIGNIFICANT_DELAYS = perturbé ; OTHER_EFFECT = information
        "severite": brute.get("typeseverite") or "",
        "niveau_severite": str(brute.get("niveauseverite") or ""),
        "titre": titre,
        # Texte complet ramené sur une seule ligne (plus lisible dans un CSV)
        "message": " ".join((brute.get("message") or "").split()),
        "debut_utc": debut_utc,
        "fin_utc": heure_de_lyon_en_utc(brute.get("fin")),
    }


def mettre_a_jour_journal(journal: list[dict], alertes: list[dict], heure_releve: str) -> int:
    """
    Reporter dans le journal les alertes du relevé (modifie « journal » sur place).
      - alerte nouvelle            → ajoutée, premiere_vue = heure du relevé,
      - alerte connue et publiée   → infos mises à jour si elles ont changé,
                                     disparue_le vidé si elle était revenue,
      - alerte absente du relevé   → disparue_le = heure du relevé.
    Renvoie le nombre de lignes ajoutées ou modifiées.
    """
    publiees = {alerte["alert_id"]: alerte for alerte in alertes}
    connues = {ligne["alert_id"]: ligne for ligne in journal}
    nb_changements = 0
    for alert_id, alerte in publiees.items():
        ligne = connues.get(alert_id)
        if ligne is None:
            journal.append({**alerte, "premiere_vue": heure_releve, "disparue_le": ""})
            nb_changements += 1
            continue
        modifiee = any(ligne.get(colonne) != alerte[colonne] for colonne in COLONNES_SUIVIES)
        if modifiee or ligne.get("disparue_le"):
            ligne.update({colonne: alerte[colonne] for colonne in COLONNES_SUIVIES})
            ligne["disparue_le"] = ""
            nb_changements += 1
    for alert_id, ligne in connues.items():
        if alert_id not in publiees and not ligne.get("disparue_le"):
            ligne["disparue_le"] = heure_releve
            nb_changements += 1
    return nb_changements


def lire_journal(fichier: Path = FICHIER_JOURNAL) -> list[dict]:
    if not fichier.exists():
        return []
    with fichier.open(newline="", encoding="utf-8") as contenu:
        return list(csv.DictReader(contenu))


def ecrire_journal(journal: list[dict], fichier: Path = FICHIER_JOURNAL) -> None:
    """Réécrire le journal, trié par date d'apparition puis identifiant (ordre stable)."""
    fichier.parent.mkdir(parents=True, exist_ok=True)
    journal = sorted(journal, key=lambda ligne: (ligne["premiere_vue"], ligne["alert_id"]))
    with fichier.open("w", newline="", encoding="utf-8") as contenu:
        ecrivain = csv.DictWriter(contenu, fieldnames=COLONNES_JOURNAL, extrasaction="ignore")
        ecrivain.writeheader()
        ecrivain.writerows(journal)


def telecharger_alertes(client: httpx.Client) -> list[dict]:
    """Toutes les alertes en cours, telles que publiées par TCL."""
    reponse = client.get(URL_ALERTES_TCL, params={"maxfeatures": 5000})
    reponse.raise_for_status()
    return reponse.json()["values"]


def collecter_alertes_tcl(heure_releve) -> dict | None:
    """
    Relever les alertes, mettre le journal à jour et renvoyer la ligne de
    résumé du relevé (ou None si aucun compte Grand Lyon n'est configuré).
    """
    identifiants = lire_identifiants()
    if identifiants is None:
        return None
    with httpx.Client(auth=identifiants, timeout=DELAI_ATTENTE_MAX_SECONDES, follow_redirects=True) as client:
        brutes = telecharger_alertes(client)
    # Une même alerte peut être publiée deux fois à l'identique : on la garde une fois
    alertes = list({alerte["alert_id"]: alerte for alerte in map(lire_alerte, brutes)}.values())
    journal = lire_journal()
    nb_changements = mettre_a_jour_journal(journal, alertes, str(heure_releve))
    if nb_changements:
        ecrire_journal(journal)
        print(f"📒 Journal des alertes TCL : {nb_changements} alerte(s) ajoutée(s), modifiée(s) ou terminée(s)")
    mises_a_jour = [brute.get("last_update_fme") for brute in brutes if brute.get("last_update_fme")]
    return {
        "ingestion_timestamp": heure_releve,
        "nb_alertes": len(alertes),
        "nb_perturbations": sum(alerte["severite"] != "OTHER_EFFECT" for alerte in alertes),
        "flux_mis_a_jour_utc": heure_de_lyon_en_utc(max(mises_a_jour)) if mises_a_jour else "",
    }


# Essai : affiche ce qui serait enregistré, sans rien écrire
if __name__ == "__main__":
    with httpx.Client(auth=lire_identifiants(), timeout=DELAI_ATTENTE_MAX_SECONDES, follow_redirects=True) as client:
        alertes = [lire_alerte(brute) for brute in telecharger_alertes(client)]
    print(f"{len(alertes)} alertes, {len({a['alert_id'] for a in alertes})} identifiants distincts")
    for alerte in alertes:
        if alerte["mode"] != "Bus":
            print(f"  {alerte['mode']} {alerte['ligne']} [{alerte['severite']}] {alerte['titre']} "
                  f"({alerte['debut_utc']} → {alerte['fin_utc']})")
