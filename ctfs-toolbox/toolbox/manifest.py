"""Manifest load/validate with strict trust boundaries (P0-IMPL-01; P1-IMPL-01).

Rules:
- schemaVersion must be 0.2.0 or 0.3.0 (versioned manifest.schema.json; the
  0.2.0 manifest schema is archived verbatim under schemas/archive/)
- project_id pattern ^[a-z0-9][a-z0-9-]{0,63}$
- every referenced data path must resolve inside the project's own directory
  (absolute paths and '..' escapes rejected)
- unknown fields rejected via additionalProperties=false
- no eval / no dynamic execution of any configuration value
- 0.3.0 adds: crawler budget/connector contract and ontology pack references;
  data-layer schemas (RAW/ODS/DW/APP) stay 0.2.0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .schema import SchemaError, load_schema, validate_against

PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SUPPORTED_VERSIONS = ("0.2.0", "0.3.2", "0.3.3", "0.4.0")
_BANNED_DYNAMIC_KEYS = ("eval", "exec", "command", "template", "callback")


class ManifestError(ValueError):
    """Trust-boundary or schema violation while loading a manifest."""


@dataclass(frozen=True)
class Manifest:
    path: Path
    project_id: str
    domain: str
    region: str
    storage: dict
    pipelines: dict
    raw: dict = field(default_factory=dict)
    crawler: dict = field(default_factory=dict)
    ontology: dict = field(default_factory=dict)
    schema_version: str = "0.4.0"

    @classmethod
    def load(cls, manifest_path: str | Path) -> "Manifest":
        path = Path(manifest_path).resolve()
        if not path.exists():
            raise ManifestError(f"manifest not found: {path}")
        text = path.read_text(encoding="utf-8")
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:  # noqa: B902
            raise ManifestError(f"manifest is not valid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise ManifestError("manifest root must be a mapping")

        # 1) versioned schema + unknown fields: pick the REAL archived contract
        #    by schemaVersion; one schema must never smuggle several versions.
        sv = data.get("schemaVersion")
        if sv in ("0.2.0", "0.3.2", "0.3.3"):
            schema_name = f"manifest-archive-{sv}"
        else:
            schema_name = "manifest"  # current contract (0.4.0); unknown versions fail the enum
        try:
            validate_against(schema_name, data)
        except SchemaError as exc:
            raise ManifestError(f"manifest schema violation ({sv}): {exc}") from exc

        # 2) strict trust-boundary checks
        project = data["project"]
        project_id = project["project_id"]
        if not PROJECT_ID_RE.fullmatch(project_id):
            raise ManifestError(f"project_id {project_id!r} fails {PROJECT_ID_RE.pattern}")

        # 3) relative-path isolation: every pipeline target must stay inside
        #    the manifest's own project directory; absolute and '..' rejected
        project_dir = path.parent.resolve()
        for layer in ("raw", "clean", "scored", "audit"):
            spec = data["pipelines"][layer]
            target = spec.get("target")
            if target is None:
                continue
            candidate = Path(target)
            if candidate.is_absolute():
                raise ManifestError(f"{layer}.target must be relative, got absolute '{target}'")
            resolved = (project_dir / candidate).resolve()
            if not resolved.is_relative_to(project_dir):
                raise ManifestError(
                    f"{layer}.target '{target}' escapes project directory (.. / link)"
                )

        # 3b) storage.path must stay inside the project directory too
        storage = data.get("storage") or {}
        storage_path = storage.get("path")
        if storage_path is not None:
            sp = Path(str(storage_path))
            if sp.is_absolute():
                raise ManifestError(f"storage.path must be relative, got absolute '{storage_path}'")
            resolved_sp = (project_dir / sp).resolve()
            if not resolved_sp.is_relative_to(project_dir):
                raise ManifestError(f"storage.path '{storage_path}' escapes project directory (.. / link)")

        # 4) no dynamic execution: manifest is pure data; assert no executable keys
        for layer, spec in data["pipelines"].items():
            for banned in _BANNED_DYNAMIC_KEYS:
                if banned in spec:
                    raise ManifestError(
                        f"{layer} uses banned dynamic key '{banned}' (dynamic execution forbidden)"
                    )
        for block_name in ("crawler", "ontology", "raw"):
            block = data.get(block_name)
            if isinstance(block, dict):
                for banned in _BANNED_DYNAMIC_KEYS:
                    if banned in block:
                        raise ManifestError(
                            f"{block_name} uses banned dynamic key '{banned}' (dynamic execution forbidden)"
                        )

        return cls(
            path=path,
            project_id=project_id,
            domain=project["domain"],
            region=project["region"],
            storage=data["storage"],
            pipelines=data["pipelines"],
            raw=data.get("raw", {}),
            crawler=data.get("crawler", {}),
            ontology=data.get("ontology", {}),
            schema_version=sv,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "project_id": self.project_id,
            "domain": self.domain,
            "region": self.region,
            "storage": self.storage,
            "pipelines": self.pipelines,
            "raw": self.raw,
            "crawler": self.crawler,
            "ontology": self.ontology,
        }
