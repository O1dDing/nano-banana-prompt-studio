"""短租约身份表。任务进度和状态查询不得续租，只有浏览器心跳可以。"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

HEARTBEAT_SECONDS = 30
LEASE_SECONDS = 90
ABSOLUTE_SECONDS = 86400


class ExpiredSession(PermissionError):
    pass


def digest(token: str) -> str:
    if not isinstance(token, str) or not 32 <= len(token) <= 128:
        raise ExpiredSession('会话无效或已过期')
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


@dataclass
class Lease:
    key: str
    created: float
    seen: float
    deadline: float
    state: dict[str, Any] = field(default_factory=dict)
    closed: threading.Event = field(default_factory=threading.Event)
    lock: threading.RLock = field(default_factory=threading.RLock)


class Leases:
    def __init__(self, *, maximum=32, clock=time.monotonic, dispose=None, sweep_seconds=5):
        self.maximum, self.clock = maximum, clock
        self.dispose = dispose or (lambda lease: None)
        self.lock = threading.RLock()
        self.items: dict[str, Lease] = {}
        self.stopped = threading.Event()
        self.thread = None
        if sweep_seconds:
            self.thread = threading.Thread(target=self._loop, args=(sweep_seconds,), daemon=True)
            self.thread.start()

    def create(self):
        self.sweep()
        with self.lock:
            if len(self.items) >= self.maximum:
                raise OverflowError('在线会话已达上限，请稍后重试')
            token = secrets.token_urlsafe(32)
            key, now = digest(token), self.clock()
            lease = Lease(key, now, now, now + ABSOLUTE_SECONDS)
            self.items[key] = lease
            return token, lease

    def is_expired(self, lease):
        now = self.clock()
        return (lease.closed.is_set() or now >= lease.deadline
                or now - lease.seen >= LEASE_SECONDS)

    def get(self, token):
        key = digest(token)
        with self.lock:
            lease = self.items.get(key)
        if lease is None:
            raise ExpiredSession('会话已回收，请重新认证')
        if self.is_expired(lease):
            self.expire_key(key)
            raise ExpiredSession('会话已超时，请重新认证')
        return lease

    def heartbeat(self, token):
        lease = self.get(token)
        with lease.lock:
            if self.is_expired(lease):
                raise ExpiredSession('会话已超时')
            lease.seen = self.clock()
        return lease

    def expire_key(self, key):
        with self.lock:
            lease = self.items.pop(key, None)
        if lease is not None:
            lease.closed.set()
            self.dispose(lease)

    def expire(self, token):
        self.expire_key(digest(token))

    def sweep(self):
        with self.lock:
            keys = [key for key, lease in self.items.items() if self.is_expired(lease)]
        for key in keys:
            self.expire_key(key)

    def _loop(self, interval):
        while not self.stopped.wait(interval):
            self.sweep()

    def close(self):
        self.stopped.set()
        with self.lock:
            keys = list(self.items)
        for key in keys:
            self.expire_key(key)
        if self.thread:
            self.thread.join(timeout=2)
