"""窗口尺寸自适应工具。"""
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget


def fit_window_to_screen(
    window: QWidget,
    preferred_width: int,
    preferred_height: int,
    min_width: int = 0,
    min_height: int = 0,
    margin: float = 0.94,
) -> None:
    """按当前屏幕可用区域钳制窗口的最小尺寸与初始尺寸。

    固定的 setMinimumSize/resize 在小分辨率或高DPI缩放
    （如 1366x768、1920x1080@150% 时逻辑分辨率仅 1280x720）下
    会超出屏幕，导致窗口底部按钮不可见。
    """
    screen = window.screen() or QGuiApplication.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        max_width = int(available.width() * margin)
        max_height = int(available.height() * margin)
    else:
        max_width, max_height = preferred_width, preferred_height

    if min_width or min_height:
        window.setMinimumSize(min(min_width, max_width), min(min_height, max_height))
    window.resize(min(preferred_width, max_width), min(preferred_height, max_height))
