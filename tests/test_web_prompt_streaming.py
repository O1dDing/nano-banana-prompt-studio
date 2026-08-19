import importlib.util
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

spec = importlib.util.spec_from_file_location(
    "nano_banana_prompt_streaming_web_app", SRC / "web" / "app.py"
)
web_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web_app)


class DummyHttpClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class DummyCompletions:
    def __init__(self):
        self.create_called = False

    def create(self, **kwargs):
        self.create_called = True
        assert kwargs["stream"] is True
        return iter(
            [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content="", reasoning_content="thinking"
                            )
                        )
                    ]
                ),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content='{"scene":"forest"}', reasoning_content=None
                            )
                        )
                    ]
                ),
            ]
        )


class DummyOpenAI:
    completions = None

    def __init__(self, **_kwargs):
        type(self).completions = DummyCompletions()
        self.chat = SimpleNamespace(completions=type(self).completions)


class WebPromptStreamingApiTests(unittest.TestCase):
    def setUp(self):
        self.client = web_app.app.test_client()

    def test_prompt_endpoints_start_before_upstream_and_report_thinking(self):
        cases = [
            ("/api/generate", {"prompt": "a forest", "images": []}),
            (
                "/api/modify",
                {
                    "current_data": "{}",
                    "modify_request": "add a forest",
                    "images": [],
                },
            ),
        ]

        for endpoint, payload in cases:
            with self.subTest(endpoint=endpoint):
                http_client = DummyHttpClient()
                with (
                    patch.object(
                        web_app.config_manager,
                        "load_config",
                        return_value={
                            "base_url": "https://example.test/v1",
                            "api_key": "test-key",
                            "model": "reasoning-model",
                        },
                    ),
                    patch("openai.OpenAI", DummyOpenAI),
                    patch("httpx.Client", return_value=http_client),
                ):
                    response = self.client.post(endpoint, json=payload, buffered=False)

                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["Cache-Control"], "no-cache")
                    self.assertEqual(response.headers["X-Accel-Buffering"], "no")
                    self.assertFalse(DummyOpenAI.completions.create_called)

                    chunks = iter(response.response)
                    first_chunk = next(chunks).decode("utf-8")
                    self.assertEqual(
                        json.loads(first_chunk.removeprefix("data: ")),
                        {"status": "started"},
                    )
                    self.assertFalse(DummyOpenAI.completions.create_called)

                    remaining = b"".join(chunks).decode("utf-8")
                    self.assertIn('data: {"status": "thinking"}', remaining)
                    self.assertIn(
                        'data: {"content": "{\\"scene\\":\\"forest\\"}"}',
                        remaining,
                    )
                    self.assertTrue(remaining.endswith("data: [DONE]\n\n"))
                    self.assertTrue(http_client.closed)

    def test_abort_after_started_closes_http_client_without_calling_upstream(self):
        http_client = DummyHttpClient()
        with (
            patch.object(
                web_app.config_manager,
                "load_config",
                return_value={
                    "base_url": "https://example.test/v1",
                    "api_key": "test-key",
                    "model": "reasoning-model",
                },
            ),
            patch("openai.OpenAI", DummyOpenAI),
            patch("httpx.Client", return_value=http_client),
        ):
            response = self.client.post(
                "/api/generate",
                json={"prompt": "a forest", "images": []},
                buffered=False,
            )

            chunks = iter(response.response)
            first_chunk = next(chunks).decode("utf-8")
            self.assertEqual(
                json.loads(first_chunk.removeprefix("data: ")),
                {"status": "started"},
            )
            response.close()

        self.assertFalse(DummyOpenAI.completions.create_called)
        self.assertTrue(http_client.closed)


@unittest.skipUnless(shutil.which("node"), "Node.js is required for browser parser tests")
class BrowserSseParserTests(unittest.TestCase):
    def test_parser_buffers_split_events_and_surfaces_server_errors(self):
        parser_path = SRC / "web" / "static" / "sse-parser.js"
        script = r"""
const { SseEventParser, parseSseJsonEvent } = require(process.argv[1]);
const parser = new SseEventParser();
const first = parser.push('data: {"content":"hel');
const second = parser.push('lo"}\r\n\r\n');
if (first.length !== 0) throw new Error('partial event emitted too early');
if (second.length !== 1) throw new Error('completed event was not emitted');
const parsed = parseSseJsonEvent(second[0]);
if (parsed.type !== 'content' || parsed.content !== 'hello') {
    throw new Error('split content event was not reconstructed');
}
let errorMessage = '';
try {
    parseSseJsonEvent('{"error":"upstream failed"}');
} catch (error) {
    errorMessage = error.message;
}
if (errorMessage !== 'upstream failed') {
    throw new Error('server error was not surfaced');
}
"""

        result = subprocess.run(
            ["node", "-e", script, str(parser_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_page_loads_parser_before_main_script(self):
        html = (SRC / "web" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertLess(
            html.index('<script src="/static/sse-parser.js"></script>'),
            html.index('<script src="/static/script.js"></script>'),
        )
        self.assertLess(
            html.index('<script src="/static/script.js"></script>'),
            html.index('<script src="/static/image-gen.js"></script>'),
        )
        self.assertLess(
            html.index('<script src="/static/image-gen.js"></script>'),
            html.index('<script src="/static/ai-stream.js"></script>'),
        )
        script = (SRC / "web" / "static" / "ai-stream.js").read_text(encoding="utf-8")
        stream_handler = script.split("async function handleAiExecute()", 1)[1].split(
            "function handleAiStop()", 1
        )[0]
        self.assertLess(
            stream_handler.index("sseParser.finish();"),
            stream_handler.rfind("} catch (e) {")
        )


if __name__ == "__main__":
    unittest.main()
