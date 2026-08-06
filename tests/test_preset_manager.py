import json
from pathlib import Path

from utils.preset_manager import PresetManager


def test_category_presets_are_separate_from_global_presets(tmp_path):
    manager = PresetManager(tmp_path)

    assert manager.save_preset("完整方案", {"风格模式": "写实"})
    assert manager.save_category_preset("basic", "写实基础", {"风格模式": "写实"})

    assert [item["name"] for item in manager.get_all_presets()] == ["完整方案"]
    assert [item["name"] for item in manager.get_category_presets("basic")] == ["写实基础"]
    assert manager.load_category_preset("basic", "写实基础") == {"风格模式": "写实"}


def test_category_presets_are_isolated_by_scope(tmp_path):
    manager = PresetManager(tmp_path)

    assert manager.save_category_preset("basic", "常用", {"风格模式": "插画"})
    assert manager.save_category_preset("scene", "常用", {"场景": {"环境": {"光线": "柔光"}}})

    assert manager.load_category_preset("basic", "常用") == {"风格模式": "插画"}
    assert manager.load_category_preset("scene", "常用") == {"场景": {"环境": {"光线": "柔光"}}}
    assert manager.delete_category_preset("basic", "常用")
    assert manager.load_category_preset("basic", "常用") is None
    assert manager.load_category_preset("scene", "常用") is not None


def test_category_scope_rejects_path_traversal(tmp_path):
    manager = PresetManager(tmp_path)

    assert not manager.save_category_preset("../outside", "bad", {"value": 1})
    assert manager.get_category_presets("../outside") == []


def test_bundled_hoshino_is_a_subject_preset():
    presets_dir = Path(__file__).parents[1] / "src" / "presets"
    old_global_preset = presets_dir / "中秋星野（仅角色）.json"
    subject_preset = presets_dir / "categories" / "subject" / "中秋星野.json"

    assert not old_global_preset.exists()
    assert subject_preset.exists()

    data = json.loads(subject_preset.read_text(encoding="utf-8"))
    subject = data["场景"]["主体"]
    assert subject["整体描述"]
    assert subject["表情与动作"]["动作"] == ""

    prompt_text = json.dumps(subject, ensure_ascii=False)
    for defining_feature in (
        "角色左眼湛蓝、角色右眼金橙",
        "粉色同心圆光环",
        "白兔造型发饰",
        "浅蓝色小鲸鱼吊坠",
        "蓝色蝴蝶结",
    ):
        assert defining_feature in prompt_text
    assert "漂浮的蓝色鲸鱼玩偶" not in prompt_text

def test_bundled_basic_presets_are_a_small_complete_default_set():
    presets_dir = (
        Path(__file__).parents[1] / "src" / "presets" / "categories" / "basic"
    )
    expected_names = {
        "现代精致动画",
        "精致游戏CG",
        "电影光影动画",
        "温暖日常动画",
        "清透轻小说插画",
        "半写实厚涂插画",
    }

    preset_files = list(presets_dir.glob("*.json"))
    assert {path.stem for path in preset_files} == expected_names

    for preset_file in preset_files:
        data = json.loads(preset_file.read_text(encoding="utf-8"))
        assert set(data) == {"风格模式", "画面气质"}
        assert all(isinstance(value, str) and value.strip() for value in data.values())

def test_bundled_scene_presets_are_a_small_complete_default_set():
    presets_dir = (
        Path(__file__).parents[1] / "src" / "presets" / "categories" / "scene"
    )
    expected_names = {
        "盛夏海边车站",
        "春日樱花坡道",
        "黄昏城市天台",
        "雨夜霓虹街道",
        "静谧星空湖畔",
        "暖光窗边房间",
    }

    preset_files = list(presets_dir.glob("*.json"))
    assert {path.stem for path in preset_files} == expected_names

    for preset_file in preset_files:
        data = json.loads(preset_file.read_text(encoding="utf-8"))
        scene = data["场景"]
        assert set(scene["环境"]) == {"地点设定", "光线", "天气氛围"}
        assert set(scene["背景"]) == {"描述", "景深"}
        assert all(value.strip() for value in scene["环境"].values())
        assert all(value.strip() for value in scene["背景"].values())


def test_bundled_camera_presets_are_a_small_complete_default_set():
    presets_dir = (
        Path(__file__).parents[1] / "src" / "presets" / "categories" / "camera"
    )
    expected_names = {
        "标准全身立绘",
        "半身角色特写",
        "横屏环境壁纸",
        "电影感叙事镜头",
        "动态仰视构图",
        "俯视氛围构图",
    }

    preset_files = list(presets_dir.glob("*.json"))
    assert {path.stem for path in preset_files} == expected_names

    for preset_file in preset_files:
        data = json.loads(preset_file.read_text(encoding="utf-8"))
        assert set(data) == {"相机"}
        assert set(data["相机"]) == {
            "机位角度",
            "构图",
            "镜头特性",
            "传感器画质",
        }
        assert all(value.strip() for value in data["相机"].values())

def test_bundled_aesthetic_presets_are_a_small_complete_default_set():
    presets_dir = (
        Path(__file__).parents[1] / "src" / "presets" / "categories" / "aesthetic"
    )
    expected_names = {
        "通透均衡",
        "柔光低对比",
        "电影冷暖调色",
        "低饱和情绪调色",
        "鲜明视觉强化",
    }

    preset_files = list(presets_dir.glob("*.json"))
    assert {path.stem for path in preset_files} == expected_names

    for preset_file in preset_files:
        data = json.loads(preset_file.read_text(encoding="utf-8"))
        aesthetic = data["审美控制"]
        assert set(aesthetic) == {"呈现意图", "材质真实度", "色彩风格"}
        assert isinstance(aesthetic["材质真实度"], list)
        assert all(value.strip() for value in aesthetic["材质真实度"])
        assert set(aesthetic["色彩风格"]) == {"整体色调", "对比度", "特殊效果"}
        assert aesthetic["呈现意图"].strip()
        assert all(value.strip() for value in aesthetic["色彩风格"].values())