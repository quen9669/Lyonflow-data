"""
TESTS DE LA MÉTÉO PRÉVUE
========================
On simule la réponse d'Open-Meteo (aucun appel réseau) et on vérifie que
les colonnes renvoyées par l'API deviennent bien une ligne par quart d'heure.
Lancement : uv run --with pytest pytest
"""

from datetime import datetime, timezone

import httpx

from src.ingestion import fetch_weather

REPONSE_API = {
    "minutely_15": {
        "time": ["2026-10-22T19:15", "2026-10-22T19:30"],
        "temperature_2m": [12.0, 11.8],
        "precipitation": [0.0, 0.4],
        "rain": [0.0, 0.4],
        "wind_speed_10m": [4.0, 5.1],
    }
}


def test_meteo_prevue_une_ligne_par_quart_d_heure(monkeypatch):
    def repondre(requete):
        assert requete.url.params["forecast_minutely_15"] == str(fetch_weather.NB_QUARTS_HEURE_PREVUS)
        return httpx.Response(200, json=REPONSE_API)

    vrai_client = httpx.Client
    monkeypatch.setattr(fetch_weather.httpx, "Client",
                        lambda **options: vrai_client(transport=httpx.MockTransport(repondre), **options))

    prevues = fetch_weather.collecter_meteo_prevue()

    assert len(prevues) == 2
    assert prevues[1] == {
        "forecast_time_api": datetime(2026, 10, 22, 19, 30, tzinfo=timezone.utc),
        "forecast_temp_c": 11.8,
        "forecast_precipitation_mm": 0.4,
        "forecast_rain_mm": 0.4,
        "forecast_wind_kmh": 5.1,
    }
