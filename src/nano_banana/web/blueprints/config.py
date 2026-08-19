from flask import Blueprint, jsonify, request

from nano_banana.core.config import flatten_legacy_or_nested
from nano_banana.core.images.provider_config import IMAGE_PROVIDER_META
from nano_banana.web.context import config_manager

bp = Blueprint("config", __name__)


@bp.get("/api/config")
def get_config():
    try:
        config = config_manager.load_config()
        safe_config = {
            "base_url": config.get("base_url", ""),
            "model": config.get("model", ""),
            "image_provider": config.get("image_provider", "") or "gemini",
            "gemini_base_url": config.get("gemini_base_url", ""),
            "gemini_model": config.get("gemini_model", ""),
            "openai_image_base_url": config.get("openai_image_base_url", ""),
            "openai_image_model": config.get("openai_image_model", ""),
            "qwen_image_base_url": config.get("qwen_image_base_url", ""),
            "qwen_image_model": config.get("qwen_image_model", ""),
            "doubao_image_base_url": config.get("doubao_image_base_url", ""),
            "doubao_image_model": config.get("doubao_image_model", ""),
            "has_api_key": bool(config.get("api_key")),
            "has_gemini_api_key": bool(config.get("gemini_api_key")),
            "has_openai_image_api_key": bool(config.get("openai_image_api_key")),
            "has_qwen_image_api_key": bool(config.get("qwen_image_api_key")),
            "has_doubao_image_api_key": bool(config.get("doubao_image_api_key")),
            "image_generation_options": config.get("image_generation_options") or {},
        }
        return jsonify(safe_config)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.post("/api/config")
def update_config():
    try:
        data = request.json
        if not isinstance(data, dict):
            return jsonify({"error": "请求体必须是 JSON 对象"}), 400
        updates = flatten_legacy_or_nested(data)
        if "image_provider" in updates and updates["image_provider"] not in IMAGE_PROVIDER_META:
            return jsonify({"error": f"未知图片生成渠道: {updates['image_provider']}"}), 400
        if not config_manager.save_config(updates):
            return jsonify({"error": "配置写入失败"}), 500
        return jsonify({"success": True})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
