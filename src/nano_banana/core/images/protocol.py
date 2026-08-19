"""图片生成 provider 协议、能力描述与注册表。"""
from __future__ import annotations

import base64
import copy
import mimetypes
import os
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from PIL import Image

from nano_banana.core.images.provider_config import (
    IMAGE_PROVIDER_META,
    extract_provider_credentials,
)


def filter_generation_options(provider_cls: type, options: dict[str, Any]) -> dict[str, Any]:
    caps = getattr(provider_cls, "CAPABILITIES", {}).get("options", {})
    return {
        key: value
        for key, value in options.items()
        if key in caps and value not in (None, "")
    }


@runtime_checkable
class ImageProvider(Protocol):
    provider: str
    model: str
    CAPABILITIES: dict[str, Any]

    def capabilities(self, model: str = "") -> dict[str, Any]: ...

    def set_generation_options(self, options: dict[str, Any]) -> None: ...

    def generate_image(
        self,
        text: str,
        images: Optional[list[str]] = None,
    ) -> Optional[Image.Image]: ...


@dataclass
class ImageGenerateOptions:
    provider: str = "gemini"
    values: dict[str, Any] = field(default_factory=dict)


def get_image_provider_capabilities(provider: str, model: str = "") -> dict[str, Any]:
    catalog = _capabilities_catalog()
    resolved_provider = provider if provider in catalog else "gemini"
    capabilities = copy.deepcopy(catalog[resolved_provider])
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


def get_provider_label(provider: str) -> str:
    meta = IMAGE_PROVIDER_META.get(provider) or {}
    caps = _capabilities_catalog().get(provider) or {}
    return str(caps.get("label") or meta.get("label") or provider)


def encode_image_reference(image_ref: str) -> str:
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


def _registry() -> dict[str, type]:
    from nano_banana.core.images.doubao import DoubaoImageProvider
    from nano_banana.core.images.gemini import GeminiImageProvider
    from nano_banana.core.images.openai_images import OpenAIImagesProvider
    from nano_banana.core.images.qwen import QwenImageProvider

    return {
        "gemini": GeminiImageProvider,
        "openai_images": OpenAIImagesProvider,
        "qwen_image": QwenImageProvider,
        "doubao_image": DoubaoImageProvider,
    }


def _capabilities_catalog() -> dict[str, dict[str, Any]]:
    return {
        provider: copy.deepcopy(cls.CAPABILITIES)
        for provider, cls in _registry().items()
    }


def __getattr__(name: str):
    if name == "IMAGE_PROVIDER_CAPABILITIES":
        value = _capabilities_catalog()
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def create_image_provider(config: dict[str, Any]):
    provider = config.get("image_provider") or "gemini"
    if provider not in IMAGE_PROVIDER_META:
        raise ValueError(f"未知图片生成渠道: {provider}")
    creds = extract_provider_credentials(config, provider)
    return create_image_provider_from_credentials(
        provider, creds["base_url"], creds["api_key"], creds["model"]
    )


def create_image_provider_from_credentials(
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
):
    if provider not in IMAGE_PROVIDER_META:
        raise ValueError(f"未知图片生成渠道: {provider}")
    registry = _registry()
    factory = registry.get(provider)
    if factory is None:
        raise ValueError(f"未知图片生成渠道: {provider}")
    if not base_url or not api_key:
        label = get_provider_label(provider)
        raise ValueError(f"请先配置 {label} Base URL 和 API Key")
    return factory(base_url=base_url, api_key=api_key, model=model)
