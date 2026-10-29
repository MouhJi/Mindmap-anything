"""Crawler-compatible input/output models without narrowing provenance."""

from typing import Any

from pydantic import ConfigDict

from ..models import Document


class RawDocument(Document):
    """The crawler's five fields, allowing arbitrary metadata and extra fields.

    Existing Document instances are accepted by DocumentCleaner. Dictionaries
    retain metadata values verbatim, including unknown keys and timestamp strings.
    """

    model_config = ConfigDict(extra="allow")
    metadata: dict[str, Any]


class CleanDocument(RawDocument):
    """Same schema as RawDocument; only markdown and text are cleaned.

    The crawler's hash remains a provenance hash of the original crawl, not a
    fingerprint of the cleaned representation.
    """
