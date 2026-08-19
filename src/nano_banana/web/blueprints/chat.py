from flask import Blueprint, Response, jsonify, request

from nano_banana.core.chat import (
    build_generate_messages,
    build_modify_messages,
    iter_sse_response,
)
from nano_banana.web.context import config_manager

bp = Blueprint("chat", __name__)


def _sse_from_messages(messages):
    chat = config_manager.get_chat_config()
    if not chat["api_key"]:
        return jsonify({"error": "请先配置API密钥"}), 400
    response = Response(
        iter_sse_response(
            messages,
            base_url=chat["base_url"],
            api_key=chat["api_key"],
            model=chat["model"] or "gpt-4o-mini",
        ),
        mimetype="text/event-stream",
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@bp.post("/api/generate")
def generate_prompt():
    try:
        data = request.json or {}
        user_prompt = data.get("prompt", "")
        images = data.get("images", [])
        if not user_prompt and not images:
            return jsonify({"error": "请提供文字描述或参考图片"}), 400
        messages = build_generate_messages(user_prompt, images)
        return _sse_from_messages(messages)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.post("/api/modify")
def modify_prompt():
    try:
        data = request.json or {}
        current_data = data.get("current_data", "")
        modify_request = data.get("modify_request", "")
        images = data.get("images", [])
        if not current_data or not modify_request:
            return jsonify({"error": "当前数据和修改要求不能为空"}), 400
        messages = build_modify_messages(current_data, modify_request, images)
        return _sse_from_messages(messages)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
