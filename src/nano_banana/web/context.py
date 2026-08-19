"""Web 共享管理器。"""

from nano_banana.core.config import AIConfigManager
from nano_banana.core.presets import PresetManager
from nano_banana.core.schema import get_schema
from nano_banana.core.yaml_handler import YamlHandler

yaml_handler = YamlHandler()
preset_manager = PresetManager()
config_manager = AIConfigManager()
CATEGORY_PRESET_SCOPES = set(get_schema().category_ids)
