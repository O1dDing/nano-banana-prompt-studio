import builtins
import importlib.util
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "nano_access_updater", ROOT / "deploy" / "update_nano_banana_codex.py"
)
UPDATER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UPDATER)


class KeepOpen(io.StringIO):
    def __exit__(self, *_args):
        return False

    def close(self):
        pass


def test_configure_access_uses_separate_nonseekable_tty_streams(tmp_path, monkeypatch):
    reader = KeepOpen(
        "myteam.cloudflareaccess.com\n"
        "audience-tag\n"
        "admin1@example.com,admin2@example.com\n"
        "\n"
        "YES\n"
    )
    writer = KeepOpen()
    real_open = builtins.open
    modes = []

    def fake_open(path, mode="r", *args, **kwargs):
        if path == "/dev/test-tty":
            modes.append(mode)
            if mode == "r":
                return reader
            if mode == "w":
                return writer
            raise AssertionError(f"non-seekable TTY opened with unsupported mode: {mode}")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    pending = UPDATER.configure_access(tmp_path, tty_path="/dev/test-tty")
    try:
        data = json.loads(pending.read_text())
        assert modes == ["r", "w"]
        assert data["issuer"] == "https://myteam.cloudflareaccess.com"
        assert data["audiences"] == ["audience-tag"]
        assert data["admin_emails"] == ["admin1@example.com", "admin2@example.com"]
        assert data["admin_subjects"] == []
    finally:
        pending.unlink(missing_ok=True)
