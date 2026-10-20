"""
TESTS DES RÉFÉRENTIELS HISTORISÉS
=================================
Lancement : uv run pytest
"""

from src.ingestion.referentiel import FIN_OUVERTE, appliquer_releve

ATTRIBUTS = ["station_name", "lat", "lon", "altitude_m"]


def station(nom="BELLECOUR", lat=45.757801, lon=4.832, altitude="170.0"):
    return {"station_id": 7, "station_name": nom, "lat": lat, "lon": lon, "altitude_m": altitude}


def test_premiere_version_ouverte_jusqu_en_2099():
    referentiel = []
    assert appliquer_releve(referentiel, "station_id", ATTRIBUTS, [station()], "T1") == 1
    assert referentiel == [{
        "station_id": "7", "station_name": "BELLECOUR", "lat": "45.757801", "lon": "4.832000",
        "altitude_m": "170.0", "valid_from": "T1", "valid_to": FIN_OUVERTE,
    }]


def test_releve_identique_ou_micro_ecart_gps_ne_cree_rien():
    referentiel = []
    appliquer_releve(referentiel, "station_id", ATTRIBUTS, [station()], "T1")
    assert appliquer_releve(referentiel, "station_id", ATTRIBUTS, [station(lat=45.7578010001)], "T2") == 0
    assert len(referentiel) == 1


def test_changement_de_nom_ferme_l_ancienne_version():
    referentiel = []
    appliquer_releve(referentiel, "station_id", ATTRIBUTS, [station()], "T1")
    appliquer_releve(referentiel, "station_id", ATTRIBUTS, [station(nom="BELLECOUR / LOUIS XIV")], "T2")
    assert [(l["station_name"], l["valid_from"], l["valid_to"]) for l in referentiel] == [
        ("BELLECOUR", "T1", "T2"),
        ("BELLECOUR / LOUIS XIV", "T2", FIN_OUVERTE),
    ]


def test_altitude_enfin_connue_complete_la_version_en_cours():
    referentiel = []
    appliquer_releve(referentiel, "station_id", ATTRIBUTS, [station(altitude=None)], "T1")
    assert appliquer_releve(referentiel, "station_id", ATTRIBUTS, [station()], "T2") == 1
    assert len(referentiel) == 1 and referentiel[0]["altitude_m"] == "170.0"


def test_information_absente_d_un_releve_ne_cree_pas_de_version():
    referentiel = []
    appliquer_releve(referentiel, "station_id", ATTRIBUTS, [station()], "T1")
    assert appliquer_releve(referentiel, "station_id", ATTRIBUTS, [station(altitude=None)], "T2") == 0
    assert referentiel[0]["altitude_m"] == "170.0"
