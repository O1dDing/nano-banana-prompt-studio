import sys
import tempfile
import types
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    import openai  # noqa: F401
except ImportError:
    openai_stub = types.ModuleType("openai")
    openai_stub.OpenAI = object
    sys.modules["openai"] = openai_stub

try:
    import loguru  # noqa: F401
except ImportError:
    loguru_stub = types.ModuleType("loguru")
    loguru_stub.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    sys.modules["loguru"] = loguru_stub

try:
    from PIL import Image  # noqa: F401
except ImportError:
    pil_stub = types.ModuleType("PIL")
    image_stub = types.SimpleNamespace(Image=object)
    pil_stub.Image = image_stub
    sys.modules["PIL"] = pil_stub

from components.image_clients import get_image_provider_capabilities
from components.image_provider_config import IMAGE_PROVIDER_META
from utils.ai_config import AIConfigManager


class AIConfigManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = AIConfigManager()
        self.manager.config_path = Path(self.temp_dir.name) / "ai_config.yaml"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, data):
        self.manager.config_path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def test_chat_and_openai_images_configs_are_isolated(self):
        self._write(
            {
                "base_url": "https://chat.example/v1",
                "api_key": "chat-key",
                "model": "chat-model",
                "image_provider": "openai_images",
                "openai_image_base_url": "https://images.example/v1",
                "openai_image_api_key": "image-key",
                "openai_image_model": "image-model",
            }
        )

        self.assertEqual(self.manager.get_chat_config()["api_key"], "chat-key")
        self.assertEqual(
            self.manager.get_image_provider_config("openai_images")["api_key"],
            "image-key",
        )

        self.manager.set_active_image_selection("openai_images", "new-image-model")
        self.assertEqual(self.manager.get_chat_config()["model"], "chat-model")
        self.assertEqual(
            self.manager.get_image_provider_config("openai_images")["model"],
            "new-image-model",
        )

    def test_generation_options_are_scoped_by_provider_and_model(self):
        self.manager.save_image_generation_options(
            "gemini",
            "model-a",
            {"aspect_ratio": "16:9", "image_size": "4K"},
        )
        self.manager.save_image_generation_options(
            "gemini",
            "model-b",
            {"aspect_ratio": "1:1", "image_size": "1K"},
        )

        self.assertEqual(
            self.manager.get_image_generation_options("gemini", "model-a")["image_size"],
            "4K",
        )
        self.assertEqual(
            self.manager.get_image_generation_options("gemini", "model-b")["image_size"],
            "1K",
        )
        self.assertEqual(
            self.manager.get_image_generation_options("openai_images", "model-a"),
            {},
        )

    def test_image_provider_requires_complete_connection(self):
        self._write(
            {
                "gemini_api_key": "image-key",
                "gemini_model": "gemini-model",
                "gemini_base_url": "",
            }
        )
        self.assertFalse(self.manager.is_image_provider_configured("gemini"))

        self.manager.save_config({"gemini_base_url": "https://gemini.example"})
        self.assertTrue(self.manager.is_image_provider_configured("gemini"))

    def test_image_provider_choices_include_only_non_empty_api_keys(self):
        self._write(
            {
                "gemini_api_key": " gemini-key ",
                "openai_image_api_key": "   ",
                "qwen_image_api_key": "qwen-key",
                "doubao_image_api_key": "doubao-key",
            }
        )

        self.assertEqual(
            self.manager.get_image_providers_with_api_key(),
            ["gemini", "qwen_image", "doubao_image"],
        )

    def test_model_capability_override_does_not_mutate_provider_defaults(self):
        model = "test-model-with-override"
        IMAGE_PROVIDER_META["gemini"].setdefault("model_capabilities", {})[model] = {
            "options": {
                "image_size": {"values": ["1K"], "default": "1K"},
                "thinking_level": None,
            }
        }
        try:
            resolved = get_image_provider_capabilities("gemini", model)
            defaults = get_image_provider_capabilities("gemini")
        finally:
            IMAGE_PROVIDER_META["gemini"]["model_capabilities"].pop(model)

        self.assertEqual(resolved["options"]["image_size"]["values"], ["1K"])
        self.assertNotIn("thinking_level", resolved["options"])
        self.assertIn("thinking_level", defaults["options"])

    def test_qwen_exposes_only_supported_model_and_hides_watermark(self):
        self.assertEqual(
            IMAGE_PROVIDER_META["qwen_image"]["model_suggestions"],
            ["qwen-image-3.0-pro"],
        )
        qwen_options = get_image_provider_capabilities("qwen_image")["options"]
        self.assertNotIn("watermark", qwen_options)

    def test_doubao_defaults_and_generation_options(self):
        credentials = self.manager.get_image_provider_config("doubao_image")
        self.assertEqual(
            credentials["base_url"],
            "https://ark.cn-beijing.volces.com/api/v3",
        )
        self.assertEqual(
            credentials["model"],
            "doubao-seedream-5-0-pro-260628",
        )

        options = get_image_provider_capabilities("doubao_image")["options"]
        self.assertEqual(options["image_size"]["values"], ["1K", "1.5K", "2K"])
        self.assertEqual(options["output_format"]["values"], ["png", "jpeg"])
        self.assertEqual(options["watermark"]["default"], "false")


if __name__ == "__main__":
    unittest.main()
