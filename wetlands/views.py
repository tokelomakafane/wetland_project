import json
import os
from pathlib import Path

from django.db import IntegrityError, models
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.conf import settings

from mapping.ee_utils import initialize_ee
from mapping.models import Wetland, WetlandMonitoringRecord

from .forms import BulkWetlandUploadForm, WetlandFilterForm, WetlandForm

WETLAND_NAMES = [
    'Mantsonyane',
    'Oxbow',
    'Literapeng',
    'Leribe Lefikeng',
    'Ha-Moroane',
    'Mathoane Ha-Khohlooa',
    'Nazareth Toll-gate',
    'Mohlakeng Mokema',
    'Mohlakeng Mokema East',
    'Mohlakeng Mokema South',
    'Mohlakeng Mokema West',
    "Mafeteng Tsita's Nek",
    "Mohale's Hoek Ha-Makhathe",
    "Lets'eng La Letsie",
    'Quthing Ha-Rantema',
    'Mokopung ha-Lepekola',
    'Semonkong',
    'Semonkong (Upper)',
    "Thaba-Tseka Mats'oana",
    'White Hill ha-Sehapi',
    "Rama's Gate",
    'Edward Dam',
    'SNP',
]


def _load_static_wetlands_geojson():
    """Load static wetland geometries from JSON file and convert to FeatureCollection."""
    json_path = Path(__file__).resolve().parent.parent / 'mapping' / 'wetland_polygons.json'
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Handle GeometryCollection format (convert to FeatureCollection)
        if data.get('type') == 'GeometryCollection':
            features = []
            for i, geom in enumerate(data.get('geometries', [])):
                feature = {
                    'type': 'Feature',
                    'geometry': geom,
                    'properties': {
                        'name': WETLAND_NAMES[i] if i < len(WETLAND_NAMES) else f'Wetland {i}',
                        'village': '',
                        'source': 'historical_static',
                        'is_static': True,
                    }
                }
                features.append(feature)
            return {'type': 'FeatureCollection', 'features': features}

        # Already a FeatureCollection
        return data
    except FileNotFoundError:
        return {'type': 'FeatureCollection', 'features': []}


def _seed_static_wetlands_into_db():
    """Create database rows for historical wetlands so they can be monitored too."""
    static_geojson = _load_static_wetlands_geojson()
    created_count = 0

    for i, feature in enumerate(static_geojson.get('features', [])):
        props = feature.get('properties', {}) or {}
        geometry = feature.get('geometry')
        if not geometry:
            continue

        name = props.get('name') or (WETLAND_NAMES[i] if i < len(WETLAND_NAMES) else f'Wetland {i}')

        _, created = Wetland.objects.get_or_create(
            name=name,
            defaults={
                'village': props.get('village', ''),
                'description': props.get('description', 'Historical wetland'),
                'geometry': json.dumps(geometry),
                'area_ha': props.get('area_ha'),
                'elevation_m': props.get('elevation_m'),
                'status': 'archived',
                'risk_level': props.get('risk_level', 'unknown'),
                'source': 'historical_static',
                'uploaded_by': 'system',
                'version': 1,
                'is_current': True,
                'metadata': {
                    'source_file': 'wetland_polygons.json',
                    'static_index': i,
                    'is_static': True,
                },
            }
        )

        if created:
            created_count += 1

    return created_count


def wetland_registry(request):
    """View all wetlands and return map-ready GeoJSON."""
    _seed_static_wetlands_into_db()

    wetlands = Wetland.objects.filter(is_current=True).order_by('-date_discovered')
    form = WetlandFilterForm(request.GET or None)

    if form.is_valid():
        search = form.cleaned_data.get('search')
        village = form.cleaned_data.get('village')
        status = form.cleaned_data.get('status')
        risk_level = form.cleaned_data.get('risk_level')
        min_area = form.cleaned_data.get('min_area_ha')
        max_area = form.cleaned_data.get('max_area_ha')

        if search:
            wetlands = wetlands.filter(
                models.Q(name__icontains=search)
                | models.Q(village__icontains=search)
                | models.Q(description__icontains=search)
            )
        if village:
            wetlands = wetlands.filter(village__icontains=village)
        if status:
            wetlands = wetlands.filter(status=status)
        if risk_level:
            wetlands = wetlands.filter(risk_level=risk_level)
        if min_area:
            wetlands = wetlands.filter(area_ha__gte=min_area)
        if max_area:
            wetlands = wetlands.filter(area_ha__lte=max_area)

    def _geometry_to_geojson(geometry_value):
        if not geometry_value:
            return None
        parsed = json.loads(geometry_value) if isinstance(geometry_value, str) else geometry_value
        if parsed.get('type') == 'Feature':
            return parsed.get('geometry')
        return parsed

    features = []
    for wetland in wetlands:
        geometry = _geometry_to_geojson(wetland.geometry)
        if not geometry:
            continue

        features.append({
            'type': 'Feature',
            'id': f'db_{wetland.id}',
            'geometry': geometry,
            'properties': {
                'id': wetland.id,
                'name': wetland.name,
                'village': wetland.village,
                'area_ha': wetland.area_ha,
                'elevation_m': wetland.elevation_m,
                'description': wetland.description,
                'status': wetland.status,
                'risk_level': wetland.risk_level,
                'uploaded_by': wetland.uploaded_by,
                'date_discovered': wetland.date_discovered.isoformat(),
                'source': wetland.source,
                'is_static': wetland.source == 'historical_static',
            }
        })

    geojson = {'type': 'FeatureCollection', 'features': features}

    context = {
        'wetlands': wetlands,
        'form': form,
        'geojson': json.dumps(geojson),
        'total_count': Wetland.objects.filter(is_current=True).count(),
        'static_count': Wetland.objects.filter(source='historical_static', is_current=True).count(),
        'active_page': 'wetland_registry',
    }
    return render(request, 'mapping/wetland_registry.html', context)


def add_wetland(request):
    """Add a new wetland from map-drawn polygon GeoJSON."""
    if request.method == 'POST':
        form = WetlandForm(request.POST)
        if form.is_valid():
            wetland = form.save(commit=False)
            wetland.source = 'manual_drawing'
            wetland.save()
            return JsonResponse({
                'success': True,
                'message': f'Wetland "{wetland.name}" created successfully!',
                'wetland_id': wetland.id,
                'redirect_url': redirect('wetlands:monitor_wetland', pk=wetland.id).url,
            })

        errors = form.errors.as_json()
        return JsonResponse({'success': False, 'errors': json.loads(errors)}, status=400)

    form = WetlandForm()
    return render(request, 'mapping/add_wetland.html', {'form': form, 'active_page': 'add_wetland'})


def upload_wetlands(request):
    """Bulk upload wetlands from GeoJSON (others stubbed)."""
    if request.method == 'POST':
        form = BulkWetlandUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file_obj = request.FILES['file']
            file_format = form.cleaned_data['file_format']
            source = form.cleaned_data['source']
            uploaded_by = form.cleaned_data['uploaded_by']
            overwrite = form.cleaned_data.get('overwrite_existing', False)

            try:
                features = _parse_upload_file(file_obj, file_format)
                created_count = 0
                updated_count = 0
                errors = []

                for i, feature in enumerate(features):
                    try:
                        geometry = feature.get('geometry')
                        if not geometry:
                            raise ValueError('Missing geometry')
                        if geometry.get('type') not in ['Polygon', 'MultiPolygon']:
                            raise ValueError('Only Polygon/MultiPolygon are supported')

                        geometry_json = json.dumps(geometry)
                        props = feature.get('properties', {})
                        name = props.get('name', f'Uploaded_Wetland_{i}')

                        existing = Wetland.objects.filter(name=name, is_current=True).first()
                        if existing and not overwrite:
                            errors.append(f"Wetland '{name}' already exists (not overwriting)")
                            continue

                        if existing and overwrite:
                            existing.is_current = False
                            existing.save()
                            updated_count += 1

                        Wetland.objects.create(
                            name=name,
                            village=props.get('village', ''),
                            description=props.get('description', ''),
                            geometry=geometry_json,
                            source=source,
                            uploaded_by=uploaded_by,
                            metadata=props,
                        )
                        created_count += 1
                    except Exception as e:
                        errors.append(f"Feature {i}: {str(e)}")

                return JsonResponse({
                    'success': True,
                    'created': created_count,
                    'updated': updated_count,
                    'errors': errors,
                    'message': f'Uploaded {created_count} wetlands successfully!',
                })
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=400)

    form = BulkWetlandUploadForm()
    return render(request, 'mapping/upload_wetlands.html', {'form': form, 'active_page': 'upload_wetlands'})


def _parse_upload_file(file_obj, file_format):
    """Parse uploaded file and extract features."""
    if file_format == 'geojson':
        content = file_obj.read().decode('utf-8')
        data = json.loads(content)
        if data.get('type') == 'FeatureCollection':
            return data.get('features', [])
        if data.get('type') == 'Feature':
            return [data]
        raise ValueError('Expected FeatureCollection or Feature')

    if file_format == 'kml':
        raise NotImplementedError('KML upload not yet implemented')
    if file_format == 'shapefile':
        raise NotImplementedError('Shapefile upload not yet implemented')
    raise ValueError(f'Unsupported format: {file_format}')


def monitor_wetland(request, pk):
    """Monitor one wetland and show stored records."""
    _seed_static_wetlands_into_db()

    try:
        wetland = Wetland.objects.get(pk=pk, is_current=True)
    except Wetland.DoesNotExist:
        return render(request, '404.html', status=404)

    records = WetlandMonitoringRecord.objects.filter(wetland=wetland).order_by('-year')
    latest_record = records.first()

    geometry = json.loads(wetland.geometry) if isinstance(wetland.geometry, str) else wetland.geometry
    if geometry.get('type') == 'Feature':
        geometry = geometry.get('geometry')

    geojson = {
        'type': 'Feature',
        'geometry': geometry,
        'properties': {
            'name': wetland.name,
            'village': wetland.village,
            'area_ha': wetland.area_ha,
        },
    }

    context = {
        'wetland': wetland,
        'latest_record': latest_record,
        'records': records,
        'geojson': json.dumps(geojson),
        'active_page': 'monitor_wetland',
    }
    return render(request, 'mapping/monitor_wetland.html', context)


def edit_wetland(request, pk):
    """Update editable wetland metadata from registry actions."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        wetland = Wetland.objects.get(pk=pk, is_current=True)
    except Wetland.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Wetland not found'}, status=404)

    if wetland.source == 'historical_static':
        return JsonResponse({'success': False, 'error': 'Historical wetlands cannot be edited'}, status=403)

    payload = request.POST
    if request.content_type and request.content_type.startswith('application/json'):
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON payload'}, status=400)

    name = str(payload.get('name', wetland.name)).strip()
    if not name:
        return JsonResponse({'success': False, 'error': 'Name is required'}, status=400)

    village = str(payload.get('village', wetland.village or '')).strip()
    description = str(payload.get('description', wetland.description or '')).strip()
    status = str(payload.get('status', wetland.status)).strip()
    risk_level = str(payload.get('risk_level', wetland.risk_level)).strip()
    uploaded_by = str(payload.get('uploaded_by', wetland.uploaded_by or '')).strip()

    valid_status = {value for value, _ in Wetland.STATUS_CHOICES}
    valid_risk = {value for value, _ in Wetland.RISK_LEVEL_CHOICES}
    if status not in valid_status:
        return JsonResponse({'success': False, 'error': 'Invalid status value'}, status=400)
    if risk_level not in valid_risk:
        return JsonResponse({'success': False, 'error': 'Invalid risk level value'}, status=400)

    elevation_raw = payload.get('elevation_m', wetland.elevation_m)
    if elevation_raw in (None, '', 'null'):
        elevation_m = None
    else:
        try:
            elevation_m = int(elevation_raw)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Elevation must be a number'}, status=400)

    wetland.name = name
    wetland.village = village
    wetland.description = description
    wetland.status = status
    wetland.risk_level = risk_level
    wetland.uploaded_by = uploaded_by
    wetland.elevation_m = elevation_m

    try:
        wetland.save()
    except IntegrityError:
        return JsonResponse({'success': False, 'error': 'Wetland name already exists'}, status=400)

    return JsonResponse({
        'success': True,
        'message': 'Wetland updated successfully',
        'wetland': {
            'id': wetland.id,
            'name': wetland.name,
            'village': wetland.village,
            'description': wetland.description,
            'status': wetland.status,
            'risk_level': wetland.risk_level,
            'elevation_m': wetland.elevation_m,
            'uploaded_by': wetland.uploaded_by,
        },
    })


def delete_wetland(request, pk):
    """Delete a user-created wetland from the registry."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        wetland = Wetland.objects.get(pk=pk, is_current=True)
    except Wetland.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Wetland not found'}, status=404)

    if wetland.source == 'historical_static':
        return JsonResponse({'success': False, 'error': 'Historical wetlands cannot be deleted'}, status=403)

    wetland_name = wetland.name
    wetland.delete()
    return JsonResponse({'success': True, 'message': f'Wetland "{wetland_name}" deleted'})


def api_wetland_erosion_data(request, pk):
    """API: compute erosion indicators for one wetland and year."""
    import ee
    import math
    from mapping.views import _calculate_bsi, _calculate_ndvi

    _seed_static_wetlands_into_db()

    try:
        wetland = Wetland.objects.get(pk=pk, is_current=True)
    except Wetland.DoesNotExist:
        return JsonResponse({'error': 'Wetland not found'}, status=404)

    year = request.GET.get('year')
    try:
        year = int(year) if year else 2023
        if year < 2013 or year > 2024:
            return JsonResponse({'error': 'Year must be between 2013 and 2024'}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid year parameter'}, status=400)

    try:
        initialize_ee()

        geom_geojson = json.loads(wetland.geometry) if isinstance(wetland.geometry, str) else wetland.geometry
        if geom_geojson.get('type') == 'Feature':
            geom_geojson = geom_geojson.get('geometry')
        geom = ee.Geometry(geom_geojson)

        start_date = ee.Date.fromYMD(year, 1, 1)
        end_date = ee.Date.fromYMD(year, 12, 31)
        col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterDate(start_date, end_date) \
            .filterBounds(geom) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))

        dem = ee.Image('USGS/SRTMGL1_003')
        slope = ee.Terrain.slope(dem).clip(geom)
        bsi = col.map(_calculate_bsi).select('BSI').mean().clip(geom)
        ndvi = col.map(_calculate_ndvi).select('NDVI').mean().clip(geom)

        risk = ee.Image(0) \
            .where(bsi.gt(0.1).And(slope.gt(8)), 1) \
            .where(bsi.gt(0.2).And(slope.gt(15)), 2) \
            .clip(geom)

        stats = risk.addBands(bsi).addBands(ndvi).addBands(slope).reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), '', True),
            geometry=geom,
            scale=30,
            maxPixels=1e6,
        )
        data = stats.getInfo()

        mean_risk = data.get('constant_mean')
        risk_class = 'LOW'
        if mean_risk and mean_risk > 1.5:
            risk_class = 'HIGH'
        elif mean_risk and mean_risk > 0.5:
            risk_class = 'MODERATE'

        slope_mean = data.get('slope_mean', 0)
        ndvi_mean = data.get('NDVI_mean', 0)
        R, K = 500, 0.32
        slope_percent = slope_mean * 1.192
        S = max(0.1, (slope_percent / 45) ** 0.5)
        L = 1.0
        LS = L * S
        C = max(0.05, min(1.0, math.exp(-2.0 * (ndvi_mean + 0.5))))
        P = 1.0
        soil_loss = R * K * LS * C * P

        return JsonResponse({
            'year': year,
            'wetland_name': wetland.name,
            'soil_loss_t_ha_yr': round(soil_loss, 2),
            'bsi_mean': round(data.get('BSI_mean', 0), 3),
            'bsi_std': round(data.get('BSI_stdDev', 0), 3),
            'ndvi_mean': round(data.get('NDVI_mean', 0), 3),
            'ndvi_std': round(data.get('NDVI_stdDev', 0), 3),
            'slope_mean': round(data.get('slope_mean', 0), 2),
            'erosion_risk': round(mean_risk or 0, 3),
            'risk_class': risk_class,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_wetland_comparison(request):
    """API: compare erosion risk between two years for one wetland."""
    import ee
    from mapping.views import _calculate_bsi

    wetland_id = request.GET.get('wetland_id')
    year_a = request.GET.get('year_a', '2018')
    year_b = request.GET.get('year_b', '2023')

    try:
        wetland = Wetland.objects.get(pk=int(wetland_id), is_current=True)
    except (Wetland.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Wetland not found'}, status=404)

    try:
        year_a, year_b = int(year_a), int(year_b)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid year parameters'}, status=400)

    try:
        initialize_ee()

        geom_geojson = json.loads(wetland.geometry) if isinstance(wetland.geometry, str) else wetland.geometry
        if geom_geojson.get('type') == 'Feature':
            geom_geojson = geom_geojson.get('geometry')
        geom = ee.Geometry(geom_geojson)

        def get_risk(year):
            start = ee.Date.fromYMD(year, 1, 1)
            end = ee.Date.fromYMD(year, 12, 31)
            col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
                .filterDate(start, end) \
                .filterBounds(geom) \
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))

            dem = ee.Image('USGS/SRTMGL1_003')
            slope = ee.Terrain.slope(dem).clip(geom)
            bsi = col.map(_calculate_bsi).select('BSI').mean().clip(geom)

            return ee.Image(0) \
                .where(bsi.gt(0.1).And(slope.gt(8)), 1) \
                .where(bsi.gt(0.2).And(slope.gt(15)), 2) \
                .clip(geom)

        risk_a = get_risk(year_a)
        risk_b = get_risk(year_b)
        change = risk_b.subtract(risk_a)

        stats = change.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=30,
            maxPixels=1e6,
        )
        data = stats.getInfo()
        mean_change = data.get('constant', 0)

        direction = 'stable'
        if mean_change > 0.1:
            direction = 'worsening'
        elif mean_change < -0.1:
            direction = 'improving'

        return JsonResponse({
            'year_a': year_a,
            'year_b': year_b,
            'mean_change': round(mean_change, 3),
            'direction': direction,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_wetland_prediction(request, pk):
    """API: return historical and predicted erosion risk for one wetland."""
    import ee
    from mapping.views import _calculate_bsi

    _seed_static_wetlands_into_db()

    try:
        wetland = Wetland.objects.get(pk=int(pk), is_current=True)
    except (Wetland.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Wetland not found'}, status=404)

    try:
        initialize_ee()

        geom_geojson = json.loads(wetland.geometry) if isinstance(wetland.geometry, str) else wetland.geometry
        if geom_geojson.get('type') == 'Feature':
            geom_geojson = geom_geojson.get('geometry')
        geom = ee.Geometry(geom_geojson)

        years = list(range(2013, 2025))
        historical = {}
        year_values = []

        def get_risk_image(year):
            start = ee.Date.fromYMD(year, 1, 1)
            end = ee.Date.fromYMD(year, 12, 31)
            col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
                .filterDate(start, end) \
                .filterBounds(geom) \
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))

            dem = ee.Image('USGS/SRTMGL1_003')
            slope = ee.Terrain.slope(dem).clip(geom)
            bsi = col.map(_calculate_bsi).select('BSI').mean().clip(geom)

            return ee.Image(0) \
                .where(bsi.gt(0.1).And(slope.gt(8)), 1) \
                .where(bsi.gt(0.2).And(slope.gt(15)), 2) \
                .clip(geom)

        for year in years:
            risk_img = get_risk_image(year)
            stats = risk_img.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geom,
                scale=30,
                maxPixels=1e6,
            )
            risk_value = stats.getInfo().get('constant')
            if risk_value is None:
                risk_value = 0
            risk_value = round(float(risk_value), 3)
            historical[str(year)] = risk_value
            year_values.append((year, risk_value))

        if len(year_values) >= 2:
            xs = [float(year) for year, _ in year_values]
            ys = [value for _, value in year_values]
            x_mean = sum(xs) / len(xs)
            y_mean = sum(ys) / len(ys)
            numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
            denominator = sum((x - x_mean) ** 2 for x in xs) or 1.0
            slope = numerator / denominator
            intercept = y_mean - slope * x_mean
        else:
            ys = [year_values[0][1]] if year_values else []
            slope = 0.0
            intercept = year_values[0][1] if year_values else 0.0

        predictions = {}
        for year in range(2025, 2031):
            predictions[str(year)] = round(intercept + slope * year, 3)

        avg_risk = sum(ys) / len(ys) if year_values else 0.0
        direction = 'stable'
        if slope > 0.01:
            direction = 'worsening'
        elif slope < -0.01:
            direction = 'improving'

        return JsonResponse({
            'wetland_id': wetland.id,
            'wetland_name': wetland.name,
            'historical': historical,
            'predictions': predictions,
            'slope': round(float(slope), 4),
            'intercept': round(float(intercept), 4),
            'average_risk': round(float(avg_risk), 3),
            'direction': direction,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
