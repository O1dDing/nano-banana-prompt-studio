import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from nano_banana.codex_bridge.server import JobManager, BridgeServer, validate_payload
from nano_banana.codex_bridge.runtime import Cancelled


def payload():
    return {'kind':'image','messages':[{'role':'user','content':'cat'}]}


def wait(manager, key):
    for _ in range(200):
        item=manager.get(key)
        if item['status'] in {'completed','failed','cancelled'}:return item
        time.sleep(.01)
    raise AssertionError('timed out')


def test_four_parallel_tasks_independent_and_ack():
    barrier=threading.Barrier(4)
    def runner(data,cancelled,progress):
        barrier.wait(timeout=2)
        return {'text':data['messages'][0]['content']}
    manager=JobManager(runner=runner, workers=4)
    try:
        ids=[]
        for i in range(4):
            body=payload();body['messages'][0]['content']=str(i)
            ids.append(manager.submit(body)['task_id'])
        assert len(set(ids))==4
        for i,key in enumerate(ids):
            result=wait(manager,key)
            assert result['status']=='completed' and result['result']['text']==str(i)
            manager.cancel(key,forget=True)
            assert manager.get(key) is None
    finally:manager.close()


def test_cancel_interrupts_running_job():
    started=threading.Event()
    def runner(data,cancelled,progress):
        started.set();cancelled.wait(2)
        raise Cancelled()
    manager=JobManager(runner=runner,workers=1)
    try:
        key=manager.submit(payload())['task_id'];assert started.wait(1)
        manager.cancel(key)
        assert wait(manager,key)['status']=='cancelled'
    finally:manager.close()


def test_queue_capacity_and_payload_reject(monkeypatch):
    monkeypatch.setenv('CODEX_MAX_PENDING','1')
    def runner(data,cancelled,progress):
        cancelled.wait(1);return {}
    manager=JobManager(runner=runner,workers=1)
    try:
        manager.submit(payload())
        with pytest.raises(OverflowError):manager.submit(payload())
        assert validate_payload({**payload(),'effort':'max'})['effort'] == 'max'
        assert validate_payload({**payload(),'effort':'none'})['effort'] == 'none'
        with pytest.raises(ValueError):validate_payload({**payload(),'effort':'ultra'})
        with pytest.raises(ValueError):validate_payload({**payload(),'command':'rm'})
        with pytest.raises(ValueError):validate_payload({'kind':'prompt','messages':payload()['messages'],'output_schema':{'$ref':'https://bad.invalid'}})
    finally:manager.close()


def test_private_http_no_unauthenticated_jobs():
    manager=JobManager(runner=lambda *_:{'text':'ok'},workers=1)
    server=BridgeServer(('127.0.0.1',0), 'a'*40, manager)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_address[1])
    try:
        with pytest.raises(HTTPError) as exc:urlopen(base+'/health')
        assert exc.value.code==401
        response=urlopen(Request(base+'/health',headers={'Authorization':'Bearer '+'a'*40}))
        assert json.load(response)['ok'] is True
        request=Request(base+'/v1/jobs',data=json.dumps(payload()).encode(),headers={'Authorization':'Bearer '+'a'*40,'Content-Type':'application/json'})
        result=json.load(urlopen(request))
        assert result['task_id']
    finally:
        server.shutdown();server.server_close();manager.close();thread.join()
