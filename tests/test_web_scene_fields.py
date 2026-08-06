from pathlib import Path


def test_web_scene_form_includes_depth_in_all_data_flows():
    root = Path(__file__).parents[1]
    html = (root / "src" / "web" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    script = (root / "src" / "web" / "static" / "script.js").read_text(
        encoding="utf-8"
    )

    assert 'id="depth"' in html
    assert "depth: document.getElementById('depth')" in script
    assert '"景深": elements.depth.value' in script
    assert 'elements.depth.value = getValue(data, "场景", "背景", "景深")' in script
    assert "['depth', ['场景', '背景', '景深']]" in script


def test_web_negative_prompt_is_enabled_by_default_and_restored_on_clear():
    root = Path(__file__).parents[1]
    html = (root / "src" / "web" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    script = (root / "src" / "web" / "static" / "script.js").read_text(
        encoding="utf-8"
    )

    assert 'id="negativePromptEnabled" style="margin-right: 8px;" checked' in html
    assert '>水印、签名、文字</textarea>' in html
    assert "const DEFAULT_NEGATIVE_PROMPT = '水印、签名、文字';" in script
    assert "elements.negativePromptEnabled.checked = true;" in script
    assert "elements.negativePromptInput.value = DEFAULT_NEGATIVE_PROMPT;" in script
    assert 'depth: ["场景", "背景", "景深"]' in script
