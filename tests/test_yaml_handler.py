import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from utils.yaml_handler import YamlHandler


class YamlHandlerTests(unittest.TestCase):
    def test_old_config_gets_the_default_negative_prompt_tag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            handler = YamlHandler()
            handler.config_path = Path(temp_dir) / "options.yaml"
            handler.save_options({"禁止元素": ["旧选项"]})

            self.assertEqual(
                handler.get_field_options("反向提示词标签"),
                ["水印、签名、文字"],
            )

    def test_saved_negative_prompt_tags_override_the_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            handler = YamlHandler()
            handler.config_path = Path(temp_dir) / "options.yaml"
            handler.save_options({"反向提示词标签": ["自定义标签"]})

            self.assertEqual(
                handler.get_field_options("反向提示词标签"),
                ["自定义标签"],
            )

    def test_first_custom_tag_keeps_the_default_for_old_configs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            handler = YamlHandler()
            handler.config_path = Path(temp_dir) / "options.yaml"
            handler.save_options({"禁止元素": ["旧选项"]})

            handler.add_option("反向提示词标签", "自定义标签")

            self.assertEqual(
                handler.get_field_options("反向提示词标签"),
                ["水印、签名、文字", "自定义标签"],
            )

    def test_default_tag_can_be_deleted_from_an_old_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            handler = YamlHandler()
            handler.config_path = Path(temp_dir) / "options.yaml"
            handler.save_options({"禁止元素": ["旧选项"]})

            handler.remove_option("反向提示词标签", "水印、签名、文字")

            self.assertEqual(handler.get_field_options("反向提示词标签"), [])


if __name__ == "__main__":
    unittest.main()
