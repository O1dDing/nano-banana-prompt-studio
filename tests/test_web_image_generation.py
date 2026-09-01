import importlib.util
import re
import sys
import time
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
        web_app.app.config["TESTING"] = True
        self.client = web_app.app.test_client()

    def wait_for_task(self, task_id, terminal=("completed", "failed", "cancelled")):
        for _ in range(300):
            response = self.client.get(f"/api/generate-image/status/{task_id}")
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            if data["status"] in terminal:
                return data
            time.sleep(0.01)
        self.fail(f"task {task_id} did not finish")

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

    def test_web_settings_include_custom_and_doubao_controls(self):
        html = (SRC / "web" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('value="doubao_image"', html)
        self.assertIn('id="configDoubaoImageBaseUrl"', html)
        self.assertIn('id="configChatWebSearchMode"', html)
        self.assertIn('value="disabled"', html)
        self.assertIn('value="auto"', html)
        self.assertIn('value="force"', html)

    def test_generation_error_state_wraps_full_message(self):
        script = (SRC / "web" / "static" / "image-gen.js").read_text(encoding="utf-8")
        styles = (SRC / "web" / "static" / "style.css").read_text(encoding="utf-8")

        self.assertIn("errorState.className = 'generation-error';", script)
        self.assertIn("errorState.setAttribute('role', 'alert');", script)
        self.assertIn("elements.resultPreview.classList.add('has-error');", script)
        self.assertIn("waitForImageTask", script)
        self.assertIn("/api/generate-image/cancel/", script)
        self.assertRegex(
            styles,
            re.compile(
                r"\.generation-error-message\s*\{[^}]*"
                r"overflow-wrap:\s*anywhere;[^}]*"
                r"white-space:\s*pre-wrap;",
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
            patch(
                "nano_banana.web.blueprints.images.create_image_provider_from_credentials",
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
            self.assertEqual(response.status_code, 202)
            task_id = response.get_json()["task_id"]
            result = self.wait_for_task(task_id)

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["image"].startswith("data:image/png;base64,"))
        create_client.assert_called_once_with(
            "qwen_image",
            "https://qwen.example/api/v1",
            "qwen-key",
            "requested-model",
        )
        self.assertEqual(image_client.options, {"aspect_ratio": "16:9"})

    def test_generate_image_returns_provider_error_verbatim_via_status(self):
        raw_error = (
            "豆包 Seedream 请求失败: Error code: 400 - {'error': {"
            "'code': 'OutputImageSensitiveContentDetected.PolicyViolation', "
            "'message': 'server message. Request id: request-123'}}"
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
            patch(
                "nano_banana.web.blueprints.images.create_image_provider_from_credentials",
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
            self.assertEqual(response.status_code, 202)
            result = self.wait_for_task(response.get_json()["task_id"])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"], raw_error)

    def test_capacity_and_unknown_task_endpoints(self):
        capacity = self.client.get("/api/generate-image/capacity")
        self.assertEqual(capacity.status_code, 200)
        self.assertGreaterEqual(capacity.get_json()["workers"], 1)
        self.assertEqual(
            self.client.get("/api/generate-image/status/not-found").status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/api/generate-image/cancel/not-found").status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
