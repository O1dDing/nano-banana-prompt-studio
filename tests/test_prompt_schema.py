import os
import subprocess
import sys
from pathlib import Path

from nano_banana.core.prompt_doc import apply_partial, flatten, nest, subset
from nano_banana.core.schema import get_schema


def test_schema_has_expected_categories_and_web_ids():
    schema = get_schema()
    assert schema.category_ids == ("basic", "scene", "subject", "camera", "aesthetic")
    assert "depth" in schema.field_ids
    assert "clothingDetails" in schema.field_ids
    assert schema.get_field("specialEffects").label == "后期效果"
    assert schema.get_field("specialEffects").widget_key == "特殊效果"
    assert schema.get_field("background").path == ("场景", "背景", "描述")


def test_nest_flatten_roundtrip_and_string_list():
    schema = get_schema()
    flat = {field.id: "值" for field in schema.iter_fields()}
    flat["materialRealism"] = "皮肤, 头发"
    nested = nest(flat, schema)
    assert nested["风格模式"] == "值"
    assert nested["场景"]["背景"]["景深"] == "值"
    assert nested["场景"]["主体"]["服装"]["细节"] == "值"
    assert nested["审美控制"]["材质真实度"] == ["皮肤", "头发"]
    back = flatten(nested, schema)
    assert back["depth"] == "值"
    assert back["clothingDetails"] == "值"
    assert back["materialRealism"] == "皮肤, 头发"


def test_subset_only_keeps_one_category():
    data = nest({"styleMode": "插画", "atmosphere": "清透", "location": "海边"}, include_empty=True)
    sliced = subset(data, "basic")
    assert sliced == {"风格模式": "插画", "画面气质": "清透"}
    assert "场景" not in sliced


def test_apply_partial_does_not_clobber_missing_keys():
    dst = {"风格模式": "A", "画面气质": "B", "场景": {"环境": {"光线": "旧"}}}
    src = {"画面气质": "C", "场景": {"环境": {"天气氛围": "雨"}}}
    merged = apply_partial(dst, src)
    assert merged["风格模式"] == "A"
    assert merged["画面气质"] == "C"
    assert merged["场景"]["环境"]["光线"] == "旧"
    assert merged["场景"]["环境"]["天气氛围"] == "雨"


def test_system_prompt_contains_schema_example_json():
    from nano_banana.core.prompts import SYSTEM_PROMPT, build_system_prompt_example

    example = build_system_prompt_example()
    assert '"风格模式"' in example
    assert '"景深"' in example
    assert example in SYSTEM_PROMPT


def test_importing_schema_does_not_load_image_providers():
    code = (
        "import sys\n"
        "from nano_banana.core.schema import get_schema\n"
        "assert get_schema().get_field('depth').id == 'depth'\n"
        "assert 'openai' not in sys.modules\n"
        "assert 'nano_banana.core.images.doubao' not in sys.modules\n"
        "assert 'nano_banana.core.config' not in sys.modules\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
    )
    assert result.returncode == 0, result.stderr or result.stdout
