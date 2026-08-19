"""AI 对话框。"""
import json
import os
from typing import List
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QFrame,
    QWidget,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
    QScrollArea,
    QComboBox,
    QTabWidget,
)
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFont, QIcon, QPixmap

from nano_banana.core.config import AIConfigManager
from nano_banana.core.images.provider_config import IMAGE_PROVIDER_META
from nano_banana.desktop.ai_service import AIService


class AIConfigDialog(QDialog):
    """AI配置对话框"""
    
    config_saved = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_manager = AIConfigManager()
        self._setup_ui()
        self._load_config()
    
    def _setup_ui(self):
        self.setWindowTitle("AI API 配置")
        self.setMinimumWidth(500)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # 说明
        info_label = QLabel(
            "请配置 OpenAI 兼容的 API 信息。"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #757575; font-size: 12px; margin-bottom: 8px;")
        layout.addWidget(info_label)
        
        # Base URL
        url_container = QWidget()
        url_layout = QVBoxLayout(url_container)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(4)
        
        url_label = QLabel("API Base URL")
        url_label.setStyleSheet("font-weight: 500; font-size: 13px;")
        url_layout.addWidget(url_label)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://api.openai.com/v1")
        url_layout.addWidget(self.url_input)
        
        url_hint = QLabel(" 通义千问: https://dashscope.aliyuncs.com/compatible-mode/v1")
        url_hint.setStyleSheet("color: #9E9E9E; font-size: 11px;")
        url_hint.setWordWrap(True)
        url_layout.addWidget(url_hint)
        
        layout.addWidget(url_container)
        
        # API Key
        key_container = QWidget()
        key_layout = QVBoxLayout(key_container)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(4)
        
        key_label = QLabel("API Key")
        key_label.setStyleSheet("font-weight: 500; font-size: 13px;")
        key_layout.addWidget(key_label)
        
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("sk-...")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        key_layout.addWidget(self.key_input)
        
        # 显示/隐藏密钥按钮
        key_actions = QHBoxLayout()
        key_actions.setContentsMargins(0, 0, 0, 0)
        
        self.show_key_btn = QPushButton("显示密钥")
        self.show_key_btn.setFixedWidth(90)
        self.show_key_btn.clicked.connect(self._toggle_key_visibility)
        key_actions.addWidget(self.show_key_btn)
        key_actions.addStretch()
        key_layout.addLayout(key_actions)
        
        layout.addWidget(key_container)
        
        # Model
        model_container = QWidget()
        model_layout = QVBoxLayout(model_container)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setSpacing(4)
        
        model_label = QLabel("模型名称")
        model_label.setStyleSheet("font-weight: 500; font-size: 13px;")
        model_layout.addWidget(model_label)
        
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("gpt-5.1")
        model_layout.addWidget(self.model_input)
        
        model_hint = QLabel("OpenAI: gpt-4.1, gpt-5.1  |   通义: qwen3-max")
        model_hint.setStyleSheet("color: #9E9E9E; font-size: 11px;")
        model_hint.setWordWrap(True)
        model_layout.addWidget(model_hint)
        
        layout.addWidget(model_container)
        
        layout.addStretch()
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        btn_layout.addStretch()
        
        save_btn = QPushButton("保存配置")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save_config)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def _load_config(self):
        """加载现有配置"""
        config = self.config_manager.load_config()
        # 只在配置存在且非空时设置文本，否则使用placeholder
        base_url = config.get("base_url", "")
        if base_url:
            self.url_input.setText(base_url)
        
        api_key = config.get("api_key", "")
        if api_key:
            self.key_input.setText(api_key)
        
        model = config.get("model", "")
        if model:
            self.model_input.setText(model)
    
    def _toggle_key_visibility(self):
        """切换密钥可见性"""
        if self.key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_key_btn.setText("隐藏密钥")
        else:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_key_btn.setText("显示密钥")
    
    def _save_config(self):
        """保存配置"""
        base_url = self.url_input.text().strip()
        api_key = self.key_input.text().strip()
        model = self.model_input.text().strip()
        
        if not api_key:
            QMessageBox.warning(self, "提示", "请输入 API Key")
            return
        
        # 直接保存用户输入的值（包括空值），不填充默认值
        config = {
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
        }
        
        if self.config_manager.save_config(config):
            self.config_saved.emit()
            self.accept()
        else:
            QMessageBox.critical(self, "错误", "保存配置失败")


class UnifiedAIConfigDialog(QDialog):
    """分别管理 AI 对话和图片生成连接配置。"""
    
    config_saved = pyqtSignal()
    
    def __init__(self, parent=None, initial_tab: str = "chat", image_provider: str | None = None):
        super().__init__(parent)
        self.config_manager = AIConfigManager()
        self._image_config_drafts = {}
        self._current_image_provider = None
        self._initial_tab = initial_tab
        self._requested_image_provider = image_provider
        self._setup_ui()
        self._load_config()
    
    def _setup_ui(self):
        self.setWindowTitle("AI 配置")
        self.setMinimumWidth(600)
        self.setModal(True)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f7fa;
            }
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #d9d9d9;
                border-radius: 6px;
                background-color: white;
                min-height: 32px;
            }
            QComboBox:hover {
                border-color: #40a9ff;
            }
            QLineEdit, QTextEdit {
                padding: 8px;
                border: 1px solid #d9d9d9;
                border-radius: 6px;
                background-color: white;
            }
            QLineEdit:focus, QTextEdit:focus {
                border-color: #40a9ff;
            }
            QPushButton {
                padding: 8px 24px;
                border-radius: 6px;
                border: 1px solid #d9d9d9;
                background-color: #ffffff;
                font-size: 13px;
                min-width: 80px;
            }
            QPushButton:hover {
                border-color: #40a9ff;
                color: #40a9ff;
            }
            QPushButton#primaryButton {
                background-color: #1890ff;
                color: white;
                border: none;
                font-weight: 500;
            }
            QPushButton#primaryButton:hover {
                background-color: #40a9ff;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)
        
        # 标题
        title = QLabel("AI 配置")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #262626;")
        layout.addWidget(title)
        
        description = QLabel("对话模型与图片生成渠道完全独立，配置不会互相复用。")
        description.setStyleSheet("color: #8c8c8c; font-size: 12px;")
        layout.addWidget(description)

        self.config_tabs = QTabWidget()
        
        # ===== 第一部分：提示词生成/修改AI配置 =====
        prompt_frame = QFrame()
        prompt_frame.setObjectName("promptConfigFrame")
        prompt_frame.setStyleSheet("""
            QFrame#promptConfigFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f0f7ff, stop:1 #ffffff);
                border: 2px solid #1890ff;
                border-radius: 12px;
                padding: 4px;
            }
        """)
        prompt_layout = QVBoxLayout(prompt_frame)
        prompt_layout.setContentsMargins(20, 20, 20, 20)
        prompt_layout.setSpacing(16)
        
        # 标题区域，带背景
        prompt_title_container = QWidget()
        prompt_title_container.setStyleSheet("""
            QWidget {
                background-color: #1890ff;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        prompt_title_layout = QHBoxLayout(prompt_title_container)
        prompt_title_layout.setContentsMargins(0, 0, 0, 0)
        prompt_title_layout.setSpacing(10)
        
        prompt_title = QLabel("提示词生成/修改 AI")
        prompt_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        prompt_title_layout.addWidget(prompt_title)
        prompt_title_layout.addStretch()
        
        prompt_layout.addWidget(prompt_title_container)
        
        prompt_layout.addWidget(self._build_labeled_widget("Base URL", self._create_url_input("prompt")))
        prompt_layout.addWidget(self._build_labeled_widget("API Key", self._create_key_input("prompt")))
        prompt_layout.addWidget(self._build_labeled_widget("模型名称", self._create_model_input("prompt")))
        
        prompt_hint = QLabel("用于 AI 生成/修改提示词，采用 OpenAI-compatible 接口。")
        prompt_hint.setWordWrap(True)
        prompt_hint.setStyleSheet("color: #595959; font-size: 12px;")
        prompt_layout.insertWidget(1, prompt_hint)
        self.config_tabs.addTab(prompt_frame, "AI 对话")
        
        # ===== 第二部分：图片生成AI配置 =====
        image_frame = QFrame()
        image_frame.setObjectName("imageConfigFrame")
        image_frame.setStyleSheet("""
            QFrame#imageConfigFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #fff7e6, stop:1 #ffffff);
                border: 2px solid #fa8c16;
                border-radius: 12px;
                padding: 4px;
            }
        """)
        image_layout = QVBoxLayout(image_frame)
        image_layout.setContentsMargins(20, 20, 20, 20)
        image_layout.setSpacing(16)
        
        # 标题区域，带背景
        image_title_container = QWidget()
        image_title_container.setStyleSheet("""
            QWidget {
                background-color: #fa8c16;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        image_title_layout = QHBoxLayout(image_title_container)
        image_title_layout.setContentsMargins(0, 0, 0, 0)
        image_title_layout.setSpacing(10)
        
        image_title = QLabel("图片生成 AI")
        image_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        image_title_layout.addWidget(image_title)
        image_title_layout.addStretch()
        
        image_layout.addWidget(image_title_container)
        
        image_config_body = QWidget()
        image_config_body_layout = QHBoxLayout(image_config_body)
        image_config_body_layout.setContentsMargins(0, 0, 0, 0)
        image_config_body_layout.setSpacing(16)

        provider_nav = QWidget()
        provider_nav.setFixedWidth(190)
        provider_nav_layout = QVBoxLayout(provider_nav)
        provider_nav_layout.setContentsMargins(0, 0, 0, 0)
        provider_nav_layout.setSpacing(8)

        provider_nav_title = QLabel("图片渠道")
        provider_nav_title.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #8c8c8c; padding-left: 4px;"
        )
        provider_nav_layout.addWidget(provider_nav_title)

        self.image_provider_input = QListWidget()
        self.image_provider_input.setSpacing(6)
        self.image_provider_input.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.image_provider_input.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
                padding: 0;
            }
            QListWidget::item {
                background-color: #ffffff;
                border: 1px solid #e8e8e8;
                border-radius: 8px;
                color: #595959;
                padding: 9px 12px;
            }
            QListWidget::item:hover {
                background-color: #fffaf0;
                border-color: #ffc069;
            }
            QListWidget::item:selected {
                background-color: #fff7e6;
                border: 1px solid #fa8c16;
                color: #d46b08;
                font-weight: 600;
            }
        """)
        for provider_id, meta in IMAGE_PROVIDER_META.items():
            item = QListWidgetItem(meta["label"])
            item.setSizeHint(QSize(0, 54))
            item.setData(Qt.ItemDataRole.UserRole, provider_id)
            self.image_provider_input.addItem(item)
        self.image_provider_input.currentRowChanged.connect(self._on_image_provider_changed)
        provider_nav_layout.addWidget(self.image_provider_input, 1)
        image_config_body_layout.addWidget(provider_nav)

        image_fields = QWidget()
        image_fields_layout = QVBoxLayout(image_fields)
        image_fields_layout.setContentsMargins(0, 0, 0, 0)
        image_fields_layout.setSpacing(16)
        image_fields_layout.addWidget(self._build_labeled_widget("Base URL", self._create_url_input("image")))
        image_fields_layout.addWidget(self._build_labeled_widget("API Key", self._create_key_input("image")))
        image_fields_layout.addWidget(self._build_labeled_widget("模型名称", self._create_model_input("image")))
        image_config_body_layout.addWidget(image_fields, 1)
        image_layout.addWidget(image_config_body, 1)

        image_hint = QLabel("这里只管理各图片渠道的连接信息；当前使用渠道请在主界面切换。")
        image_hint.setWordWrap(True)
        image_hint.setStyleSheet("color: #595959; font-size: 12px;")
        image_layout.insertWidget(1, image_hint)
        self.config_tabs.addTab(image_frame, "图片生成")
        layout.addWidget(self.config_tabs, 1)
        self.config_tabs.setCurrentIndex(1 if self._initial_tab == "image" else 0)
        
        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        
        save_btn = QPushButton("保存配置")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save_config)
        btn_row.addWidget(save_btn)
        
        layout.addLayout(btn_row)
    
    def _create_url_input(self, prefix: str) -> QWidget:
        """创建URL输入框"""
        widget = QLineEdit()
        if prefix == "prompt":
            widget.setPlaceholderText("https://api.openai.com/v1")
            self.prompt_url_input = widget
        else:
            widget.setPlaceholderText("https://generativelanguage.googleapis.com")
            self.image_url_input = widget
        return widget
    
    def _create_key_input(self, prefix: str) -> QWidget:
        """创建API Key输入框"""
        widget = QLineEdit()
        widget.setEchoMode(QLineEdit.EchoMode.Password)
        widget.setPlaceholderText("sk-...")
        toggle_action = QAction("显示", widget)
        widget.addAction(toggle_action, QLineEdit.ActionPosition.TrailingPosition)
        toggle_action.triggered.connect(
            lambda _checked=False, field=widget, action=toggle_action: self._toggle_secret(field, action)
        )
        if prefix == "prompt":
            self.prompt_key_input = widget
        else:
            self.image_key_input = widget
        return widget

    @staticmethod
    def _toggle_secret(field: QLineEdit, action) -> None:
        visible = field.echoMode() == QLineEdit.EchoMode.Password
        field.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        action.setText("隐藏" if visible else "显示")
    
    def _create_model_input(self, prefix: str) -> QWidget:
        """创建模型输入框"""
        if prefix == "prompt":
            widget = QLineEdit()
            widget.setPlaceholderText("gpt-5.1")
            self.prompt_model_input = widget
        else:
            widget = QComboBox()
            widget.setEditable(True)
            suggestions = []
            for meta in IMAGE_PROVIDER_META.values():
                suggestions.extend(meta.get("model_suggestions") or [])
            # 去重并保持顺序
            seen = set()
            ordered = []
            for name in suggestions:
                if name not in seen:
                    seen.add(name)
                    ordered.append(name)
            widget.addItems(ordered)
            self.image_model_input = widget
        return widget
    
    def _build_labeled_widget(self, label_text: str, widget: QWidget) -> QWidget:
        """创建带标签的输入组件"""
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)
        
        label = QLabel(label_text)
        label.setStyleSheet("font-weight: 600; font-size: 13px; color: #262626;")
        container_layout.addWidget(label)
        container_layout.addWidget(widget)
        return container
    
    def _load_config(self):
        """加载现有配置"""
        config = self.config_manager.load_config()
        self._image_config_cache = config
        self._image_config_drafts = {}
        for provider_id in IMAGE_PROVIDER_META:
            self._image_config_drafts[provider_id] = (
                self.config_manager.get_image_provider_config(provider_id)
            )
        
        # 提示词生成AI配置 - 只在配置存在且非空时设置文本，否则使用placeholder
        base_url = config.get("base_url", "")
        if base_url:
            self.prompt_url_input.setText(base_url)
        
        api_key = config.get("api_key", "")
        if api_key:
            self.prompt_key_input.setText(api_key)
        
        model = config.get("model", "")
        if model:
            self.prompt_model_input.setText(model)
        
        provider = self._requested_image_provider or config.get("image_provider", "") or "gemini"
        self._refresh_provider_labels()
        selected_row = 0
        for index in range(self.image_provider_input.count()):
            if self.image_provider_input.item(index).data(Qt.ItemDataRole.UserRole) == provider:
                selected_row = index
                break
        self.image_provider_input.setCurrentRow(selected_row)
        self._on_image_provider_changed()

    def _refresh_provider_labels(self) -> None:
        for index in range(self.image_provider_input.count()):
            item = self.image_provider_input.item(index)
            provider = item.data(Qt.ItemDataRole.UserRole)
            meta = IMAGE_PROVIDER_META[provider]
            draft = self._image_config_drafts.get(provider, {})
            configured = all(draft.get(key) for key in ("base_url", "api_key", "model"))
            status = "✓ 已配置" if configured else "未配置"
            item.setText(f"{meta['label']}\n{status}")

    def _on_image_provider_changed(self, _row: int = -1):
        """根据当前图片 provider 加载对应配置。"""
        current_item = self.image_provider_input.currentItem()
        provider = (
            current_item.data(Qt.ItemDataRole.UserRole)
            if current_item is not None
            else "gemini"
        )
        meta = IMAGE_PROVIDER_META.get(provider) or IMAGE_PROVIDER_META["gemini"]

        previous_provider = self._current_image_provider
        if previous_provider and previous_provider in self._image_config_drafts:
            self._image_config_drafts[previous_provider] = {
                "base_url": self.image_url_input.text(),
                "api_key": self.image_key_input.text(),
                "model": self.image_model_input.currentText(),
            }
            self._refresh_provider_labels()

        draft = self._image_config_drafts.get(provider) or {
            "base_url": "",
            "api_key": "",
            "model": meta.get("default_model") or "",
        }
        self._current_image_provider = provider

        self.image_url_input.setPlaceholderText(meta.get("url_placeholder") or "")
        self.image_url_input.setText(draft["base_url"])
        self.image_key_input.setText(draft["api_key"])
        model = draft["model"]

        # 刷新模型建议：当前渠道优先
        self.image_model_input.blockSignals(True)
        self.image_model_input.clear()
        suggestions = list(meta.get("model_suggestions") or [])
        self.image_model_input.addItems(suggestions)
        index = self.image_model_input.findText(model)
        if index >= 0:
            self.image_model_input.setCurrentIndex(index)
        else:
            self.image_model_input.setEditText(model)
        self.image_model_input.blockSignals(False)
    
    def _save_config(self):
        """保存配置"""
        # 提示词生成AI配置 - 直接获取用户输入，不填充默认值
        prompt_base_url = self.prompt_url_input.text().strip()
        prompt_api_key = self.prompt_key_input.text().strip()
        prompt_model = self.prompt_model_input.text().strip()
        
        # 图片生成AI配置 - 直接获取用户输入，不填充默认值
        current_item = self.image_provider_input.currentItem()
        image_provider = (
            current_item.data(Qt.ItemDataRole.UserRole)
            if current_item is not None
            else "gemini"
        )
        image_base_url = self.image_url_input.text().strip()
        image_api_key = self.image_key_input.text().strip()
        image_model = self.image_model_input.currentText().strip()
        self._image_config_drafts[image_provider] = {
            "base_url": image_base_url,
            "api_key": image_api_key,
            "model": image_model,
        }
        
        meta = IMAGE_PROVIDER_META.get(image_provider)
        if not meta:
            QMessageBox.warning(self, "提示", f"未知图片生成渠道: {image_provider}")
            return
        # 保存所有渠道草稿，渠道切换不会丢失本次弹窗中的编辑。
        config = {
            "base_url": prompt_base_url,
            "api_key": prompt_api_key,
            "model": prompt_model,
        }
        for provider_id, draft in self._image_config_drafts.items():
            provider_keys = IMAGE_PROVIDER_META[provider_id]["config_keys"]
            config.update({
                provider_keys["base_url"]: draft["base_url"].strip(),
                provider_keys["api_key"]: draft["api_key"].strip(),
                provider_keys["model"]: draft["model"].strip(),
            })
        
        if self.config_manager.save_config(config):
            self.config_saved.emit()
            self.accept()
        else:
            QMessageBox.critical(self, "错误", "保存配置失败，请重试")
