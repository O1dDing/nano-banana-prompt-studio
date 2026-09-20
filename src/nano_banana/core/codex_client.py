"""Web → 私有 Codex bridge；短轮询，不接触 Codex 登录凭据。"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx


class BridgeError(RuntimeError):
    pass


class CodexBridge:
    def __init__(self, identity=None):
        if identity is None:
            try:
                from nano_banana.web.user_sessions import codex_identity
                identity = codex_identity()
            except ImportError:
                pass
        self.base = os.getenv("CODEX_BRIDGE_URL", "").rstrip("/")
        parsed = urlparse(self.base)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise BridgeError("未配置私有 Codex Bridge；请先部署独立 Codex 容器")
        filename = os.getenv("CODEX_BRIDGE_TOKEN_FILE", "")
        try:
            self.token = Path(filename).read_text().strip() if filename else ""
        except OSError as exc:
            raise BridgeError("无法读取 Codex Bridge 凭证文件") from exc
        if len(self.token) < 32:
            raise BridgeError("Codex Bridge 访问凭证未配置")
        headers = {"Authorization": "Bearer " + self.token}
        if identity == 'owner':
            headers['X-Codex-Owner'] = '1'
        elif identity:
            headers['X-Codex-Session'] = identity
        self.client = httpx.Client(timeout=httpx.Timeout(90, connect=5), trust_env=False, headers=headers)

    def request(self, method, path, payload=None, timeout=None):
        try:
            response = self.client.request(method, self.base + path, json=payload, **({"timeout": timeout} if timeout else {}))
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BridgeError("Codex Bridge 无响应或返回无效数据；未改用收费 API") from exc
        if response.is_error:
            raise BridgeError(str(data.get("error") or f"Bridge HTTP {response.status_code}"))
        return data

    def close(self):
        self.client.close()

    def iter_job(self, payload, cancelled=None):
        """每次轮询返回一次快照；finally 无论完成/停止/断线均取消或回收临时任务。"""
        task_id = None
        try:
            submitted = self.request("POST", "/v1/jobs", payload)
            task_id = submitted.get("task_id")
            if not task_id:
                raise BridgeError("Codex 未返回任务编号")
            deadline = time.monotonic() + 1200
            while time.monotonic() < deadline:
                if cancelled is not None and cancelled.is_set():
                    raise BridgeError("已取消 Codex 任务")
                data = self.request("GET", f"/v1/jobs/{task_id}")
                yield data
                if data["status"] == "completed":
                    return
                if data["status"] in {"failed", "cancelled"}:
                    raise BridgeError(data.get("error") or "Codex 任务已取消")
                if cancelled is not None:
                    cancelled.wait(.5)
                else:
                    time.sleep(.5)
            raise BridgeError("Codex 任务超时，不会自动重新消费额度")
        finally:
            if task_id:
                try:
                    self.request("DELETE", f"/v1/jobs/{task_id}", timeout=3)
                except BridgeError:
                    pass  # bridge 租约超时会再次取消，绝不重提交生成。


def bridge_status():
    bridge = None
    try:
        bridge = CodexBridge()
        return bridge.request("GET", "/v1/status")
    except BridgeError as exc:
        return {"available": False, "logged_in": False, "error": str(exc)}
    finally:
        if bridge:
            bridge.close()


def iter_prompt_sse(messages, chat, output_schema):
    bridge = None
    events = None
    try:
        yield 'data: {"status":"started"}\n\n'
        bridge = CodexBridge(identity=chat.get("_codex_identity"))
        payload = {"kind": "prompt", "messages": messages,
                   "model": chat.get("codex_model", ""), "effort": chat.get("codex_effort") or "auto",
                   "web_search_mode": chat.get("web_search_mode") or "auto", "output_schema": output_schema}
        events = bridge.iter_job(payload, chat.get("_cancelled"))
        preview = None
        for item in events:
            progress = item.get("progress") or {}
            if "preview" in progress and progress["preview"] != preview:
                preview = progress["preview"]
                yield f"data: {json.dumps({'codex_preview': preview}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'status': progress.get('status') or item['status']})}\n\n"
            if item["status"] == "completed":
                result = item["result"]
                # 清除未验证预览，再提交已通过 Schema/联网校验的完整 JSON。
                yield f"data: {json.dumps({'codex_preview': ''})}\n\n"
                yield f"data: {json.dumps({'content': result['text']}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return
    except GeneratorExit:
        raise
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
    finally:
        if events is not None:
            events.close()
        if bridge:
            bridge.close()
