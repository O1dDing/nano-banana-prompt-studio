"""真实 HTTP 权限边界，身份/生成结果采用测试替身，不调用供应商。"""
import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from nano_banana.codex_bridge.multiuser import MultiuserBridge
from nano_banana.codex_bridge.server import JobManager


def test_bridge_http_never_falls_back_or_crosses_user_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_WORK_DIR', str(tmp_path))
    def fake_job(payload, cancelled, progress, *, owner=None):
        return {'text': owner or 'owner-only'}
    manager = JobManager(runner=fake_job, workers=2)
    server = MultiuserBridge(('127.0.0.1', 0), 'b' * 48, manager=manager)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    def req(method, path, token=None, data=None, internal=True):
        headers = {'Content-Type': 'application/json'}
        if internal:
            headers['Authorization'] = 'Bearer ' + 'b' * 48
        if token:
            headers['X-Codex-Session'] = token
        request = Request(base + path, method=method, headers=headers,
                          data=json.dumps(data).encode() if data is not None else None)
        with urlopen(request, timeout=3) as response:
            return json.load(response)
    body = {'kind': 'image', 'messages': [{'role': 'user', 'content': 'fixture'}]}
    try:
        with pytest.raises(HTTPError) as error:
            req('POST', '/v1/sessions', internal=False)
        assert error.value.code == 401
        assert req('GET', '/v1/status')['logged_in'] is False
        with pytest.raises(HTTPError) as error:
            req('POST', '/v1/jobs', data=body)
        assert error.value.code == 401
        a = req('POST', '/v1/sessions')['session_token']
        b = req('POST', '/v1/sessions')['session_token']
        for token in (a, b):
            lease = server.sessions.require(token)
            lease.state.update(status='ready', authenticated_at=time.monotonic())
        job = req('POST', '/v1/jobs', token=a, data=body)['task_id']
        for _ in range(100):
            result = req('GET', '/v1/jobs/' + job, token=a)
            if result['status'] == 'completed': break
            time.sleep(.01)
        assert result['status'] == 'completed'
        assert result['result']['text'] == server.sessions.require(a).key
        for method, suffix in [('GET', ''), ('POST', '/cancel'), ('DELETE', '')]:
            with pytest.raises(HTTPError) as error:
                req(method, '/v1/jobs/' + job + suffix, token=b)
            assert error.value.code == 404
        home = server.sessions.require(a).state['home']
        req('DELETE', '/v1/sessions/current', token=a)
        assert not home.exists()
        with pytest.raises(HTTPError) as error:
            req('POST', '/v1/jobs', token=a, data=body)
        assert error.value.code == 401
        assert req('POST', '/v1/sessions/heartbeat', token=b)['logged_in'] is True
    finally:
        server.shutdown()
        server.server_close()
        manager.close()
        thread.join(timeout=3)
