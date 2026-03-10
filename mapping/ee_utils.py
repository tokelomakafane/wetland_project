"""Earth Engine initialization helper."""
import ee
from django.conf import settings

_initialized = False


def initialize_ee():
    """Initialize Earth Engine API (once per process)."""
    global _initialized
    if _initialized:
        return

    project = getattr(settings, 'EE_PROJECT', None)
    key_path = getattr(settings, 'EE_SERVICE_ACCOUNT_KEY', '')
    if key_path:
        credentials = ee.ServiceAccountCredentials('', key_file=key_path)
        ee.Initialize(credentials, project=project)
    else:
        # For development: uses cached credentials from `earthengine authenticate`
        ee.Initialize(project=project)

    _initialized = True
