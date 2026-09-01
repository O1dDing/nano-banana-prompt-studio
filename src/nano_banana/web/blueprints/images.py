import base64
import os
import tempfile
from copy import deepcopy
from io import BytesIO
from typing import Any

from flask import Blueprint, jsonify, request

from nano_banana.core.images import (
    create_image_provider_from_credentials,
    get_image_provider_capabilities,
)
from nano_banana.core.images.provider_config import IMAGE_PROVIDER_META
from nano_banana.web.context import config_manager
from nano_banana.web.image_tasks import image_task_manager

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


def _decode_reference_images(images: list[Any]) -> tuple[list[str], list[str]]:
    """在线程内部把 Data URI 写成临时文件，返回引用与待清理路径。"""
    processed: list[str] = []
    temp_files: list[str] = []
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
    }

    for image_ref in images:
        if not isinstance(image_ref, str):
            raise ValueError("参考图必须是 Data URI、URL 或文件路径字符串")
        if not image_ref.startswith("data:"):
            processed.append(image_ref)
            continue
        if ";base64," not in image_ref:
            raise ValueError("参考图 Data URI 缺少 base64 标记")
        header, encoded = image_ref.split(";base64,", 1)
        mime_type = header.split(":", 1)[1].lower()
        extension = ext_map.get(mime_type, ".bin")
        try:
            image_data = base64.b64decode(encoded, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"参考图 Base64 数据无效: {exc}") from exc
        fd, path = tempfile.mkstemp(suffix=extension)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(image_data)
        except Exception:
            os.close(fd)
            raise
        temp_files.append(path)
        processed.append(path)
    return processed, temp_files


def _run_image_generation(
    *,
    prompt: str,
    images: list[Any],
    provider: str,
    credentials: dict[str, str],
    model: str,
    options: dict[str, Any],
) -> str:
    """线程池中的完整生图过程，返回 PNG Data URL。"""
    temp_files: list[str] = []
    try:
        processed_images, temp_files = _decode_reference_images(images)
        client = create_image_provider_from_credentials(
            provider,
            credentials["base_url"],
            credentials["api_key"],
            model,
        )
        client.set_generation_options(options)
        generated_image = client.generate_image(
            text=prompt,
            images=processed_images if processed_images else None,
        )
        if not generated_image:
            raise RuntimeError("生成图片失败，未返回图片数据")

        buffered = BytesIO()
        generated_image.save(buffered, format="PNG")
        encoded = base64.b64encode(buffered.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    finally:
        for path in temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as exc:  # noqa: BLE001
                print(f"Error removing temp file {path}: {exc}")


@bp.post("/api/generate-image")
def generate_image():
    """快速提交异步生图任务；实际结果由状态接口轮询。"""
    try:
        data = request.json or {}
        prompt = data.get("prompt", "")
        images = data.get("images", [])
        options = data.get("options") or {}
        provider = data.get("provider") or config_manager.get_image_provider()

        if provider not in IMAGE_PROVIDER_META:
            return jsonify({"error": f"未知图片生成渠道: {provider}"}), 400
        if not isinstance(prompt, str) or not prompt.strip():
            return jsonify({"error": "提示词不能为空"}), 400
        if not isinstance(images, list):
            return jsonify({"error": "参考图必须是数组"}), 400
        if not isinstance(options, dict):
            return jsonify({"error": "生成参数必须是 JSON 对象"}), 400

        credentials = deepcopy(config_manager.get_image_provider_config(provider))
        model = str(data.get("model") or credentials.get("model") or "").strip()
        if not model:
            return jsonify({"error": "图片模型不能为空"}), 400
        credentials["model"] = model
        missing = [
            key
            for key in ("base_url", "api_key")
            if not str(credentials.get(key) or "").strip()
        ]
        if missing:
            return jsonify({"error": "请先完成当前图片渠道配置"}), 400

        if not options:
            options = {
                "aspect_ratio": data.get("aspect_ratio", "1:1"),
                "image_size": data.get("image_size", "2K"),
                "thinking_level": data.get("thinking_level", "low"),
            }

        # 在请求线程内保存选择；任务本身持有不可变快照，后续切换渠道不会影响它。
        if not config_manager.set_active_image_selection(provider, model):
            return jsonify({"error": "图片渠道选择保存失败"}), 500
        if not config_manager.save_image_generation_options(provider, model, options):
            return jsonify({"error": "生成参数保存失败"}), 500

        prompt_snapshot = prompt
        image_snapshot = list(images)
        credential_snapshot = deepcopy(credentials)
        option_snapshot = deepcopy(options)

        task = image_task_manager.submit(
            lambda: _run_image_generation(
                prompt=prompt_snapshot,
                images=image_snapshot,
                provider=provider,
                credentials=credential_snapshot,
                model=model,
                options=option_snapshot,
            ),
            provider=provider,
            model=model,
        )
        response = jsonify({"task_id": task["task_id"], "status": task["status"]})
        response.status_code = 202
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception as exc:  # noqa: BLE001
        print(f"Generate Image Submit Error: {exc}")
        return jsonify({"error": str(exc)}), 500


@bp.get("/api/generate-image/status/<task_id>")
def get_image_task_status(task_id: str):
    task = image_task_manager.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在或已过期"}), 404
    response = jsonify(task)
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.post("/api/generate-image/cancel/<task_id>")
def cancel_image_task(task_id: str):
    task = image_task_manager.cancel(task_id)
    if not task:
        return jsonify({"error": "任务不存在或已过期"}), 404
    response = jsonify(task)
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/api/generate-image/capacity")
def get_image_task_capacity():
    """便于界面/运维确认单进程并行度。"""
    return jsonify(
        {
            "workers": image_task_manager.max_workers,
            "max_pending": image_task_manager.max_pending,
            "ttl_seconds": image_task_manager.ttl_seconds,
        }
    )
