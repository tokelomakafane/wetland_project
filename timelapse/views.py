import json
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse

from mapping.ee_utils import initialize_ee
from mapping.models import TimelapseJob, Wetland

from wetlands.views import _seed_static_wetlands_into_db

from .tasks import start_timelapse_job


def timelapse_view(request):
    """Render timelapse job UI with selectable wetlands from the database."""
    _seed_static_wetlands_into_db()

    wetlands = Wetland.objects.filter(is_current=True).order_by('name')

    features = []
    for wetland in wetlands:
        geometry = wetland.geometry
        if isinstance(geometry, str):
            try:
                geometry = json.loads(geometry)
            except json.JSONDecodeError:
                continue
        if geometry.get('type') == 'Feature':
            geometry = geometry.get('geometry', {})
        if geometry.get('type') not in ('Polygon', 'MultiPolygon'):
            continue

        features.append({
            'type': 'Feature',
            'geometry': geometry,
            'properties': {
                'id': wetland.id,
                'name': wetland.name,
                'village': wetland.village,
                'area_ha': wetland.area_ha,
            },
        })

    context = {
        'active_page': 'timelapse',
        'wetlands_geojson': json.dumps({'type': 'FeatureCollection', 'features': features}),
    }
    return render(request, 'mapping/timelapse.html', context)


def _wetland_geometry_geojson(wetland):
    geometry = wetland.geometry
    if isinstance(geometry, str):
        try:
            geometry = json.loads(geometry)
        except json.JSONDecodeError:
            return {}

    if isinstance(geometry, dict) and geometry.get('type') == 'Feature':
        geometry = geometry.get('geometry', {})

    return geometry if isinstance(geometry, dict) else {}


def _approximate_area_ha(geometry):
    if not geometry:
        return None

    try:
        geom_type = geometry.get('type')
        coords = geometry.get('coordinates')
        if geom_type not in ('Polygon', 'MultiPolygon') or not coords:
            return None

        def _ring_area(ring):
            area = 0.0
            for i in range(len(ring) - 1):
                x1, y1 = ring[i][0], ring[i][1]
                x2, y2 = ring[i + 1][0], ring[i + 1][1]
                area += (x1 * y2) - (x2 * y1)
            return abs(area) / 2.0

        def _polygon_area(poly_coords):
            if not poly_coords:
                return 0.0
            outer = _ring_area(poly_coords[0])
            holes = sum(_ring_area(ring) for ring in poly_coords[1:])
            return max(outer - holes, 0.0)

        if geom_type == 'Polygon':
            area_sq_deg = _polygon_area(coords)
        else:
            area_sq_deg = sum(_polygon_area(poly) for poly in coords)

        if area_sq_deg <= 0:
            return None

        meters_per_degree = 111000
        area_m2 = area_sq_deg * (meters_per_degree ** 2)
        return round(area_m2 / 10000, 2)
    except Exception:
        return None


def _get_latest_timelapse_job(wetland):
    return TimelapseJob.objects.filter(wetland=wetland).order_by('-created_at').first()


def _annual_timelapse_metrics(geometry, years, buffer_meters=0, cloud_threshold=20):
    import ee

    initialize_ee()

    geometry = ee.Geometry(geometry)
    if buffer_meters:
        geometry = geometry.buffer(buffer_meters)

    metric_names = ['NDWI', 'NDVI', 'MNDWI', 'LSWI', 'EVI', 'AWEI', 'SAVI', 'NDMI', 'TCW']
    series = {name: [] for name in metric_names}
    area_series = []

    for year in years:
        try:
            start_date = ee.Date.fromYMD(year, 1, 1)
            end_date = ee.Date.fromYMD(year, 12, 31)
            image = (
                ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', cloud_threshold))
                .filterBounds(geometry)
                .median()
                .clip(geometry)
            )

            ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI')
            ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
            mndwi = image.normalizedDifference(['B3', 'B11']).rename('MNDWI')
            lswi = image.normalizedDifference(['B8', 'B11']).rename('LSWI')
            evi = image.expression(
                '2.5 * ((nir - red) / (nir + 6 * red - 7.5 * blue + 1))',
                {
                    'nir': image.select('B8'),
                    'red': image.select('B4'),
                    'blue': image.select('B2'),
                },
            ).rename('EVI')
            awei = image.expression(
                '4 * (green - swir1) - (0.25 * nir + 2.75 * swir2)',
                {
                    'green': image.select('B3'),
                    'swir1': image.select('B11'),
                    'nir': image.select('B8'),
                    'swir2': image.select('B12'),
                },
            ).rename('AWEI')
            savi = image.expression(
                '1.5 * ((nir - red) / (nir + red + 0.5))',
                {
                    'nir': image.select('B8'),
                    'red': image.select('B4'),
                },
            ).rename('SAVI')
            ndmi = image.normalizedDifference(['B8', 'B11']).rename('NDMI')
            tcw = image.expression(
                '0.1509 * blue + 0.1973 * green + 0.3279 * red + 0.3406 * nir - 0.7112 * swir1 - 0.4572 * swir2',
                {
                    'blue': image.select('B2'),
                    'green': image.select('B3'),
                    'red': image.select('B4'),
                    'nir': image.select('B8'),
                    'swir1': image.select('B11'),
                    'swir2': image.select('B12'),
                },
            ).rename('TCW')

            values = ee.Image.cat([ndwi, ndvi, mndwi, lswi, evi, awei, savi, ndmi, tcw]).reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geometry,
                scale=20,
                bestEffort=True,
                maxPixels=1e10,
                tileScale=4,
            ).getInfo() or {}

            area_ha_value = (
                ndwi.gt(0)
                .selfMask()
                .multiply(ee.Image.pixelArea())
                .divide(10000)
                .rename('area_ha')
                .reduceRegion(
                    reducer=ee.Reducer.sum(),
                    geometry=geometry,
                    scale=20,
                    bestEffort=True,
                    maxPixels=1e10,
                    tileScale=4,
                )
                .getInfo()
                .get('area_ha')
            )
        except Exception:
            values = {}
            area_ha_value = None

        for name in metric_names:
            value = values.get(name)
            series[name].append(round(value, 4) if value is not None else None)

        area_series.append(round(area_ha_value, 2) if area_ha_value is not None else None)

    valid_area_values = [v for v in area_series if v is not None]
    area_delta_pct = None
    if len(valid_area_values) >= 2 and valid_area_values[0] != 0:
        area_delta_pct = round(((valid_area_values[-1] - valid_area_values[0]) / valid_area_values[0]) * 100, 2)

    return {
        'years': years,
        'series': series,
        'area_ha': area_series,
        'area_change_percent': area_delta_pct,
    }


def wetland_timelapse_view(request, pk):
    """Render preview frames and assessment charts for a single wetland."""
    _seed_static_wetlands_into_db()

    try:
        wetland = Wetland.objects.get(pk=pk, is_current=True)
    except Wetland.DoesNotExist:
        return render(request, '404.html', status=404)

    geometry = _wetland_geometry_geojson(wetland)
    latest_job = _get_latest_timelapse_job(wetland)

    if latest_job is None or latest_job.status == 'failed':
        latest_job = TimelapseJob.objects.create(
            wetland=wetland,
            start_year=2018,
            end_year=2023,
            buffer_meters=100,
            cloud_threshold=20,
            frames_per_second=1,
            dimensions=300,
        )
        start_timelapse_job(latest_job.id)

    years = list(range(latest_job.start_year, latest_job.end_year + 1))
    buffer_meters = latest_job.buffer_meters
    cloud_threshold = latest_job.cloud_threshold
    frames = latest_job.frame_urls or []
    export_status = latest_job.status
    download_url = reverse('timelapse:api_timelapse_download', args=[latest_job.id]) if latest_job.status == 'completed' and latest_job.gif_relative_path else ''

    wetland_area_ha = wetland.area_ha if wetland.area_ha is not None else _approximate_area_ha(geometry)
    assessment_data = _annual_timelapse_metrics(
        geometry=geometry,
        years=years,
        buffer_meters=buffer_meters,
        cloud_threshold=cloud_threshold,
    )

    context = {
        'active_page': 'timelapse',
        'wetland': wetland,
        'wetland_area_ha': wetland_area_ha,
        'wetland_summary': f"{wetland.name}, Wetland ID: {wetland.id}, {wetland.village or 'No village set'}",
        'timelapse_frames_json': json.dumps(frames),
        'timelapse_years_json': json.dumps(years),
        'timelapse_metrics_json': json.dumps(assessment_data),
        'timelapse_export_status': export_status,
        'timelapse_download_url': download_url,
        'timelapse_frames_loaded': len(frames),
        'timelapse_year_span': f'{years[0]} - {years[-1]}' if years else '-',
        'timelapse_job_id': latest_job.id,
        'timelapse_defaults_json': json.dumps({
            'start_year': latest_job.start_year,
            'end_year': latest_job.end_year,
            'buffer_meters': latest_job.buffer_meters,
            'cloud_threshold': latest_job.cloud_threshold,
            'dimensions': latest_job.dimensions,
            'frames_per_second': latest_job.frames_per_second,
        }),
        'timelapse_should_poll': latest_job.status in ('pending', 'running'),
    }
    return render(request, 'mapping/wetland_timelapse.html', context)


def _parse_int_param(payload, key, default, minimum=None, maximum=None):
    raw = payload.get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f'Invalid integer for {key}')

    if minimum is not None and value < minimum:
        raise ValueError(f'{key} must be >= {minimum}')
    if maximum is not None and value > maximum:
        raise ValueError(f'{key} must be <= {maximum}')
    return value


def api_timelapse_start(request):
    """Create a timelapse export job and start async processing."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    payload = request.POST
    if request.content_type == 'application/json':
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

    try:
        wetland_id = _parse_int_param(payload, 'wetland_id', None, minimum=1)
        start_year = _parse_int_param(payload, 'start_year', 2018, minimum=2013, maximum=2030)
        end_year = _parse_int_param(payload, 'end_year', 2023, minimum=2013, maximum=2030)
        buffer_meters = _parse_int_param(payload, 'buffer_meters', 100, minimum=0, maximum=5000)
        cloud_threshold = _parse_int_param(payload, 'cloud_threshold', 20, minimum=0, maximum=100)
        frames_per_second = _parse_int_param(payload, 'frames_per_second', 1, minimum=1, maximum=10)
        dimensions = _parse_int_param(payload, 'dimensions', 300, minimum=64, maximum=1024)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    if start_year > end_year:
        return JsonResponse({'error': 'start_year must be <= end_year'}, status=400)

    try:
        wetland = Wetland.objects.get(pk=wetland_id, is_current=True)
    except Wetland.DoesNotExist:
        return JsonResponse({'error': 'Wetland not found'}, status=404)

    job = TimelapseJob.objects.create(
        wetland=wetland,
        start_year=start_year,
        end_year=end_year,
        buffer_meters=buffer_meters,
        cloud_threshold=cloud_threshold,
        frames_per_second=frames_per_second,
        dimensions=dimensions,
    )

    start_timelapse_job(job.id)

    return JsonResponse({'job_id': job.id, 'status': job.status, 'message': 'Timelapse job created'}, status=202)


def api_timelapse_status(request, job_id):
    """Return current status for a timelapse job."""
    try:
        job = TimelapseJob.objects.select_related('wetland').get(pk=job_id)
    except TimelapseJob.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)

    return JsonResponse({
        'job_id': job.id,
        'wetland_id': job.wetland_id,
        'wetland_name': job.wetland.name,
        'status': job.status,
        'progress_percent': job.progress_percent,
        'error_message': job.error_message,
        'created_at': job.created_at.isoformat(),
        'updated_at': job.updated_at.isoformat(),
        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        'has_gif': bool(job.gif_relative_path),
    })


def api_timelapse_frames(request, job_id):
    """Return generated frame preview URLs for a timelapse job."""
    try:
        job = TimelapseJob.objects.get(pk=job_id)
    except TimelapseJob.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)

    return JsonResponse({
        'job_id': job.id,
        'status': job.status,
        'start_year': job.start_year,
        'end_year': job.end_year,
        'frames': job.frame_urls,
    })


def api_timelapse_download(request, job_id):
    """Download the generated GIF for a completed timelapse job."""
    try:
        job = TimelapseJob.objects.select_related('wetland').get(pk=job_id)
    except TimelapseJob.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)

    if job.status != 'completed' or not job.gif_relative_path:
        return JsonResponse({'error': 'GIF not available for this job yet'}, status=409)

    gif_path = Path(settings.MEDIA_ROOT) / job.gif_relative_path
    if not gif_path.exists():
        return JsonResponse({'error': 'GIF file missing on server'}, status=410)

    return FileResponse(
        open(gif_path, 'rb'),
        as_attachment=True,
        filename=f"{job.wetland.name.lower().replace(' ', '_')}_{job.id}.gif",
        content_type='image/gif',
    )
