from pathlib import Path

from nano_banana.core.schema import default_negative_prompt


def test_desktop_negative_prompt_is_enabled_by_default_and_restored_on_clear():
    source = (
        Path(__file__).parents[1]
        / "src"
        / "nano_banana"
        / "desktop"
        / "app.py"
    ).read_text(encoding="utf-8")

    assert "DEFAULT_NEGATIVE_PROMPT = default_negative_prompt()" in source
    assert default_negative_prompt() == "水印、签名、文字"
    assert "self.negative_prompt_enabled.setChecked(True)" in source
    assert "self.negative_prompt_input.set_value(DEFAULT_NEGATIVE_PROMPT)" in source
    assert "self.negative_group.setVisible(True)" in source
