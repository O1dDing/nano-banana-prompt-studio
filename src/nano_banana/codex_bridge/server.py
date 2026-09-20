"""私有 Codex 任务桥。只接受结构化生图/提示词任务，不暴露任意 RPC。"""
from __future__ import annotations

import hmac
import json
import os
import re
import signal
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from nano_banana.codex_bridge.runtime import Cancelled, probe_status, run_job

MAX_BODY = 48 * 1024 * 1024
FINAL = {"completed", "failed", "cancelled"}


def env_int(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def validate_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("任务必须为 JSON 对象")
    if set(payload) - {"kind", "messages", "model", "effort", "web_search_mode", "output_schema"}:
        raise ValueError("任务包含不允许的字段；桥接器不接受命令、路径或任意 RPC 配置")
    if payload.get("kind") not in {"prompt", "image"}:
        raise ValueError("kind 必须为 prompt 或 image")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 12:
        raise ValueError("messages 必须包含 1～12 条输入")
    if any(not isinstance(m, dict) or set(m) - {"role", "content"} for m in messages):
        raise ValueError("不允许的消息字段")
    model = payload.get("model") or ""
    if not isinstance(model, str) or len(model) > 128 or any(ord(c) < 32 for c in model):
        raise ValueError("模型名称无效")
    if payload.get("web_search_mode", "auto") not in {"disabled", "auto", "force"}:
        raise ValueError("不允许的联网模式")
    if payload.get("effort", "auto") not in {"auto", "none", "minimal", "low", "medium", "high", "xhigh", "max"}:
        raise ValueError("不允许的推理强度")
    if payload["kind"] == "prompt":
        schema = payload.get("output_schema")
        if not isinstance(schema, dict) or len(json.dumps(schema)) > 131072:
            raise ValueError("提示词任务缺少有效 JSON Schema")
        # 禁止外部引用，防止校验器访问任意 URL。
        def walk(value, depth=0):
            if depth > 30:
                raise ValueError("Schema 嵌套过深")
            if isinstance(value, dict):
                if "$ref" in value and not str(value["$ref"]).startswith("#"):
                    raise ValueError("Schema 不允许外部引用")
                for item in value.values():
                    walk(item, depth + 1)
            elif isinstance(value, list):
                for item in value:
                    walk(item, depth + 1)
        walk(schema)
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(schema)
    return payload


class JobManager:
    def __init__(self, runner=run_job, workers=None):
        self.workers = workers or env_int("CODEX_WORKERS", 4, 1, 32)
        self.prompt_workers = env_int("CODEX_PROMPT_WORKERS", self.workers, 1, 32)
        self.image_workers = env_int("CODEX_IMAGE_WORKERS", self.workers, 1, 32)
        self.max_pending = env_int("CODEX_MAX_PENDING", 32, 1, 128)
        self.ttl = env_int("CODEX_RESULT_TTL", 120, 30, 1800)
        self.runner = runner
        self.pools = {"prompt": ThreadPoolExecutor(max_workers=self.prompt_workers, thread_name_prefix="codex-prompt"),
                      "image": ThreadPoolExecutor(max_workers=self.image_workers, thread_name_prefix="codex-image")}
        self.lock = threading.RLock()
        self.jobs = {}
        self.closed = threading.Event()
        self.janitor = threading.Thread(target=self._janitor, daemon=True)
        self.janitor.start()

    def _janitor(self):
        while not self.closed.wait(10):
            self.cleanup()

    def cleanup(self):
        with self.lock:
            now = time.monotonic()
            for key, job in list(self.jobs.items()):
                if job["status"] in FINAL and now - job["updated"] > self.ttl:
                    del self.jobs[key]
                # 丢失的客户端不无限占用额度；仅轮询会续租，最大实际运行时间另有限制。
                elif job["status"] not in FINAL and now - job["leased"] > 120:
                    job["cancel"].set()

    def submit(self, payload):
        validate_payload(payload)
        self.cleanup()
        with self.lock:
            if sum(j["status"] not in FINAL for j in self.jobs.values()) >= self.max_pending:
                raise OverflowError("Codex 未完成任务队列已满，请稍后重试")
            # 防止已完成的大图片在未领取时无限堆积。
            finals = sorted((j for j in self.jobs.values() if j["status"] in FINAL), key=lambda j: j["updated"])
            for job in finals[:max(0, len(finals) - self.max_pending + 1)]:
                self.jobs.pop(job["id"], None)
            key = uuid.uuid4().hex
            now = time.monotonic()
            job = {"id": key, "status": "queued", "progress": {"status": "queued"},
                   "result": None, "error": None, "cancel": threading.Event(),
                   "updated": now, "leased": now, "future": None}
            self.jobs[key] = job
            job["future"] = self.pools[payload["kind"]].submit(self._execute, key, payload)
            return self._snapshot(job)

    def _execute(self, key, payload):
        with self.lock:
            job = self.jobs[key]
            if job["cancel"].is_set():
                job.update(status="cancelled", updated=time.monotonic())
                return
            job["status"] = "processing"
        def progress(value):
            with self.lock:
                if key in self.jobs:
                    self.jobs[key]["progress"].update(value)
                    self.jobs[key]["updated"] = time.monotonic()
        try:
            result = self.runner(payload, job["cancel"], progress)
            with self.lock:
                if key in self.jobs:
                    job.update(status="cancelled" if job["cancel"].is_set() else "completed",
                               result=None if job["cancel"].is_set() else result,
                               updated=time.monotonic())
        except Cancelled:
            with self.lock:
                job.update(status="cancelled", updated=time.monotonic())
        except Exception as exc:
            with self.lock:
                # 不记录请求文本、图片、Token；错误仅作为私有响应返回。
                job.update(status="failed", error=str(exc)[:1800], updated=time.monotonic())
        finally:
            payload.clear()
            with self.lock:
                job["progress"].pop("preview", None)

    @staticmethod
    def _snapshot(job):
        return {"task_id": job["id"], "status": job["status"],
                "progress": dict(job["progress"]), "result": job["result"], "error": job["error"]}

    def get(self, key):
        with self.lock:
            job = self.jobs.get(key)
            if job:
                job["leased"] = time.monotonic()
                return self._snapshot(job)
        return None

    def cancel(self, key, forget=False):
        with self.lock:
            job = self.jobs.get(key)
            if not job:
                return None
            job["cancel"].set()
            if job["future"] and job["future"].cancel():
                job.update(status="cancelled", updated=time.monotonic())
            result = self._snapshot(job)
            if forget and job["status"] in FINAL:
                self.jobs.pop(key, None)
            return result

    def close(self):
        self.closed.set()
        with self.lock:
            for job in self.jobs.values():
                job["cancel"].set()
        for pool in self.pools.values():
            pool.shutdown(wait=True, cancel_futures=True)


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, token, manager=None):
        if len(token) < 32:
            raise ValueError("Bridge token 至少 32 字符")
        self.token = token
        self.manager = manager or JobManager()
        self.probe_lock = threading.Lock()
        self.probe_cache = (0, {})
        super().__init__(address, Handler)

    def status(self):
        # 查询不创建 thread/turn；短缓存避免每个标签页都启动一个探测进程。
        with self.probe_lock:
            at, result = self.probe_cache
            if time.monotonic() - at > 15:
                try:
                    result = probe_status()
                except Exception:
                    result = {"available": False, "logged_in": False, "error": "Codex 状态探测失败"}
                self.probe_cache = (time.monotonic(), result)
            return {**result, "workers": self.manager.workers, "prompt_workers": self.manager.prompt_workers,
                    "image_workers": self.manager.image_workers, "max_pending": self.manager.max_pending}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "NanoCodexBridge/1"

    def log_message(self, *args):
        pass  # 不把提示词/路径/凭证写日志。

    def _reply(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle(self):
        supplied = self.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode("utf-8"), ("Bearer " + self.server.token).encode("utf-8")):
            return self._reply(401, {"error": "Unauthorized"})
        path = urlsplit(self.path).path
        try:
            if self.command == "GET" and path == "/health":
                return self._reply(200, {"ok": True, "workers": self.server.manager.workers})
            if self.command == "GET" and path == "/v1/status":
                return self._reply(200, self.server.status())
            if self.command == "POST" and path == "/v1/jobs":
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    return self._reply(413, {"error": "请求为空或超过 48 MiB"})
                self.connection.settimeout(30)
                raw = self.rfile.read(length)
                if len(raw) != length:
                    return self._reply(400, {"error": "请求体被截断"})
                payload = json.loads(raw)
                return self._reply(202, self.server.manager.submit(payload))
            match = re.fullmatch(r"/v1/jobs/([0-9a-f]{32})(/cancel)?", path)
            if match:
                key, suffix = match.groups()
                if self.command == "GET" and suffix is None:
                    data = self.server.manager.get(key)
                elif self.command == "POST" and suffix == "/cancel":
                    data = self.server.manager.cancel(key)
                elif self.command == "DELETE" and suffix is None:
                    data = self.server.manager.cancel(key, forget=True)
                else:
                    return self._reply(405, {"error": "Method not allowed"})
                return self._reply(200, data) if data else self._reply(404, {"error": "任务不存在或已回收"})
            return self._reply(404, {"error": "Not found"})
        except OverflowError as exc:
            return self._reply(429, {"error": str(exc)})
        except (ValueError, TypeError, KeyError) as exc:
            return self._reply(400, {"error": str(exc)[:600]})
        except Exception:
            return self._reply(500, {"error": "Bridge 内部错误；未重试为 API"})

    do_GET = _handle
    do_POST = _handle
    do_DELETE = _handle


def main():
    token = Path(os.environ["CODEX_BRIDGE_TOKEN_FILE"]).read_text().strip()
    server = BridgeServer(("0.0.0.0", int(os.getenv("CODEX_BRIDGE_PORT", "8787"))), token)
    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever()
    finally:
        server.manager.close()
        server.server_close()


if __name__ == "__main__":
    main()
