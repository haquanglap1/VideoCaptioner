"""Aspect-fit video preview with a normalized, explicitly selected subtitle region."""

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPainter, QPen
from PyQt5.QtWidgets import QWidget

from videocaptioner.core.ocr.geometry import Roi


class OcrRegionCanvas(QWidget):
    roi_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QImage()
        self.roi: Roi | None = None
        self.line_anchors: tuple[float, ...] = ()
        self.editable = True
        self.anchor: QPointF | None = None
        self.setMinimumSize(320, 160)

    def set_image(self, png: bytes):
        self.image = QImage.fromData(png)
        self.update()

    def image_rect(self) -> QRectF:
        if self.image.isNull():
            return QRectF()
        scale = min(self.width() / self.image.width(), self.height() / self.image.height())
        width, height = self.image.width() * scale, self.image.height() * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#171d27"))
        rect = self.image_rect()
        if rect.isEmpty():
            painter.setPen(QColor("#ced7e4"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Chọn video và tải ảnh xem trước")
            return
        painter.drawImage(rect, self.image)
        if self.roi and self.editable:
            r = self.roi
            painter.setPen(QPen(QColor("#44c8f5"), 2))
            painter.drawRect(QRectF(rect.x() + r.x * rect.width(), rect.y() + r.y * rect.height(),
                                    r.width * rect.width(), r.height * rect.height()))
            painter.setPen(QPen(QColor("#ffc857"), 2, Qt.PenStyle.DashLine))
            for anchor in self.line_anchors:
                y = rect.y() + (r.y + r.height * anchor) * rect.height()
                painter.drawLine(QPointF(rect.x() + r.x * rect.width(), y),
                                 QPointF(rect.x() + (r.x + r.width) * rect.width(), y))

    def mousePressEvent(self, event):
        if self.editable and event.button() == Qt.MouseButton.LeftButton and self.image_rect().contains(event.pos()):
            self.anchor = QPointF(event.pos())

    def mouseMoveEvent(self, event):
        if self.anchor is None:
            return
        rect = self.image_rect()
        point = QPointF(max(rect.left(), min(event.x(), rect.right())),
                        max(rect.top(), min(event.y(), rect.bottom())))
        selected = QRectF(self.anchor, point).normalized()
        if selected.width() >= 2 and selected.height() >= 2:
            self.roi = Roi((selected.x() - rect.x()) / rect.width(), (selected.y() - rect.y()) / rect.height(),
                           selected.width() / rect.width(), selected.height() / rect.height())
            self.roi_changed.emit(self.roi)
            self.update()

    def mouseReleaseEvent(self, event):
        self.mouseMoveEvent(event)
        self.anchor = None
