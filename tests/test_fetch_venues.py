"""
TESTS DE LA COLLECTE DES GRANDES SALLES (extraits de pages réelles, simplifiés)
==============================================================================
Lancement : uv run --with pytest pytest
"""

from src.ingestion.fetch_venues import (
    heure_de_lyon_en_utc, liens_matchs_lou, lire_halle_tony_garnier, lire_jambase, lire_ldlc_arena,
    lire_match_lou, lire_matchs_ol, lire_ol_vallee,
)

PAGE_LDLC = """<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
{"@type":"Event","name":"Saez","startDate":"2026-12-09T20:30:00+02:00","endDate":"2026-12-09T23:59:59+02:00",
 "location":{"@type":"Place","name":"LDLC Arena"}},
{"@type":"Event","name":"LDLC ASVEL / Partizan","startDate":"2026-10-28T20:00:00+02:00"}]}</script>"""

PAGE_OL_VALLEE = """
<a class="event-card__link --large" href="https://billetterie.ol.fr/fr/catalogue/match-ol-angers-sco-1" target="_self">
  <div class="event-card__title">
      OL / ANGERS SCO            </div>
  <div class="event-card__desc">
      31 octobre 2026 - 20:45                </div></a>
<a class="event-card__link" href="https://www.ldlcarena.com/evenement/ldlc-asvel-partizan-octobre-2026/">
  <div class="event-card__title">LDLC ASVEL / Partizan</div>
  <div class="event-card__desc">28 octobre 2026 - 20:00</div></a>"""

PAGE_JAMBASE = """<script type="application/ld+json">[{"@type":"MusicEvent",
"name":"Josman - Lyon - Halle Tony Garnier - Nov 7, 2026","startDate":"2026-11-07T20:00:00"},
{"@type":"MusicEvent","name":"Sans heure","startDate":"2026-11-08"}]</script>"""


def test_heure_affichee_lue_comme_heure_de_lyon_meme_en_hiver():
    # Le site annonce +02:00 en décembre : 20h30 à Lyon = 19h30 UTC (heure d'hiver)
    assert str(heure_de_lyon_en_utc("2026-12-09T20:30:00+02:00")) == "2026-12-09 19:30:00+00:00"
    assert str(heure_de_lyon_en_utc("2026-10-28T20:00:00+02:00")) == "2026-10-28 19:00:00+00:00"


def test_ldlc_arena_concert_et_match():
    lignes = lire_ldlc_arena(PAGE_LDLC)
    assert sorted((l["event_name"], l["category"], l["event_id"]) for l in lignes) == [
        ("LDLC ASVEL / Partizan", "match", "salle:ldlc-arena:202610281900"),
        ("Saez", "spectacle", "salle:ldlc-arena:202612091930"),
    ]
    assert all(l["venue_id"] == "salle:ldlc-arena" and l["source"] == "salles" for l in lignes)


def test_ol_vallee_garde_seulement_les_matchs_de_l_ol():
    lignes = lire_ol_vallee(PAGE_OL_VALLEE)
    assert len(lignes) == 1
    assert lignes[0]["event_name"] == "OL / ANGERS SCO"
    assert lignes[0]["start_utc"] == "2026-10-31 19:45:00+00:00"
    assert lignes[0]["venue_id"] == "salle:groupama-stadium"


def test_jambase_nom_de_l_artiste_et_dates_sans_heure_ignorees():
    lignes = lire_jambase(PAGE_JAMBASE, "halle-tony-garnier")
    assert [(l["event_name"], l["start_utc"]) for l in lignes] == [("Josman", "2026-11-07 19:00:00+00:00")]


def test_lou_match_a_domicile_avec_et_sans_heure():
    accueil = ('<a href="https://www.lourugby.fr/match/lyon-vannes-31-10-2026/">Infos</a>'
               '<a href="https://www.lourugby.fr/match/toulon-lyon-07-11-2026/">Infos</a>')
    assert list(liens_matchs_lou(accueil)) == ["lyon-vannes-31-10-2026"]
    avec_heure = lire_match_lou("lyon-vannes-31-10-2026", "<p>Lyon – Vannes</p><span>31/10/2026 - 16h35</span>")
    assert avec_heure["start_utc"] == "2026-10-31 15:35:00+00:00" and avec_heure["status"] == "programme"
    sans_heure = lire_match_lou("lyon-stade-toulousain-28-11-2026", "<span>28/11/2026</span>")
    assert sans_heure["status"] == "heure_a_confirmer"
    assert sans_heure["event_name"] == "LOU Rugby - Stade Toulousain"


def test_halle_tony_garnier_avec_et_sans_heure():
    page = (
        '<a href="https://www.halle-tony-garnier.com/fr/programmation/josman" class="bloc-square types type_concert">'
        '<div class="bloc-square__title">JOSMAN</div><div class="bloc-square__date"> 07.11.26 </div>'
        '<div class="bloc-square__heure"> 20h00 </div></a>'
        '<a href="https://www.halle-tony-garnier.com/fr/programmation/salon" class="bloc-square types type_salon">'
        '<div class="bloc-square__title">SALON DES VIGNERONS</div><div class="bloc-square__date"> 30.10.26 </div></a>'
    )
    lignes = lire_halle_tony_garnier(page)
    assert [(l["event_name"], l["category"], l["start_utc"], l["status"]) for l in lignes] == [
        ("JOSMAN", "concert", "2026-11-07 19:00:00+00:00", "programme"),
        ("SALON DES VIGNERONS", "salon", "2026-10-30 19:00:00+00:00", "heure_a_confirmer"),
    ]


def test_matchs_ol_a_domicile_avec_heure_fixee():
    matchs = [
        {"HomeTeam": "Lyon", "AwayTeam": "Angers", "DateUtc": "2026-10-31 19:45:00Z"},
        {"HomeTeam": "Paris", "AwayTeam": "Lyon", "DateUtc": "2026-10-25 19:45:00Z"},
        # Minuit à Lyon : heure pas encore fixée
        {"HomeTeam": "Lyon", "AwayTeam": "Monaco", "DateUtc": "2026-11-28 23:00:00Z"},
    ]
    lignes = lire_matchs_ol(matchs, "Ligue 1")
    assert [(l["event_name"], l["event_id"]) for l in lignes] == [
        ("OL - Angers (Ligue 1)", "salle:groupama-stadium:202610311945")]
