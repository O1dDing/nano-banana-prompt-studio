"""Web 页签身份与资源隔离。开启多用户后，任何 API 都不隐式使用服务器身份。"""
from __future__ import annotations

import hmac
import os
import shutil
import tempfile
import threading
import time
from collections import defaultdict, deque
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

from flask import current_app, g, has_request_context, jsonify, request

from nano_banana.codex_bridge.leases import Leases, ExpiredSession, ABSOLUTE_SECONDS
from nano_banana.core.config import AIConfigManager, flatten_legacy_or_nested
from nano_banana.core.presets import PresetManager
from nano_banana.core.yaml_handler import YamlHandler


class Scope:
    def __init__(self, lease, root):
        self.key, self.closed, self.lock = lease.key, lease.closed, threading.RLock()
        self.directory = Path(tempfile.mkdtemp(prefix='tab-', dir=root))
        self.directory.chmod(0o700)
        self.owner = False
        self.bridge_token = ''
        self.auth_anchor_set = False
        self.active = 0
        self.config_manager = AIConfigManager(config_path=self.directory / 'ai_config.yaml')
        defaults = deepcopy(AIConfigManager.DEFAULT_CONFIG)
        defaults.update(chat_engine='codex', image_provider='codex_images', codex_effort='auto')
        self.config_manager.save_config(defaults, merge_existing=False)
        self.preset_manager = PresetManager(self.directory / 'presets')
        self.yaml_handler = YamlHandler(config_path=self.directory / 'options.yaml')

    def clean(self):
        with self.lock:
            if self.closed.is_set() and not self.active:
                shutil.rmtree(self.directory, ignore_errors=True)


def enabled():
    return os.getenv('NANO_MULTIUSER', '0') == '1'


def current_scope():
    return getattr(g, 'nano_scope', None) if has_request_context() else None


def owner_key():
    scope = current_scope()
    return scope.key if scope else None


def codex_identity():
    scope = current_scope()
    if scope is None:
        return None
    return 'owner' if scope.owner else scope.bridge_token


class WebSessions:
    def __init__(self, root, *, clock=None, sweep_seconds=5):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.leases = Leases(maximum=64, dispose=self.dispose, sweep_seconds=sweep_seconds,
                             **({'clock': clock} if clock else {}))
        self.rates = defaultdict(deque)
        self.rate_lock = threading.Lock()

    def limit(self, category, client, count):
        now = time.monotonic()
        with self.rate_lock:
            for key in list(self.rates):
                if not self.rates[key] or now - self.rates[key][-1] >= 60:
                    del self.rates[key]
            # 不能无限累积伪造/不同来源的限流键。
            if len(self.rates) >= 2048 and (category, client) not in self.rates:
                raise OverflowError('请求过于频繁')
            bucket = self.rates[category, client]
            while bucket and now - bucket[0] >= 60:
                bucket.popleft()
            if len(bucket) >= count:
                raise OverflowError('请求过于频繁，请稍后重试')
            bucket.append(now)

    def create(self):
        token, lease = self.leases.create()
        try:
            with lease.lock:
                lease.state['scope'] = Scope(lease, self.root)
            return token, lease
        except Exception:
            self.leases.expire(token)
            raise

    def dispose(self, lease):
        scope = lease.state.get('scope')
        if not scope:
            return
        from nano_banana.web.image_tasks import image_task_manager
        image_task_manager.cancel_owner(scope.key)
        token, scope.bridge_token = scope.bridge_token, ''
        # Bridge 自己也有相同租约；退出请求仅加速回收，不作为唯一保障。
        if token:
            threading.Thread(target=_delete_bridge, args=(token,), daemon=True).start()
        scope.clean()

    def close(self):
        self.leases.close()


def _delete_bridge(token):
    from nano_banana.core.codex_client import CodexBridge
    bridge = None
    try:
        bridge = CodexBridge(identity=token)
        bridge.request('DELETE', '/v1/sessions/current', timeout=3)
    except Exception:
        pass
    finally:
        if bridge:
            bridge.close()


def _official_api_url(value):
    if not value:
        return True
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    host = (parsed.hostname or '').lower()
    hosts = {'api.openai.com', 'api.anthropic.com', 'api.x.ai',
             'generativelanguage.googleapis.com', 'dashscope.aliyuncs.com',
             'dashscope-intl.aliyuncs.com', 'dashscope-us.aliyuncs.com',
             'ark.cn-beijing.volces.com', 'ark.ap-southeast.bytepluses.com'}
    return (parsed.scheme == 'https' and not parsed.username and not parsed.password
            and parsed.port in (None, 443) and not parsed.fragment
            and (host in hosts or host.endswith('.maas.aliyuncs.com')))


def _response(data, status=200):
    response = jsonify(data)
    response.status_code = status
    response.headers['Cache-Control'] = 'no-store'
    return response


def install(app):
    @app.get('/api/health')
    def health():
        from nano_banana.web.image_tasks import image_task_manager
        return _response({'ok': True, 'multiuser': enabled(), 'workers': image_task_manager.max_workers})

    @app.get('/api/session/info')
    def session_info():
        return _response({'enabled': enabled(), 'heartbeat_seconds': 30, 'lease_seconds': 90,
                          'absolute_seconds': ABSOLUTE_SECONDS})

    if not enabled():
        return
    app.config['MAX_CONTENT_LENGTH'] = 48 * 1024 * 1024
    manager = WebSessions(os.getenv('NANO_SESSION_ROOT', '/run/nano-web-sessions'))
    app.extensions['nano_sessions'] = manager

    @app.errorhandler(ExpiredSession)
    def expired(exc):
        return _response({'error': str(exc), 'session_expired': True}, 401)

    @app.errorhandler(OverflowError)
    def throttled(exc):
        return _response({'error': str(exc)}, 429)

    @app.before_request
    def protect():
        if not request.path.startswith('/api/'):
            return
        origin = request.headers.get('Origin')
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in {'http', 'https'} or parsed.netloc != request.host:
                return _response({'error': '跨站请求被拒绝'}, 403)
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            return _response({'error': '跨站请求被拒绝'}, 403)
        if request.path in {'/api/health', '/api/session/info', '/api/session/open'}:
            return
        token = request.headers.get('X-Nano-Session', '')
        lease = manager.leases.get(token)
        scope = lease.state['scope']
        with scope.lock:
            if scope.closed.is_set():
                raise ExpiredSession('会话已失效')
            scope.active += 1
        g.nano_scope, g.nano_lease = scope, lease
        # 预设路径在旧桌面代码中允许 name 拼接；多用户 HTTP 输入必须额外收紧。
        if 'preset' in request.path:
            body = request.get_json(silent=True) or {}
            names = [v for k, v in (request.view_args or {}).items() if k in {'name', 'scope'}]
            names += [body.get(k) for k in ('name', 'old_name', 'new_name') if k in body]
            if any(not isinstance(v, str) or '/' in v or '\\' in v or '\x00' in v or v in {'.', '..'} for v in names):
                return _response({'error': '预设名称无效'}, 400)
        if not scope.owner and request.path == '/api/config' and request.method == 'POST':
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return _response({'error': '配置须为 JSON 对象'}, 400)
            updates = flatten_legacy_or_nested(data)
            if set(updates) - set(AIConfigManager.DEFAULT_CONFIG):
                return _response({'error': '配置包含不允许的字段'}, 400)
            try:
                valid = all(_official_api_url(v) for k, v in updates.items() if k.endswith('base_url'))
            except ValueError:
                valid = False
            if not valid:
                return _response({'error': '个人会话只允许官方 HTTPS API 地址；自定义中转仅限管理员'}, 400)
        # 每会话上传/提交速率上限，避免单个用户无限占用共享资源。
        if request.method == 'POST' and request.path in {'/api/generate', '/api/modify', '/api/generate-image'}:
            manager.limit('tasks', scope.key, 20)

    @app.teardown_request
    def release(_error):
        scope = getattr(g, 'nano_scope', None)
        if scope:
            with scope.lock:
                scope.active -= 1
            scope.clean()

    @app.after_request
    def no_cache(response):
        scope = getattr(g, 'nano_scope', None)
        lease = getattr(g, 'nano_lease', None)
        if (scope is not None and lease is not None and manager.leases.is_expired(lease)
                and request.path != '/api/session/current'):
            response = _response({'error': '会话已失效', 'session_expired': True}, 401)
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        # 不缓存入口和JS，避免升级后旧客户端绕过新会话机制或显示旧状态。
        if request.path == '/' or request.path.endswith(('.js', '.css')):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def summary(lease):
        scope = lease.state['scope']
        return {'role': 'owner' if scope.owner else 'personal',
                'expires_in': max(0, int(lease.deadline - manager.leases.clock())),
                'heartbeat_seconds': 30, 'lease_seconds': 90}

    @app.post('/api/session/open')
    def open_session():
        if request.headers.get('X-Nano-Client') != 'web':
            return _response({'error': '缺少同源客户端标记'}, 403)
        manager.limit('open', request.remote_addr or '', 10)
        token, lease = manager.create()
        return _response({'token': token, **summary(lease)}, 201)

    @app.post('/api/session/heartbeat')
    def heartbeat():
        lease = manager.leases.heartbeat(request.headers['X-Nano-Session'])
        scope = lease.state['scope']
        result = summary(lease)
        if scope.bridge_token:
            from nano_banana.core.codex_client import CodexBridge, BridgeError
            bridge = CodexBridge(identity=scope.bridge_token)
            try:
                data = bridge.request('POST', '/v1/sessions/heartbeat', timeout=10)
                result['codex'] = data
                if data.get('logged_in') and not scope.auth_anchor_set:
                    lease.deadline = manager.leases.clock() + min(ABSOLUTE_SECONDS, data['expires_in'])
                    scope.auth_anchor_set = True
            except BridgeError:
                # 不能假装续租成功或退回管理员账户。
                result['codex'] = {'logged_in': False, 'state': 'unavailable'}
            finally:
                bridge.close()
        return _response(result)

    @app.delete('/api/session/current')
    def logout():
        manager.leases.expire(request.headers['X-Nano-Session'])
        return _response({'success': True})

    @app.post('/api/session/owner')
    def owner_login():
        manager.limit('owner', request.remote_addr or '', 5)
        scope = current_scope()
        supplied = (request.get_json(silent=True) or {}).get('key', '')
        path = os.getenv('NANO_ADMIN_TOKEN_FILE', '')
        try:
            expected = Path(path).read_text().strip() if path else ''
        except OSError:
            expected = ''
        if (not isinstance(supplied, str) or len(supplied) > 256 or len(expected) < 32
                or not hmac.compare_digest(supplied.encode(), expected.encode())):
            return _response({'error': '管理员凭证无效'}, 403)
        if scope.bridge_token:
            return _response({'error': '请先退出个人会话再进入管理员模式'}, 409)
        with scope.lock:
            scope.owner = True
        return _response(summary(g.nano_lease))

    @app.post('/api/session/codex/login')
    def codex_login():
        from nano_banana.core.codex_client import CodexBridge, BridgeError
        scope = current_scope()
        if scope.owner:
            return _response({'error': '管理员模式使用服务器账户；个人授权请退出后进入个人模式'}, 409)
        manager.limit('login', scope.key, 4)
        # 同一页签重入只返回原登录，不启动多个 Device Auth。
        with scope.lock:
            bridge = CodexBridge(identity=scope.bridge_token)
            try:
                if not scope.bridge_token:
                    data = bridge.request('POST', '/v1/sessions', timeout=10)
                    scope.bridge_token = data['session_token']
                    bridge.close()
                    bridge = CodexBridge(identity=scope.bridge_token)
                data = bridge.request('POST', '/v1/sessions/login', timeout=10)
                return _response(data, 202)
            except BridgeError:
                return _response({'error': '设备授权服务不可用；请退出后重试'}, 503)
            finally:
                bridge.close()
