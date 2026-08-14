"""图片生成 provider 适配层。"""

import base64
import copy
import json
import mimetypes
import os
import ssl
import time
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from loguru import logger
from openai import OpenAI
from PIL import Image

from components.image_provider_config import (
    ASPECT_RATIO_LIST,
    IMAGE_PROVIDER_META,
    IMAGE_SIZE_LIST,
    THINKING_LEVEL_LIST,
    extract_provider_credentials,
)


IMAGE_PROVIDER_CAPABILITIES = {
    "gemini": {
        "label": IMAGE_PROVIDER_META["gemini"]["label"],
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
                "default": "2K",
                "values": IMAGE_SIZE_LIST,
            },
            "thinking_level": {
                "label": "思考级别",
                "type": "select",
                "default": "low",
                "values": THINKING_LEVEL_LIST,
            },
        },
    },
    "openai_images": {
        "label": IMAGE_PROVIDER_META["openai_images"]["label"],
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
                "default": "2K",
                "values": IMAGE_SIZE_LIST,
            },
            "quality": {
                "label": "质量",
                "type": "select",
                "default": "auto",
                "values": ["auto", "low", "medium", "high"],
            },
            "output_format": {
                "label": "输出格式",
                "type": "select",
                "default": "png",
                "values": ["png", "jpeg", "webp"],
            },
        },
    },
    "qwen_image": {
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
    },
    "doubao_image": {
        "label": IMAGE_PROVIDER_META["doubao_image"]["label"],
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
                "default": "2K",
                "values": ["1K", "1.5K", "2K"],
            },
            "output_format": {
                "label": "输出格式",
                "type": "select",
                "default": "png",
                "values": ["png", "jpeg"],
            },
            "watermark": {
                "label": "水印",
                "type": "select",
                "default": "false",
                "values": ["false", "true"],
            },
            "optimize_prompt_mode": {
                "label": "提示词优化",
                "type": "select",
                "default": "standard",
                "values": ["standard", "fast"],
            },
        },
    },
}


def get_image_provider_capabilities(provider: str, model: str = "") -> dict[str, Any]:
    """返回渠道/模型对应的生图能力，模型未声明覆盖时使用渠道默认能力。"""
    resolved_provider = provider if provider in IMAGE_PROVIDER_CAPABILITIES else "gemini"
    capabilities = copy.deepcopy(IMAGE_PROVIDER_CAPABILITIES[resolved_provider])
    model_overrides = (
        IMAGE_PROVIDER_META.get(resolved_provider, {})
        .get("model_capabilities", {})
        .get(model, {})
    )
    if model_overrides:
        capabilities.update(
            {
                key: copy.deepcopy(value)
                for key, value in model_overrides.items()
                if key != "options"
            }
        )
        for key, option in model_overrides.get("options", {}).items():
            if option is None:
                capabilities["options"].pop(key, None)
            else:
                existing = capabilities["options"].get(key, {})
                capabilities["options"][key] = {**existing, **copy.deepcopy(option)}
    return capabilities

OPENAI_IMAGES_SIZE_MAP = {
    "1K": {
        "1:1": "1024x1024",
        "2:3": "1024x1536",
        "3:2": "1536x1024",
        "3:4": "1024x1360",
        "4:3": "1360x1024",
        "4:5": "1024x1280",
        "5:4": "1280x1024",
        "9:16": "864x1536",
        "16:9": "1536x864",
        "21:9": "1792x768",
    },
    "2K": {
        "1:1": "2048x2048",
        "2:3": "1440x2160",
        "3:2": "2160x1440",
        "3:4": "1536x2048",
        "4:3": "2048x1536",
        "4:5": "1600x2000",
        "5:4": "2000x1600",
        "9:16": "1440x2560",
        "16:9": "2560x1440",
        "21:9": "3024x1296",
    },
    "4K": {
        "1:1": "2880x2880",
        "2:3": "2304x3456",
        "3:2": "3456x2304",
        "3:4": "2496x3328",
        "4:3": "3328x2496",
        "4:5": "2560x3200",
        "5:4": "3200x2560",
        "9:16": "2160x3840",
        "16:9": "3840x2160",
        "21:9": "3840x1648",
    },
}

# 千问 size 格式为 宽*高，总像素需在 512*512～2048*2048
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

DOUBAO_IMAGE_SIZE_MAP = {
    "1K": {
        "1:1": "1024x1024",
        "2:3": "832x1248",
        "3:2": "1248x832",
        "3:4": "864x1152",
        "4:3": "1152x864",
        "4:5": "960x1200",
        "5:4": "1200x960",
        "9:16": "800x1424",
        "16:9": "1424x800",
        "21:9": "1568x672",
    },
    "1.5K": {
        "1:1": "1536x1536",
        "2:3": "1248x1872",
        "3:2": "1872x1248",
        "3:4": "1344x1792",
        "4:3": "1792x1344",
        "4:5": "1280x1600",
        "5:4": "1600x1280",
        "9:16": "1152x2048",
        "16:9": "2048x1152",
        "21:9": "2352x1008",
    },
    "2K": {
        "1:1": "2048x2048",
        "2:3": "1664x2496",
        "3:2": "2496x1664",
        "3:4": "1776x2368",
        "4:3": "2368x1776",
        "4:5": "1792x2240",
        "5:4": "2240x1792",
        "9:16": "1584x2816",
        "16:9": "2816x1584",
        "21:9": "3136x1344",
    },
}

QWEN_GENERATION_PATH = "/services/aigc/multimodal-generation/generation"


@dataclass
class ImageGenerateOptions:
    """provider-specific 生图参数容器。"""

    provider: str = "gemini"
    values: dict[str, Any] = field(default_factory=dict)


def get_provider_label(provider: str) -> str:
    meta = IMAGE_PROVIDER_META.get(provider) or {}
    caps = IMAGE_PROVIDER_CAPABILITIES.get(provider) or {}
    return str(caps.get("label") or meta.get("label") or provider)


def encode_image_reference(image_ref: str) -> str:
    """将本地图片转换为模型接口可接收的 Data URI，URL/Data URI 原样保留。"""
    value = (image_ref or "").strip()
    if not value:
        raise ValueError("参考图路径为空")
    if value.startswith("data:") or value.startswith("http://") or value.startswith("https://"):
        return value
    if not os.path.isfile(value):
        raise ValueError(f"参考图文件不存在: {value}")

    mime_type, _ = mimetypes.guess_type(value)
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/png"
    with open(value, "rb") as file_obj:
        encoded = base64.b64encode(file_obj.read()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


class GeminiImageProvider:
    """Gemini 生图 provider。"""

    def __init__(self, base_url: str, api_key: str, model: str):
        from components.gemini_client import GeminiClient

        self.provider = "gemini"
        self.model = model or "gemini-3-pro-image-preview"
        self.client = GeminiClient(
            base_url=base_url,
            api_key=api_key,
            image_model=self.model,
        )
        logger.info(f"[GeminiImageProvider] 初始化完成，模型: {self.model}，地址: {base_url}")

    def set_generation_options(self, options: dict[str, Any]) -> None:
        if options.get("aspect_ratio"):
            self.client.set_aspect_ratio(options["aspect_ratio"])
        if options.get("image_size"):
            self.client.set_image_size(options["image_size"])
        if options.get("thinking_level"):
            self.client.set_thinking_level(options["thinking_level"])
        logger.info(
            f"[GeminiImageProvider] 生图参数 → 宽高比={options.get('aspect_ratio')}，"
            f"尺寸={options.get('image_size')}，思考级别={options.get('thinking_level')}"
        )

    def generate_image(self, text: str, images: Optional[list[str]] = None) -> Optional[Image.Image]:
        logger.info(f"[GeminiImageProvider] 开始生图，参考图数量: {len(images) if images else 0}")
        return self.client.generate_image(text=text, images=images)


class OpenAIImagesProvider:
    """OpenAI Images API 兼容生图 provider。"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.provider = "openai_images"
        self.model = model or "gpt-image-2"
        self.options: dict[str, Any] = {}
        self.client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/") if base_url else None)
        logger.info(f"[OpenAIImagesProvider] 初始化完成，模型: {self.model}，地址: {base_url}")

    def set_generation_options(self, options: dict[str, Any]) -> None:
        caps = IMAGE_PROVIDER_CAPABILITIES["openai_images"]["options"]
        self.options = {
            key: value
            for key, value in options.items()
            if key in caps and value not in (None, "")
        }
        logger.info(f"[OpenAIImagesProvider] 生图参数（原始）→ {options}")
        logger.info(f"[OpenAIImagesProvider] 生图参数（过滤后）→ {self.options}")

    def generate_image(self, text: str, images: Optional[list[str]] = None) -> Optional[Image.Image]:
        kwargs = self._build_request_kwargs(text)
        logger.info(f"[OpenAIImagesProvider] 发起请求，参数: { {k: v for k, v in kwargs.items() if k != 'prompt'} }，参考图数量: {len(images) if images else 0}")
        try:
            if images:
                response = self._edit_image(images, kwargs)
            else:
                response = self.client.images.generate(**kwargs)
            logger.info("[OpenAIImagesProvider] 请求成功，正在解析图片")
            return self._extract_image(response)
        except TypeError:
            logger.warning("[OpenAIImagesProvider] 参数不兼容，使用核心字段重试")
            kwargs = {key: value for key, value in kwargs.items() if key in {"model", "prompt", "size"}}
            logger.info(f"[OpenAIImagesProvider] 重试参数: {kwargs}")
            if images:
                response = self._edit_image(images, kwargs)
            else:
                response = self.client.images.generate(**kwargs)
            logger.info("[OpenAIImagesProvider] 重试成功，正在解析图片")
            return self._extract_image(response)

    def _build_request_kwargs(self, prompt: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "size": self._resolve_size(),
        }
        for key in ("quality", "output_format"):
            value = self.options.get(key)
            if value and value != "auto":
                kwargs[key] = value
        return kwargs

    def _resolve_size(self) -> str:
        aspect_ratio = self.options.get("aspect_ratio") or "1:1"
        image_size = self.options.get("image_size") or "2K"
        return OPENAI_IMAGES_SIZE_MAP.get(image_size, OPENAI_IMAGES_SIZE_MAP["2K"]).get(
            aspect_ratio,
            OPENAI_IMAGES_SIZE_MAP["2K"]["1:1"],
        )

    def _edit_image(self, images: list[str], kwargs: dict[str, Any]):
        opened_files = []
        try:
            for image_path in images:
                if not os.path.isfile(image_path):
                    raise ValueError("OpenAI Images 编辑模式需要本地图片文件路径")
                opened_files.append(open(image_path, "rb"))

            image_arg = opened_files[0] if len(opened_files) == 1 else opened_files
            return self.client.images.edit(image=image_arg, **kwargs)
        finally:
            for file_obj in opened_files:
                file_obj.close()

    @staticmethod
    def _extract_image(response) -> Optional[Image.Image]:
        if not getattr(response, "data", None):
            return None

        item = response.data[0]
        b64_json = getattr(item, "b64_json", None)
        if b64_json:
            return Image.open(BytesIO(base64.b64decode(b64_json)))

        url = getattr(item, "url", None)
        if url:
            with urlopen(url, timeout=120) as resp:
                return Image.open(BytesIO(resp.read()))

        return None


class QwenHTTPError(RuntimeError):
    """千问 HTTP 错误，保留状态码供重试策略判断。"""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class QwenImageProvider:
    """阿里云百炼千问图像 3.0（文生图 / 图生图）provider。"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.provider = "qwen_image"
        self.api_key = api_key
        self.model = model or IMAGE_PROVIDER_META["qwen_image"]["default_model"]
        self.options: dict[str, Any] = {}
        self.endpoint = self._normalize_endpoint(base_url)
        logger.info(f"[QwenImageProvider] 初始化完成，模型: {self.model}，地址: {self.endpoint}")

    @staticmethod
    def _normalize_endpoint(base_url: str) -> str:
        url = (base_url or "").strip().rstrip("/")
        if not url:
            raise ValueError("请先配置千问图像 Base URL")
        if url.endswith(QWEN_GENERATION_PATH):
            return url
        return f"{url}{QWEN_GENERATION_PATH}"

    def set_generation_options(self, options: dict[str, Any]) -> None:
        caps = IMAGE_PROVIDER_CAPABILITIES["qwen_image"]["options"]
        self.options = {
            key: value
            for key, value in options.items()
            if key in caps and value not in (None, "")
        }
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


class DoubaoImageProvider:
    """火山方舟豆包 Seedream 图片生成 provider。"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.provider = "doubao_image"
        self.model = model or IMAGE_PROVIDER_META["doubao_image"]["default_model"]
        self.options: dict[str, Any] = {}
        normalized_base_url = (base_url or "").strip().rstrip("/")
        if normalized_base_url.endswith("/images/generations"):
            normalized_base_url = normalized_base_url[: -len("/images/generations")]
        self.base_url = normalized_base_url
        self.client = OpenAI(api_key=api_key, base_url=self.base_url)
        logger.info(
            f"[DoubaoImageProvider] 初始化完成，模型: {self.model}，地址: {self.base_url}"
        )

    def set_generation_options(self, options: dict[str, Any]) -> None:
        caps = IMAGE_PROVIDER_CAPABILITIES["doubao_image"]["options"]
        self.options = {
            key: value
            for key, value in options.items()
            if key in caps and value not in (None, "")
        }
        logger.info(f"[DoubaoImageProvider] 生图参数（过滤后）→ {self.options}")

    def generate_image(
        self,
        text: str,
        images: Optional[list[str]] = None,
    ) -> Optional[Image.Image]:
        kwargs = self._build_request_kwargs(text, images)
        log_kwargs = {key: value for key, value in kwargs.items() if key != "prompt"}
        extra_body = dict(log_kwargs.get("extra_body") or {})
        if "image" in extra_body:
            refs = extra_body["image"]
            extra_body["image"] = f"{len(refs) if isinstance(refs, list) else 1} 张参考图"
            log_kwargs["extra_body"] = extra_body
        logger.info(f"[DoubaoImageProvider] 发起请求，参数: {log_kwargs}")
        try:
            response = self.client.images.generate(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"豆包 Seedream 请求失败: {exc}") from exc
        return OpenAIImagesProvider._extract_image(response)

    def _build_request_kwargs(
        self,
        prompt: str,
        images: Optional[list[str]],
    ) -> dict[str, Any]:
        extra_body: dict[str, Any] = {
            "watermark": str(self.options.get("watermark", "false")).lower() == "true",
            "optimize_prompt_options": {
                "mode": self.options.get("optimize_prompt_mode") or "standard"
            },
        }
        if images:
            if len(images) > 10:
                logger.warning(
                    f"[DoubaoImageProvider] 参考图超过 10 张，仅使用前 10 张（共 {len(images)}）"
                )
            encoded_images = [encode_image_reference(image) for image in images[:10]]
            extra_body["image"] = (
                encoded_images[0] if len(encoded_images) == 1 else encoded_images
            )

        return {
            "model": self.model,
            "prompt": prompt,
            "size": self._resolve_size(),
            "output_format": self.options.get("output_format") or "png",
            "response_format": "b64_json",
            "extra_body": extra_body,
        }

    def _resolve_size(self) -> str:
        image_size = self.options.get("image_size") or "2K"
        aspect_ratio = self.options.get("aspect_ratio") or "1:1"
        size_bucket = DOUBAO_IMAGE_SIZE_MAP.get(image_size) or DOUBAO_IMAGE_SIZE_MAP["2K"]
        return size_bucket.get(aspect_ratio) or size_bucket["1:1"]


def create_image_provider(config: dict[str, Any]):
    """根据配置创建当前图片生成 provider。"""

    provider = config.get("image_provider") or "gemini"
    if provider not in IMAGE_PROVIDER_META:
        raise ValueError(f"未知图片生成渠道: {provider}")

    creds = extract_provider_credentials(config, provider)
    base_url = creds["base_url"]
    api_key = creds["api_key"]
    model = creds["model"]
    return create_image_provider_from_credentials(provider, base_url, api_key, model)


def create_image_provider_from_credentials(
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
):
    """使用一次生成操作的连接快照创建 provider。"""
    if provider not in IMAGE_PROVIDER_META:
        raise ValueError(f"未知图片生成渠道: {provider}")

    if provider == "openai_images":
        if not base_url or not api_key:
            raise ValueError("请先配置 gpt-image-2 图片生成 Base URL 和 API Key")
        return OpenAIImagesProvider(base_url=base_url, api_key=api_key, model=model)

    if provider == "qwen_image":
        if not base_url or not api_key:
            raise ValueError("请先配置千问图像 Base URL 和 API Key")
        return QwenImageProvider(base_url=base_url, api_key=api_key, model=model)

    if provider == "doubao_image":
        if not base_url or not api_key:
            raise ValueError("请先配置豆包 Seedream Base URL 和 API Key")
        return DoubaoImageProvider(base_url=base_url, api_key=api_key, model=model)

    if provider == "gemini":
        if not base_url or not api_key:
            raise ValueError("请先配置 Gemini 图片生成 Base URL 和 API Key")
        return GeminiImageProvider(base_url=base_url, api_key=api_key, model=model)

    raise ValueError(f"未知图片生成渠道: {provider}")
