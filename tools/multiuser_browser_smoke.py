"""真实 Chromium，所有认证和模型接口都是内存 fixtures。"""
import json
import os
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from nano_banana.core.schema import get_schema
from nano_banana.core.images.codex_images import capabilities
from playwright.sync_api import sync_playwright


def main():
    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/': self.path = '/static/index.html'
            super().do_GET()
        def log_message(self, *_): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT / 'src/web')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    sessions, calls, errors = {}, [], []
    def route_api(route):
        path = route.request.url.split(origin, 1)[-1]
        token = route.request.headers.get('x-nano-session')
        method = route.request.method
        calls.append((path, token))
        status, data = 200, {}
        if path == '/api/session/info':
            data = {'enabled': True, 'heartbeat_seconds': 30, 'lease_seconds': 90, 'absolute_seconds': 86400}
        elif path == '/api/session/open':
            token = str(len(sessions) + 1).zfill(43)
            sessions[token] = {'state': 'new', 'config': {'chat_engine': 'codex', 'image_provider': 'codex_images'}}
            data, status = {'token': token, 'role': 'personal'}, 201
        elif token not in sessions or sessions[token]['state'] == 'expired':
            status, data = 401, {'session_expired': True, 'error': 'session expired'}
        elif path == '/api/session/heartbeat':
            data = {'role': 'personal', 'expires_in': 86000, 'codex': {'logged_in': sessions[token]['state'] == 'ready'}}
        elif path == '/api/session/codex/login':
            sessions[token]['state'] = 'pending'
            data, status = {'state': 'starting'}, 202
        elif path == '/api/session/current':
            sessions[token]['state'] = 'expired'
            data = {'success': True}
        elif path == '/api/codex/status':
            state = sessions[token]['state']
            data = {'state': state, 'logged_in': state == 'ready', 'image_available': state == 'ready',
                    'prompt_workers': 4, 'image_workers': 4, 'models': [],
                    'user_code': 'CODE-' + token[-4:] if state == 'pending' else '',
                    'verification_url': 'https://auth.openai.com/codex/device', 'expires_in': 86000}
        elif path == '/api/config':
            if method == 'POST':
                sessions[token]['config'].update(route.request.post_data_json)
            data = sessions[token]['config']
        elif path == '/api/schema': data = get_schema().to_public_dict()
        elif path == '/api/image-providers':
            data = {'codex_images': {'label': 'Codex Image', 'models': ['gpt-image-2'],
                    'configured_model': 'gpt-image-2', 'default_model': 'gpt-image-2',
                    'is_configured': sessions[token]['state'] == 'ready',
                    'capabilities': {'gpt-image-2': capabilities()}}}
        elif 'presets' in path: data = []
        elif path == '/api/line-art-prompt': data = {'prompt': ''}
        elif path.startswith('/api/options/'): data = []
        route.fulfill(status=status, content_type='application/json', body=json.dumps(data))
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=os.environ.get('CHROMIUM_PATH'))
            context = browser.new_context(viewport={'width': 1500, 'height': 1200})
            context.route(origin + '/api/**', route_api)
            def page():
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(origin)
                page.wait_for_selector('#nanoAccountBtn')
                return page
            a, b = page(), page()
            key = 'nano.private.tab.v1'
            ta = a.evaluate('(key) => sessionStorage.getItem(key)', key)
            tb = b.evaluate('(key) => sessionStorage.getItem(key)', key)
            assert ta and tb and ta != tb
            a.locator('#nanoAccountBtn').click()
            a.locator('#nanoDeviceStart').click()
            a.wait_for_function("document.getElementById('nanoDeviceCode').textContent.startsWith('CODE-')")
            code_a = a.locator('#nanoDeviceCode').inner_text()
            assert a.locator('#nanoDeviceLink').get_attribute('href') == 'https://auth.openai.com/codex/device'
            b.locator('#nanoAccountBtn').click(); b.locator('#nanoDeviceStart').click()
            b.wait_for_function("document.getElementById('nanoDeviceCode').textContent.startsWith('CODE-')")
            assert b.locator('#nanoDeviceCode').inner_text() != code_a
            sessions[ta]['state'] = 'ready'
            a.wait_for_function("document.getElementById('nanoSessionStatus').textContent === 'ChatGPT 已登录'")
            a.reload(); a.wait_for_selector('#nanoAccountBtn')
            assert a.evaluate('(key) => sessionStorage.getItem(key)', key) == ta
            # 模拟浏览器复制标签页带来的 sessionStorage 副本；必须建立新身份。
            clone = context.new_page()
            clone.add_init_script(f"sessionStorage.setItem({json.dumps(key)}, {json.dumps(ta)})")
            clone.goto(origin); clone.wait_for_selector('#nanoAccountBtn')
            assert clone.evaluate('(key) => sessionStorage.getItem(key)', key) not in {ta, tb}
            clone.close()
            sessions[ta]['state'] = 'expired'
            a.evaluate("fetch('/api/config').catch(() => {})")
            a.wait_for_function("sessionStorage.getItem('nano.private.tab.v1') === null")
            assert b.evaluate('(key) => sessionStorage.getItem(key)', key) == tb
            missing = [path for path, token in calls if not token and path not in {'/api/session/info', '/api/session/open'}]
            assert missing == [], missing
            assert not errors, errors
            browser.close()
            print('Multiuser browser PASS: own code, own token, refresh, duplicate tab, expiry')
    finally:
        server.shutdown(); server.server_close()


if __name__ == '__main__': main()
