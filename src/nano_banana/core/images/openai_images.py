"""OpenAI Images API 兼容生图 provider。"""

import base64
import os
from io import BytesIO
from typing import Any, Optional
from urllib.request import urlopen

from loguru import logger
from PIL import Image

from nano_banana.core.images.protocol import filter_generation_options
from nano_banana.core.images.provider_config import (
    ASPECT_RATIO_LIST,
    IMAGE_PROVIDER_META,
    IMAGE_SIZE_LIST,
)


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

class OpenAIImagesProvider:
    """OpenAI Images API 兼容生图 provider。"""

    provider = "openai_images"
    CAPABILITIES = {
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
    }

    def __init__(self, base_url: str, api_key: str, model: str):
        from openai import OpenAI

        self.model = model or "gpt-image-2"
        self.options: dict[str, Any] = {}
        self.client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/") if base_url else None)
        logger.info(f"[OpenAIImagesProvider] 初始化完成，模型: {self.model}，地址: {base_url}")

    def capabilities(self, model: str = "") -> dict[str, Any]:
        from nano_banana.core.images.protocol import get_image_provider_capabilities

        return get_image_provider_capabilities(self.provider, model or self.model)

    def set_generation_options(self, options: dict[str, Any]) -> None:
        self.options = filter_generation_options(type(self), options)
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
