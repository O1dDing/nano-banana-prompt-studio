"""明文个人配置仓库；身份索引与配置分离。页签失效永不删除此目录。"""
from __future__ import annotations

import fcntl
import os
import re
import sqlite3
import threading
import time
import uuid
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from nano_banana.core.config import AIConfigManager
from nano_banana.core.presets import PresetManager
from nano_banana.core.yaml_handler import YamlHandler


class ProfileConflict(PermissionError):
    pass


class FileLock:
    """相同对象的线程锁 + 进程间 flock；完整包住配置管理器的读-改-写。"""
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.depth = 0
        self.fd = None

    def __enter__(self):
        self.lock.acquire()
        try:
            if not self.depth:
                self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
                os.fchmod(self.fd, 0o600)
                fcntl.flock(self.fd, fcntl.LOCK_EX)
            self.depth += 1
            return self
        except BaseException:
            if self.fd is not None and not self.depth:
                os.close(self.fd)
                self.fd = None
            self.lock.release()
            raise

    def __exit__(self, *_):
        try:
            self.depth -= 1
            if not self.depth:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                os.close(self.fd)
                self.fd = None
        finally:
            self.lock.release()


def private_tree(root):
    """目录不可被其他 OS 用户遍历；不追随符号链接。"""
    root = Path(root)
    for path in [root, *root.rglob('*')]:
        if path.is_symlink():
            raise ProfileConflict('用户目录包含符号链接，拒绝使用')
        path.chmod(0o700 if path.is_dir() else 0o600)


class LockedManager:
    def __init__(self, target, lock):
        self.target, self.lock = target, lock

    def __getattr__(self, name):
        value = getattr(self.target, name)
        if not callable(value):
            return value
        def invoke(*args, **kwargs):
            with self.lock:
                result = value(*args, **kwargs)
                return result
        return invoke


class ProfileStore:
    def __init__(self, root):
        self.root = Path(root)
        if self.root.is_symlink():
            raise ProfileConflict('用户根目录不能为符号链接')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.db_path = self.root / 'profiles.sqlite'
        if self.db_path.is_symlink():
            raise ProfileConflict('用户索引不能为符号链接')
        self.index_lock = FileLock(self.root / '.index.lock')
        self.bundle_lock = threading.RLock()
        self.bundles = {}
        with self.index_lock, self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS profiles (
                issuer TEXT NOT NULL, subject TEXT NOT NULL, email TEXT NOT NULL,
                profile_id TEXT NOT NULL UNIQUE, created REAL NOT NULL, last_seen REAL NOT NULL,
                PRIMARY KEY (issuer, subject), UNIQUE (issuer, email))''')
            self.db_path.chmod(0o600)

    def connect(self):
        # 不启用 WAL，回滚日志与 db 在 0700 根目录；短事务、超时和文件锁控制并发。
        from contextlib import contextmanager
        @contextmanager
        def opened():
            db = sqlite3.connect(self.db_path, timeout=10)
            try:
                with db:
                    yield db
            finally:
                db.close()
        return opened()

    def resolve(self, identity, settings):
        subject = settings.canonical_subject(identity.subject)
        now = time.time()
        with self.index_lock, self.connect() as db:
            row = db.execute('SELECT profile_id FROM profiles WHERE issuer=? AND subject=?',
                             (identity.issuer, subject)).fetchone()
            email_owner = db.execute('SELECT subject FROM profiles WHERE issuer=? AND email=?',
                                     (identity.issuer, identity.email)).fetchone()
            if email_owner and email_owner[0] != subject:
                # 不按相同邮箱自动夺取旧 Profile；团队删除重建时由管理员显式配置别名。
                raise ProfileConflict('相同邮箱存在旧 Access 身份；请管理员配置 subject_aliases 后恢复')
            if row:
                profile_id = row[0]
                db.execute('UPDATE profiles SET email=?, last_seen=? WHERE issuer=? AND subject=?',
                           (identity.email, now, identity.issuer, subject))
            else:
                if not settings.auto_create:
                    raise ProfileConflict('此身份尚无配置档案，自动创建已关闭')
                profile_id = uuid.uuid4().hex
                db.execute('INSERT INTO profiles VALUES (?,?,?,?,?,?)',
                           (identity.issuer, subject, identity.email, profile_id, now, now))
        return profile_id, self.bundle(profile_id)

    def bundle(self, profile_id):
        if not re.fullmatch(r'[0-9a-f]{32}', profile_id):
            raise ProfileConflict('Profile ID 无效')
        with self.bundle_lock:
            if profile_id in self.bundles:
                return self.bundles[profile_id]
            directory = self.root / profile_id
            if directory.is_symlink():
                raise ProfileConflict('Profile 目录不安全')
            directory.mkdir(mode=0o700, exist_ok=True)
            private_tree(directory)
            lock = FileLock(directory / '.lock')
            with lock:
                config = AIConfigManager(config_path=directory / 'ai_config.yaml')
                if not config.config_path.exists():
                    defaults = deepcopy(AIConfigManager.DEFAULT_CONFIG)
                    defaults.update(chat_engine='api', image_provider='openai_images')
                    if not config.save_config(defaults, merge_existing=False):
                        raise RuntimeError('创建个人 API 配置失败')
                presets = PresetManager(directory / 'presets')
                options = YamlHandler(config_path=directory / 'options.yaml')
                bundle = SimpleNamespace(config_manager=LockedManager(config, lock),
                                         preset_manager=LockedManager(presets, lock),
                                         yaml_handler=LockedManager(options, lock))
                private_tree(directory)
                self.bundles[profile_id] = bundle
                return bundle

    def protect_legacy(self, managers):
        lock = FileLock(self.root / '.server-profile.lock')
        for name, manager in list(managers.items()):
            if not isinstance(manager, LockedManager):
                managers[name] = LockedManager(manager, lock)
