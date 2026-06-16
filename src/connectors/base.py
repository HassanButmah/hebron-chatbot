"""
Abstract base connector interface for Hebron University dynamic data sources.

Every concrete connector must implement:
  fetch()        -> raw data from the external source (dict / list)
  normalize()    -> list of normalised record dicts with required keys
  validate()     -> True if the raw payload looks sane
  to_documents() -> list of LangChain Document objects ready for Chroma

Each normalised record dict must contain at minimum:
  record_id    : str  – stable unique id within this source
  content      : str  – human-readable text for embedding
  effective_from  : Optional[str ISO datetime]
  effective_to    : Optional[str ISO datetime]
  version_hash : str  – SHA-256 hex of `content` for change detection
"""
from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


@dataclass
class ConnectorResult:
    """Return value from a full fetch-normalise-validate cycle."""
    records: List[Dict[str, Any]] = field(default_factory=list)
    documents: List[Document] = field(default_factory=list)
    total_fetched: int = 0
    total_valid: int = 0
    error: Optional[str] = None
    available: bool = True


def hash_content(text: str) -> str:
    """Return a stable SHA-256 hex digest for change-detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class BaseConnector(ABC):
    """
    Abstract connector for a single Hebron University data source.

    Subclasses read configuration (endpoint_url, auth_token) from the
    DynamicSource DB row that is passed at construction time, so there
    is no hard-coded credential in code.
    """

    def __init__(self, source_config: Dict[str, Any]) -> None:
        """
        :param source_config: dict matching _source_to_dict() output from database.py,
                              e.g. {'id': 1, 'name': 'Calendar', 'endpoint_url': '...', ...}
        """
        self.source_config = source_config
        self.source_id: int = source_config.get("id", 0)
        self.source_type: str = source_config.get("source_type", "generic")
        self.endpoint_url: Optional[str] = (source_config.get("endpoint_url") or "").strip() or None
        self.auth_token: Optional[str] = source_config.get("auth_token")

    @property
    def is_configured(self) -> bool:
        """True when the connector has a non-empty endpoint URL."""
        return bool(self.endpoint_url)

    @abstractmethod
    def fetch(self) -> Any:
        """
        Call the external API and return the raw response payload.
        Raise an exception on network / auth errors.
        """

    @abstractmethod
    def normalize(self, raw: Any) -> List[Dict[str, Any]]:
        """
        Convert the raw payload into a list of normalised record dicts.
        Required keys on each dict:
          record_id, content, effective_from, effective_to, version_hash
        """

    @abstractmethod
    def validate(self, raw: Any) -> bool:
        """Return True when `raw` is a non-empty, structurally valid payload."""

    def to_documents(self, records: List[Dict[str, Any]]) -> List[Document]:
        """
        Convert normalised record dicts into LangChain Document objects.
        Metadata includes source_type, source_id, record_id, version_hash,
        effective_from, and effective_to so Chroma can filter by stable IDs.
        """
        docs = []
        for rec in records:
            metadata = {
                "source_type": self.source_type,
                "source_id": str(self.source_id),
                "record_id": str(rec.get("record_id", "")),
                "version_hash": rec.get("version_hash", ""),
                "effective_from": rec.get("effective_from") or "",
                "effective_to": rec.get("effective_to") or "",
                # Use source_id as "source" so existing delete_by_source helpers work
                "source": f"dynamic_{self.source_type}_{self.source_id}",
            }
            docs.append(Document(page_content=rec["content"], metadata=metadata))
        return docs

    def run(self) -> ConnectorResult:
        """
        Full pipeline: fetch → validate → normalize → to_documents.
        Returns a ConnectorResult regardless of errors; never raises.
        """
        if not self.is_configured:
            return ConnectorResult(
                available=False,
                error=f"Source '{self.source_type}' (id={self.source_id}) is not configured: endpoint_url is empty. "
                      "Configure the endpoint URL in Admin → Dynamic Sources.",
            )
        try:
            raw = self.fetch()
        except Exception as exc:
            logger.error("Connector fetch failed for source_id=%s: %s", self.source_id, exc)
            return ConnectorResult(available=True, error=f"Fetch failed: {exc}")

        if not self.validate(raw):
            return ConnectorResult(available=True, error="Payload validation failed: empty or malformed response.")

        try:
            records = self.normalize(raw)
        except Exception as exc:
            logger.error("Connector normalize failed for source_id=%s: %s", self.source_id, exc)
            return ConnectorResult(available=True, error=f"Normalize failed: {exc}")

        docs = self.to_documents(records)
        return ConnectorResult(
            records=records,
            documents=docs,
            total_fetched=len(records),
            total_valid=len(records),
        )
