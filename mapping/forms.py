"""Compatibility import layer.

Wetland-related forms were moved to the dedicated `wetlands` app.
Keep re-exports here so existing imports continue to work during migration.
"""

from wetlands.forms import (  # noqa: F401
    BulkWetlandUploadForm,
    MonitoringRecordForm,
    WetlandFilterForm,
    WetlandForm,
)
