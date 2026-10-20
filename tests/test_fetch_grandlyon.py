"""
TESTS DE LA COLLECTE DES DONNÉES DE MOBILITÉ DU GRAND LYON
==========================================================
Lancement : uv run pytest
"""

from src.ingestion.fetch_grandlyon import (
    collecter_mobilite_grandlyon,
    extraire_parcs_relais,
    extraire_parkings,
    resumer_trafic,
)


def test_parc_relais_multipoint():
    element = {
        "geometry": {"type": "MultiPoint", "coordinates": [[4.88, 45.72]]},
        "properties": {"id": "PR1", "nom": "Parilly", "capacite": 500,
                       "nb_tot_place_dispo": 120, "last_update": "2026-10-20T09:00:00"},
    }
    assert extraire_parcs_relais([element]) == [{
        "parc_id": "PR1", "parc_name": "Parilly", "lat": 45.72, "lon": 4.88,
        "capacity": 500, "available_places_raw": 120, "last_update_api": "2026-10-20T09:00:00",
    }]


def test_parking_sans_geometrie():
    element = {"geometry": None, "properties": {"id": "P1", "nom": "Bellecour", "nb_places": 300,
                                                "places_disponibles": 12, "etat": "OUVERT"}}
    ligne = extraire_parkings([element])[0]
    assert (ligne["lat"], ligne["available_places_raw"], ligne["status_raw"]) == (None, 12, "OUVERT")


def test_resume_trafic_ignore_les_troncons_pas_a_jour():
    elements = [
        {"properties": {"etat": "V", "longueur": 100, "est_a_jour": True}},
        {"properties": {"etat": "V", "longueur": 50, "est_a_jour": True}},
        {"properties": {"etat": "R", "longueur": 200, "est_a_jour": True}},
        {"properties": {"etat": "R", "longueur": 999, "est_a_jour": False}},
        {"properties": {"etat": None, "longueur": None, "est_a_jour": None}},
    ]
    assert resumer_trafic(elements) == [
        {"traffic_status_raw": "INCONNU", "nb_segments": 1, "total_length_m": 0},
        {"traffic_status_raw": "R", "nb_segments": 1, "total_length_m": 200},
        {"traffic_status_raw": "V", "nb_segments": 2, "total_length_m": 150},
    ]


def test_sans_compte_rien_n_est_collecte(monkeypatch):
    monkeypatch.delenv("GRANDLYON_LOGIN", raising=False)
    monkeypatch.delenv("GRANDLYON_PASSWORD", raising=False)
    assert collecter_mobilite_grandlyon() is None
