"""Run under sudo in CI; no provider keys, logins, or generation calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run(*args, capture=False, check=True):
    return subprocess.run([str(x) for x in args], text=True, check=check,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None)


def main():
    assert os.geteuid() == 0
    root = Path(tempfile.mkdtemp(prefix='nano-deployment-test-'))
    data = root / 'data'
    app = root / 'user-checkout'
    app.mkdir()
    (app / 'keep-local.txt').write_text('personal modification must survive')
    (data / 'config/ai_config.yaml').mkdir(parents=True)
    (data / 'config/ai_config.yaml/old-directory-marker').write_text('preserve during rollback')
    (data / 'presets').mkdir()
    (data / 'presets/persistent.json').write_text('{"preserved": true}')
    name = 'nano-updater-smoke'
    repo = root / 'repo.git'
    run('git', 'clone', '--bare', ROOT, repo)
    run('git', '--git-dir', repo, 'tag', 'fixture', 'HEAD')
    try:
        run('docker', 'run', '-d', '--name', name, '--network', 'nano-regression',
            '-p', '127.0.0.1:55001:5000', 'nano-web:regression')
        fixture = {
            'base_url': 'https://unused.invalid/v1', 'api_key': 'dummy-test-not-a-real-key',
            'model': 'fixture-model', 'chat_web_search_mode': 'disabled',
            'openai_image_base_url': 'https://unused.invalid/v1',
            'openai_image_model': 'gpt-image-2', 'openai_image_api_key': 'dummy-image-key',
            'image_provider': 'openai_images',
        }
        setup = (
            'from pathlib import Path; import json; '
            'p=Path("/app/src/config"); p.mkdir(parents=True,exist_ok=True); '
            f'(p/"ai_config.yaml").write_text({json.dumps(json.dumps(fixture))}); '
            'p=Path("/app/src/presets"); p.mkdir(parents=True,exist_ok=True); '
            '(p/"container.json").write_text("{}")'
        )
        run('docker', 'exec', name, 'python', '-c', setup)
        os.environ['NANO_WEB_IMAGE'] = 'nano-web:regression'
        os.environ['NANO_CODEX_IMAGE'] = 'nano-codex:regression'
        command = [sys.executable, ROOT / 'deploy/update_nano_banana_codex.py',
                   '--repo', repo, '--ref', 'fixture', '--app', app,
                   '--data', data, '--container', name]
        run(*command)
        assert (app / 'keep-local.txt').read_text() == 'personal modification must survive'
        assert (data / 'config/ai_config.yaml').is_file()
        assert (data / 'presets/container.json').is_file()
        assert (data / 'presets/persistent.json').is_file()
        status = json.loads(run('docker', 'inspect', name, capture=True).stdout)[0]
        assert status['HostConfig']['PortBindings']['5000/tcp'][0]['HostPort'] == '55001'
        assert 'nano-regression' in status['NetworkSettings']['Networks']
        assert len(status['NetworkSettings']['Networks']) == 2
        state = json.loads((data / 'deployment.json').read_text())
        bridge = json.loads(run('docker', 'inspect', state['bridge'], capture=True).stdout)[0]
        assert bridge['Config']['User'] == '10001:10001'
        assert bridge['HostConfig']['ReadonlyRootfs']
        assert not bridge['HostConfig']['PortBindings']
        assert 'OPENAI_API_KEY' not in '\n'.join(bridge['Config']['Env'])
        run('docker', 'exec', name, 'python', '-c',
            'from nano_banana.core.config import AIConfigManager; '
            'c=AIConfigManager().load_config(); assert c["api_key"]=="dummy-test-not-a-real-key"; '
            'assert c["chat_engine"]=="api"')
        run(sys.executable, ROOT / 'deploy/update_nano_banana_codex.py', '--rollback', state['backup'])
        assert (data / 'config/ai_config.yaml').is_dir()
        assert (data / 'config/ai_config.yaml/old-directory-marker').is_file()
        old = json.loads(run('docker', 'inspect', name, capture=True).stdout)[0]
        assert old['State']['Running']
        assert not (old['Config'].get('Labels') or {}).get('io.nano-banana.deployment')
        assert not (data / 'deployment.json').exists()
        print('Deployment smoke PASS: directory conflict, keys/presets/ports/networks, isolated bridge, full rollback')
    finally:
        names = run('docker', 'ps', '-a', '--format', '{{.Names}}', capture=True).stdout.splitlines()
        for container in names:
            if container.startswith(name):
                run('docker', 'rm', '-f', container, check=False)
        run('docker', 'network', 'rm', name + '-codex-private', check=False)
        shutil.rmtree(root, ignore_errors=True)


if __name__ == '__main__':
    main()
