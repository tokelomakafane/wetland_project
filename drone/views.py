import json
import math
import os
import uuid
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from mapping.models import Wetland

try:
    from PIL import Image, ImageStat, ExifTags  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - handled at runtime if Pillow unavailable
    Image = None
    ImageStat = None
    ExifTags = None


def drone_upload_view(request):
    _seed_static_wetlands_into_db()
    wetlands = Wetland.objects.filter(is_current=True).order_by('name')
    return render(request, 'drone/drone_upload.html', {
        'active_page': 'drone_upload',
        'wetlands': wetlands,
    })


def api_drone_image_analysis(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({'success': False, 'error': 'Image file is required'}, status=400)

    file_name = image_file.name or ''
    if not file_name.lower().endswith('.png'):
        return JsonResponse({'success': False, 'error': 'Only PNG images are supported for this workflow'}, status=400)

    raw_bytes = image_file.read()
    if not raw_bytes:
        return JsonResponse({'success': False, 'error': 'Uploaded image is empty'}, status=400)

    try:
        image_features = _preprocess_png_features(raw_bytes)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    geotag = _extract_gps_from_image(raw_bytes)
    wetland_id = request.POST.get('wetland_id')
    selected_wetland = None
    match_distance_km = None

    if wetland_id:
        try:
            selected_wetland = Wetland.objects.get(pk=int(wetland_id), is_current=True)
        except (Wetland.DoesNotExist, ValueError):
            return JsonResponse({'success': False, 'error': 'Selected wetland not found'}, status=404)
    elif geotag:
        selected_wetland, match_distance_km = _match_wetland_from_geotag(geotag['lat'], geotag['lon'])

    if selected_wetland is None:
        wetlands = list(
            Wetland.objects.filter(is_current=True)
            .values('id', 'name', 'village')
            .order_by('name')
        )
        return JsonResponse({
            'success': False,
            'requires_wetland_selection': True,
            'error': 'Image is not geotagged or no nearby wetland was found. Please select an existing wetland.',
            'image_features': image_features,
            'geotag': geotag,
            'wetlands': wetlands,
        }, status=400)

    today = timezone.now()
    rel_path = os.path.join('wetland_uploads', str(today.year), f'{today.month:02d}', f'{uuid.uuid4().hex}.png')
    saved_path = default_storage.save(rel_path, ContentFile(raw_bytes))
    saved_url = f"{settings.MEDIA_URL}{str(saved_path).replace('\\', '/')}"

    analysis_metrics = _derive_uploaded_image_metrics(image_features)
    inference = _infer_wetland_state(image_features, analysis_metrics)

    if not _looks_like_wetland_scene(image_features, analysis_metrics):
        return JsonResponse({
            'success': False,
            'error': 'This image does not look like a wetland scene. Please upload a wetland photo, not a person or portrait.',
            'image_features': image_features,
            'analysis_metrics': analysis_metrics,
        }, status=400)

    metadata = selected_wetland.metadata or {}
    history = metadata.get('image_analysis_history', [])
    history.append({
        'timestamp': timezone.now().isoformat(),
        'file': saved_url,
        'geotag': geotag,
        'image_features': image_features,
        'analysis_metrics': analysis_metrics,
        'inference': inference,
    })
    metadata['image_analysis_history'] = history[-10:]
    metadata['last_image_analysis'] = history[-1]

    selected_wetland.risk_level = inference['risk_level']
    selected_wetland.status = inference['status']
    selected_wetland.date_last_monitored = timezone.now()
    selected_wetland.metadata = metadata
    selected_wetland.save()

    return JsonResponse({
        'success': True,
        'message': 'Image processed and wetland status updated',
        'wetland': {
            'id': selected_wetland.id,
            'name': selected_wetland.name,
            'village': selected_wetland.village,
            'status': selected_wetland.status,
            'risk_level': selected_wetland.risk_level,
        },
        'image_features': image_features,
        'analysis_metrics': analysis_metrics,
        'inference': inference,
        'geotag': geotag,
        'match_distance_km': match_distance_km,
        'uploaded_image_url': saved_url,
    })


def legacy_drone_upload_redirect(request):
    return redirect('drone:drone_upload')


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _ring_centroid(coords):
    if not coords:
        return None
    total_lat = 0.0
    total_lon = 0.0
    count = 0
    for point in coords:
        if len(point) >= 2:
            total_lon += point[0]
            total_lat += point[1]
            count += 1
    if count == 0:
        return None
    return total_lat / count, total_lon / count


def _geometry_centroid(geometry):
    if not geometry:
        return None
    geom_type = geometry.get('type')
    coords = geometry.get('coordinates')
    if geom_type == 'Polygon' and coords:
        return _ring_centroid(coords[0])
    if geom_type == 'MultiPolygon' and coords and coords[0]:
        return _ring_centroid(coords[0][0])
    return None


def _extract_gps_from_image(raw_bytes):
    if Image is None or ExifTags is None:
        return None
    try:
        img = Image.open(BytesIO(raw_bytes))
        exif = img.getexif()
        if not exif:
            return None

        gps_tag_id = None
        for key, value in ExifTags.TAGS.items():
            if value == 'GPSInfo':
                gps_tag_id = key
                break
        if gps_tag_id is None:
            return None

        gps_info = exif.get(gps_tag_id)
        if not gps_info:
            return None

        gps_data = {}
        for key, value in gps_info.items():
            gps_data[ExifTags.GPSTAGS.get(key, key)] = value

        lat = gps_data.get('GPSLatitude')
        lat_ref = gps_data.get('GPSLatitudeRef')
        lon = gps_data.get('GPSLongitude')
        lon_ref = gps_data.get('GPSLongitudeRef')
        if not (lat and lat_ref and lon and lon_ref):
            return None

        def _to_deg(value):
            d = float(value[0])
            m = float(value[1])
            s = float(value[2])
            return d + (m / 60.0) + (s / 3600.0)

        lat_value = _to_deg(lat)
        lon_value = _to_deg(lon)
        if str(lat_ref).upper().startswith('S'):
            lat_value = -lat_value
        if str(lon_ref).upper().startswith('W'):
            lon_value = -lon_value

        return {'lat': round(lat_value, 6), 'lon': round(lon_value, 6)}
    except Exception:
        return None


def _preprocess_png_features(raw_bytes):
    if Image is None or ImageStat is None:
        raise RuntimeError('Pillow is required for image preprocessing. Please install Pillow.')

    img = Image.open(BytesIO(raw_bytes)).convert('RGB')
    width, height = img.size
    working = img.copy()
    working.thumbnail((512, 512))
    stat = ImageStat.Stat(working)

    mean_r, mean_g, mean_b = stat.mean
    std_r, std_g, std_b = stat.stddev
    brightness = (mean_r + mean_g + mean_b) / 3.0
    texture = (std_r + std_g + std_b) / 3.0
    green_ratio = mean_g / max((mean_r + mean_g + mean_b), 1e-6)

    return {
        'width': width,
        'height': height,
        'mean_rgb': [round(mean_r, 2), round(mean_g, 2), round(mean_b, 2)],
        'brightness': round(brightness, 2),
        'texture': round(texture, 2),
        'green_ratio': round(green_ratio, 4),
    }


def _match_wetland_from_geotag(lat, lon, max_distance_km=15.0):
    best_wetland = None
    best_distance = None
    for wetland in Wetland.objects.filter(is_current=True):
        try:
            geometry = json.loads(wetland.geometry) if isinstance(wetland.geometry, str) else wetland.geometry
            if geometry.get('type') == 'Feature':
                geometry = geometry.get('geometry')
            centroid = _geometry_centroid(geometry)
            if not centroid:
                continue
            distance = _haversine_km(lat, lon, centroid[0], centroid[1])
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_wetland = wetland
        except Exception:
            continue

    if best_wetland is None or best_distance is None or best_distance > max_distance_km:
        return None, None
    return best_wetland, round(best_distance, 2)


def _derive_uploaded_image_metrics(image_features):
    mean_r, mean_g, mean_b = image_features['mean_rgb']
    vegetation_proxy = round(max(0.0, mean_g - max(mean_r, mean_b)) / 255.0, 4)
    dryness_proxy = round(max(0.0, ((mean_r + mean_b) / 2.0) - mean_g) / 255.0, 4)
    color_balance = round((mean_g / max(mean_r + mean_b, 1e-6)), 4)

    return {
        'vegetation_proxy': vegetation_proxy,
        'dryness_proxy': dryness_proxy,
        'color_balance': color_balance,
        'brightness_index': round(image_features['brightness'] / 255.0, 4),
        'texture_index': round(min(image_features['texture'] / 128.0, 1.0), 4),
    }


def _infer_wetland_state(image_features, analysis_metrics):
    score = 0

    green_ratio = image_features['green_ratio']
    brightness = image_features['brightness']
    texture = image_features['texture']
    vegetation_proxy = analysis_metrics['vegetation_proxy']
    dryness_proxy = analysis_metrics['dryness_proxy']

    if vegetation_proxy > 0.08:
        score += 2
    elif vegetation_proxy > 0.03:
        score += 1

    if dryness_proxy > 0.12:
        score += 1

    if texture > 40:
        score += 2
    elif texture > 25:
        score += 1

    if green_ratio < 0.30:
        score += 1
    if brightness > 170:
        score += 1

    if score >= 5:
        risk_level = 'high'
        status = 'monitoring'
        label = 'High risk'
    elif score >= 3:
        risk_level = 'moderate'
        status = 'monitoring'
        label = 'Moderate risk'
    else:
        risk_level = 'low'
        status = 'active'
        label = 'Low risk'

    return {
        'score': score,
        'risk_level': risk_level,
        'status': status,
        'label': label,
    }


def _looks_like_wetland_scene(image_features, analysis_metrics):
    vegetation_proxy = analysis_metrics['vegetation_proxy']
    dryness_proxy = analysis_metrics['dryness_proxy']
    green_ratio = image_features['green_ratio']
    brightness = image_features['brightness']
    texture = image_features['texture']

    wetland_score = 0.0

    if vegetation_proxy >= 0.05:
        wetland_score += 1.5
    if green_ratio >= 0.32:
        wetland_score += 1.0
    if dryness_proxy <= 0.14:
        wetland_score += 1.0
    if texture <= 70:
        wetland_score += 0.5
    if brightness <= 210:
        wetland_score += 0.5

    return wetland_score >= 2.5


def _load_static_wetlands_geojson():
    json_path = Path(__file__).resolve().parent.parent / 'mapping' / 'wetland_polygons.json'
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if data.get('type') == 'GeometryCollection':
            features = []
            for i, geom in enumerate(data.get('geometries', [])):
                feature = {
                    'type': 'Feature',
                    'geometry': geom,
                    'properties': {
                        'name': f'Wetland {i}',
                        'village': '',
                        'source': 'historical_static',
                        'is_static': True,
                    }
                }
                features.append(feature)
            return {'type': 'FeatureCollection', 'features': features}

        return data
    except FileNotFoundError:
        return {'type': 'FeatureCollection', 'features': []}


def _seed_static_wetlands_into_db():
    static_geojson = _load_static_wetlands_geojson()
    for i, feature in enumerate(static_geojson.get('features', [])):
        props = feature.get('properties', {}) or {}
        geometry = feature.get('geometry')
        if not geometry:
            continue

        name = props.get('name') or f'Wetland {i}'
        Wetland.objects.get_or_create(
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
