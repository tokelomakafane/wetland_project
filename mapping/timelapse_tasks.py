"""Lightweight async timelapse job runner.

This module intentionally uses a daemon thread so the feature works immediately
without Celery. It can be replaced by a proper queue worker later.
"""

import json
import os
import threading

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from .ee_timelapse import build_frame_urls, export_gif
from .ee_utils import initialize_ee
from .models import TimelapseJob


def _load_wetland_geometry(wetland):
    geometry = wetland.geometry
    if isinstance(geometry, str):
        geometry = json.loads(geometry)
    if geometry.get('type') == 'Feature':
        geometry = geometry.get('geometry', {})
    return geometry


def _run_job(job_id):
    close_old_connections()

    job = TimelapseJob.objects.select_related('wetland').get(pk=job_id)
    job.status = 'running'
    job.progress_percent = 5
    job.error_message = ''
    job.save(update_fields=['status', 'progress_percent', 'error_message', 'updated_at'])

    try:
        initialize_ee()
        geometry_geojson = _load_wetland_geometry(job.wetland)

        frame_urls = build_frame_urls(
            geometry_geojson=geometry_geojson,
            start_year=job.start_year,
            end_year=job.end_year,
            buffer_meters=job.buffer_meters,
            cloud_threshold=job.cloud_threshold,
            dimensions=job.dimensions,
        )
        job.frame_urls = frame_urls
        job.progress_percent = 60
        job.save(update_fields=['frame_urls', 'progress_percent', 'updated_at'])

        filename = f"timelapse_job_{job.id}.gif"
        relative_path = os.path.join('timelapse_exports', filename)
        absolute_path = os.path.join(settings.MEDIA_ROOT, relative_path)

        gif_url = export_gif(
            geometry_geojson=geometry_geojson,
            start_year=job.start_year,
            end_year=job.end_year,
            output_path=absolute_path,
            buffer_meters=job.buffer_meters,
            cloud_threshold=job.cloud_threshold,
            frames_per_second=job.frames_per_second,
            dimensions=job.dimensions,
        )

        job.gif_relative_path = relative_path
        job.gif_source_url = gif_url
        job.status = 'completed'
        job.progress_percent = 100
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                'gif_relative_path',
                'gif_source_url',
                'status',
                'progress_percent',
                'completed_at',
                'updated_at',
            ]
        )
    except Exception as exc:
        job.status = 'failed'
        job.progress_percent = 100
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'progress_percent', 'error_message', 'completed_at', 'updated_at'])
    finally:
        close_old_connections()


def start_timelapse_job(job_id):
    """Start job processing in a background daemon thread."""
    worker = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    worker.start()
