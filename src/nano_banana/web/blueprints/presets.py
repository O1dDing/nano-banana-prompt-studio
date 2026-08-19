from flask import Blueprint, jsonify, request

from nano_banana.core.schema import get_schema
from nano_banana.web.context import CATEGORY_PRESET_SCOPES, preset_manager, yaml_handler

bp = Blueprint("presets", __name__)


@bp.get("/api/schema")
def get_prompt_schema():
    return jsonify(get_schema().to_public_dict())


@bp.get("/api/options")
def get_options():
    try:
        return jsonify(yaml_handler.load_options())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.get("/api/options/<field_name>")
def get_field_options(field_name):
    try:
        return jsonify(yaml_handler.get_field_options(field_name))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.post("/api/options/<field_name>")
def add_option(field_name):
    try:
        value = (request.json or {}).get("value")
        if value:
            yaml_handler.add_option(field_name, value)
            return jsonify({"success": True})
        return jsonify({"error": "值不能为空"}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.delete("/api/options/<field_name>")
def delete_option(field_name):
    try:
        value = (request.get_json(silent=True) or {}).get("value")
        if value:
            yaml_handler.remove_option(field_name, value)
            return jsonify({"success": True})
        return jsonify({"error": "值不能为空"}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.get("/api/line-art-prompt")
def get_line_art_prompt():
    try:
        return jsonify({"prompt": yaml_handler.get_line_art_prompt()})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.post("/api/line-art-prompt")
def save_line_art_prompt():
    try:
        prompt = (request.json or {}).get("prompt")
        if prompt is not None:
            yaml_handler.save_line_art_prompt(prompt)
            return jsonify({"success": True})
        return jsonify({"error": "提示词不能为空"}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.get("/api/presets")
def get_presets():
    try:
        presets = preset_manager.get_all_presets()
        for preset in presets:
            preset["modified_time"] = preset["modified_time"].isoformat()
        return jsonify(presets)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.get("/api/presets/details")
def get_all_preset_details():
    try:
        details = []
        for preset in preset_manager.get_all_presets():
            data = preset_manager.load_preset(preset["name"])
            if data is not None:
                details.append(data)
        return jsonify(details)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.get("/api/presets/<name>")
def get_preset(name):
    try:
        preset = preset_manager.load_preset(name)
        if preset:
            return jsonify(preset)
        return jsonify({"error": "预设不存在"}), 404
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.post("/api/presets")
def save_preset():
    try:
        payload = request.json or {}
        name = payload.get("name")
        preset_data = payload.get("data")
        if not name or not preset_data:
            return jsonify({"error": "名称和数据不能为空"}), 400
        if preset_manager.save_preset(name, preset_data):
            return jsonify({"success": True})
        return jsonify({"error": "保存失败"}), 500
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.delete("/api/presets/<name>")
def delete_preset(name):
    try:
        if preset_manager.delete_preset(name):
            return jsonify({"success": True})
        return jsonify({"error": "删除失败"}), 500
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@bp.get("/api/category-presets/<scope>")
def get_category_presets(scope):
    if scope not in CATEGORY_PRESET_SCOPES:
        return jsonify({"error": "未知的预设分类"}), 404
    presets = preset_manager.get_category_presets(scope)
    for preset in presets:
        preset["modified_time"] = preset["modified_time"].isoformat()
    return jsonify(presets)


@bp.get("/api/category-presets/<scope>/<name>")
def get_category_preset(scope, name):
    if scope not in CATEGORY_PRESET_SCOPES:
        return jsonify({"error": "未知的预设分类"}), 404
    preset = preset_manager.load_category_preset(scope, name)
    if preset is None:
        return jsonify({"error": "分类预设不存在"}), 404
    return jsonify(preset)


@bp.post("/api/category-presets/<scope>")
def save_category_preset(scope):
    if scope not in CATEGORY_PRESET_SCOPES:
        return jsonify({"error": "未知的预设分类"}), 404
    payload = request.json or {}
    name = payload.get("name")
    preset_data = payload.get("data")
    if not name or not isinstance(preset_data, dict):
        return jsonify({"error": "名称和分类数据不能为空"}), 400
    if preset_manager.save_category_preset(scope, name, preset_data):
        return jsonify({"success": True})
    return jsonify({"error": "保存失败"}), 500


@bp.delete("/api/category-presets/<scope>/<name>")
def delete_category_preset(scope, name):
    if scope not in CATEGORY_PRESET_SCOPES:
        return jsonify({"error": "未知的预设分类"}), 404
    if preset_manager.delete_category_preset(scope, name):
        return jsonify({"success": True})
    return jsonify({"error": "删除失败"}), 404
