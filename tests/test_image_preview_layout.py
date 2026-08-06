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


if __name__ == "__main__":
    unittest.main()
