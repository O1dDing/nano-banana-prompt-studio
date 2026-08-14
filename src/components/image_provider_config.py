"""图片生成渠道的轻量配置元数据。"""

from typing import Any


ASPECT_RATIO_LIST = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
IMAGE_SIZE_LIST = ["1K", "2K", "4K"]
THINKING_LEVEL_LIST = ["none", "low", "medium", "high"]


IMAGE_PROVIDER_META: dict[str, dict[str, Any]] = {
    "gemini": {
        "label": "Gemini",
        "config_keys": {
            "base_url": "gemini_base_url",
            "api_key": "gemini_api_key",
            "model": "gemini_model",
        },
        "url_placeholder": "https://generativelanguage.googleapis.com",
        "model_suggestions": [
            "gemini-3-pro-image-preview",
            "gemini-3.1-flash-image-preview",
        ],
        "default_model": "gemini-3-pro-image-preview",
        "default_base_url": "",
    },
    "openai_images": {
        "label": "OpenAI Images",
        "config_keys": {
            "base_url": "openai_image_base_url",
            "api_key": "openai_image_api_key",
            "model": "openai_image_model",
        },
        "url_placeholder": "https://api.openai.com/v1",
        "model_suggestions": ["gpt-image-2"],
        "default_model": "gpt-image-2",
        "default_base_url": "https://api.openai.com/v1",
    },
    "qwen_image": {
        "label": "千问图像",
        "config_keys": {
            "base_url": "qwen_image_base_url",
            "api_key": "qwen_image_api_key",
            "model": "qwen_image_model",
        },
        "url_placeholder": "https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1",
        "model_suggestions": ["qwen-image-3.0-pro"],
        "default_model": "qwen-image-3.0-pro",
        "default_base_url": "",
    },
    "doubao_image": {
        "label": "豆包 Seedream",
        "config_keys": {
            "base_url": "doubao_image_base_url",
            "api_key": "doubao_image_api_key",
            "model": "doubao_image_model",
        },
        "url_placeholder": "https://ark.cn-beijing.volces.com/api/v3",
        "model_suggestions": ["doubao-seedream-5-0-pro-260628"],
        "default_model": "doubao-seedream-5-0-pro-260628",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
    },
}


def extract_provider_credentials(config: dict[str, Any], provider: str) -> dict[str, str]:
    """按渠道元数据从完整配置中取出连接参数。"""
    meta = IMAGE_PROVIDER_META.get(provider)
    if not meta:
        raise ValueError(f"未知图片生成渠道: {provider}")

    keys = meta["config_keys"]
    default_model = meta.get("default_model") or ""
    return {
        "base_url": (config.get(keys["base_url"]) or meta.get("default_base_url") or "").strip(),
        "api_key": (config.get(keys["api_key"]) or "").strip(),
        "model": (config.get(keys["model"]) or default_model).strip() or default_model,
    }
