import os
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from PyQt6.QtGui import QColor, QPixmap
    from PyQt6.QtWidgets import QApplication
except ImportError:
    QApplication = None
else:
    from app import PromptGeneratorApp
    from utils.ai_config import AIConfigManager


@unittest.skipUnless(QApplication is not None, "PyQt6 is not installed")
class ImagePreviewLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_provider_combo_shows_only_channels_with_api_keys_and_falls_back(self):
        config = deepcopy(AIConfigManager.DEFAULT_CONFIG)
        config.update(
            {
                "image_provider": "gemini",
                "gemini_base_url": "https://gemini.example",
                "gemini_api_key": "gemini-key",
                "qwen_image_api_key": "qwen-key",
            }
        )
        with (
            patch.object(AIConfigManager, "load_config", return_value=config),
            patch.object(AIConfigManager, "save_config", return_value=True),
        ):
            window = PromptGeneratorApp()

            self.assertEqual(
                [
                    window.image_provider_combo.itemData(index)
                    for index in range(window.image_provider_combo.count())
                ],
                ["gemini", "qwen_image"],
            )
            self.assertEqual(window.image_provider_combo.currentData(), "gemini")
            self.assertEqual(window.image_config_status.text(), "")

            config["gemini_api_key"] = ""
            window._refresh_image_config_from_dialog()

            self.assertEqual(window.image_provider_combo.count(), 1)
            self.assertEqual(window.image_provider_combo.currentData(), "qwen_image")
            window.close()

    def test_provider_combo_has_disabled_empty_state_without_api_keys(self):
        config = deepcopy(AIConfigManager.DEFAULT_CONFIG)
        with (
            patch.object(AIConfigManager, "load_config", return_value=config),
            patch.object(AIConfigManager, "save_config", return_value=True),
        ):
            window = PromptGeneratorApp()

            self.assertEqual(window.image_provider_combo.count(), 1)
            self.assertIsNone(window.image_provider_combo.currentData())
            self.assertFalse(window.image_provider_combo.isEnabled())
            self.assertFalse(window.image_model_combo.isEnabled())
            self.assertFalse(window.generate_image_btn.isEnabled())
            self.assertIn("填写密钥", window.image_config_status.text())
            window.close()

    def test_image_options_use_a_compact_two_column_grid(self):
        config = deepcopy(AIConfigManager.DEFAULT_CONFIG)
        config.update(
            {
                "image_provider": "qwen_image",
                "qwen_image_api_key": "qwen-key",
            }
        )
        with (
            patch.object(AIConfigManager, "load_config", return_value=config),
            patch.object(AIConfigManager, "save_config", return_value=True),
        ):
            window = PromptGeneratorApp()

            positions = [
                window.image_options_layout.getItemPosition(index)
                for index in range(window.image_options_layout.count())
            ]
            self.assertEqual(
                positions,
                [
                    (0, 0, 1, 1),
                    (0, 1, 1, 1),
                    (1, 0, 1, 1),
                    (1, 1, 1, 1),
                ],
            )
            self.assertEqual(len(window.image_option_widgets), 4)
            window.close()

    def test_preview_image_fits_inside_canvas_at_minimum_window_size(self):
        config = deepcopy(AIConfigManager.DEFAULT_CONFIG)
        with (
            patch.object(AIConfigManager, "load_config", return_value=config),
            patch.object(AIConfigManager, "save_config", return_value=True),
        ):
            window = PromptGeneratorApp()
            window.resize(window.minimumSize())
            window.show()
            self.app.processEvents()

            source = QPixmap(1600, 900)
            source.fill(QColor("red"))
            window.preview_area.setSourcePixmap(source)
            self.app.processEvents()

            preview = window.preview_area
            canvas = preview.parentWidget()
            displayed = preview.pixmap()

            self.assertTrue(
                canvas.contentsRect().contains(preview.geometry()),
                f"preview {preview.geometry()} overflows canvas {canvas.contentsRect()}",
            )
            self.assertGreaterEqual(preview.contentsRect().height(), 120)
            self.assertLessEqual(displayed.width(), preview.contentsRect().width())
            self.assertLessEqual(displayed.height(), preview.contentsRect().height())

            window.close()

    def test_long_generation_error_does_not_collapse_main_splitter(self):
        config = deepcopy(AIConfigManager.DEFAULT_CONFIG)
        with (
            patch.object(AIConfigManager, "load_config", return_value=config),
            patch.object(AIConfigManager, "save_config", return_value=True),
        ):
            window = PromptGeneratorApp()
            window.resize(1400, 900)
            window.show()
            self.app.processEvents()

            splitter_sizes_before = window.main_splitter.sizes()
            error_message = (
                "ContentFilterError.IntentDetected.PolicyViolation: "
                + "x" * 800
                + "; Request id: 021786687661009b75b42a52114d75a63a7057f0ece04dd564b0c"
            )

            window._on_generation_error(error_message)
            self.app.processEvents()

            splitter_sizes_after = window.main_splitter.sizes()
            self.assertGreater(
                splitter_sizes_after[0],
                splitter_sizes_before[0] * 0.8,
                f"long status text collapsed splitter: {splitter_sizes_before} -> {splitter_sizes_after}",
            )
            self.assertEqual(
                window.image_status_label.text(),
                "\u751f\u6210\u5931\u8d25\uff0c\u60ac\u505c\u67e5\u770b\u9519\u8bef\u8be6\u60c5",
            )
            self.assertEqual(window.image_status_label.toolTip(), error_message)
            window.close()


if __name__ == "__main__":
    unittest.main()
