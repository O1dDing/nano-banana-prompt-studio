import base64
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

from nano_banana.core.codex_client import bridge_status
from nano_banana.core.images import create_image_provider_from_credentials, get_image_provider_capabilities
from nano_banana.core.images.artifacts import image_data_url, image_from_bytes, reference_bytes
from nano_banana.core.images.codex_images import CodexImageProvider, capabilities as codex_capabilities
from nano_banana.core.images.gpt_options import normalize_options
from nano_banana.web.providers import WEB_PROVIDER_META as IMAGE_PROVIDER_META
from nano_banana.web.context import config_manager
from nano_banana.web.image_tasks import image_task_manager

bp = Blueprint("images", __name__)


@bp.get("/api/codex/status")
def get_codex_status():
    response = jsonify(bridge_status())
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/api/image-providers")
def get_image_providers():
    providers = {}
    for provider, meta in IMAGE_PROVIDER_META.items():
        if provider == "codex_images":
            status = bridge_status()
            providers[provider] = {
                "label": meta["label"], "models": ["gpt-image-2"], "configured_model": "gpt-image-2",
                "default_model": "gpt-image-2", "model_config_key": "codex_image_model",
                "auth_kind": "codex_subscription", "has_api_key": False,
                "is_configured": bool(status.get("logged_in") and status.get("image_available")),
                "capabilities": {"gpt-image-2": codex_capabilities()},
                "status_message": status.get("error") or "原生图片能力仍需首次实际任务验证",
            }
            continue
        credentials = config_manager.get_image_provider_config(provider)
        configured_model = credentials["model"]
        models = list(meta.get("model_suggestions") or [])
        if configured_model and configured_model not in models:
            models.append(configured_model)
        providers[provider] = {
            "label": meta["label"], "models": models, "default_model": meta.get("default_model") or "",
            "configured_model": configured_model, "model_config_key": meta["config_keys"]["model"],
            "has_api_key": bool(credentials["api_key"]), "auth_kind": "api_key",
            "is_configured": all(credentials.get(key) for key in ("base_url", "api_key", "model")),
            "capabilities": {model: get_image_provider_capabilities(provider, model) for model in models},
        }
    response = jsonify(providers)
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.post("/api/image-generation-settings")
def save_image_generation_settings():
    payload = request.json or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "请求体必须是对象"}), 400
    provider, model, options = payload.get("provider"), payload.get("model"), payload.get("options")
    if provider not in IMAGE_PROVIDER_META:
        return jsonify({"error": f"未知图片生成渠道: {provider}"}), 400
    if not isinstance(model, str) or not model.strip():
        return jsonify({"error": "图片模型不能为空"}), 400
    if options is not None and not isinstance(options, dict):
        return jsonify({"error": "生成参数必须是 JSON 对象"}), 400
    model = model.strip()
    if provider == "codex_images" and model != "gpt-image-2":
        return jsonify({"error": "Codex 内置图片模型不可指定，Image 2.5 请使用 API"}), 400
    # 保存未完成的输入草稿可以宽松；真正生成前严格校验，不默默修改参数。
    if not config_manager.set_active_image_selection(provider, model):
        return jsonify({"error": "图片渠道选择保存失败"}), 500
    if options is not None and not config_manager.save_image_generation_options(provider, model, options):
        return jsonify({"error": "图片生成参数保存失败"}), 500
    return jsonify({"success": True})


def _decode_reference_images(images: list[Any], directory: str):
    processed = []
    for index, ref in enumerate(images):
        if not isinstance(ref, str) or not ref.startswith("data:") or ";base64," not in ref:
            raise ValueError("Web 参考图必须通过上传、拖拽或粘贴提供，不接受服务器文件路径")
        raw = reference_bytes(base64.b64decode(ref.split(";base64,", 1)[1], validate=True))
        image = image_from_bytes(raw)
        suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[image.info["nano_native_mime"]]
        path = Path(directory) / f"reference-{index}{suffix}"
        path.write_bytes(raw)
        processed.append(str(path))
    return processed


def _run_image_generation(*, prompt, images, provider, credentials, model, options, cancelled=None):
    # 即使第二张图片损坏，第一张临时文件也一定回收。
    with tempfile.TemporaryDirectory(prefix="nano-reference-") as directory:
        processed = _decode_reference_images(images, directory)
        if provider == "codex_images":
            client = CodexImageProvider(model=model, codex_model=credentials.get("codex_model", ""),
                                        codex_effort=credentials.get("codex_effort") or "auto")
            if cancelled is not None:
                client.cancelled = cancelled
        else:
            client = create_image_provider_from_credentials(provider, credentials["base_url"], credentials["api_key"], model)
        client.set_generation_options(options)
        generated = client.generate_image(text=prompt, images=processed or None)
        if generated is None:
            raise RuntimeError("生成图片失败，未返回图片数据")
        all_images = getattr(client, "generated_images", None) or [generated]
        # API 已返回所选格式的原始字节：不二次编码。Codex 格式转换明确为本地后处理。
        local_conversion = provider == "codex_images"
        output_format = client.options.get("output_format") if local_conversion else None
        compression = client.options.get("output_compression") if local_conversion else None
        urls = [image_data_url(img, output_format=output_format, compression=compression) for img in all_images]
        metadata = deepcopy(getattr(client, "result_metadata", {}))
        metadata.setdefault("actual_sizes", [f"{img.width}x{img.height}" for img in all_images])
        metadata["output_mime"] = urls[0].split(";", 1)[0][5:]
        metadata["image_count"] = len(urls)
        return {"image": urls[0], "images": urls, "metadata": metadata}


@bp.post("/api/generate-image")
def generate_image():
    try:
        data = request.json or {}
        if not isinstance(data, dict):
            raise ValueError("请求必须是 JSON 对象")
        prompt, images = data.get("prompt", ""), data.get("images", [])
        options = data.get("options")
        provider = data.get("provider") or config_manager.get_image_provider()
        if provider not in IMAGE_PROVIDER_META:
            raise ValueError(f"未知图片生成渠道: {provider}")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("提示词不能为空")
        if not isinstance(images, list):
            raise ValueError("参考图必须是数组")
        maximum = 16 if provider == "openai_images" else 3
        if len(images) > maximum:
            raise ValueError(f"此渠道当前最多接收 {maximum} 张参考图")
        if options is not None and not isinstance(options, dict):
            raise ValueError("生成参数必须是 JSON 对象")
        if provider == "codex_images":
            cfg = config_manager.load_config()
            credentials = {"codex_model": cfg.get("codex_model", ""), "codex_effort": cfg.get("codex_effort") or "auto"}
            model = data.get("model") or "gpt-image-2"
            if model != "gpt-image-2":
                raise ValueError("Codex Image 不支持指定 Image 2.5；请改用 API 渠道")
        else:
            credentials = deepcopy(config_manager.get_image_provider_config(provider))
            model = str(data.get("model") or credentials.get("model") or "").strip()
            if not model or not all(credentials.get(k) for k in ("base_url", "api_key")):
                raise ValueError("请先完成当前图片渠道配置")
        if options is None:
            options = {"aspect_ratio": data.get("aspect_ratio", "1:1"), "image_size": data.get("image_size", "2K")}
            if provider == "gemini":
                options["thinking_level"] = data.get("thinking_level", "low")
        if provider == "openai_images":
            if len(prompt) > 32000:
                raise ValueError("GPT Image 提示词不能超过 32000 字符")
            normalize_options(options, model)  # 请求前校验，不消耗额度。
        elif provider == "codex_images":
            CodexImageProvider(model=model).set_generation_options(options)
        if not config_manager.set_active_image_selection(provider, model):
            raise RuntimeError("图片渠道选择保存失败")
        if not config_manager.save_image_generation_options(provider, model, options):
            raise RuntimeError("生成参数保存失败")
        cancelled = threading.Event()
        snapshot = {"prompt": prompt, "images": list(images), "provider": provider,
                    "credentials": credentials, "model": model, "options": deepcopy(options), "cancelled": cancelled}
        task = image_task_manager.submit(lambda: _run_image_generation(**snapshot), provider=provider, model=model,
                                         cancel_callback=cancelled.set if provider == "codex_images" else None)
        response = jsonify({"task_id": task["task_id"], "status": task["status"]})
        response.status_code = 202
        response.headers["Cache-Control"] = "no-store"
        return response
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except OverflowError as exc:
        return jsonify({"error": str(exc)}), 429
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.get("/api/generate-image/status/<task_id>")
def get_image_task_status(task_id):
    task = image_task_manager.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在或已过期"}), 404
    response = jsonify(task)
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.post("/api/generate-image/cancel/<task_id>")
def cancel_image_task(task_id):
    task = image_task_manager.cancel(task_id)
    if not task:
        return jsonify({"error": "任务不存在或已过期"}), 404
    response = jsonify(task)
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/api/generate-image/capacity")
def get_image_task_capacity():
    return jsonify({"workers": image_task_manager.max_workers, "max_pending": image_task_manager.max_pending,
                    "ttl_seconds": image_task_manager.ttl_seconds})
