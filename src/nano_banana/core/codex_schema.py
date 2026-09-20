"""从项目字段唯一真源生成 Codex outputSchema，避免另造一份不兼容 Prompt。"""
from __future__ import annotations

from nano_banana.core.schema import get_schema


def _object():
    return {"type": "object", "properties": {}, "required": [], "additionalProperties": False}


def _insert(root, path, schema):
    node = root
    for name in path[:-1]:
        node = node["properties"].setdefault(name, _object())
    node["properties"][path[-1]] = schema


def _infer(value, depth=0):
    if depth > 12:
        raise ValueError("当前 JSON 嵌套过深")
    if isinstance(value, dict):
        out = _object()
        out["properties"] = {k: _infer(v, depth + 1) for k, v in value.items()}
        return out
    if isinstance(value, list):
        return {"type": "array", "items": _infer(value[0], depth + 1) if value else {"type": "string"}}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if value is None:
        return {"type": ["string", "null"]}
    return {"type": "string"}


def prompt_output_schema(current=None):
    root = _object()
    schema = get_schema()
    for field in schema.iter_fields():
        typ = field.type
        item = {"type": typ if typ in {"string", "boolean", "integer", "number", "array"} else "string"}
        if typ == "array":
            item["items"] = {"type": "string"}
        _insert(root, field.path, item)
    for overlay in schema.overlays:
        if not overlay.ui_only:
            _insert(root, overlay.path, {"type": "string"})
    # 修改任务保留用户已有自定义字段/线稿结构，不在桥接过程中悄悄丢字段。
    def merge(node, value):
        if not isinstance(value, dict) or node.get("type") != "object":
            return
        for key, item in value.items():
            if key not in node["properties"]:
                node["properties"][key] = _infer(item)
            elif isinstance(item, dict) and node["properties"][key].get("type") == "object":
                merge(node["properties"][key], item)
    if current is not None:
        merge(root, current)
    def required(node):
        if node.get("type") == "object":
            node["required"] = list(node["properties"])
            for child in node["properties"].values():
                required(child)
        elif node.get("type") == "array":
            required(node["items"])
    required(root)
    return root
