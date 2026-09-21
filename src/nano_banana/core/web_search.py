"""第一阶段 Prompt→JSON 的可选联网搜索适配层。

联网并不是 OpenAI-compatible Chat Completions 的统一标准，因此按供应商
选择其原生接口；自动模式在接口不兼容时回退原始 Chat Completions，
强制模式则明确报错，不会伪装成已联网。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator
from urllib.parse import urlparse


VALID_WEB_SEARCH_MODES = {"disabled", "auto", "force"}


@dataclass(frozen=True)
class Stage1Event:
    type: str
    text: str = ""


def normalize_web_search_mode(value: Any) -> str:
    value = str(value or "auto").strip().lower()
    aliases = {
        "off": "disabled",
        "disable": "disabled",
        "disabled": "disabled",
        "禁止联网": "disabled",
        "auto": "auto",
        "自动联网": "auto",
        "on": "force",
        "forced": "force",
        "force": "force",
        "强制联网": "force",
    }
    value = aliases.get(value, value)
    return value if value in VALID_WEB_SEARCH_MODES else "auto"


def _provider(base_url: str) -> str:
    host = (urlparse(base_url or "").hostname or "").lower()
    if host == "generativelanguage.googleapis.com" or (
        host.endswith(".googleapis.com") and "generativelanguage" in host
    ):
        return "gemini"
    if host == "api.anthropic.com" or host.endswith(".anthropic.com"):
        return "anthropic"
    if host.endswith("dashscope.aliyuncs.com") or host.endswith("maas.aliyuncs.com"):
        return "dashscope"
    if host == "api.openai.com" or host.endswith(".openai.com"):
        return "responses"
    if host == "api.x.ai" or host.endswith(".x.ai"):
        return "responses"
    if "volces.com" in host or "volcengine.com" in host:
        return "responses"
    return "generic"


def _chat_stream(
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    extra_body: dict[str, Any] | None = None,
) -> Iterator[Stage1Event]:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if extra_body:
        kwargs["extra_body"] = extra_body

    stream = client.chat.completions.create(**kwargs)
    thinking_sent = False
    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        if not delta:
            continue
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning and not thinking_sent:
            thinking_sent = True
            yield Stage1Event("thinking")
        content = getattr(delta, "content", None)
        if content:
            yield Stage1Event("content", str(content))


def _extract_system_and_user(
    messages: list[dict[str, Any]],
) -> tuple[str, Any]:
    systems: list[str] = []
    users: list[Any] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if role in {"system", "developer"}:
            systems.append(
                content
                if isinstance(content, str)
                else json.dumps(content, ensure_ascii=False)
            )
        elif role == "user":
            users.append(content)
    user: Any = users[0] if len(users) == 1 else users
    return "\n".join(systems), user


def _data_uri(value: str) -> tuple[str, str] | None:
    if (
        not isinstance(value, str)
        or not value.startswith("data:")
        or ";base64," not in value
    ):
        return None
    header, data = value.split(";base64,", 1)
    return header[5:] or "image/png", data


def _responses_input(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if isinstance(content, str):
            parts = [{"type": "input_text", "text": content}]
        else:
            parts: list[dict[str, Any]] = []
            for item in content or []:
                if not isinstance(item, dict):
                    parts.append({"type": "input_text", "text": str(item)})
                    continue
                kind = item.get("type")
                if kind == "text":
                    parts.append({"type": "input_text", "text": item.get("text", "")})
                elif kind == "image_url":
                    url = (item.get("image_url") or {}).get("url", "")
                    if url:
                        parts.append({"type": "input_image", "image_url": url})
            if not parts:
                parts = [{"type": "input_text", "text": ""}]
        result.append({"role": role, "content": parts})
    return result


def _response_output_text(response: Any) -> str:
    direct = getattr(response, "output_text", None)
    if direct:
        return str(direct)
    chunks: list[str] = []
    for item in getattr(response, "output", None) or []:
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", "") in {"output_text", "text"}:
                text = getattr(part, "text", None)
                if text:
                    chunks.append(str(text))
    return "".join(chunks).strip()


def _response_used_search(response: Any) -> bool:
    return any(
        "web_search" in str(getattr(item, "type", "")).lower()
        for item in (getattr(response, "output", None) or [])
    )


def _responses_search(
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    force: bool,
) -> str:
    response = client.responses.create(
        model=model,
        input=_responses_input(messages),
        tools=[{"type": "web_search"}],
        tool_choice="required" if force else "auto",
    )
    if force and not _response_used_search(response):
        raise RuntimeError(
            "API 返回成功，但未检测到 web_search 调用，无法确认强制联网已执行"
        )
    text = _response_output_text(response)
    if not text:
        raise RuntimeError("Responses API 未返回可用文本")
    return text


def _gemini_input(user_content: Any) -> Any:
    if isinstance(user_content, str):
        return user_content
    if (
        isinstance(user_content, list)
        and user_content
        and isinstance(user_content[0], list)
    ):
        flattened: list[Any] = []
        for group in user_content:
            flattened.extend(group if isinstance(group, list) else [group])
        user_content = flattened

    parts: list[dict[str, Any]] = []
    for item in user_content or []:
        if not isinstance(item, dict):
            parts.append({"type": "text", "text": str(item)})
            continue
        if item.get("type") == "text":
            parts.append({"type": "text", "text": item.get("text", "")})
        elif item.get("type") == "image_url":
            url = (item.get("image_url") or {}).get("url", "")
            parsed = _data_uri(url)
            if parsed:
                mime_type, data = parsed
                parts.append(
                    {"type": "image", "data": data, "mime_type": mime_type}
                )
            elif url:
                parts.append({"type": "image", "uri": url})
    return parts or ""


def _gemini_search(
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    force: bool,
) -> str:
    import httpx

    system_text, user_content = _extract_system_and_user(messages)
    payload: dict[str, Any] = {
        "model": model,
        "input": _gemini_input(user_content),
        "tools": [{"type": "google_search"}],
        "generation_config": {"tool_choice": "any" if force else "auto"},
    }
    if system_text:
        payload["system_instruction"] = system_text

    with httpx.Client(http2=False, timeout=180) as http_client:
        response = http_client.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    steps = data.get("steps") or []
    if force and not any(
        isinstance(step, dict) and step.get("type") == "google_search_call"
        for step in steps
    ):
        raise RuntimeError("Gemini 返回成功，但未检测到 google_search_call")

    output: list[str] = []
    for step in steps:
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        for part in step.get("content") or []:
            if (
                isinstance(part, dict)
                and part.get("type") == "text"
                and part.get("text")
            ):
                output.append(part["text"])
    text = "".join(output).strip()
    if not text:
        raise RuntimeError("Gemini Interactions API 未返回可用文本")
    return text


def _anthropic_content(user_content: Any) -> list[dict[str, Any]]:
    if isinstance(user_content, str):
        return [{"type": "text", "text": user_content}]
    if (
        isinstance(user_content, list)
        and user_content
        and isinstance(user_content[0], list)
    ):
        flattened: list[Any] = []
        for group in user_content:
            flattened.extend(group if isinstance(group, list) else [group])
        user_content = flattened

    parts: list[dict[str, Any]] = []
    for item in user_content or []:
        if not isinstance(item, dict):
            parts.append({"type": "text", "text": str(item)})
            continue
        if item.get("type") == "text":
            parts.append({"type": "text", "text": item.get("text", "")})
        elif item.get("type") == "image_url":
            url = (item.get("image_url") or {}).get("url", "")
            parsed = _data_uri(url)
            if parsed:
                mime_type, data = parsed
                parts.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": data,
                        },
                    }
                )
    return parts or [{"type": "text", "text": ""}]


def _anthropic_search(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    force: bool,
) -> str:
    import httpx

    system_text, user_content = _extract_system_and_user(messages)
    endpoint = base_url.rstrip("/") + "/messages"
    conversation: list[dict[str, Any]] = [
        {"role": "user", "content": _anthropic_content(user_content)}
    ]
    tool = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}
    last_data: dict[str, Any] = {}

    with httpx.Client(http2=False, timeout=180) as http_client:
        for _ in range(4):
            payload: dict[str, Any] = {
                "model": model,
                "max_tokens": 8192,
                "messages": conversation,
                "tools": [tool],
                "tool_choice": {"type": "any" if force else "auto"},
            }
            if system_text:
                payload["system"] = system_text
            response = http_client.post(
                endpoint,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            last_data = response.json()
            if last_data.get("stop_reason") != "pause_turn":
                break
            conversation.append(
                {"role": "assistant", "content": last_data.get("content") or []}
            )
        else:
            raise RuntimeError("Anthropic 网页搜索连续 pause_turn，超过继续次数上限")

    content = last_data.get("content") or []
    if force and not any(
        isinstance(block, dict)
        and block.get("type") == "server_tool_use"
        and "web_search" in str(block.get("name", ""))
        for block in content
    ):
        # 某些模型最终回合不重复 server_tool_use；再检查已回传的中间回合。
        used_in_history = any(
            isinstance(block, dict)
            and block.get("type") == "server_tool_use"
            and "web_search" in str(block.get("name", ""))
            for message in conversation
            if message.get("role") == "assistant"
            for block in (message.get("content") or [])
        )
        if not used_in_history:
            raise RuntimeError(
                "Anthropic 返回成功，但未检测到 web_search server_tool_use"
            )

    text = "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()
    if not text:
        raise RuntimeError("Anthropic Messages API 未返回可用文本")
    return text


def iter_stage1_events(
    *,
    client: Any,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    web_search_mode: str,
) -> Iterator[Stage1Event]:
    """统一第一阶段调用入口。"""
    mode = normalize_web_search_mode(web_search_mode)
    if mode == "disabled":
        yield from _chat_stream(client, model, messages)
        return

    provider = _provider(base_url)
    force = mode == "force"

    try:
        if provider == "dashscope":
            yield from _chat_stream(
                client,
                model,
                messages,
                extra_body={
                    "enable_search": True,
                    "search_options": {"forced_search": force},
                },
            )
            return

        yield Stage1Event("thinking")
        if provider == "gemini":
            text = _gemini_search(api_key, model, messages, force)
        elif provider == "anthropic":
            text = _anthropic_search(base_url, api_key, model, messages, force)
        else:
            # OpenAI、xAI、火山方舟，以及实现 Responses 的中转网关。
            text = _responses_search(client, model, messages, force)
        yield Stage1Event("content", text)
    except Exception as exc:
        if mode == "auto":
            print(
                "[stage1-web] auto fallback: "
                f"provider={provider} model={model} error={exc}"
            )
            yield from _chat_stream(client, model, messages)
            return
        raise RuntimeError(
            "强制联网失败：当前模型或 Base URL 不支持可确认的联网搜索。"
            f" provider={provider}, model={model}, error={exc}"
        ) from exc
