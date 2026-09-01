"""OpenAI-compatible 流式聊天，无 Qt 依赖。"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from nano_banana.core.images.protocol import encode_image_reference
from nano_banana.core.prompts import MODIFY_SYSTEM_PROMPT, SYSTEM_PROMPT


CancelledFn = Callable[[], bool]


@dataclass(frozen=True)
class ChatEvent:
    type: str
    text: str = ""


def create_chat_client(*, base_url: str, api_key: str, timeout: float = 180):
    """立刻构造客户端（SSE 要在上游 create 之前先把 started 发出去）。"""
    from openai import OpenAI
    import httpx

    http_client = httpx.Client(http2=False)
    client = OpenAI(
        api_key=api_key,
        base_url=(base_url or "").rstrip("/"),
        timeout=timeout,
        http_client=http_client,
    )
    return client, http_client


def iter_completion_events(
    client,
    messages: list[dict[str, Any]],
    *,
    model: str,
    cancelled: CancelledFn | None = None,
) -> Iterator[ChatEvent]:
    thinking_reported = False
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
    )
    full_content = ""
    for chunk in stream:
        if cancelled and cancelled():
            yield ChatEvent("error", "已取消")
            return
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        reasoning_content = getattr(delta, "reasoning_content", None)
        if reasoning_content and not thinking_reported:
            thinking_reported = True
            yield ChatEvent("thinking")
        if delta and delta.content:
            full_content += delta.content
            yield ChatEvent("content", delta.content)
    yield ChatEvent("done", full_content)


def stream_chat(
    messages: list[dict[str, Any]],
    *,
    base_url: str,
    api_key: str,
    model: str,
    cancelled: CancelledFn | None = None,
    timeout: float = 180,
) -> Iterator[ChatEvent]:
    """向 OpenAI-compatible chat completions 发流式请求。"""
    if not api_key:
        yield ChatEvent("error", "请先配置API密钥")
        return
    if not (base_url or "").strip():
        yield ChatEvent("error", "请先配置Base URL")
        return
    if not (model or "").strip():
        yield ChatEvent("error", "请先配置模型名称")
        return

    try:
        client, http_client = create_chat_client(
            base_url=base_url, api_key=api_key, timeout=timeout
        )
    except ImportError as exc:
        yield ChatEvent("error", f"openai 导入失败: {exc}")
        return

    try:
        yield from iter_completion_events(
            client, messages, model=model, cancelled=cancelled
        )
    except Exception as exc:  # noqa: BLE001
        yield ChatEvent("error", _format_chat_error(exc))
    finally:
        http_client.close()


def iter_sse_response(
    messages: list[dict[str, Any]],
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float = 180,
) -> Iterator[str]:
    """Web SSE：先构造客户端并发送 started，再打上游。"""
    client, http_client = create_chat_client(
        base_url=base_url, api_key=api_key, timeout=timeout
    )
    try:
        yield f"data: {json.dumps({'status': 'started'})}\n\n"
        yield from iter_sse(
            iter_completion_events(client, messages, model=model),
            include_started=False,
        )
    except Exception as exc:  # noqa: BLE001
        yield f"data: {json.dumps({'error': _format_chat_error(exc)})}\n\n"
    finally:
        http_client.close()


def build_generate_messages(
    user_prompt: str,
    images: list[str] | None = None,
) -> list[dict[str, Any]]:
    user_content = _multimodal_user_content(
        images or [],
        text_with_images=f"请根据以下描述和参考图片生成提示词：\n\n{user_prompt}",
        text_only=f"请根据以下描述生成提示词：\n\n{user_prompt}",
        images_only="请根据参考图片生成提示词。",
        require_any=True,
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_modify_messages(
    current_data: str,
    modify_request: str,
    images: list[str] | None = None,
) -> list[dict[str, Any]]:
    text_content = (
        f"当前提示词：\n{current_data}\n\n修改要求：{modify_request}\n\n请返回修改后的JSON提示词:"
    )
    user_content = _multimodal_user_content(
        images or [],
        text_with_images=text_content,
        text_only=text_content,
        images_only=text_content,
        require_any=False,
    )
    return [
        {"role": "system", "content": MODIFY_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def iter_sse(events: Iterator[ChatEvent], *, include_started: bool = True) -> Iterator[str]:
    """把 ChatEvent 转成 SSE 行，匹配现有 Web 前端协议。"""
    if include_started:
        yield f"data: {json.dumps({'status': 'started'})}\n\n"
    for event in events:
        if event.type == "thinking":
            yield f"data: {json.dumps({'status': 'thinking'})}\n\n"
        elif event.type == "content":
            yield f"data: {json.dumps({'content': event.text})}\n\n"
        elif event.type == "error":
            yield f"data: {json.dumps({'error': event.text})}\n\n"
            return
        elif event.type == "done":
            yield "data: [DONE]\n\n"
            return
    yield "data: [DONE]\n\n"


def _multimodal_user_content(
    images: list[str],
    *,
    text_with_images: str,
    text_only: str,
    images_only: str,
    require_any: bool,
) -> Any:
    parts: list[dict[str, Any]] = []
    for image_ref in images:
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": encode_image_reference(image_ref)},
            }
        )
    if parts and (text_with_images or "").strip():
        parts.append({"type": "text", "text": text_with_images})
        return parts
    if parts:
        parts.append({"type": "text", "text": images_only})
        return parts
    if (text_only or "").strip():
        return text_only
    if require_any:
        raise ValueError("请提供文字描述或参考图片")
    return text_only


def strip_code_fences(content: str) -> str:
    """剥离 AI 返回内容外层的 ```json / ``` 围栏。

    模型经常在 JSON 前后加 markdown 代码块标记（有时还带语言名或说明文字），
    直接 json.loads 会失败。
    """
    text = (content or "").strip()
    match = re.search(r"```[ \t]*[\w-]*[ \t]*\r?\n(.*?)\r?\n?[ \t]*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # 只有开头围栏没有闭合（流被截断等情况）
    text = re.sub(r"^```[ \t]*[\w-]*[ \t]*\r?\n?", "", text)
    text = re.sub(r"\r?\n?[ \t]*```$", "", text)
    return text.strip()


def _format_chat_error(exc: Exception) -> str:
    error_msg = str(exc)
    if "401" in error_msg or "Unauthorized" in error_msg:
        return "API密钥无效或已过期，请检查配置"
    if "429" in error_msg or "rate" in error_msg.lower():
        return "请求过于频繁，请稍后再试"
    if "timeout" in error_msg.lower():
        return "请求超时，请检查网络连接或稍后再试"
    if "connect" in error_msg.lower():
        return f"网络连接失败: {error_msg}"
    return f"API调用失败: {error_msg}"
