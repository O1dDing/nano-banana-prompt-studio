"""保留图像 API 的原始输出字节；其他渠道使用明确标注的本地编码。"""
from __future__ import annotations
import base64
from io import BytesIO
from typing import Any
from PIL import Image

MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
MAX_IMAGE_BYTES = 64 * 1024 * 1024


def image_from_bytes(data: bytes) -> Image.Image:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("返回的图片为空或超过 64 MiB")
    with Image.open(BytesIO(data)) as raw:
        if raw.format not in MIME:
            raise ValueError("返回的图片不是 PNG/JPEG/WebP")
        if raw.width * raw.height > 40_000_000:
            raise ValueError("返回的图片像素过大")
        mime = MIME[raw.format]
        raw.load()
        image = raw.copy()
    image.info["nano_native_bytes"] = data
    image.info["nano_native_mime"] = mime
    return image


def image_data_url(image: Image.Image, *, output_format: str | None = None,
                   compression: int | None = None) -> str:
    native = image.info.get("nano_native_bytes")
    mime = image.info.get("nano_native_mime")
    wanted = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}.get(output_format)
    if native and mime in MIME.values() and (not wanted or wanted == mime) and compression is None:
        return f"data:{mime};base64," + base64.b64encode(native).decode("ascii")
    fmt = (output_format or "png").upper()
    if fmt not in MIME:
        raise ValueError("未知输出格式")
    target = image
    if fmt == "JPEG" and image.mode not in ("RGB", "L"):
        if "A" in image.getbands():
            target = Image.new("RGB", image.size, "white")
            target.paste(image, mask=image.getchannel("A"))
        else:
            target = image.convert("RGB")
    kwargs: dict[str, Any] = {}
    if fmt in {"JPEG", "WEBP"}:
        kwargs["quality"] = 100 if compression is None else compression
    buf = BytesIO()
    target.save(buf, format=fmt, **kwargs)
    return f"data:{MIME[fmt]};base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def reference_bytes(raw: bytes) -> bytes:
    """普通上传格式统一成可供模型读取的图片；不改变像素尺寸。"""
    try:
        image_from_bytes(raw)
        return raw
    except ValueError:
        if len(raw) > MAX_IMAGE_BYTES:
            raise
        with Image.open(BytesIO(raw)) as img:
            if img.format not in {"BMP", "GIF", "TIFF", "AVIF"} or img.width * img.height > 40_000_000:
                raise ValueError("参考图格式不支持或像素过大")
            # 动图按静态参考图处理，只取首帧，与工作台静态生图用途一致。
            img.seek(0)
            converted = img.convert("RGBA" if "A" in img.getbands() or "transparency" in img.info else "RGB")
            output = BytesIO()
            converted.save(output, format="PNG")
            return output.getvalue()
