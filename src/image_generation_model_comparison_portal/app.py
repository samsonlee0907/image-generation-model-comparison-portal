from __future__ import annotations

import base64
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from functools import partial
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QFrame,
    QSpacerItem,
)

from image_generation_model_comparison_portal.config import load_config, save_config
from image_generation_model_comparison_portal.models import (
    AppConfig,
    BENCHMARK_PRESETS,
    DIM_KEYS,
    DIM_LABELS,
    ModelConfig,
    ResultRecord,
    sample_models,
)
from image_generation_model_comparison_portal.services import ApiClient, image_data_url
from image_generation_model_comparison_portal.widgets import ModelRow, ResultCard


class TaskBridge(QObject):
    finished = Signal(int, str, str, object, object)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Image Generation Model Comparison Portal")
        self.resize(1640, 1100)
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.bridge = TaskBridge()
        self.bridge.finished.connect(self._handle_task_result)
        self.active_run_id = 0
        self.current_prompt = ""
        self.current_mode = "text"
        self.pending_generation = 0
        self.pending_cv = 0
        self.pending_eval = 0
        self.result_cards: dict[str, ResultCard] = {}
        self.result_records: dict[str, ResultRecord] = {}
        self.run_order: list[str] = []
        self.source_paths: list[str] = []
        self.mask_path: str | None = None
        self.log_entries: list[str] = []
        self.model_rows: list[ModelRow] = []
        self._build_ui()
        self._apply_theme()
        self._load_initial_config()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QVBoxLayout(hero)
        title = QLabel("Image Generation Model Comparison Portal")
        title.setObjectName("heroTitle")
        subtitle = QLabel(
            "Python-native desktop app for Azure Foundry image generation, CV analysis, concurrent evaluation, and bounding-box overlays."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("muted")
        hero_layout.addWidget(title)
        hero_layout.addWidget(subtitle)
        root.addWidget(hero)

        root.addWidget(self._build_settings_group())
        root.addWidget(self._build_models_group())
        root.addWidget(self._build_workflow_group())
        root.addWidget(self._build_results_group(), 1)
        root.addWidget(self._build_comparison_group())
        root.addWidget(self._build_log_group())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(central)
        self.setCentralWidget(scroll)

    def _build_settings_group(self) -> QWidget:
        group = QGroupBox("Global API Settings")
        layout = QGridLayout(group)
        self.global_endpoint = QLineEdit()
        self.global_secret = QLineEdit()
        self.global_secret.setEchoMode(QLineEdit.Password)
        self.global_auth_type = QComboBox()
        self.global_auth_type.addItems(["apiKey", "bearer"])
        self.gpt_api_version = QLineEdit("2025-04-01-preview")
        self.flux_api_version = QLineEdit("preview")
        self.vision_api_version = QLineEdit("2023-10-01")
        self.eval_deployment = QLineEdit()
        self.auto_eval = QComboBox()
        self.auto_eval.addItems(["yes", "no"])
        self.eval_detail = QComboBox()
        self.eval_detail.addItems(["high", "low"])
        self.cv_enabled = QComboBox()
        self.cv_enabled.addItems(["yes", "no"])
        self.cv_endpoint = QLineEdit()
        self.cv_secret = QLineEdit()
        self.cv_secret.setEchoMode(QLineEdit.Password)
        fields = [
            ("Resource Endpoint", self.global_endpoint, 0, 0),
            ("API Key / Bearer", self.global_secret, 0, 1),
            ("Auth", self.global_auth_type, 1, 0),
            ("GPT API Ver", self.gpt_api_version, 1, 1),
            ("FLUX API Ver", self.flux_api_version, 1, 2),
            ("Vision API Ver", self.vision_api_version, 1, 3),
            ("Evaluator LLM", self.eval_deployment, 2, 0),
            ("Auto Eval", self.auto_eval, 2, 1),
            ("Eval Detail", self.eval_detail, 2, 2),
            ("CV Enabled", self.cv_enabled, 2, 3),
            ("CV Endpoint", self.cv_endpoint, 3, 0),
            ("CV API Key", self.cv_secret, 3, 1),
        ]
        for label_text, widget, row, col in fields:
            wrapper = QVBoxLayout()
            label = QLabel(label_text)
            label.setObjectName("fieldLabel")
            holder = QWidget()
            holder_layout = QVBoxLayout(holder)
            holder_layout.setContentsMargins(0, 0, 0, 0)
            holder_layout.setSpacing(6)
            holder_layout.addWidget(label)
            holder_layout.addWidget(widget)
            layout.addWidget(holder, row, col)
        return group

    def _build_models_group(self) -> QWidget:
        group = QGroupBox("Models")
        layout = QVBoxLayout(group)
        toolbar = QHBoxLayout()
        self.add_model_btn = QPushButton("Add")
        self.load_sample_btn = QPushButton("Sample")
        self.save_config_btn = QPushButton("Save")
        self.clear_config_btn = QPushButton("Clear")
        toolbar.addWidget(self.add_model_btn)
        toolbar.addWidget(self.load_sample_btn)
        toolbar.addWidget(self.save_config_btn)
        toolbar.addWidget(self.clear_config_btn)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.model_list = QWidget()
        self.model_list_layout = QVBoxLayout(self.model_list)
        self.model_list_layout.setContentsMargins(0, 0, 0, 0)
        self.model_list_layout.setSpacing(8)
        self.model_list_layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))
        layout.addWidget(self.model_list)
        self.add_model_btn.clicked.connect(lambda: self._add_model_row())
        self.load_sample_btn.clicked.connect(self._load_sample_models)
        self.save_config_btn.clicked.connect(self._save_config)
        self.clear_config_btn.clicked.connect(self._clear_config)
        return group

    def _build_workflow_group(self) -> QWidget:
        group = QGroupBox("Workflows")
        layout = QVBoxLayout(group)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_text_tab(), "Text to Image")
        self.tabs.addTab(self._build_edit_tab(), "Image Edit")
        layout.addWidget(self.tabs)
        return group

    def _build_text_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        bench_box = QFrame()
        bench_box.setObjectName("benchBox")
        bench_layout = QVBoxLayout(bench_box)
        bench_title = QLabel("Benchmark Builder")
        bench_title.setObjectName("cardTitle")
        self.bench_idea = QLineEdit()
        self.bench_idea.setPlaceholderText('e.g. "cyberpunk sushi bar"')
        buttons = QHBoxLayout()
        self.gen_bench_btn = QPushButton("Generate Benchmark")
        self.watchmaker_btn = QPushButton("Watchmaker")
        self.neon_btn = QPushButton("Neon Ramen")
        buttons.addWidget(self.gen_bench_btn)
        buttons.addWidget(self.watchmaker_btn)
        buttons.addWidget(self.neon_btn)
        buttons.addStretch(1)
        self.bench_status = QLabel("")
        self.bench_annotation = QTextEdit()
        self.bench_annotation.setReadOnly(True)
        self.bench_annotation.setMinimumHeight(120)
        bench_layout.addWidget(bench_title)
        bench_layout.addWidget(self.bench_idea)
        bench_layout.addLayout(buttons)
        bench_layout.addWidget(self.bench_status)
        bench_layout.addWidget(self.bench_annotation)
        layout.addWidget(bench_box)

        self.text_prompt = QTextEdit()
        self.text_prompt.setMinimumHeight(180)
        self.text_size = QComboBox()
        self.text_size.addItems(["1024x1024", "1024x1536", "1536x1024", "auto"])
        self.text_quality = QComboBox()
        self.text_quality.addItems(["high", "medium", "low"])
        self.output_format = QComboBox()
        self.output_format.addItems(["png", "jpeg"])
        controls = QGridLayout()
        controls.addWidget(QLabel("Prompt"), 0, 0, 1, 3)
        controls.addWidget(self.text_prompt, 1, 0, 1, 3)
        controls.addWidget(QLabel("Size"), 2, 0)
        controls.addWidget(QLabel("Quality"), 2, 1)
        controls.addWidget(QLabel("Format"), 2, 2)
        controls.addWidget(self.text_size, 3, 0)
        controls.addWidget(self.text_quality, 3, 1)
        controls.addWidget(self.output_format, 3, 2)
        layout.addLayout(controls)
        self.run_text_btn = QPushButton("Generate and Compare")
        layout.addWidget(self.run_text_btn)

        self.gen_bench_btn.clicked.connect(self._generate_benchmark)
        self.watchmaker_btn.clicked.connect(partial(self._load_benchmark_preset, "watchmaker"))
        self.neon_btn.clicked.connect(partial(self._load_benchmark_preset, "neon_ramen"))
        self.run_text_btn.clicked.connect(lambda: self._start_run("text"))
        return page

    def _build_edit_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.edit_prompt = QTextEdit()
        self.edit_prompt.setMinimumHeight(140)
        layout.addWidget(QLabel("Edit Prompt"))
        layout.addWidget(self.edit_prompt)
        picker_row = QHBoxLayout()
        self.pick_sources_btn = QPushButton("Pick Source Images")
        self.pick_mask_btn = QPushButton("Pick Mask")
        self.clear_mask_btn = QPushButton("Clear Mask")
        picker_row.addWidget(self.pick_sources_btn)
        picker_row.addWidget(self.pick_mask_btn)
        picker_row.addWidget(self.clear_mask_btn)
        picker_row.addStretch(1)
        layout.addLayout(picker_row)
        self.source_label = QLabel("No source images selected")
        self.mask_label = QLabel("No mask selected")
        self.edit_size = QComboBox()
        self.edit_size.addItems(["1024x1024", "1024x1536", "1536x1024"])
        layout.addWidget(self.source_label)
        layout.addWidget(self.mask_label)
        layout.addWidget(QLabel("Edit Size"))
        layout.addWidget(self.edit_size)
        self.run_edit_btn = QPushButton("Generate Edit and Compare")
        layout.addWidget(self.run_edit_btn)
        self.pick_sources_btn.clicked.connect(self._pick_sources)
        self.pick_mask_btn.clicked.connect(self._pick_mask)
        self.clear_mask_btn.clicked.connect(self._clear_mask)
        self.run_edit_btn.clicked.connect(lambda: self._start_run("edit"))
        return page

    def _build_results_group(self) -> QWidget:
        group = QGroupBox("Results")
        layout = QVBoxLayout(group)
        top = QHBoxLayout()
        self.re_eval_btn = QPushButton("Re-Evaluate")
        self.re_eval_btn.setEnabled(False)
        self.global_status = QLabel("")
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        top.addWidget(self.re_eval_btn)
        top.addStretch(1)
        top.addWidget(self.global_status)
        layout.addLayout(top)
        layout.addWidget(self.progress)
        self.results_host = QWidget()
        self.results_layout = QVBoxLayout(self.results_host)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(12)
        self.results_layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))
        layout.addWidget(self.results_host)
        self.re_eval_btn.clicked.connect(self._re_evaluate)
        return group

    def _build_comparison_group(self) -> QWidget:
        group = QGroupBox("Comparison")
        layout = QVBoxLayout(group)
        self.comparison_table = QPlainTextEdit()
        self.comparison_table.setReadOnly(True)
        self.comparison_table.setMinimumHeight(220)
        layout.addWidget(self.comparison_table)
        return group

    def _build_log_group(self) -> QWidget:
        group = QGroupBox("Error Log")
        layout = QVBoxLayout(group)
        buttons = QHBoxLayout()
        self.copy_log_btn = QPushButton("Copy")
        self.clear_log_btn = QPushButton("Clear")
        self.log_badge = QLabel("0")
        self.log_badge.setObjectName("badge")
        buttons.addWidget(self.copy_log_btn)
        buttons.addWidget(self.clear_log_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.log_badge)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(180)
        layout.addLayout(buttons)
        layout.addWidget(self.log_view)
        self.copy_log_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.log_view.toPlainText()))
        self.clear_log_btn.clicked.connect(self._clear_log_view)
        return group

    def _apply_theme(self) -> None:
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#071018"))
        palette.setColor(QPalette.Base, QColor("#0c1624"))
        palette.setColor(QPalette.AlternateBase, QColor("#0f1c2d"))
        palette.setColor(QPalette.Text, QColor("#d8e8ff"))
        palette.setColor(QPalette.WindowText, QColor("#d8e8ff"))
        palette.setColor(QPalette.Button, QColor("#112030"))
        palette.setColor(QPalette.ButtonText, QColor("#d8e8ff"))
        palette.setColor(QPalette.Highlight, QColor("#00e5ff"))
        palette.setColor(QPalette.HighlightedText, QColor("#02131a"))
        self.setPalette(palette)
        self.setStyleSheet(
            """
            QMainWindow, QScrollArea, QWidget { background: #071018; color: #d8e8ff; }
            QGroupBox, QFrame#hero, QFrame#benchBox, QFrame#resultCard {
              border: 1px solid #183247;
              border-radius: 14px;
              background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0d1826, stop:1 #0a1220);
            }
            QGroupBox {
              margin-top: 14px;
              padding-top: 16px;
              font-weight: 700;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #6df2ff; }
            QLabel#heroTitle { font-size: 22px; font-weight: 800; color: #6df2ff; }
            QLabel#cardTitle { font-size: 16px; font-weight: 700; color: #f4f7ff; }
            QLabel#muted { color: #7f9ab3; }
            QLabel#fieldLabel { color: #8db4d6; font-size: 12px; font-weight: 700; }
            QLabel#badge {
              background: #ff3f81;
              color: white;
              border-radius: 10px;
              padding: 3px 10px;
              font-weight: 700;
            }
            QLabel[error="true"] { color: #ff7f9a; }
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
              background: #0c1624;
              border: 1px solid #21415a;
              border-radius: 10px;
              padding: 8px;
              color: #d8e8ff;
              selection-background-color: #00e5ff;
              selection-color: #041019;
            }
            QPushButton {
              background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #00d1ff, stop:1 #0087ff);
              color: #041019;
              font-weight: 800;
              border: none;
              border-radius: 10px;
              padding: 10px 14px;
            }
            QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #34e7ff, stop:1 #16a3ff); }
            QPushButton:disabled { background: #203245; color: #8ca2ba; }
            QTabWidget::pane { border: 1px solid #183247; border-radius: 10px; }
            QTabBar::tab {
              background: #0b1422;
              color: #9ec4e2;
              padding: 10px 14px;
              margin-right: 4px;
              border-top-left-radius: 10px;
              border-top-right-radius: 10px;
            }
            QTabBar::tab:selected { background: #14253b; color: #6df2ff; }
            QProgressBar {
              border: 1px solid #21415a;
              background: #0a1220;
              border-radius: 8px;
              text-align: center;
            }
            QProgressBar::chunk {
              border-radius: 8px;
              background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #00e5ff, stop:1 #ff3f81);
            }
            """
        )

    def _load_initial_config(self) -> None:
        config = load_config()
        if config is None:
            config = AppConfig(models=sample_models())
        self._apply_config(config)

    def _apply_config(self, config: AppConfig) -> None:
        self.global_endpoint.setText(config.global_endpoint)
        self.global_secret.setText(config.global_secret)
        self.global_auth_type.setCurrentText(config.global_auth_type)
        self.gpt_api_version.setText(config.gpt_api_version)
        self.flux_api_version.setText(config.flux_api_version)
        self.vision_api_version.setText(config.vision_api_version)
        self.cv_endpoint.setText(config.cv_endpoint)
        self.cv_secret.setText(config.cv_secret)
        self.eval_deployment.setText(config.eval_deployment)
        self.auto_eval.setCurrentText(config.auto_eval)
        self.eval_detail.setCurrentText(config.eval_detail)
        self.cv_enabled.setCurrentText(config.cv_enabled)
        self._clear_model_rows()
        for model in config.models or sample_models():
            self._add_model_row(model)

    def _collect_config(self) -> AppConfig:
        return AppConfig(
            global_endpoint=self.global_endpoint.text().strip(),
            global_secret=self.global_secret.text().strip(),
            global_auth_type=self.global_auth_type.currentText(),
            gpt_api_version=self.gpt_api_version.text().strip(),
            flux_api_version=self.flux_api_version.text().strip(),
            vision_api_version=self.vision_api_version.text().strip(),
            cv_endpoint=self.cv_endpoint.text().strip(),
            cv_secret=self.cv_secret.text().strip(),
            eval_deployment=self.eval_deployment.text().strip(),
            auto_eval=self.auto_eval.currentText(),
            eval_detail=self.eval_detail.currentText(),
            cv_enabled=self.cv_enabled.currentText(),
            models=[row.get_config() for row in self.model_rows],
        )

    def _save_config(self) -> None:
        save_config(self._collect_config())
        self._set_global_status("Config saved.")

    def _clear_config(self) -> None:
        self._apply_config(AppConfig(models=sample_models()))
        self._set_global_status("Config reset.")

    def _load_sample_models(self) -> None:
        self._clear_model_rows()
        for model in sample_models():
            self._add_model_row(model)

    def _add_model_row(self, config: ModelConfig | None = None) -> None:
        row = ModelRow(config)
        row.remove_requested.connect(self._remove_model_row)
        self.model_rows.append(row)
        self.model_list_layout.insertWidget(max(0, self.model_list_layout.count() - 1), row)

    def _remove_model_row(self, row: QWidget) -> None:
        if row in self.model_rows:
            self.model_rows.remove(row)
        row.setParent(None)
        row.deleteLater()

    def _clear_model_rows(self) -> None:
        for row in self.model_rows[:]:
            self._remove_model_row(row)

    def _load_benchmark_preset(self, key: str) -> None:
        preset = BENCHMARK_PRESETS[key]
        self.text_prompt.setPlainText(preset["prompt"])
        self.bench_annotation.setPlainText(preset["title"])
        self.bench_status.setText(f'Loaded "{preset["title"]}".')

    def _generate_benchmark(self) -> None:
        idea = self.bench_idea.text().strip()
        if not idea:
            self._show_error("Type a benchmark idea first.")
            return
        self.gen_bench_btn.setEnabled(False)
        self.bench_status.setText("Building benchmark...")
        self._submit_task(self.active_run_id, "benchmark", "__benchmark__", ApiClient(self._collect_config()).generate_benchmark, idea)

    def _pick_sources(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Pick source images",
            "",
            "Images (*.png *.jpg *.jpeg)",
        )
        if not paths:
            return
        self.source_paths = paths
        names = ", ".join(Path(path).name for path in paths)
        self.source_label.setText(f"Sources: {names}")

    def _pick_mask(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Pick mask image", "", "PNG (*.png)")
        if not path:
            return
        self.mask_path = path
        self.mask_label.setText(f"Mask: {Path(path).name}")

    def _clear_mask(self) -> None:
        self.mask_path = None
        self.mask_label.setText("No mask selected")

    def _enabled_models(self) -> list[ModelConfig]:
        return [row.get_config() for row in self.model_rows if row.get_config().enabled]

    def _start_run(self, mode: str) -> None:
        models = self._enabled_models()
        config = self._collect_config()
        if not models:
            self._show_error("Enable at least one model.")
            return
        if not config.global_endpoint or not config.global_secret:
            self._show_error("Set endpoint and key first.")
            return
        for model in models:
            if not model.deployment:
                self._show_error(f'Missing deployment for "{model.name}".')
                return
        if mode == "text":
            prompt = self.text_prompt.toPlainText().strip()
            if not prompt:
                self._show_error("Prompt required.")
                return
        else:
            prompt = self.edit_prompt.toPlainText().strip()
            if not prompt or not self.source_paths:
                self._show_error("Edit prompt and source images are required.")
                return
        self.active_run_id += 1
        self.current_prompt = prompt
        self.current_mode = mode
        self.result_cards.clear()
        self.result_records = {model.name: ResultRecord(model=model) for model in models}
        self.run_order = [model.name for model in models]
        self._clear_results_view()
        self._render_result_cards(models)
        self._clear_comparison()
        self.re_eval_btn.setEnabled(False)
        self._begin_phase("Generating", len(models))
        client = ApiClient(config)
        for model in models:
            if mode == "text":
                self._submit_task(
                    self.active_run_id,
                    "generate",
                    model.name,
                    client.generate_text,
                    model,
                    prompt,
                    self.text_size.currentText(),
                    self.text_quality.currentText(),
                    self.output_format.currentText(),
                )
            else:
                self._submit_task(
                    self.active_run_id,
                    "generate",
                    model.name,
                    client.generate_edit,
                    model,
                    prompt,
                    list(self.source_paths),
                    self.mask_path,
                    self.edit_size.currentText(),
                    self.output_format.currentText(),
                )

    def _clear_results_view(self) -> None:
        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_result_cards(self, models: list[ModelConfig]) -> None:
        for model in models:
            card = ResultCard(model)
            card.eval_requested.connect(self._evaluate_single)
            self.results_layout.insertWidget(max(0, self.results_layout.count() - 1), card)
            self.result_cards[model.name] = card

    def _submit_task(self, run_id: int, kind: str, model_name: str, func, *args) -> None:
        future: Future = self.executor.submit(func, *args)
        future.add_done_callback(partial(self._relay_future, run_id, kind, model_name))

    def _relay_future(self, run_id: int, kind: str, model_name: str, future: Future) -> None:
        try:
            payload = future.result()
            error = None
        except Exception as exc:
            payload = None
            error = str(exc)
        self.bridge.finished.emit(run_id, kind, model_name, payload, error)

    def _handle_task_result(self, run_id: int, kind: str, model_name: str, payload, error) -> None:
        if kind == "benchmark":
            self.gen_bench_btn.setEnabled(True)
            if error:
                self.bench_status.setText(error)
                return
            self.text_prompt.setPlainText(payload.get("prompt", ""))
            title = payload.get("title", "Benchmark")
            dim_map = payload.get("dimension_map", {})
            lines = [title, ""]
            for key in DIM_KEYS:
                lines.append(f"{DIM_LABELS[key]}: {dim_map.get(key, '—')}")
            self.bench_annotation.setPlainText("\n".join(lines))
            self.bench_status.setText(f'Loaded "{title}".')
            return
        if run_id != self.active_run_id:
            return
        if kind == "generate":
            self._handle_generation_result(model_name, payload, error)
        elif kind == "cv":
            self._handle_cv_result(model_name, payload, error)
        elif kind == "eval":
            self._handle_eval_result(model_name, payload, error)

    def _handle_generation_result(self, model_name: str, payload, error: str | None) -> None:
        card = self.result_cards[model_name]
        record = self.result_records[model_name]
        if error:
            record.error = error
            card.set_status(f"Error: {error}", True)
            self._add_log("ERROR", model_name, error)
        else:
            record.generation = payload
            usage = payload.usage
            usage_text = (
                f"In {usage.input_tokens or '—'} | Out {usage.output_tokens or '—'} | Total {usage.total_tokens or '—'}"
                if usage
                else "Per-image model"
            )
            card.set_generation(payload.image_b64, payload.mime_type, payload.response_payload)
            card.set_status(f"Done in {payload.elapsed_s:.2f}s")
            card.set_metrics(payload.elapsed_s, usage_text)
            self._add_log("INFO", model_name, f"Generation OK in {payload.elapsed_s:.2f}s")
        self.pending_generation -= 1
        self.progress.setValue(self.progress.maximum() - self.pending_generation)
        if self.pending_generation == 0:
            generated = [name for name, item in self.result_records.items() if item.generation is not None]
            self._set_global_status("Generation complete.")
            if generated and self.cv_enabled.currentText() == "yes":
                self._begin_phase("CV", len(generated))
                client = ApiClient(self._collect_config())
                for name in generated:
                    generation = self.result_records[name].generation
                    assert generation is not None
                    self.result_cards[name].set_status("Running CV...")
                    self._submit_task(self.active_run_id, "cv", name, client.analyze_image, generation.image_b64, name)
            elif generated and self.auto_eval.currentText() == "yes":
                self._start_eval_phase(generated)
            else:
                self.re_eval_btn.setEnabled(bool(generated))

    def _handle_cv_result(self, model_name: str, payload, error: str | None) -> None:
        card = self.result_cards[model_name]
        record = self.result_records[model_name]
        if error:
            card.cv_label.setText(f"CV error: {error}")
            self._add_log("ERROR", model_name, f"CV failed: {error}")
        else:
            record.cv_result = payload
            card.set_cv(payload)
            card.set_status("CV complete")
            self._add_log("INFO", model_name, f"CV OK with {len(payload.objects)} objects")
        self.pending_cv -= 1
        self.progress.setValue(self.progress.maximum() - self.pending_cv)
        if self.pending_cv == 0:
            generated = [name for name, item in self.result_records.items() if item.generation is not None]
            self._set_global_status("CV complete.")
            if generated and self.auto_eval.currentText() == "yes":
                self._start_eval_phase(generated)
            else:
                self.re_eval_btn.setEnabled(bool(generated))

    def _start_eval_phase(self, model_names: list[str]) -> None:
        self._begin_phase("Evaluating", len(model_names))
        client = ApiClient(self._collect_config())
        for name in model_names:
            card = self.result_cards[name]
            card.set_status("Evaluating...")
            generation = self.result_records[name].generation
            assert generation is not None
            self._submit_task(
                self.active_run_id,
                "eval",
                name,
                client.evaluate_image,
                image_data_url(generation.mime_type, generation.image_b64),
                self.current_prompt,
                name,
                self.result_records[name].cv_result,
            )

    def _evaluate_single(self, model_name: str) -> None:
        record = self.result_records.get(model_name)
        if record is None or record.generation is None:
            return
        if not self.eval_deployment.text().strip():
            self._show_error("Set Evaluator LLM first.")
            return
        self.re_eval_btn.setEnabled(False)
        card = self.result_cards[model_name]
        card.set_status("Evaluating...")
        client = ApiClient(self._collect_config())
        self.pending_eval += 1
        self.progress.setMaximum(max(1, self.pending_eval))
        self.progress.setValue(0)
        self._submit_task(
            self.active_run_id,
            "eval",
            model_name,
            client.evaluate_image,
            image_data_url(record.generation.mime_type, record.generation.image_b64),
            self.current_prompt,
            model_name,
            record.cv_result,
        )

    def _re_evaluate(self) -> None:
        if not self.eval_deployment.text().strip():
            self._show_error("Set Evaluator LLM first.")
            return
        generated = [name for name, item in self.result_records.items() if item.generation is not None]
        if not generated:
            return
        self._start_eval_phase(generated)

    def _handle_eval_result(self, model_name: str, payload, error: str | None) -> None:
        card = self.result_cards[model_name]
        record = self.result_records[model_name]
        if error:
            card.eval_label.setText(f"Evaluation error: {error}")
            card.set_status("Evaluation failed", True)
            self._add_log("ERROR", model_name, f"Eval failed: {error}")
        else:
            record.eval_result = payload
            card.set_eval(payload)
            card.set_status(f"Scored {payload.overall_score:.1f}")
            self._add_log("INFO", model_name, f"Eval OK: {payload.overall_score:.1f}")
        self.pending_eval -= 1
        self.progress.setValue(self.progress.maximum() - self.pending_eval)
        self._render_comparison()
        if self.pending_eval == 0:
            self._set_global_status("Evaluation complete.")
            self.re_eval_btn.setEnabled(True)

    def _render_comparison(self) -> None:
        evaluated = [(name, item.eval_result) for name, item in self.result_records.items() if item.eval_result is not None]
        if not evaluated:
            self._clear_comparison()
            return
        names = [name for name, _ in evaluated]
        lines = ["\t".join(["Dimension", *names])]
        for key in DIM_KEYS:
            scores = []
            for _, result in evaluated:
                assert result is not None
                scores.append(str(result.dimensions[key].score))
            lines.append("\t".join([DIM_LABELS[key], *scores]))
        overall = [f"{result.overall_score:.1f}" for _, result in evaluated]
        lines.append("\t".join(["Overall", *overall]))
        self.comparison_table.setPlainText("\n".join(lines))

    def _clear_comparison(self) -> None:
        self.comparison_table.setPlainText("No evaluations yet.")

    def _begin_phase(self, label: str, total: int) -> None:
        self._set_global_status(f"{label} {total} item(s)...")
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(0)
        if label == "Generating":
            self.pending_generation = total
            self.pending_cv = 0
            self.pending_eval = 0
        elif label == "CV":
            self.pending_cv = total
            self.pending_eval = 0
        elif label == "Evaluating":
            self.pending_eval = total

    def _set_global_status(self, text: str) -> None:
        self.global_status.setText(text)

    def _show_error(self, text: str) -> None:
        QMessageBox.critical(self, "Image Generation Model Comparison Portal", text)

    def _clear_log_view(self) -> None:
        self.log_entries.clear()
        self.log_view.clear()
        self.log_badge.setText("0")

    def _add_log(self, level: str, model_name: str, message: str) -> None:
        entry = f"{level} | {model_name} | {message}"
        self.log_entries.append(entry)
        self.log_view.setPlainText("\n".join(self.log_entries[-100:]))
        error_count = sum(1 for item in self.log_entries if item.startswith("ERROR"))
        self.log_badge.setText(str(error_count))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Image Generation Model Comparison Portal")
    window = MainWindow()
    window.show()
    return app.exec()
