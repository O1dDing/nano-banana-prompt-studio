"""多用户 Bridge HTTP 接口。内部访问密钥与用户身份是两个独立层次。"""
from __future__ import annotations

import hmac
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from nano_banana.codex_bridge.auth_sessions import AuthSessions
from nano_banana.codex_bridge.leases import ExpiredSession
from nano_banana.codex_bridge.runtime import run_job
from nano_banana.codex_bridge.server import BridgeServer, Handler, JobManager, MAX_BODY


class MultiuserBridge(BridgeServer):
    def __init__(self, address, token, manager=None):
        self.sessions = AuthSessions(
            Path(os.getenv('CODEX_WORK_DIR', '/run/nano-codex')) / 'sessions',
            maximum=32, on_expire=lambda key: self.manager.cancel_owner(key))
        manager = manager or JobManager(runner=self.run_owned)
        super().__init__(address, token, manager)
        self.RequestHandlerClass = MultiuserHandler

    def run_owned(self, payload, cancelled, progress, *, owner=None):
        if owner is None:
            return run_job(payload, cancelled, progress)
        with self.sessions.leases.lock:
            lease = self.sessions.leases.items.get(owner)
        if lease is None or lease.state.get('status') != 'ready':
            raise ExpiredSession('会话已失效，未提交模型请求')
        with self.sessions.scope(lease):
            return run_job(payload, cancelled, progress)

    def server_close(self):
        self.sessions.close()
        super().server_close()


class MultiuserHandler(Handler):
    def body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= MAX_BODY:
            raise ValueError('请求为空或过大')
        self.connection.settimeout(30)
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError('请求体不完整')
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError('请求体须为 JSON 对象')
        return data

    def _handle_multi(self):
        supplied = self.headers.get('Authorization', '')
        if not hmac.compare_digest(supplied.encode(), ('Bearer ' + self.server.token).encode()):
            return self._reply(401, {'error': 'Unauthorized'})
        path = urlsplit(self.path).path
        token = self.headers.get('X-Codex-Session', '')
        is_owner = self.headers.get('X-Codex-Owner') == '1'
        if token and is_owner:
            return self._reply(400, {'error': '不能同时选择两种身份'})
        try:
            if self.command == 'GET' and path == '/health':
                return self._reply(200, {'ok': True, 'multiuser': True,
                                        'workers': self.server.manager.workers})
            if self.command == 'POST' and path == '/v1/sessions':
                return self._reply(201, self.server.sessions.create())
            if path.startswith('/v1/sessions/'):
                if not token:
                    raise ExpiredSession('缺少用户会话')
                if path == '/v1/sessions/heartbeat' and self.command == 'POST':
                    return self._reply(200, self.server.sessions.heartbeat(token))
                if path == '/v1/sessions/login' and self.command == 'POST':
                    return self._reply(202, self.server.sessions.start_login(token))
                if path == '/v1/sessions/current' and self.command == 'DELETE':
                    return self._reply(200, self.server.sessions.expire(token))
            if path == '/v1/status' and self.command == 'GET':
                if token:
                    data = self.server.sessions.status(token)
                elif is_owner:
                    data = self.server.status()
                else:
                    data = {'available': True, 'logged_in': False, 'models': [],
                            'image_available': False, 'state': 'new'}
                return self._reply(200, {**data, 'multiuser': True,
                    'prompt_workers': self.server.manager.prompt_workers,
                    'image_workers': self.server.manager.image_workers,
                    'workers': self.server.manager.workers})

            # 空身份不会降级到服务器共享账户。
            if token:
                owner = self.server.sessions.require(token, ready=True).key
            elif is_owner:
                owner = None
            else:
                raise ExpiredSession('请先登录自己的 Codex 账户')
            if path == '/v1/jobs' and self.command == 'POST':
                return self._reply(202, self.server.manager.submit(self.body(), owner=owner))
            match = re.fullmatch(r'/v1/jobs/([0-9a-f]{32})(/cancel)?', path)
            if match:
                key, suffix = match.groups()
                if self.command == 'GET' and suffix is None:
                    data = self.server.manager.get(key, owner=owner)
                elif self.command == 'POST' and suffix == '/cancel':
                    data = self.server.manager.cancel(key, owner=owner)
                elif self.command == 'DELETE' and suffix is None:
                    data = self.server.manager.cancel(key, forget=True, owner=owner)
                else:
                    return self._reply(405, {'error': 'Method not allowed'})
                return self._reply(200, data) if data else self._reply(404, {'error': '任务不存在或已回收'})
            return self._reply(404, {'error': 'Not found'})
        except ExpiredSession as exc:
            return self._reply(401, {'error': str(exc), 'session_expired': True})
        except OverflowError as exc:
            return self._reply(429, {'error': str(exc)})
        except (ValueError, TypeError, KeyError):
            return self._reply(400, {'error': '请求参数无效'})
        except Exception:
            return self._reply(500, {'error': 'Bridge 内部错误；未回退到 API'})

    do_GET = _handle_multi
    do_POST = _handle_multi
    do_DELETE = _handle_multi
