"""无 UI 依赖的领域核心。"""

from nano_banana.core.presets import PresetManager
from nano_banana.core.prompt_doc import apply_partial, flatten, nest, subset
from nano_banana.core.schema import PromptSchema, get_schema
from nano_banana.core.yaml_handler import YamlHandler

__all__ = [
    "AIConfigManager",
    "PresetManager",
    "PromptSchema",
    "YamlHandler",
    "apply_partial",
    "flatten",
    "get_schema",
    "nest",
    "subset",
]


def __getattr__(name: str):
    if name == "AIConfigManager":
        from nano_banana.core.config import AIConfigManager

        return AIConfigManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
