"""Earth Engine initialization helper."""
import ee
import logging
from django.conf import settings

logger = logging.getLogger(__name__)
_initialized = False
_initialization_failed = False


def initialize_ee():
    """Initialize Earth Engine API (once per process).
    
    Handles both successful initialization and credential errors gracefully.
    """
    global _initialized, _initialization_failed
    if _initialized or _initialization_failed:
        return

    project = getattr(settings, 'EE_PROJECT', None)
    key_path = getattr(settings, 'EE_SERVICE_ACCOUNT_KEY', '')
    
    try:
        if key_path:
            credentials = ee.ServiceAccountCredentials('', key_file=key_path)
            ee.Initialize(credentials, project=project)
        else:
            # For development: uses cached credentials from `earthengine authenticate`
            ee.Initialize(project=project)
        _initialized = True
    except ee.ee_exception.EEException as e:
        logger.warning(f'Earth Engine initialization failed: {e}')
        _initialization_failed = True
    except Exception as e:
        logger.error(f'Unexpected error during Earth Engine initialization: {e}')
        _initialization_failed = True
