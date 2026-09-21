#!/usr/bin/env python3
"""Debian 12/Docker 更新器；独立构建、数据迁移、双容器健康检查和回滚。

运行：sudo python3 update_nano_banana_codex.py
登录：sudo python3 update_nano_banana_codex.py --login-only
回滚：sudo python3 update_nano_banana_codex.py --rollback /完整备份目录
不读取 ~/.codex，不重置 /opt/nano-banana-prompt-studio 的本地修改。
"""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time

LABEL = 'io.nano-banana.deployment'


def run(*args, capture=False, check=True):
    return subprocess.run([str(a) for a in args], check=check, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None)


def inspect(name):
    r = run('docker', 'inspect', name, capture=True, check=False)
    return json.loads(r.stdout)[0] if r.returncode == 0 else None


def note(text):
    print(f'[{time.strftime("%H:%M:%S")}] {text}', flush=True)


def save_json(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def merge_tree(src, dst):
    """只在独立 staging 内处理文件/目录冲突，绝不递归删除正式数据。"""
    if not src.exists():
        return
    if src.is_symlink():
        raise RuntimeError(f'数据源是符号链接，请先确认并转换为实际文件：{src}')
    if src.is_dir():
        if dst.exists() and not dst.is_dir():
            dst.unlink()
        dst.mkdir(parents=True, exist_ok=True)
        for child in src.iterdir():
            merge_tree(child, dst / child.name)
    else:
        if dst.is_dir():
            shutil.rmtree(dst)  # dst 始终是 staging 内路径。
        shutil.copy2(src, dst)


def copy_container(name, path, target):
    target.mkdir(parents=True, exist_ok=True)
    r = run('docker', 'cp', f'{name}:{path}/.', target, capture=True, check=False)
    if r.returncode and not any(s in r.stderr.lower() for s in ('could not find', 'no such file')):
        raise RuntimeError(f'容器数据备份失败：{path}\n{r.stderr}')


def ports_and_networks(old):
    if not old:
        return ['127.0.0.1:5000:5000'], []
    mode = old['HostConfig'].get('NetworkMode', '')
    if mode in ('host', 'none') or mode.startswith('container:'):
        raise RuntimeError(f'旧容器使用特殊网络 {mode}；未停止服务，请先改为 bridge 网络部署')
    ports = []
    for target, bindings in (old['HostConfig'].get('PortBindings') or {}).items():
        for binding in bindings or []:
            ip, port = binding.get('HostIp', ''), binding.get('HostPort', '')
            if not port:
                raise RuntimeError('不自动迁移随机映射端口')
            prefix = f'[{ip}]:{port}' if ':' in ip else f'{ip}:{port}' if ip else port
            ports.append(f'{prefix}:{target}')
    networks = [n for n in old['NetworkSettings']['Networks'] if n not in ('bridge', 'host', 'none')]
    allowed = {'/app/src/config', '/app/src/config/ai_config.yaml', '/app/src/config/options.yaml',
               '/app/src/presets', '/run/secrets/codex-bridge-token', '/run/secrets/nano-admin-token', '/run/nano-web-sessions', '/run/nano-access', '/app/users'}
    extra = [m['Destination'] for m in old.get('Mounts', []) if m['Destination'] not in allowed]
    if extra:
        raise RuntimeError('发现额外挂载，未停止旧服务。需人工核对迁移：' + ', '.join(extra))
    if not ports and not networks:
        raise RuntimeError('无法确认旧容器的访问入口，停止更新以免改变访问方式')
    return ports, networks


def wait_health(name, python_code):
    for _ in range(40):
        r = run('docker', 'exec', name, 'python', '-c', python_code, capture=True, check=False)
        if r.returncode == 0:
            return r.stdout.strip()
        state = inspect(name)
        if not state or not state['State']['Running']:
            break
        time.sleep(1)
    logs = run('docker', 'logs', '--tail', '40', name, capture=True, check=False)
    raise RuntimeError(f'{name} 健康检查失败\n{logs.stderr}\n{logs.stdout}')


def rollback(manifest, backup):
    """恢复容器与原持久化目录。所有操作都保留可检查的数据副本。"""
    data = Path(manifest['data'])
    web = manifest['web']
    old = manifest['old_web']
    current = inspect(web)
    if current and (current['Config'].get('Labels') or {}).get(LABEL) == manifest['stamp']:
        run('docker', 'rm', '-f', web)
    elif current and inspect(old):
        raise RuntimeError('当前容器不属于此次部署，拒绝覆盖；请手动核对')
    bridge = inspect(manifest['bridge'])
    if bridge and (bridge['Config'].get('Labels') or {}).get(LABEL) == manifest['stamp']:
        run('docker', 'rm', '-f', manifest['bridge'])
    for key in ('config', 'presets', 'access'):
        prior = backup / 'pre-swap' / key
        if prior.exists():
            live = data / key
            if live.exists():
                live.rename(backup / f'{key}-after-update-{time.time_ns()}')
            prior.rename(live)
    if inspect(old):
        run('docker', 'rename', old, web)
        if manifest['old_running']:
            run('docker', 'start', web)
    elif manifest['old_running'] and inspect(web):
        run('docker', 'start', web)
    prior_state = backup / 'deployment-before.json'
    if prior_state.is_file():
        shutil.copy2(prior_state, data / 'deployment.json')
        old_bridge = json.loads(prior_state.read_text()).get('bridge')
        if old_bridge and inspect(old_bridge):
            run('docker', 'start', old_bridge)
    elif (data / 'deployment.json').exists():
        (data / 'deployment.json').unlink()
    note('回滚完成；失败时的数据另存于备份目录，未清空')


def login(data):
    state = json.loads((data / 'deployment.json').read_text())
    name = state['bridge']
    if not inspect(name):
        raise RuntimeError('Codex 容器不存在，请先运行更新')
    note('在你自己的浏览器完成一次 ChatGPT 设备授权；不要把授权码发送给他人')
    r = run('docker', 'exec', '-it', name, 'codex', '-c', 'forced_login_method="chatgpt"',
            '-c', 'cli_auth_credentials_store="file"', '-c', 'history.persistence="none"',
            '-c', 'log_dir="/run/nano-codex/login-logs"', 'login', '--device-auth', check=False)
    if r.returncode:
        raise RuntimeError('登录未完成；现有 API 生图仍可用。确认允许设备授权后重新运行 --login-only')
    note('登录完成。网页设置 → 刷新 Codex 状态；模型从账户可用列表读取')


def bounded(name, default, maximum):
    value = int(os.getenv(name, str(default)))
    if not 1 <= value <= maximum:
        raise RuntimeError(f'{name} 必须在 1～{maximum} 之间')
    return value


def deploy(args, data):
    access_file = Path(args.access_config).resolve() if args.access_config else data / 'access/cloudflare.json'
    access_enabled = access_file.is_file()
    prior = inspect(args.container)
    was_access = prior is not None and 'NANO_ACCESS_REQUIRED=1' in prior['Config'].get('Env', [])
    prior_manifest = data / 'deployment.json'
    if prior_manifest.is_file():
        was_access = was_access or json.loads(prior_manifest.read_text()).get('access_identity', False)
    if (args.require_access or args.access_config or was_access) and not access_enabled:
        raise RuntimeError('缺少 Access 配置；拒绝降级到无 Access 模式，未停止旧服务')
    if access_file.is_symlink():
        raise RuntimeError('Access 配置不能是符号链接')
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(2)
    backup = data / 'backups' / stamp
    source = data / 'releases' / stamp
    backup.mkdir(parents=True)
    (backup / 'staging').mkdir()
    (backup / 'pre-swap').mkdir()
    old_info = inspect(args.container)
    ports, networks = ports_and_networks(old_info)
    if old_info:
        save_json(backup / 'old-container.json', old_info)
    if (data / 'deployment.json').is_file():
        shutil.copy2(data / 'deployment.json', backup / 'deployment-before.json')
    manifest = {'stamp': stamp, 'data': str(data), 'web': args.container,
                'bridge': f'{args.container}-codex-{stamp}', 'old_web': f'{args.container}-rollback-{stamp}',
                'old_running': bool(old_info and old_info['State']['Running'])}
    save_json(backup / 'rollback.json', manifest)
    image_workers = bounded('IMAGE_TASK_WORKERS', 4, 32)
    prompt_workers = bounded('CODEX_PROMPT_WORKERS', 4, 32)
    codex_images = bounded('CODEX_IMAGE_WORKERS', 4, 32)
    pending = bounded('IMAGE_TASK_MAX_PENDING', 32, 256)
    threads = bounded('WEB_THREADS', 16, 64)
    source.parent.mkdir(exist_ok=True)
    note('在独立 release 目录拉取 Fork；不覆盖原项目本地修改')
    run('git', 'clone', '--depth', '1', '--branch', args.ref, '--single-branch', args.repo, source)
    required_bridge = [
        source / 'src/nano_banana/codex_bridge/__init__.py',
        source / 'src/nano_banana/codex_bridge/server.py',
        source / 'src/nano_banana/codex_bridge/runtime.py',
        source / 'deploy/codex.Dockerfile',
    ]
    missing_bridge = [str(path.relative_to(source)) for path in required_bridge if not path.is_file()]
    if missing_bridge:
        raise RuntimeError(
            '拉取的发布源码缺少 Codex Bridge 文件，未构建也未停止旧服务：'
            + ', '.join(missing_bridge)
        )
    sha = run('git', '-C', source, 'rev-parse', 'HEAD', capture=True).stdout.strip()
    web_image = os.getenv('NANO_WEB_IMAGE') or f'nano-banana-web:codex-{sha[:12]}-{stamp}'
    bridge_image = os.getenv('NANO_CODEX_IMAGE') or f'nano-banana-codex:{sha[:12]}-{stamp}'
    note(f'构建 {sha}；此阶段旧服务继续运行')
    if not os.getenv('NANO_WEB_IMAGE'):
        run('docker', 'build', '--pull', '-f', source / 'web_dockerfile', '-t', web_image, source)
    if not os.getenv('NANO_CODEX_IMAGE'):
        # Bridge 很小且持有关键运行入口；强制无缓存重建，避免复用历史损坏/过期 COPY 层。
        run('docker', 'build', '--pull', '--no-cache',
            '-f', source / 'deploy/codex.Dockerfile', '-t', bridge_image, source)
    run('docker', 'image', 'inspect', web_image, capture=True)
    run('docker', 'image', 'inspect', bridge_image, capture=True)

    # 在创建长期 Bridge 容器、尤其是在停止旧 Web 之前，先启动一次干净容器验证安装结果。
    # 这会直接捕获 ModuleNotFoundError 等镜像打包问题。
    bridge_probe = (
        "import importlib.util, pathlib; "
        "assert importlib.util.find_spec('nano_banana.codex_bridge.server') is not None; "
        "assert importlib.util.find_spec('nano_banana.codex_bridge.runtime') is not None; "
        "import nano_banana.codex_bridge.server, nano_banana.codex_bridge.runtime; "
        "assert pathlib.Path('/app/codex-protocol.json').is_file(); "
        "print('Codex Bridge image import probe OK')"
    )
    run('docker', 'run', '--rm', '--entrypoint', 'python',
        bridge_image, '-c', bridge_probe)
    if access_enabled:
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
    secret_dir, auth = data / 'secrets', data / 'codex-auth' 
    secret_dir.mkdir(exist_ok=True)
    auth.mkdir(exist_ok=True)
    os.chown(auth, 10001, 10001)
    os.chmod(auth, 0o700)
    token = secret_dir / 'codex-bridge-token'
    if not token.exists():
        token.write_text(secrets.token_hex(32))
    if not token.is_file() or len(token.read_text().strip()) < 32:
        raise RuntimeError('Bridge token 文件无效，拒绝替换已有凭据')
    os.chown(token, 10001, 10001)
    os.chmod(token, 0o600)
    admin_token = secret_dir / 'web-admin-token'
    if not admin_token.exists():
        admin_token.write_text(secrets.token_urlsafe(32))
    if not admin_token.is_file() or len(admin_token.read_text().strip()) < 32:
        raise RuntimeError('管理员密钥文件无效，拒绝覆盖')
    os.chmod(admin_token, 0o600)
    network = f'{args.container}-codex-private'
    if run('docker', 'network', 'inspect', network, check=False, capture=True).returncode:
        run('docker', 'network', 'create', network)
    try:
        note('启动独立 Codex 容器：无公网端口、非 root、临时文件走 tmpfs')
        run('docker', 'create', '--name', manifest['bridge'], '--label', f'{LABEL}={stamp}',
            '--restart', 'unless-stopped', '--network', network, '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--pids-limit', '512',
            '--tmpfs', '/run/nano-codex:rw,size=1024m,uid=10001,gid=10001,mode=0700',
            '--tmpfs', '/tmp:rw,size=256m,mode=1777',
            '-e', f'CODEX_PROMPT_WORKERS={prompt_workers}', '-e', f'CODEX_IMAGE_WORKERS={codex_images}',
            '-e', 'CODEX_MAX_PENDING=32', '-e', 'CODEX_MULTIUSER=1',
            '-v', f'{auth}:/var/lib/nano-codex', '-v', f'{token}:/run/secrets/codex-bridge-token:ro', bridge_image)
        run('docker', 'start', manifest['bridge'])
        wait_health(manifest['bridge'], "import json,urllib.request,pathlib; t=pathlib.Path('/run/secrets/codex-bridge-token').read_text().strip(); r=urllib.request.Request('http://127.0.0.1:8787/health',headers={'Authorization':'Bearer '+t}); assert json.load(urllib.request.urlopen(r,timeout=3))['ok']")
        note('请勿在更新期间新建任务；现在停止旧 Web 并取得最终数据快照')
        if old_info:
            run('docker', 'stop', '-t', '30', args.container)
            run('docker', 'rename', args.container, manifest['old_web'])
            for key in ('config', 'presets'):
                copy_container(manifest['old_web'], '/app/src/' + key, backup / ('container-' + key))
        for key in ('config', 'presets'):
            target = backup / 'staging' / key
            target.mkdir()
            for src in (source / 'src' / key, Path(args.app) / 'src' / key,
                        data / key, backup / ('container-' + key)):
                merge_tree(src, target)
        ai = backup / 'staging/config/ai_config.yaml'
        if ai.is_dir():
            ai.rename(backup / 'conflicting-ai-config-directory')
        if not ai.is_file():
            candidates = [backup / 'container-config/ai_config.yaml', data / 'config/ai_config.yaml',
                          Path(args.app) / 'src/config/ai_config.yaml']
            valid = next((p for p in candidates if p.is_file() and not p.is_symlink()), None)
            if valid:
                shutil.copy2(valid, ai)
            elif old_info:
                raise RuntimeError('找不到旧 API 配置的真实文件，拒绝用空配置替代；冲突目录已保留')
            else:
                ai.write_text('{}\n')
        os.chmod(ai, 0o600)
        validate = "import pathlib,yaml; from nano_banana.core.config import AIConfigManager; p=pathlib.Path('/app/src/config/ai_config.yaml'); assert p.is_file(); assert isinstance(yaml.safe_load(p.read_text()) or {},dict); AIConfigManager().get_chat_config(); print('配置校验通过')"
        run('docker', 'run', '--rm', '-v', f'{backup}/staging/config:/app/src/config', web_image, 'python', '-c', validate)
        for key in ('config', 'presets'):
            if (data / key).exists():
                (data / key).rename(backup / 'pre-swap' / key)
            (backup / 'staging' / key).rename(data / key)
        if access_enabled:
            if (data / 'access').exists():
                (data / 'access').rename(backup / 'pre-swap/access')
            (backup / 'staging/access').rename(data / 'access')
            # 旧 Web 已停止，复制完整个人仓库；回滚不覆盖升级后用户新写入的档案。
            shutil.copytree(data / 'users', backup / 'users-snapshot', symlinks=True)
        cmd = ['docker', 'create', '--name', args.container, '--label', f'{LABEL}={stamp}',
               '--restart', 'unless-stopped', '--network', networks[0] if networks else network,
               '-e', f'CODEX_BRIDGE_URL=http://{manifest["bridge"]}:8787',
               '-e', 'CODEX_BRIDGE_TOKEN_FILE=/run/secrets/codex-bridge-token',
               '-e', 'NANO_MULTIUSER=1', '-e', 'NANO_ADMIN_TOKEN_FILE=/run/secrets/nano-admin-token',
               '--tmpfs', '/run/nano-web-sessions:rw,size=256m,mode=0700',
               '-v', f'{admin_token}:/run/secrets/nano-admin-token:ro',
               '-e', f'IMAGE_TASK_WORKERS={image_workers}', '-e', f'IMAGE_TASK_MAX_PENDING={pending}',
               '-e', 'IMAGE_TASK_TTL_SECONDS=1800', '-e', f'WEB_THREADS={threads}', '-e', 'WEB_TIMEOUT=180',
               '-v', f'{data}/config:/app/src/config', '-v', f'{data}/presets:/app/src/presets',
               '-v', f'{token}:/run/secrets/codex-bridge-token:ro']
        if access_enabled:
            cmd += ['-e', 'NANO_ACCESS_REQUIRED=1', '-e', 'NANO_ACCESS_CONFIG_FILE=/run/nano-access/cloudflare.json',
                    '-e', 'NANO_PROFILES_DIR=/app/users', '-v', f'{data}/access:/run/nano-access:ro',
                    '-v', f'{data}/users:/app/users']
        for binding in ports:
            cmd += ['-p', binding]
        run(*cmd, web_image)
        attached = {networks[0] if networks else network}
        for name in [*networks, network]:
            if name not in attached:
                run('docker', 'network', 'connect', name, args.container)
                attached.add(name)
        run('docker', 'start', args.container)
        result = wait_health(args.container, "import json,urllib.request; u='http://127.0.0.1:5000'; d=json.load(urllib.request.urlopen(u+'/api/health',timeout=3)); assert d['multiuser'] and d['workers']>0; print(json.dumps(d))")
        run('docker', 'exec', args.container, 'python', '-c', "from nano_banana.core.codex_client import CodexBridge; b=CodexBridge(); assert b.request('GET','/health')['ok']; b.close()")
        if access_enabled:
            run('docker', 'exec', args.container, 'python', '-c', "import http.client,json; c=http.client.HTTPConnection('127.0.0.1',5000,timeout=3); c.request('GET','/api/health'); r=c.getresponse(); assert r.status==200; assert json.loads(r.read())['access_identity']; c.request('GET','/api/config'); r=c.getresponse(); assert r.status==403; assert json.loads(r.read())['access_required']; c.close(); print('Access runtime and unauthenticated-request rejection OK')")
        save_json(data / 'deployment.json', {**manifest, 'access_identity': access_enabled, 'commit': sha, 'source': str(source),
                    'web_image': web_image, 'bridge_image': bridge_image, 'backup': str(backup)})
        old_state = backup / 'deployment-before.json'
        if old_state.is_file():
            previous = json.loads(old_state.read_text()).get('bridge')
            if previous and previous != manifest['bridge'] and inspect(previous):
                run('docker', 'stop', '-t', '30', previous)
        note(f'更新成功：{sha}\n运行源码：{source}\n任务容量：{result}\n备份：{backup}')
        print(f'登录：sudo python3 {Path(__file__).resolve()} --data {data} --login-only')
        print(f'回滚：sudo python3 {Path(__file__).resolve()} --rollback {backup}')
        print('浏览器 Ctrl+Shift+R → 我的 Codex → 个人设备授权。原配置仅管理员可见。')
        if access_enabled:
            print(f'Cloudflare 身份和多管理员配置：{data}/access/cloudflare.json')
            print('Cloudflare 登录后恢复个人 API；管理员自动使用原服务器配置。无需粘贴管理员密钥。')
        else:
            print(f'管理员密钥只在服务器查看：cat {admin_token}')
    except BaseException:
        note('更新失败，恢复旧容器及原数据')
        try:
            rollback(manifest, backup)
        except Exception as exc:
            print(f'自动回滚未完全成功：{exc}。按 {backup}/rollback.json 手动恢复。', file=sys.stderr)
        raise


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
            return [] if raw == '-' else list(dict.fromkeys(v.strip() for v in re.split(r'[,;\s]+', raw) if v.strip()))
        audiences = values('audiences', 'Application Audience (AUD)，多个用逗号分隔')
        emails = values('admin_emails', '管理员邮箱，多个用逗号分隔；输入 - 清空')
        subjects = values('admin_subjects', '管理员 sub，可留空；输入 - 清空')
        if not audiences or not (emails or subjects):
            raise RuntimeError('至少提供一个 AUD 和一名管理员')
        if any(not re.fullmatch(r'[^\s@*]+@[^\s@*]+[.][^\s@*]+', e) for e in emails):
            raise RuntimeError('管理员邮箱无效')
        settings = dict(existing, issuer=issuer, audiences=audiences, admin_emails=emails, admin_subjects=subjects)
        tty.write('将保存仅此服务器使用的 Access 配置。确认输入 YES: '); tty.flush()
        if tty.readline().strip() != 'YES':
            raise RuntimeError('已取消配置，未部署')
    # 交互输入不能提前覆盖运行中热加载的策略；新镜像校验通过后才在部署切换步骤安装。
    pending = data / ('.access.pending-' + str(time.time_ns()) + '.json')
    save_json(pending, settings)
    return pending


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', default='/opt/nano-banana-prompt-studio')
    parser.add_argument('--data', default='/opt/nano-banana-data')
    parser.add_argument('--container', default='nano-banana-web')
    parser.add_argument('--repo', default='https://github.com/O1dDing/nano-banana-prompt-studio.git')
    parser.add_argument('--ref', default='main')
    parser.add_argument('--access-config', help='Cloudflare JSON 文件；默认读取 DATA/access/cloudflare.json')
    parser.add_argument('--require-access', action='store_true', help='无 Access 配置则拒绝部署')
    parser.add_argument('--configure-access', action='store_true', help='交互填写 team、AUD、多位管理员，然后更新')
    parser.add_argument('--login-only', action='store_true')
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('请使用 sudo python3 或 root 运行')
    for tool in ('docker', 'git'):
        if not shutil.which(tool):
            parser.error(f'缺少 {tool}')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', args.container):
        parser.error('容器名无效')
    data = Path(args.data).resolve()
    if args.rollback:
        manifest = json.loads((args.rollback / 'rollback.json').read_text())
        data = Path(manifest['data']).resolve()
    if data == Path('/') or len(data.parts) < 3:
        parser.error('数据目录必须是独立的绝对目录')
    data.mkdir(parents=True, exist_ok=True)
    os.chmod(data, 0o700)
    os.umask(0o077)
    def terminated(*_):
        raise KeyboardInterrupt('收到终止信号')
    signal.signal(signal.SIGTERM, terminated)
    with (data / '.update.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('另一个更新/登录/回滚正在执行')
        if args.login_only:
            login(data)
        elif args.rollback:
            rollback(manifest, args.rollback)
        else:
            pending = None
            try:
                if args.configure_access:
                    pending = configure_access(data)
                    args.access_config = str(pending)
                    args.require_access = True
                deploy(args, data)
            finally:
                if pending is not None:
                    pending.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(f'失败：{error}', file=sys.stderr)
        sys.exit(1)
