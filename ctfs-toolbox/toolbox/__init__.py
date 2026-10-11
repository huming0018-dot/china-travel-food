"""CTFS modular data toolbox.

P0: Manifest load/validate + versioned layered Storage (SQLite isolated backend).
P1: Crawler SDK/CLI with registered connectors (http-public, snapshot-file) and
    plugin loading via importlib.metadata entry points; Ontology packs
    (install/verify/list/rollback, immutable versions, SHA index).

P0 backend: SQLite (isolated). PRD production acceptance requires Postgres;
the Storage interface leaves a Postgres adapter slot (not a fake stub).
"""

__version__ = "0.5.0"
