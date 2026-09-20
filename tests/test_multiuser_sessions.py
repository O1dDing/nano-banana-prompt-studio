"""所有账户和生成调用均为测试替身，不读取真实身份或消耗额度。"""
import threading
import time
from collections import deque
from pathlib import Path

import pytest

from nano_banana.codex_bridge.leases import Leases, ExpiredSession


class Clock:
    def __init__(self):
        self.value = 1000.0
    def __call__(self):
        return self.value
    def advance(self, seconds):
        self.value += seconds


def test_heartbeat_30_seconds_lease_90_and_no_resurrection():
    clock, removed = Clock(), []
    leases = Leases(clock=clock, dispose=lambda l: removed.append(l.key), sweep_seconds=0)
    a, la = leases.create()
    b, lb = leases.create()
    for _ in range(3):
        clock.advance(30)
        leases.heartbeat(a)
    leases.sweep()
    assert leases.get(a) is la
    assert lb.closed.is_set() and removed == [lb.key]
    with pytest.raises(ExpiredSession):
        leases.heartbeat(b)
    leases.close()


def test_24_hours_is_absolute_even_with_continuous_heartbeat():
    clock = Clock()
    leases = Leases(clock=clock, sweep_seconds=0)
    token, lease = leases.create()
    for _ in range(2879):
        clock.advance(30)
        leases.heartbeat(token)
    clock.advance(30)
    with pytest.raises(ExpiredSession):
        leases.heartbeat(token)
    assert lease.closed.is_set()
    leases.close()


def test_tenant_runtime_environment_is_thread_local(tmp_path):
    from nano_banana.codex_bridge.runtime import runtime_identity, safe_environment
    barrier = threading.Barrier(4)
    result = {}
    def worker(i):
        home = tmp_path / str(i)
        with runtime_identity(home):
            barrier.wait(timeout=2)
            result[i] = safe_environment()['CODEX_HOME']
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert result == {i: str(tmp_path / str(i)) for i in range(4)}


def test_image_task_ownership_read_cancel_and_cleanup():
    from nano_banana.web.image_tasks import ImageTaskManager
    manager = ImageTaskManager()
    gate = threading.Event()
    task = manager.submit(lambda: gate.wait(1) or 'image', provider='x', model='x', owner='alice')
    key = task['task_id']
    try:
        assert manager.get(key, owner='bob') is None
        assert manager.get(key) is None
        assert manager.cancel(key, owner='bob') is None
        assert manager.get(key, owner='alice') is not None
        manager.cancel_owner('alice')
        gate.set()
    finally:
        gate.set()
        manager._executor.shutdown(wait=True)


def test_bridge_job_ownership_and_expiration():
    from nano_banana.codex_bridge.server import JobManager
    gate = threading.Event()
    def run(body, stop, progress, *, owner=None):
        stop.wait(1)
        return {'text': owner}
    manager = JobManager(runner=run, workers=1)
    try:
        job = manager.submit({'kind': 'image', 'messages': [{'role': 'user', 'content': 'x'}]}, owner='alice')
        key = job['task_id']
        assert manager.get(key, owner='bob') is None
        assert manager.cancel(key, owner='bob') is None
        manager.cancel_owner('alice')
        assert manager.jobs[key]['cancel'].is_set()
    finally:
        manager.close()


@pytest.fixture
def multi_app(tmp_path, monkeypatch):
    monkeypatch.setenv('NANO_MULTIUSER', '1')
    monkeypatch.setenv('NANO_SESSION_ROOT', str(tmp_path / 'sessions'))
    admin = tmp_path / 'admin-key'
    admin.write_text('a' * 48)
    monkeypatch.setenv('NANO_ADMIN_TOKEN_FILE', str(admin))
    from nano_banana.core.config import AIConfigManager
    from nano_banana.web import context
    owner = AIConfigManager(config_path=tmp_path / 'owner.yaml')
    owner.save_config({'api_key': 'server-secret-do-not-copy', 'model': 'owner-model'})
    monkeypatch.setitem(context._legacy, 'config_manager', owner)
    from nano_banana.web.app import create_app
    app = create_app()
    app.config['TESTING'] = True
    yield app
    app.extensions['nano_sessions'].close()


def open_tab(client):
    response = client.post('/api/session/open', headers={'X-Nano-Client': 'web'})
    assert response.status_code == 201
    return {'X-Nano-Session': response.json['token']}


def test_private_config_and_presets_are_isolated(multi_app):
    client = multi_app.test_client()
    a, b = open_tab(client), open_tab(client)
    assert client.get('/api/config').status_code == 401
    assert client.get('/api/config', headers=a).json['has_api_key'] is False
    assert client.post('/api/config', headers=a, json={'codex_model': 'alice-model', 'api_key': 'alice-key'}).status_code == 200
    assert client.get('/api/config', headers=b).json['codex_model'] != 'alice-model'
    assert client.get('/api/config', headers=b).json['has_api_key'] is False
    assert client.post('/api/presets', headers=a, json={'name': 'mine', 'data': {'note': 'private'}}).status_code == 200
    assert client.get('/api/presets/mine', headers=b).status_code == 404
    assert client.get('/api/presets/mine', headers=a).json == {'note': 'private'}
    assert client.post('/api/presets', headers=a, json={'name': '../steal', 'data': {'x': 1}}).status_code == 400
    assert client.post('/api/config', headers=b, json={'base_url': 'http://127.0.0.1:8787'}).status_code == 400
    assert client.post('/api/config', headers=b, json={'base_url': 'https://api.openai.com/v1'}).status_code == 200


def test_owner_unlock_does_not_promote_other_tabs(multi_app):
    client = multi_app.test_client()
    a, b = open_tab(client), open_tab(client)
    assert client.post('/api/session/owner', headers=a, json={'key': 'wrong'}).status_code == 403
    assert client.post('/api/session/owner', headers=a, json={'key': 'a' * 48}).status_code == 200
    assert client.get('/api/config', headers=a).json['model'] == 'owner-model'
    assert client.get('/api/config', headers=b).json['model'] != 'owner-model'
    assert client.get('/api/config', headers=b).json['has_api_key'] is False


def test_logout_destroy_and_refresh_resume(multi_app):
    client = multi_app.test_client()
    a, b = open_tab(client), open_tab(client)
    manager = multi_app.extensions['nano_sessions']
    lease = manager.leases.get(a['X-Nano-Session'])
    directory = lease.state['scope'].directory
    assert client.post('/api/session/heartbeat', headers=a).status_code == 200
    # 浏览器刷新只重用短期页签凭证，不重新生成身份。
    assert client.get('/api/config', headers=a).status_code == 200
    assert client.delete('/api/session/current', headers=a).status_code == 200
    assert not directory.exists()
    assert client.get('/api/config', headers=a).status_code == 401
    assert client.get('/api/config', headers=b).status_code == 200


def test_cross_origin_and_no_global_fallback(multi_app):
    client = multi_app.test_client()
    a = open_tab(client)
    assert client.post('/api/session/open').status_code == 403
    assert client.get('/api/config', headers={**a, 'Origin': 'https://bad.example'}).status_code == 403
    assert client.post('/api/generate-image', json={'provider': 'codex_images', 'prompt': 'x'}).status_code == 401
    assert client.get('/api/health').json['multiuser'] is True


def test_each_device_login_uses_an_independent_identity_and_cleanup(tmp_path, monkeypatch):
    from nano_banana.codex_bridge.auth_sessions import AuthSessions
    from nano_banana.codex_bridge import runtime
    finish = threading.Event()
    clock = Clock()
    class FakeRpc:
        counter = 0
        def __init__(self, work):
            self.closed = threading.Event()
            self.pending = deque()
            self.home, register = runtime._IDENTITY.get()
            self.uid = self.home.name
            self.sent = False
            register(self)
        def initialize(self): pass
        def call(self, method, params, **kw):
            if method == 'account/login/start':
                return {'type': 'chatgptDeviceCode', 'loginId': self.uid,
                        'verificationUrl': 'https://auth.openai.com/codex/device',
                        'userCode': self.uid[-8:]}
            if method == 'account/read': return {'account': {'type': 'chatgpt', 'planType': 'plus'}}
            return {}
        def _get(self):
            if finish.wait(.01) and not self.sent:
                self.sent = True
                return {'method': 'account/login/completed', 'params': {'loginId': self.uid, 'success': True}}
            return None
        def close(self): self.closed.set()
    sessions = AuthSessions(tmp_path, clock=clock, rpc_factory=FakeRpc, sweep_seconds=0)
    a, b = sessions.create(), sessions.create()
    try:
        sessions.start_login(a['session_token']); sessions.start_login(b['session_token'])
        for _ in range(200):
            sa, sb = sessions.status(a['session_token']), sessions.status(b['session_token'])
            if sa['state'] == sb['state'] == 'pending': break
            time.sleep(.01)
        assert sa['user_code'] and sa['user_code'] != sb['user_code']
        la, lb = sessions.require(a['session_token']), sessions.require(b['session_token'])
        assert la.state['home'] != lb.state['home']
        finish.set()
        for _ in range(200):
            if la.state['status'] == lb.state['status'] == 'ready': break
            time.sleep(.01)
        assert la.state['status'] == lb.state['status'] == 'ready'
        sessions.expire(a['session_token'])
        for _ in range(200):
            if not la.state['home'].exists(): break
            time.sleep(.01)
        assert not la.state['home'].exists()
        assert lb.state['home'].exists() and not lb.closed.is_set()
    finally:
        finish.set()
        sessions.close()
