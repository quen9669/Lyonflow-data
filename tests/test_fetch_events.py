"""
TESTS DE LA COLLECTE DES ÉVÉNEMENTS ET DE LA POLLUTION
======================================================
Lancement : uv run pytest
"""

from src.ingestion.fetch_events import extraire_evenements_ticketmaster, extraire_indices_atmo

REPONSE_TICKETMASTER = {
    "_embedded": {"events": [
        {
            "id": "G5abc",
            "name": "Concert test",
            "dates": {
                "start": {"localDate": "2026-11-05", "localTime": "20:00:00", "dateTime": "2026-11-05T19:00:00Z"},
                "status": {"code": "onsale"},
            },
            "classifications": [{"segment": {"name": "Music"}, "genre": {"name": "Rock"}}],
            "_embedded": {"venues": [
                {"id": "KovZ1", "name": "Le Transbordeur", "location": {"latitude": "45.7835", "longitude": "4.8603"}}
            ]},
        },
        {"id": "G5sanslieu", "name": "Sans lieu", "dates": {"start": {"localDate": "2026-11-06"}}},
    ]},
    "page": {"totalPages": 1},
}


def test_evenement_ticketmaster_avec_lieu():
    evenements, lieux = extraire_evenements_ticketmaster(REPONSE_TICKETMASTER)
    assert evenements[0] == {
        "source": "ticketmaster", "event_id": "tm:G5abc", "venue_id": "tm:KovZ1",
        "event_name": "Concert test", "category": "Music", "genre": "Rock",
        "start_utc": "2026-11-05T19:00:00Z", "start_local": "2026-11-05 20:00:00", "status": "onsale",
    }
    assert lieux == [{"venue_id": "tm:KovZ1", "venue_name": "Le Transbordeur", "lat": "45.7835", "lon": "4.8603"}]


def test_evenement_sans_lieu_garde_mais_sans_lieu():
    evenements, lieux = extraire_evenements_ticketmaster(REPONSE_TICKETMASTER)
    assert evenements[1]["venue_id"] == "" and evenements[1]["start_local"] == "2026-11-06"
    assert len(lieux) == 1


def test_indice_atmo():
    reponse = {"features": [{"properties": {
        "date_ech": "2026-10-20", "lib_zone": "Lyon", "code_qual": 2, "lib_qual": "Moyen"}}]}
    assert extraire_indices_atmo(reponse) == [{
        "type": "indice", "date_echeance": "2026-10-20", "zone": "Lyon",
        "polluant": "", "indice": 2, "niveau": "Moyen",
    }]
