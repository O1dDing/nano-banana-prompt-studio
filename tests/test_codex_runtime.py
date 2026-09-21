import base64
import json
import threading
from collections import deque
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from nano_banana.codex_bridge import runtime

SCHEMA={'type':'object','properties':{'prompt':{'type':'string'}},'required':['prompt'],'additionalProperties':False}
PAYLOAD={'kind':'prompt','messages':[{'role':'system','content':'Return JSON'},{'role':'user','content':'draw a cat'}], 'output_schema':SCHEMA, 'web_search_mode':'disabled'}


class FakeRpc:
    events=[]
    params=[]
    account='chatgpt'
    ephemeral=True
    fail_turn=False
    def __init__(self, work, *args):
        self.work=work;self.thread_id=None;self.turn_id=None
        self.pending=deque(type(self).events)
        (work/'temporary-file').write_text('temporary')
    def initialize(self):pass
    def call(self, method, params, **kw):
        type(self).params.append((method,params))
        if method=='account/read':return {'account':{'type':self.account,'planType':'plus'}}
        if method=='thread/start':return {'thread':{'id':'t','ephemeral':self.ephemeral}}
        if method=='turn/start':
            if self.fail_turn: raise runtime.CodexError('failure')
            return {'turn':{'id':'u'}}
    def _get(self):raise RuntimeError('missing fake event')
    def interrupt(self):pass
    def close(self):pass


def event(item):
    return {'method':'item/completed','params':{'threadId':'t','turnId':'u','item':item}}


def finish():
    return {'method':'turn/completed','params':{'threadId':'t','turn':{'id':'u','status':'completed'}}}


@pytest.fixture
def fake(monkeypatch, tmp_path):
    FakeRpc.params=[];FakeRpc.events=[];FakeRpc.account='chatgpt';FakeRpc.ephemeral=True;FakeRpc.fail_turn=False
    monkeypatch.setattr(runtime,'Rpc',FakeRpc)
    monkeypatch.setattr(runtime,'protocol_capabilities',lambda:{'ready':True,'image_generation':True})
    monkeypatch.setenv('CODEX_WORK_DIR',str(tmp_path))
    return tmp_path


def test_prompt_ephemeral_without_auth_key_or_files(fake):
    FakeRpc.events=[event({'type':'agentMessage','id':'m','phase':'final_answer','text':'{"prompt":"cat"}'}), finish()]
    result=runtime.run_job(PAYLOAD, threading.Event(), lambda _:None)
    assert json.loads(result['text'])=={'prompt':'cat'}
    params=dict(FakeRpc.params)
    assert params['thread/start']['ephemeral'] is True
    assert params['thread/start']['sandbox']=='read-only'
    assert params['thread/start']['approvalPolicy']=='never'
    assert params['turn/start']['outputSchema']==SCHEMA
    assert list(fake.iterdir())==[]


def test_reject_api_auth_no_turn(fake):
    FakeRpc.account='apiKey'
    with pytest.raises(runtime.CodexError, match='ChatGPT'):
        runtime.run_job(PAYLOAD,threading.Event(),lambda _:None)
    assert 'turn/start' not in dict(FakeRpc.params)
    assert list(fake.iterdir())==[]


def test_reject_non_ephemeral_before_turn(fake):
    FakeRpc.ephemeral=False
    with pytest.raises(runtime.CodexError,match='ephemeral'):
        runtime.run_job(PAYLOAD,threading.Event(),lambda _:None)
    assert 'turn/start' not in dict(FakeRpc.params)
    assert list(fake.iterdir())==[]


def test_force_search_rejects_no_actual_event(fake):
    FakeRpc.events=[event({'type':'agentMessage','text':'{"prompt":"cat"}'}),finish()]
    with pytest.raises(runtime.CodexError,match='强制联网'):
        runtime.run_job({**PAYLOAD,'web_search_mode':'force'},threading.Event(),lambda _:None)
    assert list(fake.iterdir())==[]


def test_force_search_accepts_actual_completed_search(fake):
    FakeRpc.events=[event({'type':'webSearch','id':'s','query':'cat','action':{'type':'search'}}),event({'type':'agentMessage','text':'{"prompt":"cat"}'}),finish()]
    result=runtime.run_job({**PAYLOAD,'web_search_mode':'force'},threading.Event(),lambda _:None)
    assert result['metadata']['search_used'] is True


def test_missing_image_cannot_be_text_or_paid_fallback(fake):
    FakeRpc.events=[event({'type':'agentMessage','text':'image is saved'}),finish()]
    with pytest.raises(runtime.CodexError,match='原生'):
        runtime.run_job({**PAYLOAD,'kind':'image'},threading.Event(),lambda _:None)
    assert list(fake.iterdir())==[]


def test_native_image_artifact_and_cleanup(fake):
    buf=BytesIO();Image.new('RGB',(32,64)).save(buf,format='PNG')
    FakeRpc.events=[event({'type':'imageGeneration','id':'i','status':'completed','result':base64.b64encode(buf.getvalue()).decode()}),finish()]
    result=runtime.run_job({**PAYLOAD,'kind':'image'},threading.Event(),lambda _:None)
    assert result['images'][0].startswith('data:image/png;')
    assert result['metadata']['billing']=='codex_subscription'
    assert list(fake.iterdir())==[]


def test_file_escape_rejected(tmp_path):
    with pytest.raises(runtime.CodexError,match='临时目录'):
        runtime.extract_image_item({'status':'completed','savedPath':'/etc/passwd'}, tmp_path)


def test_shell_and_api_credentials_not_inherited(monkeypatch,tmp_path):
    monkeypatch.setenv('OPENAI_API_KEY','secret')
    monkeypatch.setenv('CODEX_API_KEY','secret')
    monkeypatch.setenv('HTTP_PROXY','http://gateway')
    environment=runtime.safe_environment()
    assert not {'OPENAI_API_KEY','CODEX_API_KEY','HTTP_PROXY'} & environment.keys()
    args=runtime.command(tmp_path,'prompt','disabled')
    assert 'history.persistence="none"' in args
    assert 'features.shell_tool=false' in args
    assert 'forced_login_method="chatgpt"' in args
    assert 'features.image_generation=false' in args
    assert args[-3:]==['app-server','--listen','stdio://']


def test_disallowed_tool_aborts_and_cleans(fake):
    FakeRpc.events=[{'method':'item/started','params':{'item':{'type':'commandExecution'}}}]
    with pytest.raises(runtime.CodexError,match='未授权'):
        runtime.run_job(PAYLOAD,threading.Event(),lambda _:None)
    assert list(fake.iterdir())==[]


def test_invalid_json_fails_without_applying(fake):
    FakeRpc.events=[event({'type':'agentMessage','text':'not json'}),finish()]
    with pytest.raises(runtime.CodexError,match='JSON'):
        runtime.run_job(PAYLOAD,threading.Event(),lambda _:None)
    assert list(fake.iterdir())==[]


def test_cancel_cleanup(fake):
    flag=threading.Event();flag.set()
    with pytest.raises(runtime.Cancelled):
        runtime.run_job(PAYLOAD,flag,lambda _:None)
    assert list(fake.iterdir())==[]
