from pathlib import Path

from nano_banana.core.schema import get_schema


def test_aesthetic_controls_use_precise_display_labels_with_compatible_keys():
    field = get_schema().get_field("specialEffects")
    assert field.label == "后期效果"
    assert field.widget_key == "特殊效果"
    assert get_schema().get_category("aesthetic").label == "调色与质感"

    web = (Path(__file__).parents[1] / "src" / "web" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    assert 'data-tab="aesthetic"' in web
    assert 'data-preset-label="调色与质感"' in web
    assert '<label for="specialEffects">后期效果' in web
