"""资源路径处理，支持开发环境与 PyInstaller 打包。"""
import sys
from pathlib import Path


def get_base_path() -> Path:
    """
    获取应用基础路径。
    - 开发环境: src/
    - 打包后: exe 所在目录
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def get_repo_root() -> Path:
    if getattr(sys, "frozen", False):
        return get_base_path()
    return Path(__file__).resolve().parents[3]


def get_resource_path(relative_path: str) -> Path:
    return get_base_path() / relative_path


def get_config_path() -> Path:
    return get_resource_path("config/options.yaml")


def get_presets_dir() -> Path:
    return get_resource_path("presets")


def get_images_dir() -> Path:
    if getattr(sys, "frozen", False):
        return get_resource_path("images")
    return get_repo_root() / "images"


def get_schema_path() -> Path:
    return Path(__file__).resolve().parent / "schema.yaml"
