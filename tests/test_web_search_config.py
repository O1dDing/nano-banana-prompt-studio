from nano_banana.core.config import flatten_legacy_or_nested, nest_config


def test_web_search_mode_round_trip_in_nested_chat_config():
    nested = {
        "chat": {
            "base_url": "https://api.example/v1",
            "api_key": "secret",
            "model": "model",
            "web_search_mode": "force",
        },
        "image": {"active": "gemini", "providers": {}, "options": {}},
    }
    flat = flatten_legacy_or_nested(nested)
    assert flat["chat_web_search_mode"] == "force"
    rebuilt = nest_config(flat)
    assert rebuilt["chat"]["web_search_mode"] == "force"
