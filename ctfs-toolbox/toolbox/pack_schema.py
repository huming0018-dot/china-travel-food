"""Generic pack reader for M2/M3/M6.

Only reads what P0 OntologyManager already exposes (install/verify/list/rollback/load).
No business fields here: every field name comes from the pack contract files.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

from toolbox.ontology import OntologyManager, PackError


@dataclass(frozen=True)
class PackContract:
    pack_id: str
    version: str
    pack: dict
    fields: dict
    pointers: dict
    validation: dict
    rubric: dict
    expectations: dict
    store_root: pathlib.Path = field(repr=False)


def load_pack(store_root: pathlib.Path, pack_id: str) -> PackContract:
    """Load the active, verified pack (tampered packs are refused by load())."""
    mgr = OntologyManager(store_root)
    loaded = mgr.load(pack_id)
    return PackContract(
        pack_id=loaded["pack_id"],
        version=loaded["version"],
        pack=loaded["pack"],
        fields=loaded["fields"],
        pointers=loaded["pointers"],
        validation=loaded["validation"],
        rubric=loaded["rubric"],
        expectations=loaded["expectations"],
        store_root=store_root,
    )


def resolve_pointer(root: dict, pointer: str) -> object:
    """JSON pointer subset: /a/b/c, no ~0/~1 escapes beyond plain keys.

    Unsupported pointer syntax raises ValueError (fail closed, no partial match).
    """
    if not pointer.startswith("/"):
        raise ValueError(f"pointer must start with '/': {pointer!r}")
    parts = pointer[1:].split("/")
    node = root
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"pointer {pointer!r} not found at {part!r}")
        node = node[part]
    return node


def evidence_fields(contract: PackContract) -> list[str]:
    cov = contract.validation.get("coverage", {})
    fields = cov.get("evidence_fields", [])
    if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
        raise PackError(f"pack {contract.pack_id} coverage.evidence_fields must be list[str]")
    return fields


def classification_fields(contract: PackContract) -> list[str]:
    cls = contract.validation.get("classification", {})
    fields = cls.get("fields", []) if isinstance(cls, dict) else []
    if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
        raise PackError(f"pack {contract.pack_id} classification.fields must be list[str]")
    return fields
