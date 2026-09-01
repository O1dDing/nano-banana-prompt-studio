from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src" / "web" / "static" / "script.js"


def test_drafts_are_saved_per_tab_with_legacy_migration():
    script = SCRIPT.read_text(encoding="utf-8")
    assert "sessionStorage.setItem(\n            DRAFT_STORAGE_KEY" in script
    assert "let raw = sessionStorage.getItem(DRAFT_STORAGE_KEY);" in script
    assert "raw = localStorage.getItem(DRAFT_STORAGE_KEY);" in script
    assert "localStorage.removeItem(DRAFT_STORAGE_KEY);" in script
    assert "localStorage.setItem(\n            DRAFT_STORAGE_KEY" not in script
