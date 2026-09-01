"""图片生成适配层。provider 实现按需导入，避免 schema/config 被 openai 绑死。"""

from nano_banana.core.images.protocol import (
    ImageGenerateOptions,
    ImageProvider,
    create_image_provider,
    create_image_provider_from_credentials,
    encode_image_reference,
    get_image_provider_capabilities,
    get_provider_label,
)
from nano_banana.core.images.provider_config import IMAGE_PROVIDER_META

_PROVIDER_EXPORTS = {
    "DoubaoImageProvider": ("nano_banana.core.images.doubao", "DoubaoImageProvider"),
    "GeminiImageProvider": ("nano_banana.core.images.gemini", "GeminiImageProvider"),
    "OpenAIImagesProvider": ("nano_banana.core.images.openai_images", "OpenAIImagesProvider"),
    "QwenHTTPError": ("nano_banana.core.images.qwen", "QwenHTTPError"),
    "QwenImageProvider": ("nano_banana.core.images.qwen", "QwenImageProvider"),
}

__all__ = [
    "IMAGE_PROVIDER_CAPABILITIES",
    "IMAGE_PROVIDER_META",
    "DoubaoImageProvider",
    "GeminiImageProvider",
    "ImageGenerateOptions",
    "ImageProvider",
    "OpenAIImagesProvider",
    "QwenHTTPError",
    "QwenImageProvider",
    "create_image_provider",
    "create_image_provider_from_credentials",
    "encode_image_reference",
    "get_image_provider_capabilities",
    "get_provider_label",
]


def __getattr__(name: str):
    if name == "IMAGE_PROVIDER_CAPABILITIES":
        from nano_banana.core.images.protocol import IMAGE_PROVIDER_CAPABILITIES

        globals()[name] = IMAGE_PROVIDER_CAPABILITIES
        return IMAGE_PROVIDER_CAPABILITIES
    target = _PROVIDER_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    from importlib import import_module

    value = getattr(import_module(module_name), attr)
    globals()[name] = value
    return value
