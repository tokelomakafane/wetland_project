import json
import os
from pathlib import Path

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.http import FileResponse
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.views.decorators.csrf import ensure_csrf_cookie
from django.conf import settings
from django import forms as django_forms
from django.db import models
from django.urls import reverse

from .ee_utils import initialize_ee
from .models import CommunityInput, Wetland
from timelapse.tasks import start_timelapse_job
from wetlands.views import _seed_static_wetlands_into_db


def _ee_json_error(exc):
    """Return a clear JSON response for Earth Engine failures."""
    message = str(exc)
    project = getattr(settings, 'EE_PROJECT', '')
    details = {
        'error': message,
        'ee_project': project,
    }

    if 'USER_PROJECT_DENIED' in message or 'required permission' in message.lower():
        details['hint'] = (
            'Grant your account roles/serviceusage.serviceUsageConsumer on the EE project '
            f'({project}) or set EE_PROJECT to a project you can access.'
        )
        return JsonResponse(details, status=503)

    return JsonResponse(details, status=500)


# ── Wetland sample sites (same data as in GEE script) ──────────────
SAMPLE_SITES = [
    {"sample_number": 23, "village": "Ha-Moroane libeng sa masole", "elevation": 1827, "lat": -29.28004, "lng": 27.66464},
    {"sample_number": 27, "village": "Oxbow", "elevation": 2523, "lat": -28.76356, "lng": 28.62816},
    {"sample_number": 32, "village": "Literapeng", "elevation": 1696, "lat": -28.80034, "lng": 28.21499},
    {"sample_number": 35, "village": "SNP", "elevation": 2541, "lat": -29.86857, "lng": 29.09700},
    {"sample_number": 36, "village": "Edward Dam", "elevation": 2381, "lat": -29.86067, "lng": 29.04599},
    {"sample_number": 40, "village": "Rama's Gate", "elevation": 2296, "lat": -30.04973, "lng": 28.92411},
    {"sample_number": 43, "village": "Lets'eng La Letsie", "elevation": None, "lat": -30.30846, "lng": 28.16463},
    {"sample_number": 47, "village": "Semonkong", "elevation": 2210, "lat": -29.86027, "lng": 28.06483},
    {"sample_number": 48, "village": "Semonkong", "elevation": 2590, "lat": -29.75008, "lng": 27.95681},
    {"sample_number": 53, "village": "Mokopung ha-Lepekola", "elevation": 2214, "lat": -29.98040, "lng": 28.15933},
    {"sample_number": 59, "village": "White Hill ha-Sehapi (Qacha's Neck)", "elevation": 1574, "lat": -30.06126, "lng": 28.47229},
    {"sample_number": 62, "village": "Quthing Ha-Rantema Lekhalong", "elevation": 2350, "lat": -30.17489, "lng": 28.00933},
    {"sample_number": 65, "village": "Leribe tsikoane Lefikeng", "elevation": 1554, "lat": -28.88662, "lng": 27.98529},
    {"sample_number": 70, "village": "Thaba-Tseka Mats'oana", "elevation": None, "lat": -29.51818, "lng": 28.43349},
    {"sample_number": 71, "village": "Thaba-tseka Ha-cheche Mantsonyane", "elevation": 2554, "lat": -29.53544, "lng": 28.23498},
    {"sample_number": 76, "village": "Maseru Nazareth Toll-gate", "elevation": 1792, "lat": -29.40787, "lng": 27.81029},
    {"sample_number": 80, "village": "Maseru Mohlakeng Mokema", "elevation": 1580, "lat": -29.46375, "lng": 27.63583},
    {"sample_number": 84, "village": "Berea Mathoane Ha-Khohlooa", "elevation": 1750, "lat": -29.32343, "lng": 27.72630},
    {"sample_number": 85, "village": "Mohale's Hoek Ha-Makhathe", "elevation": 1481, "lat": -30.05519, "lng": 27.40725},
    {"sample_number": 92, "village": "Mafeteng Tsita's Nek", "elevation": 1614, "lat": -29.71037, "lng": 27.28346},
    {"sample_number": 95, "village": "Mafeteng Ts'akholo", "elevation": 1568, "lat": -29.66871, "lng": 27.96222},
]


def index(request):
    """Redirect root to login page."""
    return redirect('mapping:login')


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            try:
                role = user.profile.role
            except Exception:
                role = None
            if role == 'community_member':
                return redirect('mapping:community_portal')
            return redirect('mapping:dashboard')
        return render(request, 'mapping/login.html', {'error': 'Invalid username or password'})
    return render(request, 'mapping/login.html')


def logout_view(request):
    logout(request)
    return redirect('mapping:login')


def dashboard(request):
    """Render the main wetland map page."""
    return render(request, 'mapping/dashboard.html', {'active_page': 'mapping'})


def monitor_view(request):
    import json as _json
    from .models import Wetland

    risk_to_status = {'low': 'healthy', 'moderate': 'critical', 'high': 'severe', 'unknown': 'healthy'}
    obs_to_threat = {'erosion': 'erosion', 'invasive_species': 'species', 'grazing': 'trampling'}

    def _centroid(geometry_str):
        try:
            geom = _json.loads(geometry_str)
            if geom.get('type') == 'Feature':
                geom = geom['geometry']
            coords = geom.get('coordinates', [])
            if geom.get('type') == 'Polygon' and coords:
                ring = coords[0]
                return (
                    round(sum(c[1] for c in ring) / len(ring), 6),
                    round(sum(c[0] for c in ring) / len(ring), 6),
                )
        except Exception:
            pass
        return None, None

    wetlands_data = []
    qs = Wetland.objects.filter(is_current=True).prefetch_related('monitoring_records', 'community_inputs')
    for w in qs:
        lat, lng = _centroid(w.geometry)
        if lat is None:
            continue

        record = w.monitoring_records.order_by('-year').first()

        if record and record.risk_class:
            status = risk_to_status.get(record.risk_class, risk_to_status.get(w.risk_level, 'healthy'))
        else:
            status = risk_to_status.get(w.risk_level, 'healthy')

        ndvi_val = round(record.ndvi_mean, 2) if record and record.ndvi_mean is not None else None
        record_year = record.year if record else None

        latest_input = w.community_inputs.filter(severity__in=['critical', 'warning']).order_by('-created_at').first()
        threat = obs_to_threat.get(latest_input.observation) if latest_input else None

        note = w.description or (record.notes if record else '') or ''

        wetlands_data.append({
            'id': w.id,
            'name': w.name,
            'district': w.village or 'Lesotho',
            'lat': lat,
            'lng': lng,
            'status': status,
            'ndvi': ndvi_val,
            'area_ha': w.area_ha,
            'threat': threat,
            'note': note,
            'record_year': record_year,
            'health_score': None,
            'health_label': None,
        })

    return render(request, 'mapping/monitor.html', {
        'active_page': 'monitor',
        'wetlands_json': _json.dumps(wetlands_data),
        'wetland_count': len(wetlands_data),
    })


def community_portal_view(request):
    """Standalone report form for Community Member role."""
    if not request.user.is_authenticated:
        return redirect('mapping:login')
    wetlands = Wetland.objects.filter(is_current=True).order_by('name').values('id', 'name', 'village')
    return render(request, 'mapping/community_portal.html', {'wetlands': list(wetlands)})


def alerts_view(request):
    return render(request, 'mapping/alerts.html', {'active_page': 'alerts'})


def api_early_warning_alerts(request):
    """Compatibility wrapper that delegates to the dedicated early_warning app."""
    from early_warning.views import api_early_warning_alerts as impl

    return impl(request)


def api_mark_early_warning_alert_read(request):
    """Compatibility wrapper that delegates alert read-state persistence."""
    from early_warning.views import mark_early_warning_alert_read as impl

    return impl(request)


@ensure_csrf_cookie
def community_view(request):
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
        'active_page': 'community',
        'wetlands_geojson': json.dumps({'type': 'FeatureCollection', 'features': features}),
    }
    return render(request, 'mapping/community.html', context)


def community_inputs_log_view(request):
    """Paginated log of community inputs — community members see only their own."""
    severity_filter = request.GET.get('severity', '')
    observation_filter = request.GET.get('observation', '')
    wetland_filter = request.GET.get('wetland', '')

    qs = CommunityInput.objects.select_related('wetland').order_by('-created_at')

    # Community members may only see their own submissions
    try:
        role = request.user.profile.role
    except Exception:
        role = None
    if role == 'community_member':
        own_name = request.user.get_full_name() or request.user.username
        qs = qs.filter(submitted_by=own_name)

    if severity_filter:
        qs = qs.filter(severity=severity_filter)
    if observation_filter:
        qs = qs.filter(observation=observation_filter)
    if wetland_filter:
        try:
            qs = qs.filter(wetland_id=int(wetland_filter))
        except (TypeError, ValueError):
            pass

    paginator = Paginator(qs, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    wetlands = Wetland.objects.filter(is_current=True).order_by('name').values('id', 'name')

    return render(request, 'mapping/community_inputs_log.html', {
        'active_page': 'community',
        'page_obj': page_obj,
        'wetlands': list(wetlands),
        'severity_filter': severity_filter,
        'observation_filter': observation_filter,
        'wetland_filter': wetland_filter,
        'severity_choices': CommunityInput.SEVERITY_CHOICES,
        'observation_choices': CommunityInput.OBSERVATION_CHOICES,
        'total_count': paginator.count,
    })


def api_create_community_input(request):
    """Persist a community input report for a selected wetland."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

    try:
        wetland_id = int(payload.get('wetland_id'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid wetland_id'}, status=400)

    observation = (payload.get('observation') or '').strip()
    severity = (payload.get('severity') or '').strip()
    comments = (payload.get('comments') or '').strip()

    valid_observations = {choice[0] for choice in CommunityInput.OBSERVATION_CHOICES}
    valid_severities = {choice[0] for choice in CommunityInput.SEVERITY_CHOICES}

    if observation not in valid_observations:
        return JsonResponse({'error': 'Invalid observation value'}, status=400)
    if severity not in valid_severities:
        return JsonResponse({'error': 'Invalid severity value'}, status=400)
    if not comments:
        return JsonResponse({'error': 'Comments are required'}, status=400)

    try:
        wetland = Wetland.objects.get(pk=wetland_id, is_current=True)
    except Wetland.DoesNotExist:
        return JsonResponse({'error': 'Wetland not found'}, status=404)

    submitted_by = ''
    if getattr(request, 'user', None) and request.user.is_authenticated:
        submitted_by = request.user.get_full_name() or request.user.username

    entry = CommunityInput.objects.create(
        wetland=wetland,
        observation=observation,
        severity=severity,
        comments=comments,
        submitted_by=submitted_by,
    )

    return JsonResponse({
        'id': entry.id,
        'message': 'Community input saved successfully',
        'wetland': wetland.name,
        'observation': entry.observation,
        'severity': entry.severity,
        'comments': entry.comments,
        'created_at': entry.created_at.isoformat(),
    }, status=201)


def _serialize_community_input(entry):
    return {
        'id': entry.id,
        'wetland_id': entry.wetland_id,
        'wetland': entry.wetland.name,
        'observation': entry.observation,
        'severity': entry.severity,
        'comments': entry.comments,
        'submitted_by': entry.submitted_by,
        'created_at': entry.created_at.isoformat(),
        'updated_at': entry.updated_at.isoformat(),
    }


def api_list_community_inputs(request):
    """List community inputs, optionally filtered by wetland_id."""
    if request.method != 'GET':
        return JsonResponse({'error': 'GET required'}, status=405)

    queryset = CommunityInput.objects.select_related('wetland').order_by('-created_at')
    wetland_id = request.GET.get('wetland_id')
    if wetland_id:
        try:
            queryset = queryset.filter(wetland_id=int(wetland_id))
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Invalid wetland_id'}, status=400)

    return JsonResponse({'results': [_serialize_community_input(item) for item in queryset]})


def api_get_community_input(request, input_id):
    """Retrieve a single community input by id."""
    if request.method != 'GET':
        return JsonResponse({'error': 'GET required'}, status=405)

    try:
        entry = CommunityInput.objects.select_related('wetland').get(pk=input_id)
    except CommunityInput.DoesNotExist:
        return JsonResponse({'error': 'Community input not found'}, status=404)

    return JsonResponse(_serialize_community_input(entry))


def api_update_community_input(request, input_id):
    """Update an existing community input."""
    if request.method not in ('PUT', 'PATCH'):
        return JsonResponse({'error': 'PUT or PATCH required'}, status=405)

    try:
        entry = CommunityInput.objects.select_related('wetland').get(pk=input_id)
    except CommunityInput.DoesNotExist:
        return JsonResponse({'error': 'Community input not found'}, status=404)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

    if 'observation' in payload:
        observation = (payload.get('observation') or '').strip()
        valid_observations = {choice[0] for choice in CommunityInput.OBSERVATION_CHOICES}
        if observation not in valid_observations:
            return JsonResponse({'error': 'Invalid observation value'}, status=400)
        entry.observation = observation

    if 'severity' in payload:
        severity = (payload.get('severity') or '').strip()
        valid_severities = {choice[0] for choice in CommunityInput.SEVERITY_CHOICES}
        if severity not in valid_severities:
            return JsonResponse({'error': 'Invalid severity value'}, status=400)
        entry.severity = severity

    if 'comments' in payload:
        comments = (payload.get('comments') or '').strip()
        if not comments:
            return JsonResponse({'error': 'Comments are required'}, status=400)
        entry.comments = comments

    if 'wetland_id' in payload:
        try:
            wetland_id = int(payload.get('wetland_id'))
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Invalid wetland_id'}, status=400)
        try:
            wetland = Wetland.objects.get(pk=wetland_id, is_current=True)
        except Wetland.DoesNotExist:
            return JsonResponse({'error': 'Wetland not found'}, status=404)
        entry.wetland = wetland

    entry.save()
    return JsonResponse(_serialize_community_input(entry))


def api_delete_community_input(request, input_id):
    """Delete an existing community input."""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE required'}, status=405)

    try:
        entry = CommunityInput.objects.get(pk=input_id)
    except CommunityInput.DoesNotExist:
        return JsonResponse({'error': 'Community input not found'}, status=404)

    entry.delete()
    return JsonResponse({'message': 'Community input deleted'})


def users_view(request):
    from django.contrib.auth.models import User as AuthUser
    from users.models import UserProfile

    # Only system admins may access this page
    try:
        role = request.user.profile.role
    except Exception:
        role = None
    if not request.user.is_authenticated or role != 'system_admin':
        return redirect('mapping:dashboard')

    error = None
    success = None

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            new_role = request.POST.get('role', 'community_member').strip()

            if not username or not password:
                error = 'Username and password are required.'
            elif AuthUser.objects.filter(username=username).exists():
                error = f'Username "{username}" is already taken.'
            else:
                new_user = AuthUser.objects.create_user(
                    username=username, password=password,
                    first_name=first_name, last_name=last_name, email=email,
                    is_staff=(new_role == 'system_admin'),
                    is_superuser=(new_role == 'system_admin'),
                )
                UserProfile.objects.create(user=new_user, role=new_role)
                success = f'User "{username}" created successfully.'

        elif action == 'delete':
            uid = request.POST.get('user_id')
            if str(uid) == str(request.user.id):
                error = 'You cannot delete your own account.'
            else:
                try:
                    AuthUser.objects.get(pk=uid).delete()
                    success = 'User deleted.'
                except AuthUser.DoesNotExist:
                    error = 'User not found.'

    users = AuthUser.objects.select_related('profile').order_by('username')
    role_choices = UserProfile.ROLE_CHOICES
    return render(request, 'mapping/users.html', {
        'active_page': 'users',
        'users': users,
        'role_choices': role_choices,
        'error': error,
        'success': success,
    })


def ee_tile_url(request):
    """Return Earth Engine map tile URLs for the classification layers."""
    import ee

    asset_id = getattr(settings, 'EE_ASSET_ID', '')

    try:
        initialize_ee()
        # Load the classified image from GEE Asset
        classified = ee.Image(asset_id)

        # Full classification layer
        full_vis = classified.visualize(
            min=0, max=1,
            palette=['d9c99e', '0571b0']
        )
        full_map = full_vis.getMapId()

        # Wetland-only layer (class 1)
        wetland_only = classified.eq(1).selfMask().visualize(
            min=1, max=1,
            palette=['00ffff']
        )
        wetland_map = wetland_only.getMapId()

        # NDVI from Sentinel-2 composite
        lesotho = ee.FeatureCollection('FAO/GAUL/2015/level0') \
            .filter(ee.Filter.eq('ADM0_NAME', 'Lesotho'))
        study_area = lesotho.geometry().simplify(100)

        s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filter(ee.Filter.calendarRange(8, 10, 'month')) \
            .filterDate('2022-01-01', '2023-12-31') \
            .filterBounds(study_area) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10)) \
            .median() \
            .clip(study_area)

        ndvi = s2.normalizedDifference(['B8', 'B4']).rename('NDVI')
        ndvi_vis = ndvi.visualize(min=-0.2, max=0.8, palette=['white', 'green'])
        ndvi_map = ndvi_vis.getMapId()

        ndwi = s2.normalizedDifference(['B3', 'B8']).rename('NDWI')
        ndwi_vis = ndwi.visualize(
            min=-0.5, max=0.5,
            palette=['brown', 'white', 'blue']
        )
        ndwi_map = ndwi_vis.getMapId()

        return JsonResponse({
            'classification': full_map['tile_fetcher'].url_format,
            'wetlands': wetland_map['tile_fetcher'].url_format,
            'ndvi': ndvi_map['tile_fetcher'].url_format,
            'ndwi': ndwi_map['tile_fetcher'].url_format,
        })

    except Exception as e:
        return _ee_json_error(e)


def wetland_stats(request):
    """Return wetland area statistics."""
    import ee

    asset_id = getattr(settings, 'EE_ASSET_ID', '')

    try:
        initialize_ee()
        classified = ee.Image(asset_id)
        lesotho = ee.FeatureCollection('FAO/GAUL/2015/level0') \
            .filter(ee.Filter.eq('ADM0_NAME', 'Lesotho'))
        study_area = lesotho.geometry().simplify(100)

        # Wetland area
        wetland_area = classified.eq(1).multiply(ee.Image.pixelArea()).divide(10000)
        stats = wetland_area.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=study_area,
            scale=100,
            maxPixels=1e10,
            tileScale=16,
            bestEffort=True
        )

        # Lesotho total area
        total_area = study_area.area().divide(10000)

        return JsonResponse({
            'wetland_area_ha': stats.getInfo().get('classification', 0),
            'total_area_ha': total_area.getInfo(),
            'sample_sites': len(SAMPLE_SITES),
        })

    except Exception as e:
        return _ee_json_error(e)


def sample_sites(request):
    """Return wetland sample site data as GeoJSON."""
    features = []
    for site in SAMPLE_SITES:
        features.append({
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [site['lng'], site['lat']],
            },
            'properties': {
                'sample_number': site['sample_number'],
                'village': site['village'],
                'elevation': site['elevation'],
            }
        })

    return JsonResponse({
        'type': 'FeatureCollection',
        'features': features,
    })


# ── LST Monitoring helpers ─────────────────────────────────────────

def _calculate_lst(image):
    """Apply LST calculation to a Landsat 8 TOA image (server-side EE)."""
    thermal = image.select('B10')
    ndvi = image.normalizedDifference(['B5', 'B4'])
    emissivity = ndvi.expression('0.004 * V + 0.986', {'V': ndvi})
    lst = thermal.expression(
        'Tb / (1 + (0.00115 * Tb / 1.4388) * log(emissivity)) - 273.15',
        {'Tb': thermal, 'emissivity': emissivity}
    ).rename('LST')
    return image.addBands(lst)


def _get_sample_sites_fc():
    """Build EE FeatureCollection of sample sites with 500 m buffers."""
    import ee
    features = []
    for s in SAMPLE_SITES:
        feat = ee.Feature(
            ee.Geometry.Point([s['lng'], s['lat']]).buffer(500),
            {
                'sample_number': s['sample_number'],
                'village': s['village'],
                'elevation': s['elevation'] if s['elevation'] else 0,
                'lat': s['lat'],
                'lng': s['lng'],
            }
        )
        features.append(feat)
    return ee.FeatureCollection(features)


def _classify_health(temp):
    """Classify an LST value into a health category string."""
    if temp is None:
        return 'No Data'
    if temp <= 18:
        return 'Healthy'
    if temp <= 22:
        return 'Stressed'
    if temp <= 26:
        return 'Critical'
    return 'Severe'


# ── LST views ──────────────────────────────────────────────────────

def lst_view(request):
    """Render the LST monitoring page."""
    return render(request, 'mapping/lst_monitor.html', {'active_page': 'lst'})


def wetland_lst(request):
    """Return per-site mean LST for a given year (Oct → Mar summer)."""
    import ee

    year = request.GET.get('year', '2023')
    try:
        year = int(year)
        if year < 2013 or year > 2024:
            return JsonResponse({'error': 'Year must be between 2013 and 2024'}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid year parameter'}, status=400)

    try:
        initialize_ee()
        sites = _get_sample_sites_fc()
        start = ee.Date.fromYMD(year, 10, 1)
        end = ee.Date.fromYMD(year + 1, 3, 31)

        col = ee.ImageCollection('LANDSAT/LC08/C02/T1_TOA') \
            .filterDate(start, end) \
            .filterBounds(sites.geometry())

        mean_lst = col.map(_calculate_lst).select('LST').mean()

        # Generate tile URL for the LST raster overlay
        lst_vis = mean_lst.visualize(
            min=10, max=30,
            palette=['#313695', '#4575b4', '#74add1', '#abd9e9',
                     '#fee090', '#fdae61', '#f46d43', '#d73027', '#a50026']
        )
        lst_map = lst_vis.getMapId()
        tile_url = lst_map['tile_fetcher'].url_format

        results = mean_lst.reduceRegions(
            collection=sites,
            reducer=ee.Reducer.mean(),
            scale=30,
        )

        data = results.getInfo()

        site_data = []
        for feature in data['features']:
            props = feature['properties']
            temp = props.get('mean')
            if temp is not None:
                temp = round(temp, 2)
            site_data.append({
                'sample_number': props.get('sample_number'),
                'village': props.get('village'),
                'elevation': props.get('elevation'),
                'lat': props.get('lat'),
                'lng': props.get('lng'),
                'temperature': temp,
                'health': _classify_health(temp),
            })

        return JsonResponse({'year': year, 'sites': site_data, 'tile_url': tile_url})

    except Exception as e:
        return _ee_json_error(e)


def wetland_lst_predict(request):
    """Return historical per-site LST (2013-2024) + linear predictions (2025-2030)."""
    import ee

    try:
        initialize_ee()
        sites = _get_sample_sites_fc()
        years = list(range(2013, 2025))

        # Stack annual mean LST bands + linear-fit trend in one image
        stacked = None
        annual_images = []
        for yr in years:
            start = ee.Date.fromYMD(yr, 10, 1)
            end = ee.Date.fromYMD(yr + 1, 3, 31)
            col = ee.ImageCollection('LANDSAT/LC08/C02/T1_TOA') \
                .filterDate(start, end) \
                .filterBounds(sites.geometry())
            mean_lst = col.map(_calculate_lst).select('LST').mean()
            renamed = mean_lst.rename('LST_{}'.format(yr))
            stacked = renamed if stacked is None else stacked.addBands(renamed)
            time_band = ee.Image.constant(yr).float().rename('year')
            annual_images.append(mean_lst.addBands(time_band).set('year', yr))

        # Linear fit: LST = offset + scale * year
        annual_col = ee.ImageCollection(annual_images)
        trend = annual_col.select(['year', 'LST']).reduce(ee.Reducer.linearFit())
        stacked = stacked.addBands(trend)

        # Single server call for everything
        results = stacked.reduceRegions(
            collection=sites,
            reducer=ee.Reducer.mean(),
            scale=30,
        )
        data = results.getInfo()

        response_data = []
        for feature in data['features']:
            props = feature['properties']
            historical = {}
            for yr in years:
                val = props.get('LST_{}'.format(yr))
                historical[str(yr)] = round(val, 2) if val is not None else None

            slope = props.get('scale')
            intercept = props.get('offset')
            predictions = {}
            if slope is not None and intercept is not None:
                for yr in range(2025, 2031):
                    predictions[str(yr)] = round(intercept + slope * yr, 2)
                slope = round(slope, 4)

            response_data.append({
                'sample_number': props.get('sample_number'),
                'village': props.get('village'),
                'lat': props.get('lat'),
                'lng': props.get('lng'),
                'historical': historical,
                'slope': slope,
                'predictions': predictions,
            })

        return JsonResponse({'sites': response_data})

    except Exception as e:
        return _ee_json_error(e)


# ── Soil Erosion helpers ───────────────────────────────────────────

# Wetland names mapped by polygon index (matched by centroid proximity to sample sites)
WETLAND_NAMES = [
    'Mantsonyane',                   # 0
    'Oxbow',                         # 1
    'Literapeng',                    # 2
    'Leribe Lefikeng',               # 3
    'Ha-Moroane',                    # 4
    'Mathoane Ha-Khohlooa',          # 5
    'Nazareth Toll-gate',            # 6
    'Mohlakeng Mokema',              # 7
    'Mohlakeng Mokema East',         # 8
    'Mohlakeng Mokema South',        # 9
    'Mohlakeng Mokema West',         # 10
    "Mafeteng Tsita's Nek",          # 11
    "Mohale's Hoek Ha-Makhathe",     # 12
    "Lets'eng La Letsie",            # 13
    'Quthing Ha-Rantema',            # 14
    'Mokopung ha-Lepekola',          # 15
    'Semonkong',                     # 16
    'Semonkong (Upper)',             # 17
    "Thaba-Tseka Mats'oana",         # 18
    'White Hill ha-Sehapi',          # 19
    "Rama's Gate",                   # 20
    'Edward Dam',                    # 21
    'SNP',                           # 22
]


def _load_wetland_geometry():
    """Load wetland polygon geometry from JSON file."""
    import ee
    json_path = os.path.join(os.path.dirname(__file__), 'wetland_polygons.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        geojson = json.load(f)
    return ee.Geometry(geojson)


def _get_wetland_polygon_fc():
    """Build an EE FeatureCollection of individual wetland polygons."""
    import ee
    geom = _load_wetland_geometry()
    return ee.FeatureCollection(
        geom.geometries().map(lambda g: ee.Feature(ee.Geometry(g)))
    )


def _calculate_bsi(image):
    """Calculate BSI for a Sentinel-2 image (server-side)."""
    import ee
    bsi = image.expression(
        '((B11 + B4) - (B8 + B2)) / ((B11 + B4) + (B8 + B2))',
        {
            'B11': image.select('B11'),
            'B4':  image.select('B4'),
            'B8':  image.select('B8'),
            'B2':  image.select('B2'),
        }
    ).rename('BSI')
    return image.addBands(bsi)


def _calculate_ndvi(image):
    """Calculate NDVI for a Sentinel-2 image (server-side)."""
    import ee
    return image.addBands(image.normalizedDifference(['B8', 'B4']).rename('NDVI'))


def _get_rusle_factors():
    """Return static RUSLE factor images: K, LS, P."""
    import ee
    import math

    dem = ee.Image('USGS/SRTMGL1_003')
    slope_deg = ee.Terrain.slope(dem)
    slope_pct = slope_deg.tan().multiply(100)

    # LS-factor (Wischmeier & Smith 1978, cell-based)
    m_exp = ee.Image(0.2) \
        .where(slope_pct.gte(1).And(slope_pct.lt(3)), 0.2) \
        .where(slope_pct.gte(3).And(slope_pct.lt(5)), 0.3) \
        .where(slope_pct.gte(5), 0.5)
    slope_length_factor = ee.Image(30).divide(22.13).pow(m_exp)
    slope_steepness = ee.Image(0.065) \
        .add(slope_pct.multiply(0.045)) \
        .add(slope_pct.pow(2).multiply(0.0065))
    LS = slope_length_factor.multiply(slope_steepness).rename('LS')

    # K-factor from OpenLandMap soil texture class
    soil_texture = ee.Image('OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02').select('b0')
    K = ee.Image(0.032) \
        .where(soil_texture.eq(1),  0.022) \
        .where(soil_texture.eq(2),  0.025) \
        .where(soil_texture.eq(3),  0.032) \
        .where(soil_texture.eq(4),  0.035) \
        .where(soil_texture.eq(5),  0.038) \
        .where(soil_texture.eq(6),  0.030) \
        .where(soil_texture.eq(7),  0.040) \
        .where(soil_texture.eq(8),  0.042) \
        .where(soil_texture.eq(9),  0.028) \
        .where(soil_texture.eq(10), 0.045) \
        .where(soil_texture.eq(11), 0.020) \
        .where(soil_texture.eq(12), 0.013) \
        .rename('K')

    P = ee.Image(1).rename('P')

    return K, LS, P, slope_deg


def _get_r_factor(year, geom):
    """Calculate R-factor (Rainfall Erosivity) from CHIRPS for a year."""
    import ee
    start = ee.Date.fromYMD(year, 1, 1)
    end = ee.Date.fromYMD(year, 12, 31)
    chirps = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY') \
        .filterDate(start, end) \
        .filterBounds(geom)
    annual_p = chirps.sum().rename('annual_P')

    months = ee.List.sequence(1, 12)
    monthly_sq_sum = ee.ImageCollection(months.map(lambda m: (
        chirps.filterDate(
            ee.Date.fromYMD(year, ee.Number(m), 1),
            ee.Date.fromYMD(year, ee.Number(m), 1).advance(1, 'month')
        ).sum().rename('monthly_P').pow(2)
    ))).sum()

    R = monthly_sq_sum.divide(annual_p.max(1)).multiply(1.735).rename('R').clip(geom)
    return R


def _get_c_factor(ndvi):
    """Calculate C-factor from NDVI (Van der Knijff et al. 2000)."""
    import ee
    ndvi_clamped = ndvi.max(0).min(0.99)
    C = ndvi_clamped.multiply(2.0).divide(ee.Image(1.0).subtract(ndvi_clamped)) \
        .multiply(-1).exp() \
        .min(1).max(0) \
        .rename('C')
    return C


def _get_erosion_for_year(year):
    """Compute RUSLE soil loss (A = R x K x LS x C x P) for a given year."""
    import ee
    geom = _load_wetland_geometry()
    start = ee.Date.fromYMD(year, 1, 1)
    end = ee.Date.fromYMD(year, 12, 31)

    col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
        .filterDate(start, end) \
        .filterBounds(geom) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))

    ndvi = col.map(_calculate_ndvi).select('NDVI').mean().clip(geom)

    K, LS, P, slope_deg = _get_rusle_factors()
    R = _get_r_factor(year, geom)
    C = _get_c_factor(ndvi)

    soil_loss = R.multiply(K.clip(geom)) \
        .multiply(LS.clip(geom)) \
        .multiply(C) \
        .multiply(P.clip(geom)) \
        .rename('soil_loss')

    return soil_loss


def _classify_erosion(mean_soil_loss):
    """Classify mean soil loss (t/ha/yr) into a label."""
    if mean_soil_loss is None:
        return 'No Data'
    if mean_soil_loss >= 30:
        return 'Very High'
    if mean_soil_loss >= 15:
        return 'High'
    if mean_soil_loss >= 5:
        return 'Moderate'
    return 'Low'


# ── Erosion views ──────────────────────────────────────────────────

def erosion_view(request):
    """Render the soil erosion monitoring page."""
    return render(request, 'mapping/erosion_monitor.html', {'active_page': 'erosion'})


def timelapse_view(request):
    from timelapse.views import timelapse_view as impl
    return impl(request)


def _wetland_geometry_geojson(wetland):
    from timelapse.views import _wetland_geometry_geojson as impl
    return impl(wetland)


def _approximate_area_ha(geometry):
    from timelapse.views import _approximate_area_ha as impl
    return impl(geometry)


def _get_latest_timelapse_job(wetland):
    from timelapse.views import _get_latest_timelapse_job as impl
    return impl(wetland)


def _annual_timelapse_metrics(geometry, years, buffer_meters=0, cloud_threshold=20):
    from timelapse.views import _annual_timelapse_metrics as impl
    return impl(geometry, years, buffer_meters=buffer_meters, cloud_threshold=cloud_threshold)


def wetland_timelapse_view(request, pk):
    from timelapse.views import wetland_timelapse_view as impl
    return impl(request, pk)


def wetland_erosion(request):
    """Return per-polygon RUSLE soil loss for a given year + tile URL."""
    import ee

    year = request.GET.get('year', '2023')
    try:
        year = int(year)
        if year < 2017 or year > 2024:
            return JsonResponse({'error': 'Year must be between 2017 and 2024'}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid year parameter'}, status=400)

    try:
        initialize_ee()
        soil_loss = _get_erosion_for_year(year)
        polygons = _get_wetland_polygon_fc()

        # Tile URL for soil loss raster
        sl_vis = soil_loss.visualize(
            min=0, max=40,
            palette=['#1a9850', '#91cf60', '#fee08b', '#fc8d59', '#d73027', '#7f0000']
        )
        sl_map = sl_vis.getMapId()
        tile_url = sl_map['tile_fetcher'].url_format

        # Per-polygon stats
        stats = soil_loss.reduceRegions(
            collection=polygons,
            reducer=ee.Reducer.mean(),
            scale=10,
            tileScale=4,
        )

        data = stats.getInfo()

        polygon_data = []
        for i, feature in enumerate(data['features']):
            props = feature['properties']
            mean_sl = props.get('mean')
            if mean_sl is not None:
                mean_sl = round(mean_sl, 2)

            coords = feature['geometry']['coordinates'][0]
            lngs = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            centroid_lng = sum(lngs) / len(lngs)
            centroid_lat = sum(lats) / len(lats)

            polygon_data.append({
                'index': i,
                'name': WETLAND_NAMES[i] if i < len(WETLAND_NAMES) else 'Wetland ' + str(i),
                'mean_soil_loss': mean_sl,
                'status': _classify_erosion(mean_sl),
                'centroid_lat': round(centroid_lat, 6),
                'centroid_lng': round(centroid_lng, 6),
                'coordinates': coords,
            })

        return JsonResponse({
            'year': year,
            'tile_url': tile_url,
            'polygons': polygon_data,
        })

    except Exception as e:
        return _ee_json_error(e)


def wetland_erosion_compare(request):
    """Compare RUSLE soil loss between two years."""
    import ee

    year_a = request.GET.get('year_a', '2018')
    year_b = request.GET.get('year_b', '2023')
    try:
        year_a = int(year_a)
        year_b = int(year_b)
        for y in (year_a, year_b):
            if y < 2017 or y > 2024:
                return JsonResponse({'error': 'Years must be between 2017 and 2024'}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid year parameter'}, status=400)

    try:
        initialize_ee()
        sl_a = _get_erosion_for_year(year_a)
        sl_b = _get_erosion_for_year(year_b)
        polygons = _get_wetland_polygon_fc()

        diff = sl_b.subtract(sl_a).rename('soil_loss_change')

        diff_vis = diff.visualize(
            min=-20, max=20,
            palette=['#1a9850', '#91cf60', '#ffffbf', '#fc8d59', '#d73027']
        )
        diff_map = diff_vis.getMapId()
        tile_url = diff_map['tile_fetcher'].url_format

        stats = diff.reduceRegions(
            collection=polygons,
            reducer=ee.Reducer.mean(),
            scale=10,
            tileScale=4,
        )
        data = stats.getInfo()

        changes = []
        for i, feature in enumerate(data['features']):
            mean_change = feature['properties'].get('mean')
            if mean_change is not None:
                mean_change = round(mean_change, 2)
            direction = 'stable'
            if mean_change is not None:
                if mean_change > 1:
                    direction = 'worsening'
                elif mean_change < -1:
                    direction = 'improving'
            changes.append({
                'index': i,
                'name': WETLAND_NAMES[i] if i < len(WETLAND_NAMES) else 'Wetland ' + str(i),
                'mean_change': mean_change,
                'direction': direction,
            })

        return JsonResponse({
            'year_a': year_a,
            'year_b': year_b,
            'tile_url': tile_url,
            'changes': changes,
        })

    except Exception as e:
        return _ee_json_error(e)


def wetland_erosion_predict(request):
    """Return RUSLE soil loss trend (2017-2024) + predictions (2025-2030) per polygon."""
    import ee

    try:
        initialize_ee()
        geom = _load_wetland_geometry()
        polygons = _get_wetland_polygon_fc()
        years = list(range(2017, 2025))

        # Build annual soil loss images + linear fit
        stacked = None
        annual_images = []
        for yr in years:
            sl = _get_erosion_for_year(yr)
            renamed = sl.rename('SL_{}'.format(yr))
            stacked = renamed if stacked is None else stacked.addBands(renamed)
            time_band = ee.Image.constant(yr).float().rename('year')
            annual_images.append(sl.addBands(time_band).set('year', yr))

        # Linear fit: soil_loss = offset + scale * year
        annual_col = ee.ImageCollection(annual_images)
        trend = annual_col.select(['year', 'soil_loss']).reduce(ee.Reducer.linearFit())
        stacked = stacked.addBands(trend)

        # Single server call
        results = stacked.reduceRegions(
            collection=polygons,
            reducer=ee.Reducer.mean(),
            scale=30,
            tileScale=4,
        )
        data = results.getInfo()

        polygon_data = []
        for i, feature in enumerate(data['features']):
            props = feature['properties']
            historical = {}
            for yr in years:
                val = props.get('SL_{}'.format(yr))
                historical[str(yr)] = round(val, 2) if val is not None else None

            slope = props.get('scale')
            intercept = props.get('offset')
            predictions = {}
            if slope is not None and intercept is not None:
                for yr in range(2025, 2031):
                    predicted = max(0, intercept + slope * yr)
                    predictions[str(yr)] = round(predicted, 2)
                slope = round(slope, 4)

            coords = feature['geometry']['coordinates'][0]
            lngs = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            centroid_lng = sum(lngs) / len(lngs)
            centroid_lat = sum(lats) / len(lats)

            polygon_data.append({
                'index': i,
                'name': WETLAND_NAMES[i] if i < len(WETLAND_NAMES) else 'Wetland ' + str(i),
                'centroid_lat': round(centroid_lat, 6),
                'centroid_lng': round(centroid_lng, 6),
                'historical': historical,
                'slope': slope,
                'predictions': predictions,
            })

        return JsonResponse({'polygons': polygon_data})

    except Exception as e:
        return _ee_json_error(e)


# ══════════════════════════════════════════════════════════════════
#  NEW WETLAND MANAGEMENT VIEWS (Dynamic Mapping & Monitoring)
# ══════════════════════════════════════════════════════════════════

def _load_static_wetlands_geojson():
    from wetlands.views import _load_static_wetlands_geojson as impl
    return impl()


def _seed_static_wetlands_into_db():
    from wetlands.views import _seed_static_wetlands_into_db as impl
    return impl()


def wetland_registry(request):
    from wetlands.views import wetland_registry as impl
    return impl(request)


def add_wetland(request):
    from wetlands.views import add_wetland as impl
    return impl(request)


def upload_wetlands(request):
    from wetlands.views import upload_wetlands as impl
    return impl(request)


def _parse_upload_file(file_obj, file_format):
    from wetlands.views import _parse_upload_file as impl
    return impl(file_obj, file_format)


def monitor_wetland(request, pk):
    from wetlands.views import monitor_wetland as impl
    return impl(request, pk)


def api_wetland_erosion_data(request, pk):
    from wetlands.views import api_wetland_erosion_data as impl
    return impl(request, pk)


def api_wetland_comparison(request):
    from wetlands.views import api_wetland_comparison as impl
    return impl(request)


def api_wetland_prediction(request, pk):
    from wetlands.views import api_wetland_prediction as impl
    return impl(request, pk)


def _parse_int_param(payload, key, default, minimum=None, maximum=None):
    from timelapse.views import _parse_int_param as impl
    return impl(payload, key, default, minimum=minimum, maximum=maximum)


def api_timelapse_start(request):
    from timelapse.views import api_timelapse_start as impl
    return impl(request)


def api_timelapse_status(request, job_id):
    from timelapse.views import api_timelapse_status as impl
    return impl(request, job_id)


def api_timelapse_frames(request, job_id):
    from timelapse.views import api_timelapse_frames as impl
    return impl(request, job_id)


def api_timelapse_download(request, job_id):
    from timelapse.views import api_timelapse_download as impl
    return impl(request, job_id)
