"""桌面端 AI 提示词服务：QThread 只包 core.chat。"""
from __future__ import annotations

from typing import Callable, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from nano_banana.core.chat import (
    build_generate_messages,
    build_modify_messages,
    stream_chat,
)
from nano_banana.core.config import AIConfigManager


class _ChatStreamThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)
    stream_chunk = pyqtSignal(str)
    stream_done = pyqtSignal(str)

    def __init__(self, messages: list, config_manager: AIConfigManager):
        super().__init__()
        self.messages = messages
        self.config_manager = config_manager
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self.progress.emit("正在连接AI服务...")
            chat = self.config_manager.get_chat_config()
            full_content = ""
            self.progress.emit("正在生成提示词...")
            for event in stream_chat(
                self.messages,
                base_url=chat["base_url"],
                api_key=chat["api_key"],
                model=chat["model"] or "gpt-4o-mini",
                cancelled=lambda: self._cancelled,
            ):
                if event.type == "content":
                    full_content += event.text
                    self.stream_chunk.emit(event.text)
                elif event.type == "done":
                    self.stream_done.emit(event.text or full_content)
                    return
                elif event.type == "error":
                    self.error.emit(event.text)
                    return
        except Exception as exc:  # noqa: BLE001
            import traceback

            self.error.emit(f"发生未知错误: {exc}\n{traceback.format_exc()}")


class AIGenerateThread(_ChatStreamThread):
    def __init__(
        self,
        user_prompt: str,
        config_manager: AIConfigManager,
        image_paths: Optional[List[str]] = None,
    ):
        try:
            messages = build_generate_messages(user_prompt, image_paths or [])
        except ValueError as exc:
            messages = None
            self._init_error = str(exc)
        else:
            self._init_error = ""
        super().__init__(messages or [], config_manager)

    def run(self):
        if self._init_error:
            self.error.emit(self._init_error)
            return
        super().run()


class AIModifyThread(_ChatStreamThread):
    def __init__(
        self,
        current_data: str,
        modify_request: str,
        config_manager: AIConfigManager,
        image_paths: Optional[List[str]] = None,
    ):
        messages = build_modify_messages(current_data, modify_request, image_paths or [])
        super().__init__(messages, config_manager)
        self.current_data = current_data
        self.modify_request = modify_request
        self.image_paths = image_paths or []

    def run(self):
        self.progress.emit("正在修改提示词...")
        super().run()


class AIService:
    def __init__(self):
        self.config_manager = AIConfigManager()
        self._current_thread: Optional[_ChatStreamThread] = None

    def is_configured(self) -> bool:
        return self.config_manager.is_configured()

    def generate_async(
        self,
        user_prompt: str,
        on_finished: Callable[[dict], None],
        on_error: Callable[[str], None],
        on_progress: Callable[[str], None] = None,
        on_stream_chunk: Callable[[str], None] = None,
        on_stream_done: Callable[[str], None] = None,
        image_paths: Optional[List[str]] = None,
    ) -> AIGenerateThread:
        return self._start_thread(
            AIGenerateThread(user_prompt, self.config_manager, image_paths),
            on_finished,
            on_error,
            on_progress,
            on_stream_chunk,
            on_stream_done,
        )

    def generate_modify_async(
        self,
        current_data: str,
        modify_request: str,
        on_finished: Callable[[dict], None],
        on_error: Callable[[str], None],
        on_progress: Callable[[str], None] = None,
        on_stream_chunk: Callable[[str], None] = None,
        on_stream_done: Callable[[str], None] = None,
        image_paths: Optional[List[str]] = None,
    ) -> AIModifyThread:
        return self._start_thread(
            AIModifyThread(current_data, modify_request, self.config_manager, image_paths),
            on_finished,
            on_error,
            on_progress,
            on_stream_chunk,
            on_stream_done,
        )

    def cancel(self):
        if self._current_thread and self._current_thread.isRunning():
            self._current_thread.cancel()
            self._current_thread.wait(1000)

    def _start_thread(self, thread, on_finished, on_error, on_progress, on_stream_chunk, on_stream_done):
        if self._current_thread and self._current_thread.isRunning():
            self._current_thread.cancel()
            self._current_thread.wait(1000)
        thread.finished.connect(on_finished)
        thread.error.connect(on_error)
        if on_progress:
            thread.progress.connect(on_progress)
        if on_stream_chunk:
            thread.stream_chunk.connect(on_stream_chunk)
        if on_stream_done:
            thread.stream_done.connect(on_stream_done)
        self._current_thread = thread
        thread.start()
        return thread
