from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QPointF, QRectF, QSize, Qt, QStandardPaths, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QImageReader, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from PIL import Image, UnidentifiedImageError

from region_editor import RegionEditorDialog
from remove_signature_background import (
    NamedRegion,
    RemovalOptions,
    process_image_file,
    process_image_regions,
    sanitize_output_stem,
)

APP_NAME = "Nukki"
WINDOW_TITLE = "Nukki"
SUPPORTED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".jpe",
    ".jfif",
    ".webp",
    ".bmp",
    ".dib",
    ".gif",
    ".tif",
    ".tiff",
    ".ico",
    ".ppm",
    ".pgm",
    ".pbm",
    ".pnm",
    ".tga",
    ".avif",
}
IMAGE_FILE_DIALOG_FILTER = (
    "Image files (*.png *.jpg *.jpeg *.jpe *.jfif *.webp *.bmp *.dib *.gif "
    "*.tif *.tiff *.ico *.ppm *.pgm *.pbm *.pnm *.tga *.avif);;All files (*)"
)
OUTPUT_HISTORY_LIMIT = 6
DEFAULT_CROP_ENABLED = False
DEFAULT_OPEN_FOLDER_ENABLED = True
PROCESS_MODE_BACKGROUND = "background"
PROCESS_MODE_SCAN = "scan"
BACKGROUND_OUTPUT_SUFFIX = "_transparent"
SCAN_OUTPUT_SUFFIX = "_scan"

APP_SUBTITLE = "\uc774\ubbf8\uc9c0 \ubc30\uacbd \uc81c\uac70 \ud504\ub85c\uadf8\ub7a8"
UPLOAD_TITLE = "\uc774\ubbf8\uc9c0 \ucd94\uac00"
UPLOAD_BUTTON = "+    \ud30c\uc77c \ucd94\uac00 \ub610\ub294 \ub4dc\ub798\uadf8\nJPG, PNG, WEBP \ub4f1 \uc774\ubbf8\uc9c0 \ud30c\uc77c\uc744 \ucd94\uac00\ud558\uc138\uc694."
REMOVE_SELECTED = "\uc120\ud0dd \uc0ad\uc81c"
CLEAR_ALL = "\uc804\uccb4 \uc0ad\uc81c"
OUTPUT_TITLE = "\uc800\uc7a5 \uc124\uc815"
OUTPUT_BROWSE = "\ud3f4\ub354 \uc120\ud0dd"
CURRENT_OUTPUT = "\ud604\uc7ac \uc800\uc7a5 \uacbd\ub85c: {path}"
SAVE_NAME_LABEL = "\uc800\uc7a5 \uc774\ub984"
SAVE_NAME_BUTTON = "\uc124\uc815"
SAVE_NAME_PLACEHOLDER = "\uc608: \ub85c\uace0"
CROP_TEXT = "\uc5ec\ubc31 \uc790\ub3d9 \uc790\ub974\uae30"
OPEN_FOLDER_TEXT = "\uc644\ub8cc \ud6c4 \ucd9c\ub825 \ud3f4\ub354 \uc5f4\uae30"
ACTION_TITLE = "\uc804\uccb4 \uc9c4\ud589\ub960"
STATUS_IDLE = "\ub300\uae30 \uc911"
STATUS_RUNNING = "\ucc98\ub9ac \uc911"
STATUS_DONE = "\uc644\ub8cc"
STATUS_ERROR = "\uc624\ub958"
START_BUTTON = "\uc2dc\uc791\ud558\uae30"
QUEUE_TITLE = "\uc774\ubbf8\uc9c0 \ubaa9\ub85d"
QUEUE_HINT = "\uc5ec\ub7ec \uc774\ubbf8\uc9c0\ub97c \ucd94\uac00\ud558\uac70\ub098 \uc774 \uc601\uc5ed\uc73c\ub85c \ub4dc\ub798\uadf8\ud574 \ub123\uc744 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
LOG_TITLE = "\ub85c\uadf8"
CLEAR_LOG = "\ub85c\uadf8 \uc9c0\uc6b0\uae30"
PNG_LABEL = "PNG (\ud22c\uba85)"
JPEG_LABEL = "JPEG"
OUTPUT_FORMAT_LABEL = "\ucd9c\ub825 \ud615\uc2dd"
OUTPUT_PATH_LABEL = "\uc800\uc7a5 \uacbd\ub85c"
READY_TEXT = "\uc900\ube44 \uc644\ub8cc"
NO_FILES_MESSAGE = "\ucc98\ub9ac\ud560 \uc774\ubbf8\uc9c0\ub97c \ud558\ub098 \uc774\uc0c1 \ucd94\uac00\ud574 \uc8fc\uc138\uc694."
NO_OUTPUT_DIR_MESSAGE = "\ucd9c\ub825 \ud3f4\ub354\ub97c \uba3c\uc800 \uc120\ud0dd\ud574 \uc8fc\uc138\uc694."
COMPLETE_TITLE = "\uc791\uc5c5 \uc644\ub8cc"
COMPLETE_MESSAGE = "\uc791\uc5c5\uc774 \uc644\ub8cc\ub418\uc5c8\uc2b5\ub2c8\ub2e4.\n\uc131\uacf5: {success}\n\uc2e4\ud328: {failed}"
ERROR_TITLE = "\uc624\ub958"
UNEXPECTED_ERROR_MESSAGE = "\ucc98\ub9ac \uc911 \uc608\uc0c1\uce58 \ubabb\ud55c \uc624\ub958\uac00 \ubc1c\uc0dd\ud588\uc2b5\ub2c8\ub2e4. \ub85c\uadf8\ub97c \ud655\uc778\ud574 \uc8fc\uc138\uc694."
PICK_IMAGES_TITLE = "\uc774\ubbf8\uc9c0 \uc120\ud0dd"
PICK_OUTPUT_TITLE = "\ucd9c\ub825 \ud3f4\ub354 \uc120\ud0dd"
QUEUE_STATUS_QUEUED = "\ub300\uae30 \uc911"
QUEUE_STATUS_PROCESSING = "\ucc98\ub9ac \uc911"
QUEUE_STATUS_DONE = "\uc644\ub8cc"
QUEUE_STATUS_FAILED = "\uc2e4\ud328"
REGION_EDIT_TOOLTIP = "\uc601\uc5ed \ud3b8\uc9d1"


def app_data_dir() -> Path:
    directory = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not directory:
        directory = str(Path.home() / ".nukki")
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    return target


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def default_output_dir() -> Path:
    documents_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    if documents_dir:
        return Path(documents_dir) / "Nukki Output"
    return Path.cwd() / "output"


def load_settings() -> dict:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(payload: dict) -> None:
    settings_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def is_supported_image(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False

    if QImageReader.imageFormat(str(path)):
        return True

    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except (UnidentifiedImageError, OSError, ValueError):
        return False


def open_folder_in_explorer(path: Path) -> None:
    try:
        os.startfile(str(path))
    except AttributeError:
        pass


def normalize_history(history: list[str], preferred: str = "") -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in ([preferred] if preferred else []) + history:
        text = raw.strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= OUTPUT_HISTORY_LIMIT:
            break
    return result


def preferred_input_dir(last_input_dir: str, current_output_dir: str) -> str:
    if last_input_dir and Path(last_input_dir).exists():
        return last_input_dir
    if current_output_dir and Path(current_output_dir).exists():
        return current_output_dir
    return str(Path.home())


def rounded_pixmap(source: QPixmap, width: int, height: int, radius: int) -> QPixmap:
    canvas = QPixmap(width, height)
    canvas.fill(Qt.GlobalColor.transparent)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
    painter.setClipPath(clip)

    scaled = source.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    x = (scaled.width() - width) / 2
    y = (scaled.height() - height) / 2
    painter.drawPixmap(QRectF(0, 0, width, height), scaled, QRectF(x, y, width, height))
    painter.end()
    return canvas


def create_logo_pixmap(size: int = 52) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#ff5a00"))
    painter.drawEllipse(QRectF(2, 2, size - 4, size - 4))

    painter.save()
    clip = QPainterPath()
    clip.addEllipse(QRectF(2, 2, size - 4, size - 4))
    painter.setClipPath(clip)
    painter.translate(size / 2, size / 2)
    painter.rotate(-26)
    painter.setPen(QPen(QColor("#ffffff"), max(5, size // 9), Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
    for offset in (-size * 0.28, -size * 0.09, size * 0.1, size * 0.29):
        painter.drawLine(QPointF(-size * 0.55, offset), QPointF(size * 0.55, offset))
    painter.restore()
    painter.end()
    return pixmap


def create_background_pixmap(size: int = 54, color: str = "#ff5a00") -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor(color), 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)

    step = size / 5
    for row in range(3):
        for column in range(3):
            x = 6 + column * step
            y = 6 + row * step
            painter.drawRoundedRect(QRectF(x, y, step - 4, step - 4), 4, 4)

    painter.setPen(QPen(QColor(color), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(size * 0.28, size * 0.72), QPointF(size * 0.72, size * 0.28))
    painter.drawLine(QPointF(size * 0.55, size * 0.28), QPointF(size * 0.72, size * 0.28))
    painter.drawLine(QPointF(size * 0.72, size * 0.28), QPointF(size * 0.72, size * 0.45))
    painter.end()
    return pixmap


def create_scan_pixmap(size: int = 54, color: str = "#ff5a00") -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor(color), 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)

    page = QRectF(size * 0.23, size * 0.13, size * 0.46, size * 0.64)
    painter.drawRoundedRect(page, 3, 3)
    painter.drawLine(QPointF(size * 0.58, size * 0.13), QPointF(size * 0.69, size * 0.24))
    painter.drawLine(QPointF(size * 0.31, size * 0.38), QPointF(size * 0.57, size * 0.38))
    painter.drawLine(QPointF(size * 0.31, size * 0.5), QPointF(size * 0.52, size * 0.5))
    painter.drawLine(QPointF(size * 0.31, size * 0.62), QPointF(size * 0.47, size * 0.62))
    painter.drawEllipse(QRectF(size * 0.54, size * 0.67, size * 0.23, size * 0.13))
    painter.end()
    return pixmap


def create_control_pixmap(kind: str, size: int = 28, color: str = "#4d5159") -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if kind == "settings":
        center = QPointF(size / 2, size / 2)
        painter.drawEllipse(center, size * 0.12, size * 0.12)
        for index in range(8):
            painter.save()
            painter.translate(center)
            painter.rotate(index * 45)
            painter.drawLine(QPointF(size * 0.25, 0), QPointF(size * 0.37, 0))
            painter.restore()
        painter.drawEllipse(center, size * 0.28, size * 0.28)
    elif kind == "minimize":
        painter.drawLine(QPointF(size * 0.25, size * 0.55), QPointF(size * 0.75, size * 0.55))
    elif kind == "close":
        painter.drawLine(QPointF(size * 0.28, size * 0.28), QPointF(size * 0.72, size * 0.72))
        painter.drawLine(QPointF(size * 0.72, size * 0.28), QPointF(size * 0.28, size * 0.72))
    elif kind == "trash":
        painter.drawLine(QPointF(size * 0.32, size * 0.32), QPointF(size * 0.68, size * 0.32))
        painter.drawRoundedRect(QRectF(size * 0.34, size * 0.38, size * 0.32, size * 0.4), 3, 3)
        painter.drawLine(QPointF(size * 0.42, size * 0.46), QPointF(size * 0.42, size * 0.69))
        painter.drawLine(QPointF(size * 0.58, size * 0.46), QPointF(size * 0.58, size * 0.69))
        painter.drawLine(QPointF(size * 0.42, size * 0.25), QPointF(size * 0.58, size * 0.25))
    elif kind == "play":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPolygon(
            [
                QPointF(size * 0.34, size * 0.22),
                QPointF(size * 0.34, size * 0.78),
                QPointF(size * 0.78, size * 0.5),
            ]
        )

    painter.end()
    return pixmap


def create_pencil_pixmap(size: int = 26) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#6654f1"))
    painter.translate(size / 2, size / 2)
    painter.rotate(-28)
    painter.drawRoundedRect(QRectF(-7, -2.5, 14, 5), 2.5, 2.5)
    painter.setBrush(QColor("#f6cf72"))
    painter.drawPolygon(
        [
            QPointF(7, -2.5),
            QPointF(11, 0),
            QPointF(7, 2.5),
        ]
    )
    painter.setBrush(QColor("#ffffff"))
    painter.drawPolygon(
        [
            QPointF(11, 0),
            QPointF(13, -1.2),
            QPointF(13, 1.2),
        ]
    )
    painter.resetTransform()
    painter.end()
    return pixmap


def make_thumbnail(path: Path, size: int = 54) -> QPixmap:
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        fallback = QPixmap(size, size)
        fallback.fill(QColor("#eef1f6"))
        return rounded_pixmap(fallback, size, size, 16)
    return rounded_pixmap(pixmap, size, size, 16)


def supported_paths_from_urls(urls) -> list[str]:
    paths: list[str] = []
    seen: set[Path] = set()
    for url in urls:
        local = url.toLocalFile()
        if not local:
            continue
        candidate = Path(local)
        candidates: list[Path]
        if candidate.is_dir():
            candidates = [path for path in candidate.rglob("*") if path.is_file()]
        else:
            candidates = [candidate]

        for image_path in candidates:
            try:
                resolved = image_path.resolve()
            except OSError:
                continue
            if resolved in seen or not is_supported_image(resolved):
                continue
            seen.add(resolved)
            paths.append(str(resolved))
    return paths


def has_local_drop_urls(event) -> bool:
    if not event.mimeData().hasUrls():
        return False
    return any(bool(url.toLocalFile()) for url in event.mimeData().urls())


def set_drag_active_style(widget: QWidget | None, active: bool) -> None:
    if widget is None:
        return
    value = "true" if active else "false"
    if widget.property("dragActive") == value:
        return
    widget.setProperty("dragActive", value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class QueueListWidget(QListWidget):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSpacing(10)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if has_local_drop_urls(event):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if has_local_drop_urls(event):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        paths = supported_paths_from_urls(event.mimeData().urls())
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        event.ignore()


class DropAreaButton(QPushButton):
    files_dropped = Signal(list)

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setAcceptDrops(True)
        set_drag_active_style(self, False)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if has_local_drop_urls(event):
            set_drag_active_style(self, True)
            event.acceptProposedAction()
            return
        set_drag_active_style(self, False)
        event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if has_local_drop_urls(event):
            set_drag_active_style(self, True)
            event.acceptProposedAction()
            return
        set_drag_active_style(self, False)
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        set_drag_active_style(self, False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        set_drag_active_style(self, False)
        paths = supported_paths_from_urls(event.mimeData().urls())
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        event.ignore()


class ImageDropFrame(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.drag_highlight_target: QWidget | None = None

    def set_drag_highlight_target(self, widget: QWidget | None) -> None:
        self.drag_highlight_target = widget

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if has_local_drop_urls(event):
            set_drag_active_style(self.drag_highlight_target, True)
            event.acceptProposedAction()
            return
        set_drag_active_style(self.drag_highlight_target, False)
        event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if has_local_drop_urls(event):
            set_drag_active_style(self.drag_highlight_target, True)
            event.acceptProposedAction()
            return
        set_drag_active_style(self.drag_highlight_target, False)
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        set_drag_active_style(self.drag_highlight_target, False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        set_drag_active_style(self.drag_highlight_target, False)
        paths = supported_paths_from_urls(event.mimeData().urls())
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        event.ignore()


class QueueItemWidget(QFrame):
    edit_requested = Signal()
    remove_requested = Signal()

    def __init__(self, source_path: Path) -> None:
        super().__init__()
        self.source_path = source_path
        self.output_stem = ""
        self.setObjectName("queueItem")
        self._highlighted = False
        self.region_names: list[str] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(16)

        self.check_box = QCheckBox()
        self.check_box.setObjectName("rowCheck")
        self.check_box.setFixedWidth(0)
        self.check_box.hide()
        self.check_box.toggled.connect(self._refresh_visual_state)
        self.check_box.setCursor(Qt.CursorShape.PointingHandCursor)

        self.thumbnail = QLabel()
        self.thumbnail.setObjectName("thumbLabel")
        self.thumbnail.setPixmap(make_thumbnail(source_path, 68))
        self.thumbnail.setFixedSize(68, 68)
        self.thumbnail.setScaledContents(False)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(6)

        top_line = QHBoxLayout()
        top_line.setContentsMargins(0, 0, 0, 0)
        top_line.setSpacing(10)

        self.name_label = QLabel(source_path.name)
        self.name_label.setObjectName("nameLabel")

        self.badge_label = QLabel(source_path.suffix.replace(".", "").upper() or "IMG")
        self.badge_label.setObjectName("badgeLabel")

        self.edit_button = QToolButton()
        self.edit_button.setObjectName("editButton")
        self.edit_button.setIcon(QIcon(create_pencil_pixmap(24)))
        self.edit_button.setIconSize(QSize(20, 20))
        self.edit_button.setToolTip(REGION_EDIT_TOOLTIP)
        self.edit_button.clicked.connect(self.edit_requested.emit)

        top_line.addWidget(self.name_label)
        top_line.addWidget(self.badge_label, 0, Qt.AlignmentFlag.AlignVCenter)
        top_line.addWidget(self.edit_button, 0, Qt.AlignmentFlag.AlignVCenter)
        top_line.addStretch(1)

        self.detail_label = QLabel(QUEUE_STATUS_QUEUED)
        self.detail_label.setObjectName("metaLabel")

        text_column.addLayout(top_line)
        text_column.addWidget(self.detail_label)

        self.progress = QProgressBar()
        self.progress.setObjectName("itemProgress")
        self.progress.setTextVisible(False)
        self.progress.setFixedSize(320, 10)
        self.progress.setRange(0, 100)
        self.progress.setValue(24)
        self.progress.setProperty("barState", "queued")
        text_column.addWidget(self.progress, 0, Qt.AlignmentFlag.AlignLeft)

        self.delete_button = QToolButton()
        self.delete_button.setObjectName("deleteButton")
        self.delete_button.setIcon(QIcon(create_control_pixmap("trash", 30)))
        self.delete_button.setIconSize(QSize(26, 26))
        self.delete_button.clicked.connect(self.remove_requested.emit)
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)

        layout.addWidget(self.thumbnail)
        layout.addLayout(text_column, 1)
        layout.addWidget(self.delete_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        for clickable in (self, self.thumbnail, self.name_label, self.badge_label, self.detail_label, self.progress):
            if clickable is not self:
                clickable.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._refresh_visual_state()

    def set_state(self, state: str, detail: str = "") -> None:
        if state == QUEUE_STATUS_PROCESSING:
            self.detail_label.setText("\ucc98\ub9ac \uc911...")
            self.progress.setRange(0, 0)
            self.progress.setProperty("barState", "processing")
        elif state == QUEUE_STATUS_DONE:
            self.detail_label.setText(detail or "\uc800\uc7a5 \uc644\ub8cc")
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.progress.setProperty("barState", "done")
        elif state == QUEUE_STATUS_FAILED:
            self.detail_label.setText(detail or "\uc2e4\ud328")
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.progress.setProperty("barState", "failed")
        else:
            self.detail_label.setText(self._queued_detail_text())
            self.progress.setRange(0, 100)
            self.progress.setValue(24)
            self.progress.setProperty("barState", "queued")

        self.progress.style().unpolish(self.progress)
        self.progress.style().polish(self.progress)
        self.progress.update()

    def is_checked(self) -> bool:
        return self.check_box.isChecked()

    def set_regions(self, regions: list[NamedRegion]) -> None:
        self.region_names = [region.name for region in regions]
        self.detail_label.setText(self._queued_detail_text())

    def set_output_name(self, output_stem: str, extension: str) -> None:
        self.output_stem = output_stem
        if output_stem:
            self.name_label.setText(f"{output_stem}{extension}")
            self.name_label.setToolTip(f"\uc6d0\ubcf8: {self.source_path.name}")
        else:
            self.name_label.setText(self.source_path.name)
            self.name_label.setToolTip("")

    def region_count(self) -> int:
        return len(self.region_names)

    def set_highlighted(self, highlighted: bool) -> None:
        self._highlighted = highlighted
        self._refresh_visual_state()

    def _refresh_visual_state(self) -> None:
        active = self._highlighted or self.check_box.isChecked()
        self.setProperty("activeRow", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.check_box.toggle()
            event.accept()
            return
        super().mousePressEvent(event)

    def _queued_detail_text(self) -> str:
        if not self.region_names:
            return QUEUE_STATUS_QUEUED
        return f"{len(self.region_names)}\uac1c \uc601\uc5ed: {', '.join(self.region_names[:3])}" + ("..." if len(self.region_names) > 3 else "")


class BatchWorker(QObject):
    progress_changed = Signal(int, int)
    item_updated = Signal(int, str, str)
    log_message = Signal(str)
    completed = Signal(str, int, int)
    failed = Signal(str)

    def __init__(
        self,
        input_files: list[str],
        output_dir: str,
        options: RemovalOptions,
        region_map: dict[str, list[NamedRegion]] | None = None,
        output_name_map: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.input_files = input_files
        self.output_dir = output_dir
        self.options = options
        self.region_map = region_map or {}
        self.output_name_map = output_name_map or {}

    @Slot()
    def run(self) -> None:
        success_count = 0
        failure_count = 0
        total = len(self.input_files)

        try:
            mode_label = "\uc2a4\uce94 \uc774\ubbf8\uc9c0 \ub9cc\ub4e4\uae30" if self.options.method == "scan" else "\ubc30\uacbd\uc81c\uac70"
            self.log_message.emit(f"{mode_label}: {total} \ud30c\uc77c\uc774 \ub300\uae30 \uc911\uc785\ub2c8\ub2e4.")
            for index, file_path in enumerate(self.input_files):
                source = Path(file_path)
                self.item_updated.emit(index, QUEUE_STATUS_PROCESSING, "")
                self.log_message.emit(f"[{index + 1}/{total}] \ucc98\ub9ac \uc911: {source.name}")

                try:
                    regions = self.region_map.get(str(source), [])
                    output_stem = self.output_name_map.get(str(source), "")
                    job_options = replace(self.options, output_suffix="") if output_stem else self.options
                    if regions:
                        output_paths, methods = process_image_regions(
                            input_path=source,
                            regions=regions,
                            output_dir=self.output_dir,
                            options=job_options,
                            output_stem=output_stem or None,
                        )
                        detail = f"{len(output_paths)}\uac1c \ucd9c\ub825"
                        self.item_updated.emit(index, QUEUE_STATUS_DONE, detail)
                        self.log_message.emit(
                            f"[{index + 1}/{total}] \uc644\ub8cc: {source.name} -> {len(output_paths)}\uac1c \uc601\uc5ed \ucd9c\ub825"
                        )
                        if methods:
                            self.log_message.emit(f"    \ucc98\ub9ac \ubc29\uc2dd: {', '.join(sorted(set(methods)))}")
                    else:
                        output_path, method = process_image_file(
                            input_path=source,
                            output_dir=self.output_dir,
                            options=job_options,
                            output_stem=output_stem or None,
                        )
                        self.item_updated.emit(index, QUEUE_STATUS_DONE, output_path.name)
                        self.log_message.emit(
                            f"[{index + 1}/{total}] \uc644\ub8cc: {source.name} -> {output_path.name} ({method})"
                        )
                    success_count += 1
                except Exception as exc:
                    self.item_updated.emit(index, QUEUE_STATUS_FAILED, str(exc))
                    self.log_message.emit(f"[{index + 1}/{total}] \uc2e4\ud328: {source.name} -> {exc}")
                    failure_count += 1

                self.progress_changed.emit(index + 1, total)

            self.completed.emit(self.output_dir, success_count, failure_count)
        except Exception:
            self.failed.emit(traceback.format_exc())


class NukkiWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.worker_thread: QThread | None = None
        self.worker: BatchWorker | None = None
        self.settings = load_settings()
        self.last_input_dir = str(self.settings.get("last_input_dir", ""))
        self.output_history: list[str] = normalize_history(list(self.settings.get("output_history", [])))
        self.queued_files: list[str] = []
        self.queue_widgets: list[QueueItemWidget] = []
        self.region_configs: dict[str, list[NamedRegion]] = {}
        self.output_name_map: dict[str, str] = {}
        saved_mode = str(self.settings.get("mode", PROCESS_MODE_BACKGROUND)).strip().lower()
        self.selected_mode = PROCESS_MODE_SCAN if saved_mode == PROCESS_MODE_SCAN else PROCESS_MODE_BACKGROUND
        self._drag_start_position: QPoint | None = None

        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        self.setMinimumSize(1360, 780)
        self.resize(1480, 835)
        self.setWindowIcon(QIcon(create_logo_pixmap(64)))

        self._build_ui()
        self._load_settings_into_ui()
        self._apply_styles()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 136:
            self._drag_start_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_start_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_start_position)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_start_position = None
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if has_local_drop_urls(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if has_local_drop_urls(event):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        paths = supported_paths_from_urls(event.mimeData().urls())
        if paths:
            self.add_files(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("rootWidget")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(0)

        outer = QFrame()
        outer.setObjectName("outerFrame")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        outer_layout.addWidget(self._build_header())

        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)
        body_row.addWidget(self._build_sidebar())
        body_row.addWidget(self._build_content(), 1)
        outer_layout.addLayout(body_row)

        root_layout.addWidget(outer)
        self.setCentralWidget(root)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("headerFrame")
        header.setFixedHeight(118)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(34, 18, 34, 18)
        layout.setSpacing(18)

        logo = QLabel()
        logo.setPixmap(create_logo_pixmap(62))
        logo.setFixedSize(62, 62)

        brand_column = QVBoxLayout()
        brand_column.setContentsMargins(0, 0, 0, 0)
        brand_column.setSpacing(2)

        brand = QLabel(APP_NAME)
        brand.setObjectName("brandLabel")
        subtitle = QLabel(APP_SUBTITLE)
        subtitle.setObjectName("subtitleLabel")
        brand_column.addWidget(brand)
        brand_column.addWidget(subtitle)

        self.settings_button = QToolButton()
        self.settings_button.setObjectName("windowButton")
        self.settings_button.setIcon(QIcon(create_control_pixmap("settings", 34)))
        self.settings_button.setIconSize(QSize(30, 30))
        self.settings_button.setToolTip("\uc124\uc815")

        minimize_button = QToolButton()
        minimize_button.setObjectName("windowButton")
        minimize_button.setIcon(QIcon(create_control_pixmap("minimize", 34)))
        minimize_button.setIconSize(QSize(30, 30))
        minimize_button.clicked.connect(self.showMinimized)

        close_button = QToolButton()
        close_button.setObjectName("windowButton")
        close_button.setIcon(QIcon(create_control_pixmap("close", 34)))
        close_button.setIconSize(QSize(30, 30))
        close_button.clicked.connect(self.close)

        layout.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(brand_column)
        layout.addStretch(1)
        layout.addWidget(self.settings_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addSpacing(16)
        layout.addWidget(minimize_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignVCenter)
        return header

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebarFrame")
        sidebar.setFixedWidth(150)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(14)

        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)

        self.background_button = QToolButton()
        self.background_button.setObjectName("navButton")
        self.background_button.setText("\ubc30\uacbd\uc81c\uac70")
        self.background_button.setIcon(QIcon(create_background_pixmap(52)))
        self.background_button.setIconSize(QSize(48, 48))
        self.background_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.background_button.setCheckable(True)
        self.background_button.clicked.connect(lambda: self._set_mode(PROCESS_MODE_BACKGROUND))

        self.scan_button = QToolButton()
        self.scan_button.setObjectName("navButton")
        self.scan_button.setText("\uc2a4\uce94 \uc774\ubbf8\uc9c0\n\ub9cc\ub4e4\uae30")
        self.scan_button.setIcon(QIcon(create_scan_pixmap(52)))
        self.scan_button.setIconSize(QSize(48, 48))
        self.scan_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.scan_button.setCheckable(True)
        self.scan_button.clicked.connect(lambda: self._set_mode(PROCESS_MODE_SCAN))

        self.mode_group.addButton(self.background_button)
        self.mode_group.addButton(self.scan_button)

        layout.addWidget(self.background_button, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.scan_button, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return sidebar

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("contentFrame")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(20)

        grid = QHBoxLayout()
        grid.setSpacing(18)

        left_column = QVBoxLayout()
        left_column.setSpacing(14)
        left_column.addWidget(self._build_upload_card())
        left_column.addWidget(self._build_queue_card(), 1)

        right_column = QVBoxLayout()
        right_column.setSpacing(14)
        right_column.addWidget(self._build_output_card())
        right_column.addWidget(self._build_log_card(), 1)

        grid.addLayout(left_column, 2)
        grid.addLayout(right_column, 1)
        layout.addLayout(grid, 1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(16)
        bottom_row.addWidget(self._build_progress_card(), 1)

        self.start_button = QPushButton(START_BUTTON)
        self.start_button.setObjectName("startButton")
        self.start_button.setIcon(QIcon(create_control_pixmap("play", 42, "#ffffff")))
        self.start_button.setIconSize(QSize(38, 38))
        self.start_button.clicked.connect(self.start_processing)
        bottom_row.addWidget(self.start_button)

        layout.addLayout(bottom_row)
        return content

    def _build_upload_card(self) -> QFrame:
        card = ImageDropFrame()
        card.setObjectName("card")
        card.files_dropped.connect(self.add_files)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(14)

        title = QLabel(UPLOAD_TITLE)
        title.setObjectName("cardTitle")

        self.add_button = DropAreaButton(UPLOAD_BUTTON)
        self.add_button.setObjectName("uploadButton")
        self.add_button.clicked.connect(self.select_files)
        self.add_button.files_dropped.connect(self.add_files)
        card.set_drag_highlight_target(self.add_button)

        self.remove_button = QPushButton(REMOVE_SELECTED)
        self.remove_button.setObjectName("subButton")
        self.remove_button.clicked.connect(self.remove_selected_rows)
        self.remove_button.hide()

        self.clear_button = QPushButton(CLEAR_ALL)
        self.clear_button.setObjectName("subButton")
        self.clear_button.clicked.connect(self.clear_files)

        layout.addWidget(title)
        layout.addWidget(self.add_button)
        return card

    def _build_output_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)

        title = QLabel(OUTPUT_TITLE)
        title.setObjectName("cardTitle")

        path_label = QLabel(OUTPUT_PATH_LABEL)
        path_label.setObjectName("fieldLabel")

        path_row = QHBoxLayout()
        path_row.setSpacing(10)

        self.output_dir_combo = QComboBox()
        self.output_dir_combo.setObjectName("pathCombo")
        self.output_dir_combo.setEditable(True)
        self.output_dir_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.output_dir_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.output_dir_combo.lineEdit().setPlaceholderText("\ucd9c\ub825 \ud3f4\ub354\ub97c \uc120\ud0dd\ud558\uc138\uc694.")
        self.output_dir_combo.lineEdit().editingFinished.connect(self.on_output_dir_changed)
        self.output_dir_combo.activated.connect(lambda _index: self.on_output_dir_changed())

        browse = QPushButton(OUTPUT_BROWSE)
        browse.setObjectName("browseButton")
        browse.clicked.connect(self.choose_output_dir)

        path_row.addWidget(self.output_dir_combo, 1)
        path_row.addWidget(browse)

        save_name_label = QLabel(SAVE_NAME_LABEL)
        save_name_label.setObjectName("fieldLabel")

        save_name_row = QHBoxLayout()
        save_name_row.setSpacing(10)

        self.save_name_edit = QLineEdit()
        self.save_name_edit.setObjectName("saveNameEdit")
        self.save_name_edit.setPlaceholderText(SAVE_NAME_PLACEHOLDER)
        self.save_name_edit.editingFinished.connect(self.save_ui_settings)

        self.apply_name_button = QPushButton(SAVE_NAME_BUTTON)
        self.apply_name_button.setObjectName("browseButton")
        self.apply_name_button.clicked.connect(lambda: self.apply_save_name())

        save_name_row.addWidget(self.save_name_edit, 1)
        save_name_row.addWidget(self.apply_name_button)

        format_label = QLabel(OUTPUT_FORMAT_LABEL)
        format_label.setObjectName("fieldLabel")

        format_row = QHBoxLayout()
        format_row.setSpacing(24)

        self.format_group = QButtonGroup(self)
        self.png_radio = QRadioButton(PNG_LABEL)
        self.jpeg_radio = QRadioButton(JPEG_LABEL)
        self.png_radio.setObjectName("radioLike")
        self.jpeg_radio.setObjectName("radioLike")
        self.png_radio.clicked.connect(lambda: self._set_format("png"))
        self.jpeg_radio.clicked.connect(lambda: self._set_format("jpeg"))
        self.format_group.addButton(self.png_radio)
        self.format_group.addButton(self.jpeg_radio)
        self.format_group.setExclusive(True)

        format_row.addWidget(self.png_radio)
        format_row.addWidget(self.jpeg_radio)
        format_row.addStretch(1)

        self.crop_check = QCheckBox(CROP_TEXT)
        self.crop_check.stateChanged.connect(self.save_ui_settings)

        self.open_folder_check = QCheckBox(OPEN_FOLDER_TEXT)
        self.open_folder_check.stateChanged.connect(self.save_ui_settings)

        self.path_hint = QLabel("")
        self.path_hint.setObjectName("hintLabel")
        self.path_hint.hide()

        layout.addWidget(title)
        layout.addWidget(path_label)
        layout.addLayout(path_row)
        layout.addSpacing(4)
        layout.addWidget(save_name_label)
        layout.addLayout(save_name_row)
        layout.addSpacing(4)
        layout.addWidget(format_label)
        layout.addLayout(format_row)
        layout.addSpacing(2)
        layout.addWidget(self.crop_check)
        layout.addWidget(self.open_folder_check)
        layout.addWidget(self.path_hint)
        return card

    def _build_progress_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("progressCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(26)

        title = QLabel(ACTION_TITLE)
        title.setObjectName("progressTitle")

        self.status_label = QLabel("0%")
        self.status_label.setObjectName("progressPercent")

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("mainProgress")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(READY_TEXT)
        self.progress_bar.setFixedHeight(12)

        layout.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.progress_bar, 1, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _build_queue_card(self) -> QFrame:
        card = ImageDropFrame()
        card.setObjectName("card")
        card.files_dropped.connect(self.add_files)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title = QLabel(QUEUE_TITLE)
        title.setObjectName("cardTitle")

        self.count_label = QLabel("(0 \ud30c\uc77c)")
        self.count_label.setObjectName("countChip")
        self.clear_button.show()

        header_row.addWidget(title)
        header_row.addWidget(self.count_label)
        header_row.addStretch(1)
        header_row.addWidget(self.clear_button)

        self.queue_list = QueueListWidget()
        self.queue_list.setObjectName("queueList")
        self.queue_list.files_dropped.connect(self.add_files)

        layout.addLayout(header_row)
        layout.addWidget(self.queue_list, 1)
        return card

    def _build_log_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        chip = QLabel(LOG_TITLE)
        chip.setObjectName("cardTitle")

        clear_button = QPushButton(CLEAR_LOG)
        clear_button.setObjectName("subButton")

        self.log_output = QPlainTextEdit()
        self.log_output.setObjectName("logOutput")
        self.log_output.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setPointSize(10)
        self.log_output.setFont(mono)
        clear_button.clicked.connect(self.log_output.clear)

        header_row.addWidget(chip)
        header_row.addStretch(1)
        header_row.addWidget(clear_button)

        layout.addLayout(header_row)
        layout.addWidget(self.log_output, 1)
        return card

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, #rootWidget {
                background: transparent;
                font-family: "Malgun Gothic";
            }
            QLabel, QCheckBox, QRadioButton, QToolButton, QPushButton {
                background: transparent;
            }
            #outerFrame {
                background: #fbfaf8;
                border: 1px solid #cfcfcf;
                border-radius: 18px;
            }
            #headerFrame {
                background: #ffffff;
                border-top-left-radius: 18px;
                border-top-right-radius: 18px;
                border-bottom: 1px solid #e7e2dd;
            }
            #sidebarFrame {
                background: #fbfaf8;
                border-right: 1px solid #ebe5df;
                border-bottom-left-radius: 18px;
            }
            #contentFrame {
                background: #fbfaf8;
                border-bottom-right-radius: 18px;
            }
            #brandLabel {
                color: #050505;
                font: 800 32px "Malgun Gothic";
            }
            #subtitleLabel {
                color: #4d5159;
                font: 500 18px "Malgun Gothic";
            }
            #pageTitle {
                color: #151515;
                font: 800 26px "Malgun Gothic";
            }
            #card {
                background: #ffffff;
                border: 1px solid #e8e2dc;
                border-radius: 14px;
            }
            #cardTitle {
                color: #111111;
                font: 800 18px "Malgun Gothic";
            }
            #fieldLabel {
                color: #171717;
                font: 700 14px "Malgun Gothic";
            }
            #statusLabel, #hintLabel, #metaLabel {
                color: #6a6d73;
                font: 500 13px "Malgun Gothic";
            }
            #countChip, #logChip {
                color: #5d6067;
                font: 600 15px "Malgun Gothic";
                padding: 0;
            }
            QToolButton#windowButton {
                border: none;
                border-radius: 8px;
                min-width: 38px;
                max-width: 38px;
                min-height: 38px;
                max-height: 38px;
                padding: 0;
            }
            QToolButton#windowButton:hover {
                background: #f4f1ee;
            }
            QToolButton#navButton {
                background: #ffffff;
                border: 1px solid #ece6df;
                border-radius: 14px;
                color: #151515;
                font: 800 16px "Malgun Gothic";
                min-width: 110px;
                max-width: 110px;
                min-height: 124px;
                padding: 12px 6px;
            }
            QToolButton#navButton:hover {
                border-color: #ffb27d;
                background: #fffaf6;
            }
            QToolButton#navButton:checked {
                border: 1px solid #ff8c45;
                background: #fff7f0;
                color: #111111;
            }
            #uploadButton {
                background: #ffffff;
                border: 1.6px dashed #ff8d45;
                border-radius: 12px;
                color: #575b63;
                font: 600 18px "Malgun Gothic";
                min-height: 112px;
                padding: 10px 18px;
                text-align: center;
            }
            #uploadButton:hover {
                background: #fff9f5;
                border-color: #ff6a00;
            }
            #uploadButton[dragActive="true"] {
                background: #fff1e6;
                border: 2px dashed #ff5a00;
                color: #ff5a00;
                font: 800 18px "Malgun Gothic";
            }
            #subButton, #browseButton {
                background: #ffffff;
                border: 1px solid #e0dcd7;
                border-radius: 8px;
                color: #151515;
                font: 700 14px "Malgun Gothic";
                min-height: 38px;
                padding: 0 14px;
            }
            #subButton:hover, #browseButton:hover {
                background: #fff7f0;
                border-color: #ff9c5a;
            }
            QComboBox#pathCombo {
                background: #ffffff;
                border: 1px solid #e0dcd7;
                border-radius: 8px;
                padding: 0 12px;
                min-height: 42px;
                color: #1b1b1b;
                font: 600 13px "Malgun Gothic";
            }
            QComboBox#pathCombo::drop-down {
                width: 28px;
                border: none;
            }
            QComboBox#pathCombo QAbstractItemView {
                background: #ffffff;
                border: 1px solid #e0dcd7;
                selection-background-color: #fff1e7;
            }
            QLineEdit {
                border: none;
                background: transparent;
            }
            QLineEdit#saveNameEdit {
                background: #ffffff;
                border: 1px solid #e0dcd7;
                border-radius: 8px;
                padding: 0 12px;
                min-height: 42px;
                color: #1b1b1b;
                font: 600 13px "Malgun Gothic";
            }
            QCheckBox, QRadioButton {
                color: #1d1d1f;
                font: 700 15px "Malgun Gothic";
                spacing: 8px;
            }
            QCheckBox::indicator, QRadioButton::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #d0d0d0;
                background: #ffffff;
            }
            QCheckBox::indicator {
                border-radius: 5px;
            }
            QRadioButton::indicator {
                border-radius: 9px;
            }
            QCheckBox::indicator:checked {
                background: #ff5a00;
                border-color: #ff5a00;
            }
            QRadioButton::indicator:checked {
                background: #ff5a00;
                border-color: #ff5a00;
            }
            QRadioButton#radioLike {
                font: 800 16px "Malgun Gothic";
            }
            QRadioButton#radioLike:checked {
                color: #ff5a00;
            }
            #startButton {
                background: #ff5a00;
                border: 1px solid #ff5a00;
                border-radius: 14px;
                color: #ffffff;
                font: 900 24px "Malgun Gothic";
                min-width: 260px;
                min-height: 78px;
                padding: 0 30px;
            }
            #startButton:hover {
                background: #ff6b16;
            }
            #startButton:disabled {
                background: #ffc09b;
                border-color: #ffc09b;
                color: #fff8f4;
            }
            #progressCard {
                background: #ffffff;
                border: 1px solid #e8e2dc;
                border-radius: 12px;
            }
            #progressTitle {
                color: #111111;
                font: 800 17px "Malgun Gothic";
            }
            #progressPercent {
                color: #171717;
                font: 500 22px "Malgun Gothic";
            }
            QProgressBar#mainProgress {
                background: #f0ebe7;
                border: none;
                border-radius: 6px;
            }
            QProgressBar#mainProgress::chunk {
                border-radius: 6px;
                background: #ff5a00;
            }
            QListWidget#queueList {
                background: #ffffff;
                border: none;
                outline: none;
            }
            QListWidget#queueList::item {
                border: none;
                padding: 0;
            }
            QListWidget#queueList::item:selected {
                background: transparent;
            }
            #queueItem {
                background: #ffffff;
                border: 1px solid transparent;
                border-bottom: 1px solid #f0ece8;
                border-radius: 10px;
            }
            #queueItem[activeRow="true"] {
                background: #fff8f2;
                border: 1px solid #ffd0ad;
            }
            #thumbLabel {
                background: #f8f8f8;
                border: 1px solid #eeeeee;
                border-radius: 10px;
            }
            QCheckBox#rowCheck {
                spacing: 0;
            }
            QCheckBox#rowCheck::indicator {
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 1px solid #d0d0d0;
                background: #ffffff;
            }
            QCheckBox#rowCheck::indicator:checked {
                background: #ff5a00;
                border-color: #ff5a00;
            }
            QToolButton#editButton {
                background: #ffffff;
                border: 1px solid #e0dcd7;
                border-radius: 7px;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
                padding: 0;
            }
            QToolButton#editButton:hover {
                background: #fff5ee;
                border-color: #ffad76;
            }
            QToolButton#deleteButton {
                background: transparent;
                border: none;
                border-radius: 8px;
                min-width: 40px;
                max-width: 40px;
                min-height: 40px;
                max-height: 40px;
                padding: 0;
            }
            QToolButton#deleteButton:hover {
                background: #fff1e7;
            }
            #nameLabel {
                color: #111111;
                font: 700 17px "Malgun Gothic";
            }
            #badgeLabel {
                background: #edf5e8;
                border: 1px solid #d7e8ce;
                border-radius: 7px;
                color: #4a7a36;
                font: 700 12px "Malgun Gothic";
                padding: 3px 9px;
            }
            QProgressBar#itemProgress {
                background: #eee8e3;
                border: none;
                border-radius: 5px;
            }
            QProgressBar#itemProgress::chunk {
                background: #ff5a00;
                border-radius: 5px;
            }
            QProgressBar#itemProgress[barState="done"]::chunk {
                background: #4fae58;
            }
            QProgressBar#itemProgress[barState="failed"]::chunk {
                background: #d77878;
            }
            QProgressBar#itemProgress[barState="processing"]::chunk {
                background: #ff8d45;
            }
            QPlainTextEdit#logOutput {
                background: #ffffff;
                border: none;
                border-top: 1px solid #ece6df;
                color: #171717;
                padding: 12px 4px 4px 4px;
            }
            """
        )

    def _load_settings_into_ui(self) -> None:
        output_dir = str(self.settings.get("output_dir", "")).strip() or str(default_output_dir())
        self.output_history = normalize_history(self.output_history, output_dir)
        self._populate_output_history(output_dir)

        output_format = str(self.settings.get("output_format", "png")).strip().lower()
        self._set_format("jpeg" if output_format == "jpeg" else "png", save=False)

        self.save_name_edit.setText(str(self.settings.get("save_name", "")).strip())
        self.crop_check.setChecked(bool(self.settings.get("crop", DEFAULT_CROP_ENABLED)))
        self.open_folder_check.setChecked(bool(self.settings.get("open_folder", DEFAULT_OPEN_FOLDER_ENABLED)))
        self.path_hint.setText(CURRENT_OUTPUT.format(path=output_dir))
        self._set_mode(self.selected_mode, save=False)

    def _populate_output_history(self, current_value: str) -> None:
        self.output_dir_combo.blockSignals(True)
        self.output_dir_combo.clear()
        self.output_dir_combo.addItems(self.output_history)
        self.output_dir_combo.setCurrentText(current_value)
        self.output_dir_combo.blockSignals(False)

    def current_output_dir(self) -> str:
        return self.output_dir_combo.currentText().strip()

    def current_output_format(self) -> str:
        return "jpeg" if self.jpeg_radio.isChecked() else "png"

    def current_output_extension(self) -> str:
        return ".jpg" if self.current_output_format() == "jpeg" else ".png"

    def current_save_name(self) -> str:
        return self.save_name_edit.text().strip()

    def _set_format(self, value: str, save: bool = True) -> None:
        is_jpeg = value == "jpeg"
        self.png_radio.blockSignals(True)
        self.jpeg_radio.blockSignals(True)
        self.png_radio.setChecked(not is_jpeg)
        self.jpeg_radio.setChecked(is_jpeg)
        self.png_radio.blockSignals(False)
        self.jpeg_radio.blockSignals(False)
        self._refresh_output_name_visuals()
        if save:
            self.save_ui_settings()

    def _set_mode(self, mode: str, save: bool = True) -> None:
        self.selected_mode = PROCESS_MODE_SCAN if mode == PROCESS_MODE_SCAN else PROCESS_MODE_BACKGROUND
        if hasattr(self, "background_button"):
            self.background_button.blockSignals(True)
            self.scan_button.blockSignals(True)
            self.background_button.setChecked(self.selected_mode == PROCESS_MODE_BACKGROUND)
            self.scan_button.setChecked(self.selected_mode == PROCESS_MODE_SCAN)
            self.background_button.blockSignals(False)
            self.scan_button.blockSignals(False)
        if save:
            self.save_ui_settings()

    def _remember_output_dir(self, output_dir: str) -> None:
        self.output_history = normalize_history(self.output_history, output_dir)
        self._populate_output_history(output_dir)

    def _remember_last_input_dir(self, directory: str | Path) -> None:
        self.last_input_dir = str(Path(directory).expanduser().resolve())

    def save_ui_settings(self) -> None:
        output_dir = self.current_output_dir() or str(default_output_dir())
        self._remember_output_dir(output_dir)
        payload = {
            "output_dir": output_dir,
            "output_history": self.output_history,
            "output_format": self.current_output_format(),
            "mode": self.selected_mode,
            "save_name": self.current_save_name(),
            "crop": self.crop_check.isChecked(),
            "open_folder": self.open_folder_check.isChecked(),
            "last_input_dir": self.last_input_dir,
        }
        self.settings = payload
        self.path_hint.setText(CURRENT_OUTPUT.format(path=output_dir))
        save_settings(payload)

    @Slot()
    def apply_save_name(self, show_log: bool = True) -> None:
        raw_name = self.current_save_name()
        cleaned_name = sanitize_output_stem(raw_name, fallback="")
        if cleaned_name != raw_name:
            self.save_name_edit.setText(cleaned_name)

        self.output_name_map.clear()
        if cleaned_name:
            for index, path in enumerate(self.queued_files, start=1):
                self.output_name_map[path] = f"{cleaned_name}({index})"

        self._refresh_output_name_visuals()
        self.save_ui_settings()

        if not show_log:
            return
        if not self.queued_files:
            self.append_log("\uc800\uc7a5 \uc774\ub984\uc744 \uc800\uc7a5\ud588\uc2b5\ub2c8\ub2e4. \uc774\ubbf8\uc9c0\ub97c \ucd94\uac00\ud558\uba74 \ubaa9\ub85d\uc5d0 \ubc18\uc601\ub429\ub2c8\ub2e4.")
        elif cleaned_name:
            self.append_log(f"\uc800\uc7a5 \uc774\ub984\uc744 '{cleaned_name}' \uae30\uc900\uc73c\ub85c {len(self.queued_files)}\uac1c \ud30c\uc77c\uc5d0 \uc801\uc6a9\ud588\uc2b5\ub2c8\ub2e4.")
        else:
            self.append_log("\uc800\uc7a5 \uc774\ub984 \uc124\uc815\uc744 \uc9c0\uc6b0\uace0 \uc6d0\ubcf8 \ud30c\uc77c\uba85\uc73c\ub85c \ub418\ub3cc\ub838\uc2b5\ub2c8\ub2e4.")

    def _refresh_output_name_visuals(self) -> None:
        extension = self.current_output_extension()
        for path, widget in zip(self.queued_files, self.queue_widgets):
            widget.set_output_name(self.output_name_map.get(path, ""), extension)

    @Slot()
    def on_output_dir_changed(self) -> None:
        self.save_ui_settings()

    @Slot()
    def choose_output_dir(self) -> None:
        start_dir = self.current_output_dir() or str(default_output_dir())
        selected = QFileDialog.getExistingDirectory(self, PICK_OUTPUT_TITLE, start_dir)
        if not selected:
            return
        self._remember_output_dir(selected)
        self.save_ui_settings()

    @Slot()
    def select_files(self) -> None:
        start_dir = preferred_input_dir(self.last_input_dir, self.current_output_dir())
        files, _ = QFileDialog.getOpenFileNames(
            self,
            PICK_IMAGES_TITLE,
            start_dir,
            IMAGE_FILE_DIALOG_FILTER,
        )
        if not files:
            return

        self._remember_last_input_dir(Path(files[0]).parent)
        self.save_ui_settings()
        self.add_files(files)

    @Slot(list)
    def add_files(self, files: list[str]) -> None:
        added = 0
        skipped = 0
        known = {Path(path).resolve() for path in self.queued_files}

        for raw_path in files:
            candidate = Path(raw_path)
            if not candidate.exists() or not candidate.is_file() or not is_supported_image(candidate):
                skipped += 1
                continue

            resolved = candidate.resolve()
            if resolved in known:
                skipped += 1
                continue

            known.add(resolved)
            self.queued_files.append(str(resolved))
            self._append_queue_item(resolved)
            added += 1

        if added:
            self._remember_last_input_dir(Path(files[0]).parent)
            self.save_ui_settings()
            if self.current_save_name():
                self.apply_save_name(show_log=False)

        self._refresh_count_label()
        if added:
            self.append_log(f"{added} \ud30c\uc77c\uc744 \ubaa9\ub85d\uc5d0 \ucd94\uac00\ud588\uc2b5\ub2c8\ub2e4.")
        if skipped:
            self.append_log(f"{skipped} \ud30c\uc77c\uc740 \uc9c0\uc6d0\ud558\uc9c0 \uc54a\uac70\ub098 \uc774\ubbf8 \ucd94\uac00\ub418\uc5b4 \uac74\ub108\ub6f0\uc5c8\uc2b5\ub2c8\ub2e4.")

    def _append_queue_item(self, path: Path) -> None:
        widget = QueueItemWidget(path)
        widget.edit_requested.connect(lambda path_str=str(path): self.open_region_editor(path_str))
        widget.remove_requested.connect(lambda path_str=str(path): self.remove_file(path_str))
        item = QListWidgetItem()
        item.setSizeHint(QSize(0, 88))
        self.queue_list.addItem(item)
        self.queue_list.setItemWidget(item, widget)
        self.queue_widgets.append(widget)
        self._sync_region_visual(path)

    def _sync_region_visual(self, path: Path | str) -> None:
        key = str(Path(path).resolve())
        if key not in self.queued_files:
            return
        row = self.queued_files.index(key)
        regions = self.region_configs.get(key, [])
        if 0 <= row < len(self.queue_widgets):
            self.queue_widgets[row].set_regions(regions)

    def open_region_editor(self, path_str: str) -> None:
        source_path = Path(path_str)
        existing = self.region_configs.get(str(source_path), [])
        dialog = RegionEditorDialog(source_path, existing, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        regions = dialog.result_regions()
        if regions:
            self.region_configs[str(source_path)] = regions
            self.append_log(f"{source_path.name}: {len(regions)}\uac1c \uc601\uc5ed\uc744 \uc124\uc815\ud588\uc2b5\ub2c8\ub2e4.")
        else:
            self.region_configs.pop(str(source_path), None)
            self.append_log(f"{source_path.name}: \uc601\uc5ed \uc124\uc815\uc744 \uc9c0\uc6e0\uc2b5\ub2c8\ub2e4.")
        self._sync_region_visual(source_path)

    def remove_file(self, path_str: str) -> None:
        key = str(Path(path_str).resolve())
        if key not in self.queued_files:
            return

        row = self.queued_files.index(key)
        self.queue_list.takeItem(row)
        del self.queued_files[row]
        del self.queue_widgets[row]
        self.region_configs.pop(key, None)
        self._refresh_count_label()
        if self.current_save_name():
            self.apply_save_name(show_log=False)
        self.append_log(f"{Path(key).name} \ud30c\uc77c\uc744 \ubaa9\ub85d\uc5d0\uc11c \uc0ad\uc81c\ud588\uc2b5\ub2c8\ub2e4.")

    @Slot()
    def remove_selected_rows(self) -> None:
        checked_rows = [index for index, widget in enumerate(self.queue_widgets) if widget.is_checked()]
        rows = sorted(checked_rows, reverse=True)
        if not rows:
            return

        for row in rows:
            path_key = self.queued_files[row]
            self.queue_list.takeItem(row)
            del self.queued_files[row]
            del self.queue_widgets[row]
            self.region_configs.pop(path_key, None)

        self._refresh_count_label()
        if self.current_save_name():
            self.apply_save_name(show_log=False)
        self.append_log(f"\uc120\ud0dd\ud55c {len(rows)}\uac1c \ud30c\uc77c\uc744 \uc0ad\uc81c\ud588\uc2b5\ub2c8\ub2e4.")

    @Slot()
    def clear_files(self) -> None:
        if not self.queued_files:
            return
        self.queue_list.clear()
        self.queued_files.clear()
        self.queue_widgets.clear()
        self.region_configs.clear()
        self.output_name_map.clear()
        self._refresh_count_label()
        self.status_label.setText("0%")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(READY_TEXT)
        self.append_log("\uc774\ubbf8\uc9c0 \ubaa9\ub85d\uc744 \ube44\uc6e0\uc2b5\ub2c8\ub2e4.")

    def _refresh_count_label(self) -> None:
        self.count_label.setText(f"({len(self.queued_files)} \ud30c\uc77c)")

    def append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.appendPlainText(f"[{timestamp}] {message}")
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def build_options(self) -> RemovalOptions:
        is_scan_mode = self.selected_mode == PROCESS_MODE_SCAN
        return RemovalOptions(
            method="scan" if is_scan_mode else "white",
            transparent_cutoff=8 if is_scan_mode else 18,
            opaque_cutoff=100 if is_scan_mode else 96,
            crop=self.crop_check.isChecked(),
            output_format=self.current_output_format(),
            output_suffix=SCAN_OUTPUT_SUFFIX if is_scan_mode else BACKGROUND_OUTPUT_SUFFIX,
        )

    @Slot()
    def start_processing(self) -> None:
        if self.worker_thread is not None:
            return
        if not self.queued_files:
            QMessageBox.warning(self, ERROR_TITLE, NO_FILES_MESSAGE)
            return

        output_dir = self.current_output_dir()
        if not output_dir:
            QMessageBox.warning(self, ERROR_TITLE, NO_OUTPUT_DIR_MESSAGE)
            return

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        self.save_ui_settings()

        for widget in self.queue_widgets:
            widget.set_state(QUEUE_STATUS_QUEUED)

        self.status_label.setText(f"0% (0/{len(self.queued_files)})")
        self.progress_bar.setRange(0, len(self.queued_files))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"0 / {len(self.queued_files)}")
        mode_label = "\uc2a4\uce94 \uc774\ubbf8\uc9c0 \ub9cc\ub4e4\uae30" if self.selected_mode == PROCESS_MODE_SCAN else "\ubc30\uacbd\uc81c\uac70"
        self.append_log(f"{mode_label} \uc791\uc5c5\uc744 \uc2dc\uc791\ud569\ub2c8\ub2e4.")
        self.append_log(f"\ucd9c\ub825 \ud3f4\ub354: {output_dir}")
        self._set_processing_state(True)

        self.worker_thread = QThread(self)
        region_map = {
            path: [region.copy() for region in regions]
            for path, regions in self.region_configs.items()
            if path in self.queued_files and regions
        }
        output_name_map = {
            path: self.output_name_map[path]
            for path in self.queued_files
            if path in self.output_name_map
        }
        self.worker = BatchWorker(
            list(self.queued_files),
            output_dir,
            self.build_options(),
            region_map=region_map,
            output_name_map=output_name_map,
        )
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress_changed.connect(self.on_progress_changed)
        self.worker.item_updated.connect(self.on_item_updated)
        self.worker.log_message.connect(self.append_log)
        self.worker.completed.connect(self.on_processing_complete)
        self.worker.failed.connect(self.on_processing_failed)
        self.worker.completed.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(self._cleanup_worker)
        self.worker_thread.start()

    def _set_processing_state(self, busy: bool) -> None:
        self.start_button.setDisabled(busy)
        self.add_button.setDisabled(busy)
        self.remove_button.setDisabled(busy)
        self.clear_button.setDisabled(busy)
        self.output_dir_combo.setDisabled(busy)
        self.crop_check.setDisabled(busy)
        self.open_folder_check.setDisabled(busy)
        self.png_radio.setDisabled(busy)
        self.jpeg_radio.setDisabled(busy)
        self.background_button.setDisabled(busy)
        self.scan_button.setDisabled(busy)
        for widget in self.queue_widgets:
            widget.check_box.setDisabled(busy)
            widget.edit_button.setDisabled(busy)
            widget.delete_button.setDisabled(busy)

    @Slot(int, int)
    def on_progress_changed(self, current: int, total: int) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"{current} / {total}")
        percent = int(round((current / max(1, total)) * 100))
        self.status_label.setText(f"{percent}% ({current}/{total})")

    @Slot(int, str, str)
    def on_item_updated(self, row: int, status: str, detail: str) -> None:
        if 0 <= row < len(self.queue_widgets):
            self.queue_widgets[row].set_state(status, detail)

    @Slot(str, int, int)
    def on_processing_complete(self, output_dir: str, success_count: int, failure_count: int) -> None:
        self._set_processing_state(False)
        total = max(1, len(self.queued_files))
        self.status_label.setText(f"100% ({success_count}/{total})")
        self.progress_bar.setFormat(f"Done: {success_count} success")
        self.append_log(f"\uc644\ub8cc: \uc131\uacf5 {success_count}, \uc2e4\ud328 {failure_count}")

        if self.open_folder_check.isChecked() and success_count > 0:
            output_path = Path(output_dir)
            if output_path.exists():
                self.append_log(f"\ucd9c\ub825 \ud3f4\ub354\ub97c \uc5fd\ub2c8\ub2e4: {output_path}")
                open_folder_in_explorer(output_path)

        QMessageBox.information(
            self,
            COMPLETE_TITLE,
            COMPLETE_MESSAGE.format(success=success_count, failed=failure_count),
        )

    @Slot(str)
    def on_processing_failed(self, traceback_text: str) -> None:
        self._set_processing_state(False)
        self.status_label.setText(STATUS_ERROR)
        self.progress_bar.setFormat("Failed")
        self.append_log("\uc77c\uad04 \ucc98\ub9ac \uc911 \uc608\uc0c1\uce58 \ubabb\ud55c \uc624\ub958:")
        self.append_log(traceback_text)
        QMessageBox.critical(self, ERROR_TITLE, UNEXPECTED_ERROR_MESSAGE)

    @Slot()
    def _cleanup_worker(self) -> None:
        self.worker = None
        self.worker_thread = None


def main() -> None:
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(APP_NAME)

    app = QApplication(sys.argv)
    app.setFont(QFont("Malgun Gothic", 10))
    window = NukkiWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
