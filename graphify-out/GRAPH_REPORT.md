# Graph Report - lyonflow-data  (2026-11-06)

## Corpus Check
- 39 files · ~16,841 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 3, .lock 1)

## Summary
- 423 nodes · 693 edges · 25 communities (19 shown, 6 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 10 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `01b7ddaf`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- fetch_venues.py
- controler_flux
- steps
- fetch_events.py
- fetch_grandlyon.py
- csv
- fetch_tcl.py
- steps
- test_collect_bronze.py
- steps
- steps
- httpx
- collect_bronze.py
- health_check.yml
- steps
- test_venues.yml
- collect_loop.py
- fetch_school_holidays.py
- datetime
- lyonflow-data
- CLAUDE.md
- lyonflow-data

## God Nodes (most connected - your core abstractions)
1. `controler_flux()` - 18 edges
2. `collecter_et_sauvegarder()` - 13 edges
3. `collecter_mobilite_grandlyon()` - 12 edges
4. `collecter_alertes_tcl()` - 12 edges
5. `appliquer_releve()` - 12 edges
6. `collecter_salles()` - 11 edges
7. `mettre_a_jour_fichier()` - 11 edges
8. `collecter_pollution()` - 9 edges
9. `nettoyer()` - 9 edges
10. `ligne()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `test_colonne_ajoutee_en_cours_de_journee()` --calls--> `ajouter_au_fichier_du_jour()`  [EXTRACTED]
  tests/test_collect_bronze.py → src/ingestion/collect_bronze.py
- `test_meteo_enregistree_meme_si_velov_en_panne()` --calls--> `collecter_et_sauvegarder()`  [EXTRACTED]
  tests/test_collect_bronze.py → src/ingestion/collect_bronze.py
- `test_seances_a_lyon_dans_la_periode()` --calls--> `extraire_evenements_openagenda()`  [EXTRACTED]
  tests/test_fetch_events.py → src/ingestion/fetch_events.py
- `test_parc_relais_multipoint()` --calls--> `extraire_parcs_relais()`  [EXTRACTED]
  tests/test_fetch_grandlyon.py → src/ingestion/fetch_grandlyon.py
- `test_parking_sans_geometrie()` --calls--> `extraire_parkings()`  [EXTRACTED]
  tests/test_fetch_grandlyon.py → src/ingestion/fetch_grandlyon.py

## Import Cycles
- None detected.

## Communities (25 total, 6 thin omitted)

### Community 0 - "fetch_venues.py"
Cohesion: 0.08
Nodes (27): collecter_salles(), halle_tony_garnier(), jambase(), ldlc_arena(), lou(), matchs_ol(), ol_vallee(), evenements_json_ld() (+19 more)

### Community 1 - "controler_flux"
Cohesion: 0.12
Nodes (17): controler_flux(), controler_tout(), dernier_releve(), Flux, lire_heure(), releve_precedent(), stations_qui_bougent(), tableau_markdown() (+9 more)

### Community 2 - "steps"
Cohesion: 0.07
Nodes (31): if, needs, runs-on, steps, timeout-minutes, GH_TOKEN, GRANDLYON_LOGIN, GRANDLYON_PASSWORD (+23 more)

### Community 3 - "fetch_events.py"
Cohesion: 0.11
Nodes (12): ajouter_au_fichier_du_jour(), collecter_evenements_et_pollution(), collecter_openagenda(), collecter_pollution(), distance_km(), extraire_depassements(), extraire_evenements_openagenda(), extraire_vigilance() (+4 more)

### Community 4 - "fetch_grandlyon.py"
Cohesion: 0.11
Nodes (11): collecter_mobilite_grandlyon(), coordonnees(), extraire_parcs_relais(), extraire_parkings(), lire_identifiants(), resumer_trafic(), telecharger_couche(), test_parc_relais_multipoint() (+3 more)

### Community 5 - "csv"
Cohesion: 0.14
Nodes (12): migrer_source(), appliquer_releve(), ecrire_referentiel(), lire_referentiel(), mettre_a_jour_fichier(), normaliser(), station(), test_altitude_enfin_connue_complete_la_version_en_cours() (+4 more)

### Community 6 - "fetch_tcl.py"
Cohesion: 0.14
Nodes (11): collecter_alertes_tcl(), ecrire_journal(), heure_de_lyon_en_utc(), identifiant_alerte(), lire_alerte(), lire_journal(), mettre_a_jour_journal(), telecharger_alertes() (+3 more)

### Community 7 - "steps"
Cohesion: 0.11
Nodes (18): jobs, salles, name, on, schedule, workflow_dispatch, permissions, contents (+10 more)

### Community 8 - "test_collect_bronze.py"
Cohesion: 0.14
Nodes (9): collecter_velov_avec_essais(), compter_par_type(), sans_pause(), test_colonne_ajoutee_en_cours_de_journee(), test_meteo_enregistree_meme_si_velov_en_panne(), test_velos_electriques_et_mecaniques(), test_velov_abandonne_apres_trois_essais(), test_velov_reussit_au_deuxieme_essai() (+1 more)

### Community 9 - "steps"
Cohesion: 0.12
Nodes (16): GRANDLYON_LOGIN, GRANDLYON_PASSWORD, jobs, test, name, on, workflow_dispatch, permissions (+8 more)

### Community 10 - "steps"
Cohesion: 0.12
Nodes (16): GRANDLYON_LOGIN, GRANDLYON_PASSWORD, jobs, test, name, on, workflow_dispatch, permissions (+8 more)

### Community 11 - "httpx"
Cohesion: 0.18
Nodes (5): collecter_altitudes_stations(), sauvegarder_altitudes(), collecter_etat_stations(), convertir_date_api(), telecharger_json()

### Community 12 - "collect_bronze.py"
Cohesion: 0.18
Nodes (7): ajouter_au_fichier_du_jour(), collecter_et_sauvegarder(), enregistrer_meteo(), lire_altitudes(), lire_meteo_sans_bloquer(), mettre_a_jour_referentiel(), collecter_meteo_actuelle()

### Community 13 - "health_check.yml"
Cohesion: 0.12
Nodes (15): runs-on, steps, timeout-minutes, jobs, controle, name, on, schedule (+7 more)

### Community 14 - "steps"
Cohesion: 0.12
Nodes (15): OPENAGENDA_API_KEY, jobs, test, name, on, workflow_dispatch, permissions, contents (+7 more)

### Community 15 - "test_venues.yml"
Cohesion: 0.14
Nodes (13): jobs, test, name, on, workflow_dispatch, permissions, contents, name (+5 more)

### Community 16 - "collect_loop.py"
Cohesion: 0.26
Nodes (3): enregistrer_sur_github(), lancer_boucle(), prochain_quart_d_heure()

### Community 17 - "fetch_school_holidays.py"
Cohesion: 0.27
Nodes (5): mettre_a_jour_calendrier(), selectionner_vacances_lyon(), test_garde_lyon_et_ignore_les_autres_academies(), test_ignore_les_dates_propres_aux_enseignants_et_les_doublons(), test_trie_les_periodes_par_date()

### Community 19 - "lyonflow-data"
Cohesion: 0.40
Nodes (4): Contenu, Lancer une collecte à la main, lyonflow-data, Surveillance

## Knowledge Gaps
- **1 isolated node(s):** `lyonflow-data`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 198 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `collecter_mobilite_grandlyon()` connect `fetch_grandlyon.py` to `httpx`, `collect_bronze.py`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **What connects `lyonflow-data` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `fetch_venues.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08081632653061224 - nodes in this community are weakly interconnected._
- **Why does `collecter_salles()` connect `fetch_venues.py` to `httpx`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Should `controler_flux` be split into smaller, more focused modules?**
  _Cohesion score 0.12298387096774194 - nodes in this community are weakly interconnected._
- **Why does `mettre_a_jour_fichier()` connect `csv` to `fetch_venues.py`, `fetch_events.py`, `collect_bronze.py`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Should `steps` be split into smaller, more focused modules?**
  _Cohesion score 0.06854838709677419 - nodes in this community are weakly interconnected._