"""Offline wrapping only: never signs, renews, fetches, or reads an Owner key."""
import argparse, base64, datetime as dt, json, os, re, stat, sys
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl
HOST='bdwrhshgdeghgyzwpxnl.supabase.co'
PROD='app-lyart-eta-22.vercel.app'
MIMES={'json':'application/json; charset=utf-8','html':'text/html; charset=utf-8','jsonl':'application/x-ndjson; charset=utf-8','csv':'text/csv; charset=utf-8'}
def reject(): raise ValueError('page_link_invalid')
def plain_path(p):
 if not p.is_absolute() or any(q.is_symlink() for q in (p,*p.parents)): reject()
def read_private(p):
 plain_path(p)
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  s=os.fstat(fd)
  if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or stat.S_IMODE(s.st_mode)!=0o600 or s.st_uid!=os.getuid() or not 0<s.st_size<=24576: reject()
  raw=os.read(fd,24577)
  if len(raw)!=s.st_size: reject()
  def unique(pairs):
   out={}
   for k,v in pairs:
    if k in out: reject()
    out[k]=v
   return out
  return json.loads(raw.decode('utf8'),object_pairs_hook=unique,parse_constant=lambda _:reject())
 finally: os.close(fd)
def validate(v,now=None):
 now=now or dt.datetime.now(dt.timezone.utc)
 if type(v)is not dict or set(v)!={'schema','owner_scope','report_hash','project_id','issued_at','expires_at','expires_in','formats','media_bytes_included'}: reject()
 if v['schema']!='crowd-publication-links-v1' or v['owner_scope']!='crowd-owner-main' or type(v['report_hash'])is not str or not re.fullmatch('[a-f0-9]{64}',v['report_hash']) or v['project_id']!='shanghai-existing-six-domain' or type(v['expires_in'])is not int or v['expires_in']!=900 or v['media_bytes_included']is not False: reject()
 stamps=[]
 for k in ['issued_at','expires_at']:
  if type(v[k])is not str or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z',v[k]): reject()
  stamps.append(dt.datetime.fromisoformat(v[k].replace('Z','+00:00')))
 if (stamps[1]-stamps[0]).total_seconds()!=900 or stamps[0]>now+dt.timedelta(seconds=30) or stamps[1]<=now: reject()
 if type(v['formats'])is not dict or set(v['formats'])!=set(MIMES): reject()
 for f,mime in MIMES.items():
  e=v['formats'][f]
  if type(e)is not dict or set(e)!={'sha256','bytes','mime','signed_url'} or type(e['sha256'])is not str or not re.fullmatch('[a-f0-9]{64}',e['sha256']) or type(e['bytes'])is not int or not 0<e['bytes']<=1000000 or e['mime']!=mime or type(e['signed_url'])is not str or len(e['signed_url'])>8192: reject()
  u=urlsplit(e['signed_url']); expected='/storage/v1/object/sign/crowd-publication-snapshots/publications/crowd-owner-main/'+v['report_hash']+'/report.'+f
  if u.scheme!='https' or u.netloc!=HOST or u.path!=expected or u.fragment or not e['signed_url'].startswith('https://'+HOST+expected+'?'): reject()
  pairs=parse_qsl(u.query,keep_blank_values=True)
  if len(pairs)!=2 or sorted(k for k,_ in pairs)!=['download','token'] or dict(pairs)['download']!='' or not re.fullmatch('[A-Za-z0-9_.-]{1,4096}',dict(pairs)['token']): reject()
 if v['formats']['json']['sha256']!=v['report_hash']: reject()
 return v

def make(links, page, output):
 # Only the original production page is currently authorized here. Preview hosts require an explicit reviewed update.
 u=urlsplit(page)
 if u.scheme!='https' or u.netloc!=PROD or u.path!='/materials' or u.query or u.fragment: reject()
 links=Path(links); output=Path(output); plain_path(output)
 if output.parent!=links.parent: reject()
 v=validate(read_private(links)); encoded=base64.urlsafe_b64encode(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()).rstrip(b'=')
 if len(encoded)>32755: reject()
 raw=page.encode()+b'#publication='+encoded+b'\n'
 fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
 return {'report_hash':v['report_hash'],'expires_at':v['expires_at']}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--links-output',required=True);p.add_argument('--page',default='https://'+PROD+'/materials');p.add_argument('--output',required=True);a=p.parse_args()
 try: print(json.dumps(make(a.links_output,a.page,a.output)))
 except Exception: print('page_link_invalid',file=sys.stderr);sys.exit(1)
