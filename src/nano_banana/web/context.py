"""Web 管理器：旧单用户/管理员使用原数据；个人页签使用独立临时数据。"""
from werkzeug.local import LocalProxy
from nano_banana.core.config import AIConfigManager
from nano_banana.core.presets import PresetManager
from nano_banana.core.schema import get_schema
from nano_banana.core.yaml_handler import YamlHandler

_legacy = {'yaml_handler': YamlHandler(), 'preset_manager': PresetManager(),
           'config_manager': AIConfigManager()}


def _manager(name):
    from nano_banana.web.user_sessions import current_scope
    scope = current_scope()
    return getattr(scope, name) if scope is not None and not scope.owner else _legacy[name]


yaml_handler = LocalProxy(lambda: _manager('yaml_handler'))
preset_manager = LocalProxy(lambda: _manager('preset_manager'))
config_manager = LocalProxy(lambda: _manager('config_manager'))
CATEGORY_PRESET_SCOPES = set(get_schema().category_ids)
