# Lesotho Wetland Monitoring System

A web-based platform for monitoring, mapping, and managing wetland ecosystems across Lesotho. Built with Django and Google Earth Engine, the system provides real-time spectral health analysis, early warning alerts, drone image integration, and community field reporting through a role-based multi-user interface.

**Live:** [https://thuto.co.ls](https://thuto.co.ls)

---

## Features

### Wetland Health Monitoring
- Computes **NDVI**, **MNDWI**, **NDMI**, and **BSI** spectral indices from Sentinel-2 imagery via Google Earth Engine
- Scores each wetland as **Healthy**, **Fair**, or **Degraded** based on multi-metric thresholds
- Interactive Leaflet map with colour-coded markers updated after each EE assessment

### Early Warning System
- Rule-based alert engine triggers warnings when spectral indices cross critical thresholds
- Alerts classified by severity: **Critical**, **Warning**, **Info**, **Resolved**
- Unread badge count in sidebar; mark-as-read per alert

### Wetland Registry
- Add, edit, and delete wetland sites with GPS coordinates and geometry
- Bulk upload via CSV
- Per-wetland monitoring history and boundary change tracking

### LST & Soil Erosion Analysis
- Land Surface Temperature monitoring from Sentinel-3 / Landsat
- RUSLE-based soil erosion risk model (R × K × LS × C × P factors)

### Timelapse
- Generate and export animated GIF timelapses of wetland change over user-defined date ranges
- Download per-wetland timelapse exports

### Drone Image Upload
- Upload drone imagery with automatic GPS extraction
- Image preprocessing and wetland-site matching
- State inference overlay on matched wetland

### Community Field Reporting
- Community members submit field observations (grazing, erosion, invasive species)
- Severity rating per report; each member sees only their own submissions

### User Management
- Five roles with distinct access levels
- System Admin can create and delete users from within the app

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 4.2, Python 3.10+ |
| Remote Sensing | Google Earth Engine Python API |
| Database | SQLite (development / small-scale production) |
| Mapping | Leaflet.js |
| Image Processing | Pillow |
| Frontend | Vanilla JS, CSS Grid/Flexbox |
| Web Server | Nginx + Gunicorn |
| CDN / SSL | Cloudflare |

---

## Roles & Access

| Role | Monitoring Dashboards | Data Upload | User Management | Field Reports |
|---|:---:|:---:|:---:|:---:|
| System Admin | Yes | Yes | Yes | — |
| DOE Officer | Yes | Yes | — | — |
| DMA Officer | Yes | Yes | — | — |
| NUL Researcher | Yes | — | — | — |
| Community Member | — | — | — | Yes |

---

## Project Structure

```
wetland_project/
├── mapping/          # Core app — dashboard, monitor, alerts, community inputs, users
│   ├── ee_utils.py   # Google Earth Engine helpers
│   ├── middleware.py # Login-required middleware
│   └── context_processors.py
├── wetlands/         # Wetland registry, erosion analysis, prediction
├── drone/            # Drone image upload and analysis
├── early_warning/    # Alert engine and API
├── timelapse/        # Timelapse generation and export
├── users/            # UserProfile model and role definitions
└── wetland_project/  # Django settings and URL root
```

---

## Local Development

```bash
git clone https://github.com/tokelomakafane/wetland_project.git
cd wetland_project

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_users     # creates default accounts (see below)
python manage.py runserver
```

Authenticate with Google Earth Engine (first run only):
```bash
earthengine authenticate
```

### Default Accounts

| Username | Password | Role |
|---|---|---|
| `admin` | `admin` | System Admin |
| `doe_officer` | `doe123` | DOE Officer |
| `dma_officer` | `dma123` | DMA Officer |
| `nul_researcher` | `nul123` | NUL Researcher |
| `community` | `community123` | Community Member |

---

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full guide covering Digital Ocean, Nginx, Gunicorn, and Cloudflare SSL configuration for `thuto.co.ls`.

---

## Spectral Indices Reference

| Index | Formula | Indicates |
|---|---|---|
| NDVI | (B8 − B4) / (B8 + B4) | Vegetation greenness |
| MNDWI | (B3 − B11) / (B3 + B11) | Water content / wetness |
| NDMI | (B8 − B11) / (B8 + B11) | Moisture in vegetation |
| BSI | ((B11+B4) − (B8+B2)) / ((B11+B4) + (B8+B2)) | Bare soil exposure |

Sentinel-2 bands: B2=Blue, B3=Green, B4=Red, B8=NIR, B11=SWIR1

---

## License

Academic / research use. Contact the National University of Lesotho or the Department of Environment for usage permissions.
