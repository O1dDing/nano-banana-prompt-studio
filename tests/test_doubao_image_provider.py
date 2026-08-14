import base64
import json
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import httpx
from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from components.image_clients import (  # noqa: E402
    DoubaoImageProvider,
    create_image_provider_from_credentials,
)


class DoubaoImageProviderTests(unittest.TestCase):
    def _create_provider(self, base_url="https://ark.cn-beijing.volces.com/api/v3"):
        return DoubaoImageProvider(
            base_url=base_url,
            api_key="test-key",
            model="doubao-seedream-5-0-pro-260628",
        )

    def test_full_generation_endpoint_is_normalized_to_openai_base_url(self):
        provider = self._create_provider(
            "https://ark.cn-beijing.volces.com/api/v3/images/generations"
        )

        self.assertEqual(
            provider.base_url,
            "https://ark.cn-beijing.volces.com/api/v3",
        )

    def test_request_kwargs_include_seedream_options_and_local_reference(self):
        provider = self._create_provider()
        provider.set_generation_options(
            {
                "aspect_ratio": "16:9",
                "image_size": "2K",
                "output_format": "jpeg",
                "watermark": "true",
                "optimize_prompt_mode": "fast",
                "unsupported": "ignored",
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "reference.png"
            image_path.write_bytes(b"reference-bytes")
            kwargs = provider._build_request_kwargs("test prompt", [str(image_path)])

        self.assertEqual(kwargs["model"], "doubao-seedream-5-0-pro-260628")
        self.assertEqual(kwargs["prompt"], "test prompt")
        self.assertEqual(kwargs["size"], "2816x1584")
        self.assertEqual(kwargs["output_format"], "jpeg")
        self.assertEqual(kwargs["response_format"], "b64_json")
        self.assertTrue(kwargs["extra_body"]["watermark"])
        self.assertEqual(
            kwargs["extra_body"]["optimize_prompt_options"],
            {"mode": "fast"},
        )
        self.assertTrue(
            kwargs["extra_body"]["image"].startswith("data:image/png;base64,")
        )

    def test_generate_image_parses_base64_response(self):
        provider = self._create_provider()
        image_buffer = BytesIO()
        Image.new("RGB", (3, 2), "white").save(image_buffer, format="PNG")
        response = SimpleNamespace(
            data=[
                SimpleNamespace(
                    b64_json=base64.b64encode(image_buffer.getvalue()).decode("ascii"),
                    url=None,
                )
            ]
        )
        provider.client = SimpleNamespace(
            images=SimpleNamespace(generate=lambda **_kwargs: response)
        )

        generated = provider.generate_image("test prompt")

        self.assertIsNotNone(generated)
        self.assertEqual(generated.size, (3, 2))

    def test_api_error_preserves_server_response_details(self):
        provider = self._create_provider()

        request_id = "0217866875428522f7309b89ef4aa83d5a6323dac40bcdef47e0e"
        error_body = {
            "error": {
                "code": "OutputImageSensitiveContentDetected.PolicyViolation",
                "message": (
                    "The request failed because the output image may be related "
                    f"to copyright restrictions. Request id: {request_id}"
                ),
                "param": "",
                "type": "BadRequestError",
            }
        }

        http_client = httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(400, json=error_body)
            )
        )
        provider.client = OpenAI(
            api_key="test-key",
            base_url=provider.base_url,
            http_client=http_client,
        )
        try:
            with self.assertRaises(RuntimeError) as caught:
                provider.generate_image("test prompt")
        finally:
            provider.client.close()

        error_text = str(caught.exception)
        self.assertIn("Error code: 400", error_text)
        self.assertIn(error_body["error"]["code"], error_text)
        self.assertIn(error_body["error"]["message"], error_text)
        self.assertIn("'param': ''", error_text)
        self.assertIn("'type': 'BadRequestError'", error_text)
        self.assertIn(request_id, error_text)
        self.assertNotIn("请移除作品名", error_text)

    def test_openai_sdk_serializes_doubao_request_body(self):
        provider = self._create_provider()
        provider.set_generation_options(
            {
                "aspect_ratio": "4:3",
                "image_size": "1.5K",
                "output_format": "png",
                "watermark": "false",
                "optimize_prompt_mode": "standard",
            }
        )
        image_buffer = BytesIO()
        Image.new("RGB", (1, 1), "white").save(image_buffer, format="PNG")
        captured = {}

        def handle_request(request):
            captured["path"] = request.url.path
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "b64_json": base64.b64encode(
                                image_buffer.getvalue()
                            ).decode("ascii")
                        }
                    ]
                },
            )

        http_client = httpx.Client(transport=httpx.MockTransport(handle_request))
        provider.client = OpenAI(
            api_key="test-key",
            base_url=provider.base_url,
            http_client=http_client,
        )
        try:
            generated = provider.generate_image(
                "test prompt",
                ["https://example.com/reference.png"],
            )
        finally:
            provider.client.close()

        self.assertIsNotNone(generated)
        self.assertEqual(captured["path"], "/api/v3/images/generations")
        self.assertEqual(
            captured["body"],
            {
                "model": "doubao-seedream-5-0-pro-260628",
                "prompt": "test prompt",
                "size": "1792x1344",
                "output_format": "png",
                "response_format": "b64_json",
                "watermark": False,
                "optimize_prompt_options": {"mode": "standard"},
                "image": "https://example.com/reference.png",
            },
        )

    def test_factory_creates_doubao_provider(self):
        provider = create_image_provider_from_credentials(
            "doubao_image",
            "https://ark.cn-beijing.volces.com/api/v3",
            "test-key",
            "doubao-seedream-5-0-pro-260628",
        )

        self.assertIsInstance(provider, DoubaoImageProvider)


if __name__ == "__main__":
    unittest.main()
