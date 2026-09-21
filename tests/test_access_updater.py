"""无需 Docker 或联网的更新器安全回归；真实部署另由 Docker smoke 验证。"""
import ast
import builtins
from collections import deque
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / 'deploy/update_nano_banana_codex.py'
spec = importlib.util.spec_from_file_location('nano_access_updater_tests', UPDATER)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def test_all_literal_python_probes_compile_before_deployment():
    count = 0
    for node in ast.walk(ast.parse(UPDATER.read_text())):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if value.startswith(('import ', 'from ')):
                compile(value, '<updater-python-probe>', 'exec')
                count += 1
    assert count >= 4


@pytest.mark.parametrize('container_access,manifest_access', [(True, False), (False, True)])
def test_missing_existing_access_policy_cannot_downgrade(tmp_path, monkeypatch, container_access, manifest_access):
    prior = {'Config': {'Env': ['NANO_ACCESS_REQUIRED=1'] if container_access else []}}
    monkeypatch.setattr(updater, 'inspect', lambda _: prior)
    monkeypatch.setattr(updater, 'run', lambda *_a, **_k: pytest.fail('must not mutate Docker'))
    if manifest_access:
        (tmp_path / 'deployment.json').write_text(json.dumps({'access_identity': True}))
    args = SimpleNamespace(access_config=None, require_access=False, container='nano-test')
    with pytest.raises(RuntimeError, match='拒绝降级'):
        updater.deploy(args, tmp_path)
    assert not (tmp_path / 'releases').exists()


def test_interactive_policy_is_staged_without_replacing_live_config(tmp_path, monkeypatch):
    (tmp_path / 'access').mkdir()
    live = tmp_path / 'access/cloudflare.json'
    original = json.dumps({'issuer': 'https://original.cloudflareaccess.com', 'audiences': ['old-aud'],
                           'admin_emails': ['old-admin@example.com'], 'admin_subjects': []})
    live.write_text(original)
    replies = deque(['new-team.cloudflareaccess.com\n', 'new-aud\n',
                     'one@example.com,two@example.com\n', '\n', 'YES\n'])
    class TTY:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def write(self, _): pass
        def flush(self): pass
        def readline(self): return replies.popleft()
    original_open = builtins.open
    monkeypatch.setattr(builtins, 'open', lambda path, *a, **k: TTY() if str(path) == '/dev/tty' else original_open(path, *a, **k))
    pending = updater.configure_access(tmp_path)
    assert pending != live and pending.parent == tmp_path
    assert live.read_text() == original
    staged = json.loads(pending.read_text())
    assert staged['issuer'] == 'https://new-team.cloudflareaccess.com'
    assert staged['admin_emails'] == ['one@example.com', 'two@example.com']
    assert pending.stat().st_mode & 0o777 == 0o600
