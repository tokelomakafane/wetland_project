# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run development server
python manage.py runserver

# Apply migrations
python manage.py migrate

# Create migrations after model changes
python manage.py makemigrations

# Run tests
python manage.py test

# Run tests for a single app
python manage.py test mapping
python manage.py test drone
python manage.py test early_warning
python manage.py test wetlands
python manage.py test timelapse

# Open Django shell
python manage.py shell

# Collect static files
python manage.py collectstatic
```

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | random fallback | Django secret key |
| `EE_PROJECT` | `tokelo-329815` | Primary Earth Engine project ID |
| `EE_FALLBACK_PROJECT` | `crypto-analogy-444606-s2` | Fallback if primary EE project is denied |
| `EE_SERVICE_ACCOUNT_KEY` | none (uses cached credentials) | Path to service account JSON for EE auth |

No `.env` file is required for local dev — Earth Engine uses cached credentials (`earthengine authenticate`) by default.

## Architecture

This is a Django 4.2+ wetland monitoring platform for Lesotho that pulls satellite imagery via the Google Earth Engine Python API to track vegetation health, erosion, and land surface temperature across registered wetland sites.

### Apps

| App | Responsibility |
|---|---|
| `mapping` | Core GIS views, Earth Engine integration, RUSLE erosion model, LST monitoring, tile endpoints |
| `wetlands` | Wetland CRUD (draw polygon, bulk upload), health dashboards, per-wetland API endpoints |
| `drone` | Drone PNG upload, EXIF geotag parsing, pixel-level vegetation analysis, wetland state inference |
| `early_warning` | Rule-based composite alert scoring across all wetlands and monitoring records |
| `timelapse` | Async GIF generation using EE; job lifecycle tracked in `TimelapseJob` model |

### Key Design Decisions

**No spatial database** — Wetland geometries are stored as raw GeoJSON strings in a plain `TextField`. There are no PostGIS/spatial queries; all geometric operations happen client-side or in Earth Engine.

**Lightweight async** — Timelapse GIF jobs run in daemon threads (`threading.Thread(daemon=True)`), not Celery. Job state is tracked in the `TimelapseJob` model (pending → running → completed/failed).

**Earth Engine initialization** — `mapping/ee_utils.py` initializes EE once per process. On a permission error it automatically retries with `EE_FALLBACK_PROJECT`. Views that call EE should import from `ee_utils` rather than calling `ee.Initialize()` directly.

**Session-based alert read state** — Unread/read status for early warning alerts is stored in `request.session`, not in the database. The session key is `SESSION_READ_ALERTS_KEY` in `early_warning/views.py`.

**Context processor** — `mapping.context_processors.early_warning_alert_count` injects `unread_alert_count` into every template context so the nav badge stays current without a separate API call.

### Data Models (all in `mapping/models.py`)

- **`Wetland`** — polygon registry; geometry stored as GeoJSON string; tracks `area_ha`, `status`, `risk_level`, `source`, `version`, and a JSONField `metadata` for flexible properties.
- **`WetlandMonitoringRecord`** — annual/seasonal time-series metrics (NDVI, BSI, slope, erosion risk) linked to a `Wetland`.
- **`WetlandBoundaryChange`** — full edit history with old/new geometry and `change_reason`; supports rollback.
- **`TimelapseJob`** — tracks async GIF jobs: frame URLs, gif path, progress %, error messages.

### Earth Engine Data Sources

| Dataset | GEE ID | Used For |
|---|---|---|
| Sentinel-2 SR | `COPERNICUS/S2_SR_HARMONIZED` | NDVI, BSI, vegetation indices |
| Landsat 8 TOA | `LANDSAT/LC08/C02/T1_TOA` | Land Surface Temperature (thermal band) |
| SRTM DEM | `USGS/SRTMGL1_003` | LS factor in RUSLE erosion model |
| CHIRPS | `UCSB-CHG/CHIRPS/DAILY` | Rainfall erosivity (R factor) |
| OpenLandMap soil | — | K factor (soil erodibility) |
| FAO GAUL | — | Country boundary for Lesotho |

The custom EE asset `projects/tokelo-329815/assets/Lesotho_Wetland_Classification_2013_2023` holds the historical wetland classification raster used for tile overlays.

### RUSLE Erosion Model

Soil loss is calculated as **A = R × K × LS × C × P** inside `mapping/views.py`:
- `_get_r_factor()` — CHIRPS rainfall erosivity
- `_get_rusle_factors()` — static LS, K, P factors from DEM and soil layers
- `_get_c_factor()` — vegetation cover from NDVI
- `_get_erosion_for_year()` — assembles the full product for a given year

### Early Warning Scoring

`early_warning/views.py::_build_early_warning_alerts()` iterates all wetlands and their monitoring records, comparing consecutive years. Composite score thresholds:

| Metric | Warning threshold | Critical threshold |
|---|---|---|
| NDVI decline | ≥ 20% | ≥ 35% |
| BSI (bare soil index) | ≥ 0.18 | ≥ 0.25 |
| BSI year-on-year increase | ≥ 20% | — |
| LST (°C) | ≥ 26 °C | ≥ 30 °C |
| LST increase | ≥ 2 °C | — |
| Erosion risk score | ≥ 1.5 | — |

Severity is `critical` if any critical rule fires or 2+ warning rules fire; `warning` if 1 warning rule; `info` otherwise.

### URL Structure

Root `urls.py` includes four URL namespaces that partially overlap at `/`:
```
/admin/                  → Django admin
/                        → mapping.urls  (login, dashboard, monitoring pages, EE APIs)
/drone/                  → drone.urls
/                        → wetlands.urls (wetland CRUD, per-wetland APIs)
/                        → timelapse.urls
```
Static wetland seeds (`wetland_polygons.json`, 23 pre-defined sites) are loaded by `wetlands/views.py::_seed_static_wetlands_into_db()` on first access.
