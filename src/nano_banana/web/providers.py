"""Web 扩展渠道；不把 Codex 凭据伪装成 API Key 或改变桌面 API 注册表。"""
from nano_banana.core.images.provider_config import IMAGE_PROVIDER_META

WEB_PROVIDER_META = {
    **IMAGE_PROVIDER_META,
    "codex_images": {"label": "Codex Image（套餐 / 实验）", "auth_kind": "codex_subscription",
                     "config_keys": {"model": "codex_image_model"},
                     "model_suggestions": ["gpt-image-2"], "default_model": "gpt-image-2"},
}
