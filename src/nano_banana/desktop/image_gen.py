"""桌面端生图控件与生成流程。"""
import json
import os
import time
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QLabel,
    QFrame,
    QMessageBox,
    QComboBox,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QImage, QCursor, QIcon

from nano_banana.core.images import get_image_provider_capabilities
from nano_banana.core.images.provider_config import IMAGE_PROVIDER_META
from nano_banana.desktop.dialogs.image_dialog import ImageGenerationThread
from nano_banana.desktop.preview import ImagePreviewDialog, ImagePreviewLabel
from nano_banana.desktop.window_utils import get_last_dir, remember_last_dir

MAX_IMAGE_HISTORY = 10


class ImageGenController:
    """MainWindow mixin：渠道选择、参考图、生成与预览。"""

    def _create_image_generate_area(self) -> QWidget:
        """创建生图区域"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 0, 0, 0)
        layout.setSpacing(12)

        # 标题
        title = QLabel("图片生成")
        title.setObjectName("previewTitle")
        layout.addWidget(title)

        # 上方：参数和参考图片区域（合并）
        param_frame = QFrame()
        param_frame.setObjectName("paramFrame")
        param_frame.setStyleSheet("""
            QFrame#paramFrame {
                background-color: #ffffff;
                border: 1px solid #e8e8e8;
                border-radius: 8px;
            }
        """)
        param_layout = QVBoxLayout(param_frame)
        param_layout.setContentsMargins(16, 12, 16, 12)
        param_layout.setSpacing(12)

        provider_row = QWidget()
        provider_layout = QHBoxLayout(provider_row)
        provider_layout.setContentsMargins(0, 0, 0, 0)
        provider_layout.setSpacing(8)

        provider_layout.addWidget(QLabel("渠道"))
        self.image_provider_combo = QComboBox()
        provider_layout.addWidget(self.image_provider_combo, 1)

        provider_layout.addWidget(QLabel("模型"))
        self.image_model_combo = QComboBox()
        self.image_model_combo.setEditable(False)
        provider_layout.addWidget(self.image_model_combo, 2)

        self.image_config_status = QLabel()
        provider_layout.addWidget(self.image_config_status)
        param_layout.addWidget(provider_row)

        self.image_options_container = QWidget()
        self.image_options_layout = QGridLayout(self.image_options_container)
        self.image_options_layout.setContentsMargins(0, 0, 0, 0)
        self.image_options_layout.setHorizontalSpacing(16)
        self.image_options_layout.setVerticalSpacing(8)
        self.image_options_layout.setColumnStretch(0, 1)
        self.image_options_layout.setColumnStretch(1, 1)
        param_layout.addWidget(self.image_options_container)
        self._load_image_generation_controls()

        # 参考图片区域：合并到参数设置中
        img_row = QWidget()
        img_row_layout = QHBoxLayout(img_row)
        img_row_layout.setContentsMargins(0, 0, 0, 0)
        img_row_layout.setSpacing(12)

        # 添加参考图按钮
        self.add_image_btn = QPushButton("添加参考图")
        self.add_image_btn.setObjectName("secondaryButton")
        self.add_image_btn.clicked.connect(self._add_images)
        img_row_layout.addWidget(self.add_image_btn)

        # 图片按钮容器（显示图一、图二等）
        self.image_buttons_container = QWidget()
        self.image_buttons_layout = QHBoxLayout(self.image_buttons_container)
        self.image_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.image_buttons_layout.setSpacing(8)
        self.image_buttons_layout.addStretch()
        
        # 提示文本
        self.image_hint_label = QLabel("点击删除参考图")
        self.image_hint_label.setStyleSheet("font-size: 11px; color: #8c8c8c;")
        self.image_buttons_layout.addWidget(self.image_hint_label)
        
        img_row_layout.addWidget(self.image_buttons_container, 1)

        param_layout.addWidget(img_row)
        layout.addWidget(param_frame)

        # 下方：预览区域
        preview_frame = QFrame()
        preview_frame.setObjectName("previewFrame")
        preview_frame.setStyleSheet("""
            QFrame#previewFrame {
                background-color: #ffffff;
                border: 1px solid #e8e8e8;
                border-radius: 8px;
            }
        """)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        preview_layout.setSpacing(12)

        preview_title = QLabel("生成预览")
        preview_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #262626;")
        preview_layout.addWidget(preview_title)

        # 预览画布
        preview_canvas = QFrame()
        preview_canvas.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            "stop:0 #fafafa, stop:1 #f0f0f0); "
            "border: 2px dashed #d9d9d9; border-radius: 6px;"
        )
        canvas_layout = QVBoxLayout(preview_canvas)
        canvas_layout.setContentsMargins(16, 16, 16, 16)

        self.preview_area = ImagePreviewLabel("图片生成后会显示在这里")
        self.preview_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_area.setMinimumHeight(120)
        self.preview_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_area.setStyleSheet("color: #bfbfbf; font-size: 13px; border: none;")
        # 禁用自动缩放，使用手动缩放以保持宽高比
        self.preview_area.setScaledContents(False)
        # 连接点击事件
        self.preview_area.clicked.connect(self._show_image_preview)
        canvas_layout.addWidget(self.preview_area)

        preview_layout.addWidget(preview_canvas, 1)

        # 历史缩略图条：新结果不再覆盖旧图，点击可回看
        self.history_list = QListWidget()
        self.history_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.history_list.setFlow(QListWidget.Flow.LeftToRight)
        self.history_list.setWrapping(False)
        self.history_list.setFixedHeight(76)
        self.history_list.setIconSize(QSize(56, 56))
        self.history_list.setSpacing(6)
        self.history_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.history_list.setToolTip("本次会话的生成历史，点击回看")
        self.history_list.itemClicked.connect(self._on_history_item_clicked)
        self.history_list.setVisible(False)
        preview_layout.addWidget(self.history_list)

        layout.addWidget(preview_frame, 1)

        # 状态标签
        self.image_status_label = QLabel("准备就绪")
        self.image_status_label.setStyleSheet("color: #595959; font-size: 12px;")
        layout.addWidget(self.image_status_label)

        return container

    def _create_param_row(self, label_text: str, items: list, default: str = None) -> QWidget:
        """创建参数行"""
        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(12)

        label = QLabel(label_text)
        # 最小宽度保证对齐，长文本/大字体时允许自动加宽而不是裁剪
        label.setMinimumWidth(72)
        label.setStyleSheet("font-size: 12px; color: #595959;")
        container_layout.addWidget(label)

        combo = QComboBox()
        combo.addItems(items)
        if default:
            combo.setCurrentText(default)
        combo.setStyleSheet("""
            QComboBox {
                padding: 4px 8px;
                border: 1px solid #d9d9d9;
                border-radius: 4px;
                background-color: white;
                min-height: 24px;
                font-size: 12px;
            }
            QComboBox:hover {
                border-color: #40a9ff;
            }
        """)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        container_layout.addWidget(combo, 1)

        return container

    def _load_image_generation_controls(self):
        """从配置加载主界面的当前生图渠道与模型。"""
        provider = self._refresh_image_provider_choices(
            self.config_manager.get_image_provider()
        )
        if not provider:
            self._render_image_options("", "", cache_current=False)
            self.image_provider_combo.currentIndexChanged.connect(self._on_image_provider_changed)
            self.image_model_combo.currentIndexChanged.connect(self._on_image_model_changed)
            return
        self._populate_image_models(provider)
        model = self.image_model_combo.currentText()
        self.config_manager.set_active_image_selection(provider, model)
        self._render_image_options(provider, model)
        self.image_provider_combo.currentIndexChanged.connect(self._on_image_provider_changed)
        self.image_model_combo.currentIndexChanged.connect(self._on_image_model_changed)

    def _refresh_image_provider_choices(self, preferred_provider: str = "") -> str:
        """仅显示已填写密钥的渠道，并返回最终选中的渠道。"""
        available_providers = self.config_manager.get_image_providers_with_api_key()
        stored_provider = self.config_manager.get_image_provider()
        selected_provider = next(
            (
                provider
                for provider in (preferred_provider, stored_provider)
                if provider in available_providers
            ),
            available_providers[0] if available_providers else "",
        )

        self.image_provider_combo.blockSignals(True)
        self.image_provider_combo.clear()
        for provider in available_providers:
            self.image_provider_combo.addItem(IMAGE_PROVIDER_META[provider]["label"], provider)
        if selected_provider:
            self.image_provider_combo.setCurrentIndex(
                self.image_provider_combo.findData(selected_provider)
            )
        else:
            self.image_provider_combo.addItem("请先配置图片渠道", None)
        self.image_provider_combo.setEnabled(bool(available_providers))
        self.image_provider_combo.blockSignals(False)
        self.image_model_combo.setEnabled(bool(available_providers))
        return selected_provider

    def _populate_image_models(self, provider: str, preferred_model: str = ""):
        meta = IMAGE_PROVIDER_META.get(provider) or IMAGE_PROVIDER_META["gemini"]
        configured_model = self.config_manager.get_image_provider_config(provider)["model"]
        model = preferred_model or configured_model or meta.get("default_model") or ""
        models = list(meta.get("model_suggestions") or [])
        if model and model not in models:
            models.append(model)
        self.image_model_combo.blockSignals(True)
        self.image_model_combo.clear()
        self.image_model_combo.addItems(models)
        self.image_model_combo.setCurrentText(model)
        self.image_model_combo.blockSignals(False)

    def _cache_current_image_options(self):
        if not self._active_image_provider or not self.image_option_widgets:
            return
        self.config_manager.save_image_generation_options(
            self._active_image_provider,
            self._active_image_model,
            self._collect_image_options(),
        )

    def _on_image_provider_changed(self, *_args):
        self._cache_current_image_options()
        provider = self.image_provider_combo.currentData()
        if not provider:
            return
        self._populate_image_models(provider)
        model = self.image_model_combo.currentText().strip()
        self.config_manager.set_active_image_selection(provider, model)
        self._render_image_options(provider, model, cache_current=False)

    def _on_image_model_changed(self, *_args):
        provider = self.image_provider_combo.currentData()
        if not provider:
            return
        model = self.image_model_combo.currentText().strip()
        if provider == self._active_image_provider and model == self._active_image_model:
            return
        self._cache_current_image_options()
        self.config_manager.set_active_image_selection(provider, model)
        self._render_image_options(provider, model, cache_current=False)

    def _on_image_option_changed(self, *_args):
        self._cache_current_image_options()

    def _render_image_options(
        self,
        provider: str | None = None,
        model: str | None = None,
        cache_current: bool = True,
    ):
        """根据主界面的 provider/model 渲染并恢复生图参数。"""
        if cache_current:
            self._cache_current_image_options()
        while self.image_options_layout.count():
            item = self.image_options_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.image_option_widgets = {}
        provider = provider or self.image_provider_combo.currentData()
        if not provider:
            self._active_image_provider = ""
            self._active_image_model = ""
            self.image_model_combo.blockSignals(True)
            self.image_model_combo.clear()
            self.image_model_combo.blockSignals(False)
            self._update_image_config_status()
            return
        model = (model if model is not None else self.image_model_combo.currentText()).strip()
        self._active_image_provider = provider
        self._active_image_model = model
        provider_config = get_image_provider_capabilities(provider, model)
        saved_options = self.config_manager.get_image_generation_options(provider, model)

        for index, (key, option) in enumerate(provider_config["options"].items()):
            value = saved_options.get(key, option.get("default"))
            if value not in option.get("values", []):
                value = option.get("default")
            container = self._create_param_row(
                option["label"],
                option.get("values", []),
                default=value,
            )
            combo = container.findChild(QComboBox)
            combo.currentTextChanged.connect(self._on_image_option_changed)
            self.image_option_widgets[key] = combo
            self.image_options_layout.addWidget(container, index // 2, index % 2)
        self._update_image_config_status()

    def _update_image_config_status(self):
        provider = self.image_provider_combo.currentData()
        configured = bool(
            provider and self.config_manager.is_image_provider_configured(provider)
        )
        if not provider:
            self.image_config_status.setText("请先在 AI 配置中填写密钥")
            self.image_config_status.setStyleSheet("color: #cf1322; font-size: 12px;")
        elif configured:
            self.image_config_status.clear()
        else:
            self.image_config_status.setText("未配置")
            self.image_config_status.setStyleSheet("color: #cf1322; font-size: 12px;")
        if hasattr(self, "generate_image_btn"):
            generating = bool(self.worker_thread and self.worker_thread.isRunning())
            # 生成中按钮是「取消生成」，必须保持可点
            self.generate_image_btn.setEnabled(generating or configured)

    def _collect_image_options(self) -> dict:
        """收集当前 provider 的生图参数"""
        return {
            key: combo.currentText()
            for key, combo in self.image_option_widgets.items()
        }


    # ========== 生图相关方法 ==========

    def _add_images(self):
        """添加参考图片"""
        if len(self.selected_images) >= 3:
            QMessageBox.information(self, "提示", "最多只能选择 3 张参考图")
            return

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择参考图片",
            get_last_dir("reference"),
            "图像文件 (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not files:
            return
        remember_last_dir(files[0], "reference")
        self._add_reference_paths(files)

    def _add_reference_paths(self, paths: list):
        """把图片路径加入参考图（拖拽/粘贴/文件对话框共用入口）。"""
        remaining = 3 - len(self.selected_images)
        if remaining <= 0:
            self._set_image_status("最多只能选择 3 张参考图", "#faad14")
            return
        added = 0
        for path in paths[:remaining]:
            if path not in self.selected_images:
                self.selected_images.append(path)
                self._append_image_item(path)
                added += 1
        if added:
            self._set_image_status(f"已添加 {added} 张参考图", "#52c41a")

    def _number_to_chinese(self, num: int) -> str:
        """将数字转换为中文数字"""
        chinese_nums = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        if 1 <= num <= 10:
            return chinese_nums[num]
        return str(num)

    def _append_image_item(self, path: str):
        """添加图片按钮"""
        index = len(self.selected_images) - 1  # 图片已添加到列表，所以索引是长度减1
        chinese_num = self._number_to_chinese(index + 1)
        btn = QPushButton(f"图{chinese_num}")
        btn.setToolTip(path)
        btn.setStyleSheet("""
            QPushButton {
                padding: 4px 12px;
                font-size: 12px;
                border: 1px solid #d9d9d9;
                border-radius: 4px;
                background-color: #ffffff;
                min-width: 50px;
            }
            QPushButton:hover {
                border-color: #ff4d4f;
                background-color: #fff1f0;
                color: #ff4d4f;
            }
        """)
        # 连接删除事件，确保正确捕获索引
        btn.clicked.connect(lambda checked, idx=index: self._remove_image_by_index(idx))
        self.image_buttons.append(btn)
        # 在提示文本之前插入按钮
        self.image_buttons_layout.insertWidget(self.image_buttons_layout.count() - 1, btn)

    def _remove_image_by_index(self, index: int):
        """根据索引删除图片"""
        if 0 <= index < len(self.selected_images):
            # 删除图片路径
            self.selected_images.pop(index)
            # 删除按钮
            btn = self.image_buttons.pop(index)
            btn.setParent(None)
            btn.deleteLater()
            # 更新剩余按钮的文本和事件
            self._refresh_image_buttons()

    def _refresh_image_buttons(self):
        """刷新图片按钮的文本和事件"""
        for i, btn in enumerate(self.image_buttons):
            chinese_num = self._number_to_chinese(i + 1)
            btn.setText(f"图{chinese_num}")
            # 断开旧连接
            try:
                btn.clicked.disconnect()
            except TypeError:
                pass  # 如果没有连接，忽略错误
            # 连接新事件，使用lambda并确保正确捕获索引
            btn.clicked.connect(lambda checked, idx=i: self._remove_image_by_index(idx))

    def _clear_images(self):
        """清空所有图片"""
        # 删除所有按钮
        for btn in self.image_buttons:
            btn.setParent(None)
            btn.deleteLater()
        self.image_buttons.clear()
        self.selected_images.clear()

    def _on_generate_image_clicked(self):
        """生成图片按钮点击：生成中再次点击即取消"""
        if self.worker_thread and self.worker_thread.isRunning():
            self._cancel_image_generation()
            return

        # 检查是否启用了角色线稿模式
        if self.line_art_mode_enabled.isChecked():
            # 使用UI中的线稿提示词
            line_art_prompt = self.line_art_prompt_input.toPlainText().strip()
            if not line_art_prompt:
                QMessageBox.warning(self, "提示", "线稿提示词不能为空")
                return
            prompt_text = line_art_prompt
            
            # 如果启用了特别要求，追加到线稿提示词后面
            if self.special_requirement_enabled.isChecked():
                special_text = self.special_requirement_input.toPlainText().strip()
                if special_text:
                    prompt_text = prompt_text + "\n\n额外要求：" + special_text
        else:
            # 正常模式：使用表单数据
            prompt_data = self._collect_form_data()
            prompt_text = json.dumps(prompt_data, ensure_ascii=False, indent=2)
            
            if not prompt_text or prompt_text.strip() == "{}":
                QMessageBox.warning(self, "提示", "当前提示词为空，请先填写表单内容")
                return

            # 如果启用了特别要求，追加到prompt后面
            if self.special_requirement_enabled.isChecked():
                special_text = self.special_requirement_input.toPlainText().strip()
                if special_text:
                    prompt_text = prompt_text + "\n\n特别要求：" + special_text

        try:
            provider = self.image_provider_combo.currentData()
            if not provider:
                QMessageBox.warning(self, "未配置图片渠道", "请先在 AI 配置中填写渠道密钥。")
                return
            model = self.image_model_combo.currentText().strip()
            image_config = self.config_manager.get_active_image_config(provider, model)
        except ValueError as exc:
            QMessageBox.warning(self, "图片渠道配置无效", f"{exc}\n请重新选择并保存图片生成渠道。")
            return
        if not image_config.get("api_key"):
            reply = QMessageBox.question(
                self,
                "未配置 API",
                "尚未配置当前图片生成 API，是否现在配置？",
                QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._open_image_config_dialog()
            return

        # 验证通过后，立即禁用按钮，防止重复点击
        self._set_image_generating_state(True)
        
        self.generated_image_bytes = None
        self.generated_pixmap = None
        self.preview_area.setText("正在生成，请稍候...")
        self.preview_area.clearSourcePixmap()
        self.save_image_btn.setEnabled(False)
        if hasattr(self, "copy_image_btn"):
            self.copy_image_btn.setEnabled(False)
        
        # 根据模式显示不同的状态信息
        if self.line_art_mode_enabled.isChecked():
            self._set_image_status("提交到图片生成服务（角色线稿模式）", "#1890ff")
        else:
            self._set_image_status("提交到图片生成服务", "#1890ff")
        # 禁用点击预览功能
        self._enable_image_preview(False)

        self.worker_thread = ImageGenerationThread(
            prompt=prompt_text,
            image_paths=self.selected_images,
            options=self._collect_image_options(),
            image_config=image_config,
        )
        self.worker_thread.progress.connect(lambda msg: self._set_image_status(f"⏳ {msg}", "#1890ff"))
        self.worker_thread.image_ready.connect(self._on_image_ready)
        self.worker_thread.error.connect(self._on_generation_error)
        self.worker_thread.finished.connect(self._on_thread_finished)
        self.worker_thread.start()

    def _cancel_image_generation(self):
        """取消当前生图：断开信号后放弃该线程，UI 立即恢复可用。"""
        thread = self.worker_thread
        if not thread:
            return
        thread.cancel()
        for signal in (thread.progress, thread.image_ready, thread.error, thread.finished):
            try:
                signal.disconnect()
            except TypeError:
                pass
        # 保住引用直到线程自然结束，避免 QThread 运行中被析构
        self._stale_image_threads = [
            t for t in getattr(self, "_stale_image_threads", []) if t.isRunning()
        ]
        self._stale_image_threads.append(thread)
        self.worker_thread = None
        self._set_image_generating_state(False)
        self.preview_area.setText("已取消生成")
        self._set_image_status("已取消", "#8c8c8c")

    def _on_thread_finished(self):
        """线程完成"""
        self._set_image_generating_state(False)
        self.worker_thread = None

    def _on_image_ready(self, image_bytes: bytes):
        """图片生成完成"""
        self.generated_image_bytes = image_bytes
        pixmap = QPixmap.fromImage(QImage.fromData(image_bytes))
        self.generated_pixmap = pixmap
        self._append_to_history(image_bytes, pixmap)
        self._refresh_preview_pixmap()
        self.save_image_btn.setEnabled(True)
        if hasattr(self, "copy_image_btn"):
            self.copy_image_btn.setEnabled(True)
        self._set_image_status("生成完成，点击图片可查看大图", "#52c41a")
        # 启用点击预览功能
        self._enable_image_preview(True)

    def _append_to_history(self, image_bytes: bytes, pixmap: QPixmap):
        """记录生成历史并刷新缩略图条。"""
        self.image_history.append((image_bytes, pixmap))
        if len(self.image_history) > MAX_IMAGE_HISTORY:
            self.image_history.pop(0)
            self.history_list.takeItem(0)
        thumbnail = pixmap.scaled(
            56, 56,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        item = QListWidgetItem(QIcon(thumbnail), "")
        item.setToolTip(f"第 {len(self.image_history)} 张，点击回看")
        self.history_list.addItem(item)
        self.history_list.setCurrentItem(item)
        self.history_list.scrollToItem(item)
        self.history_list.setVisible(True)

    def _on_history_item_clicked(self, item: QListWidgetItem):
        """点击历史缩略图，切换主预览。"""
        row = self.history_list.row(item)
        if not (0 <= row < len(self.image_history)):
            return
        image_bytes, pixmap = self.image_history[row]
        self.generated_image_bytes = image_bytes
        self.generated_pixmap = pixmap
        self._refresh_preview_pixmap()
        self.save_image_btn.setEnabled(True)
        if hasattr(self, "copy_image_btn"):
            self.copy_image_btn.setEnabled(True)
        self._enable_image_preview(True)
        self._set_image_status(f"已切换到历史第 {row + 1} 张", "#595959")

    def _copy_image_to_clipboard(self):
        """把当前图片复制到剪贴板。"""
        if not self.generated_pixmap:
            return
        QApplication.clipboard().setPixmap(self.generated_pixmap)
        self._set_image_status("图片已复制到剪贴板", "#52c41a")

    def _on_generation_error(self, message: str):
        """生成错误"""
        self._set_image_status("生成失败", "#ff4d4f", message)
        self.preview_area.setText("生成失败，请调整参数后重试")
        # 禁用点击预览功能
        self._enable_image_preview(False)
        # 确保在错误时也恢复按钮状态（虽然 _on_thread_finished 也会调用，但这里明确调用更安全）
        self._set_image_generating_state(False)
        self._show_image_error(message)

    def _show_image_error(self, message: str):
        """弹窗展示生成错误，支持选中和一键复制。非阻塞，避免卡事件循环。"""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("图片生成失败")
        box.setText("图片生成失败，错误详情：")
        box.setInformativeText(message)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        copy_btn = box.addButton("复制错误信息", QMessageBox.ButtonRole.ActionRole)
        box.addButton("关闭", QMessageBox.ButtonRole.RejectRole)

        def _on_clicked(button):
            if button is copy_btn:
                QApplication.clipboard().setText(message)
                self._set_image_status("错误信息已复制到剪贴板", "#8c8c8c", message)

        box.buttonClicked.connect(_on_clicked)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        box.open()

    def _set_image_generating_state(self, generating: bool):
        """设置生成状态"""
        self.image_provider_combo.setEnabled(not generating)
        self.image_model_combo.setEnabled(not generating)
        for combo in self.image_option_widgets.values():
            combo.setEnabled(not generating)
        self.add_image_btn.setEnabled(not generating)
        # 禁用所有图片按钮
        for btn in self.image_buttons:
            btn.setEnabled(not generating)
        if generating:
            # 生成中按钮变为取消入口，保持可点
            self.generate_image_btn.setText("取消生成")
            self.generate_image_btn.setEnabled(True)
        else:
            self.generate_image_btn.setText("生成图片")
            self._update_image_config_status()

    def _save_image(self):
        """保存图片"""
        if not self.generated_image_bytes:
            return

        default_name = time.strftime("generated_%Y%m%d_%H%M%S.png")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "另存为",
            os.path.join(get_last_dir("save"), default_name),
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg)"
        )
        if not file_path:
            return
        remember_last_dir(file_path, "save")

        suffix = os.path.splitext(file_path)[1].lower()
        format_name = "PNG" if suffix in ("", ".png") else "JPEG"
        image = QImage.fromData(self.generated_image_bytes)
        if not image.save(file_path, format_name):
            QMessageBox.critical(self, "错误", "保存图片失败，请重试")
        else:
            self._set_image_status(f"图片已保存到 {file_path}", "#52c41a")

    def _set_image_status(
        self,
        text: str,
        color: str = "#757575",
        tooltip: str = "",
    ):
        """设置状态文本"""
        self.image_status_label.setText(text)
        self.image_status_label.setToolTip(tooltip)
        self.image_status_label.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _open_image_config_dialog(self):
        """打开当前图片渠道的连接配置。"""
        from nano_banana.desktop.dialogs.config_dialog import UnifiedAIConfigDialog
        provider = self.image_provider_combo.currentData() or self.config_manager.get_image_provider()
        dialog = UnifiedAIConfigDialog(self, initial_tab="image", image_provider=provider)
        dialog.config_saved.connect(self._refresh_image_config_from_dialog)
        dialog.exec()

    def _refresh_image_config_from_dialog(self):
        provider = self.image_provider_combo.currentData() or ""
        self._cache_current_image_options()
        provider = self._refresh_image_provider_choices(provider)
        if not provider:
            self._render_image_options("", "", cache_current=False)
            return
        self._populate_image_models(provider)
        model = self.image_model_combo.currentText().strip()
        self.config_manager.set_active_image_selection(provider, model)
        self._render_image_options(provider, model, cache_current=False)

    def _refresh_preview_pixmap(self):
        """刷新预览图片"""
        if not self.generated_pixmap:
            self.preview_area.clearSourcePixmap()
            self.preview_area.setScaledContents(False)
            return

        self.preview_area.setSourcePixmap(self.generated_pixmap)
        self.preview_area.setScaledContents(False)
    
    def _enable_image_preview(self, enabled: bool):
        """启用/禁用图片预览功能"""
        if enabled and self.generated_pixmap:
            # 设置手型光标，提示可点击
            self.preview_area.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        else:
            # 恢复默认光标
            self.preview_area.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
    
    def _show_image_preview(self):
        """显示图片预览对话框"""
        if not self.generated_pixmap:
            return
        
        dialog = ImagePreviewDialog(self.generated_pixmap, self)
        dialog.exec()
