# lyonflow-data

Relevés de l'état des stations Vélo'v de la Métropole de Lyon et de la météo,
collectés automatiquement tous les quarts d'heure (:00, :15, :30, :45 UTC)
par GitHub Actions.

## Contenu

| Dossier | Contenu |
|---|---|
| `data/bronze/velov/` | Un fichier CSV par jour (UTC) : une ligne par station et par relevé (flux GBFS Vélo'v) |
| `data/bronze/weather/` | Un fichier CSV par jour : la météo à chaque relevé (Open-Meteo, Lyon Bellecour) |
| `data/bronze/feed/` | Un fichier CSV par jour : date de génération du flux GBFS et nombre de stations |
| `data/bronze/park_and_ride/` | Un fichier CSV par jour : places libres de chaque parc relais TCL à chaque relevé |
| `data/bronze/parking/` | Un fichier CSV par jour : places libres de chaque parking de la Métropole à chaque relevé |
| `data/bronze/traffic/` | Un fichier CSV par jour : résumé de l'état du trafic routier à chaque relevé |
| `data/reference/stations_altitude.csv` | Altitude de chaque station (Open-Meteo) |
| `data/reference/velov_stations.csv` | Référentiel des stations Vélo'v : nom, latitude, longitude, altitude |
| `data/reference/parcs_relais.csv` | Référentiel des parcs relais : nom, latitude, longitude |
| `data/reference/parkings.csv` | Référentiel des parkings : nom, latitude, longitude |
| `data/reference/school_holidays.csv` | Vacances scolaires de l'académie de Lyon (Éducation nationale), mises à jour à chaque démarrage du robot |
| `src/ingestion/` | Scripts de collecte |
| `.github/workflows/collect_15min.yml` | Le robot de collecte |

Toutes les tables se relient par la colonne `ingestion_timestamp`.

Les relevés ne contiennent que l'identifiant de chaque station ou parking. Le nom et la position sont rangés une seule fois dans les référentiels, avec une période de validité : `valid_from` (apparition de cette version) et `valid_to` (2099-12-31 tant que rien n'a changé). Si un nom ou une position change, l'ancienne version est fermée et une nouvelle est ouverte : le passé n'est jamais réécrit.

## Lancer une collecte à la main

```bash
uv sync
uv run python -m src.ingestion.collect_bronze
```

Sources : [data.grandlyon.com](https://data.grandlyon.com) (parcs relais TCL, parkings, trafic),
[Calendrier scolaire](https://data.education.gouv.fr/explore/dataset/fr-en-calendrier-scolaire/),
[GBFS Vélo'v](https://download.data.grandlyon.com/files/rdata/jcd_jcdecaux.jcdvelov/gbfs.json),
[Open-Meteo](https://open-meteo.com).
