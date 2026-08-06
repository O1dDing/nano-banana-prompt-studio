from pathlib import Path


def test_desktop_negative_prompt_is_enabled_by_default_and_restored_on_clear():
    root = Path(__file__).parents[1]
    source = (root / "src" / "app.py").read_text(encoding="utf-8")

    assert 'DEFAULT_NEGATIVE_PROMPT = "水印、签名、文字"' in source
    assert "self.negative_prompt_enabled.setChecked(True)" in source
    assert "self.negative_prompt_input.set_value(DEFAULT_NEGATIVE_PROMPT)" in source
    assert "self.negative_group.setVisible(True)" in source
