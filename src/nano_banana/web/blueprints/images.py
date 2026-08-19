import base64
import os
import tempfile
from io import BytesIO

from flask import Blueprint, jsonify, request

from nano_banana.core.images import (
    create_image_provider_from_credentials,
    get_image_provider_capabilities,
)
from nano_banana.core.images.provider_config import IMAGE_PROVIDER_META
from nano_banana.web.context import config_manager

bp = Blueprint("images", __name__)


@bp.get("/api/image-providers")
def get_image_providers():
    providers = {}
    for provider, meta in IMAGE_PROVIDER_META.items():
        credentials = config_manager.get_image_provider_config(provider)
        configured_model = credentials["model"]
        models = list(meta.get("model_suggestions") or [])
        if configured_model and configured_model not in models:
            models.append(configured_model)
        providers[provider] = {
            "label": meta["label"],
            "models": models,
            "default_model": meta.get("default_model") or "",
            "configured_model": configured_model,
            "model_config_key": meta["config_keys"]["model"],
            "has_api_key": bool(credentials["api_key"]),
            "is_configured": all(
                credentials.get(key) for key in ("base_url", "api_key", "model")
            ),
            "capabilities": {
                model: get_image_provider_capabilities(provider, model)
                for model in models
            },
        }
    return jsonify(providers)


@bp.post("/api/image-generation-settings")
def save_image_generation_settings():
    payload = request.json or {}
    provider = payload.get("provider")
    model = payload.get("model")
    options = payload.get("options")
    if provider not in IMAGE_PROVIDER_META:
        return jsonify({"error": f"未知图片生成渠道: {provider}"}), 400
    if not isinstance(model, str) or not model.strip():
        return jsonify({"error": "图片模型不能为空"}), 400
    if options is not None and not isinstance(options, dict):
        return jsonify({"error": "生成参数必须是 JSON 对象"}), 400
    model = model.strip()
    if not config_manager.set_active_image_selection(provider, model):
        return jsonify({"error": "图片渠道选择保存失败"}), 500
    if options is not None and not config_manager.save_image_generation_options(
        provider, model, options
    ):
        return jsonify({"error": "图片生成参数保存失败"}), 500
    return jsonify({"success": True})


@bp.post("/api/generate-image")
def generate_image():
    temp_files = []
    try:
        data = request.json or {}
        prompt = data.get("prompt", "")
        images = data.get("images", [])
        options = data.get("options") or {}
        provider = data.get("provider") or config_manager.get_image_provider()
        if provider not in IMAGE_PROVIDER_META:
            return jsonify({"error": f"未知图片生成渠道: {provider}"}), 400

        credentials = config_manager.get_image_provider_config(provider)
        model = (data.get("model") or credentials["model"]).strip()
        if not model:
            return jsonify({"error": "图片模型不能为空"}), 400
        credentials["model"] = model
        if not options:
            options = {
                "aspect_ratio": data.get("aspect_ratio", "1:1"),
                "image_size": data.get("image_size", "2K"),
                "thinking_level": data.get("thinking_level", "low"),
            }
        if not prompt:
            return jsonify({"error": "提示词不能为空"}), 400

        processed_images = []
        if images:
            for img_str in images:
                if isinstance(img_str, str) and img_str.startswith("data:"):
                    try:
                        header, encoded = img_str.split(";base64,")
                        mime_type = header.split(":")[1]
                        ext_map = {
                            "image/jpeg": ".jpg",
                            "image/png": ".png",
                            "image/webp": ".webp",
                            "image/gif": ".gif",
                            "image/bmp": ".bmp",
                        }
                        ext = ext_map.get(mime_type, ".jpg")
                        img_data = base64.b64decode(encoded)
                        fd, path = tempfile.mkstemp(suffix=ext)
                        with os.fdopen(fd, "wb") as handle:
                            handle.write(img_data)
                        temp_files.append(path)
                        processed_images.append(path)
                    except Exception as exc:  # noqa: BLE001
                        print(f"Error processing image: {exc}")
                        processed_images.append(img_str)
                else:
                    processed_images.append(img_str)

        client = create_image_provider_from_credentials(
            provider,
            credentials["base_url"],
            credentials["api_key"],
            model,
        )
        client.set_generation_options(options)
        config_manager.set_active_image_selection(provider, model)
        config_manager.save_image_generation_options(provider, model, options)
        generated_image = client.generate_image(
            text=prompt,
            images=processed_images if processed_images else None,
        )
        if generated_image:
            buffered = BytesIO()
            generated_image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            return jsonify({"image": f"data:image/png;base64,{img_str}"})
        return jsonify({"error": "生成图片失败，未返回图片数据"}), 500
    except Exception as exc:  # noqa: BLE001
        print(f"Generate Image Error: {exc}")
        return jsonify({"error": str(exc)}), 500
    finally:
        for path in temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as exc:  # noqa: BLE001
                print(f"Error removing temp file {path}: {exc}")
