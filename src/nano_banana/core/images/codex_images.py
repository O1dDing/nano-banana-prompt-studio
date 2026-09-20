"""Codex 套餐图片通道。尺寸/质量为请求意图，不伪装成 Images API 原生控制。"""
from __future__ import annotations

import base64
import json
import threading
from copy import deepcopy

from nano_banana.core.codex_client import CodexBridge
from nano_banana.core.images.artifacts import image_data_url, image_from_bytes
from nano_banana.core.images.gpt_options import capabilities as api_capabilities, normalize_options
from nano_banana.core.images.protocol import encode_image_reference


CODEX_IMAGE_MODEL = "gpt-image-2"


def capabilities():
    caps = api_capabilities(CODEX_IMAGE_MODEL)
    caps.update(label="Codex Image", parameter_control="prompt_hints",
                max_reference_images=3, experimental=True,
                notice="不单独收 API 费；消耗 Codex 额度。尺寸/质量/背景为提示性要求，非硬参数；不放大冒充。模型由 Codex 内置工具决定，不能选择 Image 2.5。返回格式必要时在本地转换。")
    opts = caps["options"]
    opts.pop("moderation")
    opts.pop("n")
    opts["quality"]["label"] = "生成质量意图"
    opts["size"]["label"] = "期望像素尺寸"
    opts["background"]["label"] = "背景意图"
    opts["output_format"]["label"] = "交付格式"
    return caps


class CodexImageProvider:
    provider = "codex_images"
    CAPABILITIES = capabilities()

    def __init__(self, *, model=CODEX_IMAGE_MODEL, codex_model="", codex_effort="auto", codex_identity=None):
        if model != CODEX_IMAGE_MODEL:
            raise ValueError("Codex 内置生图不能指定 Image 2.5 或其他 Image 模型；请选择 OpenAI Images API")
        self.model, self.codex_model, self.codex_effort = model, codex_model, codex_effort
        self.codex_identity = codex_identity
        self.options = {}
        self.generated_images = []
        self.result_metadata = {}
        self.cancelled = threading.Event()

    def set_generation_options(self, options):
        unknown = set(options) - set(self.CAPABILITIES["options"])
        if unknown:
            raise ValueError("Codex Image 不支持这些原生参数：" + ", ".join(sorted(unknown)))
        self.options = normalize_options(options, CODEX_IMAGE_MODEL)

    def generate_image(self, text, images=None):
        if len(images or []) > 3:
            raise ValueError("Codex Image 当前最多接收 3 张参考图")
        options = self.options or normalize_options({}, self.model)
        constraints = {key: options[key] for key in ("size", "quality", "background")}
        instruction = ("$imagegen\nUse the built-in image-generation tool to generate exactly one image. "
                       "Never write scripts, use shell, call a paid Image API, or synthesize a fake image. "
                       "Requested appearance constraints (best effort only): " + json.dumps(constraints) +
                       "\nUser's final image prompt follows. Preserve all constraints, negative instructions, "
                       "reference image identity, composition and requested edits:\n" + text)
        parts = [{"type": "image_url", "image_url": {"url": encode_image_reference(path)}} for path in images or []]
        parts.append({"type": "text", "text": instruction})
        bridge = CodexBridge(identity=self.codex_identity)
        events = bridge.iter_job({"kind": "image", "messages": [{"role": "user", "content": parts}],
                                 "model": self.codex_model, "effort": self.codex_effort,
                                 "web_search_mode": "disabled"}, self.cancelled)
        try:
            result = None
            for item in events:
                if item["status"] == "completed":
                    result = item["result"]
            if not result or not result.get("images"):
                raise RuntimeError("Codex 没有返回原生图片；未调用收费 API")
            # 不读任意 URL/磁盘路径；Bridge 已把受限工作目录中的原生结果规范化。
            self.generated_images = [image_from_bytes(base64.b64decode(value.split(",", 1)[1], validate=True))
                                     for value in result["images"]]
            warnings = ["Codex 的 quality/size/background 仅为提示性要求；未核实原生生成参数。"]
            actual = [f"{img.width}x{img.height}" for img in self.generated_images]
            if options["size"] != "auto" and any(size != options["size"] for size in actual):
                warnings.append(f"期望 {options['size']}；实际 {', '.join(actual)}。未裁切、缩放或放大图片。")
            if options["background"] == "transparent" and any("A" not in img.getbands() for img in self.generated_images):
                warnings.append("原生结果不含透明通道，未伪造透明背景。")
            self.result_metadata = {**result.get("metadata", {}), "actual_sizes": actual,
                "requested_hints": constraints, "warnings": warnings,
                "output_format": options["output_format"], "encoding": "local_conversion_if_needed",
                "native_model_reported": False}
            return self.generated_images[0]
        finally:
            events.close()
            bridge.close()
