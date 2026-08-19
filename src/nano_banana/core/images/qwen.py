"""阿里云百炼千问图像 provider。"""

import json
import ssl
import time
from io import BytesIO
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from loguru import logger
from PIL import Image

from nano_banana.core.images.protocol import encode_image_reference, filter_generation_options
from nano_banana.core.images.provider_config import (
    ASPECT_RATIO_LIST,
    IMAGE_PROVIDER_META,
)


QWEN_IMAGE_SIZE_MAP = {
    "1K": {
        "1:1": "1024*1024",
        "2:3": "768*1152",
        "3:2": "1152*768",
        "3:4": "960*1280",
        "4:3": "1280*960",
        "4:5": "896*1120",
        "5:4": "1120*896",
        "9:16": "720*1280",
        "16:9": "1280*720",
        "21:9": "1344*576",
    },
    "2K": {
        "1:1": "2048*2048",
        "2:3": "1440*2160",
        "3:2": "2160*1440",
        "3:4": "1536*2048",
        "4:3": "2048*1536",
        "4:5": "1600*2000",
        "5:4": "2000*1600",
        "9:16": "1536*2688",
        "16:9": "2688*1536",
        "21:9": "2688*1152",
    },
}
QWEN_GENERATION_PATH = "/services/aigc/multimodal-generation/generation"


class QwenHTTPError(RuntimeError):
    """千问 HTTP 错误，保留状态码供重试策略判断。"""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class QwenImageProvider:
    """阿里云百炼千问图像 3.0（文生图 / 图生图）provider。"""

    provider = "qwen_image"
    CAPABILITIES = {
        "label": IMAGE_PROVIDER_META["qwen_image"]["label"],
        "options": {
            "aspect_ratio": {
                "label": "宽高比",
                "type": "select",
                "default": "1:1",
                "values": ASPECT_RATIO_LIST,
            },
            "image_size": {
                "label": "尺寸",
                "type": "select",
                "default": "auto",
                "values": ["auto", "1K", "2K"],
            },
            "prompt_extend": {
                "label": "提示词增强",
                "type": "select",
                "default": "true",
                "values": ["true", "false"],
            },
            "prompt_extend_mode": {
                "label": "增强方式",
                "type": "select",
                "default": "direct",
                "values": ["direct", "agent"],
            },
        },
    }

    def __init__(self, base_url: str, api_key: str, model: str):
        self.api_key = api_key
        self.model = model or IMAGE_PROVIDER_META["qwen_image"]["default_model"]
        self.options: dict[str, Any] = {}
        self.endpoint = self._normalize_endpoint(base_url)
        logger.info(f"[QwenImageProvider] 初始化完成，模型: {self.model}，地址: {self.endpoint}")

    def capabilities(self, model: str = "") -> dict[str, Any]:
        from nano_banana.core.images.protocol import get_image_provider_capabilities

        return get_image_provider_capabilities(self.provider, model or self.model)

    @staticmethod
    def _normalize_endpoint(base_url: str) -> str:
        url = (base_url or "").strip().rstrip("/")
        if not url:
            raise ValueError("请先配置千问图像 Base URL")
        if url.endswith(QWEN_GENERATION_PATH):
            return url
        return f"{url}{QWEN_GENERATION_PATH}"

    def set_generation_options(self, options: dict[str, Any]) -> None:
        self.options = filter_generation_options(type(self), options)
        logger.info(f"[QwenImageProvider] 生图参数（原始）→ {options}")
        logger.info(f"[QwenImageProvider] 生图参数（过滤后）→ {self.options}")

    def generate_image(self, text: str, images: Optional[list[str]] = None) -> Optional[Image.Image]:
        content = self._build_content(text, images)
        has_refs = any("image" in item for item in content)
        parameters = self._build_parameters(has_refs=has_refs)
        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ]
            },
            "parameters": parameters,
        }
        logger.info(
            f"[QwenImageProvider] 发起请求，模型={self.model}，参考图={sum(1 for i in content if 'image' in i)}，"
            f"parameters={parameters}"
        )
        response = self._post_json(payload)
        return self._extract_image(response)

    def _build_content(self, text: str, images: Optional[list[str]]) -> list[dict[str, str]]:
        content: list[dict[str, str]] = []
        if images:
            if len(images) > 3:
                logger.warning(f"[QwenImageProvider] 参考图超过 3 张，仅使用前 3 张（共 {len(images)}）")
            for image_ref in images[:3]:
                content.append({"image": self._encode_image_ref(image_ref)})
        content.append({"text": text})
        return content

    def _build_parameters(self, has_refs: bool) -> dict[str, Any]:
        parameters: dict[str, Any] = {"n": 1}

        prompt_extend = self.options.get("prompt_extend", "true")
        parameters["prompt_extend"] = str(prompt_extend).lower() != "false"

        mode = self.options.get("prompt_extend_mode") or "direct"
        if has_refs and mode == "agent":
            logger.warning("[QwenImageProvider] I2I 不支持 agent 增强，已降为 direct")
            mode = "direct"
        parameters["prompt_extend_mode"] = mode

        parameters["watermark"] = False

        size = self._resolve_size()
        if size:
            parameters["size"] = size
        return parameters

    def _resolve_size(self) -> Optional[str]:
        image_size = self.options.get("image_size") or "auto"
        if image_size == "auto":
            return None
        aspect_ratio = self.options.get("aspect_ratio") or "1:1"
        size_bucket = QWEN_IMAGE_SIZE_MAP.get(image_size) or QWEN_IMAGE_SIZE_MAP["2K"]
        return size_bucket.get(aspect_ratio) or size_bucket.get("1:1")

    def _encode_image_ref(self, image_ref: str) -> str:
        return encode_image_reference(image_ref)

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload)
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                raw = self._http_request(
                    "POST",
                    self.endpoint,
                    content=body.encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    timeout=180.0,
                )
                break
            except QwenHTTPError as exc:
                last_error = exc
                if not self._is_transient_http_error(exc.status_code) or attempt >= 3:
                    raise
                logger.warning(f"[QwenImageProvider] POST 重试 {attempt}/3: {exc}")
                time.sleep(1.5 * attempt)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if not self._is_transient_network_error(exc) or attempt >= 3:
                    raise RuntimeError(f"千问图像网络错误: {exc}") from exc
                logger.warning(f"[QwenImageProvider] POST 重试 {attempt}/3: {exc}")
                time.sleep(1.5 * attempt)
        else:
            raise RuntimeError(f"千问图像网络错误: {last_error}")

        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"千问图像返回非 JSON: {raw[:200]!r}") from exc

        if isinstance(data, dict) and data.get("code"):
            raise RuntimeError(
                f"千问图像请求失败: code={data.get('code')}, message={data.get('message')}"
                + (f", request_id={data.get('request_id')}" if data.get("request_id") else "")
            )
        if isinstance(data, dict) and data.get("status_code") not in (None, 200):
            raise RuntimeError(
                f"千问图像请求失败: status_code={data.get('status_code')}, "
                f"code={data.get('code')}, message={data.get('message')}"
            )
        return data

    @staticmethod
    def _is_transient_network_error(exc: Exception) -> bool:
        text = str(exc).lower()
        needles = (
            "not_enough_data",
            "ssl",
            "eof",
            "timed out",
            "timeout",
            "connection refused",
            "all connection attempts failed",
            "connection reset",
            "connection aborted",
            "temporarily unavailable",
            "remote disconnected",
            "server disconnected",
        )
        if any(n in text for n in needles):
            return True
        if type(exc).__module__.startswith("httpx"):
            return type(exc).__name__ in {
                "CloseError",
                "ConnectError",
                "ConnectTimeout",
                "NetworkError",
                "PoolTimeout",
                "ReadError",
                "ReadTimeout",
                "RemoteProtocolError",
                "TransportError",
                "WriteError",
                "WriteTimeout",
            }
        return isinstance(exc, (ssl.SSLError, TimeoutError, ConnectionError, OSError))

    @staticmethod
    def _is_transient_http_error(status_code: int) -> bool:
        return status_code == 429 or status_code in {500, 502, 503, 504}

    @staticmethod
    def _http_request(
        method: str,
        url: str,
        *,
        content: Optional[bytes] = None,
        headers: Optional[dict[str, str]] = None,
        timeout: float = 120.0,
    ) -> bytes:
        """优先 httpx（与项目其它 AI 调用一致），失败再回退 urllib。"""
        try:
            import httpx

            with httpx.Client(http2=False, timeout=timeout, follow_redirects=True) as client:
                response = client.request(method, url, content=content, headers=headers or {})
                if response.status_code >= 400:
                    detail = response.text
                    try:
                        parsed = response.json()
                        code = parsed.get("code") or response.status_code
                        message = parsed.get("message") or detail
                        request_id = parsed.get("request_id") or ""
                        raise QwenHTTPError(
                            f"千问图像请求失败: code={code}, message={message}"
                            + (f", request_id={request_id}" if request_id else ""),
                            response.status_code,
                        )
                    except QwenHTTPError:
                        raise
                    except Exception:  # noqa: BLE001
                        raise QwenHTTPError(
                            f"千问图像请求失败: HTTP {response.status_code}, {detail[:300]}",
                            response.status_code,
                        )
                return response.content
        except ImportError:
            pass

        request = Request(url, data=content, headers=headers or {}, method=method)
        try:
            with urlopen(request, timeout=timeout) as resp:
                return resp.read()
        except HTTPError as exc:
            error_body = ""
            try:
                error_body = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
            detail = error_body or str(exc)
            try:
                parsed = json.loads(error_body) if error_body else {}
                code = parsed.get("code") or exc.code
                message = parsed.get("message") or detail
                request_id = parsed.get("request_id") or ""
                raise QwenHTTPError(
                    f"千问图像请求失败: code={code}, message={message}"
                    + (f", request_id={request_id}" if request_id else ""),
                    exc.code,
                ) from exc
            except QwenHTTPError:
                raise
            except Exception:  # noqa: BLE001
                raise QwenHTTPError(
                    f"千问图像请求失败: HTTP {exc.code}, {detail}",
                    exc.code,
                ) from exc
        except URLError as exc:
            raise

    def _extract_image(self, response: dict[str, Any]) -> Optional[Image.Image]:
        choices = ((response.get("output") or {}).get("choices")) or []
        if not choices:
            logger.warning("[QwenImageProvider] 响应无 choices")
            return None

        content = ((choices[0].get("message") or {}).get("content")) or []
        image_url = None
        for item in content:
            if isinstance(item, dict) and item.get("image"):
                image_url = item["image"]
                break
        if not image_url:
            logger.warning("[QwenImageProvider] 响应未包含 image URL")
            return None

        logger.info("[QwenImageProvider] 正在下载生成图片")
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                image_bytes = self._http_request("GET", image_url, timeout=120.0)
                return Image.open(BytesIO(image_bytes))
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                is_transient = self._is_transient_network_error(exc)
                if isinstance(exc, QwenHTTPError):
                    is_transient = self._is_transient_http_error(exc.status_code)
                if not is_transient or attempt >= 3:
                    raise RuntimeError(f"千问图像下载失败: {exc}") from exc
                logger.warning(f"[QwenImageProvider] 下载重试 {attempt}/3: {exc}")
                time.sleep(1.5 * attempt)
        raise RuntimeError(f"千问图像下载失败: {last_error}")
