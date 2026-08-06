import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    QApplication = None
else:
    from components.tag_text_input import TagTextInput, normalize_negative_prompt


@unittest.skipUnless(QApplication is not None, "PyQt6 is not installed")
class TagTextInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tag_fills_input_without_duplicating_it(self):
        widget = TagTextInput("反向提示词标签", ["水印、签名、文字"])

        widget._apply_tag("水印、签名、文字")
        widget._apply_tag("水印、签名、文字")

        self.assertEqual(widget.get_value(), "水印、签名、文字")

    def test_tag_is_added_from_the_dedicated_input(self):
        yaml_handler = Mock()
        widget = TagTextInput("反向提示词标签", [], yaml_handler=yaml_handler)
        widget.set_value("已有反向提示词")
        widget.tag_input.setText("低清晰度")

        widget._add_new_tag()

        self.assertEqual(widget._options, ["低清晰度"])
        self.assertEqual(widget.get_value(), "已有反向提示词")
        self.assertEqual(widget.tag_input.text(), "")
        yaml_handler.add_option.assert_called_once_with("反向提示词标签", "低清晰度")

    def test_tag_can_be_deleted(self):
        yaml_handler = Mock()
        widget = TagTextInput(
            "反向提示词标签", ["水印、签名、文字"], yaml_handler=yaml_handler
        )

        widget._delete_tag("水印、签名、文字")

        self.assertEqual(widget._options, [])
        yaml_handler.remove_option.assert_called_once_with(
            "反向提示词标签", "水印、签名、文字"
        )

    def test_legacy_negative_prompt_groups_are_joined(self):
        value = normalize_negative_prompt(
            {"禁止元素": ["水印", "文字"], "禁止风格": ["模糊"]}
        )

        self.assertEqual(value, "水印, 文字, 模糊")


if __name__ == "__main__":
    unittest.main()
