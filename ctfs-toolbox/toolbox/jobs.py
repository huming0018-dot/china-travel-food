"""M5 built-in serial DAG with durable attempts, exact refs and recovery locks."""
from __future__ import annotations
import fcntl, json, os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from . import __version__
from .bindings import binding, canonical, digest
from .crawler import Crawler
from .stages import Stages, exact_ref

class JobError(ValueError): pass
STAGES=("crawl","clean","score","audit","deliver")
def now(): return datetime.now(timezone.utc).isoformat()

class Jobs:
    def __init__(self, manifest, contract, storage, as_of):
        self.manifest,self.contract,self.storage,self.as_of=manifest,contract,storage,as_of
        self.directory=manifest.path.parent.resolve()/"data"
        if self.directory.is_symlink(): raise JobError("job directory symlink")
        self.directory.mkdir(exist_ok=True)
        self.path=self.directory/"jobs.sqlite"
        if self.path.is_symlink(): raise JobError("job database symlink")
        self.db=sqlite3.connect(self.path,isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("CREATE TABLE IF NOT EXISTS jobs(pid TEXT,job_id TEXT, fingerprint TEXT,binding_json TEXT,state TEXT,started_at TEXT,finished_at TEXT,PRIMARY KEY(pid,job_id)); CREATE TABLE IF NOT EXISTS attempts(seq INTEGER PRIMARY KEY AUTOINCREMENT,pid TEXT,job_id TEXT,stage TEXT,state TEXT,started_at TEXT,finished_at TEXT,outputs TEXT,error_kind TEXT); CREATE TABLE IF NOT EXISTS stages(pid TEXT,job_id TEXT,stage TEXT,state TEXT,outputs TEXT,attempt INTEGER,PRIMARY KEY(pid,job_id,stage));")
    def close(self): self.db.close()
    def status(self,job_id):
        pid=self.manifest.project_id
        r=self.db.execute("SELECT fingerprint,state,started_at,finished_at FROM jobs WHERE pid=? AND job_id=?",(pid,job_id)).fetchone()
        if not r: raise JobError("job not found")
        attempts=[dict(zip(("seq","stage","state","started_at","finished_at","outputs","error_kind"),a)) for a in self.db.execute("SELECT seq,stage,state,started_at,finished_at,outputs,error_kind FROM attempts WHERE pid=? AND job_id=? ORDER BY seq",(pid,job_id))]
        for a in attempts: a["outputs"]=json.loads(a["outputs"]) if a["outputs"] else None
        return {"project_id":pid,"job_id":job_id,"fingerprint":r[0],"state":r[1],"started_at":r[2],"finished_at":r[3],"attempts":attempts}
    def _validate_refs(self,refs):
        for ref in refs:
            row=self.storage.read(self.manifest.project_id,ref["layer"],ref["record_id"],ref.get("version"))
            if canonical(exact_ref(row,ref["layer"])) != canonical(ref): raise JobError("durable output reference differs")
    def run(self,job_id,pause_after=None):
        if not isinstance(job_id,str) or not job_id or len(job_id)>64 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in job_id): raise JobError("invalid job id")
        if pause_after is not None and pause_after not in STAGES: raise JobError("unknown pause stage")
        lockpath=self.directory/("job-"+job_id+".lock")
        fd=os.open(lockpath,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise JobError("job already running")
            try: return self._run_locked(job_id,pause_after)
            except Exception:
                if self.db.in_transaction:self.db.execute("ROLLBACK")
                self.db.execute("UPDATE jobs SET state='blocked',finished_at=? WHERE pid=? AND job_id=? AND state NOT IN ('failed','unknown_external','failed_external_retained')",(now(),self.manifest.project_id,job_id))
                raise
        finally: os.close(fd)
    def _run_locked(self,job_id,pause_after):
        pid=self.manifest.project_id
        bound=binding(self.contract,self.as_of,__version__,self.manifest)
        previous=self.db.execute("SELECT fingerprint FROM jobs WHERE pid=? AND job_id=?",(pid,job_id)).fetchone()
        if previous and previous[0]!=bound["fingerprint"]: raise JobError("job tool/pack/config/as_of changed; cannot resume")
        if not previous:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,NULL)",(pid,job_id,bound["fingerprint"],canonical(bound).decode(),"created",now()))
                for stage in STAGES:self.db.execute("INSERT INTO stages VALUES(?,?,?,?,NULL,NULL)",(pid,job_id,stage,"pending"))
                self.db.execute("COMMIT")
            except Exception:self.db.execute("ROLLBACK");raise
        states={s:(state,json.loads(out) if out else None,attempt) for s,state,out,attempt in self.db.execute("SELECT stage,state,outputs,attempt FROM stages WHERE pid=? AND job_id=?",(pid,job_id))}
        # Lock ownership proves no previous worker remains active. Preserve the abandoned attempt.
        for stage,(state,out,attempt) in states.items():
            if state=="running":
                recovery="unknown_external" if stage=="crawl" else "interrupted_internal"
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    self.db.execute("UPDATE attempts SET state=?,finished_at=?,error_kind=? WHERE seq=?",(recovery,now(),recovery,attempt))
                    self.db.execute("UPDATE stages SET state=? WHERE pid=? AND job_id=? AND stage=?",(recovery,pid,job_id,stage))
                    self.db.execute("COMMIT")
                except Exception:self.db.execute("ROLLBACK");raise
                states[stage]=(recovery,out,attempt)
        outputs={}
        adapter=Stages(self.manifest,self.contract,self.storage,self.as_of)
        for stage in STAGES:
            state,out,_=states[stage]
            if stage=="crawl" and state=="failed":
                self.db.execute("UPDATE jobs SET state='failed_external_retained' WHERE pid=? AND job_id=?",(pid,job_id))
                raise JobError("failed external stage retained; no automatic replay")
            if state=="unknown_external":
                self.db.execute("UPDATE jobs SET state='unknown_external' WHERE pid=? AND job_id=?",(pid,job_id))
                raise JobError("external stage result unknown; no automatic replay")
            if state=="completed":
                if stage in ("crawl","clean","score"):
                    self._validate_refs(out)
                elif stage=="audit":
                    self._validate_refs([item["audit"] for item in out])
                    from .consumer import Consumer
                    # Recompute exact historic chains without appending a replacement audit version.
                    Consumer(self.manifest,self.contract,self.storage,self.as_of).dataset(out)
                if stage=="deliver":
                    from .consumer import Consumer
                    current=Consumer(self.manifest,self.contract,self.storage,self.as_of).publication(out)
                    if digest(current)!=out["report_hash"]:raise JobError("completed delivery changed")
                outputs[stage]=out
                continue
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute("UPDATE jobs SET state='running',finished_at=NULL WHERE pid=? AND job_id=?",(pid,job_id))
                cur=self.db.execute("INSERT INTO attempts(pid,job_id,stage,state,started_at) VALUES(?,?,?,?,?)",(pid,job_id,stage,"running",now()))
                attempt=cur.lastrowid
                self.db.execute("UPDATE stages SET state='running',attempt=? WHERE pid=? AND job_id=? AND stage=?",(attempt,pid,job_id,stage));self.db.execute("COMMIT")
            except Exception:self.db.execute("ROLLBACK");raise
            out=None
            try:
                if binding(self.contract,self.as_of,__version__,self.manifest)["fingerprint"]!=bound["fingerprint"]: raise JobError("binding changed during job")
                if stage=="crawl":
                    crawler=Crawler(self.manifest,self.storage)
                    try: receipts=crawler.crawl()
                    finally: crawler.close()
                    if any(r.get("ok") is not True for r in receipts):
                        out={"receipts":receipts}
                        raise JobError("crawl retained failure; no new retry")
                    out=[exact_ref(self.storage.read(pid,"RAW",r["raw_id"]),"RAW") for r in receipts]
                elif stage=="clean":
                    out=[exact_ref(row,"ODS") for raw in outputs["crawl"] for row in adapter.clean(raw["record_id"])]
                elif stage=="score":
                    out=[exact_ref(adapter.score(ref["record_id"],ref["version"]),"DW") for ref in outputs["clean"]]
                elif stage=="audit":
                    out=[]
                    for ref in outputs["score"]:
                        dw=self.storage.read(pid,"DW",ref["record_id"],ref["version"])
                        ods=self.storage.read(pid,"ODS",dw["parent_ref"]["record_id"],dw["parent_ref"]["version"])
                        rawref=ods["parent_ref"]
                        audit=adapter.audit(rawref["record_id"],ref["record_id"],ref["version"])
                        item={"raw":rawref,"dw":ref,"audit":exact_ref(audit["audit"],"APP")}
                        out.append(item)
                        if audit["passed"] is not True: raise JobError("audit admission blocked")
                else:
                    from .consumer import Consumer
                    out=Consumer(self.manifest,self.contract,self.storage,self.as_of).publish(outputs["audit"])
                if not out: raise JobError("stage produced no outputs")
                serialized=canonical(out).decode()
                self.db.execute("BEGIN IMMEDIATE")
                self.db.execute("UPDATE attempts SET state='completed',finished_at=?,outputs=? WHERE seq=?",(now(),serialized,attempt))
                self.db.execute("UPDATE stages SET state='completed',outputs=? WHERE pid=? AND job_id=? AND stage=?",(serialized,pid,job_id,stage));self.db.execute("COMMIT")
                outputs[stage]=out
            except Exception as exc:
                if self.db.in_transaction:self.db.execute("ROLLBACK")
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    self.db.execute("UPDATE attempts SET state='failed',finished_at=?,outputs=?,error_kind=? WHERE seq=?",(now(),canonical(out).decode() if out is not None else None,type(exc).__name__,attempt))
                    self.db.execute("UPDATE stages SET state='failed' WHERE pid=? AND job_id=? AND stage=?",(pid,job_id,stage))
                    self.db.execute("UPDATE jobs SET state='failed',finished_at=? WHERE pid=? AND job_id=?",(now(),pid,job_id))
                    self.db.execute("COMMIT")
                except Exception:self.db.execute("ROLLBACK");raise
                raise
            if pause_after==stage:
                self.db.execute("UPDATE jobs SET state='paused' WHERE pid=? AND job_id=?",(pid,job_id))
                return self.status(job_id)
        self.db.execute("UPDATE jobs SET state='completed',finished_at=? WHERE pid=? AND job_id=?",(now(),pid,job_id))
        return self.status(job_id)
