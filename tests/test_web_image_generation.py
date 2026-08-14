import importlib.util
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

spec = importlib.util.spec_from_file_location(
    "nano_banana_web_app", SRC / "web" / "app.py"
)
web_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web_app)


class DummyImageClient:
    def __init__(self):
        self.options = None

    def set_generation_options(self, options):
        self.options = options

    def generate_image(self, text, images=None):
        return Image.new("RGB", (2, 2), "white")


class WebImageGenerationApiTests(unittest.TestCase):
    def setUp(self):
        self.client = web_app.app.test_client()

    def test_provider_metadata_exposes_availability_without_credentials(self):
        credentials = {
            "gemini": {
                "base_url": "https://gemini.example",
                "api_key": "secret-key",
                "model": "gemini-3-pro-image-preview",
            },
            "openai_images": {
                "base_url": "https://api.openai.com/v1",
                "api_key": "",
                "model": "gpt-image-2",
            },
            "qwen_image": {
                "base_url": "",
                "api_key": "qwen-key",
                "model": "qwen-image-3.0-pro",
            },
            "doubao_image": {
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "api_key": "doubao-key",
                "model": "doubao-seedream-5-0-pro-260628",
            },
        }
        with patch.object(
            web_app.config_manager,
            "get_image_provider_config",
            side_effect=lambda provider: credentials[provider],
        ):
            response = self.client.get("/api/image-providers")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["gemini"]["has_api_key"])
        self.assertTrue(data["gemini"]["is_configured"])
        self.assertFalse(data["openai_images"]["has_api_key"])
        self.assertFalse(data["qwen_image"]["is_configured"])
        self.assertTrue(data["doubao_image"]["is_configured"])
        self.assertNotIn("api_key", data["gemini"])
        self.assertIn("gemini-3-pro-image-preview", data["gemini"]["capabilities"])

    def test_web_settings_include_doubao_channel(self):
        html = (SRC / "web" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('value="doubao_image"', html)
        self.assertIn('id="configDoubaoImageBaseUrl"', html)
        self.assertIn('id="configDoubaoImageApiKey"', html)
        self.assertIn('id="configDoubaoImageModel"', html)

    def test_generation_error_state_wraps_full_message(self):
        script = (SRC / "web" / "static" / "script.js").read_text(encoding="utf-8")
        styles = (SRC / "web" / "static" / "style.css").read_text(encoding="utf-8")

        self.assertIn("errorState.className = 'generation-error';", script)
        self.assertIn("errorState.setAttribute('role', 'alert');", script)
        self.assertIn("elements.resultPreview.classList.add('has-error');", script)
        self.assertRegex(
            styles,
            re.compile(
                r"\.generation-error-message\s*\{[^}]*"
                r"overflow-wrap:\s*anywhere;[^}]*"
                r"white-space:\s*pre-wrap;",
                re.DOTALL,
            ),
        )
        self.assertRegex(
            styles,
            re.compile(
                r"\.result-preview\.has-error\s*\{[^}]*overflow:\s*visible;",
                re.DOTALL,
            ),
        )

    def test_generation_settings_are_scoped_by_provider_and_model(self):
        payload = {
            "provider": "qwen_image",
            "model": "qwen-image-3.0-pro",
            "options": {"aspect_ratio": "16:9", "image_size": "2K"},
        }
        with (
            patch.object(
                web_app.config_manager, "set_active_image_selection", return_value=True
            ) as save_selection,
            patch.object(
                web_app.config_manager, "save_image_generation_options", return_value=True
            ) as save_options,
        ):
            response = self.client.post(
                "/api/image-generation-settings", json=payload
            )

        self.assertEqual(response.status_code, 200)
        save_selection.assert_called_once_with("qwen_image", "qwen-image-3.0-pro")
        save_options.assert_called_once_with(
            "qwen_image", "qwen-image-3.0-pro", payload["options"]
        )

    def test_generate_image_uses_requested_provider_and_model_snapshot(self):
        credentials = {
            "base_url": "https://qwen.example/api/v1",
            "api_key": "qwen-key",
            "model": "stored-model",
        }
        image_client = DummyImageClient()
        with (
            patch.object(
                web_app.config_manager,
                "get_image_provider_config",
                return_value=credentials,
            ),
            patch.object(
                web_app.config_manager, "set_active_image_selection", return_value=True
            ),
            patch.object(
                web_app.config_manager, "save_image_generation_options", return_value=True
            ),
            patch.object(
                web_app,
                "create_image_provider_from_credentials",
                return_value=image_client,
            ) as create_client,
        ):
            response = self.client.post(
                "/api/generate-image",
                json={
                    "prompt": "test prompt",
                    "provider": "qwen_image",
                    "model": "requested-model",
                    "options": {"aspect_ratio": "16:9"},
                },
            )

        self.assertEqual(response.status_code, 200)
        create_client.assert_called_once_with(
            "qwen_image",
            "https://qwen.example/api/v1",
            "qwen-key",
            "requested-model",
        )
        self.assertEqual(image_client.options, {"aspect_ratio": "16:9"})

    def test_generate_image_returns_provider_error_verbatim(self):
        raw_error = (
            "豆包 Seedream 请求失败: Error code: 400 - {'error': {"
            "'code': 'OutputImageSensitiveContentDetected.PolicyViolation', "
            "'message': 'server message. Request id: request-123', "
            "'param': '', 'type': 'BadRequestError'}}"
        )

        class FailingImageClient(DummyImageClient):
            def generate_image(self, text, images=None):
                raise RuntimeError(raw_error)

        credentials = {
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "api_key": "doubao-key",
            "model": "doubao-seedream-5-0-pro-260628",
        }
        with (
            patch.object(
                web_app.config_manager,
                "get_image_provider_config",
                return_value=credentials,
            ),
            patch.object(
                web_app.config_manager, "set_active_image_selection", return_value=True
            ),
            patch.object(
                web_app.config_manager, "save_image_generation_options", return_value=True
            ),
            patch.object(
                web_app,
                "create_image_provider_from_credentials",
                return_value=FailingImageClient(),
            ),
        ):
            response = self.client.post(
                "/api/generate-image",
                json={
                    "prompt": "test prompt",
                    "provider": "doubao_image",
                    "model": "doubao-seedream-5-0-pro-260628",
                    "options": {},
                },
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["error"], raw_error)


if __name__ == "__main__":
    unittest.main()
