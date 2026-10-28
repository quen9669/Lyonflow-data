"""
BOUCLE DE COLLECTE À HEURES FIXES (:00, :15, :30, :45)
=======================================================

POURQUOI CE SCRIPT :
GitHub ne lance pas les tâches programmées à l'heure exacte : la première nuit,
les passages sont arrivés toutes les 20 à 54 minutes au lieu de 15.
La solution retenue (« boucle longue ») : un seul passage GitHub Actions reste
allumé plusieurs heures et déclenche lui-même la collecte pile à chaque
quart d'heure. Quand il s'arrête, il relance lui-même le passage suivant, qui
prend aussitôt le relais.

DÉROULEMENT :
  1. On attend le prochain quart d'heure (par exemple 10h15:00).
  2. On collecte un relevé (collect_bronze.py) et on l'enregistre sur GitHub.
  3. On recommence, jusqu'à atteindre la durée maximale prévue.
Si une collecte échoue (API Vélo'v en panne malgré les nouveaux essais), la boucle
continue au quart d'heure suivant : une panne passagère ne doit pas arrêter tout
l'historique. Ce qui a pu être relevé (la météo) est enregistré quand même.
À la fin, le passage s'affiche en rouge dans GitHub s'il y a eu au moins un échec,
pour que l'on soit prévenu.

Lancement : uv run python -m src.ingestion.collect_loop
"""

import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

from src.ingestion.collect_bronze import collecter_et_sauvegarder

# Intervalle entre deux collectes
INTERVALLE = timedelta(minutes=15)

# Durée de vie d'un passage. GitHub coupe tout passage au bout de 6 heures :
# on s'arrête avant, pour que le passage se termine proprement.
DUREE_MAX = timedelta(hours=5, minutes=30)


def prochain_quart_d_heure(maintenant: datetime) -> datetime:
    """
    Calculer l'heure du prochain quart d'heure pile.
    Exemples : 10h07 → 10h15 ; 10h15:30 → 10h30 ; 10h59 → 11h00.
    """
    debut_de_l_heure = maintenant.replace(minute=0, second=0, microsecond=0)
    quarts_ecoules = (maintenant - debut_de_l_heure) // INTERVALLE
    return debut_de_l_heure + (quarts_ecoules + 1) * INTERVALLE


def enregistrer_sur_github() -> None:
    """
    Envoyer les nouveaux relevés sur GitHub (équivalent des commandes
    git add / commit / push qu'on taperait à la main).
    Si quelqu'un a modifié le dépôt entre-temps, on récupère d'abord ses
    changements (git pull --rebase), avec jusqu'à 3 tentatives.
    """
    subprocess.run(["git", "add", "data/"], check=True)
    # « git diff --cached --quiet » répond 0 quand il n'y a rien de nouveau
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        print("Aucune nouvelle donnée à enregistrer.")
        return
    message = f"Collecte automatique du {datetime.now(tz=timezone.utc):%Y-%m-%d %H:%M} UTC"
    subprocess.run(["git", "commit", "-q", "-m", message], check=True)
    for tentative in range(3):
        if (
            subprocess.run(["git", "pull", "-q", "--rebase"]).returncode == 0
            and subprocess.run(["git", "push", "-q"]).returncode == 0
        ):
            return
        time.sleep(5)
    raise RuntimeError("Impossible d'envoyer les relevés sur GitHub après 3 tentatives.")


def lancer_boucle() -> int:
    """
    Collecter à chaque quart d'heure jusqu'à la fin de la durée prévue.
    Renvoie le nombre de collectes en échec.
    """
    fin_prevue = datetime.now(tz=timezone.utc) + DUREE_MAX
    nb_echecs = 0

    while True:
        # Étape 1 : On attend le prochain quart d'heure pile
        rendez_vous = prochain_quart_d_heure(datetime.now(tz=timezone.utc))
        if rendez_vous > fin_prevue:
            break
        attente = (rendez_vous - datetime.now(tz=timezone.utc)).total_seconds()
        print(f"Prochaine collecte à {rendez_vous:%H:%M} UTC (attente {attente / 60:.0f} min)")
        time.sleep(max(attente, 0))

        # Étape 2 : On collecte et on enregistre, sans laisser une panne arrêter la boucle.
        # Même si la collecte échoue, on enregistre ce qui a pu être relevé
        # (par exemple la météo quand Vélo'v est en panne).
        try:
            collecter_et_sauvegarder()
        except Exception as erreur:
            nb_echecs += 1
            print(f"❌ Échec de la collecte de {rendez_vous:%H:%M} : {erreur}")
        try:
            enregistrer_sur_github()
        except Exception as erreur:
            nb_echecs += 1
            print(f"❌ Échec de l'enregistrement sur GitHub de {rendez_vous:%H:%M} : {erreur}")

    print(f"Fin du passage. Collectes en échec : {nb_echecs}")
    return nb_echecs


if __name__ == "__main__":
    # Code de sortie 1 = le passage apparaît en rouge dans GitHub Actions
    sys.exit(1 if lancer_boucle() > 0 else 0)
