"""M7 read-only delivery gate, immutable reports and a loopback HTTP consumer."""
from __future__ import annotations
import copy, html, json, os, tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
from . import __version__
from .auditor import Auditor
from .bindings import binding, canonical, digest, utc
from .stages import exact_ref
from .writer import append, record_id, wrap_record

class DeliveryError(ValueError): pass

def safe_url(value):
    if not isinstance(value,str):return None
    try:
        u=urlsplit(value)
        if u.scheme=="https" and u.hostname and u.username is None and u.password is None and not any(ord(c)<32 for c in value):return value
    except ValueError:pass
    return None

def atomic(path,payload):
    path=Path(path)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):raise DeliveryError("delivery path symlink")
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".delivery-",dir=path.parent)
    with os.fdopen(fd,"wb") as f:f.write(payload);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

class Consumer:
    def __init__(self,manifest,contract,storage,as_of):
        self.manifest,self.contract,self.storage,self.as_of=manifest,contract,storage,as_of
        self.pid=manifest.project_id
        self._derive_asof=as_of is None
    def dataset(self,chains):
        if not isinstance(chains,list) or not chains:raise DeliveryError("no audited chains")
        bound=binding(self.contract,self.as_of,__version__,self.manifest)
        items=[];seen=set()
        for chain in chains:
            if not isinstance(chain,dict) or set(chain)!={"raw","dw","audit"}:raise DeliveryError("invalid chain contract")
            rows={}
            for name in ("raw","dw","audit"):
                ref=chain[name]
                if ref.get("project_id")!=self.pid:raise DeliveryError("cross-project delivery")
                required="RAW" if name=="raw" else "DW" if name=="dw" else "APP"
                if ref.get("layer")!=required:raise DeliveryError("reference layer differs")
                row=self.storage.read(self.pid,required,ref.get("record_id"),ref.get("version"))
                if canonical(exact_ref(row,required))!=canonical(ref):raise DeliveryError("exact reference changed")
                rows[name]=row
            dw,audit=rows["dw"],rows["audit"]
            key=(dw["record_id"],dw["version"])
            if key in seen:raise DeliveryError("duplicate DW delivery")
            seen.add(key)
            if audit.get("schema_kind")!="audit" or audit["content"].get("audit",{}).get("passed") is not True:raise DeliveryError("stored audit failed")
            if canonical(audit["parent_ref"])!=canonical(chain["dw"]):raise DeliveryError("audit exact DW parent differs")
            result=Auditor(self.contract,self.as_of,__version__,self.storage,self.pid).audit(self.manifest,chain["raw"]["record_id"],dw["record_id"],dw["version"])
            if result.passed is not True:raise DeliveryError("current audit failed")
            if canonical(result.audit_record["payload"])!=canonical(audit["content"]):raise DeliveryError("stored audit differs from independent current derivation")
            if digest(wrap_record("APP",self.pid,audit["record_id"],audit["parent_ref"],result.audit_record["payload"],"audit"))!=audit["content_hash"]:raise DeliveryError("stored audit hash differs")
            c=dw["content"]
            items.append({**{k:copy.deepcopy(c[k]) for k in ("identity","draft","classification","evidence","sources","unknowns","scope","score")},"metadata":copy.deepcopy(c.get("metadata",{})),"refs":copy.deepcopy(chain)})
        return {"project_id":self.pid,"domain":self.manifest.domain,"region":self.manifest.region,"as_of":self.as_of,"tool_version":__version__,"config_fingerprint":bound["fingerprint"],"items":items,"presentation":copy.deepcopy(self.contract.fields.get("presentation",{}))}
    def publish(self,chains):
        data=self.dataset(chains);blob=canonical(data);sha=digest(data)
        base=self.manifest.path.parent/"data"/"deliveries"/sha
        for name,content in (("report.json",blob),("index.html",render(data).encode("utf-8"))):
            path=base/name
            if path.exists():
                if path.is_symlink() or path.read_bytes()!=content:raise DeliveryError("existing immutable report differs")
            else:atomic(path,content)
        receipt_path=base/"receipt.json"
        if receipt_path.exists():
            receipt=json.loads(receipt_path.read_text())
            self.publication(receipt)
            atomic(self.manifest.path.parent/"data"/"delivery-index.json",canonical(receipt))
            return receipt
        views=[]
        for item in data["items"]:
            identity=item["identity"]
            rid=record_id("view",self.contract.pack_id,identity["source_record_revision"],identity["source_record_id"])
            content={"view":{"report_hash":sha,"item":item,"audit_ref":item["refs"]["audit"]},"provenance":{"tool_version":__version__,"config_fingerprint":data["config_fingerprint"]}}
            version=append(self.storage,self.pid,"APP",rid,item["refs"]["dw"],content,"view")
            views.append(exact_ref(self.storage.read(self.pid,"APP",rid,version),"APP"))
        index={"report_hash":sha,"chains":chains,"views":views,"as_of":self.as_of,"config_fingerprint":data["config_fingerprint"],"directory":"data/deliveries/"+sha,"item_count":len(data["items"])}
        atomic(receipt_path,canonical(index))
        atomic(self.manifest.path.parent/"data"/"delivery-index.json",canonical(index))
        return index
    def current(self):
        path=self.manifest.path.parent/"data"/"delivery-index.json"
        if path.is_symlink():raise DeliveryError("delivery index symlink")
        return self.publication(json.loads(path.read_text()))
    def publication(self,index):
        sha=index.get("report_hash")
        if not isinstance(sha,str) or len(sha)!=64 or any(c not in "0123456789abcdef" for c in sha):raise DeliveryError("invalid publication hash")
        base=self.manifest.path.parent/"data"/"deliveries"/sha
        for name in ("receipt.json","report.json","index.html"):
            path=base/name
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):raise DeliveryError("publication path symlink")
        stored=json.loads((base/"receipt.json").read_text())
        if canonical(stored)!=canonical(index):raise DeliveryError("immutable publication receipt differs")
        utc(index.get("as_of"),"stored evaluation time")
        if self._derive_asof:self.as_of=index["as_of"]
        elif index["as_of"]!=self.as_of:raise DeliveryError("delivery evaluation time differs")
        data=self.dataset(index["chains"])
        if digest(data)!=index["report_hash"] or data["config_fingerprint"]!=index["config_fingerprint"]:raise DeliveryError("delivery index stale")
        if len(index["views"])!=len(data["items"]):raise DeliveryError("APP view count differs")
        for ref,item in zip(index["views"],data["items"]):
            row=self.storage.read(self.pid,"APP",ref["record_id"],ref["version"])
            identity=item["identity"]
            rid=record_id("view",self.contract.pack_id,identity["source_record_revision"],identity["source_record_id"])
            content={"view":{"report_hash":index["report_hash"],"item":item,"audit_ref":item["refs"]["audit"]},"provenance":{"tool_version":__version__,"config_fingerprint":data["config_fingerprint"]}}
            expected=wrap_record("APP",self.pid,rid,item["refs"]["dw"],content,"view")
            if ref.get("project_id")!=self.pid or ref.get("layer")!="APP" or canonical(exact_ref(row,"APP"))!=canonical(ref) or row["content_hash"]!=digest(expected):raise DeliveryError("APP view differs from audited item")
        if index.get("item_count")!=len(data["items"]) or index.get("directory")!="data/deliveries/"+sha:raise DeliveryError("publication metadata differs")
        if (base/"report.json").read_bytes()!=canonical(data) or (base/"index.html").read_bytes()!=render(data).encode("utf-8"):raise DeliveryError("immutable report bytes differ")
        return data

def render(data):
    # Storage normalizes mapping order; rendering must use the same canonical order.
    data=json.loads(canonical(data))
    esc=lambda v:html.escape(str(v),quote=True)
    present=data.get("presentation",{})
    if not isinstance(present,dict):raise DeliveryError("presentation must be data mapping")
    labels=present.get("field_labels",{});unknown_labels=present.get("unknown_labels",{})
    if not isinstance(labels,dict) or not isinstance(unknown_labels,dict):raise DeliveryError("presentation labels must be mapping")
    title=present.get("report_title","发现报告")
    chunks=['<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>body{font:16px system-ui;background:#f5f4ef;color:#182923;max-width:1050px;margin:auto;padding:30px}article{background:white;border-radius:14px;padding:24px;margin:20px 0}h1,h2{color:#225342}a{color:#215e83}dt{font-weight:bold}dd{margin:5px 0 16px}small{color:#5a6963}pre{white-space:pre-wrap;word-break:break-word}summary{cursor:pointer}.notice{background:#e7ece4;padding:16px;border-radius:10px}</style><body>']
    chunks.append('<h1>'+esc(title)+'</h1><p>'+esc(present.get("description",data["project_id"]))+'</p><p>'+str(len(data["items"]))+' 条来源已审的发现</p>')
    if present.get("notice"):chunks.append('<p class="notice">'+esc(present["notice"])+ '</p>')
    for item in data["items"]:
        chunks.append('<article><h2>'+esc(item["identity"].get("title",item["identity"]["source_record_id"]))+'</h2><dl>')
        for field,value in item["draft"].items():
            if field==present.get("title_field"):continue
            chunks.append('<dt>'+esc(labels.get(field,field))+'</dt><dd>'+esc(json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else value)+'</dd>')
        chunks.append('</dl>')
        if item["unknowns"]:
            unknown=[]
            for field,value in item["unknowns"].items():
                display=present.get("unknown_value_label","待确认") if value=="unknown" else value
                unknown.append(str(unknown_labels.get(field,field))+'：'+str(display))
            chunks.append('<p>尚未确认：'+esc('；'.join(unknown))+'</p>')
        chunks.append('<h3>查看来源</h3><ul>')
        for src in item["sources"]:
            url=safe_url(src.get("url"));label=esc(urlsplit(url).hostname if url else src.get("source_id","来源"))
            chunks.append('<li>'+('<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+label+'</a>' if url else label)+' · 取得时间 '+esc(src.get("retrieved_at"))+'</li>')
        detail={k:item[k] for k in ("metadata","classification","scope","sources","evidence","score","refs")}
        detail["evaluation"]={"as_of":data["as_of"],"tool_version":data["tool_version"],"config_fingerprint":data["config_fingerprint"]}
        chunks.append('</ul><details><summary>核对原文、证据和版本</summary><pre>'+esc(json.dumps(detail,ensure_ascii=False,indent=2))+'</pre></details></article>')
    return ''.join(chunks)+"</body></html>"

def serve(manifests,pack_root,as_of=None,port=18790):
    from .manifest import Manifest
    from .pack_schema import load_pack
    from .storage_factory import make_storage
    # CLI holds only paths and fixed as_of. Re-load all configuration for every request.
    registry={}
    for path in manifests:
        m=Manifest.load(path)
        if m.project_id in registry:raise DeliveryError("duplicate project")
        registry[m.project_id]=str(path)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            route=urlsplit(self.path).path
            if route=="/":
                body=('<!doctype html><meta charset="utf-8"><h1>CTFS 项目索引</h1>'+''.join('<p><a href="/'+html.escape(pid,quote=True)+'/">'+html.escape(pid)+'</a></p>' for pid in registry)).encode()
                status,ctype=200,"text/html; charset=utf-8"
            else:
                parts=route.strip('/').split('/')
                if len(parts)>2 or parts[0] not in registry or (len(parts)==2 and parts[1]!="report.json"):
                    status,ctype,body=404,"application/json",b'{"error":"not_found"}'
                else:
                    store=None
                    try:
                        m=Manifest.load(registry[parts[0]])
                        if m.project_id != parts[0]:raise DeliveryError("route project changed")
                        selected=m.ontology.get("packs",[])
                        if len(selected)!=1:raise DeliveryError("exactly one active pack required")
                        contract=load_pack(Path(pack_root),selected[0]);store=make_storage(m.to_dict(),m.path.parent,read_only=True)
                        data=Consumer(m,contract,store,as_of).current()
                        json_requested=len(parts)==2
                        body=canonical(data) if json_requested else render(data).encode()
                        status,ctype=200,"application/json; charset=utf-8" if json_requested else "text/html; charset=utf-8"
                    except Exception:
                        status,ctype,body=409,"application/json",b'{"error":"delivery_gate_failed"}'
                    finally:
                        if store is not None:store.close()
            self.send_response(status);self.send_header("Content-Type",ctype);self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control","no-store");self.send_header("Content-Security-Policy","default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'");self.send_header("X-Content-Type-Options","nosniff");self.end_headers();self.wfile.write(body)
    if type(port) is not int or not 1024<=port<=65535:raise DeliveryError("invalid loopback port")
    HTTPServer(("127.0.0.1",port),Handler).serve_forever()
