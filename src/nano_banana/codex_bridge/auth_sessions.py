"""官方设备授权的会话适配器；OpenAI 凭据不回传浏览器或写入持久数据卷。"""
from __future__ import annotations

import shutil
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from nano_banana.codex_bridge.leases import Leases, ExpiredSession, ABSOLUTE_SECONDS, LEASE_SECONDS
from nano_banana.codex_bridge.runtime import (
    Rpc, Cancelled, CodexError, runtime_identity, subscription_account, probe_status,
)

LOGIN_SECONDS = 600


class AuthSessions:
    def __init__(self, root, *, maximum=32, clock=None, rpc_factory=Rpc, on_expire=None,
                 sweep_seconds=5):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.rpc_factory = rpc_factory
        self.on_expire = on_expire or (lambda key: None)
        self.leases = Leases(maximum=maximum, dispose=self._dispose,
                             sweep_seconds=sweep_seconds, **({'clock': clock} if clock else {}))

    def create(self):
        token, lease = self.leases.create()
        try:
            with lease.lock:
                home = Path(tempfile.mkdtemp(prefix='identity-', dir=self.root))
                home.chmod(0o700)
                lease.state.update(home=home, status='new', users=0, rpcs=set(),
                                   error='', code='', url='', login_id='', cache={},
                                   cache_at=0, probe_lock=threading.Lock(), authenticated_at=None)
            return {'session_token': token, **self.snapshot(lease)}
        except Exception:
            self.leases.expire(token)
            raise

    def require(self, token, ready=False):
        lease = self.leases.get(token)
        if ready and lease.state.get('status') != 'ready':
            raise ExpiredSession('请先完成本页的 Codex 授权')
        if (lease.state.get('authenticated_at') is None
                and self.leases.clock() - lease.created >= LOGIN_SECONDS):
            self.leases.expire(token)
            raise ExpiredSession('授权已超时，请重新登录')
        return lease

    def snapshot(self, lease):
        with lease.lock:
            state = lease.state
            return {'state': state.get('status', 'new'), 'logged_in': state.get('status') == 'ready',
                    'user_code': state.get('code', ''), 'verification_url': state.get('url', ''),
                    'error': state.get('error', ''), 'heartbeat_seconds': 30, 'lease_seconds': LEASE_SECONDS,
                    'expires_in': max(0, int(lease.deadline - self.leases.clock()))}

    def heartbeat(self, token):
        self.require(token)
        return self.snapshot(self.leases.heartbeat(token))

    def status(self, token):
        lease = self.require(token)
        result = self.snapshot(lease)
        if not result['logged_in']:
            return {**result, 'available': True, 'models': [], 'image_available': False}
        with lease.state['probe_lock']:
            state = lease.state
            if not state['cache'] or self.leases.clock() - state['cache_at'] > 15:
                with self.scope(lease):
                    state['cache'] = probe_status()
                    state['cache_at'] = self.leases.clock()
            if lease.closed.is_set():
                raise ExpiredSession('会话已结束')
            # 真正 account/read 的结果优先，不能用缓存的 ready 覆盖授权已失效。
            return {**result, **state['cache']}

    def start_login(self, token):
        lease = self.require(token)
        with lease.lock:
            if lease.state['status'] in {'starting', 'pending', 'ready'}:
                return self.snapshot(lease)
            if lease.state['status'] != 'new':
                raise ExpiredSession('授权已结束，请重新登录')
            lease.state['status'] = 'starting'
            worker = threading.Thread(target=self._login, args=(lease,), daemon=True)
            worker.start()
        return self.snapshot(lease)

    def _login(self, lease):
        rpc = None
        try:
            with self.scope(lease):
                work = lease.state['home'] / 'login-work'
                work.mkdir(mode=0o700)
                rpc = self.rpc_factory(work)
                rpc.initialize()
                info = rpc.call('account/login/start', {'type': 'chatgptDeviceCode'},
                                timeout=30, cancelled=lease.closed)
                url = info.get('verificationUrl', '')
                parsed = urlsplit(url)
                code = info.get('userCode')
                if (info.get('type') != 'chatgptDeviceCode' or parsed.scheme != 'https'
                        or parsed.hostname != 'auth.openai.com' or parsed.username or parsed.password
                        or parsed.port not in (None, 443) or parsed.path.rstrip('/') != '/codex/device'
                        or not isinstance(code, str) or not 1 <= len(code) <= 128
                        or not info.get('loginId')):
                    raise CodexError('无有效官方设备授权信息')
                with lease.lock:
                    if lease.closed.is_set():
                        raise Cancelled()
                    lease.state.update(code=code, url=url, login_id=info['loginId'], status='pending')
                while not lease.closed.is_set() and self.leases.clock() - lease.created < LOGIN_SECONDS:
                    msg = rpc.pending.popleft() if rpc.pending else rpc._get()
                    if not msg:
                        continue
                    params = msg.get('params') or {}
                    if (msg.get('method') != 'account/login/completed'
                            or params.get('loginId') != lease.state['login_id']):
                        continue
                    if params.get('success') is not True:
                        raise CodexError('设备授权未完成')
                    subscription_account(rpc)
                    with lease.lock:
                        if lease.closed.is_set():
                            raise Cancelled()
                        lease.state.update(status='ready', authenticated_at=self.leases.clock(),
                                           code='', url='', login_id='')
                        lease.deadline = self.leases.clock() + ABSOLUTE_SECONDS
                    return
                raise CodexError('设备授权超时')
        except Exception:
            with lease.lock:
                if not lease.closed.is_set():
                    lease.state.update(status='failed', error='设备授权失败或超时，请退出后重新授权',
                                       code='', url='')
        finally:
            if rpc:
                try:
                    if lease.state.get('status') != 'ready' and lease.state.get('login_id'):
                        rpc.call('account/login/cancel', {'loginId': lease.state['login_id']}, timeout=2)
                except Exception:
                    pass
                rpc.close()
                with lease.lock:
                    lease.state.get('rpcs', set()).discard(rpc)
            self._clean_if_idle(lease)

    @contextmanager
    def scope(self, lease):
        with lease.lock:
            if self.leases.is_expired(lease):
                raise ExpiredSession('Codex 身份已失效')
            lease.state['users'] += 1
        def register(rpc):
            with lease.lock:
                if lease.closed.is_set():
                    rpc.close()
                    raise Cancelled('Codex 身份已失效')
                lease.state['rpcs'].add(rpc)
        try:
            with runtime_identity(lease.state['home'], register):
                yield
        finally:
            with lease.lock:
                lease.state['users'] -= 1
                lease.state['rpcs'] = {rpc for rpc in lease.state['rpcs'] if not rpc.closed.is_set()}
            self._clean_if_idle(lease)

    def _dispose(self, lease):
        with lease.lock:
            lease.state.update(status='expired', code='', url='', login_id='', cache={})
            rpcs = tuple(lease.state.get('rpcs', ()))
        self.on_expire(lease.key)
        for rpc in rpcs:
            try:
                rpc.close()
            except Exception:
                pass
        with lease.lock:
            lease.state['rpcs'] = {rpc for rpc in rpcs if not rpc.closed.is_set()}
        self._clean_if_idle(lease)

    def _clean_if_idle(self, lease):
        with lease.lock:
            if lease.closed.is_set() and not lease.state.get('users') and not lease.state.get('rpcs'):
                home = lease.state.get('home')
                if home is not None:
                    shutil.rmtree(home, ignore_errors=True)

    def expire(self, token):
        self.leases.expire(token)
        return {'logged_in': False, 'state': 'expired'}

    def close(self):
        self.leases.close()
