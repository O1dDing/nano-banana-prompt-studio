from types import SimpleNamespace

import pytest

from nano_banana.core.web_search import (
    iter_stage1_events,
    normalize_web_search_mode,
)


class FakeChatCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        delta = SimpleNamespace(content='{"ok": true}', reasoning_content=None)
        return [SimpleNamespace(choices=[SimpleNamespace(delta=delta)])]


class FakeResponses:
    def __init__(self, error=None, response=None):
        self.error = error
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def make_client(*, responses_error=None):
    chat_completions = FakeChatCompletions()
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=chat_completions),
        responses=FakeResponses(error=responses_error),
    )
    return client, chat_completions


def base_messages():
    return [
        {"role": "system", "content": "Return JSON"},
        {"role": "user", "content": "Draw a red car"},
    ]


def test_normalize_modes():
    assert normalize_web_search_mode("禁止联网") == "disabled"
    assert normalize_web_search_mode("自动联网") == "auto"
    assert normalize_web_search_mode("强制联网") == "force"
    assert normalize_web_search_mode("unknown") == "auto"


def test_disabled_keeps_original_chat_completion():
    client, chat = make_client()
    events = list(
        iter_stage1_events(
            client=client,
            base_url="https://api.openai.com/v1",
            api_key="key",
            model="model",
            messages=base_messages(),
            web_search_mode="disabled",
        )
    )
    assert [event.text for event in events if event.type == "content"] == [
        '{"ok": true}'
    ]
    assert len(chat.calls) == 1
    assert "extra_body" not in chat.calls[0]


def test_dashscope_uses_native_search_extension():
    client, chat = make_client()
    list(
        iter_stage1_events(
            client=client,
            base_url="https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            api_key="key",
            model="qwen3.8-max",
            messages=base_messages(),
            web_search_mode="force",
        )
    )
    assert chat.calls[0]["extra_body"] == {
        "enable_search": True,
        "search_options": {"forced_search": True},
    }


def test_generic_auto_falls_back_to_chat_completion():
    client, chat = make_client(responses_error=RuntimeError("no responses endpoint"))
    events = list(
        iter_stage1_events(
            client=client,
            base_url="https://gateway.example/v1",
            api_key="key",
            model="model",
            messages=base_messages(),
            web_search_mode="auto",
        )
    )
    assert any(event.type == "content" for event in events)
    assert len(chat.calls) == 1


def test_generic_force_reports_incompatible_gateway():
    client, _ = make_client(responses_error=RuntimeError("no responses endpoint"))
    with pytest.raises(RuntimeError, match="强制联网失败"):
        list(
            iter_stage1_events(
                client=client,
                base_url="https://gateway.example/v1",
                api_key="key",
                model="model",
                messages=base_messages(),
                web_search_mode="force",
            )
        )
