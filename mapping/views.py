import json

from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.conf import settings

from .ee_utils import initialize_ee


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
    """Render simulated login page; POST redirects to dashboard."""
    if request.method == 'POST':
        return redirect('mapping:dashboard')
    return render(request, 'mapping/login.html')


def dashboard(request):
    """Render the main wetland map page."""
    return render(request, 'mapping/dashboard.html', {'active_page': 'mapping'})


def monitor_view(request):
    return render(request, 'mapping/monitor.html', {'active_page': 'monitor'})


def alerts_view(request):
    return render(request, 'mapping/alerts.html', {'active_page': 'alerts'})


def community_view(request):
    return render(request, 'mapping/community.html', {'active_page': 'community'})


def drone_upload_view(request):
    return render(request, 'mapping/drone_upload.html', {'active_page': 'drone_upload'})


def users_view(request):
    return render(request, 'mapping/users.html', {'active_page': 'users'})


def ee_tile_url(request):
    """Return Earth Engine map tile URLs for the classification layers."""
    import ee
    initialize_ee()

    asset_id = getattr(settings, 'EE_ASSET_ID', '')

    try:
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
        return JsonResponse({'error': str(e)}, status=500)


def wetland_stats(request):
    """Return wetland area statistics."""
    import ee
    initialize_ee()

    asset_id = getattr(settings, 'EE_ASSET_ID', '')

    try:
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
        return JsonResponse({'error': str(e)}, status=500)


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
