"""Web 图片只来自上传；桌面共用构造器不得读取访客提供的服务器路径。"""
import base64
import threading
from io import BytesIO

import pytest
from PIL import Image

from nano_banana.web.blueprints import chat


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('NANO_MULTIUSER', '1')
    monkeypatch.setenv('NANO_SESSION_ROOT', str(tmp_path / 'sessions'))
    from nano_banana.web.app import create_app
    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    opened = client.post('/api/session/open', headers={'X-Nano-Client': 'web'})
    assert opened.status_code == 201
    headers = {'X-Nano-Session': opened.json['token']}
    yield client, headers
    app.extensions['nano_sessions'].close()


@pytest.mark.parametrize('endpoint', ['/api/generate', '/api/modify'])
@pytest.mark.parametrize('images', [
    ['/app/src/config/ai_config.yaml'],
    ['file:///etc/passwd'],
    ['http://127.0.0.1:8787/health'],
    ['https://example.invalid/image.png'],
    'data:image/png;base64,anything',
    [{'path': '/etc/passwd'}],
    ['data:image/png;base64,%%%'],
])
def test_reject_before_message_construction(client, monkeypatch, endpoint, images):
    http, headers = client
    def forbidden(*_args, **_kwargs):
        pytest.fail('unsafe input reached shared message constructor')
    monkeypatch.setattr(chat, 'build_generate_messages', forbidden)
    monkeypatch.setattr(chat, 'build_modify_messages', forbidden)
    result = http.post(endpoint, headers=headers, json={
        'prompt': 'test', 'current_data': '{}', 'modify_request': 'test', 'images': images,
    })
    assert result.status_code == 400


@pytest.mark.parametrize('endpoint', ['/api/generate', '/api/modify'])
@pytest.mark.parametrize('fmt,mime', [('PNG', 'image/png'), ('JPEG', 'image/jpeg'), ('WEBP', 'image/webp')])
def test_reference_bytes_reach_generate_and_modify(client, monkeypatch, endpoint, fmt, mime):
    http, headers = client
    data = BytesIO()
    Image.new('RGB', (8, 8), 'red').save(data, format=fmt)
    raw = data.getvalue()
    supplied = 'data:application/octet-stream;base64,' + base64.b64encode(raw).decode()
    captured = {}
    def fake_sse(messages, current_data=None):
        captured['messages'] = messages
        return {'ok': True}
    monkeypatch.setattr(chat, '_sse_from_messages', fake_sse)
    response = http.post(endpoint, headers=headers, json={
        'prompt': 'test', 'current_data': '{}', 'modify_request': 'test', 'images': [supplied],
    })
    assert response.status_code == 200
    parts = captured['messages'][-1]['content']
    reference = next(part['image_url']['url'] for part in parts if part['type'] == 'image_url')
    assert reference.startswith('data:' + mime + ';base64,')
    assert base64.b64decode(reference.split(',', 1)[1]) == raw


def test_closed_api_scope_does_not_start_upstream(monkeypatch):
    stop = threading.Event()
    stop.set()
    monkeypatch.setattr(chat, 'create_chat_client', lambda **_: pytest.fail('expired session called API'))
    events = list(chat._iter_stage1_sse([], {'_cancelled': stop}))
    assert len(events) == 1 and 'error' in events[0]
