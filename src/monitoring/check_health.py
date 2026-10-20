"""
CONTRÔLE DE SANTÉ DES FLUX (lancé toutes les heures par GitHub)
================================================================

POURQUOI :
Le robot continue de tourner quand une seule source tombe en panne : si l'API
des parkings ne répond plus, les Vélo'v et la météo sont toujours relevés, et
rien ne se voit dans GitHub. Ce contrôle regarde chaque flux séparément.

CE QU'IL VÉRIFIE, POUR CHAQUE FLUX :
  - l'heure du dernier relevé enregistré : trop ancienne = « EN RETARD » ;
  - le nombre de lignes de ce dernier relevé : trop faible = « INCOMPLET »
    (par exemple 12 stations Vélo'v au lieu de 467) ;
  - pour Vélo'v, l'heure de mise à jour annoncée par l'opérateur : si elle
    n'avance plus, les données sont « FIGÉES » même si on les relève bien.

CE QU'IL FAIT :
  - il écrit un tableau lisible dans le résumé du passage GitHub (onglet Actions) ;
  - s'il trouve un problème, le passage s'affiche en rouge, et GitHub t'envoie
    alors un e-mail automatiquement. Un e-mail par heure tant que le problème dure.

Lancement : uv run python -m src.monitoring.check_health
"""

import csv
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

DOSSIER_BRONZE = Path("data/bronze")


@dataclass
class Flux:
    nom: str             # nom affiché
    dossier: str         # sous-dossier de data/bronze
    retard_max: timedelta
    lignes_min: int      # nombre minimal de lignes attendu dans un relevé
    role: str            # à quoi sert ce flux (pour le métier)


# Les flux du quart d'heure ont droit à 30 minutes (un relevé manqué passe,
# deux d'affilée déclenchent l'alerte). Les événements et la pollution sont
# relevés à chaque démarrage de passage, environ toutes les 5h30 : 7 heures.
# Le programme des grandes salles est relevé une fois par semaine : 8 jours.
FLUX = [
    Flux("Vélo'v", "velov", timedelta(minutes=30), 400, "vélos et places de chaque station"),
    Flux("Météo", "weather", timedelta(minutes=30), 1, "pluie, température, vent"),
    Flux("Flux GBFS", "feed", timedelta(minutes=30), 1, "fraîcheur des données Vélo'v"),
    Flux("Parcs relais TCL", "park_and_ride", timedelta(minutes=30), 10, "remplissage des P+R"),
    Flux("Parkings", "parking", timedelta(minutes=30), 30, "remplissage des parkings de la ville"),
    Flux("Trafic routier", "traffic", timedelta(minutes=30), 1, "part du réseau chargé"),
    Flux("Alertes TCL", "tcl_feed", timedelta(minutes=30), 1, "travaux, déviations et coupures du réseau TCL"),
    Flux("Événements", "events", timedelta(hours=7), 1, "concerts, matchs, soirées à venir"),
    Flux("Pollution", "air_quality", timedelta(hours=7), 1, "vigilance et dépassements de seuil"),
    # Relevé chaque lundi : 8 jours laissent une marge d'une journée
    Flux("Grandes salles", "events_salles", timedelta(days=8), 20, "matchs OL, LOU, ASVEL et concerts des grandes salles"),
]

# Au-delà, l'heure annoncée par l'opérateur Vélo'v est jugée figée
RETARD_MAX_OPERATEUR = timedelta(minutes=30)


def lire_heure(texte: str) -> datetime:
    """Lire une heure enregistrée par le robot (toujours en UTC)."""
    return datetime.fromisoformat(texte.strip())


def dernier_releve(dossier: Path) -> tuple[datetime | None, list[dict]]:
    """Heure et lignes du dernier relevé du flux (fichiers du jour, puis de la veille…)."""
    for fichier in sorted(dossier.glob("*.csv"), reverse=True):
        with fichier.open(encoding="utf-8", newline="") as f:
            lignes = list(csv.DictReader(f))
        if lignes:
            heure = max(lire_heure(l["ingestion_timestamp"]) for l in lignes)
            return heure, [l for l in lignes if lire_heure(l["ingestion_timestamp"]) == heure]
    return None, []


def controler_flux(flux: Flux, dossier_bronze: Path, maintenant: datetime) -> dict:
    """Diagnostiquer un flux : état, heure du dernier relevé, retard, lignes, explication."""
    heure, lignes = dernier_releve(dossier_bronze / flux.dossier)
    resultat = {"flux": flux.nom, "role": flux.role, "dernier_releve": heure,
                "retard_min": None, "lignes": len(lignes)}
    if heure is None:
        return {**resultat, "etat": "ABSENT", "explication": "aucun relevé enregistré"}

    retard = maintenant - heure
    resultat["retard_min"] = int(retard.total_seconds() // 60)
    if retard > flux.retard_max:
        return {**resultat, "etat": "EN RETARD",
                "explication": f"dernier relevé il y a {resultat['retard_min']} min "
                               f"(maximum {int(flux.retard_max.total_seconds() // 60)} min)"}
    if len(lignes) < flux.lignes_min:
        return {**resultat, "etat": "INCOMPLET",
                "explication": f"{len(lignes)} lignes au lieu d'au moins {flux.lignes_min}"}

    if flux.dossier == "velov":
        annonces = [lire_heure(l["last_update_api"]) for l in lignes if l.get("last_update_api")]
        # L'heure par station n'est pas fiable (une station calme ne se signale pas) :
        # on regarde la station la plus récente.
        if annonces and heure - max(annonces) > RETARD_MAX_OPERATEUR:
            return {**resultat, "etat": "FIGÉ",
                    "explication": "l'opérateur n'a mis à jour aucune station depuis "
                                   f"{int((heure - max(annonces)).total_seconds() // 60)} min"}
    return {**resultat, "etat": "OK", "explication": ""}


def controler_tout(dossier_bronze: Path = DOSSIER_BRONZE, maintenant: datetime | None = None) -> list[dict]:
    """Diagnostiquer tous les flux."""
    maintenant = maintenant or datetime.now(timezone.utc)
    return [controler_flux(flux, dossier_bronze, maintenant) for flux in FLUX]


def tableau_markdown(resultats: list[dict]) -> str:
    """Tableau lisible pour le résumé du passage GitHub."""
    pictos = {"OK": "🟢", "EN RETARD": "🔴", "ABSENT": "🔴", "INCOMPLET": "🟠", "FIGÉ": "🟠"}
    lignes = ["| | Flux | Sert à | Dernier relevé (UTC) | Lignes | Problème |",
              "|---|---|---|---|---|---|"]
    for r in resultats:
        heure = r["dernier_releve"].strftime("%d/%m %H:%M") if r["dernier_releve"] else "jamais"
        lignes.append(f"| {pictos[r['etat']]} | {r['flux']} | {r['role']} | {heure} "
                      f"| {r['lignes']} | {r['explication']} |")
    return "\n".join(lignes)


if __name__ == "__main__":
    resultats = controler_tout()
    tableau = tableau_markdown(resultats)
    print(tableau)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("## Santé des flux\n\n" + tableau + "\n")
    problemes = [r for r in resultats if r["etat"] != "OK"]
    if problemes:
        print(f"\n{len(problemes)} flux en difficulté : "
              + ", ".join(f"{r['flux']} ({r['etat']})" for r in problemes))
        sys.exit(1)
    print("\nTous les flux sont à jour.")
