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

    def __init__(self, config_manager: AIConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _build_messages(self) -> list:
        raise NotImplementedError

    def run(self):
        try:
            # 消息构建包含参考图读盘 + base64 编码，必须留在工作线程里，
            # 否则大图会卡死 UI。
            self.progress.emit("正在处理输入...")
            try:
                messages = self._build_messages()
            except ValueError as exc:
                self.error.emit(str(exc))
                return
            if self._cancelled:
                return
            self.progress.emit("正在连接AI服务...")
            chat = self.config_manager.get_chat_config()
            full_content = ""
            self.progress.emit("正在生成提示词...")
            for event in stream_chat(
                messages,
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
        super().__init__(config_manager)
        self.user_prompt = user_prompt
        self.image_paths = image_paths or []

    def _build_messages(self) -> list:
        return build_generate_messages(self.user_prompt, self.image_paths)


class AIModifyThread(_ChatStreamThread):
    def __init__(
        self,
        current_data: str,
        modify_request: str,
        config_manager: AIConfigManager,
        image_paths: Optional[List[str]] = None,
    ):
        super().__init__(config_manager)
        self.current_data = current_data
        self.modify_request = modify_request
        self.image_paths = image_paths or []

    def _build_messages(self) -> list:
        return build_modify_messages(self.current_data, self.modify_request, self.image_paths)

    def run(self):
        self.progress.emit("正在修改提示词...")
        super().run()


class AIService:
    def __init__(self):
        self.config_manager = AIConfigManager()
        self._current_thread: Optional[_ChatStreamThread] = None
        # 已取消但可能还在跑的线程：保住引用防止 QThread 运行中被析构
        self._stale_threads: List[_ChatStreamThread] = []

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
        """取消当前任务：断开信号后打取消标记，不阻塞主线程等待。"""
        thread = self._current_thread
        if thread is None:
            return
        self._current_thread = None
        if thread.isRunning():
            self._disconnect_all(thread)
            thread.cancel()
            self._stale_threads.append(thread)

    @staticmethod
    def _disconnect_all(thread: _ChatStreamThread):
        for signal in (
            thread.finished,
            thread.error,
            thread.progress,
            thread.stream_chunk,
            thread.stream_done,
        ):
            try:
                signal.disconnect()
            except TypeError:
                pass  # 没有连接

    def _start_thread(self, thread, on_finished, on_error, on_progress, on_stream_chunk, on_stream_done):
        self.cancel()
        self._stale_threads = [t for t in self._stale_threads if t.isRunning()]
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
