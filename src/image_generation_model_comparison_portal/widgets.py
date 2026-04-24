from __future__ import annotations

import base64
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from image_generation_model_comparison_portal.models import BoundingBox, CvResult, DIM_KEYS, DIM_LABELS, EvalResult, ModelConfig, MODEL_OPTIONS
from image_generation_model_comparison_portal.services import pretty_json


class ImagePreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._boxes: list[BoundingBox] = []
        self.setMinimumHeight(280)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def clear(self) -> None:
        self._pixmap = None
        self._boxes = []
        self.update()

    def set_image_bytes(self, image_bytes: bytes) -> None:
        pixmap = QPixmap()
        pixmap.loadFromData(image_bytes)
        self._pixmap = pixmap
        self.update()

    def set_boxes(self, boxes: list[BoundingBox]) -> None:
        self._boxes = boxes
        self.update()

    def current_image_bytes(self) -> bytes | None:
        if self._pixmap is None:
            return None
        buffer = self._pixmap.toImage().bits()
        return bytes(buffer)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#09111f"))
        if self._pixmap is None or self._pixmap.isNull():
            painter.setPen(QColor("#7f8ca3"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Waiting for image")
            return
        target = self._scaled_target_rect()
        painter.drawPixmap(target, self._pixmap)
        if not self._boxes:
            return
        scale_x = target.width() / self._pixmap.width()
        scale_y = target.height() / self._pixmap.height()
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        for box in self._boxes:
            rect = QRectF(
                target.x() + box.x * scale_x,
                target.y() + box.y * scale_y,
                max(1.0, box.w * scale_x),
                max(1.0, box.h * scale_y),
            )
            painter.setPen(QPen(QColor("#00e5ff"), 2))
            painter.setBrush(QColor(0, 229, 255, 28))
            painter.drawRoundedRect(rect, 6, 6)
            label = f"{box.label} {box.confidence * 100:.0f}%"
            text_rect = QRectF(rect.x(), max(target.y(), rect.y() - 22), min(180.0, rect.width() + 16), 20)
            painter.fillRect(text_rect, QColor(0, 229, 255, 190))
            painter.setPen(QColor("#041019"))
            painter.drawText(text_rect.adjusted(6, 0, -4, 0), Qt.AlignVCenter | Qt.AlignLeft, label)

    def _scaled_target_rect(self) -> QRectF:
        assert self._pixmap is not None
        pixmap_size = self._pixmap.size()
        scaled = pixmap_size.scaled(self.size(), Qt.KeepAspectRatio)
        x = (self.width() - scaled.width()) / 2
        y = (self.height() - scaled.height()) / 2
        return QRectF(x, y, float(scaled.width()), float(scaled.height()))


class ModelRow(QWidget):
    remove_requested = Signal(QWidget)

    def __init__(self, config: ModelConfig | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.enabled = QCheckBox("Use")
        self.name = QLineEdit()
        self.kind = QComboBox()
        self.deployment = QLineEdit()
        self.remove_button = QPushButton("Remove")
        self._build_ui()
        self.kind.currentIndexChanged.connect(self._sync_name_placeholder)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        self.set_config(config or ModelConfig())

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.name.setPlaceholderText("Name")
        self.deployment.setPlaceholderText("Deployment")
        self.kind.setMinimumWidth(180)
        for value, label in MODEL_OPTIONS:
            self.kind.addItem(label, value)
        layout.addWidget(self.enabled)
        layout.addWidget(self.name, 1)
        layout.addWidget(self.kind, 1)
        layout.addWidget(self.deployment, 1)
        layout.addWidget(self.remove_button)

    def _sync_name_placeholder(self) -> None:
        if self.name.text().strip():
            return
        self.name.setPlaceholderText(self.kind.currentText())

    def set_config(self, config: ModelConfig) -> None:
        self.enabled.setChecked(config.enabled)
        self.name.setText(config.name)
        index = self.kind.findData(config.kind)
        if index >= 0:
            self.kind.setCurrentIndex(index)
        self.deployment.setText(config.deployment)
        self._sync_name_placeholder()

    def get_config(self) -> ModelConfig:
        name = self.name.text().strip() or self.kind.currentText()
        return ModelConfig(
            enabled=self.enabled.isChecked(),
            name=name,
            kind=str(self.kind.currentData()),
            deployment=self.deployment.text().strip(),
        )


class ResultCard(QFrame):
    eval_requested = Signal(str)

    def __init__(self, model: ModelConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.image_bytes: bytes | None = None
        self.download_path: str | None = None
        self.setObjectName("resultCard")
        self.title = QLabel(model.name)
        self.meta = QLabel(f"{model.kind} | {model.deployment or '-'}")
        self.state = QLabel("Queued...")
        self.metrics = QLabel("")
        self.preview = ImagePreview()
        self.download_btn = QPushButton("Download")
        self.eval_btn = QPushButton("Eval")
        self.json_btn = QPushButton("JSON")
        self.cv_label = QLabel("CV pending")
        self.eval_label = QLabel("Evaluation pending")
        self.json_panel = QWidget()
        self.gen_json = QPlainTextEdit()
        self.cv_json = QPlainTextEdit()
        self.eval_json = QPlainTextEdit()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.title.setObjectName("cardTitle")
        self.meta.setObjectName("muted")
        self.state.setObjectName("stateLabel")
        self.metrics.setObjectName("muted")
        self.metrics.setWordWrap(True)
        self.cv_label.setWordWrap(True)
        self.eval_label.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.meta)
        layout.addWidget(self.state)
        layout.addWidget(self.metrics)
        layout.addWidget(self.preview)
        actions = QHBoxLayout()
        actions.addWidget(self.download_btn)
        actions.addWidget(self.eval_btn)
        actions.addWidget(self.json_btn)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addWidget(QLabel("Vision"))
        layout.addWidget(self.cv_label)
        layout.addWidget(QLabel("Evaluation"))
        layout.addWidget(self.eval_label)
        self.json_panel.setVisible(False)
        json_layout = QGridLayout(self.json_panel)
        json_layout.addWidget(QLabel("Generation JSON"), 0, 0)
        json_layout.addWidget(QLabel("CV JSON"), 0, 1)
        json_layout.addWidget(QLabel("Eval JSON"), 0, 2)
        for editor in (self.gen_json, self.cv_json, self.eval_json):
            editor.setReadOnly(True)
            editor.setMinimumHeight(180)
        json_layout.addWidget(self.gen_json, 1, 0)
        json_layout.addWidget(self.cv_json, 1, 1)
        json_layout.addWidget(self.eval_json, 1, 2)
        layout.addWidget(self.json_panel)
        self.eval_btn.clicked.connect(lambda: self.eval_requested.emit(self.model.name))
        self.json_btn.clicked.connect(lambda: self.json_panel.setVisible(not self.json_panel.isVisible()))
        self.download_btn.clicked.connect(self._download_image)

    def set_status(self, text: str, error: bool = False) -> None:
        self.state.setText(text)
        self.state.setProperty("error", error)
        self.style().unpolish(self.state)
        self.style().polish(self.state)

    def set_metrics(self, elapsed_s: float, usage_text: str) -> None:
        self.metrics.setText(f"Time: {elapsed_s:.2f}s | {usage_text}")

    def set_generation(self, image_b64: str, mime_type: str, payload: dict) -> None:
        self.image_bytes = base64.b64decode(image_b64)
        suffix = ".jpg" if mime_type == "image/jpeg" else ".png"
        self.download_path = f"{self.model.name}{suffix}"
        self.preview.set_image_bytes(self.image_bytes)
        self.gen_json.setPlainText(pretty_json(payload))

    def set_cv(self, result: CvResult) -> None:
        counts = result.object_counts()
        count_text = ", ".join(f"{name} x{count}" for name, count in counts.items()) or "No objects detected"
        tags = ", ".join(f"{name} {confidence * 100:.0f}%" for name, confidence in result.tags[:12]) or "No tags"
        self.cv_label.setText(f"Objects: {count_text}\nTags: {tags}")
        self.preview.set_boxes(result.objects)
        self.cv_json.setPlainText(pretty_json(result.raw_payload))

    def set_eval(self, result: EvalResult) -> None:
        lines = [
            f"Overall: {result.overall_score:.1f}",
            result.summary,
            "",
            "Strengths: " + "; ".join(result.strengths),
            "Weaknesses: " + "; ".join(result.weaknesses),
        ]
        lines.append("")
        for key in DIM_KEYS:
            dimension = result.dimensions[key]
            lines.append(f"{DIM_LABELS[key]}: {dimension.score}/10 | {dimension.note}")
        self.eval_label.setText("\n".join(lines))
        self.eval_json.setPlainText(pretty_json(result.raw_payload))

    def clear_cv(self) -> None:
        self.cv_label.setText("CV pending")
        self.preview.set_boxes([])
        self.cv_json.clear()

    def clear_eval(self) -> None:
        self.eval_label.setText("Evaluation pending")
        self.eval_json.clear()

    def _download_image(self) -> None:
        if not self.image_bytes:
            return
        initial = self.download_path or f"{self.model.name}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Save image", initial, "Images (*.png *.jpg *.jpeg)")
        if not path:
            return
        Path(path).write_bytes(self.image_bytes)
