"""兼容入口：python src/web/app.py"""

from nano_banana.core.images import create_image_provider_from_credentials
from nano_banana.web.app import app, main
from nano_banana.web.context import config_manager, preset_manager, yaml_handler

__all__ = [
    "app",
    "config_manager",
    "create_image_provider_from_credentials",
    "main",
    "preset_manager",
    "yaml_handler",
]

if __name__ == "__main__":
    main()
