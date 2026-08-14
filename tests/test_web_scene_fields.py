import re
from pathlib import Path


def read_web_files():
    root = Path(__file__).parents[1]
    html = (root / "src" / "web" / "static" / "index.html").read_text(encoding="utf-8")
    script = (root / "src" / "web" / "static" / "script.js").read_text(encoding="utf-8")
    return root, html, script


def test_web_scene_form_includes_depth_in_all_data_flows():
    _, html, script = read_web_files()
    assert 'id="depth"' in html
    assert "depth: document.getElementById('depth')" in script
    assert '"景深": elements.depth.value' in script
    assert 'elements.depth.value = getValue(data, "场景", "背景", "景深")' in script
    assert "['depth', ['场景', '背景', '景深']]" in script


def test_web_negative_prompt_is_enabled_by_default_and_restored_on_clear():
    _, html, script = read_web_files()
    assert 'id="negativePromptEnabled" style="margin-right: 8px;" checked' in html
    assert '>水印、签名、文字</textarea>' in html
    assert "const DEFAULT_NEGATIVE_PROMPT = '水印、签名、文字';" in script
    assert "elements.negativePromptEnabled.checked = true;" in script
    assert "elements.negativePromptInput.value = DEFAULT_NEGATIVE_PROMPT;" in script


def test_web_subject_form_preserves_clothing_details_in_all_data_flows():
    _, html, script = read_web_files()
    assert 'id="clothingDetails"' in html
    assert "clothingDetails: document.getElementById('clothingDetails')" in script
    assert '"细节": elements.clothingDetails.value' in script
    assert 'elements.clothingDetails.value = getValue(data, "场景", "主体", "服装", "细节")' in script
    assert "['clothingDetails', ['场景', '主体', '服装', '细节']]" in script


def test_web_image_generation_controls_match_desktop_selection_flow():
    _, html, script = read_web_files()
    assert 'id="imageProviderSelect"' in html
    assert 'id="imageModelSelect"' in html
    assert 'id="imageProviderStatus"' in html
    assert 'id="imageProviderStatusButton"' in html
    assert 'id="imageProviderStatusPopover"' in html
    assert 'aria-describedby="imageProviderStatusPopover"' in html
    assert ".filter(([, config]) => config.is_configured)" in script
    assert "renderImageProviderStatus()" in script
    assert "尚未配置图片渠道，请点击右上角“设置”添加渠道密钥" in script
    assert "config.is_configured ? '已配置' : '未配置'" in script
    assert "elements.imageProviderStatusButton.hidden = configuredProviders.length === 0" in script
    assert "'/api/image-generation-settings'" in script
    assert "provider," in script
    assert "model," in script
    assert "updateImageGenerationAvailability()" in script


def test_web_uses_structured_prompt_workspace():
    root, html, _ = read_web_files()
    ui = (root / "src" / "web" / "static" / "structured-ui.js").read_text(encoding="utf-8")
    assert 'id="promptProgressText"' in html
    assert 'id="structurePreview"' in html
    assert 'class="field-option-manage"' in html
    assert "const categoryFields" in ui
    assert "`/api/options/${encodeURIComponent(fieldName)}`" in ui


def test_web_fields_use_one_editable_saved_option_list():
    root, _, script = read_web_files()
    ui = (root / "src" / "web" / "static" / "structured-ui.js").read_text(encoding="utf-8")
    assert "createEditableCombobox(control)" in ui
    assert "field-option-dropdown" in ui
    assert "updateFieldSuggestions" not in script
    assert "preset-suggest-select" not in script
    assert "field-suggestions" not in ui


def test_web_structured_fields_use_consistent_single_line_controls():
    _, html, _ = read_web_files()
    structured = html.split('id="tab-basic"', 1)[1].split('id="tab-advanced"', 1)[0]
    full_span_fields = set()
    for block in structured.split('class="form-group field-control full-span"')[1:]:
        marker = 'data-field-name="'
        full_span_fields.add(block.split(marker, 1)[1].split('"', 1)[0])
    assert full_span_fields == set()
    assert '<textarea' not in structured

def test_web_uses_two_columns_only_for_large_subject_category():
    _, html, _ = read_web_files()
    basic = html.split('id="tab-basic"', 1)[1].split('id="tab-scene"', 1)[0]
    scene = html.split('id="tab-scene"', 1)[1].split('id="tab-subject"', 1)[0]
    subject = html.split('id="tab-subject"', 1)[1].split('id="tab-camera"', 1)[0]
    camera = html.split('id="tab-camera"', 1)[1].split('id="tab-aesthetic"', 1)[0]
    aesthetic = html.split('id="tab-aesthetic"', 1)[1].split('id="tab-advanced"', 1)[0]

    assert 'class="form-grid form-grid-two-column"' in subject
    for category in (basic, scene, camera, aesthetic):
        assert 'class="form-grid"' in category
        assert 'form-grid-two-column' not in category
    assert '<input type="text" id="location" class="text-input">' in scene
    assert '<input type="text" id="background" class="text-input">' in scene
    assert '<input type="text" id="description" class="text-input">' in subject
    assert '<input type="text" id="materialRealism" class="text-input">' in aesthetic


def test_generation_preview_reserves_scrollbar_space_and_switches_once():
    root, _, _ = read_web_files()
    static = root / "src" / "web" / "static"
    style = (static / "style.css").read_text(encoding="utf-8")
    ui = (static / "structured-ui.js").read_text(encoding="utf-8")

    assert "scrollbar-gutter: stable" in style
    assert "if (hasGeneratedContent && !hadGeneratedContent)" in ui



def test_desktop_inspector_uses_remaining_viewport_height_without_page_scroll():
    root, _, _ = read_web_files()
    style = (root / "src" / "web" / "static" / "style.css").read_text(encoding="utf-8")

    inspector = re.search(r"\.inspector-panel\s*\{([^}]+)\}", style).group(1)
    preview = re.search(r"\.preview-area-row\s*\{([^}]+)\}", style).group(1)
    generation = re.search(r"\.generation-panel\s*\{([^}]+)\}", style).group(1)
    mobile = style.split("@media (max-width: 760px)", 1)[1]
    mobile_inspector = re.search(r"\.inspector-panel\s*\{([^}]+)\}", mobile).group(1)
    mobile_preview = re.search(r"\.preview-area-row\s*\{([^}]+)\}", mobile).group(1)

    assert "height: calc(100vh - var(--header-height))" in inspector
    assert "min-height: 0" in inspector
    assert "overflow: hidden" in inspector
    assert "flex: 1 1 auto" in preview
    assert "min-height: 0" in preview
    assert "max-height: none" in preview
    assert "flex: 0 0 auto" in generation
    assert "height: auto" in mobile_inspector
    assert "overflow: visible" in mobile_inspector
    assert "flex: none" in mobile_preview
    assert "min-height: 285px" in mobile_preview

def test_web_uses_readable_type_scale_and_consistent_category_controls():
    root, _, _ = read_web_files()
    style = (root / "src" / "web" / "static" / "style.css").read_text(encoding="utf-8")

    assert "--font-size-body: 14px;" in style
    assert "--font-size-label: 13px;" in style
    assert "--font-size-meta: 12px;" in style
    assert "--control-height: 40px;" in style
    assert ".category-preset-bar .select-input, .category-preset-bar .btn" in style
    assert "height: var(--control-height);" in style
    assert "min-height: var(--control-height);" in style
