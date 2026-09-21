"""OpenAI Images 原生生成/编辑：校验参数、显式 MIME、保留输出字节。"""
from __future__ import annotations

import base64
import os
import inspect
from io import BytesIO
from typing import Any, Optional
from urllib.request import urlopen

from PIL import Image

from nano_banana.core.images.gpt_options import (
    SIZE_MAP as OPENAI_IMAGES_SIZE_MAP,
    capabilities as gpt_capabilities,
    normalize_options,
    resolve_size,
)
from nano_banana.core.images.artifacts import MAX_IMAGE_BYTES, image_from_bytes


class OpenAIImagesProvider:
    provider = "openai_images"
    CAPABILITIES = gpt_capabilities("gpt-image-2")

    def __init__(self, base_url: str, api_key: str, model: str):
        from openai import OpenAI
        self.model = model or "gpt-image-2"
        self.options: dict[str, Any] = {}
        self.generated_images: list[Image.Image] = []
        self.result_metadata: dict[str, Any] = {}
        self.client = OpenAI(api_key=api_key,
                             base_url=base_url.rstrip("/") if base_url else None,
                             timeout=900, max_retries=0)

    def capabilities(self, model: str = "") -> dict[str, Any]:
        return gpt_capabilities(model or self.model)

    def set_generation_options(self, options: dict[str, Any]) -> None:
        self.options = normalize_options(options, self.model)

    def generate_image(self, text: str, images: Optional[list[str]] = None) -> Optional[Image.Image]:
        kwargs = self._build_request_kwargs(text)
        if images:
            response = self._edit_image(images, kwargs)
        else:
            response = self._invoke(self.client.images.generate, kwargs)
        # 不因 TypeError 删除 quality/format 再请求，避免悄悄降级与重复计费。
        self.generated_images = self._extract_images(response)
        self.result_metadata = {"billing": "api", "model": self.model,
                                "parameters": {k: v for k, v in kwargs.items() if k != "prompt"},
                                "actual_sizes": [f"{im.width}x{im.height}" for im in self.generated_images],
                                "encoding": "provider_original_bytes"}
        if kwargs["size"] != "auto":
            width, height = map(int, kwargs["size"].split("x"))
            if width * height > 3686400:
                self.result_metadata["experimental_size"] = True
        return self.generated_images[0] if self.generated_images else None

    def _build_request_kwargs(self, prompt: str) -> dict[str, Any]:
        normalized = normalize_options(self.options, self.model)
        return {"model": self.model, "prompt": prompt, **normalized}

    def _resolve_size(self) -> str:
        return resolve_size(self.options, self.model)

    @staticmethod
    def _invoke(method, kwargs):
        # SDK 1.x 可能尚未声明 edit.moderation 等新字段；完整传给原生接口，不丢参数、不重试。
        params = inspect.signature(method).parameters
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            return method(**kwargs)
        known = {k: v for k, v in kwargs.items() if k in params}
        extra = {k: v for k, v in kwargs.items() if k not in params}
        if extra:
            known["extra_body"] = extra
        return method(**known)

    @staticmethod
    def _detect_openai_input_mime(image_path: str) -> tuple[str, str]:
        format_map = {"JPEG": ("image/jpeg", ".jpg"), "PNG": ("image/png", ".png"),
                      "WEBP": ("image/webp", ".webp")}
        if os.path.getsize(image_path) >= 50 * 1024 * 1024:
            raise ValueError("每张 OpenAI 参考图必须小于 50 MiB")
        try:
            with Image.open(image_path) as image:
                fmt = (image.format or "").upper()
                image.verify()
        except Exception as exc:
            raise ValueError("无法识别或读取参考图") from exc
        if fmt not in format_map:
            raise ValueError("OpenAI Images 参考图仅支持 JPEG、PNG、WebP")
        mime, ext = format_map[fmt]
        return mime, (os.path.splitext(os.path.basename(image_path))[0] or "image") + ext

    def _edit_image(self, images: list[str], kwargs: dict[str, Any]):
        if not 1 <= len(images) <= 16:
            raise ValueError("OpenAI Images 每次需要 1～16 张参考图")
        opened_files, upload_files = [], []
        try:
            for path in images:
                if not os.path.isfile(path):
                    raise ValueError("OpenAI Images 编辑模式需要本地图片文件路径")
                mime, name = self._detect_openai_input_mime(path)
                handle = open(path, "rb")
                opened_files.append(handle)
                upload_files.append((name, handle, mime))
            image_arg = upload_files[0] if len(upload_files) == 1 else upload_files
            return self._invoke(self.client.images.edit, {"image": image_arg, **kwargs})
        finally:
            for handle in opened_files:
                handle.close()

    @staticmethod
    def _extract_images(response) -> list[Image.Image]:
        result = []
        for item in getattr(response, "data", None) or []:
            b64 = getattr(item, "b64_json", None)
            url = getattr(item, "url", None)
            if b64:
                if len(b64) > MAX_IMAGE_BYTES * 4 // 3 + 16:
                    raise ValueError("图片响应过大")
                raw = base64.b64decode(b64, validate=True)
            elif url:
                if not str(url).startswith("https://"):
                    raise ValueError("图片下载地址必须是 HTTPS")
                with urlopen(url, timeout=120) as resp:
                    raw = resp.read(MAX_IMAGE_BYTES + 1)
            else:
                continue
            result.append(image_from_bytes(raw))
        return result

    @staticmethod
    def _extract_image(response) -> Optional[Image.Image]:
        images = OpenAIImagesProvider._extract_images(response)
        return images[0] if images else None
