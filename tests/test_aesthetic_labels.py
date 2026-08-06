from pathlib import Path


def test_aesthetic_controls_use_precise_display_labels_with_compatible_keys():
    root = Path(__file__).parents[1]
    desktop = (root / "src" / "app.py").read_text(encoding="utf-8")
    web = (root / "src" / "web" / "static" / "index.html").read_text(
        encoding="utf-8"
    )

    assert 'FieldGroup("调色与质感", color_class="aesthetic")' in desktop
    assert '_add_field(aesthetic_group, "后期效果", "特殊效果")' in desktop
    assert '_add_category_preset_controls(aesthetic_group, "aesthetic", "调色与质感")' in desktop
    assert 'data-tab="aesthetic">调色与质感</button>' in web
    assert 'data-preset-label="调色与质感"' in web
    assert '<label for="specialEffects">后期效果</label>' in web
