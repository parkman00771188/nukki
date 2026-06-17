from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from nukki_updater import (
    UpdatePackage,
    app_install_dir,
    ensure_local_version_file,
    find_update_package,
    prepare_update_package,
    schedule_update_install,
)


def create_update_logo_pixmap(size: int = 70) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#ff5a00"))
    painter.drawEllipse(QRectF(3, 3, size - 6, size - 6))
    painter.save()
    clip = QPainterPath()
    clip.addEllipse(QRectF(3, 3, size - 6, size - 6))
    painter.setClipPath(clip)
    painter.translate(size / 2, size / 2)
    painter.rotate(-26)
    painter.setPen(QPen(QColor("#ffffff"), max(6, size // 9), Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
    for offset in (-size * 0.28, -size * 0.09, size * 0.10, size * 0.29):
        painter.drawLine(QPointF(-size * 0.55, offset), QPointF(size * 0.55, offset))
    painter.restore()
    painter.end()
    return pixmap


class StartupUpdateCheckWorker(QObject):
    status_changed = Signal(str)
    progress_changed = Signal(int)
    update_available = Signal(object)
    no_update = Signal(str)
    failed = Signal(str)
    finished = Signal()

    @Slot()
    def run(self) -> None:
        try:
            self.status_changed.emit("현재 버전을 확인하는 중입니다...")
            current_version = ensure_local_version_file()
            self.progress_changed.emit(25)
            self.status_changed.emit("업데이트 버전을 확인하는 중입니다...")
            package = find_update_package(current_version)
            self.progress_changed.emit(80)
            if package is None:
                self.no_update.emit(current_version)
            else:
                self.update_available.emit(package)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class StartupUpdateDownloadWorker(QObject):
    status_changed = Signal(str)
    progress_changed = Signal(int)
    ready = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, package: UpdatePackage, target_dir: Path) -> None:
        super().__init__()
        self.package = package
        self.target_dir = target_dir

    @Slot()
    def run(self) -> None:
        try:
            self.status_changed.emit(f"{self.package.remote_version} 업데이트 파일을 다운로드하는 중입니다...")
            source_dir, _update_root = prepare_update_package(self.package, progress=self.progress_changed.emit)
            self.status_changed.emit("업데이트 설치를 준비하는 중입니다...")
            script_path = schedule_update_install(source_dir, self.target_dir, self.package.remote_version)
            self.ready.emit(str(script_path))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class StartupUpdateDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.should_exit_for_update = False
        self.package: UpdatePackage | None = None
        self.worker_thread: QThread | None = None
        self.worker: QObject | None = None

        self.setWindowTitle("Nukki 업데이트 확인")
        self.setModal(True)
        self.setFixedSize(480, 306)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
        self._build_ui()
        QTimer.singleShot(120, self.start_check)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 24)
        layout.setSpacing(16)

        logo_row = QHBoxLayout()
        logo_row.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(create_update_logo_pixmap(70))
        logo.setFixedSize(76, 76)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_row.addWidget(logo)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Nukki")
        title.setObjectName("updateTitle")
        title.setFont(QFont("Malgun Gothic", 24, QFont.Weight.Black))
        subtitle = QLabel("업데이트를 확인하고 있습니다.")
        subtitle.setObjectName("updateSubtitle")
        title_col.addStretch(1)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_col.addStretch(1)
        logo_row.addLayout(title_col, 1)
        layout.addLayout(logo_row)

        self.status_label = QLabel("프로그램을 시작할 준비를 하는 중입니다...")
        self.status_label.setObjectName("updateStatus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        layout.addWidget(self.progress_bar)

        self.detail_label = QLabel("")
        self.detail_label.setObjectName("updateDetail")
        self.detail_label.setWordWrap(True)
        self.detail_label.setMinimumHeight(42)
        layout.addWidget(self.detail_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.update_button = QPushButton("업데이트")
        self.update_button.setObjectName("updatePrimaryButton")
        self.update_button.setVisible(False)
        self.update_button.clicked.connect(self.start_update)
        button_row.addWidget(self.update_button)

        self.cancel_button = QPushButton("취소")
        self.cancel_button.setObjectName("updateSecondaryButton")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.accept)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        self.setStyleSheet("""
            QDialog { background: #fffaf5; color: #191919; }
            QLabel#updateTitle { color: #111111; font-size: 30px; font-weight: 900; }
            QLabel#updateSubtitle { color: #5c6470; font-size: 14px; font-weight: 600; }
            QLabel#updateStatus { color: #1d232b; font-size: 16px; font-weight: 700; }
            QLabel#updateDetail { color: #7a818d; font-size: 13px; line-height: 1.35; }
            QProgressBar { background: #eee8e3; border: 0; border-radius: 5px; }
            QProgressBar::chunk { background: #ff5a00; border-radius: 5px; }
            QPushButton { min-width: 104px; min-height: 38px; padding: 0 18px; border-radius: 10px; font-size: 14px; font-weight: 800; }
            QPushButton#updatePrimaryButton { color: #ffffff; background: #ff5a00; border: 1px solid #ff5a00; }
            QPushButton#updatePrimaryButton:hover { background: #ff6f1d; }
            QPushButton#updateSecondaryButton { color: #353941; background: #ffffff; border: 1px solid #e4d9d0; }
            QPushButton#updateSecondaryButton:hover { border-color: #ffb27d; color: #ff5a00; }
        """)

    def _clear_worker(self) -> None:
        self.worker = None
        self.worker_thread = None

    def _start_thread(self, worker: QObject) -> None:
        self.worker_thread = QThread(self)
        self.worker = worker
        worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(worker.run)
        worker.finished.connect(self.worker_thread.quit)
        worker.finished.connect(worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(self._clear_worker)
        self.worker_thread.start()

    def start_check(self) -> None:
        self.progress_bar.setValue(12)
        worker = StartupUpdateCheckWorker()
        worker.status_changed.connect(self.status_label.setText)
        worker.progress_changed.connect(self.progress_bar.setValue)
        worker.update_available.connect(self.on_update_available)
        worker.no_update.connect(self.on_no_update)
        worker.failed.connect(self.on_check_failed)
        self._start_thread(worker)

    @Slot(object)
    def on_update_available(self, package: object) -> None:
        if not isinstance(package, UpdatePackage):
            self.on_check_failed("업데이트 정보를 읽을 수 없습니다.")
            return
        self.package = package
        self.progress_bar.setValue(100)
        self.status_label.setText("새 업데이트가 있습니다.")
        self.detail_label.setText(f"현재 버전 {package.current_version}에서 최신 버전 {package.remote_version}(으)로 업데이트할 수 있습니다.\n취소하면 기존 버전으로 바로 실행됩니다.")
        self.update_button.setVisible(True)
        self.cancel_button.setVisible(True)
        self.cancel_button.setText("취소")

    @Slot(str)
    def on_no_update(self, version: str) -> None:
        self.progress_bar.setValue(100)
        self.status_label.setText("최신 버전입니다.")
        self.detail_label.setText(f"현재 버전 {version}으로 실행합니다.")
        QTimer.singleShot(650, self.accept)

    @Slot(str)
    def on_check_failed(self, message: str) -> None:
        self.progress_bar.setValue(100)
        self.status_label.setText("업데이트 확인에 실패했습니다.")
        self.detail_label.setText(f"{message}\n기존 버전으로 실행할 수 있습니다.")
        self.update_button.setVisible(False)
        self.cancel_button.setVisible(True)
        self.cancel_button.setText("실행")

    @Slot()
    def start_update(self) -> None:
        if self.package is None:
            return
        self.update_button.setDisabled(True)
        self.cancel_button.setDisabled(True)
        self.progress_bar.setValue(0)
        self.detail_label.setText("다운로드가 끝나면 프로그램을 종료하고 새 파일로 교체합니다.")
        worker = StartupUpdateDownloadWorker(self.package, app_install_dir())
        worker.status_changed.connect(self.status_label.setText)
        worker.progress_changed.connect(self.progress_bar.setValue)
        worker.ready.connect(self.on_update_ready)
        worker.failed.connect(self.on_update_failed)
        self._start_thread(worker)

    @Slot(str)
    def on_update_ready(self, _script_path: str) -> None:
        self.should_exit_for_update = True
        self.progress_bar.setValue(100)
        self.status_label.setText("업데이트 준비가 완료되었습니다.")
        self.detail_label.setText("Nukki를 종료한 뒤 새 버전으로 교체하고 다시 실행합니다.")
        QTimer.singleShot(900, self.accept)

    @Slot(str)
    def on_update_failed(self, message: str) -> None:
        self.update_button.setDisabled(False)
        self.cancel_button.setDisabled(False)
        self.cancel_button.setText("기존 버전 실행")
        self.status_label.setText("업데이트에 실패했습니다.")
        self.detail_label.setText(f"{message}\n기존 버전으로 계속 실행할 수 있습니다.")
