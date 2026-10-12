"""Versioned JSON Schema validation for CTFS Toolbox.

Validator: official `jsonschema` library (Draft 2020-12, locked version).
Schema assets ship inside the wheel under toolbox/schemas/. Schema files are
meta-validated with Draft202012Validator.check_schema at load time so a bad
schema asset fails loudly instead of silently passing everything. minLength /
minimum / maximum / pattern / required / additionalProperties and unknown
`type` values are enforced by jsonschema itself (no partial hand-rolled
subset; unknown schema types fail closed).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, FormatChecker, ValidationError as _JsonValidationError
    from jsonschema.exceptions import SchemaError as _JsonSchemaError
except ImportError:  # pragma: no cover - present in wheel installs
    Draft202012Validator = None  # type: ignore[assignment]

try:
    from rfc3339_validator import validate_rfc3339
except ImportError:
    validate_rfc3339 = None

SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"

SCHEMA_FILES: dict[str, str] = {
    "manifest": "manifest.schema.json",
    "manifest-archive-0.2.0": "archive/manifest.0.2.0.schema.json",
    "manifest-archive-0.3.2": "archive/manifest.0.3.2.schema.json",
    "manifest-archive-0.3.3": "archive/manifest.0.3.3.schema.json",
    "pack": "pack.schema.json",
    "raw": "raw.schema.json",
    "receipt": "receipt.schema.json",
    "clean": "clean.schema.json",
    "scored": "scored.schema.json",
    "audit": "audit.schema.json",
    "view": "view.schema.json",
}

_schema_cache: dict[str, dict[str, Any]] = {}


class SchemaError(Exception):
    """Raised when data fails the versioned schema or a schema asset is invalid."""


def load_schema(name: str) -> dict[str, Any]:
    if name not in SCHEMA_FILES:
        raise SchemaError(f"unknown schema name: {name}")
    if name in _schema_cache:
        return _schema_cache[name]
    path = SCHEMAS_DIR / SCHEMA_FILES[name]
    if not path.is_file():
        raise SchemaError(f"schema asset not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemaError(f"schema asset is not valid JSON: {path}: {exc}") from exc
    if Draft202012Validator is not None:
        try:
            Draft202012Validator.check_schema(data)
        except _JsonSchemaError as exc:
            raise SchemaError(
                f"schema asset is not a valid Draft 2020-12 schema: {path}: {exc.message}"
            ) from exc
    _schema_cache[name] = data
    return data


def validate_against(name: str, data: Any) -> None:
    """Validate `data` against the named versioned schema.

    Raises SchemaError on failure.
    """
    schema = load_schema(name)
    if Draft202012Validator is None:
        raise SchemaError("jsonschema dependency unavailable")
    if validate_rfc3339 is None:
        raise SchemaError("locked RFC3339 date-time validator dependency unavailable")
    checker=FormatChecker()
    @checker.checks("date-time")
    def strict_datetime(value):
        return not isinstance(value,str) or bool(validate_rfc3339(value.upper()))
    try:
        Draft202012Validator(schema, format_checker=checker).validate(data)
    except _JsonValidationError as exc:
        path = ".".join(str(p) for p in exc.absolute_path) or "<root>"
        raise SchemaError(
            f"{name} schema validation failed at {path}: {exc.message}"
        ) from exc
