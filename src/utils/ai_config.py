"""AI API 配置管理。对话 AI 与图片生成渠道使用相互独立的配置。"""
from copy import deepcopy
from typing import Any

import yaml
from utils.resource_path import get_resource_path

from components.image_provider_config import IMAGE_PROVIDER_META, extract_provider_credentials


class AIConfigManager:
    """管理AI API配置的保存和加载"""
    
    DEFAULT_CONFIG = {
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-5.1",
        "chat_web_search_mode": "auto",
        "image_provider": "gemini",
        "gemini_base_url": "",
        "gemini_api_key": "",
        "gemini_model": "gemini-3-pro-image-preview",
        "openai_image_base_url": "https://api.openai.com/v1",
        "openai_image_api_key": "",
        "openai_image_model": "gpt-image-2",
        "qwen_image_base_url": "",
        "qwen_image_api_key": "",
        "qwen_image_model": "qwen-image-3.0-pro",
        "doubao_image_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "doubao_image_api_key": "",
        "doubao_image_model": "doubao-seedream-5-0-pro-260628",
        "image_generation_options": {},
    }
    
    def __init__(self):
        self.config_path = get_resource_path("config/ai_config.yaml")
        self._ensure_config_exists()
    
    def _ensure_config_exists(self):
        """确保配置文件目录存在"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
    
    def load_config(self) -> dict:
        """加载AI配置"""
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data:
                        result = {}
                        for key, default in self.DEFAULT_CONFIG.items():
                            fallback = deepcopy(default) if isinstance(default, dict) else ""
                            result[key] = data.get(key, fallback)
                        return result
        except Exception as e:
            print(f"加载AI配置失败: {e}")
        # 如果配置文件不存在或加载失败，返回所有字段为空字符串
        return {
            key: deepcopy(default) if isinstance(default, dict) else ""
            for key, default in self.DEFAULT_CONFIG.items()
        }
    
    def save_config(self, config: dict, merge_existing: bool = True) -> bool:
        """保存AI配置，默认保留已有字段"""
        try:
            data_to_save = {}
            if merge_existing and self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    existing = yaml.safe_load(f) or {}
                    if isinstance(existing, dict):
                        data_to_save.update(existing)
            data_to_save.update(config)

            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    data_to_save,
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False,
                )
            return True
        except Exception as e:
            print(f"保存AI配置失败: {e}")
            return False
    
    def is_configured(self) -> bool:
        """检查 AI 对话服务是否已配置。"""
        return bool(self.get_chat_config()["api_key"])

    def get_chat_config(self) -> dict[str, str]:
        """获取只供提示词生成/修改使用的 OpenAI-compatible 配置。"""
        config = self.load_config()
        return {
            "base_url": (config.get("base_url") or "").strip(),
            "api_key": (config.get("api_key") or "").strip(),
            "model": (config.get("model") or "").strip(),
        }
    
    def get_base_url(self) -> str:
        return self.load_config().get("base_url", "")
    
    def get_api_key(self) -> str:
        return self.load_config().get("api_key", "")
    
    def get_model(self) -> str:
        return self.load_config().get("model", "")

    def get_gemini_config(self) -> dict:
        config = self.load_config()
        return {
            "base_url": config.get("gemini_base_url", ""),
            "api_key": config.get("gemini_api_key", ""),
            "model": config.get("gemini_model", ""),
        }

    def get_image_provider(self) -> str:
        return self.load_config().get("image_provider", "") or "gemini"

    def get_image_provider_config(self, provider: str) -> dict[str, str]:
        """获取指定图片渠道的独立连接配置。"""
        return extract_provider_credentials(self.load_config(), provider)

    def is_image_provider_configured(self, provider: str | None = None) -> bool:
        """检查指定（默认当前）图片渠道的连接信息是否完整。"""
        provider = provider or self.get_image_provider()
        image_config = self.get_image_provider_config(provider)
        return all(
            image_config.get(key)
            for key in ("base_url", "api_key", "model")
        )

    def get_image_providers_with_api_key(self) -> list[str]:
        """按界面定义顺序返回已填写 API 密钥的图片渠道。"""
        return [
            provider
            for provider in IMAGE_PROVIDER_META
            if self.get_image_provider_config(provider)["api_key"]
        ]

    def set_active_image_selection(self, provider: str, model: str | None = None) -> bool:
        """保存主界面当前使用的图片渠道和模型，不改动任何凭证。"""
        meta = IMAGE_PROVIDER_META.get(provider)
        if not meta:
            raise ValueError(f"未知图片生成渠道: {provider}")
        config: dict[str, str] = {"image_provider": provider}
        if model is not None:
            config[meta["config_keys"]["model"]] = model.strip()
        return self.save_config(config)

    @staticmethod
    def _options_model_key(model: str) -> str:
        return model.strip() or "__default__"

    def get_image_generation_options(self, provider: str, model: str = "") -> dict[str, Any]:
        """读取指定渠道/模型上次使用的生成参数。"""
        all_options = self.load_config().get("image_generation_options") or {}
        if not isinstance(all_options, dict):
            return {}
        provider_options = all_options.get(provider) or {}
        if not isinstance(provider_options, dict):
            return {}
        options = provider_options.get(self._options_model_key(model)) or {}
        return deepcopy(options) if isinstance(options, dict) else {}

    def save_image_generation_options(
        self,
        provider: str,
        model: str,
        options: dict[str, Any],
    ) -> bool:
        """保存指定渠道/模型的生成参数偏好。"""
        if provider not in IMAGE_PROVIDER_META:
            raise ValueError(f"未知图片生成渠道: {provider}")
        config = self.load_config()
        all_options = config.get("image_generation_options") or {}
        if not isinstance(all_options, dict):
            all_options = {}
        all_options = deepcopy(all_options)
        provider_options = all_options.setdefault(provider, {})
        provider_options[self._options_model_key(model)] = deepcopy(options)
        return self.save_config({"image_generation_options": all_options})

    def get_openai_image_config(self) -> dict:
        config = self.load_config()
        return {
            "base_url": config.get("openai_image_base_url", ""),
            "api_key": config.get("openai_image_api_key", ""),
            "model": config.get("openai_image_model", "") or "gpt-image-2",
        }

    def get_qwen_image_config(self) -> dict:
        config = self.load_config()
        return {
            "base_url": config.get("qwen_image_base_url", ""),
            "api_key": config.get("qwen_image_api_key", ""),
            "model": config.get("qwen_image_model", "") or "qwen-image-3.0-pro",
        }

    def get_doubao_image_config(self) -> dict:
        config = self.load_config()
        return {
            "base_url": config.get("doubao_image_base_url", "")
            or "https://ark.cn-beijing.volces.com/api/v3",
            "api_key": config.get("doubao_image_api_key", ""),
            "model": config.get("doubao_image_model", "")
            or "doubao-seedream-5-0-pro-260628",
        }

    def get_active_image_config(
        self,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict:
        """获取生图配置；可用界面快照覆盖当前渠道/模型。"""
        config = self.load_config()
        provider = provider or config.get("image_provider", "") or "gemini"
        if provider not in IMAGE_PROVIDER_META:
            raise ValueError(f"未知图片生成渠道: {provider}")

        image_config = extract_provider_credentials(config, provider)
        if model is not None:
            image_config["model"] = model.strip() or image_config["model"]
        return {
            "provider": provider,
            **image_config,
        }

    def get_gemini_base_url(self) -> str:
        return self.get_gemini_config().get("base_url", "")

    def get_gemini_api_key(self) -> str:
        return self.get_gemini_config().get("api_key", "")

    def get_gemini_model(self) -> str:
        return self.get_gemini_config().get("model", "")
