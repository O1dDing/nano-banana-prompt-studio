from flask import Blueprint, jsonify, request

from nano_banana.core.config import flatten_legacy_or_nested
from nano_banana.web.providers import WEB_PROVIDER_META as IMAGE_PROVIDER_META
from nano_banana.core.web_search import normalize_web_search_mode
from nano_banana.web.context import config_manager

bp = Blueprint("config", __name__)


@bp.get("/api/config")
def get_config():
    try:
        config = config_manager.load_config()
        safe_config = {
            "chat_engine": config.get("chat_engine") or "api",
            "codex_model": config.get("codex_model") or "",
            "codex_effort": config.get("codex_effort") or "auto",
            "base_url": config.get("base_url", ""),
            "model": config.get("model", ""),
            "chat_web_search_mode": normalize_web_search_mode(
                config.get("chat_web_search_mode", "auto")
            ),
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
        if updates.get("chat_engine", "api") not in {"api", "codex"}:
            return jsonify({"error": "未知提示词后端"}), 400
        if updates.get("codex_effort", "auto") not in {"auto", "minimal", "low", "medium", "high", "xhigh"}:
            return jsonify({"error": "无效 Codex 推理强度"}), 400
        if "codex_model" in updates and (not isinstance(updates["codex_model"], str) or len(updates["codex_model"]) > 128):
            return jsonify({"error": "无效 Codex 模型名称"}), 400
        if "chat_web_search_mode" in updates:
            updates["chat_web_search_mode"] = normalize_web_search_mode(
                updates["chat_web_search_mode"]
            )
        if (
            "image_provider" in updates
            and updates["image_provider"] not in IMAGE_PROVIDER_META
        ):
            return jsonify(
                {"error": f"未知图片生成渠道: {updates['image_provider']}"}
            ), 400
        if not config_manager.save_config(updates):
            return jsonify({"error": "配置写入失败"}), 500
        return jsonify({"success": True})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
