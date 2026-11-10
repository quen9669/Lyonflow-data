"""Tests de la boucle de collecte : changement de machine après plusieurs échecs."""

from src.ingestion import collect_loop


def preparer(monkeypatch, resultats):
    """Simuler la boucle sans attendre ni toucher à GitHub."""
    appels = []

    def collecte_simulee():
        appels.append(1)
        if not resultats.pop(0):
            raise TimeoutError("timed out")

    monkeypatch.setattr(collect_loop, "collecter_et_sauvegarder", collecte_simulee)
    monkeypatch.setattr(collect_loop, "enregistrer_sur_github", lambda: None)
    monkeypatch.setattr(collect_loop.time, "sleep", lambda secondes: None)
    return appels


def test_trois_echecs_d_affilee_passent_le_relais(monkeypatch):
    appels = preparer(monkeypatch, [True, False, False, False, True, True])
    assert collect_loop.lancer_boucle() == 3
    assert len(appels) == 4  # 1 réussite puis 3 échecs, et on s'arrête


def test_echecs_isoles_ne_coupent_pas_le_passage(monkeypatch):
    # 2 échecs, 1 réussite, 2 échecs, 1 réussite : jamais 3 d'affilée, on continue.
    # Les 3 échecs de la fin servent seulement à arrêter le test.
    appels = preparer(monkeypatch, [False, False, True, False, False, True, False, False, False])
    assert collect_loop.lancer_boucle() == 7
    assert len(appels) == 9
