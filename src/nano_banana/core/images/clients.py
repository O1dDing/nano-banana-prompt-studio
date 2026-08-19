"""图片生成 provider 兼容导出。"""

from nano_banana.core.images.protocol import (
    ImageGenerateOptions,
    create_image_provider,
    create_image_provider_from_credentials,
    encode_image_reference,
    get_image_provider_capabilities,
    get_provider_label,
)

__all__ = [
    "IMAGE_PROVIDER_CAPABILITIES",
    "DoubaoImageProvider",
    "GeminiImageProvider",
    "ImageGenerateOptions",
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
    from nano_banana.core import images as images_pkg

    return getattr(images_pkg, name)
