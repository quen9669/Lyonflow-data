"""
TESTS DU JOURNAL DES ALERTES TRAFIC TCL
=======================================
Lancement : uv run pytest
"""

from src.ingestion.fetch_tcl import heure_de_lyon_en_utc, lire_alerte, mettre_a_jour_journal

BRUTE_T1 = {
    "cause": "travaux", "debut": "2026-10-21 21:15:00", "fin": "2026-10-22 01:30:00",
    "ligne_com": "T1", "mode": "Tramway", "niveauseverite": 20, "titre": "Travaux T1  -  21/10",
    "type": "Perturbation", "typeseverite": "SIGNIFICANT_DELAYS", "message": "Ligne\n coupée",
}


def test_heures_de_lyon_converties_en_utc():
    # Heure d'été (UTC+2) puis heure d'hiver (UTC+1)
    assert heure_de_lyon_en_utc("2026-10-21 21:15:00") == "2026-10-21 19:15:00+00:00"
    assert heure_de_lyon_en_utc("2026-11-02 01:30:00") == "2026-11-02 00:30:00+00:00"
    assert heure_de_lyon_en_utc(None) == ""


def test_lecture_d_une_alerte():
    alerte = lire_alerte(BRUTE_T1)
    assert alerte["ligne"] == "T1"
    assert alerte["titre"] == "Travaux T1 - 21/10"
    assert alerte["message"] == "Ligne coupée"
    assert alerte["debut_utc"] == "2026-10-21 19:15:00+00:00"
    # Même alerte relue plus tard → même identifiant
    assert lire_alerte(dict(BRUTE_T1))["alert_id"] == alerte["alert_id"]


def test_journal_apparition_modification_disparition():
    journal = []
    alerte = lire_alerte(BRUTE_T1)
    assert mettre_a_jour_journal(journal, [alerte], "R1") == 1
    assert journal[0]["premiere_vue"] == "R1" and journal[0]["disparue_le"] == ""
    # Relevé identique : rien ne change
    assert mettre_a_jour_journal(journal, [alerte], "R2") == 0
    # Fin repoussée : la ligne est mise à jour, sans changer premiere_vue
    prolongee = lire_alerte({**BRUTE_T1, "fin": "2026-10-23 01:30:00"})
    assert mettre_a_jour_journal(journal, [prolongee], "R3") == 1
    assert journal[0]["fin_utc"] == "2026-10-22 23:30:00+00:00" and journal[0]["premiere_vue"] == "R1"
    # Plus publiée : elle est marquée terminée une seule fois
    assert mettre_a_jour_journal(journal, [], "R4") == 1
    assert mettre_a_jour_journal(journal, [], "R5") == 0
    assert journal[0]["disparue_le"] == "R4"
    # Republiée : de nouveau en cours
    assert mettre_a_jour_journal(journal, [prolongee], "R6") == 1
    assert journal[0]["disparue_le"] == ""
