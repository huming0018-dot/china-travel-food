"""Shared validators migrated from the audited semantic_store.py semantics.

Functions migrated (semantic semantics preserved, Shanghai-only boundary removed):
- serialized / digest / stamp / text / iso_date / safe_url
- Unicode quote slicing check (body[start:end] == quote)
- canonical hash verification

Migration origin: semantic_store.py inside
redacted-app-source.tar (see SOURCE_REUSE-v1 for the exact archive SHA).

NOTE: this module is domain-agnostic; no food / Shanghai business fields live here.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import date, datetime, timezone
from urllib.parse import urlsplit


class ValidatorError(ValueError):
    """Raised when a shared validator rejects a value."""


def serialized(value):
    """Canonical JSON string (migrated from semantic_store.serialized)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest(value: str) -> str:
    """SHA-256 of UTF-8 text (migrated from semantic_store.digest)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def digest_bytes(value: bytes) -> str:
    """SHA-256 of raw bytes (captured payload hashing)."""
    return hashlib.sha256(value).hexdigest()


def stamp() -> str:
    """UTC ISO-8601 timestamp (migrated from semantic_store.stamp)."""
    return datetime.now(timezone.utc).isoformat()


def text(value, label: str, limit: int = 300, optional: bool = False):
    """Non-empty bounded text, no NUL (migrated from semantic_store.text)."""
    if optional and value is None:
        return None
    if not isinstance(value, str) or not 0 < len(value.strip()) <= limit:
        raise ValidatorError(
            f"{label} must be nonempty text within {limit} characters")
    if "\x00" in value:
        raise ValidatorError(f"{label} contains a null character")
    return value


def iso_date(value, label: str):
    """Explicit ISO date or timezone-aware timestamp (migrated from semantic_store.iso_date)."""
    if value is None:
        return None
    text(value, label, 64)
    try:
        if len(value) == 10:
            date.fromisoformat(value)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValidatorError(f"{label} timestamp requires a timezone")
    except ValueError as exc:
        raise ValidatorError(
            f"{label} must be an explicit ISO date or timezone-aware timestamp") from exc
    return value


def _is_public_ip(ip_str: str) -> bool:
    try:
        address = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return address.is_global and not address.is_loopback and not address.is_link_local


def safe_url(value, label: str = "source URL"):
    """Public HTTPS URL only, no credentials (migrated from semantic_store.safe_url).

    Rejects: non-https, localhost/.local/.internal hosts, private/loopback IPs,
    embedded credentials, non-443 ports.
    """
    text(value, label, 4096)
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https":
            raise ValidatorError(f"{label} requires https")
        if not parsed.hostname or parsed.username or parsed.password:
            raise ValidatorError(f"{label} requires https and no credentials")
        host = parsed.hostname.lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValidatorError("Private source URL is not supported")
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            addr = None
        if addr is not None:
            if not addr.is_global:
                raise ValidatorError("Private source URL is not supported")
        elif "." not in host:
            raise ValidatorError(f"{label} requires a public hostname")
        if parsed.port not in (None, 443):
            raise ValidatorError(f"{label} requires the default HTTPS port")
    except ValidatorError:
        raise
    except ValueError as exc:
        raise ValidatorError("Invalid source URL") from exc
    return value


def unicode_quote_check(body: str, start: int, end: int, quote: str):
    """Exact Unicode slice provenance check (migrated from semantic_store normalize_candidate).

    Requires 0 <= start < end <= len(body) and body[start:end] == quote.
    """
    if type(start) is not int or type(end) is not int:
        raise ValidatorError("Invalid Unicode evidence offsets")
    if not (0 <= start < end <= len(body)):
        raise ValidatorError("Invalid Unicode evidence offsets")
    if body[start:end] != quote:
        raise ValidatorError("Evidence quote does not match the exact source version")


def canonical_hash_check(canonical_body: str, declared_sha256: str, label: str = "canonical_body_sha256"):
    """Content hash must match the actual body (migrated from semantic_store normalize_source)."""
    if not isinstance(declared_sha256, str) or len(declared_sha256) != 64 \
            or not all(c in "0123456789abcdef" for c in declared_sha256):
        raise ValidatorError(f"{label} must be a 64-char lowercase hex sha256")
    if digest(canonical_body) != declared_sha256:
        raise ValidatorError("Canonical body hash does not match")
