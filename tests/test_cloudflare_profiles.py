"""Access RSA 签名使用测试密钥；不触碰 Cloudflare / Codex 真实账户。"""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from nano_banana.core.access_config import AccessConfig
from nano_banana.web.access_identity import AccessVerifier, AccessDenied, AccessUnavailable, Identity
from nano_banana.web.profiles import ProfileStore, ProfileConflict

ISSUER = 'https://nano-test.cloudflareaccess.com'
AUD = 'nano-app-test-audience'


@pytest.fixture
def policy(tmp_path):
    path = tmp_path / 'access.json'
    path.write_text(json.dumps({'issuer': ISSUER, 'audiences': [AUD],
                               'admin_emails': ['owner@example.com', 'second@example.com'],
                               'admin_subjects': ['admin-sub-3']}))
    return path


@pytest.fixture
def signing():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid='test', alg='RS256', use='sig')
    return key, {'keys': [jwk]}


def token(signing, sub='alice', email='alice@example.com', **overrides):
    now = int(time.time())
    payload = dict(iss=ISSUER, aud=[AUD], sub=sub, email=email, type='app',
                   iat=now-1, nbf=now-1, exp=now+3600)
    payload.update(overrides)
    return jwt.encode(payload, signing[0], algorithm='RS256', headers={'kid': 'test'})


def test_verified_claims_and_cached_rotating_keys(policy, signing):
    calls = []
    def keys(issuer):
        calls.append(issuer)
        return signing[1]
    verifier = AccessVerifier(policy, fetch_keys=keys)
    identity, settings = verifier.verify(token(signing))
    assert identity.subject == 'alice' and identity.email == 'alice@example.com'
    for _ in range(10): verifier.verify(token(signing))
    assert calls == [ISSUER]
    assert settings.is_admin('x', 'SECOND@example.com')
    assert settings.is_admin('admin-sub-3', 'third@example.com')
    assert not settings.is_admin('alice', 'alice@example.com')


@pytest.mark.parametrize('overrides', [
    {'iss': 'https://evil.cloudflareaccess.com'}, {'aud': ['other-app']},
    {'exp': 1}, {'type': 'org'}, {'sub': ''}, {'email': ''}, {'common_name': 'service'},
    {'nbf': 9999999999}, {'iat': 9999999999}, {'email': None},
])
def test_invalid_identity_rejected(policy, signing, overrides):
    v = AccessVerifier(policy, fetch_keys=lambda _: signing[1])
    with pytest.raises(AccessDenied): v.verify(token(signing, **overrides))


def test_missing_forged_and_bad_config_fail_closed(policy, signing):
    v = AccessVerifier(policy, fetch_keys=lambda _: signing[1])
    with pytest.raises(AccessDenied): v.verify('')
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(AccessDenied): v.verify(token((other, signing[1])))
    good = token(signing)
    v.verify(good)
    policy.write_text('{malformed')
    with pytest.raises(AccessUnavailable): v.verify(good)


@pytest.fixture
def access_app(tmp_path, monkeypatch, policy, signing):
    from nano_banana.web import context
    from nano_banana.core.config import AIConfigManager
    original = dict(context._legacy)
    owner = AIConfigManager(config_path=tmp_path / 'owner.yaml')
    owner.save_config({'api_key': 'SERVER-SECRET', 'model': 'server-model'})
    monkeypatch.setitem(context._legacy, 'config_manager', owner)
    monkeypatch.setenv('NANO_MULTIUSER', '1')
    monkeypatch.setenv('NANO_ACCESS_REQUIRED', '1')
    monkeypatch.setenv('NANO_SESSION_ROOT', str(tmp_path / 'sessions'))
    monkeypatch.setenv('NANO_PROFILES_DIR', str(tmp_path / 'profiles'))
    monkeypatch.setenv('NANO_ACCESS_CONFIG_FILE', str(policy))
    monkeypatch.setattr(AccessVerifier, '_download_keys', staticmethod(lambda _: signing[1]))
    from nano_banana.web.app import create_app
    apps = []
    def new_app():
        app = create_app()
        app.config['TESTING'] = True
        apps.append(app)
        return app
    app = new_app()
    yield app, new_app
    for a in apps: a.extensions['nano_sessions'].close()
    context._legacy.update(original)


def open_tab(client, assertion):
    response = client.post('/api/session/open', headers={
        'X-Nano-Client': 'web', 'Cf-Access-Jwt-Assertion': assertion})
    assert response.status_code == 201, response.json
    return {'Cf-Access-Jwt-Assertion': assertion, 'X-Nano-Session': response.json['token']}, response.json


def test_two_users_persist_only_own_keys_across_logout_and_restart(access_app, signing):
    app, new_app = access_app
    c = app.test_client()
    a, ai = open_tab(c, token(signing))
    b, bi = open_tab(c, token(signing, 'bob', 'bob@example.com'))
    assert ai['profile_id'] != bi['profile_id']
    assert c.get('/api/config', headers=a).json['has_api_key'] is False
    assert c.post('/api/config', headers=a, json={'api_key': 'ALICE-SECRET', 'model': 'alice-model'}).status_code == 200
    assert c.post('/api/config', headers=b, json={'api_key': 'BOB-SECRET', 'model': 'bob-model'}).status_code == 200
    assert c.post('/api/config', headers=a, json={'api_key': ''}).status_code == 200
    result = c.get('/api/config', headers=a)
    assert result.json['has_api_key'] and 'ALICE-SECRET' not in result.text and 'SERVER-SECRET' not in result.text
    assert c.post('/api/presets', headers=a, json={'name': 'saved', 'data': {'note': 'alice'}}).status_code == 200
    assert c.get('/api/presets/saved', headers=b).status_code == 404
    assert c.delete('/api/session/current', headers=a).status_code == 200
    c2 = new_app().test_client()
    a2, info = open_tab(c2, token(signing))
    assert info['profile_id'] == ai['profile_id']
    assert c2.get('/api/config', headers=a2).json['has_api_key'] is True
    assert c2.get('/api/config', headers=a2).json['model'] == 'alice-model'
    assert c2.get('/api/presets/saved', headers=a2).json == {'note': 'alice'}
    assert c2.delete('/api/config/keys/api_key', headers=a2).status_code == 200
    assert c2.get('/api/config', headers=a2).json['has_api_key'] is False
    assert c.get('/api/config', headers=b).json['has_api_key'] is True


def test_two_admins_and_hot_revocation_without_web_escalation(access_app, signing, policy):
    app, _ = access_app
    c = app.test_client()
    one, data1 = open_tab(c, token(signing, 'admin1', 'owner@example.com'))
    two, data2 = open_tab(c, token(signing, 'admin2', 'second@example.com'))
    friend, _ = open_tab(c, token(signing))
    assert data1['role'] == data2['role'] == 'owner'
    assert c.get('/api/config', headers=one).json['model'] == 'server-model'
    assert c.get('/api/config', headers=two).json['has_api_key']
    assert not c.get('/api/config', headers=friend).json['has_api_key']
    assert c.post('/api/session/owner', headers=friend, json={'key': 'x'*48}).status_code == 403
    assert c.post('/api/config', headers=friend, json={'admin_emails': ['alice@example.com']}).status_code == 400
    cfg = json.loads(policy.read_text()); cfg['admin_emails'].remove('second@example.com')
    policy.write_text(json.dumps(cfg))
    assert c.get('/api/config', headers=two).status_code == 401
    assert c.get('/api/config', headers=one).status_code == 200
    demoted, data = open_tab(c, token(signing, 'admin2', 'second@example.com'))
    assert data['role'] == 'personal'
    assert not c.get('/api/config', headers=demoted).json['has_api_key']


def test_header_spoofing_cross_identity_and_app_token_expiry(access_app, signing):
    app, _ = access_app; c = app.test_client()
    assert c.get('/api/health').status_code == 200
    assert c.get('/api/config', headers={'Cf-Access-Authenticated-User-Email': 'owner@example.com'}).status_code == 403
    a, _ = open_tab(c, token(signing))
    switched = {**a, 'Cf-Access-Jwt-Assertion': token(signing, 'bob', 'bob@example.com')}
    assert c.get('/api/config', headers=switched).status_code == 401
    assert c.get('/api/config', headers=a).status_code == 200
    lease = app.extensions['nano_sessions'].leases.get(a['X-Nano-Session'])
    lease.state['access_deadline'] = 0
    assert c.post('/api/session/heartbeat', headers=a).status_code == 401


def test_same_email_does_not_silently_rebind(policy, tmp_path):
    store = ProfileStore(tmp_path / 'profiles')
    settings = AccessConfig.load(policy)
    first = Identity(ISSUER, 'old-sub', 'alice@example.com', int(time.time())+3600)
    pid, _ = store.resolve(first, settings)
    changed = Identity(ISSUER, 'new-sub', first.email, first.expires)
    with pytest.raises(ProfileConflict): store.resolve(changed, settings)
    cfg = json.loads(policy.read_text()); cfg['subject_aliases'] = {'new-sub': 'old-sub'}
    assert store.resolve(changed, AccessConfig.parse(cfg))[0] == pid


def test_same_profile_concurrent_writes_and_different_stores(tmp_path, policy):
    a = ProfileStore(tmp_path / 'profiles'); b = ProfileStore(tmp_path / 'profiles')
    identity = Identity(ISSUER, 'friend', 'friend@example.com', int(time.time())+3600)
    p1, one = a.resolve(identity, AccessConfig.load(policy))
    p2, two = b.resolve(identity, AccessConfig.load(policy))
    assert p1 == p2
    barrier = threading.Barrier(2)
    def write(bundle, provider):
        barrier.wait(timeout=3)
        for i in range(10):
            assert bundle.config_manager.save_image_generation_options(provider, 'test-model', {'n': i})
    with ThreadPoolExecutor(2) as pool:
        fs = [pool.submit(write, one, 'openai_images'), pool.submit(write, two, 'gemini')]
        for f in fs: f.result(timeout=10)
    opts = one.config_manager.load_config()['image_generation_options']
    assert opts['openai_images']['test-model']['n'] == 9
    assert opts['gemini']['test-model']['n'] == 9
