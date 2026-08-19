"""预设管理器"""
import os
import json
from pathlib import Path
from datetime import datetime
from nano_banana.core.resource_path import get_presets_dir


class PresetManager:
    """管理提示词预设的保存和加载"""

    def __init__(self, presets_dir: Path | None = None):
        self.presets_dir = Path(presets_dir) if presets_dir else get_presets_dir()
        self._ensure_dir_exists()

    @staticmethod
    def _safe_name(name: str) -> str:
        """清理文件名中的非法字符。"""
        return "".join(
            c for c in name
            if c.isalnum() or c in (' ', '-', '_', '（', '）', '(', ')')
        ).strip()

    def _get_category_dir(self, scope: str) -> Path | None:
        """返回分类预设目录，拒绝可能逃逸预设目录的 scope。"""
        if not scope or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in scope):
            return None
        return self.presets_dir / "categories" / scope

    def _ensure_dir_exists(self):
        """确保预设目录存在"""
        self.presets_dir.mkdir(parents=True, exist_ok=True)

    def get_all_presets(self) -> list[dict]:
        """获取所有预设列表，返回 [{name, path, modified_time}, ...]"""
        presets = []
        for file in self.presets_dir.glob("*.json"):
            try:
                stat = file.stat()
                presets.append({
                    "name": file.stem,
                    "path": str(file),
                    "modified_time": datetime.fromtimestamp(stat.st_mtime),
                })
            except Exception:
                continue
        # 按修改时间倒序排列
        presets.sort(key=lambda x: x["modified_time"], reverse=True)
        return presets

    def save_preset(self, name: str, data: dict) -> bool:
        """保存预设"""
        try:
            safe_name = self._safe_name(name)
            if not safe_name:
                safe_name = f"preset_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            file_path = self.presets_dir / f"{safe_name}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存预设失败: {e}")
            return False

    def load_preset(self, name: str) -> dict | None:
        """加载预设"""
        try:
            file_path = self.presets_dir / f"{name}.json"
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"加载预设失败: {e}")
        return None

    def delete_preset(self, name: str) -> bool:
        """删除预设"""
        try:
            file_path = self.presets_dir / f"{name}.json"
            if file_path.exists():
                file_path.unlink()
                return True
        except Exception as e:
            print(f"删除预设失败: {e}")
        return False

    def rename_preset(self, old_name: str, new_name: str) -> bool:
        """重命名预设"""
        try:
            old_path = self.presets_dir / f"{old_name}.json"
            new_path = self.presets_dir / f"{new_name}.json"
            if old_path.exists() and not new_path.exists():
                old_path.rename(new_path)
                return True
        except Exception as e:
            print(f"重命名预设失败: {e}")
        return False

    def get_category_presets(self, scope: str) -> list[dict]:
        """获取指定分类的预设列表。"""
        category_dir = self._get_category_dir(scope)
        if category_dir is None or not category_dir.exists():
            return []

        presets = []
        for file in category_dir.glob("*.json"):
            try:
                stat = file.stat()
                presets.append({
                    "name": file.stem,
                    "path": str(file),
                    "modified_time": datetime.fromtimestamp(stat.st_mtime),
                })
            except Exception:
                continue
        presets.sort(key=lambda item: item["modified_time"], reverse=True)
        return presets

    def save_category_preset(self, scope: str, name: str, data: dict) -> bool:
        """保存仅包含一个分类字段的预设。"""
        try:
            category_dir = self._get_category_dir(scope)
            safe_name = self._safe_name(name)
            if category_dir is None or not safe_name or not isinstance(data, dict):
                return False
            category_dir.mkdir(parents=True, exist_ok=True)
            with open(category_dir / f"{safe_name}.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存分类预设失败: {e}")
            return False

    def load_category_preset(self, scope: str, name: str) -> dict | None:
        """加载指定分类预设。"""
        try:
            category_dir = self._get_category_dir(scope)
            safe_name = self._safe_name(name)
            if category_dir is None or not safe_name or safe_name != name:
                return None
            file_path = category_dir / f"{safe_name}.json"
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, dict) else None
        except Exception as e:
            print(f"加载分类预设失败: {e}")
        return None

    def delete_category_preset(self, scope: str, name: str) -> bool:
        """删除指定分类预设。"""
        try:
            category_dir = self._get_category_dir(scope)
            safe_name = self._safe_name(name)
            if category_dir is None or not safe_name or safe_name != name:
                return False
            file_path = category_dir / f"{safe_name}.json"
            if file_path.exists():
                file_path.unlink()
                return True
        except Exception as e:
            print(f"删除分类预设失败: {e}")
        return False
