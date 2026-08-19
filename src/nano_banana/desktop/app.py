"""主应用程序窗口"""
import json
import os
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QSplitter,
    QPushButton,
    QTextEdit,
    QLabel,
    QFrame,
    QMessageBox,
    QComboBox,
    QInputDialog,
    QMenu,
    QCheckBox,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QFont, QAction, QPixmap, QIcon, QCursor, QDesktopServices

try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

from nano_banana.desktop.components.combo_input import ComboInput
from nano_banana.desktop.components.field_group import FieldGroup
from nano_banana.desktop.components.aspect_ratio_selector import AspectRatioSelector
from nano_banana.desktop.components.multi_select import MultiSelectInput
from nano_banana.desktop.components.tag_text_input import TagTextInput, normalize_negative_prompt
from nano_banana.core.yaml_handler import YamlHandler
from nano_banana.core.presets import PresetManager
from nano_banana.core.resource_path import get_images_dir
from nano_banana.desktop.dialogs.generate_dialog import AIGenerateDialog
from nano_banana.core.config import AIConfigManager
from nano_banana.desktop.styles import LIGHT_THEME
from nano_banana.desktop.preview import ClickableLabel
from nano_banana.core.prompt_doc import flatten, nest, order_document, subset
from nano_banana.core.schema import default_negative_prompt, get_schema
from nano_banana.desktop.form_panel import add_schema_field_groups
from nano_banana.desktop.image_gen import ImageGenController
from nano_banana.desktop.window_utils import fit_window_to_screen


DEFAULT_NEGATIVE_PROMPT = default_negative_prompt()


class PromptGeneratorApp(ImageGenController, QMainWindow):
    """提示词生成器主窗口"""

    def __init__(self):
        super().__init__()
        self.yaml_handler = YamlHandler()
        self.preset_manager = PresetManager()
        self.config_manager = AIConfigManager()
        self.prompt_schema = get_schema()
        self.field_widgets = {}  # 存储所有字段的widget引用
        self.current_preset_name = None
        self.category_preset_selectors = {}
        
        # 生图相关
        self.selected_images = []
        self.image_buttons = []  # 存储图片按钮的列表
        self.generated_image_bytes = None
        self.generated_pixmap = None
        self.worker_thread = None
        self.image_option_widgets = {}
        self._active_image_provider = ""
        self._active_image_model = ""

        self._setup_window()
        self._setup_ui()
        self._load_presets_to_selector()

    def _setup_window(self):
        self.setWindowTitle("Nano Banana 生图工具")
        # 尺寸按屏幕可用区域钳制，小分辨率/高DPI缩放下不会超出屏幕
        fit_window_to_screen(self, 1400, 900, min_width=1200, min_height=800)
        self.setStyleSheet(LIGHT_THEME)
        
        # 设置窗口图标
        icon_path = get_images_dir() / "logo.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # 标题区域（含预设选择器）
        header = self._create_header()
        main_layout.addWidget(header)

        # 预设工具栏
        preset_bar = self._create_preset_bar()
        main_layout.addWidget(preset_bar)

        # 主内容区域 - 使用分割器（三列布局）
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(8)
        # 禁止把面板拖成 0 宽导致内容"消失"
        self.main_splitter.setChildrenCollapsible(False)

        # 左侧：表单区域
        form_area = self._create_form_area()
        self.main_splitter.addWidget(form_area)

        # 中间：JSON预览区域（可折叠）
        self.json_preview_area = self._create_json_preview_area()
        self.main_splitter.addWidget(self.json_preview_area)

        # 右侧：生图区域
        image_generate_area = self._create_image_generate_area()
        self.main_splitter.addWidget(image_generate_area)

        # 窗口拉伸时三列按比例分配多余空间
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 1)

        # 设置分割比例，默认隐藏中间列
        self.main_splitter.setSizes([600, 0, 600])
        # 默认隐藏中间列
        self.json_preview_area.setVisible(False)
        self.json_preview_visible = False
        main_layout.addWidget(self.main_splitter, 1)

        # 底部按钮区域
        button_bar = self._create_button_bar()
        main_layout.addWidget(button_bar)

    def _create_header(self) -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 10)

        # Logo - 可点击
        logo_label = ClickableLabel()
        logo_path = get_images_dir() / "logo.png"
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            # 缩放logo到合适大小，保持高质量
            scaled_pixmap = pixmap.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
        logo_label.setFixedSize(52, 52)
        logo_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        logo_label.setToolTip("点击访问 GitHub 仓库")
        logo_label.clicked.connect(self._open_github_link)
        layout.addWidget(logo_label)

        # 标题 - 可点击
        title_container = QWidget()
        title_layout = QVBoxLayout(title_container)
        title_layout.setContentsMargins(12, 0, 0, 0)
        title_layout.setSpacing(4)

        title = ClickableLabel("Nano Banana 图片生成工具")
        title.setObjectName("appTitle")
        title.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        title.setToolTip("点击访问 GitHub 仓库")
        title.clicked.connect(self._open_github_link)
        title_layout.addWidget(title)

        subtitle = ClickableLabel("一站式AI图片生成工具，通过结构化提示词控制图片生成质量")
        subtitle.setObjectName("appSubtitle")
        subtitle.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        subtitle.setToolTip("点击访问 GitHub 仓库")
        subtitle.clicked.connect(self._open_github_link)
        title_layout.addWidget(subtitle)

        layout.addWidget(title_container)
        layout.addStretch()

        return header

    def _open_github_link(self):
        """打开GitHub仓库链接"""
        url = QUrl("https://github.com/lissettecarlr/nano-banana-prompt-studio")
        QDesktopServices.openUrl(url)

    def _create_preset_bar(self) -> QWidget:
        """创建预设工具栏"""
        bar = QFrame()
        bar.setObjectName("presetBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 预设标签
        label = QLabel("预设:")
        label.setObjectName("presetLabel")
        layout.addWidget(label)

        # 预设选择器
        self.preset_selector = QComboBox()
        self.preset_selector.setObjectName("presetSelector")
        self.preset_selector.setMinimumWidth(250)
        self.preset_selector.setPlaceholderText("选择预设...")
        self.preset_selector.currentTextChanged.connect(self._on_preset_selected)
        layout.addWidget(self.preset_selector)

        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.setToolTip("刷新预设列表")
        refresh_btn.clicked.connect(self._load_presets_to_selector)
        layout.addWidget(refresh_btn)

        # AI提示词生成按钮
        ai_btn = QPushButton("AI提示词生成")
        ai_btn.setObjectName("aiGenerateButton")
        ai_btn.setToolTip("使用AI根据描述自动生成提示词")
        ai_btn.clicked.connect(self._show_ai_generate_dialog)
        layout.addWidget(ai_btn)

        # 添加AI修改按钮
        ai_modify_btn = QPushButton("AI提示词修改")
        ai_modify_btn.setObjectName("aiGenerateButton")  # 使用相同的对象名以保持样式一致
        ai_modify_btn.setToolTip("使用AI根据描述修改当前提示词")
        ai_modify_btn.clicked.connect(self._show_ai_modify_dialog)
        layout.addWidget(ai_modify_btn)

        # 移除独立的AI生图按钮，已整合到主界面右侧

        layout.addStretch()

        # 管理预设按钮
        manage_btn = QPushButton("管理预设")
        manage_btn.setObjectName("secondaryButton")
        manage_btn.clicked.connect(self._show_preset_menu)
        layout.addWidget(manage_btn)

        # AI配置按钮
        ai_config_btn = QPushButton("AI配置")
        ai_config_btn.setObjectName("secondaryButton")
        ai_config_btn.clicked.connect(self._open_ai_config_dialog)
        layout.addWidget(ai_config_btn)

        return bar

    def _create_form_area(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 16, 0)

        add_schema_field_groups(self, layout)

        # ===== 特别要求（可选） =====
        special_container = QWidget()
        special_layout = QVBoxLayout(special_container)
        special_layout.setContentsMargins(0, 0, 0, 0)
        special_layout.setSpacing(0)

        # 启用开关
        self.special_requirement_enabled = QCheckBox("启用特别要求")
        self.special_requirement_enabled.setObjectName("specialRequirementToggle")
        self.special_requirement_enabled.setChecked(False)  # 默认不启用
        self.special_requirement_enabled.stateChanged.connect(self._on_special_requirement_toggle_changed)
        special_layout.addWidget(self.special_requirement_enabled)

        # 特别要求分组
        self.special_requirement_group = FieldGroup("特别要求", color_class="special")
        self.special_requirement_input = QTextEdit()
        self.special_requirement_input.setPlaceholderText("请输入额外的特别要求，这些内容不会纳入AI提示词生成和修改，只在生成图片时补充...")
        self.special_requirement_input.setMaximumHeight(100)
        self.special_requirement_input.setStyleSheet("""
            QTextEdit {
                padding: 8px;
                border: 1px solid #d9d9d9;
                border-radius: 4px;
                background-color: white;
                font-size: 12px;
            }
            QTextEdit:focus {
                border-color: #40a9ff;
            }
        """)
        self.special_requirement_group.add_widget(self.special_requirement_input)
        self.special_requirement_group.setVisible(False)  # 默认隐藏
        special_layout.addWidget(self.special_requirement_group)

        layout.addWidget(special_container)

        # ===== 7. 角色线稿生成（专用模式） =====
        line_art_container = QWidget()
        line_art_layout = QVBoxLayout(line_art_container)
        line_art_layout.setContentsMargins(0, 0, 0, 0)
        line_art_layout.setSpacing(0)

        # 角色线稿生成开关 - 使用与其他选项一致的命名格式
        self.line_art_mode_enabled = QCheckBox("启用角色线稿生成")
        self.line_art_mode_enabled.setObjectName("lineArtModeToggle")
        self.line_art_mode_enabled.setChecked(False)  # 默认不启用
        self.line_art_mode_enabled.setToolTip("启用后将使用专用线稿提示词，并禁用其他表单设置（除额外要求外）")
        self.line_art_mode_enabled.stateChanged.connect(self._on_line_art_mode_toggle_changed)
        line_art_layout.addWidget(self.line_art_mode_enabled)

        # 添加说明提示
        self.line_art_hint = QLabel("启用后，除特别要求外，其他提示词被禁用。")
        self.line_art_hint.setStyleSheet("color: #999999; font-size: 12px; margin-left: 24px; margin-bottom: 4px;")
        line_art_layout.addWidget(self.line_art_hint)

        # 线稿提示词分组
        self.line_art_group = FieldGroup("线稿提示词", color_class="special")
        
        # 提示词编辑框
        self.line_art_prompt_input = QTextEdit()
        self.line_art_prompt_input.setPlaceholderText("请输入角色线稿生成的提示词...")
        self.line_art_prompt_input.setMinimumHeight(120)
        self.line_art_prompt_input.setMaximumHeight(200)
        self.line_art_prompt_input.setStyleSheet("""
            QTextEdit {
                padding: 8px;
                border: 1px solid #d9d9d9;
                border-radius: 4px;
                background-color: white;
                font-size: 12px;
            }
            QTextEdit:focus {
                border-color: #40a9ff;
            }
        """)
        self.line_art_group.add_widget(self.line_art_prompt_input)
        
        # 保存按钮容器
        save_btn_container = QWidget()
        save_btn_layout = QHBoxLayout(save_btn_container)
        save_btn_layout.setContentsMargins(0, 8, 0, 0)
        save_btn_layout.addStretch()
        
        self.save_line_art_prompt_btn = QPushButton("保存提示词")
        self.save_line_art_prompt_btn.setObjectName("secondaryButton")
        self.save_line_art_prompt_btn.clicked.connect(self._save_line_art_prompt)
        save_btn_layout.addWidget(self.save_line_art_prompt_btn)
        
        self.line_art_group.add_widget(save_btn_container)
        self.line_art_group.setVisible(False)  # 默认隐藏
        line_art_layout.addWidget(self.line_art_group)

        layout.addWidget(line_art_container)

        # ===== 8. 反向提示词（可选） =====
        negative_container = QWidget()
        negative_layout = QVBoxLayout(negative_container)
        negative_layout.setContentsMargins(0, 0, 0, 0)
        negative_layout.setSpacing(0)

        # 启用开关
        self.negative_prompt_enabled = QCheckBox("启用反向提示词")
        self.negative_prompt_enabled.setObjectName("negativePromptToggle")
        self.negative_prompt_enabled.setChecked(True)
        self.negative_prompt_enabled.stateChanged.connect(self._on_negative_toggle_changed)
        negative_layout.addWidget(self.negative_prompt_enabled)

        # 反向提示词分组
        self.negative_group = FieldGroup("反向提示词", color_class="negative")
        negative_tags = self.yaml_handler.get_field_options("反向提示词标签")
        self.negative_prompt_input = TagTextInput(
            field_name="反向提示词标签",
            options=negative_tags,
            yaml_handler=self.yaml_handler,
        )
        self.negative_prompt_input.set_value(DEFAULT_NEGATIVE_PROMPT)
        self.negative_prompt_input.value_changed.connect(self._on_field_changed)
        self.negative_group.add_field("提示词", self.negative_prompt_input)
        self.negative_group.setVisible(True)
        negative_layout.addWidget(self.negative_group)

        layout.addWidget(negative_container)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    def _add_field(self, group: FieldGroup, label: str, field_name: str):
        """添加一个字段到分组"""
        options = self.yaml_handler.get_field_options(field_name)
        widget = ComboInput(
            field_name=field_name, options=options, yaml_handler=self.yaml_handler
        )
        widget.value_changed.connect(self._on_field_changed)
        group.add_field(label, widget)
        self.field_widgets[field_name] = widget

    def _add_category_preset_controls(
        self, group: FieldGroup, scope: str, label: str
    ):
        """在分类标题中加入预设选择和管理控件。"""
        selector = QComboBox()
        selector.setObjectName("categoryPresetSelector")
        selector.setMinimumWidth(140)
        selector.setMaximumWidth(190)
        selector.setToolTip(f"应用{label}预设，仅覆盖本分类")
        selector.activated.connect(
            lambda index, s=scope: self._load_category_preset(s, index)
        )
        self.category_preset_selectors[scope] = selector
        group.add_header_widget(selector)

        manage_btn = QPushButton("管理")
        manage_btn.setObjectName("secondaryButton")
        manage_btn.setToolTip(f"保存或删除{label}预设")
        manage_btn.clicked.connect(
            lambda checked=False, s=scope, l=label, b=manage_btn:
                self._show_category_preset_menu(s, l, b)
        )
        group.add_header_widget(manage_btn)
        self._refresh_category_preset_selector(scope)

    def _refresh_category_preset_selector(self, scope: str, selected_name: str = ""):
        selector = self.category_preset_selectors.get(scope)
        if selector is None:
            return
        selector.blockSignals(True)
        selector.clear()
        selector.addItem("分类预设...", None)
        for preset in self.preset_manager.get_category_presets(scope):
            selector.addItem(preset["name"], preset["name"])
        if selected_name:
            index = selector.findData(selected_name)
            if index >= 0:
                selector.setCurrentIndex(index)
        selector.blockSignals(False)

    def _collect_category_preset_data(self, scope: str) -> dict:
        return subset(self._collect_form_data(), scope, self.prompt_schema)

    def _load_category_preset(self, scope: str, index: int):
        selector = self.category_preset_selectors.get(scope)
        if selector is None or index <= 0:
            return
        name = selector.itemData(index)
        data = self.preset_manager.load_category_preset(scope, name)
        if not data:
            self._show_toast(f"加载分类预设失败: {name}")
            return
        self._fill_form_from_data(data)
        self._show_toast(f"已应用分类预设: {name}")

    def _save_category_preset(self, scope: str, label: str):
        selector = self.category_preset_selectors.get(scope)
        default_name = selector.currentData() if selector else ""
        name, ok = QInputDialog.getText(
            self, f"保存{label}预设", "请输入预设名称:", text=default_name or ""
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        data = self._collect_category_preset_data(scope)
        if self.preset_manager.save_category_preset(scope, name, data):
            safe_name = self.preset_manager._safe_name(name)
            self._refresh_category_preset_selector(scope, safe_name)
            self._show_toast(f"{label}预设已保存: {safe_name}")
        else:
            self._show_toast(f"保存{label}预设失败")

    def _show_category_preset_menu(
        self, scope: str, label: str, anchor: QWidget
    ):
        menu = QMenu(self)
        save_action = QAction("保存当前分类", self)
        save_action.triggered.connect(
            lambda checked=False: self._save_category_preset(scope, label)
        )
        menu.addAction(save_action)

        presets = self.preset_manager.get_category_presets(scope)
        delete_menu = menu.addMenu("删除分类预设")
        if presets:
            for preset in presets:
                action = QAction(preset["name"], self)
                action.triggered.connect(
                    lambda checked=False, n=preset["name"]:
                        self._delete_category_preset(scope, label, n)
                )
                delete_menu.addAction(action)
        else:
            empty_action = QAction("(暂无预设)", self)
            empty_action.setEnabled(False)
            delete_menu.addAction(empty_action)
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _delete_category_preset(self, scope: str, label: str, name: str):
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除{label}预设「{name}」吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self.preset_manager.delete_category_preset(scope, name):
            self._refresh_category_preset_selector(scope)
            self._show_toast(f"已删除分类预设: {name}")
        else:
            self._show_toast(f"删除分类预设失败: {name}")

    def _add_multi_select_field(self, group: FieldGroup, label: str, field_name: str):
        """添加一个多选字段到分组"""
        options = self.yaml_handler.get_field_options(field_name)
        widget = MultiSelectInput(
            field_name=field_name, options=options, yaml_handler=self.yaml_handler
        )
        widget.value_changed.connect(self._on_field_changed)
        group.add_field(label, widget)
        self.field_widgets[field_name] = widget

    def _create_json_preview_area(self) -> QWidget:
        """创建JSON预览区域（可折叠）"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 0, 0, 0)
        layout.setSpacing(12)

        # 预览标题
        title = QLabel("JSON 预览")
        title.setObjectName("previewTitle")
        layout.addWidget(title)

        # JSON文本框
        self.json_preview = QTextEdit()
        self.json_preview.setReadOnly(True)
        self.json_preview.setPlaceholderText("填写表单后，这里将实时显示生成的JSON提示词...")
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.json_preview.setFont(font)
        layout.addWidget(self.json_preview)

        return container

    def _toggle_json_preview(self):
        """切换JSON预览列的显示/隐藏"""
        self.json_preview_visible = not self.json_preview_visible
        self.json_preview_area.setVisible(self.json_preview_visible)
        
        # 更新按钮文字
        if self.json_preview_visible:
            self.json_toggle_btn.setText("JSON隐藏")
        else:
            self.json_toggle_btn.setText("JSON浏览")
        
        # 按当前分割器实际宽度按比例分配，而不是写死像素值
        total = max(self.main_splitter.width(), 1)
        if self.json_preview_visible:
            left = int(total * 0.38)
            middle = int(total * 0.24)
            self.main_splitter.setSizes([left, middle, total - left - middle])
        else:
            half = total // 2
            self.main_splitter.setSizes([half, 0, total - half])

    def _create_button_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(12)

        # 左侧按钮组
        # 清空按钮
        clear_btn = QPushButton("清空表单")
        clear_btn.setObjectName("secondaryButton")
        clear_btn.clicked.connect(self._clear_form)
        layout.addWidget(clear_btn)

        # 复制按钮（从右侧移过来，样式和清空表单一致）
        copy_btn = QPushButton("复制表单")
        copy_btn.setObjectName("secondaryButton")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        layout.addWidget(copy_btn)

        # JSON浏览/隐藏按钮
        self.json_toggle_btn = QPushButton("JSON浏览")
        self.json_toggle_btn.setObjectName("secondaryButton")
        self.json_toggle_btn.clicked.connect(self._toggle_json_preview)
        layout.addWidget(self.json_toggle_btn)

        layout.addStretch()

        # 右侧按钮组：生图相关按钮
        self.save_image_btn = QPushButton("保存图片")
        self.save_image_btn.setObjectName("secondaryButton")
        self.save_image_btn.setEnabled(False)
        self.save_image_btn.clicked.connect(self._save_image)
        layout.addWidget(self.save_image_btn)

        self.generate_image_btn = QPushButton("生成图片")
        self.generate_image_btn.setObjectName("primaryButton")
        self.generate_image_btn.clicked.connect(self._on_generate_image_clicked)
        layout.addWidget(self.generate_image_btn)
        self._update_image_config_status()

        return bar

    def _on_field_changed(self, value: str = None):
        """字段值改变时自动更新预览"""
        self._generate_json()

    def _on_negative_toggle_changed(self, state: int):
        """反向提示词开关切换"""
        enabled = state == 2  # Qt.CheckState.Checked = 2
        self.negative_group.setVisible(enabled)
        self._generate_json()

    def _on_special_requirement_toggle_changed(self, state: int):
        """特别要求开关切换"""
        enabled = state == 2  # Qt.CheckState.Checked = 2
        self.special_requirement_group.setVisible(enabled)
        # 特别要求不纳入JSON预览，所以不需要调用 _generate_json()

    def _on_line_art_mode_toggle_changed(self, state: int):
        """角色线稿模式开关切换"""
        enabled = state == 2  # Qt.CheckState.Checked = 2
        
        # 显示/隐藏线稿提示词分组
        self.line_art_group.setVisible(enabled)
        
        # 如果启用，加载当前的线稿提示词到编辑框
        if enabled:
            current_prompt = self.yaml_handler.get_line_art_prompt()
            self.line_art_prompt_input.setText(current_prompt)
        
        # 需要禁用/启用的控件列表（不包括特别要求）
        controls_to_toggle = [
            self.negative_prompt_enabled,
        ]
        
        # 表单字段控件
        for widget in self.field_widgets.values():
            widget.setEnabled(not enabled)
        
        # 其他开关控件
        for ctrl in controls_to_toggle:
            ctrl.setEnabled(not enabled)
        
        # 反向提示词分组
        self.negative_group.setEnabled(not enabled)
        
        # 如果启用线稿模式，收起其他已展开的可选分组（除特别要求外）
        if enabled:
            self.negative_prompt_enabled.setChecked(False)
        
        self._generate_json()

    def _save_line_art_prompt(self):
        """保存线稿提示词到配置文件"""
        prompt_text = self.line_art_prompt_input.toPlainText().strip()
        if not prompt_text:
            QMessageBox.warning(self, "提示", "提示词不能为空")
            return
            
        try:
            self.yaml_handler.save_line_art_prompt(prompt_text)
            self._show_toast("提示词保存成功")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败: {str(e)}")

    def _generate_json(self):
        """生成JSON提示词"""
        data = self._collect_form_data()
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        self.json_preview.setText(json_str)

    def _collect_form_data(self) -> dict:
        """收集表单数据并组织成目标格式"""
        flat = {}
        for field in self.prompt_schema.iter_fields():
            widget = self.field_widgets.get(field.widget_key)
            flat[field.id] = widget.get_value() if widget else ""
        data = nest(flat, self.prompt_schema)
        if self.negative_prompt_enabled.isChecked():
            data["反向提示词"] = self.negative_prompt_input.get_value()
        return order_document(data, self.prompt_schema)

    # ========== 预设相关方法 ==========

    def _load_presets_to_selector(self):
        """加载预设到选择器"""
        self.preset_selector.blockSignals(True)
        self.preset_selector.clear()
        self.preset_selector.addItem("")  # 空选项

        presets = self.preset_manager.get_all_presets()
        for preset in presets:
            self.preset_selector.addItem(preset['name'], preset['name'])

        self.preset_selector.blockSignals(False)
        self._show_toast(f"已加载 {len(presets)} 个预设")

    def _on_preset_selected(self, text: str):
        """选择预设时加载"""
        if not text or text == "":
            return

        # 获取实际的预设名称
        idx = self.preset_selector.currentIndex()
        preset_name = self.preset_selector.itemData(idx)

        if preset_name:
            self._load_preset(preset_name)

    def _load_preset(self, name: str):
        """加载预设到表单"""
        data = self.preset_manager.load_preset(name)
        if not data:
            self._show_toast(f"加载预设失败: {name}")
            return

        # 解析嵌套数据并填充表单
        self._fill_form_from_data(data)
        self.current_preset_name = name
        self._show_toast(f"已加载预设: {name}")

    def _fill_form_from_data(self, data: dict):
        """从数据填充表单"""
        _MISSING = object()
        flat = flatten(data, self.prompt_schema, include_missing=False)
        for field in self.prompt_schema.iter_fields():
            if field.id not in flat or field.widget_key not in self.field_widgets:
                continue
            value = flat[field.id]
            self.field_widgets[field.widget_key].set_value("" if value is None else value)

        aspect_data = data.get("画幅设置", _MISSING)
        if (
            aspect_data is not _MISSING
            and isinstance(aspect_data, dict)
            and hasattr(self, "aspect_enabled")
        ):
            has_aspect = bool(
                aspect_data.get("比例") or aspect_data.get("推荐分辨率") or aspect_data.get("用途")
            )
            self.aspect_enabled.setChecked(has_aspect)
            self.aspect_group.setVisible(has_aspect)
            if has_aspect:
                self.aspect_selector.set_values(
                    ratio=aspect_data.get("比例", ""),
                    resolution=aspect_data.get("推荐分辨率", ""),
                    usage=aspect_data.get("用途", ""),
                )

        # 处理反向提示词开关状态；仅当预设提供该块时覆盖
        negative_data = data.get("反向提示词", _MISSING)
        if negative_data is not _MISSING:
            negative_text = normalize_negative_prompt(negative_data)
            self.negative_prompt_input.set_value(negative_text)
            has_negative = bool(negative_text)
            self.negative_prompt_enabled.setChecked(has_negative)
            self.negative_group.setVisible(has_negative)

        self._generate_json()

    def _list_to_str(self, lst) -> str:
        """列表转字符串"""
        if isinstance(lst, list):
            return ", ".join(str(item) for item in lst if item)
        return str(lst) if lst else ""

    def _save_as_preset(self):
        """保存当前配置为预设"""
        default_name = self.current_preset_name or ""
        name, ok = QInputDialog.getText(
            self,
            "保存预设",
            "请输入预设名称:",
            text=default_name
        )

        if ok and name.strip():
            name = name.strip()
            data = self._collect_form_data()

            if self.preset_manager.save_preset(name, data):
                self.current_preset_name = name
                self._load_presets_to_selector()
                # 选中刚保存的预设
                for i in range(self.preset_selector.count()):
                    if self.preset_selector.itemData(i) == name:
                        self.preset_selector.setCurrentIndex(i)
                        break
                self._show_toast(f"预设已保存: {name}")
            else:
                self._show_toast("保存预设失败")

    def _show_preset_menu(self):
        """显示预设管理菜单"""
        menu = QMenu(self)
        # 使用与全局主题一致的样式
        menu.setStyleSheet("""
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #E0E0E0;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px 8px 12px;
                color: #2B2B2B;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #F7F7F7;
                color: #2B2B2B;
            }
            QMenu::separator {
                height: 1px;
                background-color: #EAEAEA;
                margin: 4px 8px;
            }
        """)

        # 保存为预设
        save_action = QAction("保存为预设", self)
        save_action.triggered.connect(self._save_as_preset)
        menu.addAction(save_action)

        menu.addSeparator()

        # 删除预设子菜单
        presets = self.preset_manager.get_all_presets()
        if presets:
            delete_menu = menu.addMenu("删除预设")
            delete_menu.setStyleSheet(menu.styleSheet())
            for preset in presets:
                action = QAction(preset['name'], self)
                action.triggered.connect(
                    lambda checked, n=preset['name']: self._delete_preset(n)
                )
                delete_menu.addAction(action)
        else:
            no_preset = QAction("(暂无预设)", self)
            no_preset.setEnabled(False)
            menu.addAction(no_preset)

        menu.exec(self.sender().mapToGlobal(self.sender().rect().bottomLeft()))

    def _delete_preset(self, name: str):
        """删除预设"""
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除预设「{name}」吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.preset_manager.delete_preset(name):
                self._load_presets_to_selector()
                if self.current_preset_name == name:
                    self.current_preset_name = None
                self._show_toast(f"已删除预设: {name}")
            else:
                self._show_toast("删除预设失败")

    # ========== AI 生成相关方法 ==========

    def _show_ai_generate_dialog(self):
        """显示AI生成对话框"""
        from nano_banana.desktop.dialogs.generate_dialog import AIGenerateDialog
        dialog = AIGenerateDialog(self)
        dialog.generated.connect(self._on_ai_generated)
        dialog.exec()

    def _show_ai_modify_dialog(self):
        """显示AI修改对话框"""
        from nano_banana.desktop.dialogs.modify_dialog import AIModifyDialog
        # 获取当前表单数据
        current_data = self._collect_form_data()
        dialog = AIModifyDialog(current_data, self)
        dialog.modified.connect(self._on_ai_modified)
        dialog.exec()

    def _open_ai_config_dialog(self):
        """打开统一的AI配置对话框"""
        from nano_banana.desktop.dialogs.config_dialog import UnifiedAIConfigDialog
        dialog = UnifiedAIConfigDialog(self, initial_tab="chat")
        dialog.config_saved.connect(self._refresh_image_config_from_dialog)
        dialog.exec()
    
    def resizeEvent(self, event):
        """窗口大小改变事件"""
        super().resizeEvent(event)
        if hasattr(self, 'preview_area') and self.generated_pixmap:
            self._refresh_preview_pixmap()

    def _on_ai_generated(self, data: dict):
        """AI生成完成后应用到表单"""
        self._fill_form_from_data(data)
        self.current_preset_name = None
        self._show_toast("已应用AI生成的提示词")

    def _on_ai_modified(self, data: dict):
        """AI修改完成后应用到表单"""
        self._fill_form_from_data(data)
        self.current_preset_name = None
        self._show_toast("已应用AI修改的提示词")

    # ========== 其他方法 ==========

    def _copy_to_clipboard(self):
        """复制JSON到剪贴板"""
        json_text = self.json_preview.toPlainText()
        if not json_text:
            self._generate_json()
            json_text = self.json_preview.toPlainText()

        if CLIPBOARD_AVAILABLE:
            try:
                pyperclip.copy(json_text)
                self._show_toast("已复制到剪贴板")
            except Exception:
                from PyQt6.QtWidgets import QApplication
                QApplication.clipboard().setText(json_text)
                self._show_toast("已复制到剪贴板")
        else:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(json_text)
            self._show_toast("已复制到剪贴板")

    def _clear_form(self):
        """清空表单"""
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空所有表单内容吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            for widget in self.field_widgets.values():
                widget.clear()
            if hasattr(self, "aspect_selector"):
                self.aspect_selector.clear()
            self.json_preview.clear()
            self.current_preset_name = None
            self.preset_selector.setCurrentIndex(0)
            if hasattr(self, "aspect_enabled"):
                self.aspect_enabled.setChecked(False)
                self.aspect_group.setVisible(False)
            # 恢复默认反向提示词
            self.negative_prompt_enabled.setChecked(True)
            self.negative_group.setVisible(True)
            self.negative_prompt_input.set_value(DEFAULT_NEGATIVE_PROMPT)
            # 重置特别要求开关
            self.special_requirement_enabled.setChecked(False)
            self.special_requirement_group.setVisible(False)
            self.special_requirement_input.clear()
            # 清空生图相关
            if hasattr(self, 'selected_images'):
                self._clear_images()
            self.generated_image_bytes = None
            self.generated_pixmap = None
            if hasattr(self, 'preview_area'):
                self.preview_area.setText("图片生成后会显示在这里")
                self.preview_area.clearSourcePixmap()
            if hasattr(self, 'save_image_btn'):
                self.save_image_btn.setEnabled(False)
            if hasattr(self, 'image_status_label'):
                self._set_image_status("准备就绪")
            # 禁用预览功能
            self._enable_image_preview(False)
            self._show_toast("表单已清空")

    def _show_toast(self, message: str):
        """显示简短提示"""
        self.statusBar().showMessage(message, 3000)
