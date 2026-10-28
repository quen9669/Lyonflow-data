"""
TESTS DES ESSAIS VÉLO'V ET DE LA MÉTÉO DE SECOURS
=================================================
Après la panne de la nuit du 27 au 28/10/2026 (serveur Vélo'v du Grand Lyon
muet pendant 11h), on vérifie que :
  - Vélo'v est réessayé dans le même quart d'heure avant d'abandonner ;
  - la météo est enregistrée même quand Vélo'v reste injoignable.
On simule les API (aucun appel réseau) et on supprime les pauses.
Lancement : uv run --with pytest pytest
"""

import csv

import httpx
import pytest

from src.ingestion import collect_bronze

METEO = {"weather_time_api": "2026-10-28T02:00", "weather_temp_c": 9.5,
         "weather_precipitation_mm": 0.0, "weather_rain_mm": 0.0, "weather_wind_kmh": 6.0}


@pytest.fixture
def sans_pause(monkeypatch):
    pauses = []
    monkeypatch.setattr(collect_bronze.time, "sleep", pauses.append)
    return pauses


def test_velov_reussit_au_deuxieme_essai(monkeypatch, sans_pause):
    reponses = [httpx.ReadTimeout("timed out"), [{"station_id": "1001"}]]

    def collecter():
        reponse = reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse

    monkeypatch.setattr(collect_bronze, "collecter_etat_stations", collecter)

    assert collect_bronze.collecter_velov_avec_essais() == [{"station_id": "1001"}]
    assert sans_pause == [120]


def test_velov_abandonne_apres_trois_essais(monkeypatch, sans_pause):
    appels = []

    def collecter():
        appels.append(1)
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(collect_bronze, "collecter_etat_stations", collecter)

    with pytest.raises(httpx.ConnectTimeout):
        collect_bronze.collecter_velov_avec_essais()
    assert len(appels) == 3
    assert sans_pause == [120, 180]


def test_meteo_enregistree_meme_si_velov_en_panne(monkeypatch, tmp_path, sans_pause):
    def collecter():
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(collect_bronze, "collecter_etat_stations", collecter)
    monkeypatch.setattr(collect_bronze, "collecter_meteo_actuelle", lambda: dict(METEO))
    monkeypatch.setattr(collect_bronze, "collecter_meteo_prevue", lambda: [])
    monkeypatch.setattr(collect_bronze, "DOSSIER_BRONZE_METEO", tmp_path / "weather")
    monkeypatch.setattr(collect_bronze, "DOSSIER_BRONZE_VELOV", tmp_path / "velov")

    with pytest.raises(httpx.ReadTimeout):
        collect_bronze.collecter_et_sauvegarder()

    fichiers = list((tmp_path / "weather").glob("*.csv"))
    assert len(fichiers) == 1
    with fichiers[0].open(encoding="utf-8") as fichier:
        lignes = list(csv.DictReader(fichier))
    assert len(lignes) == 1 and lignes[0]["weather_temp_c"] == "9.5"
    assert lignes[0]["ingestion_timestamp"]
    assert not (tmp_path / "velov").exists()
