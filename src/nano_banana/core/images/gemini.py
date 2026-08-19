"""Gemini 生图 provider。"""

from typing import Any, Optional

from loguru import logger
from PIL import Image

from nano_banana.core.images.provider_config import (
    ASPECT_RATIO_LIST,
    IMAGE_PROVIDER_META,
    IMAGE_SIZE_LIST,
    THINKING_LEVEL_LIST,
)


class GeminiImageProvider:
    """Gemini 生图 provider。"""

    provider = "gemini"
    CAPABILITIES = {
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
    }

    def __init__(self, base_url: str, api_key: str, model: str):
        from nano_banana.core.images.gemini_client import GeminiClient

        self.model = model or "gemini-3-pro-image-preview"
        self.client = GeminiClient(
            base_url=base_url,
            api_key=api_key,
            image_model=self.model,
        )
        logger.info(f"[GeminiImageProvider] 初始化完成，模型: {self.model}，地址: {base_url}")

    def capabilities(self, model: str = "") -> dict[str, Any]:
        from nano_banana.core.images.protocol import get_image_provider_capabilities

        return get_image_provider_capabilities(self.provider, model or self.model)

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
