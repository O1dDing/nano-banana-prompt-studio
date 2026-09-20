import json
from collections.abc import Iterator
from typing import Any

from flask import Blueprint, Response, jsonify, request

from nano_banana.core.chat import (
    build_generate_messages,
    build_modify_messages,
    create_chat_client,
)
from nano_banana.core.web_search import iter_stage1_events
from nano_banana.core.codex_client import iter_prompt_sse
from nano_banana.core.codex_schema import prompt_output_schema
from nano_banana.core.chat import strip_code_fences
from nano_banana.web.context import config_manager

bp = Blueprint("chat", __name__)


def _format_error(exc: Exception) -> str:
    message = str(exc)
    lower = message.lower()
    if "401" in message or "unauthorized" in lower:
        return "API密钥无效或已过期，请检查配置"
    if "429" in message or "rate" in lower:
        return "请求过于频繁，请稍后再试"
    if "timeout" in lower:
        return "请求超时，请检查网络连接或稍后再试"
    if "connect" in lower:
        return f"网络连接失败: {message}"
    return message


def _iter_stage1_sse(
    messages: list[dict[str, Any]],
    chat: dict[str, str],
) -> Iterator[str]:
    http_client = None
    try:
        client, http_client = create_chat_client(
            base_url=chat["base_url"],
            api_key=chat["api_key"],
            timeout=180,
        )
        yield f"data: {json.dumps({'status': 'started'})}\n\n"
        thinking_reported = False
        for event in iter_stage1_events(
            client=client,
            base_url=chat["base_url"],
            api_key=chat["api_key"],
            model=chat["model"] or "gpt-4o-mini",
            messages=messages,
            web_search_mode=chat.get("web_search_mode", "auto"),
        ):
            if event.type == "thinking" and not thinking_reported:
                thinking_reported = True
                yield f"data: {json.dumps({'status': 'thinking'})}\n\n"
            elif event.type == "content" and event.text:
                yield f"data: {json.dumps({'content': event.text})}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:  # noqa: BLE001
        yield f"data: {json.dumps({'error': _format_error(exc)})}\n\n"
    finally:
        if http_client is not None:
            http_client.close()


def _sse_from_messages(messages: list[dict[str, Any]], current_data=None):
    chat = config_manager.get_chat_config()
    from nano_banana.web.user_sessions import codex_identity, current_scope
    chat['_codex_identity'] = codex_identity()
    scope = current_scope()
    chat['_cancelled'] = scope.closed if scope else None
    if chat.get("engine") == "codex":
        current = None
        if isinstance(current_data, str):
            try:
                current, _ = json.JSONDecoder().raw_decode(strip_code_fences(current_data).lstrip())
            except (ValueError, TypeError):
                pass
        response = Response(iter_prompt_sse(messages, chat, prompt_output_schema(current)), mimetype="text/event-stream")
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Accel-Buffering"] = "no"
        return response
    if not chat["api_key"]:
        return jsonify({"error": "请先配置API密钥"}), 400
    if not chat["base_url"]:
        return jsonify({"error": "请先配置Base URL"}), 400
    if not chat["model"]:
        return jsonify({"error": "请先配置模型名称"}), 400

    response = Response(
        _iter_stage1_sse(messages, chat),
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
        return _sse_from_messages(messages, current_data=current_data)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
