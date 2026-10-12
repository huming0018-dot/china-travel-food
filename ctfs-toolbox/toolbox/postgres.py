"""PostgreSQL backend using the same reviewed layered storage operations.
No embedded credentials. DSN is supplied by the caller's cloud environment.
A dedicated ctfs_* schema is mandatory; public/production schemas are refused.
Schema-level transaction advisory locks serialize version/CAS/receipt writes.
"""
from __future__ import annotations
import hashlib
import ipaddress
import os
import re
from .storage import SqliteStorage, StorageError

class _Cursor:
    def __init__(self,cursor,lastrowid=None):
        self.cursor=cursor
        self.lastrowid=lastrowid
    def fetchone(self): return self.cursor.fetchone()
    def fetchall(self): return self.cursor.fetchall()

class _PostgresConnection:
    def __init__(self,conn,lock_key):
        self.conn=conn
        self.lock_key=lock_key
    def execute(self,query,params=None):
        if query=="BEGIN IMMEDIATE":
            self.conn.execute("BEGIN")
            self.conn.execute("SELECT pg_advisory_xact_lock(%s)",(self.lock_key,))
            return _Cursor(self.conn.cursor())
        query=query.replace("?","%s")
        if query.lstrip().startswith("INSERT INTO receipts "):
            cursor=self.conn.execute(query+" RETURNING seq",params)
            return _Cursor(cursor,int(cursor.fetchone()[0]))
        return _Cursor(self.conn.execute(query,params))
    def close(self): self.conn.close()

class PostgresStorage(SqliteStorage):
    """Actual PostgreSQL implementation, not a production Supabase acceptance."""
    def __init__(self,dsn:str,schema:str="ctfs_toolbox",*,read_only:bool=False):
        if type(read_only) is not bool:
            raise StorageError("read_only must be boolean")
        if not isinstance(schema,str) or not re.fullmatch(r"ctfs_[a-z0-9_]{1,48}",schema):
            raise StorageError("PostgreSQL requires a dedicated ctfs_* schema")
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict
        try:
            options=conninfo_to_dict(dsn)
        except Exception as exc:
            raise StorageError("postgres DSN parse failed ("+type(exc).__name__+")") from None
        # libpq also accepts connection hosts via hostaddr, service files and
        # environment. A service is opaque: require certificate validation.
        def value(key,envkey):
            return options.get(key) or os.environ.get(envkey,"")
        def local_host(host):
            if host in ("","localhost") or host.startswith("/"):
                return True
            try:return ipaddress.ip_address(host).is_loopback
            except ValueError:return False
        def local_addr(addr):
            if not addr:return True
            try:return ipaddress.ip_address(addr).is_loopback
            except ValueError:return False
        local=(not value("service","PGSERVICE") and
               all(local_host(h) for h in value("host","PGHOST").split(",")) and
               all(local_addr(h) for h in value("hostaddr","PGHOSTADDR").split(",")))
        if not local and value("sslmode","PGSSLMODE")!="verify-full":
            raise StorageError("remote or opaque PostgreSQL requires sslmode=verify-full")
        connection_options={"autocommit":True,"connect_timeout":10}
        if not local:
            # Explicit driver arguments override service-file/environment values.
            connection_options["sslmode"]="verify-full"
        if not value("service","PGSERVICE"):
            for key,envkey in (("host","PGHOST"),("hostaddr","PGHOSTADDR")):
                effective=value(key,envkey)
                if effective:connection_options[key]=effective
        try:
            conn=psycopg.connect(dsn,**connection_options)
        except Exception as exc:
            raise StorageError("postgres connection failed ("+type(exc).__name__+")") from None
        key=int.from_bytes(hashlib.sha256(schema.encode()).digest()[:8],"big") & ((1<<63)-1)
        self._conn=_PostgresConnection(conn,key)
        self._read_only = read_only
        if read_only:
            try:
                self._init_read_only(conn, schema)
            except StorageError:
                try: conn.close()
                except Exception: pass
                raise
            except Exception as exc:
                try: conn.close()
                except Exception: pass
                raise StorageError("read-only postgres backend initialization failed ("+type(exc).__name__+")") from None
            return
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            exists=conn.execute("SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name=%s)",(schema,)).fetchone()[0]
            if exists:
                marker=conn.execute("SELECT to_regclass(%s)",(schema+"._toolbox_meta",)).fetchone()[0]
                if not marker:
                    raise StorageError("refusing an existing schema not created by this toolbox")
                contract=conn.execute(sql.SQL("SELECT value FROM {}._toolbox_meta WHERE key='contract'").format(sql.Identifier(schema))).fetchone()
                if not contract or contract[0]!="layered-storage/0.2":
                    raise StorageError("incompatible existing toolbox schema contract")
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
            conn.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {}._toolbox_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)").format(sql.Identifier(schema)))
            conn.execute(sql.SQL("INSERT INTO {}._toolbox_meta(key,value) VALUES('contract','layered-storage/0.2') ON CONFLICT(key) DO NOTHING").format(sql.Identifier(schema)))
            conn.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(sql.Identifier(schema)))
            conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            statements=[
                """CREATE TABLE IF NOT EXISTS raw_records (
                project_id TEXT NOT NULL,id TEXT NOT NULL,layer TEXT NOT NULL,
                payload BYTEA NOT NULL,payload_kind TEXT NOT NULL,content_hash TEXT NOT NULL,
                source_url TEXT,source_hash TEXT,batch TEXT,captured_at TEXT,
                lineage TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(project_id,id))""",
                """CREATE TABLE IF NOT EXISTS receipts (
                seq BIGSERIAL PRIMARY KEY,project_id TEXT NOT NULL,raw_id TEXT NOT NULL,
                receipt TEXT NOT NULL,created_at TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS versions (
                project_id TEXT NOT NULL,id TEXT NOT NULL,layer TEXT NOT NULL,
                schema_kind TEXT NOT NULL,version INTEGER NOT NULL,content_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,parent_ref TEXT,lineage TEXT NOT NULL,
                created_at TEXT NOT NULL,PRIMARY KEY(project_id,id,layer,version))""",
                "CREATE INDEX IF NOT EXISTS idx_raw_proj ON raw_records(project_id)",
                "CREATE INDEX IF NOT EXISTS idx_ver_proj ON versions(project_id,layer)"]
            for stmt in statements:conn.execute(stmt)
            conn.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM PUBLIC").format(sql.Identifier(schema)))
            conn.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA {} FROM PUBLIC").format(sql.Identifier(schema)))
            self._conn.execute("COMMIT")
        except Exception:
            try:self._conn.execute("ROLLBACK")
            finally:conn.close()
            raise

    def _init_read_only(self, conn, schema) -> None:
        """Verify an existing toolbox schema and enforce database-layer read-only.

        Connection-scoped default_transaction_read_only is set and verified via
        SHOW default and current transaction state. No DDL/DML is attempted;
        every required relation and the contract marker must already exist.
        """
        from psycopg import sql
        conn.autocommit = True
        exists=conn.execute("SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name=%s)",(schema,)).fetchone()[0]
        if not exists:
            raise StorageError("read-only postgres backend: schema does not exist")
        rows=conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=%s",(schema,)).fetchall()
        present={r[0] for r in rows}
        missing={"raw_records","versions","receipts","_toolbox_meta"}-present
        if missing:
            raise StorageError("read-only postgres backend: toolbox tables missing: "+",".join(sorted(missing)))
        cols=conn.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=%s AND table_name='_toolbox_meta' AND column_name IN ('key','value')",(schema,)).fetchall()
        colset={(r[0],r[1]) for r in cols}
        if ("_toolbox_meta","key") not in colset or ("_toolbox_meta","value") not in colset:
            raise StorageError("read-only postgres backend: _toolbox_meta lacks key/value columns")
        contract=conn.execute(sql.SQL("SELECT value FROM {}._toolbox_meta WHERE key='contract'").format(sql.Identifier(schema))).fetchone()
        if not contract or contract[0]!="layered-storage/0.2":
            raise StorageError("incompatible existing toolbox schema contract")
        conn.execute("SET default_transaction_read_only = on")
        row=conn.execute("SHOW default_transaction_read_only").fetchone()
        if not row or str(row[0]).lower()!="on":
            raise StorageError("read-only postgres backend: connection read-only not enforced")
        row=conn.execute("SHOW transaction_read_only").fetchone()
        if not row or str(row[0]).lower()!="on":
            raise StorageError("read-only postgres backend: current transaction read-only not enforced")
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))

    def _guard_writes(self) -> None:
        if getattr(self, "_read_only", False):
            raise StorageError("read-only postgres backend rejects writes")

    def write_raw(self, project_id: str, record: dict, record_id: str | None = None) -> str:
        self._guard_writes()
        return super().write_raw(project_id, record, record_id)

    def append_receipt(self, project_id: str, raw_id: str, receipt: dict) -> int:
        self._guard_writes()
        return super().append_receipt(project_id, raw_id, receipt)

    def append_version(self, project_id: str, layer: str, record: dict, expected_version: int | None = None) -> int:
        self._guard_writes()
        return super().append_version(project_id, layer, record, expected_version)
