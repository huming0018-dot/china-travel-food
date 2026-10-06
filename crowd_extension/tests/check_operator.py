"""Small checks for publication identity, paged export and evidence bridge; no live backend."""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'cloud'))
import crowd_v4 as crowd

with tempfile.TemporaryDirectory() as tmp:
    tmp=Path(tmp)
    first=list(crowd.tasks([{'name':'测试餐厅','restaurant_id':17}]))[0]
    second=list(crowd.tasks([{'name':'测试餐厅','restaurant_id':17}]))[0]
    assert first['source_key']==second['source_key'] and first['restaurant_id']==17
    assert first['source_key']!=list(crowd.tasks([{'name':'测试餐厅分店'}]))[0]['source_key']
    try: list(crowd.tasks(['']))
    except ValueError: pass
    else: raise AssertionError('empty store name accepted')
    text='测试餐厅清蒸鱼真的好吃，这是逐字公开原话。'
    def proof(i):return {'proof_id':i,'store_name':'测试餐厅','verified_quote':text,'source_checked_at':'2026-10-05T14:00:00Z','record':{'standard':{'url':'https://www.xiaohongshu.com/explore/'+str(i).zfill(24)},'evidence':{'text':text},'extra':{'custom':True}}}
    calls=[]
    def mock_rpc(action,payload):
        assert action=='export';calls.append(payload['after_id'])
        return [proof(1)] if payload['after_id']==0 else [proof(3)] if payload['after_id']==1 else []
    destination=tmp/'verified.jsonl'
    with patch.object(crowd,'rpc',mock_rpc):
        assert crowd.export(destination)=={'exported':2,'total':2}
        assert calls==[0,1,3]
        assert crowd.export(destination)['total']==2
    pages,urls=crowd.verified_pages('测试餐厅',destination)
    assert len(pages)==2 and text in pages[0] and len(urls)==2
    assert crowd.verified_pages('其他店',destination)==([],[])
    original=destination.read_text()
    with patch('crowd_v4.os.replace',side_effect=OSError('simulated interrupted replace')):
        try:crowd.atomic(destination,'broken')
        except OSError:pass
        else:raise AssertionError('fault injection did not run')
    assert destination.read_text()==original
    assert not list(tmp.glob('.verified.jsonl*'))
print('PASS operator: stable task identity, paged/replayed export, source quotes, atomic file recovery')
