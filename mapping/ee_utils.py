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
    fallback_project = getattr(settings, 'EE_FALLBACK_PROJECT', None)
    key_path = getattr(settings, 'EE_SERVICE_ACCOUNT_KEY', '')

    def _is_project_permission_error(exc):
        msg = str(exc)
        return 'USER_PROJECT_DENIED' in msg or 'required permission' in msg.lower()

    if key_path:
        credentials = ee.ServiceAccountCredentials('', key_file=key_path)
        try:
            ee.Initialize(credentials, project=project)
        except ee.EEException as exc:
            if fallback_project and fallback_project != project and _is_project_permission_error(exc):
                ee.Initialize(credentials, project=fallback_project)
            else:
                raise
    else:
        # For development: uses cached credentials from `earthengine authenticate`.
        # Try primary project, then configured fallback project, then default project.
        try:
            ee.Initialize(project=project)
        except ee.EEException as exc:
            if fallback_project and fallback_project != project and _is_project_permission_error(exc):
                try:
                    ee.Initialize(project=fallback_project)
                except ee.EEException as fallback_exc:
                    if _is_project_permission_error(fallback_exc):
                        ee.Initialize()
                    else:
                        raise
            elif project and _is_project_permission_error(exc):
                ee.Initialize()
            else:
                raise

    _initialized = True
