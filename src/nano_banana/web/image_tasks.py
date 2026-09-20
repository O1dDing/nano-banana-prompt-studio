"""单进程线程池图片任务，支持 Codex 中断和多图片返回。"""
from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

FINAL_STATUSES = {"completed", "failed", "cancelled"}
PUBLIC_TASK_KEYS = {"task_id", "status", "image", "images", "metadata", "error", "provider", "model", "created_at", "updated_at"}


def _bounded_env_int(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


class ImageTaskManager:
    def __init__(self):
        self.max_workers = _bounded_env_int("IMAGE_TASK_WORKERS", 4, 1, 32)
        self.max_pending = _bounded_env_int("IMAGE_TASK_MAX_PENDING", 32, 1, 256)
        self.ttl_seconds = _bounded_env_int("IMAGE_TASK_TTL_SECONDS", 1800, 60, 86400)
        self.max_completed = _bounded_env_int("IMAGE_TASK_MAX_COMPLETED", 32, 1, 256)
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="nano-image")
        self._lock = threading.RLock()
        self._tasks = {}

    def submit(self, runner, *, provider, model, cancel_callback=None):
        self.cleanup()
        with self._lock:
            active = sum(task["status"] not in FINAL_STATUSES for task in self._tasks.values())
            if active >= self.max_pending:
                raise OverflowError(f"生图队列已满（上限 {self.max_pending} 个未完成任务），请稍后再试")
            key, now = uuid.uuid4().hex, time.time()
            task = {"task_id": key, "status": "queued", "image": None, "images": [], "metadata": {},
                    "error": None, "provider": provider, "model": model, "created_at": now, "updated_at": now,
                    "cancel_requested": False, "future": None, "cancel_callback": cancel_callback}
            self._tasks[key] = task
            task["future"] = self._executor.submit(self._execute, key, runner)
            return self._public_snapshot(task)

    def _execute(self, key, runner):
        with self._lock:
            task = self._tasks.get(key)
            if not task:
                return
            if task["cancel_requested"]:
                self._finish_locked(task, "cancelled")
                return
            task.update(status="processing", updated_at=time.time())
        try:
            result = runner()
            if not isinstance(result, (str, dict)):
                raise ValueError("图片任务返回格式错误")
            with self._lock:
                task = self._tasks.get(key)
                if not task:
                    return
                if task["cancel_requested"]:
                    self._finish_locked(task, "cancelled")
                else:
                    self._finish_locked(task, "completed", image=result.get("image") if isinstance(result, dict) else result)
                    if isinstance(result, dict):
                        task["images"] = result.get("images") or [result["image"]]
                        task["metadata"] = result.get("metadata") or {}
                    else:
                        task["images"] = [result]
        except Exception as exc:
            with self._lock:
                task = self._tasks.get(key)
                if task:
                    self._finish_locked(task, "cancelled" if task["cancel_requested"] else "failed", error=None if task["cancel_requested"] else str(exc))
        finally:
            with self._lock:
                if key in self._tasks:
                    self._tasks[key]["cancel_callback"] = None
            self.cleanup()

    def _finish_locked(self, task, status, *, image=None, error=None):
        task.update(status=status, image=image, error=error, updated_at=time.time())

    def get(self, task_id):
        self.cleanup()
        with self._lock:
            task = self._tasks.get(task_id)
            return self._public_snapshot(task) if task else None

    def cancel(self, task_id):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            if task["status"] not in FINAL_STATUSES:
                task["cancel_requested"] = True
                callback = task.get("cancel_callback")
                if callback:
                    callback()  # 仅设置 Event，不执行网络 IO。
                if task["future"] and task["future"].cancel():
                    self._finish_locked(task, "cancelled")
                else:
                    task.update(status="cancelling", updated_at=time.time())
            return self._public_snapshot(task)

    def cleanup(self):
        with self._lock:
            now = time.time()
            final = sorted((task for task in self._tasks.values() if task["status"] in FINAL_STATUSES), key=lambda task: task["updated_at"])
            excess = max(0, len(final) - self.max_completed)
            for index, task in enumerate(final):
                if index < excess or now - task["updated_at"] > self.ttl_seconds:
                    self._tasks.pop(task["task_id"], None)

    @staticmethod
    def _public_snapshot(task):
        return deepcopy({key: task.get(key) for key in PUBLIC_TASK_KEYS if key in task})


image_task_manager = ImageTaskManager()
