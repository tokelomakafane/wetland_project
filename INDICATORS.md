# Wetland Indicators Reference

## Overview

This document inventories all indicators used to monitor and analyze wetlands in the system. Indicators are grouped into five families: **wetland metadata**, **monitoring record metrics**, **thermal metrics**, **erosion metrics**, and **timelapse spectral series**. Each indicator is mapped to its data source, computation method, storage location, and usage across the dashboard, monitoring pages, alerts, and timelapse views.

---

## 1. Wetland Metadata

Wetland-level fields that describe the identity and overall status of a wetland. These fields persist for the life of the wetland record.

| Indicator | Field | Model | Storage | Input Method | Used By |
|-----------|-------|-------|---------|--------------|---------|
| **Status** | `status` | `Wetland` | Persistent (CharField) | Registry edit modal, manual selection | Registry filter, dashboard badges, alerts context |
| **Risk Level** | `risk_level` | `Wetland` | Persistent (CharField) | Registry edit modal, programmatic assignment | Registry filter/badge, dashboard summaries, comparison logic |
| **Name** | `name` | `Wetland` | Persistent (CharField) | Registry form or bulk import | UI headers, titles, alerts, all reporting surfaces |
| **Village** | `village` | `Wetland` | Persistent (CharField) | Registry form or bulk import | Registry list, alerts, filtering, UI context |
| **Area (hectares)** | `area_ha` | `Wetland` | Persistent (FloatField), calculated on save | Auto-calculated from geometry | Timelapse display, area-change metrics, summaries |
| **Elevation** | `elevation_m` | `Wetland` | Persistent (IntegerField) | Registry edit form | Context display, spatial analysis |
| **Description** | `description` | `Wetland` | Persistent (TextField) | Registry edit form | Registry detail view, context |
| **Metadata (JSON)** | `metadata` | `Wetland` | Persistent (JSONField) | Programmatic assignment (e.g., LST updates) | LST alert logic, flexible extensibility |

**Sources:**
- Defined in [mapping/models.py](mapping/models.py#L10-L120)
- Edited via [wetlands/forms.py](wetlands/forms.py#L7-L60) and registry modal in [mapping/templates/mapping/wetland_registry.html](mapping/templates/mapping/wetland_registry.html)
- Displayed in [mapping/templates/mapping/wetland_registry.html](mapping/templates/mapping/wetland_registry.html) and referenced in alerts/monitor pages

---

## 2. Monitoring Record Metrics

Time-series indicators stored per year and season. These are snapshot values for a specific monitoring period, collected either manually via form entry or computed from Earth Engine data.

### Vegetation & Soil Indices

| Indicator | Field | Model | Range | Storage | Computed By | Used By |
|-----------|-------|-------|-------|---------|-------------|---------|
| **NDVI Mean** | `ndvi_mean` | `WetlandMonitoringRecord` | -1.0 to 1.0 | Persistent (FloatField, nullable) | EE Sentinel-2 normalized difference ([B8–B4] / [B8+B4]) | Monitor page cards, early warning decline logic, form display |
| **NDVI Std Dev** | `ndvi_std` | `WetlandMonitoringRecord` | 0.0+ | Persistent (FloatField, nullable) | EE reducer | Monitor page, statistical context |
| **BSI Mean** | `bsi_mean` | `WetlandMonitoringRecord` | -1.0 to 1.0 | Persistent (FloatField, nullable) | EE Sentinel-2 bare soil index ([B11+B4–B8–B2] / [B11+B4+B8+B2]) | Monitor page cards, early warning threshold logic, soil degradation assessment |
| **BSI Std Dev** | `bsi_std` | `WetlandMonitoringRecord` | 0.0+ | Persistent (FloatField, nullable) | EE reducer | Statistical context (rarely displayed) |
| **Slope Mean** | `slope_mean` | `WetlandMonitoringRecord` | 0–90° | Persistent (FloatField, nullable) | EE SRTM DEM terrain analysis | Monitor page cards, RUSLE erosion calculation, topographic context |

**Computation Entry Point:**
- EE calculations in [mapping/views.py](mapping/views.py#L560-L620), especially `_calculate_ndvi()` and `_calculate_bsi()`
- Bulk computed via `/api/wetland-erosion-data/` in [wetlands/views.py](wetlands/views.py#L430-L520)

**Displayed In:**
- [mapping/templates/mapping/monitor_wetland.html](mapping/templates/mapping/monitor_wetland.html#L180-L220) as cards (NDVI, BSI, slope)

---

### Erosion Risk

| Indicator | Field | Model | Range | Storage | Computed By | Used By |
|-----------|-------|-------|-------|---------|-------------|---------|
| **Erosion Risk (numeric)** | `erosion_risk` | `WetlandMonitoringRecord` | 0.0–2.0 | Persistent (FloatField, nullable, validators [0,2]) | RUSLE model: R×K×LS×C×P (see [mapping/views.py](mapping/views.py#L567-L640)) | Monitor page display, risk-to-class conversion, early warning thresholds |
| **Risk Class (label)** | `risk_class` | `WetlandMonitoringRecord` | 'low', 'moderate', 'high' | Persistent (CharField, nullable) | Derived from `erosion_risk` via `_classify_erosion()` ([mapping/views.py](mapping/views.py#L594-L602)) or manual entry | Monitor page badge, history item styling, card borders |

**RUSLE Factors:**
- **R (Rainfall Erosivity):** From CHIRPS daily rainfall, computed annually [mapping/views.py](mapping/views.py#L625-L636)
- **K (Soil Erodibility):** From OpenLandMap soil texture [mapping/views.py](mapping/views.py#L600-L618)
- **LS (Slope Length & Steepness):** From SRTM DEM [mapping/views.py](mapping/views.py#L580-L595)
- **C (Cover Factor):** Derived from NDVI [mapping/views.py](mapping/views.py#L644-L651)
- **P (Practice Factor):** Set to 1.0 (no conservation practices) [mapping/views.py](mapping/views.py#L653)

**Classification Function:**
- `_classify_erosion(mean_soil_loss)` [mapping/views.py](mapping/views.py#L594-L602):
  - soil_loss ≥ 30 t/ha/yr → 'Very High'
  - 15–29 → 'High'
  - 5–14 → 'Moderate'
  - < 5 → 'Low'

**Displayed In:**
- [mapping/templates/mapping/monitor_wetland.html](mapping/templates/mapping/monitor_wetland.html#L182-L195) as a large risk value card and badge
- Early warning alerts [mapping/templates/mapping/alerts.html](mapping/templates/mapping/alerts.html) as threshold triggers

---

### Data Quality

| Indicator | Field | Model | Storage | Input Method | Used By |
|-----------|-------|-------|---------|--------------|---------|
| **Cloud Cover (%)** | `cloud_cover` | `WetlandMonitoringRecord` | Persistent (FloatField, 0–100, nullable) | EE metadata or manual entry | Monitor page display, filtering/alerts, data confidence assessment |
| **Data Quality** | `data_quality` | `WetlandMonitoringRecord` | 'good', 'fair', 'poor' | Manual selection in form | Form display, context for data validity |

**Displayed In:**
- [mapping/templates/mapping/monitor_wetland.html](mapping/templates/mapping/monitor_wetland.html#L210-L215) as a status card ('Cloud Cover')

**Sources:**
- Model: [mapping/models.py](mapping/models.py#L183-L220)
- Form: [wetlands/forms.py](wetlands/forms.py#L230-L310)
- Display: [mapping/templates/mapping/monitor_wetland.html](mapping/templates/mapping/monitor_wetland.html#L187-L225)

---

## 3. Thermal Metrics (LST)

Land Surface Temperature (LST) computed from Landsat 8 thermal band (B10). LST is not stored as a monitoring record but is computed on demand and cached in `Wetland.metadata['latest_lst_c']`.

| Indicator | Source | Computation | Range | Storage | Used By |
|-----------|--------|-------------|-------|---------|---------|
| **LST (°C)** | Landsat 8 Band 10 (thermal) | Radiometric inversion and atmospheric correction [mapping/views.py](mapping/views.py#L245-L260) | -40–80°C | `Wetland.metadata['latest_lst_c']` (cached) | LST monitor UI, early warning alert logic |
| **Health (label)** | LST mean value | `_classify_health()` [mapping/views.py](mapping/views.py#L271-L280) | 'Healthy', 'Stressed', 'Critical', 'Severe', 'No Data' | UI-only label | LST monitor page status pills and coloring |

**LST Calculation:**
- Formula: `Tb / (1 + 0.00115 × Tb / 1.4388 × ln(emissivity)) − 273.15`
  - Tb = thermal band value (Kelvin)
  - Emissivity derived from NDVI: `0.004 × NDVI + 0.986`
- Implementation: [mapping/views.py](mapping/views.py#L245-L260)

**Health Classification:**
- ≤ 18°C → 'Healthy'
- 18–22°C → 'Stressed'
- 22–26°C → 'Critical'
- > 26°C → 'Severe'

**API Endpoints:**
- `GET /api/lst-data/?year=YYYY` — Returns per-site LST and tile URL for given year [mapping/views.py](mapping/views.py#L296-L360)
- `GET /api/lst-predict/?year=YYYY` — Returns historical LST (2013–2024) + linear predictions (2025–2030) [mapping/views.py](mapping/views.py#L363-L415)

**Displayed In:**
- [mapping/templates/mapping/lst_monitor.html](mapping/templates/mapping/lst_monitor.html) as:
  - Map overlay (heat map with color scale 10–30°C)
  - Site list with status pills colored by health class
  - Bar chart of per-site temperatures
  - Trend & prediction chart (on-demand)

**Alert Usage:**
- [early_warning/views.py](early_warning/views.py#L35-L71): LST ≥ 30°C triggers critical alert; ≥ 26°C triggers warning

---

## 4. Erosion Monitoring (Summary View)

Per-polygon soil-loss raster computed annually at the feature/polygon level.

| Indicator | Source | Computation | Storage | Used By |
|-----------|--------|-------------|---------|---------|
| **Soil Loss (t/ha/yr)** | RUSLE NDVI+K+LS+R+C+P | Mean aggregated per polygon | API response (not persisted) | Erosion monitor UI, polygon tooltips, year comparisons |
| **Erosion Status (label)** | Soil loss mean | `_classify_erosion()` | API response (not persisted) | Erosion monitor map markers, polygon popups |
| **Polygon Centroid** | GeoJSON features | Computed from coordinate ring | API response (not persisted) | Erosion monitor map placement |

**API Endpoint:**
- `GET /api/wetland-erosion/?year=YYYY` — Returns per-polygon soil loss, status label, centroid, and tile URL [mapping/views.py](mapping/views.py#L653-L710)
- `GET /api/wetland-erosion-compare/?year_a=A&year_b=B` — Returns change between two years [mapping/views.py](mapping/views.py#L713-L760)

**Displayed In:**
- [mapping/templates/mapping/erosion_monitor.html](mapping/templates/mapping/erosion_monitor.html) (referenced via view, not shown in detail)
- Tile URL rendered on erosion map with color scale (0–40 t/ha/yr)

---

## 5. Timelapse Spectral Metrics

Nine annual spectral indices computed from Sentinel-2 median composites per year. These form a time-series for multi-year trend analysis and export as GIF frames.

| Indicator | Formula | Sentinel-2 Bands | Data Type | Used By |
|-----------|---------|------------------|-----------|---------|
| **NDWI** | (B3 − B8) / (B3 + B8) | Green, NIR | Annual mean | Water index trend, area-of-water calculation |
| **NDVI** | (B8 − B4) / (B8 + B4) | NIR, Red | Annual mean | Vegetation index, C-factor (erosion), trend |
| **MNDWI** | (B3 − B11) / (B3 + B11) | Green, SWIR1 | Annual mean | Modified water index for open water vs. vegetation |
| **LSWI** | (B8 − B11) / (B8 + B11) | NIR, SWIR1 | Annual mean | Lignin + moisture index, stress indicator |
| **EVI** | 2.5 × (B8 − B4) / (B8 + 6×B4 − 7.5×B2 + 1) | NIR, Red, Blue | Annual mean | Enhanced vegetation index (atmospherically corrected) |
| **AWEI** | 4×(B3−B11) − (0.25×B8 + 2.75×B12) | Green, SWIR1, NIR, SWIR2 | Annual mean | Automated Water Extraction Index for wetland/water |
| **SAVI** | 1.5 × (B8 − B4) / (B8 + B4 + 0.5) | NIR, Red | Annual mean | Soil-Adjusted Vegetation Index |
| **NDMI** | (B8 − B11) / (B8 + B11) | NIR, SWIR1 | Annual mean | Normalized Difference Moisture Index |
| **TCW** | 0.1509×B2 + 0.1973×B3 + 0.3279×B4 + 0.3406×B8 − 0.7112×B11 − 0.4572×B12 | All bands | Annual mean | Tasseled Cap Wetness (moisture/water content) |

**Computation Entry Point:**
- `_annual_timelapse_metrics(geometry, years, buffer_meters=0, cloud_threshold=20)` [timelapse/views.py](timelapse/views.py#L112-L210)
- Query: S2 median composite per year, filtered on cloud cover (default ≤ 20%)
- Output: JSON dictionary with `{'series': {metric_name: [year_1_val, year_2_val, ...]}, 'area_ha': [...], 'area_change_percent': X}`

**Area Metric:**
- **Wetland Area (ha):** Calculated using NDWI > 0 threshold to mask water pixels, then sum pixel areas
- **Area Change (%):** `((area_year_final − area_year_initial) / area_year_initial) × 100`

**Displayed In:**
- [mapping/templates/mapping/wetland_timelapse.html](mapping/templates/mapping/wetland_timelapse.html) as:
  - Nine separate line or bar charts (one per metric) showing year-over-year values
  - Area (ha) chart with percentage change note
  - Each chart interactive with Chart.js

**GIF Export:**
- Frames generated for each year via async Celery task [timelapse/tasks.py](timelapse/tasks.py)
- Each frame is a spatial snapshot of the wetland at that year overlaid on satellite basemap

**Sources:**
- Model/Job storage: [mapping/models.py](mapping/models.py) `TimelapseJob` 
- Metric calculation: [timelapse/views.py](timelapse/views.py#L112-L210)
- UI display: [mapping/templates/mapping/wetland_timelapse.html](mapping/templates/mapping/wetland_timelapse.html)

---

## 6. Early Warning Alert Indicators

Alerts are composite, threshold-based assessments combining multiple indicators. The alert engine synthesizes rule triggers and severity levels.

### Alert Triggers

| Trigger | Indicator(s) | Threshold | Severity | Reason |
|---------|--------------|-----------|----------|--------|
| **NDVI Decline** | NDVI % change (year-over-year) | ≥ 20% decline | Warning; ≥ 35% = Critical | Vegetation loss indicates stress/erosion |
| **BSI Current** | BSI mean value | ≥ 0.18 | Warning; ≥ 0.25 = Critical | High bare soil indicates erosion risk |
| **BSI Increase** | BSI % change (year-over-year) | ≥ 10–20% increase | Warning | Rapid soil exposure degradation |
| **LST Current** | LST mean (°C) | ≥ 26°C | Warning; ≥ 30°C = Critical | High temperature indicates thermal stress |
| **LST Increase** | LST change (°C, year-over-year) | ≥ 2°C increase | Warning | Rapid temperature rise suggests stress onset |
| **Erosion Risk** | Erosion risk score | ≥ 1.0 | Warning; ≥ 1.5 = Critical | RUSLE model indicates high soil loss |

**Composite Scoring:**
- Each triggered rule contributes a score component (0.0–0.35)
- Final score: min(sum(components), 1.0)
- Severity determination: if ≥1 critical rule OR ≥2 warning rules → 'critical'; 1 warning → 'warning'; else 'info'
- Alerts with score < 0.30 and no rule triggers are suppressed

**Implementation:**
- [early_warning/views.py](early_warning/views.py#L29-L100): `_compose_composite_alert()`
- [early_warning/views.py](early_warning/views.py#L102-L250): `_build_early_warning_alerts()`

**Displayed In:**
- [mapping/templates/mapping/alerts.html](mapping/templates/mapping/alerts.html) as:
  - Alert cards with severity badges (Critical, Warning, Info)
  - Summary counts (Total, Unread, Critical, Resolved)
  - Filterable list with search and severity/type filters
  - Detail modal showing full alert description, thresholds, and metadata

---

## Usage Map

### By Page/Surface

| Surface | Indicators Used | Notes |
|---------|-----------------|-------|
| **Dashboard** ([mapping/templates/mapping/dashboard.html](mapping/templates/mapping/dashboard.html)) | Risk level, status, name, village, area | Wetland feature map layer and summary statistics |
| **Registry** ([mapping/templates/mapping/wetland_registry.html](mapping/templates/mapping/wetland_registry.html)) | Name, village, risk level, status, area, elevation | Editable list view, filter by risk/status, bulk upload |
| **Monitor (Soil)** ([mapping/templates/mapping/monitor_wetland.html](mapping/templates/mapping/monitor_wetland.html)) | NDVI mean/std, BSI mean, slope mean, cloud cover, erosion risk, risk class, monitoring history | Year slider for historical record access, year-over-year comparison, trend chart, prediction chart |
| **Monitor (LST)** ([mapping/templates/mapping/lst_monitor.html](mapping/templates/mapping/lst_monitor.html)) | LST per site, health label, historical LST (2013–2024), LST predictions (2025–2030) | Map overlay, site list with colored pills, bar/line charts |
| **Timelapse** ([mapping/templates/mapping/wetland_timelapse.html](mapping/templates/mapping/wetland_timelapse.html)) | NDWI, NDVI, MNDWI, LSWI, EVI, AWEI, SAVI, NDMI, TCW, area (ha), area change (%) | Nine time-series charts, GIF frames, status tracking |
| **Alerts** ([mapping/templates/mapping/alerts.html](mapping/templates/mapping/alerts.html)) | NDVI decline %, BSI current/increase, LST current/increase, erosion risk, severity label, alert category | Composite thresholds, severity badge, detail modal, filtering |
| **Erosion Monitor** | Soil loss (t/ha/yr), erosion status label, polygon centroid | Raster overlay, per-polygon tooltip, year comparison |

---

## Key Observations & Inconsistencies

### 1. Risk Terminology Overlap

- `Wetland.risk_level` ('low', 'moderate', 'high', 'unknown'): Persistent wetland-level assessment, edited manually in registry.
- `WetlandMonitoringRecord.risk_class` ('low', 'moderate', 'high'): Derived annually from erosion risk score; may not sync automatically with `risk_level`.
- **Implication:** A wetland's `risk_level` may differ from its latest `risk_class`, creating potential confusion. Consider adding explicit sync logic or UI clarification.

### 2. Erosion Risk Scales

- **Numeric range:** 0.0–2.0 (`erosion_risk` field)
- **Classification thresholds:** Low (< 5 t/ha/yr), Moderate (5–15), High (15–30), Very High (≥ 30)
- **Used interchangeably in different contexts:** Storage as 0–2, display as t/ha/yr, classification as string labels
- **Implication:** The relationship between the 0–2 scale and the t/ha/yr scale is context-dependent; document this mapping more explicitly in code comments.

### 3. Health vs. Quality Terminology

- **LST Health** (from LST monitor): 'Healthy', 'Stressed', 'Critical', 'Severe' — a thermal assessment
- **Data Quality** (form field): 'good', 'fair', 'poor' — a metadata assessment
- **Alert Severity**: 'critical', 'warning', 'info', 'resolved' — a priority/action level
- **Implication:** Three separate "health/quality" concepts; ensure labels are consistently used in UI to avoid reader confusion.

### 4. Storage vs. Computed

- **Stored in DB:** Wetland metadata, monitoring records (NDVI, BSI, slope, erosion risk, risk class, cloud cover), boundary change history
- **Computed on-demand:** LST, timelapse metrics, per-polygon erosion rasters
- **Cached in metadata:** `Wetland.metadata['latest_lst_c']` for alert logic
- **Implication:** Alert logic depends on cache freshness; consider implementing explicit cache invalidation or scheduled updates.

### 5. Missing Indicator Fields

- **BSI Standard Deviation:** `bsi_std` exists in the model but is rarely displayed or used (unlike `ndvi_std`).
- **Timelapse Integration with Monitoring Records:** Timelapse metrics (NDWI, EVI, etc.) are not stored in `WetlandMonitoringRecord`; they live only in timelapse job output.
- **Implication:** Consider whether timelapse metrics should be synced back to monitoring records for unified time-series queries.

---

## References & Notes

### Data Sources

- **Sentinel-2 (S2):** Copernicus program, Level-2A surface reflectance (`COPERNICUS/S2_SR_HARMONIZED`)
- **Landsat 8:** USGS thermal band (`LANDSAT/LC08/C02/T1_TOA`)
- **SRTM DEM:** USGS 1-arc-second digital elevation model (`USGS/SRTMGL1_003`)
- **CHIRPS:** Climate Hazards Group rainfall data (`UCSB-CHG/CHIRPS/DAILY`)
- **OpenLandMap:** Soil texture classification (`OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02`)

### Configuration

- **Cloud Threshold (default):** 20% for monitoring, configurable per job
- **LST Calculation:** October–March (austral summer) per year
- **RUSLE Factors:** See computation details in [mapping/views.py](mapping/views.py) section "Soil Erosion"
- **Timelapse Defaults:** Start year 2018, end year 2023, buffer 100m, frames per second 1, dimensions 300×300

---

## How to Use This Document

1. **Find an indicator:** Use the table-of-contents structure or search (Ctrl+F) for the indicator name.
2. **Understand computation:** Look at the "Computation" or "Formula" column to see which data source and formula is used.
3. **Locate source code:** See the section headers for references to the implementation files.
4. **Check usage:** Look at the "Used By" column or the Usage Map section to see which pages/alerts consume the indicator.
5. **Trace cascades:** Follow the dependency chain (e.g., NDVI → erosion risk → risk class → monitor card display).
