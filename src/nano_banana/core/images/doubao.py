"""火山方舟豆包 Seedream 生图 provider。"""

from typing import Any, Optional

from loguru import logger
from PIL import Image

from nano_banana.core.images.openai_images import OpenAIImagesProvider
from nano_banana.core.images.protocol import encode_image_reference, filter_generation_options
from nano_banana.core.images.provider_config import (
    ASPECT_RATIO_LIST,
    IMAGE_PROVIDER_META,
)


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

class DoubaoImageProvider:
    """火山方舟豆包 Seedream 图片生成 provider。"""

    provider = "doubao_image"
    CAPABILITIES = {
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
    }

    def __init__(self, base_url: str, api_key: str, model: str):
        from openai import OpenAI

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

    def capabilities(self, model: str = "") -> dict[str, Any]:
        from nano_banana.core.images.protocol import get_image_provider_capabilities

        return get_image_provider_capabilities(self.provider, model or self.model)

    def set_generation_options(self, options: dict[str, Any]) -> None:
        self.options = filter_generation_options(type(self), options)
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
