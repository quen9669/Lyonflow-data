"""
TESTS DU CONTRÔLE DE SANTÉ DES FLUX
===================================
Lancement : uv run --with pytest pytest
"""

from datetime import datetime, timezone

from src.monitoring.check_health import FLUX, controler_flux

MAINTENANT = datetime(2026, 10, 20, 15, 10, tzinfo=timezone.utc)
VELOV = next(f for f in FLUX if f.dossier == "velov")
METEO = next(f for f in FLUX if f.dossier == "weather")


def ecrire_velov(dossier, heure, nb_stations, annonce):
    (dossier / "velov").mkdir(parents=True, exist_ok=True)
    lignes = ["ingestion_timestamp,station_id,last_update_api"]
    lignes += [f"{heure},{i},{annonce}" for i in range(nb_stations)]
    (dossier / "velov" / "2026-10-20.csv").write_text("\n".join(lignes) + "\n", encoding="utf-8")


def test_flux_a_jour(tmp_path):
    ecrire_velov(tmp_path, "2026-10-20 15:00:00+00:00", 467, "2026-10-20 14:59:00+00:00")
    assert controler_flux(VELOV, tmp_path, MAINTENANT)["etat"] == "OK"


def test_flux_en_retard(tmp_path):
    ecrire_velov(tmp_path, "2026-10-20 14:15:00+00:00", 467, "2026-10-20 14:14:00+00:00")
    resultat = controler_flux(VELOV, tmp_path, MAINTENANT)
    assert resultat["etat"] == "EN RETARD"
    assert resultat["retard_min"] == 55


def test_releve_incomplet(tmp_path):
    ecrire_velov(tmp_path, "2026-10-20 15:00:00+00:00", 12, "2026-10-20 14:59:00+00:00")
    assert controler_flux(VELOV, tmp_path, MAINTENANT)["etat"] == "INCOMPLET"


def test_donnees_figees_chez_l_operateur(tmp_path):
    ecrire_velov(tmp_path, "2026-10-20 15:00:00+00:00", 467, "2026-10-20 13:00:00+00:00")
    assert controler_flux(VELOV, tmp_path, MAINTENANT)["etat"] == "FIGÉ"


def test_flux_jamais_releve(tmp_path):
    assert controler_flux(METEO, tmp_path, MAINTENANT)["etat"] == "ABSENT"
