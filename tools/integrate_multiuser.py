"""一次性、带匹配检查的分支集成；验证通过后提交生成源码并移除此工具。"""
from pathlib import Path


def replace(path, old, new, count=1):
    p = Path(path)
    s = p.read_text()
    if old not in s:
        if new in s:
            return
        raise RuntimeError(f'{path}: target not found: {old[:120]!r}')
    if count is not None and s.count(old) != count:
        raise RuntimeError(f'{path}: expected {count}, found {s.count(old)}: {old[:100]!r}')
    p.write_text(s.replace(old, new) if count is None else s.replace(old, new, count))


r = 'src/nano_banana/codex_bridge/runtime.py'
replace(r, 'from collections import deque\n', 'from collections import deque\nfrom contextlib import contextmanager\nfrom contextvars import ContextVar\n')
replace(r, 'MAX_EVENT_BYTES = ', '''_IDENTITY = ContextVar('nano_codex_identity', default=None)


@contextmanager
def runtime_identity(home, register=None):
    marker = _IDENTITY.set((Path(home), register))
    try:
        yield
    finally:
        _IDENTITY.reset(marker)


def work_root():
    identity = _IDENTITY.get()
    return identity[0] / 'work' if identity else Path(os.environ.get('CODEX_WORK_DIR', '/run/nano-codex'))


MAX_EVENT_BYTES = ''')
replace(r, '    result["RUST_LOG"] = "error"\n', '''    identity = _IDENTITY.get()
    if identity:
        result['CODEX_HOME'] = str(identity[0])
        result['HOME'] = str(identity[0])
        result['XDG_CACHE_HOME'] = str(identity[0] / 'cache')
    result["RUST_LOG"] = "error"
''')
replace(r, '        self.work = work\n', '        self.work = work\n        self._close_lock = threading.RLock()\n')
replace(r, '        self.turn_id: str | None = None\n', '''        self.turn_id: str | None = None
        identity = _IDENTITY.get()
        if identity and identity[1]:
            identity[1](self)
''')
replace(r, '    def close(self):\n        self.closed.set()\n', '''    def close(self):
        with self._close_lock:
            if self.closed.is_set():
                return
            self._close_impl()

    def _close_impl(self):
        self.closed.set()
''')
replace(r, '    root = Path(os.environ.get("CODEX_WORK_DIR", "/run/nano-codex"))\n', '    root = work_root()\n', count=2)

s = 'src/nano_banana/codex_bridge/server.py'
replace(s, '    def submit(self, payload):\n', '    def submit(self, payload, owner=None):\n')
replace(s, '            key = uuid.uuid4().hex\n', '''            if owner is not None and sum(j.get('owner') == owner and j['status'] not in FINAL for j in self.jobs.values()) >= 8:
                raise OverflowError('当前用户已有8个未完成任务，请等待或取消后再试')
            key = uuid.uuid4().hex
''')
replace(s, '                   "updated": now, "leased": now, "future": None}\n', '                   "updated": now, "leased": now, "future": None, "owner": owner}\n')
replace(s, '            result = self.runner(payload, job["cancel"], progress)\n', '''            if job.get('owner') is None:
                result = self.runner(payload, job["cancel"], progress)
            else:
                result = self.runner(payload, job["cancel"], progress, owner=job['owner'])
''')
replace(s, '    def get(self, key):\n', '    def get(self, key, owner=None):\n')
replace(s, '            if job:\n                job["leased"]', '            if job and job.get("owner") == owner:\n                job["leased"]')
replace(s, '    def cancel(self, key, forget=False):\n', '    def cancel(self, key, forget=False, owner=None):\n')
replace(s, '            if not job:\n                return None\n', '            if not job or job.get("owner") != owner:\n                return None\n')
replace(s, '    def close(self):\n        self.closed.set()\n', '''    def cancel_owner(self, owner):
        with self.lock:
            for key, job in list(self.jobs.items()):
                if job.get('owner') == owner:
                    self.cancel(key, forget=True, owner=owner)
                    job['result'] = None
                    job['progress'].pop('preview', None)

    def close(self):
        self.closed.set()
''')
replace(s, '    server = BridgeServer(("0.0.0.0", int(os.getenv("CODEX_BRIDGE_PORT", "8787"))), token)\n', '''    server_type = BridgeServer
    if os.getenv('CODEX_MULTIUSER', '0') == '1':
        from nano_banana.codex_bridge.multiuser import MultiuserBridge
        server_type = MultiuserBridge
    server = server_type(("0.0.0.0", int(os.getenv("CODEX_BRIDGE_PORT", "8787"))), token)
''')

c = 'src/nano_banana/core/config.py'
replace(c, 'class AIConfigManager:', 'from pathlib import Path\n\n\nclass AIConfigManager:')
replace(c, '    def __init__(self):\n        self._config_lock = threading.RLock()\n        self.config_path = get_resource_path("config/ai_config.yaml")\n', '    def __init__(self, config_path=None):\n        self._config_lock = threading.RLock()\n        self.config_path = Path(config_path) if config_path is not None else get_resource_path("config/ai_config.yaml")\n')
y = 'src/nano_banana/core/yaml_handler.py'
replace(y, '    def __init__(self):\n        self.config_path = get_config_path()\n', '    def __init__(self, config_path=None):\n        self.config_path = Path(config_path) if config_path is not None else get_config_path()\n')
Path('src/nano_banana/web/context.py').write_text('''"""Web 管理器：旧单用户/管理员使用原数据；个人页签使用独立临时数据。"""
from werkzeug.local import LocalProxy
from nano_banana.core.config import AIConfigManager
from nano_banana.core.presets import PresetManager
from nano_banana.core.schema import get_schema
from nano_banana.core.yaml_handler import YamlHandler

_legacy = {'yaml_handler': YamlHandler(), 'preset_manager': PresetManager(),
           'config_manager': AIConfigManager()}


def _manager(name):
    from nano_banana.web.user_sessions import current_scope
    scope = current_scope()
    return getattr(scope, name) if scope is not None and not scope.owner else _legacy[name]


yaml_handler = LocalProxy(lambda: _manager('yaml_handler'))
preset_manager = LocalProxy(lambda: _manager('preset_manager'))
config_manager = LocalProxy(lambda: _manager('config_manager'))
CATEGORY_PRESET_SCOPES = set(get_schema().category_ids)
''')
a = 'src/nano_banana/web/app.py'
replace(a, '    CORS(app)\n', '''    from nano_banana.web.user_sessions import install, enabled
    if not enabled():
        CORS(app)
    install(app)
''')
# Read-only health contains no configuration or account information.
u = 'src/nano_banana/web/user_sessions.py'
replace(u, '    @app.get(\'/api/session/info\')\n', '''    @app.get('/api/health')
    def health():
        from nano_banana.web.image_tasks import image_task_manager
        return _response({'ok': True, 'multiuser': enabled(), 'workers': image_task_manager.max_workers})

    @app.get('/api/session/info')
''')
replace(u, "if request.path in {'/api/session/info', '/api/session/open'}:", "if request.path in {'/api/health', '/api/session/info', '/api/session/open'}:")

b = 'src/nano_banana/core/codex_client.py'
replace(b, '    def __init__(self):\n', '''    def __init__(self, identity=None):
        if identity is None:
            try:
                from nano_banana.web.user_sessions import codex_identity
                identity = codex_identity()
            except ImportError:
                pass
''')
replace(b, '        self.client = httpx.Client(timeout=httpx.Timeout(90, connect=5), trust_env=False,\n                                   headers={"Authorization": "Bearer " + self.token})\n', '''        headers = {"Authorization": "Bearer " + self.token}
        if identity == 'owner':
            headers['X-Codex-Owner'] = '1'
        elif identity:
            headers['X-Codex-Session'] = identity
        self.client = httpx.Client(timeout=httpx.Timeout(90, connect=5), trust_env=False, headers=headers)
''')
replace(b, '        bridge = CodexBridge()\n        payload = ', '        bridge = CodexBridge(identity=chat.get("_codex_identity"))\n        payload = ')
replace(b, '        events = bridge.iter_job(payload)\n', '        events = bridge.iter_job(payload, chat.get("_cancelled"))\n')
ch = 'src/nano_banana/web/blueprints/chat.py'
replace(ch, '    chat = config_manager.get_chat_config()\n', '''    chat = config_manager.get_chat_config()
    from nano_banana.web.user_sessions import codex_identity, current_scope
    chat['_codex_identity'] = codex_identity()
    scope = current_scope()
    chat['_cancelled'] = scope.closed if scope else None
''')

im = 'src/nano_banana/core/images/codex_images.py'
replace(im, 'def __init__(self, *, model=CODEX_IMAGE_MODEL, codex_model="", codex_effort="auto"):', 'def __init__(self, *, model=CODEX_IMAGE_MODEL, codex_model="", codex_effort="auto", codex_identity=None):')
replace(im, '        self.options = {}\n', '        self.codex_identity = codex_identity\n        self.options = {}\n')
replace(im, '        bridge = CodexBridge()\n', '        bridge = CodexBridge(identity=self.codex_identity)\n')
images = 'src/nano_banana/web/blueprints/images.py'
replace(images, 'from nano_banana.web.image_tasks import image_task_manager\n', 'from nano_banana.web.image_tasks import image_task_manager\nfrom nano_banana.web.user_sessions import current_scope, owner_key, codex_identity\n')
replace(images, '                                        codex_effort=credentials.get("codex_effort") or "auto")\n', '                                        codex_effort=credentials.get("codex_effort") or "auto",\n                                        codex_identity=credentials.get("codex_identity"))\n')
replace(images, '        processed = _decode_reference_images(images, directory)\n', '''        if cancelled is not None and cancelled.is_set():
            raise RuntimeError('会话或任务已取消，未发出生成请求')
        processed = _decode_reference_images(images, directory)
''')
replace(images, '            credentials = {"codex_model": cfg.get("codex_model", ""), "codex_effort": cfg.get("codex_effort") or "auto"}\n', '            credentials = {"codex_model": cfg.get("codex_model", ""), "codex_effort": cfg.get("codex_effort") or "auto", "codex_identity": codex_identity()}\n')
replace(images, '                                         cancel_callback=cancelled.set if provider == "codex_images" else None)\n', '                                         cancel_callback=cancelled.set, owner=owner_key())\n')
replace(images, '    task = image_task_manager.get(task_id)\n', '    task = image_task_manager.get(task_id, owner=owner_key())\n')
replace(images, '    task = image_task_manager.cancel(task_id)\n', '    task = image_task_manager.cancel(task_id, owner=owner_key())\n')
tasks = 'src/nano_banana/web/image_tasks.py'
replace(tasks, 'def submit(self, runner, *, provider, model, cancel_callback=None):', 'def submit(self, runner, *, provider, model, cancel_callback=None, owner=None):')
replace(tasks, '            key, now = uuid.uuid4().hex, time.time()\n', '''            if owner is not None and sum(t.get('owner') == owner and t['status'] not in FINAL_STATUSES for t in self._tasks.values()) >= 8:
                raise OverflowError('当前用户已有8个未完成图片任务')
            key, now = uuid.uuid4().hex, time.time()
''')
replace(tasks, '                    "cancel_requested": False, "future": None, "cancel_callback": cancel_callback}\n', '                    "cancel_requested": False, "future": None, "cancel_callback": cancel_callback, "owner": owner}\n')
replace(tasks, '    def get(self, task_id):\n', '    def get(self, task_id, owner=None):\n')
replace(tasks, '            return self._public_snapshot(task) if task else None\n', '            return self._public_snapshot(task) if task and task.get("owner") == owner else None\n')
replace(tasks, '    def cancel(self, task_id):\n', '    def cancel(self, task_id, owner=None):\n')
replace(tasks, '            if not task:\n                return None\n', '            if not task or task.get("owner") != owner:\n                return None\n')
replace(tasks, '    def cleanup(self):\n', '''    def cancel_owner(self, owner):
        with self._lock:
            for key, task in list(self._tasks.items()):
                if task.get('owner') == owner:
                    self.cancel(key, owner=owner)
                    task.update(image=None, images=[], metadata={})
                    if task['status'] in FINAL_STATUSES:
                        self._tasks.pop(key, None)

    def cleanup(self):
''')
# Snapshot access may outlive the request, but never consults a changed global account.

html = 'src/web/static/index.html'
replace(html, '<script src="/static/script.js', '<script src="/static/session-bootstrap.js"></script>\n<script src="/static/script.js')
js = 'src/web/static/session-bootstrap.js'
replace(js, "        authCode = '';\n        const code", "        authCode = '';\n        if (typeof state !== 'undefined') state.codexModels = [];\n        const code")
css = Path('src/web/static/style.css')
css.write_text(css.read_text() + '''
/* Per-tab identity; device codes are rendered as text, never as HTML. */
#nanoSessionModal { z-index: 1800; }
.nano-auth-body { display: grid; gap: 14px; }
.nano-auth-body p { margin: 0; color: var(--text-secondary); }
.nano-auth-actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
#nanoDeviceCode { display: block; font-size: 28px; letter-spacing: .1em; user-select: all; margin: 12px 0; overflow-wrap: anywhere; }
#nanoSessionStatus[data-state="success"] { color: var(--success); }
#nanoSessionStatus[data-state="error"] { color: var(--error-color); }
.nano-auth-body details input { margin: 10px 0; }
#nanoAccountBtn { flex-shrink: 0; }
''')

# Deployment: turn on both layers; keep existing owner data out of tenant directories.
d = 'deploy/update_nano_banana_codex.py'
replace(d, "'/app/src/presets', '/run/secrets/codex-bridge-token'}", "'/app/src/presets', '/run/secrets/codex-bridge-token', '/run/secrets/nano-admin-token', '/run/nano-web-sessions'}")
replace(d, "    os.chmod(token, 0o600)\n", '''    os.chmod(token, 0o600)
    admin_token = secret_dir / 'web-admin-token'
    if not admin_token.exists():
        admin_token.write_text(secrets.token_urlsafe(32))
    if not admin_token.is_file() or len(admin_token.read_text().strip()) < 32:
        raise RuntimeError('管理员密钥文件无效，拒绝覆盖')
    os.chmod(admin_token, 0o600)
''')
replace(d, "            '-e', 'CODEX_MAX_PENDING=32',\n", "            '-e', 'CODEX_MAX_PENDING=32', '-e', 'CODEX_MULTIUSER=1',\n")
replace(d, "               '-e', 'CODEX_BRIDGE_TOKEN_FILE=/run/secrets/codex-bridge-token',\n", "               '-e', 'CODEX_BRIDGE_TOKEN_FILE=/run/secrets/codex-bridge-token',\n               '-e', 'NANO_MULTIUSER=1', '-e', 'NANO_ADMIN_TOKEN_FILE=/run/secrets/nano-admin-token',\n               '--tmpfs', '/run/nano-web-sessions:rw,size=256m,mode=0700',\n               '-v', f'{admin_token}:/run/secrets/nano-admin-token:ro',\n")
replace(d, "c=json.load(urllib.request.urlopen(u+'/api/config',timeout=3)); assert 'chat_engine' in c; d=json.load(urllib.request.urlopen(u+'/api/generate-image/capacity',timeout=3)); assert d['workers']>0; print(json.dumps(d))", "d=json.load(urllib.request.urlopen(u+'/api/health',timeout=3)); assert d['multiuser'] and d['workers']>0; print(json.dumps(d))")
replace(d, "        print('浏览器 Ctrl+Shift+R；原 API 配置保留。Codex 必须登录后手动选择，不自动切换。')", "        print('浏览器 Ctrl+Shift+R → 我的 Codex → 个人设备授权。原配置仅管理员可见。')\n        print(f'管理员密钥只在服务器查看：cat {admin_token}')")
# Integration is syntactic only; deployment smoke and unit/browser tests run next.
print('Multiuser integration applied')
