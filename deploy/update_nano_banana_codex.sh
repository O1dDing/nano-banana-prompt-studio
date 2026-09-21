#!/usr/bin/env bash
# Debian 12: verified updater; --configure-access prompts for team/AUD/admins.
set -Eeuo pipefail
umask 077
if [[ ${EUID} -ne 0 ]]; then
    echo '请使用 sudo bash，或在 root 终端运行。' >&2
    exit 1
fi
for tool in curl python3 git docker; do
    command -v "$tool" >/dev/null 2>&1 || { echo "缺少命令：$tool" >&2; exit 1; }
done
# Only the updater is pinned. It deploys current main unless --ref is supplied.
SOURCE_COMMIT='5c2695ca19c0bf7ac91dd46268c9afee1cc51b92'
EXPECTED_BLOB='206ee7713ed769b862749b60073abf1aa3e749b7'
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
UPDATER="${SCRIPT_DIR}/update_nano_banana_codex-${SOURCE_COMMIT:0:12}.py"
TEMP_FILE="$(mktemp "${SCRIPT_DIR}/.nano-codex-updater.XXXXXX")"
trap 'rm -f -- "$TEMP_FILE"' EXIT
curl --fail --location --proto '=https' --tlsv1.2 --retry 3 --connect-timeout 20 --max-time 180 \
  "https://raw.githubusercontent.com/O1dDing/nano-banana-prompt-studio/${SOURCE_COMMIT}/deploy/update_nano_banana_codex.py" \
  --output "$TEMP_FILE"
python3 - "$TEMP_FILE" "$EXPECTED_BLOB" <<'PY'
import hashlib
from pathlib import Path
import sys
raw = Path(sys.argv[1]).read_bytes()
actual = hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()
if actual != sys.argv[2]:
    raise SystemExit('更新器内容校验失败；未执行，也未停止旧服务。')
compile(raw, 'update_nano_banana_codex.py', 'exec')
print('Access 更新器版本和 Python 语法校验通过。', flush=True)
PY
mv -fT -- "$TEMP_FILE" "$UPDATER"
chmod 600 "$UPDATER"
trap - EXIT
exec python3 "$UPDATER" "$@"
