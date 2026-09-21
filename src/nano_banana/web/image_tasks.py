"""进程内异步生图任务管理器。

单进程内由线程池执行耗时的上游图片请求，HTTP 提交与状态轮询保持短连接，
避免 Cloudflare 524。多个浏览器标签页通过独立 task_id 并发使用。
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from typing import Any, Callable


FINAL_STATUSES = {"completed", "failed", "cancelled"}
PUBLIC_TASK_KEYS = {
    "task_id",
    "status",
    "image",
    "error",
    "provider",
    "model",
    "created_at",
    "updated_at",
}


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


class ImageTaskManager:
    """线程安全、带 TTL 与取消标记的进程内任务队列。"""

    def __init__(self) -> None:
        self.max_workers = _bounded_env_int("IMAGE_TASK_WORKERS", 4, 1, 16)
        self.max_pending = _bounded_env_int("IMAGE_TASK_MAX_PENDING", 32, 1, 256)
        self.ttl_seconds = _bounded_env_int(
            "IMAGE_TASK_TTL_SECONDS", 1800, 60, 86400
        )
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="nano-image",
        )
        self._lock = threading.RLock()
        self._tasks: dict[str, dict[str, Any]] = {}

    def submit(
        self,
        runner: Callable[[], str],
        *,
        provider: str,
        model: str,
    ) -> dict[str, Any]:
        self.cleanup()
        with self._lock:
            active = sum(
                1
                for task in self._tasks.values()
                if task.get("status") not in FINAL_STATUSES
            )
            if active >= self.max_pending:
                raise RuntimeError(
                    f"生图队列已满（上限 {self.max_pending} 个未完成任务），请稍后再试"
                )

            now = time.time()
            task_id = uuid.uuid4().hex
            task: dict[str, Any] = {
                "task_id": task_id,
                "status": "queued",
                "image": None,
                "error": None,
                "provider": provider,
                "model": model,
                "created_at": now,
                "updated_at": now,
                "cancel_requested": False,
                "future": None,
            }
            self._tasks[task_id] = task
            future = self._executor.submit(self._execute, task_id, runner)
            task["future"] = future
            return self._public_snapshot(task)

    def _execute(self, task_id: str, runner: Callable[[], str]) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            if task.get("cancel_requested"):
                self._finish_locked(task, "cancelled")
                return
            task["status"] = "processing"
            task["updated_at"] = time.time()

        try:
            image = runner()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                task = self._tasks.get(task_id)
                if not task:
                    return
                if task.get("cancel_requested"):
                    self._finish_locked(task, "cancelled")
                else:
                    self._finish_locked(task, "failed", error=str(exc))
            return

        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            if task.get("cancel_requested"):
                self._finish_locked(task, "cancelled")
            else:
                self._finish_locked(task, "completed", image=image)

    def _finish_locked(
        self,
        task: dict[str, Any],
        status: str,
        *,
        image: str | None = None,
        error: str | None = None,
    ) -> None:
        task["status"] = status
        task["image"] = image
        task["error"] = error
        task["updated_at"] = time.time()

    def get(self, task_id: str) -> dict[str, Any] | None:
        self.cleanup()
        with self._lock:
            task = self._tasks.get(task_id)
            return self._public_snapshot(task) if task else None

    def cancel(self, task_id: str) -> dict[str, Any] | None:
        self.cleanup()
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            if task.get("status") in FINAL_STATUSES:
                return self._public_snapshot(task)

            task["cancel_requested"] = True
            future: Future[Any] | None = task.get("future")
            if future is not None and future.cancel():
                self._finish_locked(task, "cancelled")
            else:
                # 已发送到第三方 API 的 HTTP 请求通常无法由本进程强制中断；
                # 标记 cancelling 后，任务结束时丢弃结果并转为 cancelled。
                task["status"] = "cancelling"
                task["updated_at"] = time.time()
            return self._public_snapshot(task)

    def cleanup(self) -> None:
        now = time.time()
        with self._lock:
            expired = [
                task_id
                for task_id, task in self._tasks.items()
                if task.get("status") in FINAL_STATUSES
                and now - float(task.get("updated_at") or now) > self.ttl_seconds
            ]
            for task_id in expired:
                self._tasks.pop(task_id, None)

    @staticmethod
    def _public_snapshot(task: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(
            {key: task.get(key) for key in PUBLIC_TASK_KEYS if key in task}
        )


image_task_manager = ImageTaskManager()
