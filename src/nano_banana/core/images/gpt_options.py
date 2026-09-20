"""GPT Image 的原生参数契约。只校验，不静默降质、改尺寸或更换模型。

规格核对：2026-09-20，OpenAI Images generate/edit reference。
Codex 内置生图并不共享这个参数接口；其软约束在 codex_images 中声明。
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

GPT25_MODELS = ["gpt-image-2.5-sunburst", "gpt-image-2.5-flare"]
GPT_IMAGE_MODELS = ["gpt-image-2", *GPT25_MODELS,
                    "gpt-image-2.5-sunburst-2026-09-08", "gpt-image-2.5-flare-2026-09-08"]
SIZES = ["auto", "1024x1024", "1536x1024", "1024x1536", "1536x864",
         "2048x1152", "1152x2048", "2048x2048", "2560x1440", "1440x2560",
         "3840x2160", "2160x3840", "2880x2880"]
SIZE_LIMITS = {"step": 16, "max_side": 3840, "min_pixels": 655360,
               "max_pixels": 8294400, "max_ratio": 3, "experimental_pixels": 3686400}
# 旧版“档位 + 比例”保留。实际 WIDTHxHEIGHT 始终可见；不把档位当精确边长。
SIZE_MAP = {
    "1K": {"1:1": "1024x1024", "2:3": "1024x1536", "3:2": "1536x1024",
           "3:4": "1024x1360", "4:3": "1360x1024", "4:5": "1024x1280",
           "5:4": "1280x1024", "9:16": "864x1536", "16:9": "1536x864", "21:9": "1792x768"},
    "2K": {"1:1": "2048x2048", "2:3": "1440x2160", "3:2": "2160x1440",
           "3:4": "1536x2048", "4:3": "2048x1536", "4:5": "1600x2000",
           "5:4": "2000x1600", "9:16": "1440x2560", "16:9": "2560x1440", "21:9": "3024x1296"},
    "4K": {"1:1": "2880x2880", "2:3": "2304x3456", "3:2": "3456x2304",
           "3:4": "2448x3264", "4:3": "3264x2448", "4:5": "2560x3200",
           "5:4": "3200x2560", "9:16": "2160x3840", "16:9": "3840x2160", "21:9": "3840x1648"},
}


def is_gpt25(model: str) -> bool:
    return any(model == name or re.fullmatch(re.escape(name) + r"-\d{4}-\d{2}-\d{2}", model)
               for name in GPT25_MODELS)


def flexible_size(model: str) -> bool:
    return is_gpt25(model) or bool(re.fullmatch(r"gpt-image-2(?:-\d{4}-\d{2}-\d{2})?", model))


def validate_size(value: str, model: str = "gpt-image-2") -> str:
    value = str(value).strip().lower()
    if value == "auto":
        return value
    match = re.fullmatch(r"([1-9]\d{0,4})x([1-9]\d{0,4})", value)
    if not match:
        raise ValueError("size 必须为 auto 或 WIDTHxHEIGHT，例如 2048x1152")
    width, height = map(int, match.groups())
    if not flexible_size(model):
        if value not in {"1024x1024", "1536x1024", "1024x1536"}:
            raise ValueError(f"{model} 未声明任意分辨率支持，请使用 1024x1024、1536x1024 或 1024x1536")
        return value
    if width % 16 or height % 16:
        raise ValueError("宽、高都必须是 16 的倍数；不会自动取整或缩放")
    if max(width, height) > 3840:
        raise ValueError("任一边不能超过 3840 像素")
    if max(width, height) > 3 * min(width, height):
        raise ValueError("宽高比必须在 1:3 到 3:1 之间")
    if not 655360 <= width * height <= 8294400:
        raise ValueError("总像素数必须在 655360～8294400 之间（并非支持 3840×3840）")
    return f"{width}x{height}"


def resolve_size(options: dict[str, Any], model: str = "gpt-image-2") -> str:
    direct = str(options.get("size") or "").strip()
    if direct:
        return validate_size(direct, model)
    tier, ratio = options.get("image_size") or "2K", options.get("aspect_ratio") or "1:1"
    if tier not in SIZE_MAP or ratio not in SIZE_MAP[tier]:
        raise ValueError("未知图片档位或宽高比")
    value = SIZE_MAP[tier][ratio]
    if not flexible_size(model):
        a, b = map(int, ratio.split(":"))
        value = "1024x1024" if a == b else ("1536x1024" if a > b else "1024x1536")
    return validate_size(value, model)


def integer_option(value: Any, key: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
        raise ValueError(f"{key} 必须是整数")
    result = int(value)
    if not minimum <= result <= maximum:
        raise ValueError(f"{key} 必须在 {minimum}～{maximum} 之间")
    return result


def normalize_options(options: dict[str, Any], model: str) -> dict[str, Any]:
    if not isinstance(options, dict):
        raise ValueError("图片参数必须是 JSON 对象")
    allowed = {"size", "aspect_ratio", "image_size", "quality", "output_format",
               "output_compression", "background", "moderation", "n"}
    unknown = set(options) - allowed
    if unknown:
        raise ValueError("该图片渠道不支持参数：" + ", ".join(sorted(unknown)))
    out = {"size": resolve_size(options, model), "quality": options.get("quality") or "auto",
           "output_format": options.get("output_format") or "png",
           "background": options.get("background") or "auto",
           "moderation": options.get("moderation") or "auto",
           "n": integer_option(options.get("n", 1), "n", 1, 10)}
    quality = ["auto", "low", "medium", "high"] + (["xhigh", "max"] if is_gpt25(model) else [])
    for key, values in {"quality": quality, "output_format": ["png", "jpeg", "webp"],
                        "background": ["auto", "opaque", "transparent"],
                        "moderation": ["auto", "low"]}.items():
        if out[key] not in values:
            raise ValueError(f"{model} 的 {key} 仅支持：{', '.join(values)}")
    if out["background"] == "transparent" and out["output_format"] == "jpeg":
        raise ValueError("JPEG 不支持透明背景；请选择 PNG 或 WebP")
    compression = options.get("output_compression")
    if compression not in (None, ""):
        out["output_compression"] = integer_option(compression, "output_compression", 0, 100)
        if out["output_format"] == "png":
            raise ValueError("output_compression 仅适用于 JPEG/WebP；PNG 请留空")
    return out


def capabilities(model: str = "gpt-image-2") -> dict[str, Any]:
    quality = ["auto", "low", "medium", "high"] + (["xhigh", "max"] if is_gpt25(model) else [])
    def select(label, default, values):
        return {"label": label, "type": "select", "default": default, "values": values}
    return {"label": "OpenAI Images", "max_reference_images": 16,
        "size_limits": deepcopy(SIZE_LIMITS) if flexible_size(model) else None,
        "size_presets": deepcopy(SIZE_MAP), "parameter_control": "native_api",
        "options": {
            "aspect_ratio": select("宽高比（size 留空时）", "1:1", list(SIZE_MAP["2K"])),
            "image_size": select("尺寸档位（实际像素以 size 为准）", "2K", list(SIZE_MAP)),
            "size": {"label": "精确 size（留空使用上方预设）", "type": "text", "default": "",
                     "values": SIZES if flexible_size(model) else SIZES[:4],
                     "placeholder": "auto / 2048x1152 / 自定义 WIDTHxHEIGHT",
                     "help": "16 的倍数；每边≤3840；比例≤3:1；655360～8294400 像素。>3686400 像素为实验性。"},
            "quality": select("生成质量（API 原生参数）", "auto", quality),
            "output_format": select("输出格式（原始字节保留）", "png", ["png", "jpeg", "webp"]),
            "output_compression": {"label": "JPEG/WebP 压缩参数（留空使用 API 默认）", "type": "number",
                                   "default": "", "min": 0, "max": 100, "step": 1},
            "background": select("背景", "auto", ["auto", "opaque", "transparent"]),
            "moderation": select("审核强度（API 支持值，非关闭审核）", "auto", ["auto", "low"]),
            "n": {"label": "每次生成张数（每张均计费）", "type": "number", "default": 1, "min": 1, "max": 10, "step": 1},
        }}
