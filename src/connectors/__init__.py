# Connector package for Hebron University dynamic data sources.
from .base import BaseConnector, ConnectorResult
from .official_api import (
    CalendarConnector,
    AnnouncementsConnector,
    AdmissionsConnector,
)

__all__ = [
    "BaseConnector",
    "ConnectorResult",
    "CalendarConnector",
    "AnnouncementsConnector",
    "AdmissionsConnector",
]
