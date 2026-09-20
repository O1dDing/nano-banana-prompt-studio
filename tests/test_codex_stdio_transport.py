import os
import sys
import threading
from pathlib import Path

from nano_banana.codex_bridge import runtime


def test_real_stdio_response_interleaving_without_api(monkeypatch,tmp_path):
    fake=tmp_path/'fake-codex'
    fake.write_text('#!'+sys.executable+'\n'+r'''
import json,sys
for line in sys.stdin:
 m=json.loads(line);method=m.get('method');p=m.get('params',{})
 if 'id' not in m:continue
 if method=='initialize':result={}
 elif method=='account/read':result={'account':{'type':'chatgpt','planType':'plus'}}
 elif method=='thread/start':
  assert p['ephemeral'] is True and p['sandbox']=='read-only'
  result={'thread':{'id':'t','ephemeral':True}}
 elif method=='turn/start':
  print(json.dumps({'method':'item/completed','params':{'threadId':'t','turnId':'u','item':{'type':'agentMessage','text':'{"ok":true}'}}}),flush=True)
  print(json.dumps({'method':'turn/completed','params':{'threadId':'t','turn':{'id':'u','status':'completed'}}}),flush=True)
  result={'turn':{'id':'u'}}
 else:result={}
 print(json.dumps({'id':m['id'],'result':result}),flush=True)
''')
    fake.chmod(0o700)
    work=tmp_path/'work';work.mkdir()
    monkeypatch.setenv('CODEX_BIN',str(fake))
    monkeypatch.setenv('CODEX_WORK_DIR',str(work))
    monkeypatch.setattr(runtime,'protocol_capabilities',lambda:{'ready':True})
    result=runtime.run_job({'kind':'prompt','messages':[{'role':'user','content':'hello'}], 'web_search_mode':'disabled',
                           'output_schema':{'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}},threading.Event(),lambda _:None)
    assert 'true' in result['text']
    assert list(work.iterdir())==[]
