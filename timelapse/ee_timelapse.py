"""Earth Engine timelapse helpers converted from the project JS scripts."""

import os
from urllib.request import urlretrieve

import ee


def _to_ee_geometry(geometry_geojson):
    """Normalize a GeoJSON geometry or Feature payload to ee.Geometry."""
    payload = geometry_geojson
    if payload.get('type') == 'Feature':
        payload = payload.get('geometry', {})
    return ee.Geometry(payload)


def visualize_image(image):
    """Convert Sentinel-2 surface reflectance into 8-bit RGB for timelapse exports."""
    return (
        image
        .select(['B4', 'B3', 'B2'])
        .unitScale(0, 3000)
        .pow(1 / 1.3)
        .multiply(255)
        .toByte()
        .rename(['R', 'G', 'B'])
    )


def _annual_rgb_image(geometry, year, cloud_threshold):
    start = ee.Date.fromYMD(year, 1, 1)
    end = ee.Date.fromYMD(year, 12, 31)

    raw = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterDate(start, end)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', cloud_threshold))
        .filterBounds(geometry)
        .median()
        .clip(geometry)
    )
    return visualize_image(raw)


def build_annual_images(geometry_geojson, start_year, end_year, buffer_meters=100, cloud_threshold=20):
    """Build an ImageCollection of annual 8-bit RGB timelapse frames."""
    geometry = _to_ee_geometry(geometry_geojson).buffer(buffer_meters)

    images = []
    for year in range(start_year, end_year + 1):
        frame = _annual_rgb_image(geometry, year, cloud_threshold)
        frame = frame.set('year', year)
        frame = frame.set('system:time_start', ee.Date.fromYMD(year, 6, 1).millis())
        images.append(frame)

    return ee.ImageCollection(images), geometry


def build_frame_urls(geometry_geojson, start_year, end_year, buffer_meters=100, cloud_threshold=20, dimensions=300):
    """Build per-year preview frame URLs for browser playback controls."""
    geometry = _to_ee_geometry(geometry_geojson).buffer(buffer_meters)

    frame_urls = []
    for year in range(start_year, end_year + 1):
        frame = _annual_rgb_image(geometry, year, cloud_threshold)
        url = frame.getThumbURL({
            'bands': ['R', 'G', 'B'],
            'min': 0,
            'max': 255,
            'region': geometry,
            'dimensions': dimensions,
            'format': 'png',
        })
        frame_urls.append({'year': year, 'url': url})

    return frame_urls


def export_gif(geometry_geojson, start_year, end_year, output_path, buffer_meters=100, cloud_threshold=20, frames_per_second=1, dimensions=300):
    """Create a GIF timelapse URL from EE and download it to output_path."""
    annual_images, geometry = build_annual_images(
        geometry_geojson=geometry_geojson,
        start_year=start_year,
        end_year=end_year,
        buffer_meters=buffer_meters,
        cloud_threshold=cloud_threshold,
    )

    gif_url = annual_images.getVideoThumbURL({
        'region': geometry,
        'dimensions': dimensions,
        'crs': 'EPSG:4326',
        'framesPerSecond': frames_per_second,
        'min': 0,
        'max': 255,
        'bands': ['R', 'G', 'B'],
        'format': 'gif',
    })

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    urlretrieve(gif_url, output_path)

    return gif_url
