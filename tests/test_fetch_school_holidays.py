"""
TESTS DU CALENDRIER DES VACANCES SCOLAIRES
==========================================
Lancement : uv run --with pytest pytest
"""

from src.ingestion.fetch_school_holidays import selectionner_vacances_lyon

TOUSSAINT = {
    "description": "Vacances de la Toussaint",
    "population": "-",
    "start_date": "2026-10-16T22:00:00+00:00",
    "end_date": "2026-11-01T23:00:00+00:00",
    "location": "Lyon",
    "zones": "Zone A",
    "annee_scolaire": "2026-2027",
}


def test_garde_lyon_et_ignore_les_autres_academies():
    grenoble = {**TOUSSAINT, "location": "Grenoble"}
    assert selectionner_vacances_lyon([TOUSSAINT, grenoble]) == [
        {
            "annee_scolaire": "2026-2027",
            "description": "Vacances de la Toussaint",
            "start_date": "2026-10-16T22:00:00+00:00",
            "end_date": "2026-11-01T23:00:00+00:00",
        }
    ]


def test_ignore_les_dates_propres_aux_enseignants_et_les_doublons():
    enseignants = {**TOUSSAINT, "population": "Enseignants", "start_date": "2026-10-15T22:00:00+00:00"}
    assert len(selectionner_vacances_lyon([TOUSSAINT, TOUSSAINT, enseignants])) == 1


def test_trie_les_periodes_par_date():
    noel = {**TOUSSAINT, "description": "Vacances de Noël", "start_date": "2026-12-18T23:00:00+00:00"}
    periodes = selectionner_vacances_lyon([noel, TOUSSAINT])
    assert [p["description"] for p in periodes] == ["Vacances de la Toussaint", "Vacances de Noël"]
