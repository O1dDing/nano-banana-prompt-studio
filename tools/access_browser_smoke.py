"""实际 Chromium + Flask + 本地 RSA 测试 JWT，不调用外部账户/模型。"""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from playwright.sync_api import sync_playwright
    from werkzeug.serving import make_server
    with tempfile.TemporaryDirectory(prefix='nano-access-browser-') as temp:
        root = Path(temp)
        policy = root / 'access.json'
        policy.write_text(json.dumps({'issuer': 'https://browser-test.cloudflareaccess.com',
                                     'audiences': ['browser-app'], 'admin_emails': ['owner@example.com']}))
        os.environ.update(NANO_MULTIUSER='1', NANO_ACCESS_REQUIRED='1',
                          NANO_ACCESS_CONFIG_FILE=str(policy), NANO_PROFILES_DIR=str(root/'users'),
                          NANO_SESSION_ROOT=str(root/'sessions'))
        from nano_banana.web.access_identity import AccessVerifier
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        jwk.update(kid='browser', alg='RS256', use='sig')
        AccessVerifier._download_keys = staticmethod(lambda _: {'keys': [jwk]})
        from nano_banana.web.app import app
        server = make_server('127.0.0.1', 0, app, threaded=True)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        def token(name):
            now = int(time.time())
            return jwt.encode(dict(iss='https://browser-test.cloudflareaccess.com', aud=['browser-app'],
                                   sub=name, email=name+'@example.com', type='app', iat=now-1, nbf=now-1, exp=now+3600),
                              key, algorithm='RS256', headers={'kid': 'browser'})
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                contexts = []
                def tab(name):
                    context = browser.new_context(extra_http_headers={'Cf-Access-Jwt-Assertion': token(name)})
                    contexts.append(context)
                    page = context.new_page()
                    page.goto(f'http://127.0.0.1:{server.server_port}')
                    page.wait_for_selector('#nanoAccountBtn')
                    return page
                alice, bob, owner = tab('alice'), tab('bob'), tab('owner')
                def config(page):
                    return page.evaluate("async () => (await fetch('/api/config')).json()")
                assert not config(alice)['has_api_key']
                assert alice.evaluate("async () => (await fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({api_key:'browser-only-test-key',model:'alice-model'})})).status") == 200
                assert config(alice)['has_api_key'] and not config(bob)['has_api_key']
                alice.reload(); alice.wait_for_selector('#nanoAccountBtn')
                assert config(alice)['model'] == 'alice-model'
                alice.locator('#nanoAccountBtn').click()
                assert 'alice@example.com' in alice.locator('#nanoSiteIdentity').inner_text()
                assert alice.locator('#nanoSessionModal details').is_hidden()
                alice.locator('#nanoSessionLogout').click()
                alice.wait_for_function("document.getElementById('nanoSessionStatus').textContent.includes('持久配置')")
                assert config(alice)['has_api_key']
                assert owner.locator('#nanoAccountBtn').inner_text() == '管理员'
                # 同一页签改用另一个 Access 身份：旧 token 被拒；刷新后只能进入新用户档案。
                contexts[0].set_extra_http_headers({'Cf-Access-Jwt-Assertion': token('charlie')})
                assert alice.evaluate("async () => (await fetch('/api/config')).status") == 401
                alice.reload(); alice.wait_for_selector('#nanoAccountBtn')
                assert not config(alice)['has_api_key']
                browser.close()
        finally:
            server.shutdown(); worker.join(timeout=5)
            app.extensions['nano_sessions'].close()
    print('Access browser PASS: JWT identity / own profile / refresh / logout restore / multi-admin UI / identity switch')


if __name__ == '__main__':
    main()
