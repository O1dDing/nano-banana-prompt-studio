"""一次性、严格匹配的开发迁移脚本；不在用户服务器自动修改运行源码。"""
from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    s = p.read_text()
    if new in s:
        return
    if s.count(old) != 1 and old.strip() != 'if (data.session_expired) expireUI();':
        raise SystemExit(f'{path}: target count {s.count(old)}')
    p.write_text(s.replace(old, new) if old.strip() == 'if (data.session_expired) expireUI();' else s.replace(old, new, 1))


p = 'pyproject.toml'
edit(p, 'web = [\n', 'web = [\n    "PyJWT[crypto]>=2.10.1,<3",\n')
p = 'src/nano_banana/web/user_sessions.py'
edit(p, "    return os.getenv('NANO_MULTIUSER', '0') == '1'", "    return os.getenv('NANO_MULTIUSER', '0') == '1' or os.getenv('NANO_ACCESS_REQUIRED', '0') == '1'")
edit(p, "return _response({'ok': True, 'multiuser': enabled(), 'workers': image_task_manager.max_workers})",
     "return _response({'ok': True, 'multiuser': enabled(), 'access_identity': os.getenv('NANO_ACCESS_REQUIRED') == '1', 'workers': image_task_manager.max_workers})")
edit(p, "return _response({'enabled': enabled(), 'heartbeat_seconds': 30, 'lease_seconds': 90,\n                          'absolute_seconds': ABSOLUTE_SECONDS})",
     "return _response({'enabled': enabled(), 'heartbeat_seconds': 30, 'lease_seconds': 90,\n                          'absolute_seconds': ABSOLUTE_SECONDS,\n                          **(app.extensions['nano_access'].info() if 'nano_access' in app.extensions else {})})")
edit(p, "    app.extensions['nano_sessions'] = manager\n", "    app.extensions['nano_sessions'] = manager\n    if os.getenv('NANO_ACCESS_REQUIRED', '0') == '1':\n        from nano_banana.web.access_binding import AccessBinding\n        AccessBinding(app, manager)\n")
edit(p, "                'heartbeat_seconds': 30, 'lease_seconds': 90}\n\n    @app.post('/api/session/open')",
     "                'heartbeat_seconds': 30, 'lease_seconds': 90,\n                **(app.extensions['nano_access'].summary(lease) if 'nano_access' in app.extensions else {})}\n\n    @app.post('/api/session/open')")
edit(p, "        token, lease = manager.create()\n        return _response({'token': token, **summary(lease)}, 201)",
     "        token, lease = manager.create()\n        if 'nano_access' in app.extensions:\n            app.extensions['nano_access'].attach(lease)\n        return _response({'token': token, **summary(lease)}, 201)")
p = 'src/nano_banana/codex_bridge/leases.py'
edit(p, "return (lease.closed.is_set() or now >= lease.deadline\n                or now - lease.seen >= LEASE_SECONDS)",
     "return (lease.closed.is_set() or now >= lease.deadline\n                or now >= lease.state.get('access_deadline', float('inf'))\n                or now - lease.seen >= LEASE_SECONDS)")

p = 'src/nano_banana/web/blueprints/config.py'
edit(p, 'bp = Blueprint("config", __name__)', 'bp = Blueprint("config", __name__)\n\nSECRET_KEYS = {"api_key", "gemini_api_key", "openai_image_api_key", "qwen_image_api_key", "doubao_image_api_key"}')
edit(p, '        updates = flatten_legacy_or_nested(data)\n', '''        updates = flatten_legacy_or_nested(data)
        from nano_banana.core.config import AIConfigManager
        if set(updates) - set(AIConfigManager.DEFAULT_CONFIG):
            return jsonify({"error": "配置包含不允许的字段"}), 400
        for key in SECRET_KEYS & updates.keys():
            if not isinstance(updates[key], str):
                return jsonify({"error": "API Key 必须是字符串"}), 400
        # 空白保存只更新其它设置；删除必须走显式 DELETE，不能误清其它页签保存的 Key。
        updates = {key: value for key, value in updates.items()
                   if key not in SECRET_KEYS or value.strip()}
''')
s = Path(p).read_text()
if 'def clear_api_key(' not in s:
    Path(p).write_text(s + '''

@bp.delete('/api/config/keys/<key>')
def clear_api_key(key):
    if key not in SECRET_KEYS:
        return jsonify({'error': '未知密钥字段'}), 400
    if not config_manager.save_config({key: ''}):
        return jsonify({'error': '密钥清除失败'}), 500
    return jsonify({'success': True})
''')

p = 'src/web/static/session-bootstrap.js'
edit(p, "    let lost = false, authCode = '';", "    let lost = false, authCode = '';\n    let accessInfo = null;")
edit(p, '            if (data.session_expired) expireUI();', '            if (data.session_expired || data.access_required) expireUI();')
edit(p, "        if (!info.enabled) return; // 兼容单用户旧部署和离线 UI 测试。", '''        if (!info.enabled) return; // 兼容单用户旧部署和离线 UI 测试。
        accessInfo = info.identity_provider === 'cloudflare' ? info : null;
        if (accessInfo) {
            const previous = sessionStorage.getItem('nano.access.identity');
            if (previous && previous !== info.identity_key) {
                sessionStorage.removeItem(KEY);
                sessionStorage.removeItem('nano-banana-form-draft');
            }
            sessionStorage.setItem('nano.access.identity', info.identity_key);
        }''')
edit(p, "if (badge) badge.textContent = role === 'owner' ? '管理员' : '我的 Codex';", "if (badge) {badge.textContent = role === 'owner' ? '管理员' : '我的 Codex'; badge.title = accessInfo?.email || '';}\n        const identity = document.getElementById('nanoSiteIdentity');\n        if (identity) identity.textContent = accessInfo ? '网站身份：' + accessInfo.email + (role === 'owner' ? ' · 管理员' : '') : '';")
edit(p, '<div class="modal-body nano-auth-body"><p id="nanoSessionStatus" role="status">尚未认证</p>', '<div class="modal-body nano-auth-body"><p id="nanoSiteIdentity"></p><p id="nanoSessionStatus" role="status">尚未认证</p>')
edit(p, "        document.body.appendChild(modal);", '''        if (accessInfo) {
            modal.querySelector('details').hidden = true;
            document.getElementById('nanoSessionStatus');
            const description = modal.querySelector('.nano-auth-body > p:nth-of-type(3)');
            if (description) description.textContent = '网站身份由 Cloudflare 验证；API 配置和预设永久保存。Codex 授权仅用于当前页签，30 秒心跳、90 秒失联回收、最长 24 小时。';
        }
        document.body.appendChild(modal);''')
edit(p, "        button.textContent = '我的 Codex';", "        button.textContent = role === 'owner' ? '管理员' : '我的 Codex';\n        button.title = accessInfo?.email || '';\n        document.getElementById('nanoSiteIdentity').textContent = accessInfo ? '网站身份：' + accessInfo.email + (role === 'owner' ? ' · 管理员' : '') : '';")
edit(p, "await reloadWorkbench(); renderStatus('已退出；当前是新的未认证个人会话');", "await reloadWorkbench(); renderStatus(accessInfo ? 'Codex 会话已销毁；已重新加载此 Cloudflare 身份的持久配置' : '已退出；当前是新的未认证个人会话');")
edit(p, "            if (data.session_expired) expireUI();\n        }\n        return response;", "            if (data.session_expired || data.access_required) expireUI();\n        }\n        return response;") if "            if (data.session_expired) expireUI();\n        }\n        return response;" in Path(p).read_text() else None
edit(p, "        if (response.status === 401) {", "        if (response.status === 401 || response.status === 403 || response.status === 503) {")
edit(p, "window.NanoSession = {ready, get enabled() {return active;}, get role() {return role;},", "window.NanoSession = {ready, get enabled() {return active;}, get role() {return role;}, get accessIdentity() {return accessInfo;},")
# Headers contain only our tab token. The Cloudflare JWT is injected by the reverse proxy, not JS.

p = 'src/web/static/image-gen.js'
edit(p, "    elements.configModal.classList.add('active');", "    if (typeof refreshProfileKeyControls === 'function') refreshProfileKeyControls();\n    elements.configModal.classList.add('active');")
edit(p, "    try {\n        const response = await fetch('/api/config', {", "    // 只提交改变的字段，避免同一个人的两个页签覆盖彼此未修改的设置。\n    for (const [key, value] of Object.entries(payload)) {\n        if (value === state.config[key]) delete payload[key];\n    }\n    try {\n        const response = await fetch('/api/config', {")
p = 'src/web/static/index.html'
edit(p, '<script src="/static/codex-ui.js"></script>', '<script src="/static/codex-ui.js"></script><script src="/static/access-profile-ui.js"></script>')

# Docker updater: Access mode opt-in from server file, auto-preserved on subsequent upgrades.
p = 'deploy/update_nano_banana_codex.py'
edit(p, "'/run/secrets/nano-admin-token', '/run/nano-web-sessions'}", "'/run/secrets/nano-admin-token', '/run/nano-web-sessions', '/run/nano-access', '/app/users'}")
edit(p, "    for key in ('config', 'presets'):\n        prior =", "    for key in ('config', 'presets', 'access'):\n        prior =")
edit(p, "    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(2)", '''    access_file = Path(args.access_config).resolve() if args.access_config else data / 'access/cloudflare.json'
    access_enabled = access_file.is_file()
    if args.require_access and not access_enabled:
        raise RuntimeError('缺少 Access 配置；先使用 --configure-access，未停止旧服务')
    if access_file.is_symlink():
        raise RuntimeError('Access 配置不能是符号链接')
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(2)''')
edit(p, "    secret_dir, auth = data / 'secrets', data / 'codex-auth'", '''    if access_enabled:
        access_stage = backup / 'staging/access'
        access_stage.mkdir(mode=0o700)
        shutil.copy2(access_file, access_stage / 'cloudflare.json')
        os.chmod(access_stage / 'cloudflare.json', 0o600)
        # 先用新镜像的实际解析器验证信任边界，错误配置绝不进入切换步骤。
        run('docker', 'run', '--rm', '-v', f'{access_stage}:/run/nano-access:ro', web_image,
            'python', '-c', "from nano_banana.core.access_config import AccessConfig; c=AccessConfig.load('/run/nano-access/cloudflare.json'); print('Access 配置校验通过；多管理员已配置')")
        profiles = data / 'users'
        profiles.mkdir(mode=0o700, exist_ok=True)
        os.chmod(profiles, 0o700)
    secret_dir, auth = data / 'secrets', data / 'codex-auth' ''')
edit(p, "        cmd = ['docker', 'create', '--name', args.container,", '''        if access_enabled:
            if (data / 'access').exists():
                (data / 'access').rename(backup / 'pre-swap/access')
            (backup / 'staging/access').rename(data / 'access')
            # 旧 Web 已停止，复制完整个人仓库；回滚不覆盖升级后用户新写入的档案。
            shutil.copytree(data / 'users', backup / 'users-snapshot', symlinks=True)
        cmd = ['docker', 'create', '--name', args.container,''')
edit(p, "        for binding in ports:\n            cmd += ['-p', binding]", "        if access_enabled:\n            cmd += ['-e', 'NANO_ACCESS_REQUIRED=1', '-e', 'NANO_ACCESS_CONFIG_FILE=/run/nano-access/cloudflare.json',\n                    '-e', 'NANO_PROFILES_DIR=/app/users', '-v', f'{data}/access:/run/nano-access:ro',\n                    '-v', f'{data}/users:/app/users']\n        for binding in ports:\n            cmd += ['-p', binding]")
edit(p, "        save_json(data / 'deployment.json', {**manifest, 'commit': sha, 'source': str(source),", "        if access_enabled:\n            run('docker', 'exec', args.container, 'python', '-c', \"import json,urllib.request,urllib.error; u='http://127.0.0.1:5000'; assert json.load(urllib.request.urlopen(u+'/api/health'))['access_identity']; exec(\\\"try:\\n urllib.request.urlopen(u+'/api/config')\\n raise AssertionError('missing JWT accepted')\\nexcept urllib.error.HTTPError as e:\\n assert e.code == 403\\\")\")\n        save_json(data / 'deployment.json', {**manifest, 'access_identity': access_enabled, 'commit': sha, 'source': str(source),")
edit(p, "        print(f'管理员密钥只在服务器查看：cat {admin_token}')", "        if access_enabled:\n            print(f'Cloudflare 身份和多管理员配置：{data}/access/cloudflare.json')\n            print('Cloudflare 登录后恢复个人 API；管理员自动使用原服务器配置。无需粘贴管理员密钥。')\n        else:\n            print(f'管理员密钥只在服务器查看：cat {admin_token}')")
edit(p, "    parser.add_argument('--login-only', action='store_true')", "    parser.add_argument('--access-config', help='Cloudflare JSON 文件；默认读取 DATA/access/cloudflare.json')\n    parser.add_argument('--require-access', action='store_true', help='无 Access 配置则拒绝部署')\n    parser.add_argument('--configure-access', action='store_true', help='交互填写 team、AUD、多位管理员，然后更新')\n    parser.add_argument('--login-only', action='store_true')")
edit(p, "        else:\n            deploy(args, data)\n", "        else:\n            if args.configure_access:\n                configure_access(data)\n                args.require_access = True\n            deploy(args, data)\n")
configure = '''
def configure_access(data):
    """仅服务器 root 可运行；配置和密钥不从浏览器参数学习。"""
    path = data / 'access/cloudflare.json'
    existing = json.loads(path.read_text()) if path.is_file() else {}
    with open('/dev/tty', 'r+') as tty:
        def ask(label, current=''):
            tty.write(f'{label}' + (f' [{current}]' if current else '') + ': ')
            tty.flush()
            line = tty.readline()
            if not line:
                raise RuntimeError('配置输入已结束')
            return line.strip() or current
        issuer = ask('Cloudflare Team 域名（例如 myteam.cloudflareaccess.com）', existing.get('issuer', ''))
        if not issuer.startswith('https://'):
            issuer = 'https://' + issuer
        issuer = issuer.rstrip('/')
        if not re.fullmatch(r'https://[a-z0-9][a-z0-9-]*[.]cloudflareaccess[.]com', issuer):
            raise RuntimeError('Team 域名格式无效')
        def values(name, label):
            raw = ask(label, ','.join(existing.get(name, [])))
            return [] if raw == '-' else list(dict.fromkeys(v.strip() for v in re.split(r'[,;\\s]+', raw) if v.strip()))
        audiences = values('audiences', 'Application Audience (AUD)，多个用逗号分隔')
        emails = values('admin_emails', '管理员邮箱，多个用逗号分隔；输入 - 清空')
        subjects = values('admin_subjects', '管理员 sub，可留空；输入 - 清空')
        if not audiences or not (emails or subjects):
            raise RuntimeError('至少提供一个 AUD 和一名管理员')
        if any(not re.fullmatch(r'[^\\s@*]+@[^\\s@*]+[.][^\\s@*]+', e) for e in emails):
            raise RuntimeError('管理员邮箱无效')
        settings = dict(existing, issuer=issuer, audiences=audiences, admin_emails=emails, admin_subjects=subjects)
        tty.write('将保存仅此服务器使用的 Access 配置。确认输入 YES: '); tty.flush()
        if tty.readline().strip() != 'YES':
            raise RuntimeError('已取消配置，未部署')
    path.parent.mkdir(mode=0o700, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name('cloudflare.previous-' + str(time.time_ns()) + '.json'))
    save_json(path, settings)

'''
if 'def configure_access(' not in Path(p).read_text():
    edit(p, '\ndef main():\n', configure + '\ndef main():\n')

p = '.github/workflows/web-regression.yml'
edit(p, 'branches: [main, feat/codex-subscription-images-20260920, hotfix/codex-bridge-import-20260920, feat/multiuser-codex-sessions-20260920]', "branches: [main, 'feat/**', 'fix/**', 'hotfix/**']")
edit(p, '          python tools/multiuser_browser_smoke.py', '          python tools/multiuser_browser_smoke.py\n          python tools/access_browser_smoke.py')
edit(p, 'run: sudo --preserve-env=PATH python tools/deployment_smoke.py', 'run: |\n          sudo --preserve-env=PATH python tools/deployment_smoke.py\n          sudo --preserve-env=PATH python tools/access_deployment_smoke.py')
print('Access integration patched. Pin the bootstrap to the resulting updater commit before final release.')
