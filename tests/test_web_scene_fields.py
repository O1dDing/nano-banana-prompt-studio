"""Schema 契约：桌面控件 key / Web DOM id 必须跟 schema.yaml 对齐。"""
import re
from pathlib import Path

from nano_banana.core.schema import default_negative_prompt, get_schema


ROOT = Path(__file__).parents[1]


def test_desktop_form_is_schema_driven():
    desktop = (ROOT / "src" / "nano_banana" / "desktop" / "form_panel.py").read_text(
        encoding="utf-8"
    )
    assert "add_schema_field_groups" in desktop
    app = (ROOT / "src" / "nano_banana" / "desktop" / "app.py").read_text(encoding="utf-8")
    assert "add_schema_field_groups(self, layout)" in app
    assert "class PromptGeneratorApp(ImageGenController, QMainWindow)" in app
    image_gen = (ROOT / "src" / "nano_banana" / "desktop" / "image_gen.py").read_text(
        encoding="utf-8"
    )
    assert "class ImageGenController" in image_gen
    assert "nest(flat, self.prompt_schema)" in app
    assert "subset(self._collect_form_data(), scope, self.prompt_schema)" in app


def test_web_uses_schema_api_and_prompt_doc():
    html = (ROOT / "src" / "web" / "static" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "src" / "web" / "static" / "script.js").read_text(encoding="utf-8")
    schema_js = (ROOT / "src" / "web" / "static" / "schema-form.js").read_text(encoding="utf-8")
    ui = (ROOT / "src" / "web" / "static" / "structured-ui.js").read_text(encoding="utf-8")

    assert 'src="/static/schema-form.js"' in html
    assert 'src="/static/image-gen.js"' in html
    assert 'src="/static/ai-stream.js"' in html
    assert "/api/schema" in schema_js
    assert "PromptDoc.nestFromElements" in script
    assert "hydrateFromSchema" in ui
    assert get_schema().get_field("depth").id == "depth"
    assert get_schema().get_field("clothingDetails").widget_key == "服装细节"


def test_web_and_desktop_field_ids_match_schema():
    schema = get_schema()
    html = (ROOT / "src" / "web" / "static" / "index.html").read_text(encoding="utf-8")
    for field in schema.iter_fields():
        assert f'id="{field.id}"' in html
        assert f'data-field-name="{field.widget_key}"' in html or f'data-field-name="{field.label}"' in html


def test_negative_prompt_default_comes_from_schema():
    assert default_negative_prompt() == "水印、签名、文字"
    app = (ROOT / "src" / "nano_banana" / "desktop" / "app.py").read_text(encoding="utf-8")
    html = (ROOT / "src" / "web" / "static" / "index.html").read_text(encoding="utf-8")
    assert "DEFAULT_NEGATIVE_PROMPT = default_negative_prompt()" in app
    assert "self.negative_prompt_enabled.setChecked(True)" in app
    assert 'id="negativePromptEnabled"' in html
    assert "checked" in html.split('id="negativePromptEnabled"', 1)[1].split(">", 1)[0]


def test_aesthetic_label_is_declared_in_schema():
    field = get_schema().get_field("specialEffects")
    assert field.label == "后期效果"
    html = (ROOT / "src" / "web" / "static" / "index.html").read_text(encoding="utf-8")
    assert '<label for="specialEffects">后期效果' in html


def test_web_structured_layout_still_uses_single_line_controls():
    html = (ROOT / "src" / "web" / "static" / "index.html").read_text(encoding="utf-8")
    structured = html.split('id="tab-basic"', 1)[1].split('id="tab-advanced"', 1)[0]
    assert "<textarea" not in structured
    subject = html.split('id="tab-subject"', 1)[1].split('id="tab-camera"', 1)[0]
    assert 'class="form-grid form-grid-two-column"' in subject


def test_generation_preview_css_keeps_stable_scrollbar():
    style = (ROOT / "src" / "web" / "static" / "style.css").read_text(encoding="utf-8")
    ui = (ROOT / "src" / "web" / "static" / "structured-ui.js").read_text(encoding="utf-8")
    assert "scrollbar-gutter: stable" in style
    assert "if (hasGeneratedContent && !hadGeneratedContent)" in ui

    inspector = re.search(r"\.inspector-panel\s*\{([^}]+)\}", style).group(1)
    assert "height: calc(100vh - var(--header-height))" in inspector
