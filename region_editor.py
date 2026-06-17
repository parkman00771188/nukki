from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from remove_signature_background import NamedRegion

RECT_MODE = "rect"
POLYGON_MODE = "polygon"
CANVAS_MARGIN = 8
CANVAS_FRAME_OUTSET = 4
DEFAULT_VIEWPORT_SIZE = QSize(1080, 760)
MIN_ZOOM_FACTOR = 0.35
MAX_ZOOM_FACTOR = 6.0
ZOOM_STEP = 1.15


def create_tool_icon(mode: str, size: int = 22) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor("#efeaff"), 1.8))
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if mode == RECT_MODE:
        painter.drawRoundedRect(QRectF(3.5, 4.5, size - 7, size - 9), 4, 4)
    else:
        polygon = QPolygonF(
            [
                QPointF(4.5, size * 0.72),
                QPointF(size * 0.34, 4.5),
                QPointF(size - 4.5, size * 0.32),
                QPointF(size * 0.74, size - 4.5),
            ]
        )
        painter.drawPolygon(polygon)
        painter.setBrush(QColor("#efeaff"))
        for point in polygon:
            painter.drawEllipse(point, 1.7, 1.7)

    painter.end()
    return QIcon(pixmap)


class RegionCanvas(QFrame):
    region_created = Signal(object)
    region_selected = Signal(int)
    zoom_changed = Signal(float)

    def __init__(self, image_path: Path, regions: list[NamedRegion]) -> None:
        super().__init__()
        self.image_path = image_path
        self.regions = regions
        self.selected_index = -1
        self.draw_mode = RECT_MODE
        self.zoom_factor = 1.0
        self.base_viewport_size = QSize(DEFAULT_VIEWPORT_SIZE)
        self.pan_active = False
        self.pan_start_global: QPoint | None = None
        self.pan_start_horizontal = 0
        self.pan_start_vertical = 0
        self.rect_start: tuple[int, int] | None = None
        self.rect_end: tuple[int, int] | None = None
        self.polygon_draft: list[tuple[int, int]] = []
        self.polygon_hover: tuple[int, int] | None = None
        self.pixmap = QPixmap(str(image_path))

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setObjectName("regionCanvas")
        self.update_canvas_size()

    def set_selected_index(self, index: int) -> None:
        self.selected_index = index
        self.update()

    def set_draw_mode(self, mode: str) -> None:
        self.draw_mode = POLYGON_MODE if mode == POLYGON_MODE else RECT_MODE
        self.cancel_draft()

    def set_base_viewport_size(self, size: QSize) -> None:
        if size.width() <= 0 or size.height() <= 0:
            return
        if self.base_viewport_size == size:
            return
        self.base_viewport_size = QSize(size)
        self.update_canvas_size()

    def set_zoom_factor(self, value: float) -> None:
        clamped = max(MIN_ZOOM_FACTOR, min(MAX_ZOOM_FACTOR, float(value)))
        if abs(clamped - self.zoom_factor) < 0.0001:
            return
        self.zoom_factor = clamped
        self.update_canvas_size()
        self.zoom_changed.emit(self.zoom_factor)
        self.update()

    def refresh(self) -> None:
        self.update_canvas_size()
        self.update()

    def cancel_draft(self) -> None:
        self.rect_start = None
        self.rect_end = None
        self.polygon_draft.clear()
        self.polygon_hover = None
        self.update()

    def update_canvas_size(self) -> None:
        display_size = self._display_image_size()
        width = max(self.base_viewport_size.width(), display_size.width() + CANVAS_MARGIN * 2)
        height = max(self.base_viewport_size.height(), display_size.height() + CANVAS_MARGIN * 2)
        self.setMinimumSize(width, height)
        self.resize(width, height)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#17151d"))

        view_rect = self._image_rect()
        if view_rect.isValid() and not self.pixmap.isNull():
            painter.fillRect(
                view_rect.adjusted(
                    -CANVAS_FRAME_OUTSET,
                    -CANVAS_FRAME_OUTSET,
                    CANVAS_FRAME_OUTSET,
                    CANVAS_FRAME_OUTSET,
                ),
                QColor("#262230"),
            )
            painter.drawPixmap(view_rect, self.pixmap)

            for index, region in enumerate(self.regions):
                path = self._region_to_view_path(region)
                if path.isEmpty():
                    continue

                is_selected = index == self.selected_index
                painter.setPen(QPen(QColor("#66d08e") if is_selected else QColor("#9e8cff"), 2.4))
                painter.setBrush(QColor(102, 208, 142, 30) if is_selected else QColor(158, 140, 255, 26))
                painter.drawPath(path)

                if is_selected:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor("#66d08e"))
                    for point in self._region_to_view_points(region):
                        painter.drawEllipse(point, 4.5, 4.5)

                bounds = path.boundingRect().toRect()
                label_width = min(220, max(108, bounds.width() - 12))
                label_rect = QRect(bounds.left() + 6, bounds.top() + 6, label_width, 24)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#66d08e") if is_selected else QColor("#8d78f0"))
                painter.drawRoundedRect(QRectF(label_rect), 10, 10)
                painter.setPen(QColor("#ffffff"))
                painter.drawText(label_rect.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, region.name)

            self._paint_rect_preview(painter)
            self._paint_polygon_preview(painter)

        painter.end()
        super().paintEvent(event)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        delta = event.angleDelta().y()
        if self.pixmap.isNull() or delta == 0:
            super().wheelEvent(event)
            return

        old_image_rect = self._image_rect()
        old_zoom = self.zoom_factor
        global_point = event.globalPosition().toPoint()
        anchor_ratio: tuple[float, float] | None = None
        local_point = event.position().toPoint()

        if old_image_rect.contains(local_point):
            anchor_ratio = (
                (local_point.x() - old_image_rect.x()) / max(1, old_image_rect.width()),
                (local_point.y() - old_image_rect.y()) / max(1, old_image_rect.height()),
            )

        steps = max(1, abs(delta) // 120)
        scale_multiplier = ZOOM_STEP**steps
        new_zoom = old_zoom * scale_multiplier if delta > 0 else old_zoom / scale_multiplier
        self.set_zoom_factor(new_zoom)

        if anchor_ratio is not None and abs(self.zoom_factor - old_zoom) > 0.0001:
            self._reposition_scrollbars(global_point, anchor_ratio)

        event.accept()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.MiddleButton:
            scroll_area = self._find_scroll_area()
            if scroll_area is not None:
                self.pan_active = True
                self.pan_start_global = event.globalPosition().toPoint()
                self.pan_start_horizontal = scroll_area.horizontalScrollBar().value()
                self.pan_start_vertical = scroll_area.verticalScrollBar().value()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.grabMouse(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return

        if event.button() == Qt.MouseButton.RightButton and self.draw_mode == POLYGON_MODE and self.polygon_draft:
            self.polygon_draft.pop()
            if not self.polygon_draft:
                self.polygon_hover = None
            self.update()
            event.accept()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        view_point = event.position().toPoint()
        if self.draw_mode == POLYGON_MODE:
            if self.polygon_draft and self._is_near_first_polygon_vertex(view_point):
                self._finalize_polygon()
                event.accept()
                return

            if not self.polygon_draft:
                index = self._hit_test(view_point)
                if index >= 0:
                    self.region_selected.emit(index)
                    event.accept()
                    return

            image_point = self._view_point_to_image(view_point, clamp=False)
            if image_point is None:
                super().mousePressEvent(event)
                return

            self.region_selected.emit(-1)
            self._append_polygon_point(image_point)
            event.accept()
            return

        index = self._hit_test(view_point)
        if index >= 0:
            self.region_selected.emit(index)
            event.accept()
            return

        image_point = self._view_point_to_image(view_point, clamp=False)
        if image_point is None:
            super().mousePressEvent(event)
            return

        self.region_selected.emit(-1)
        self.rect_start = image_point
        self.rect_end = image_point
        event.accept()
        self.update()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self.pan_active:
            self._update_pan(event.globalPosition().toPoint())
            event.accept()
            return

        if self.draw_mode == POLYGON_MODE:
            self.polygon_hover = self._view_point_to_image(event.position().toPoint(), clamp=True)
            self.update()
            return

        if self.rect_start is None:
            super().mouseMoveEvent(event)
            return

        self.rect_end = self._view_point_to_image(event.position().toPoint(), clamp=True)
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.MiddleButton and self.pan_active:
            self._stop_pan()
            event.accept()
            return

        if self.draw_mode == POLYGON_MODE:
            super().mouseReleaseEvent(event)
            return

        if event.button() != Qt.MouseButton.LeftButton or self.rect_start is None or self.rect_end is None:
            super().mouseReleaseEvent(event)
            return

        start_x, start_y = self.rect_start
        end_x, end_y = self.rect_end
        self.rect_start = None
        self.rect_end = None
        self.update()

        width = abs(end_x - start_x)
        height = abs(end_y - start_y)
        if width < 12 or height < 12:
            return

        next_index = len(self.regions) + 1
        region = NamedRegion(
            name=f"region_{next_index}",
            left=min(start_x, end_x),
            top=min(start_y, end_y),
            right=max(start_x, end_x) + 1,
            bottom=max(start_y, end_y) + 1,
            shape=RECT_MODE,
        )
        self.region_created.emit(region)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self.draw_mode == POLYGON_MODE and len(self.polygon_draft) >= 3:
            self._finalize_polygon()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_draft()
            event.accept()
            return

        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and self.draw_mode == POLYGON_MODE and len(self.polygon_draft) >= 3:
            self._finalize_polygon()
            event.accept()
            return

        super().keyPressEvent(event)

    def _paint_rect_preview(self, painter: QPainter) -> None:
        if self.rect_start is None or self.rect_end is None:
            return

        start = self._image_point_to_view(self.rect_start)
        end = self._image_point_to_view(self.rect_end)
        preview = QRect(start.toPoint(), end.toPoint()).normalized()
        painter.setPen(QPen(QColor("#f7c94b"), 2, Qt.PenStyle.DashLine))
        painter.setBrush(QColor(247, 201, 75, 34))
        painter.drawRoundedRect(QRectF(preview), 8, 8)

    def _paint_polygon_preview(self, painter: QPainter) -> None:
        if not self.polygon_draft:
            return

        points = [self._image_point_to_view(point) for point in self.polygon_draft]
        if self.polygon_hover is not None:
            points.append(self._image_point_to_view(self.polygon_hover))

        painter.setPen(QPen(QColor("#f7c94b"), 2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if len(points) >= 2:
            painter.drawPolyline(QPolygonF(points))

        if len(self.polygon_draft) >= 3:
            first_point = self._image_point_to_view(self.polygon_draft[0])
            last_point = self._image_point_to_view(self.polygon_draft[-1])
            painter.drawLine(last_point, first_point)

        painter.setPen(Qt.PenStyle.NoPen)
        for index, point in enumerate(self.polygon_draft):
            painter.setBrush(QColor("#66d08e") if index == 0 and len(self.polygon_draft) >= 3 else QColor("#f7c94b"))
            painter.drawEllipse(self._image_point_to_view(point), 5, 5)

    def _append_polygon_point(self, point: tuple[int, int]) -> None:
        if self.polygon_draft and abs(self.polygon_draft[-1][0] - point[0]) <= 1 and abs(self.polygon_draft[-1][1] - point[1]) <= 1:
            return

        self.polygon_draft.append(point)
        self.polygon_hover = point
        self.update()

    def _finalize_polygon(self) -> None:
        if len(self.polygon_draft) < 3:
            self.cancel_draft()
            return

        xs = [point[0] for point in self.polygon_draft]
        ys = [point[1] for point in self.polygon_draft]
        next_index = len(self.regions) + 1
        region = NamedRegion(
            name=f"region_{next_index}",
            left=min(xs),
            top=min(ys),
            right=max(xs) + 1,
            bottom=max(ys) + 1,
            shape=POLYGON_MODE,
            points=tuple(self.polygon_draft),
        )
        self.cancel_draft()
        self.region_created.emit(region)

    def _base_scale(self) -> float:
        if self.pixmap.isNull():
            return 1.0

        available_width = max(120, self.base_viewport_size.width() - CANVAS_MARGIN * 2)
        available_height = max(120, self.base_viewport_size.height() - CANVAS_MARGIN * 2)
        width_scale = available_width / max(1, self.pixmap.width())
        height_scale = available_height / max(1, self.pixmap.height())
        return max(0.01, min(width_scale, height_scale))

    def _display_image_size(self) -> QSize:
        if self.pixmap.isNull():
            return QSize(self.base_viewport_size)

        scale = self._base_scale() * self.zoom_factor
        width = max(1, int(round(self.pixmap.width() * scale)))
        height = max(1, int(round(self.pixmap.height() * scale)))
        return QSize(width, height)

    def _image_rect(self) -> QRect:
        if self.pixmap.isNull():
            return QRect()

        display_size = self._display_image_size()
        x = (self.width() - display_size.width()) // 2
        extra_vertical = self.height() - display_size.height()
        y = CANVAS_MARGIN if extra_vertical > CANVAS_MARGIN * 2 else extra_vertical // 2
        return QRect(x, y, display_size.width(), display_size.height())

    def _view_point_to_image(self, point: QPoint, clamp: bool) -> tuple[int, int] | None:
        rect = self._image_rect()
        if not rect.isValid() or self.pixmap.isNull():
            return None

        if not clamp and not rect.contains(point):
            return None

        if clamp:
            point = QPoint(
                max(rect.left(), min(point.x(), rect.right())),
                max(rect.top(), min(point.y(), rect.bottom())),
            )

        x_ratio = (point.x() - rect.x()) / max(1, rect.width())
        y_ratio = (point.y() - rect.y()) / max(1, rect.height())
        x = max(0, min(self.pixmap.width() - 1, int(x_ratio * self.pixmap.width())))
        y = max(0, min(self.pixmap.height() - 1, int(y_ratio * self.pixmap.height())))
        return x, y

    def _image_point_to_view(self, point: tuple[int, int]) -> QPointF:
        image_rect = self._image_rect()
        if not image_rect.isValid() or self.pixmap.isNull():
            return QPointF()

        x_scale = image_rect.width() / max(1, self.pixmap.width())
        y_scale = image_rect.height() / max(1, self.pixmap.height())
        return QPointF(
            image_rect.x() + point[0] * x_scale,
            image_rect.y() + point[1] * y_scale,
        )

    def _region_to_view_points(self, region: NamedRegion) -> list[QPointF]:
        if self.pixmap.isNull():
            return []
        return [self._image_point_to_view(point) for point in region.normalized_points(self.pixmap.width(), self.pixmap.height())]

    def _region_to_view_path(self, region: NamedRegion) -> QPainterPath:
        points = self._region_to_view_points(region)
        path = QPainterPath()
        if len(points) < 3:
            return path

        path.addPolygon(QPolygonF(points))
        path.closeSubpath()
        return path

    def _hit_test(self, point: QPoint) -> int:
        point_f = QPointF(point)
        for index in range(len(self.regions) - 1, -1, -1):
            path = self._region_to_view_path(self.regions[index])
            if not path.isEmpty() and path.contains(point_f):
                return index
        return -1

    def _is_near_first_polygon_vertex(self, view_point: QPoint) -> bool:
        if len(self.polygon_draft) < 3:
            return False
        first_point = self._image_point_to_view(self.polygon_draft[0])
        return abs(first_point.x() - view_point.x()) <= 12 and abs(first_point.y() - view_point.y()) <= 12

    def _find_scroll_area(self) -> QScrollArea | None:
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                return parent
            parent = parent.parentWidget()
        return None

    def _update_pan(self, global_point: QPoint) -> None:
        if not self.pan_active or self.pan_start_global is None:
            return

        scroll_area = self._find_scroll_area()
        if scroll_area is None:
            return

        delta = global_point - self.pan_start_global
        horizontal = scroll_area.horizontalScrollBar()
        vertical = scroll_area.verticalScrollBar()
        horizontal.setValue(self.pan_start_horizontal - delta.x())
        vertical.setValue(self.pan_start_vertical - delta.y())

    def _stop_pan(self) -> None:
        self.pan_active = False
        self.pan_start_global = None
        self.releaseMouse()
        self.unsetCursor()

    def _reposition_scrollbars(self, global_point: QPoint, anchor_ratio: tuple[float, float]) -> None:
        scroll_area = self._find_scroll_area()
        if scroll_area is None:
            return

        image_rect = self._image_rect()
        if not image_rect.isValid():
            return

        viewport_point = scroll_area.viewport().mapFromGlobal(global_point)
        target_x = int(image_rect.x() + anchor_ratio[0] * image_rect.width() - viewport_point.x())
        target_y = int(image_rect.y() + anchor_ratio[1] * image_rect.height() - viewport_point.y())

        horizontal = scroll_area.horizontalScrollBar()
        vertical = scroll_area.verticalScrollBar()
        horizontal.setValue(max(horizontal.minimum(), min(horizontal.maximum(), target_x)))
        vertical.setValue(max(vertical.minimum(), min(vertical.maximum(), target_y)))


class RegionDetailCanvas(QFrame):
    region_changed = Signal(object)

    def __init__(self, image_path: Path, region: NamedRegion) -> None:
        super().__init__()
        self.image_path = image_path
        self.pixmap = QPixmap(str(image_path))
        self.region = region.copy()
        self.drag_mode: str | None = None
        self.drag_handle = ""
        self.drag_point_index = -1
        self.last_image_point: tuple[int, int] | None = None

        self.setObjectName("detailMaskCanvas")
        self.setMinimumSize(640, 520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self._normalize_region()

    def set_region(self, region: NamedRegion) -> None:
        self.region = region.copy()
        self._normalize_region()
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#17151d"))

        image_rect = self._image_rect()
        if image_rect.isValid() and not self.pixmap.isNull():
            painter.fillRect(image_rect.adjusted(-4, -4, 4, 4), QColor("#262230"))
            painter.drawPixmap(image_rect, self.pixmap)

            region_path = self._region_to_view_path(self.region)
            if not region_path.isEmpty():
                outside_path = QPainterPath()
                outside_path.addRect(QRectF(image_rect))
                outside_path = outside_path.subtracted(region_path)
                painter.fillPath(outside_path, QColor(10, 8, 15, 125))

                painter.setPen(QPen(QColor("#ffebe8"), 2.2))
                painter.setBrush(QColor(255, 53, 53, 108))
                painter.drawPath(region_path)
                self._paint_handles(painter)

        painter.end()
        super().paintEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if self.pixmap.isNull():
            super().mousePressEvent(event)
            return

        view_point = event.position().toPoint()
        if event.button() == Qt.MouseButton.RightButton and self.region.shape_key() == POLYGON_MODE:
            point_index = self._hit_polygon_point(view_point)
            points = list(self.region.normalized_points(*self._image_size()))
            if point_index >= 0 and len(points) > 3:
                del points[point_index]
                self._set_polygon_points(points)
                self._emit_region_changed()
                event.accept()
                return

        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        handle = self._hit_rect_handle(view_point)
        if handle:
            self.drag_mode = "rect_handle"
            self.drag_handle = handle
            event.accept()
            return

        point_index = self._hit_polygon_point(view_point)
        if point_index >= 0:
            self.drag_mode = "polygon_point"
            self.drag_point_index = point_index
            event.accept()
            return

        if self._region_to_view_path(self.region).contains(QPointF(view_point)):
            self.drag_mode = "move"
            self.last_image_point = self._view_point_to_image(view_point, clamp=True)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        view_point = event.position().toPoint()
        image_point = self._view_point_to_image(view_point, clamp=True)

        if self.drag_mode and image_point is not None:
            if self.drag_mode == "rect_handle":
                self._apply_rect_handle(self.drag_handle, image_point)
            elif self.drag_mode == "polygon_point":
                self._apply_polygon_point(self.drag_point_index, image_point)
            elif self.drag_mode == "move" and self.last_image_point is not None:
                dx = image_point[0] - self.last_image_point[0]
                dy = image_point[1] - self.last_image_point[1]
                applied_dx, applied_dy = self._move_region(dx, dy)
                self.last_image_point = (
                    self.last_image_point[0] + applied_dx,
                    self.last_image_point[1] + applied_dy,
                )

            self._emit_region_changed()
            event.accept()
            return

        self._update_hover_cursor(view_point)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self.drag_mode:
            self.drag_mode = None
            self.drag_handle = ""
            self.drag_point_index = -1
            self.last_image_point = None
            self.unsetCursor()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self.region.shape_key() == POLYGON_MODE:
            edge_index = self._hit_polygon_edge(event.position().toPoint())
            image_point = self._view_point_to_image(event.position().toPoint(), clamp=True)
            if edge_index >= 0 and image_point is not None:
                points = list(self.region.normalized_points(*self._image_size()))
                points.insert(edge_index + 1, image_point)
                self._set_polygon_points(points)
                self._emit_region_changed()
                event.accept()
                return

        super().mouseDoubleClickEvent(event)

    def _emit_region_changed(self) -> None:
        self.update()
        self.region_changed.emit(self.region.copy())

    def _image_size(self) -> tuple[int, int]:
        return max(1, self.pixmap.width()), max(1, self.pixmap.height())

    def _normalize_region(self) -> None:
        width, height = self._image_size()
        if self.region.shape_key() == POLYGON_MODE:
            points = self.region.normalized_points(width, height)
            self._set_polygon_points(points, emit=False)
            return

        left, top, right, bottom = self.region.normalized_box(width, height)
        self.region = NamedRegion(
            name=self.region.name,
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            shape=RECT_MODE,
        )

    def _image_rect(self) -> QRect:
        if self.pixmap.isNull():
            return QRect()

        padding = 18
        available_width = max(1, self.width() - padding * 2)
        available_height = max(1, self.height() - padding * 2)
        scale = min(available_width / max(1, self.pixmap.width()), available_height / max(1, self.pixmap.height()))
        width = max(1, int(round(self.pixmap.width() * scale)))
        height = max(1, int(round(self.pixmap.height() * scale)))
        return QRect((self.width() - width) // 2, (self.height() - height) // 2, width, height)

    def _view_point_to_image(self, point: QPoint, clamp: bool) -> tuple[int, int] | None:
        rect = self._image_rect()
        if not rect.isValid() or self.pixmap.isNull():
            return None

        if not clamp and not rect.contains(point):
            return None

        if clamp:
            point = QPoint(
                max(rect.left(), min(point.x(), rect.right())),
                max(rect.top(), min(point.y(), rect.bottom())),
            )

        x_ratio = (point.x() - rect.x()) / max(1, rect.width())
        y_ratio = (point.y() - rect.y()) / max(1, rect.height())
        return (
            max(0, min(self.pixmap.width() - 1, int(x_ratio * self.pixmap.width()))),
            max(0, min(self.pixmap.height() - 1, int(y_ratio * self.pixmap.height()))),
        )

    def _image_point_to_view(self, point: tuple[int, int]) -> QPointF:
        rect = self._image_rect()
        if not rect.isValid() or self.pixmap.isNull():
            return QPointF()

        x_scale = rect.width() / max(1, self.pixmap.width())
        y_scale = rect.height() / max(1, self.pixmap.height())
        return QPointF(rect.x() + point[0] * x_scale, rect.y() + point[1] * y_scale)

    def _region_to_view_path(self, region: NamedRegion) -> QPainterPath:
        path = QPainterPath()
        if self.pixmap.isNull():
            return path

        points = [self._image_point_to_view(point) for point in region.normalized_points(*self._image_size())]
        if len(points) < 3:
            return path

        path.addPolygon(QPolygonF(points))
        path.closeSubpath()
        return path

    def _rect_handle_points(self) -> dict[str, QPointF]:
        if self.region.shape_key() != RECT_MODE:
            return {}

        width, height = self._image_size()
        left, top, right, bottom = self.region.normalized_box(width, height)
        right_point = max(left, right - 1)
        bottom_point = max(top, bottom - 1)
        mid_x = (left + right_point) // 2
        mid_y = (top + bottom_point) // 2
        return {
            "left_top": self._image_point_to_view((left, top)),
            "top": self._image_point_to_view((mid_x, top)),
            "right_top": self._image_point_to_view((right_point, top)),
            "right": self._image_point_to_view((right_point, mid_y)),
            "right_bottom": self._image_point_to_view((right_point, bottom_point)),
            "bottom": self._image_point_to_view((mid_x, bottom_point)),
            "left_bottom": self._image_point_to_view((left, bottom_point)),
            "left": self._image_point_to_view((left, mid_y)),
        }

    def _paint_handles(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor("#ffffff"), 1.4))
        painter.setBrush(QColor("#ff3535"))
        if self.region.shape_key() == RECT_MODE:
            for point in self._rect_handle_points().values():
                painter.drawEllipse(point, 5.2, 5.2)
            return

        for point in self.region.normalized_points(*self._image_size()):
            painter.drawEllipse(self._image_point_to_view(point), 5.2, 5.2)

    def _hit_rect_handle(self, view_point: QPoint) -> str:
        if self.region.shape_key() != RECT_MODE:
            return ""

        for name, point in self._rect_handle_points().items():
            if abs(point.x() - view_point.x()) <= 11 and abs(point.y() - view_point.y()) <= 11:
                return name
        return ""

    def _hit_polygon_point(self, view_point: QPoint) -> int:
        if self.region.shape_key() != POLYGON_MODE:
            return -1

        for index, point in enumerate(self.region.normalized_points(*self._image_size())):
            view = self._image_point_to_view(point)
            if abs(view.x() - view_point.x()) <= 11 and abs(view.y() - view_point.y()) <= 11:
                return index
        return -1

    def _hit_polygon_edge(self, view_point: QPoint) -> int:
        points = self.region.normalized_points(*self._image_size())
        if self.region.shape_key() != POLYGON_MODE or len(points) < 3:
            return -1

        view_points = [self._image_point_to_view(point) for point in points]
        target = QPointF(view_point)
        best_index = -1
        best_distance = 14.0
        for index, start in enumerate(view_points):
            end = view_points[(index + 1) % len(view_points)]
            distance = self._distance_to_segment(target, start, end)
            if distance < best_distance:
                best_distance = distance
                best_index = index
        return best_index

    def _distance_to_segment(self, point: QPointF, start: QPointF, end: QPointF) -> float:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length_sq = dx * dx + dy * dy
        if length_sq <= 0.0001:
            return math.hypot(point.x() - start.x(), point.y() - start.y())

        t = max(0.0, min(1.0, ((point.x() - start.x()) * dx + (point.y() - start.y()) * dy) / length_sq))
        projection = QPointF(start.x() + t * dx, start.y() + t * dy)
        return math.hypot(point.x() - projection.x(), point.y() - projection.y())

    def _apply_rect_handle(self, handle: str, point: tuple[int, int]) -> None:
        width, height = self._image_size()
        left, top, right, bottom = self.region.normalized_box(width, height)
        min_size = 8
        x, y = point

        if "left" in handle:
            left = min(max(0, x), right - min_size)
        if "right" in handle:
            right = max(min(width, x + 1), left + min_size)
        if "top" in handle:
            top = min(max(0, y), bottom - min_size)
        if "bottom" in handle:
            bottom = max(min(height, y + 1), top + min_size)

        self.region = NamedRegion(self.region.name, left, top, right, bottom, RECT_MODE)

    def _apply_polygon_point(self, point_index: int, point: tuple[int, int]) -> None:
        points = list(self.region.normalized_points(*self._image_size()))
        if not (0 <= point_index < len(points)):
            return

        points[point_index] = point
        if len(set(points)) < 3:
            return
        self._set_polygon_points(points)

    def _move_region(self, dx: int, dy: int) -> tuple[int, int]:
        if dx == 0 and dy == 0:
            return 0, 0

        width, height = self._image_size()
        if self.region.shape_key() == POLYGON_MODE:
            points = self.region.normalized_points(width, height)
            min_x = min(point[0] for point in points)
            max_x = max(point[0] for point in points)
            min_y = min(point[1] for point in points)
            max_y = max(point[1] for point in points)
            dx = max(-min_x, min(dx, width - 1 - max_x))
            dy = max(-min_y, min(dy, height - 1 - max_y))
            self._set_polygon_points([(x + dx, y + dy) for x, y in points])
            return dx, dy

        left, top, right, bottom = self.region.normalized_box(width, height)
        dx = max(-left, min(dx, width - right))
        dy = max(-top, min(dy, height - bottom))
        self.region = NamedRegion(self.region.name, left + dx, top + dy, right + dx, bottom + dy, RECT_MODE)
        return dx, dy

    def _set_polygon_points(self, points: list[tuple[int, int]], emit: bool = True) -> None:
        width, height = self._image_size()
        normalized = [
            (max(0, min(int(x), width - 1)), max(0, min(int(y), height - 1)))
            for x, y in points
        ]
        if len(normalized) < 3:
            return

        xs = [point[0] for point in normalized]
        ys = [point[1] for point in normalized]
        self.region = NamedRegion(
            name=self.region.name,
            left=min(xs),
            top=min(ys),
            right=max(xs) + 1,
            bottom=max(ys) + 1,
            shape=POLYGON_MODE,
            points=tuple(normalized),
        )
        if emit:
            self.update()

    def _update_hover_cursor(self, view_point: QPoint) -> None:
        if self._hit_rect_handle(view_point) or self._hit_polygon_point(view_point):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            return
        if self._region_to_view_path(self.region).contains(QPointF(view_point)):
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        self.unsetCursor()


class RegionDetailDialog(QDialog):
    def __init__(self, image_path: Path, region: NamedRegion, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image_path = image_path
        self.original_region = region.copy()
        self.region = region.copy()
        self._updating_controls = False
        self.pixmap = QPixmap(str(image_path))

        self.setWindowTitle(f"영역 세부 설정 - {region.name}")
        self.resize(1120, 760)

        self._build_ui()
        self._apply_styles()
        self._sync_controls_from_region()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        title = QLabel("영역 세부 설정")
        title.setObjectName("dialogTitle")

        help_text = QLabel("붉은 영역이 처리 후 남길 마스킹 영역입니다. 미리보기에서 영역을 드래그하거나 오른쪽 좌표값으로 정밀하게 수정할 수 있습니다.")
        help_text.setObjectName("helperText")
        help_text.setWordWrap(True)

        body = QHBoxLayout()
        body.setSpacing(16)

        self.mask_canvas = RegionDetailCanvas(self.image_path, self.region)
        self.mask_canvas.region_changed.connect(self._handle_canvas_region_changed)

        side_panel = QFrame()
        side_panel.setObjectName("detailSidePanel")
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(18, 18, 18, 18)
        side_layout.setSpacing(12)

        name_label = QLabel("이름")
        name_label.setObjectName("fieldLabel")
        self.name_input = QLineEdit()
        self.name_input.textChanged.connect(self._handle_name_changed)

        self.shape_label = QLabel("")
        self.shape_label.setObjectName("helperText")
        self.point_label = QLabel("")
        self.point_label.setObjectName("helperText")

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.left_spin = self._create_spin_box()
        self.right_spin = self._create_spin_box()
        self.top_spin = self._create_spin_box()
        self.bottom_spin = self._create_spin_box()
        grid.addWidget(self._field_label("X 시작"), 0, 0)
        grid.addWidget(self.left_spin, 0, 1)
        grid.addWidget(self._field_label("X 끝"), 1, 0)
        grid.addWidget(self.right_spin, 1, 1)
        grid.addWidget(self._field_label("Y 시작"), 2, 0)
        grid.addWidget(self.top_spin, 2, 1)
        grid.addWidget(self._field_label("Y 끝"), 3, 0)
        grid.addWidget(self.bottom_spin, 3, 1)

        reset_button = QPushButton("처음 영역으로 복원")
        reset_button.clicked.connect(self._reset_region)

        side_layout.addWidget(name_label)
        side_layout.addWidget(self.name_input)
        side_layout.addSpacing(4)
        side_layout.addWidget(self.shape_label)
        side_layout.addWidget(self.point_label)
        side_layout.addSpacing(8)
        side_layout.addLayout(grid)
        side_layout.addSpacing(8)
        side_layout.addWidget(reset_button)
        side_layout.addStretch(1)

        body.addWidget(self.mask_canvas, 1)
        body.addWidget(side_panel, 0)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root.addWidget(title)
        root.addWidget(help_text)
        root.addLayout(body, 1)
        root.addWidget(buttons)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #1f1c28;
                color: #f1eff7;
                font-family: "Malgun Gothic";
            }
            #dialogTitle {
                font: 800 22px "Malgun Gothic";
                color: #ffffff;
            }
            #helperText {
                color: #c4bed4;
                font: 500 13px "Malgun Gothic";
            }
            #fieldLabel {
                color: #ffffff;
                font: 700 13px "Malgun Gothic";
            }
            #detailSidePanel {
                background: #262230;
                border: 1px solid #3a3348;
                border-radius: 18px;
                min-width: 300px;
                max-width: 340px;
            }
            #detailMaskCanvas {
                background: #17151d;
                border: 1px solid #393348;
                border-radius: 18px;
            }
            QLineEdit, QSpinBox {
                background: #201c29;
                border: 1px solid #4a435a;
                border-radius: 10px;
                color: #f3f1f9;
                min-height: 34px;
                padding: 0 10px;
            }
            QPushButton {
                background: #302944;
                border: 1px solid #5a4d79;
                border-radius: 12px;
                min-height: 38px;
                color: #ffffff;
                font: 600 14px "Malgun Gothic";
                padding: 0 14px;
            }
            QPushButton:hover {
                background: #3a3153;
            }
            QDialogButtonBox QPushButton {
                min-width: 110px;
            }
            """
        )

    def _create_spin_box(self) -> QSpinBox:
        spin_box = QSpinBox()
        width = max(1, self.pixmap.width())
        height = max(1, self.pixmap.height())
        spin_box.setRange(0, max(width, height))
        spin_box.valueChanged.connect(self._handle_spin_changed)
        return spin_box

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _sync_controls_from_region(self) -> None:
        width = max(1, self.pixmap.width())
        height = max(1, self.pixmap.height())
        left, top, right, bottom = self.region.normalized_box(width, height)
        shape_label = "다각형" if self.region.shape_key() == POLYGON_MODE else "사각형"
        point_count = len(self.region.points) if self.region.shape_key() == POLYGON_MODE else 4

        self._updating_controls = True
        self.name_input.setText(self.region.name)
        self.left_spin.setRange(0, max(0, width - 1))
        self.right_spin.setRange(1, width)
        self.top_spin.setRange(0, max(0, height - 1))
        self.bottom_spin.setRange(1, height)
        self.left_spin.setValue(left)
        self.right_spin.setValue(right)
        self.top_spin.setValue(top)
        self.bottom_spin.setValue(bottom)
        self.shape_label.setText(f"형태: {shape_label}")
        self.point_label.setText(f"점 개수: {point_count}")
        self._updating_controls = False

    def _handle_canvas_region_changed(self, region: NamedRegion) -> None:
        self.region = region.copy()
        self._sync_controls_from_region()

    def _handle_name_changed(self, text: str) -> None:
        if self._updating_controls:
            return

        self.region.name = text.strip() or "region"
        self.mask_canvas.set_region(self.region)

    def _handle_spin_changed(self) -> None:
        if self._updating_controls:
            return

        left = self.left_spin.value()
        right = self.right_spin.value()
        top = self.top_spin.value()
        bottom = self.bottom_spin.value()
        if right <= left:
            right = left + 1
        if bottom <= top:
            bottom = top + 1

        width = max(1, self.pixmap.width())
        height = max(1, self.pixmap.height())
        right = min(width, right)
        bottom = min(height, bottom)

        self.region = self._region_resized_to_box(self.region, left, top, right, bottom)
        self.mask_canvas.set_region(self.region)
        self._sync_controls_from_region()

    def _region_resized_to_box(self, region: NamedRegion, left: int, top: int, right: int, bottom: int) -> NamedRegion:
        if region.shape_key() != POLYGON_MODE:
            return NamedRegion(region.name, left, top, right, bottom, RECT_MODE)

        width = max(1, self.pixmap.width())
        height = max(1, self.pixmap.height())
        old_left, old_top, old_right, old_bottom = region.normalized_box(width, height)
        old_width = max(1, old_right - old_left - 1)
        old_height = max(1, old_bottom - old_top - 1)
        new_width = max(1, right - left - 1)
        new_height = max(1, bottom - top - 1)
        points = []
        for x, y in region.normalized_points(width, height):
            x_ratio = (x - old_left) / old_width
            y_ratio = (y - old_top) / old_height
            points.append((int(round(left + x_ratio * new_width)), int(round(top + y_ratio * new_height))))

        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return NamedRegion(
            name=region.name,
            left=min(xs),
            top=min(ys),
            right=max(xs) + 1,
            bottom=max(ys) + 1,
            shape=POLYGON_MODE,
            points=tuple(points),
        )

    def _reset_region(self) -> None:
        self.region = self.original_region.copy()
        self.mask_canvas.set_region(self.region)
        self._sync_controls_from_region()

    def result_region(self) -> NamedRegion:
        name = self.name_input.text().strip() or self.region.name.strip() or "region"
        self.region.name = name
        return self.region.copy()


class RegionEditorDialog(QDialog):
    def __init__(self, image_path: Path, regions: list[NamedRegion] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image_path = image_path
        self.regions: list[NamedRegion] = [region.copy() for region in (regions or [])]

        self.setWindowTitle(f"영역 편집 - {image_path.name}")
        self.setModal(True)
        self.resize(1400, 960)

        self._build_ui()
        self._populate_region_list()
        self._set_draw_mode(RECT_MODE)
        self._apply_styles()
        self._update_canvas_viewport_reference()
        QTimer.singleShot(0, self.fit_to_view)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        title = QLabel("영역 편집")
        title.setObjectName("dialogTitle")

        help_text = QLabel("마우스 휠로 확대/축소할 수 있고, 휠 버튼을 누른 채 드래그하면 이동할 수 있습니다. 사각형은 드래그, 다각형은 점을 찍은 뒤 첫 점 클릭 또는 더블클릭으로 완료합니다.")
        help_text.setObjectName("helperText")
        help_text.setWordWrap(True)

        tool_row = QHBoxLayout()
        tool_row.setSpacing(10)

        tool_label = QLabel("선택 도구")
        tool_label.setObjectName("toolLabel")

        self.rect_tool = QToolButton()
        self.rect_tool.setObjectName("toolButton")
        self.rect_tool.setCheckable(True)
        self.rect_tool.setText("사각형")
        self.rect_tool.setIcon(create_tool_icon(RECT_MODE))
        self.rect_tool.setIconSize(QSize(22, 22))
        self.rect_tool.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self.polygon_tool = QToolButton()
        self.polygon_tool.setObjectName("toolButton")
        self.polygon_tool.setCheckable(True)
        self.polygon_tool.setText("다각형")
        self.polygon_tool.setIcon(create_tool_icon(POLYGON_MODE))
        self.polygon_tool.setIconSize(QSize(22, 22))
        self.polygon_tool.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_group.addButton(self.rect_tool)
        self.tool_group.addButton(self.polygon_tool)

        self.rect_tool.clicked.connect(lambda: self._set_draw_mode(RECT_MODE))
        self.polygon_tool.clicked.connect(lambda: self._set_draw_mode(POLYGON_MODE))

        cancel_draft_button = QPushButton("현재 그리기 취소")
        cancel_draft_button.clicked.connect(self.canvas_cancel_draft)

        fit_button = QPushButton("맞춤 보기")
        fit_button.clicked.connect(self.fit_to_view)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("zoomChip")

        self.mode_hint = QLabel("")
        self.mode_hint.setObjectName("helperText")
        self.mode_hint.setWordWrap(True)

        tool_row.addWidget(tool_label)
        tool_row.addWidget(self.rect_tool)
        tool_row.addWidget(self.polygon_tool)
        tool_row.addWidget(self.zoom_label)
        tool_row.addStretch(1)
        tool_row.addWidget(fit_button)
        tool_row.addWidget(cancel_draft_button)

        row = QHBoxLayout()
        row.setSpacing(18)

        self.canvas = RegionCanvas(self.image_path, self.regions)
        self.canvas.region_created.connect(self._handle_region_created)
        self.canvas.region_selected.connect(self._select_region)
        self.canvas.zoom_changed.connect(self._update_zoom_label)

        self.canvas_scroll = QScrollArea()
        self.canvas_scroll.setObjectName("canvasScrollArea")
        self.canvas_scroll.setWidget(self.canvas)
        self.canvas_scroll.setWidgetResizable(False)
        self.canvas_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.canvas_scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        side_panel = QFrame()
        side_panel.setObjectName("sidePanel")
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(18, 18, 18, 18)
        side_layout.setSpacing(14)

        panel_title = QLabel("영역 목록")
        panel_title.setObjectName("panelTitle")

        self.region_list = QListWidget()
        self.region_list.currentRowChanged.connect(self._select_region)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("영역 이름")
        self.name_input.textChanged.connect(self._rename_selected_region)

        name_label = QLabel("이름")
        name_label.setObjectName("fieldLabel")

        self.region_detail_button = QPushButton("영역 세부 설정")
        self.region_detail_button.setObjectName("detailButton")
        self.region_detail_button.clicked.connect(self._show_region_detail_settings)
        self.region_detail_button.setEnabled(False)

        self.coordinate_label = QLabel("선택된 영역 없음")
        self.coordinate_label.setObjectName("helperText")
        self.coordinate_label.setWordWrap(True)

        delete_button = QPushButton("선택 영역 삭제")
        delete_button.clicked.connect(self._delete_selected_region)

        clear_button = QPushButton("전체 삭제")
        clear_button.clicked.connect(self._clear_regions)

        side_layout.addWidget(panel_title)
        side_layout.addWidget(self.region_list, 1)
        side_layout.addWidget(name_label)
        side_layout.addWidget(self.name_input)
        side_layout.addWidget(self.region_detail_button)
        side_layout.addWidget(self.coordinate_label)
        side_layout.addWidget(delete_button)
        side_layout.addWidget(clear_button)
        side_layout.addStretch(1)

        row.addWidget(self.canvas_scroll, 1)
        row.addWidget(side_panel, 0)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_with_validation)
        buttons.rejected.connect(self.reject)

        root.addWidget(title)
        root.addWidget(help_text)
        root.addLayout(tool_row)
        root.addWidget(self.mode_hint)
        root.addLayout(row, 1)
        root.addWidget(buttons)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._update_canvas_viewport_reference()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #1f1c28;
                color: #f1eff7;
                font-family: "Malgun Gothic";
            }
            #dialogTitle {
                font: 800 22px "Malgun Gothic";
                color: #ffffff;
            }
            #toolLabel, #panelTitle {
                font: 700 16px "Malgun Gothic";
                color: #ffffff;
            }
            #helperText {
                color: #c4bed4;
                font: 500 13px "Malgun Gothic";
            }
            #fieldLabel {
                color: #ffffff;
                font: 700 13px "Malgun Gothic";
            }
            #zoomChip {
                background: #2a2537;
                border: 1px solid #50486a;
                border-radius: 12px;
                color: #ffffff;
                font: 700 13px "Malgun Gothic";
                padding: 7px 12px;
            }
            QScrollArea#canvasScrollArea {
                background: #17151d;
                border: 1px solid #393348;
                border-radius: 18px;
            }
            QScrollArea#canvasScrollArea > QWidget > QWidget {
                background: #17151d;
            }
            #regionCanvas {
                background: #17151d;
                border: none;
                border-radius: 18px;
            }
            #sidePanel {
                background: #262230;
                border: 1px solid #3a3348;
                border-radius: 18px;
                min-width: 320px;
            }
            QListWidget, QLineEdit {
                background: #201c29;
                border: 1px solid #4a435a;
                border-radius: 12px;
                color: #f3f1f9;
            }
            QListWidget::item {
                padding: 10px 12px;
                border-bottom: 1px solid #342d42;
            }
            QListWidget::item:selected {
                background: #493d6c;
            }
            QLineEdit {
                min-height: 36px;
                padding: 0 12px;
            }
            QPushButton, QToolButton#toolButton {
                background: #302944;
                border: 1px solid #5a4d79;
                border-radius: 12px;
                min-height: 38px;
                color: #ffffff;
                font: 600 14px "Malgun Gothic";
                padding: 0 14px;
            }
            QPushButton:hover, QToolButton#toolButton:hover {
                background: #3a3153;
            }
            QPushButton:disabled {
                background: #241f30;
                border-color: #3a3348;
                color: #777085;
            }
            QPushButton#detailButton {
                margin-top: 2px;
                margin-bottom: 2px;
            }
            QToolButton#toolButton {
                min-width: 118px;
            }
            QToolButton#toolButton:checked {
                background: #5f4a98;
                border-color: #8e74da;
            }
            QDialogButtonBox QPushButton {
                min-width: 110px;
            }
            """
        )

    def canvas_cancel_draft(self) -> None:
        self.canvas.cancel_draft()

    def _set_draw_mode(self, mode: str) -> None:
        is_polygon = mode == POLYGON_MODE
        self.rect_tool.setChecked(not is_polygon)
        self.polygon_tool.setChecked(is_polygon)
        self.canvas.set_draw_mode(mode)
        self.mode_hint.setText(
            "사각형 모드: 드래그해서 한 번에 영역을 만듭니다."
            if not is_polygon
            else "다각형 모드: 클릭으로 점 추가, 첫 점 클릭 또는 더블클릭으로 완료합니다. 우클릭은 마지막 점 취소입니다."
        )

    def _update_zoom_label(self, zoom_factor: float) -> None:
        self.zoom_label.setText(f"{int(round(zoom_factor * 100))}%")

    def _update_canvas_viewport_reference(self) -> None:
        viewport_size = self.canvas_scroll.viewport().size()
        if viewport_size.width() > 0 and viewport_size.height() > 0:
            self.canvas.set_base_viewport_size(viewport_size)

    def fit_to_view(self) -> None:
        self._update_canvas_viewport_reference()
        self.canvas.set_zoom_factor(1.0)
        self.canvas.refresh()
        self.canvas_scroll.horizontalScrollBar().setValue(self.canvas_scroll.horizontalScrollBar().minimum())
        self.canvas_scroll.verticalScrollBar().setValue(self.canvas_scroll.verticalScrollBar().minimum())

    def _populate_region_list(self) -> None:
        current_row = self.region_list.currentRow()
        self.region_list.blockSignals(True)
        self.region_list.clear()
        for region in self.regions:
            self.region_list.addItem(QListWidgetItem(self._region_item_text(region)))
        self.region_list.blockSignals(False)

        if self.regions:
            next_row = min(max(current_row, 0), len(self.regions) - 1)
            self.region_list.setCurrentRow(next_row)
            self._select_region(next_row)
        else:
            self._select_region(-1)

    def _region_item_text(self, region: NamedRegion) -> str:
        shape_label = "다각형" if region.shape_key() == POLYGON_MODE else "사각형"
        return f"[{shape_label}] {region.name}"

    def _region_detail_text(self, region: NamedRegion) -> str:
        shape_label = "다각형" if region.shape_key() == POLYGON_MODE else "사각형"
        point_count = len(region.points) if region.shape_key() == POLYGON_MODE else 4
        return (
            f"이름: {region.name}\n"
            f"형태: {shape_label}\n"
            f"점 개수: {point_count}\n"
            f"x: {region.left} - {region.right}\n"
            f"y: {region.top} - {region.bottom}"
        )

    def _handle_region_created(self, region: NamedRegion) -> None:
        self.regions.append(region)
        self._populate_region_list()
        self.region_list.setCurrentRow(len(self.regions) - 1)
        self.canvas.refresh()

    def _select_region(self, index: int) -> None:
        self.canvas.set_selected_index(index)
        self.region_list.blockSignals(True)
        if 0 <= index < self.region_list.count():
            self.region_list.setCurrentRow(index)
        else:
            self.region_list.clearSelection()
        self.region_list.blockSignals(False)

        self.name_input.blockSignals(True)
        if 0 <= index < len(self.regions):
            region = self.regions[index]
            self.name_input.setEnabled(True)
            self.region_detail_button.setEnabled(True)
            self.name_input.setText(region.name)
            detail_lines = self._region_detail_text(region).splitlines()
            self.coordinate_label.setText("\n".join(detail_lines[1:]))
        else:
            self.name_input.setEnabled(False)
            self.region_detail_button.setEnabled(False)
            self.name_input.clear()
            self.coordinate_label.setText("선택된 영역 없음")
        self.name_input.blockSignals(False)

    def _show_region_detail_settings(self) -> None:
        index = self.region_list.currentRow()
        if not (0 <= index < len(self.regions)):
            QMessageBox.information(self, "영역 세부 설정", "먼저 영역을 선택해 주세요.")
            return

        dialog = RegionDetailDialog(self.image_path, self.regions[index], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.regions[index] = dialog.result_region()
        self._populate_region_list()
        self.region_list.setCurrentRow(index)
        self.canvas.refresh()

    def _rename_selected_region(self, text: str) -> None:
        index = self.region_list.currentRow()
        if not (0 <= index < len(self.regions)):
            return
        self.regions[index].name = text.strip() or f"region_{index + 1}"
        self.region_list.item(index).setText(self._region_item_text(self.regions[index]))
        self.canvas.refresh()

    def _delete_selected_region(self) -> None:
        index = self.region_list.currentRow()
        if not (0 <= index < len(self.regions)):
            return
        del self.regions[index]
        self._populate_region_list()
        self.canvas.refresh()

    def _clear_regions(self) -> None:
        if not self.regions:
            return
        self.regions.clear()
        self._populate_region_list()
        self.canvas.cancel_draft()
        self.canvas.refresh()

    def _accept_with_validation(self) -> None:
        for index, region in enumerate(self.regions):
            region.name = region.name.strip() or f"region_{index + 1}"

        seen: set[str] = set()
        for region in self.regions:
            key = region.name.lower()
            if key in seen:
                QMessageBox.warning(self, "이름 중복", "영역 이름은 서로 다르게 지정해 주세요.")
                return
            seen.add(key)

        self.accept()

    def result_regions(self) -> list[NamedRegion]:
        return [region.copy() for region in self.regions]
