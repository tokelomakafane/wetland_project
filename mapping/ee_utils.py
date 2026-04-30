"""Earth Engine initialization helper."""
import ee
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)
_initialized = False
_initialization_failed = False


def _read_service_account_email(key_path):
    try:
        with open(key_path, 'r', encoding='utf-8') as f:
            return json.load(f).get('client_email', '')
    except Exception as exc:
        logger.warning(f'Could not read service account email from key file: {exc}')
        return ''


def initialize_ee():
    """Initialize Earth Engine API (once per process).
    
    Handles both successful initialization and credential errors gracefully.
    """
    global _initialized, _initialization_failed
    if _initialized or _initialization_failed:
        return
    project = getattr(settings, 'EE_PROJECT', None)
    fallback_project = getattr(settings, 'EE_FALLBACK_PROJECT', None)
    key_path = getattr(settings, 'EE_SERVICE_ACCOUNT_KEY', '')

    def _is_project_permission_error(exc):
        msg = str(exc)
        return 'USER_PROJECT_DENIED' in msg or 'required permission' in msg.lower()

    try:
        if key_path:
            service_account = (
                getattr(settings, 'EE_SERVICE_ACCOUNT', '')
                or _read_service_account_email(key_path)
            )
            credentials = ee.ServiceAccountCredentials(service_account, key_file=key_path)
            try:
                ee.Initialize(credentials, project=project)
            except ee.EEException as exc:
                if fallback_project and fallback_project != project and _is_project_permission_error(exc):
                    try:
                        ee.Initialize(credentials, project=fallback_project)
                    except ee.EEException as exc2:
                        logger.warning(f'Earth Engine initialization failed for both primary and fallback projects: {exc2}')
                        _initialization_failed = True
                        return
                else:
                    logger.warning(f'Earth Engine initialization failed: {exc}')
                    _initialization_failed = True
                    return
        else:
            # For development: uses cached credentials from `earthengine authenticate`.
            try:
                ee.Initialize(project=project)
            except ee.EEException as exc:
                if fallback_project and fallback_project != project and _is_project_permission_error(exc):
                    try:
                        ee.Initialize(project=fallback_project)
                    except ee.EEException as fallback_exc:
                        if _is_project_permission_error(fallback_exc):
                            try:
                                ee.Initialize()
                            except Exception as final_exc:
                                logger.warning(f'Earth Engine initialization failed for default project as well: {final_exc}')
                                _initialization_failed = True
                                return
                        else:
                            logger.error(f'Unexpected EEException during fallback initialization: {fallback_exc}')
                            _initialization_failed = True
                            return
                elif project and _is_project_permission_error(exc):
                    try:
                        ee.Initialize()
                    except Exception as final_exc:
                        logger.warning(f'Earth Engine initialization failed for default project: {final_exc}')
                        _initialization_failed = True
                        return
                else:
                    logger.warning(f'Earth Engine initialization failed: {exc}')
                    _initialization_failed = True
                    return

        _initialized = True
    except Exception as e:
        logger.error(f'Unexpected error during Earth Engine initialization: {e}')
        _initialization_failed = True
        return
