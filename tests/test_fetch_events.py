"""
TESTS DE LA COLLECTE DES ÉVÉNEMENTS ET DE LA POLLUTION
======================================================
Lancement : uv run pytest
"""

from datetime import datetime, timezone

from src.ingestion.fetch_events import (
    extraire_depassements,
    extraire_evenements_openagenda,
    extraire_vigilance,
)

DEBUT = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
FIN = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)

EVENEMENTS_OPENAGENDA = [
    {
        "uid": 111, "title": {"fr": "Concert test"}, "status": 1, "keywords": {"fr": ["rock", "live"]},
        "location": {"uid": 9, "name": "Le Transbordeur", "latitude": 45.7835, "longitude": 4.8603},
        "timings": [
            {"begin": "2026-10-25T20:00:00+02:00", "end": "2026-10-25T23:00:00+02:00"},
            {"begin": "2026-12-25T20:00:00+01:00", "end": "2026-12-25T23:00:00+01:00"},  # hors période
        ],
    },
    {   # à Paris : écarté
        "uid": 222, "title": {"fr": "Soirée à Paris"},
        "location": {"uid": 8, "name": "Paris", "latitude": 48.8555, "longitude": 2.2927},
        "timings": [{"begin": "2026-10-25T20:00:00+02:00", "end": "2026-10-25T23:00:00+02:00"}],
    },
]


def test_seances_a_lyon_dans_la_periode():
    seances, lieux = extraire_evenements_openagenda(EVENEMENTS_OPENAGENDA, "Shotgun", DEBUT, FIN)
    assert seances == [{
        "source": "openagenda", "event_id": "oa:111:202610251800", "venue_id": "oa:9",
        "event_name": "Concert test", "category": "Shotgun", "genre": "rock, live",
        "start_utc": "2026-10-25 18:00:00+00:00", "end_utc": "2026-10-25 21:00:00+00:00",
        "status": "programme",
    }]
    assert lieux == [{"venue_id": "oa:9", "venue_name": "Le Transbordeur", "lat": 45.7835, "lon": 4.8603}]


def test_vigilance_et_depassements_de_la_zone_lyonnaise():
    vigilance = [
        {"id_zone": 2003, "lib_court_zone": "Bassin Lyon Nord-Isère", "polluant_id": "",
         "niveau_id": 2, "niveau_vigilance": "Jaune"},
        {"id_zone": 2016, "lib_court_zone": "Zone Alpine Ain", "niveau_id": 1, "niveau_vigilance": "Vert"},
    ]
    assert extraire_vigilance(vigilance, "2026-10-20") == [{
        "type": "vigilance", "date_echeance": "2026-10-20", "zone": "Bassin Lyon Nord-Isère",
        "polluant": "", "indice": 2, "niveau": "Jaune",
    }]
    alertes = [{"code_zone": 2003, "lib_zone": "Bassin Lyon Nord-Isère", "date_ech": "2026-10-21T00:00:00Z",
                "code_pol": "5", "lib_pol": "PM10", "etat": "PAS DE DEPASSEMENT"}]
    assert extraire_depassements(alertes)[0]["date_echeance"] == "2026-10-21"
    assert extraire_depassements(alertes)[0]["niveau"] == "PAS DE DEPASSEMENT"
