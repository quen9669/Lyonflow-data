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
| `data/reference/stations_altitude.csv` | Altitude de chaque station (Open-Meteo) |
| `src/ingestion/` | Scripts de collecte |
| `.github/workflows/collect_15min.yml` | Le robot de collecte |

Les trois tables se relient par la colonne `ingestion_timestamp`.

## Lancer une collecte à la main

```bash
uv sync
uv run python -m src.ingestion.collect_bronze
```

Sources : [GBFS Vélo'v](https://download.data.grandlyon.com/files/rdata/jcd_jcdecaux.jcdvelov/gbfs.json),
[Open-Meteo](https://open-meteo.com).
