from __future__ import annotations

import atexit
import base64
import json
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
import webbrowser
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from image_generation_model_comparison_portal.config import load_config, save_config
from image_generation_model_comparison_portal.models import AppConfig, BENCHMARK_PRESETS, DIM_LABELS, ModelConfig, sample_models
from image_generation_model_comparison_portal.services import ApiClient, image_data_url


WEB_DIR = Path(__file__).with_name("web")
REPORT_BUILDER = Path(__file__).with_name("report_builder.mjs")
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_plain(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain(item) for item in value]
    return value


class RunManager:
    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=12)
        self.lock = threading.RLock()
        self.runs: dict[str, dict[str, Any]] = {}
        self.temp_dirs: list[str] = []

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
        for temp_dir in self.temp_dirs:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def bootstrap_payload(self) -> dict[str, Any]:
        config = load_config() or AppConfig(models=sample_models())
        return {
            "config": config.to_dict(),
            "sampleModels": [model.to_dict() for model in sample_models()],
            "dimLabels": DIM_LABELS,
            "presets": BENCHMARK_PRESETS,
        }

    def save_config_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        config = AppConfig.from_dict(data)
        save_config(config)
        return {"ok": True}

    def generate_benchmark(self, config_data: dict[str, Any], idea: str) -> dict[str, Any]:
        config = AppConfig.from_dict(config_data)
        return ApiClient(config).generate_benchmark(idea)

    def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = AppConfig.from_dict(payload["config"])
        mode = payload["mode"]
        prompt = str(payload["prompt"]).strip()
        if not prompt:
            raise RuntimeError("Prompt required.")
        models = [ModelConfig(**item) for item in payload["models"]]
        if not models:
            raise RuntimeError("Enable at least one model.")
        temp_dir = tempfile.mkdtemp(prefix="image-generation-model-comparison-portal-")
        self.temp_dirs.append(temp_dir)
        source_paths: list[str] = []
        mask_path: str | None = None
        source_files_payload = payload.get("sourceFiles", [])
        source_data_urls = [item.get("dataUrl", "") for item in source_files_payload if item.get("dataUrl")]
        prompt_guidance = payload.get("promptGuidance") or {}
        if mode == "edit":
            source_paths = self._decode_uploads(temp_dir, source_files_payload)
            if not source_paths:
                raise RuntimeError("Edit mode requires at least one source image.")
            mask_items = payload.get("maskFiles", [])
            if mask_items:
                mask_path = self._decode_uploads(temp_dir, mask_items)[0]
        client = ApiClient(config)
        try:
            prepared = client.prepare_prompt(
                prompt=prompt,
                mode=mode,
                dimension_map=prompt_guidance.get("dimensionMap") or {},
                source_image_data_urls=source_data_urls,
            )
        except Exception:
            prepared = {
                "enriched_prompt": prompt,
                "summary": "",
                "source_summary": "",
                "dimension_map": prompt_guidance.get("dimensionMap") or {},
                "used_enrichment": False,
            }
        run_id = uuid.uuid4().hex[:12]
        run_state = {
            "id": run_id,
            "mode": mode,
            "prompt": prompt,
            "effectivePrompt": prepared["enriched_prompt"],
            "promptGuidance": {
                "title": prompt_guidance.get("title") or "",
                "summary": prepared.get("summary") or "",
                "sourceSummary": prepared.get("source_summary") or "",
                "dimensionMap": prepared.get("dimension_map") or {},
                "usedEnrichment": prepared.get("used_enrichment", False),
            },
            "textSize": payload.get("textSize", "1024x1024"),
            "textQuality": payload.get("textQuality", "high"),
            "outputFormat": payload.get("outputFormat", "png"),
            "editSize": payload.get("editSize", "1024x1024"),
            "status": "running",
            "phase": "generating",
            "progress": {"label": "Generating", "done": 0, "total": len(models)},
            "order": [model.name for model in models],
            "results": {model.name: self._base_result(model) for model in models},
            "errorLog": [],
            "tempDir": temp_dir,
            "config": config.to_dict(),
            "autoEval": config.auto_eval == "yes",
            "cvEnabled": config.cv_enabled == "yes",
            "sourcePaths": source_paths,
            "maskPath": mask_path,
            "activeTargets": [model.name for model in models],
            "reportPath": None,
        }
        with self.lock:
            self.runs[run_id] = run_state
        for model in models:
            self._submit_generation(run_id, client, model)
        return {"runId": run_id}

    def retry_generation(self, run_id: str, config_data: dict[str, Any], model_name: str) -> dict[str, Any]:
        with self.lock:
            run = self.runs.get(run_id)
            if run is None:
                raise KeyError(run_id)
            if run["status"] == "running":
                raise RuntimeError("Run is still in progress.")
            if model_name not in run["results"]:
                raise RuntimeError("Model not found in this run.")
            run["config"] = config_data
            run["status"] = "running"
            run["phase"] = "generating"
            run["progress"] = {"label": f"Retrying {model_name}", "done": 0, "total": 1}
            run["activeTargets"] = [model_name]
            run["reportPath"] = None
            result = run["results"][model_name]
            result["status"] = "Retrying..."
            result["error"] = None
            result["metrics"] = {}
            result["generation"] = None
            result["cv"] = None
            result["evaluation"] = None
            model = ModelConfig(**result["model"])
        config = AppConfig.from_dict(config_data)
        client = ApiClient(config)
        self._submit_generation(run_id, client, model)
        return {"ok": True}

    def export_report(self, run_id: str) -> dict[str, Any]:
        with self.lock:
            run = self.runs.get(run_id)
            if run is None:
                raise KeyError(run_id)
            report_path = run.get("reportPath")
            if report_path and Path(report_path).exists():
                path = Path(report_path)
                return {
                    "ok": True,
                    "fileName": path.name,
                    "downloadUrl": f"/api/runs/{run_id}/report.pptx",
                }
            if not any(run["results"][name].get("generation") for name in run["order"]):
                raise RuntimeError("No generated images are available for report export.")
            temp_dir = run["tempDir"]
            payload = _to_plain(run)
            payload["dimLabels"] = DIM_LABELS
        node_path, repo_root = self._report_runtime()
        report_dir = Path(temp_dir) / "report"
        report_dir.mkdir(parents=True, exist_ok=True)
        input_path = report_dir / "report-input.json"
        output_path = report_dir / f"image-generation-model-comparison-portal-report-{run_id}.pptx"
        input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        proc = subprocess.run(
            [node_path, str(REPORT_BUILDER), str(input_path), str(output_path)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if proc.returncode != 0 or not output_path.exists():
            detail = (proc.stderr or proc.stdout or "Report generation failed.").strip()
            raise RuntimeError(detail)
        with self.lock:
            if run_id in self.runs:
                self.runs[run_id]["reportPath"] = str(output_path)
        return {
            "ok": True,
            "fileName": output_path.name,
            "downloadUrl": f"/api/runs/{run_id}/report.pptx",
        }

    def get_report_path(self, run_id: str) -> Path:
        with self.lock:
            run = self.runs.get(run_id)
            if run is None:
                raise KeyError(run_id)
            report_path = run.get("reportPath")
        if not report_path:
            raise FileNotFoundError(run_id)
        path = Path(report_path)
        if not path.exists():
            raise FileNotFoundError(run_id)
        return path

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.lock:
            if run_id not in self.runs:
                raise KeyError(run_id)
            return _to_plain(self.runs[run_id])

    def trigger_evaluation(self, run_id: str, config_data: dict[str, Any], model_name: str | None) -> dict[str, Any]:
        with self.lock:
            run = self.runs.get(run_id)
            if run is None:
                raise KeyError(run_id)
            run["config"] = config_data
        config = AppConfig.from_dict(config_data)
        if model_name:
            target_names = [model_name]
        else:
            with self.lock:
                target_names = [name for name in run["order"] if run["results"][name]["generation"]]
        self._start_eval_phase(run_id, config, target_names)
        return {"ok": True}

    def _decode_uploads(self, temp_dir: str, items: list[dict[str, str]]) -> list[str]:
        paths: list[str] = []
        for index, item in enumerate(items):
            data_url = item.get("dataUrl", "")
            if "," not in data_url:
                continue
            header, raw_b64 = data_url.split(",", 1)
            suffix = ".png"
            if "jpeg" in header or "jpg" in header:
                suffix = ".jpg"
            file_name = item.get("name") or f"upload-{index}{suffix}"
            path = Path(temp_dir) / file_name
            path.write_bytes(base64.b64decode(raw_b64))
            paths.append(str(path))
        return paths

    def _base_result(self, model: ModelConfig) -> dict[str, Any]:
        return {
            "model": model.to_dict(),
            "status": "Queued...",
            "error": None,
            "metrics": {},
            "generation": None,
            "cv": None,
            "evaluation": None,
        }

    def _submit_generation(self, run_id: str, client: ApiClient, model: ModelConfig) -> None:
        run = self.runs[run_id]
        if run["mode"] == "text":
            self._submit(
                run_id,
                "generate",
                model.name,
                client.generate_text,
                model,
                run["effectivePrompt"],
                run["textSize"],
                run["textQuality"],
                run["outputFormat"],
            )
            return
        if model.kind.startswith("mai-"):
            self._submit(
                run_id,
                "generate",
                model.name,
                client.generate_text,
                model,
                run["effectivePrompt"],
                run["editSize"],
                "high",
                run["outputFormat"],
            )
            return
        self._submit(
            run_id,
            "generate",
            model.name,
            client.generate_edit,
            model,
            run["effectivePrompt"],
            list(run["sourcePaths"]),
            run["maskPath"],
            run["editSize"],
            run["outputFormat"],
        )

    def _report_runtime(self) -> tuple[str, Path]:
        repo_root = Path(__file__).resolve().parents[2]
        node_modules = repo_root / "node_modules"
        node_path: Path | None = None
        env_node = os.environ.get("CODEX_PRIMARY_RUNTIME_NODE") or os.environ.get("CODEX_RUNTIME_NODE")
        if env_node and Path(env_node).exists():
            node_path = Path(env_node)
        if node_path is None:
            candidates = sorted(
                Path.home().glob(".cache/codex-runtimes/*/dependencies/node/bin/node.exe"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                node_path = candidates[0]
        if node_path is None:
            raise RuntimeError("Node runtime for PPTX export was not found.")
        runtime_node_modules = node_path.parents[1] / "node_modules"
        if not runtime_node_modules.exists():
            raise RuntimeError("Bundled slide runtime packages were not found.")
        if not node_modules.exists():
            proc = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(node_modules), str(runtime_node_modules)],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0 and not node_modules.exists():
                detail = (proc.stderr or proc.stdout or "Unable to link node_modules.").strip()
                raise RuntimeError(detail)
        return str(node_path), repo_root

    def _submit(self, run_id: str, stage: str, model_name: str, func, *args) -> None:
        future: Future = self.executor.submit(func, *args)
        future.add_done_callback(lambda task: self._handle_task(run_id, stage, model_name, task))

    def _handle_task(self, run_id: str, stage: str, model_name: str, future: Future) -> None:
        try:
            payload = future.result()
            error = None
        except Exception as exc:
            payload = None
            error = str(exc)
        with self.lock:
            run = self.runs.get(run_id)
            if run is None:
                return
        if stage == "generate":
            self._handle_generation(run_id, model_name, payload, error)
        elif stage == "cv":
            self._handle_cv(run_id, model_name, payload, error)
        elif stage == "eval":
            self._handle_eval(run_id, model_name, payload, error)

    def _handle_generation(self, run_id: str, model_name: str, payload, error: str | None) -> None:
        next_cv = False
        next_eval = False
        generated: list[str] = []
        with self.lock:
            run = self.runs[run_id]
            active_targets = list(run.get("activeTargets") or run["order"])
            result = run["results"][model_name]
            if error:
                result["status"] = f"Error: {error}"
                result["error"] = error
                run["errorLog"].append({"level": "ERROR", "model": model_name, "message": error})
            else:
                result["error"] = None
                result["status"] = f"Done in {payload.elapsed_s:.2f}s"
                result["metrics"] = {
                    "elapsedS": payload.elapsed_s,
                    "inputTokens": payload.usage.input_tokens if payload.usage else None,
                    "outputTokens": payload.usage.output_tokens if payload.usage else None,
                    "totalTokens": payload.usage.total_tokens if payload.usage else None,
                }
                result["generation"] = {
                    "imageDataUrl": image_data_url(payload.mime_type, payload.image_b64),
                    "mimeType": payload.mime_type,
                    "elapsedS": payload.elapsed_s,
                    "promptUsed": run["effectivePrompt"],
                    "request": payload.request_payload,
                    "response": payload.response_payload,
                    "url": payload.url,
                    "editFallbackUsed": run["mode"] == "edit" and result["model"]["kind"].startswith("mai-"),
                }
                run["errorLog"].append({"level": "INFO", "model": model_name, "message": f"Generation OK in {payload.elapsed_s:.2f}s"})
            run["progress"]["done"] += 1
            run["reportPath"] = None
            if run["progress"]["done"] >= run["progress"]["total"]:
                generated = [name for name in active_targets if run["results"][name]["generation"]]
                if generated and run["cvEnabled"]:
                    run["phase"] = "cv"
                    run["progress"] = {"label": "CV", "done": 0, "total": len(generated)}
                    run["activeTargets"] = list(generated)
                    next_cv = True
                elif generated and run["autoEval"]:
                    run["phase"] = "evaluating"
                    run["progress"] = {"label": "Evaluating", "done": 0, "total": len(generated)}
                    run["activeTargets"] = list(generated)
                    next_eval = True
                else:
                    run["phase"] = "idle"
                    run["status"] = "ready"
                    run["activeTargets"] = []
        if next_cv:
            config = AppConfig.from_dict(self.runs[run_id]["config"])
            client = ApiClient(config)
            for name in generated:
                generation = self.runs[run_id]["results"][name]["generation"]
                if generation:
                    self._submit(run_id, "cv", name, client.analyze_image, generation["imageDataUrl"].split(",", 1)[1], name)
        elif next_eval:
            self._start_eval_phase(run_id, AppConfig.from_dict(self.runs[run_id]["config"]), generated)

    def _handle_cv(self, run_id: str, model_name: str, payload, error: str | None) -> None:
        next_eval = False
        generated: list[str] = []
        with self.lock:
            run = self.runs[run_id]
            active_targets = list(run.get("activeTargets") or run["order"])
            result = run["results"][model_name]
            if error:
                result["cv"] = {"error": error, "objects": [], "tags": [], "raw": None}
                run["errorLog"].append({"level": "ERROR", "model": model_name, "message": f"CV failed: {error}"})
            else:
                result["cv"] = {
                    "objects": _to_plain(payload.objects),
                    "tags": _to_plain(payload.tags),
                    "counts": payload.object_counts(),
                    "raw": payload.raw_payload,
                }
                result["status"] = "CV complete"
                run["errorLog"].append({"level": "INFO", "model": model_name, "message": f"CV OK with {len(payload.objects)} objects"})
            run["progress"]["done"] += 1
            if run["progress"]["done"] >= run["progress"]["total"]:
                generated = [name for name in active_targets if run["results"][name]["generation"]]
                if generated and run["autoEval"]:
                    run["phase"] = "evaluating"
                    run["progress"] = {"label": "Evaluating", "done": 0, "total": len(generated)}
                    run["activeTargets"] = list(generated)
                    next_eval = True
                else:
                    run["phase"] = "idle"
                    run["status"] = "ready"
                    run["activeTargets"] = []
        if next_eval:
            self._start_eval_phase(run_id, AppConfig.from_dict(self.runs[run_id]["config"]), generated)

    def _start_eval_phase(self, run_id: str, config: AppConfig, model_names: list[str]) -> None:
        if not model_names:
            with self.lock:
                run = self.runs[run_id]
                run["phase"] = "idle"
                run["status"] = "ready"
                run["activeTargets"] = []
            return
        with self.lock:
            run = self.runs[run_id]
            run["phase"] = "evaluating"
            run["status"] = "running"
            run["progress"] = {"label": "Evaluating", "done": 0, "total": len(model_names)}
            run["activeTargets"] = list(model_names)
        client = ApiClient(config)
        for model_name in model_names:
            generation = self.runs[run_id]["results"][model_name]["generation"]
            if not generation:
                with self.lock:
                    self.runs[run_id]["progress"]["done"] += 1
                continue
            cv = self.runs[run_id]["results"][model_name]["cv"]
            self._submit(
                run_id,
                "eval",
                model_name,
                client.evaluate_image,
                generation["imageDataUrl"],
                self.runs[run_id]["prompt"],
                model_name,
                self._cv_from_frontend(cv),
                self.runs[run_id]["effectivePrompt"],
                self.runs[run_id]["promptGuidance"]["dimensionMap"],
                self.runs[run_id]["promptGuidance"]["sourceSummary"],
            )

    def _cv_from_frontend(self, cv_payload: dict[str, Any] | None):
        if not cv_payload or cv_payload.get("error"):
            return None
        class Box:
            def __init__(self, item: dict[str, Any]) -> None:
                self.label = item["label"]
                self.confidence = item["confidence"]
                self.x = item["x"]
                self.y = item["y"]
                self.w = item["w"]
                self.h = item["h"]

        class CvShim:
            def __init__(self, payload: dict[str, Any]) -> None:
                self.objects = [Box(item) for item in payload.get("objects", [])]
                self.tags = [tuple(item) for item in payload.get("tags", [])]
                self.raw_payload = payload.get("raw")

            def object_counts(self) -> dict[str, int]:
                counts: dict[str, int] = {}
                for item in self.objects:
                    counts[item.label] = counts.get(item.label, 0) + 1
                return counts

        return CvShim(cv_payload)

    def _handle_eval(self, run_id: str, model_name: str, payload, error: str | None) -> None:
        with self.lock:
            run = self.runs[run_id]
            result = run["results"][model_name]
            if error:
                result["evaluation"] = {"error": error}
                result["status"] = "Evaluation failed"
                result["error"] = error
                run["errorLog"].append({"level": "ERROR", "model": model_name, "message": f"Eval failed: {error}"})
            else:
                result["error"] = None
                result["evaluation"] = _to_plain(payload)
                result["status"] = f"Scored {payload.overall_score:.1f}"
                run["errorLog"].append({"level": "INFO", "model": model_name, "message": f"Eval OK: {payload.overall_score:.1f}"})
            run["progress"]["done"] += 1
            if run["progress"]["done"] >= run["progress"]["total"]:
                run["phase"] = "complete"
                run["status"] = "ready"
                run["activeTargets"] = []


RUNS = RunManager()
atexit.register(RUNS.shutdown)


class AppHandler(BaseHTTPRequestHandler):
    server_version = "ImageGenerationModelComparisonPortalHTTP/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/static/"):
            local = WEB_DIR / parsed.path.removeprefix("/static/")
            if local.suffix == ".css":
                self._serve_file(local, "text/css; charset=utf-8")
                return
            if local.suffix == ".js":
                self._serve_file(local, "application/javascript; charset=utf-8")
                return
        if parsed.path == "/api/bootstrap":
            self._json_response(HTTPStatus.OK, RUNS.bootstrap_payload())
            return
        if parsed.path.endswith("/report.pptx") and parsed.path.startswith("/api/runs/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 4:
                run_id = parts[2]
                try:
                    path = RUNS.get_report_path(run_id)
                except KeyError:
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": "Run not found."})
                    return
                except FileNotFoundError:
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": "Report not found."})
                    return
                self._serve_file(path, PPTX_MIME, download_name=path.name)
                return
        if parsed.path.startswith("/api/runs/"):
            run_id = parsed.path.split("/")[-1]
            try:
                payload = RUNS.get_run(run_id)
            except KeyError:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "Run not found."})
                return
            self._json_response(HTTPStatus.OK, payload)
            return
        self._json_response(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        data = self._read_json()
        if parsed.path == "/api/config":
            self._json_response(HTTPStatus.OK, RUNS.save_config_payload(data))
            return
        if parsed.path == "/api/benchmark":
            try:
                payload = RUNS.generate_benchmark(data["config"], data["idea"])
            except Exception as exc:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._json_response(HTTPStatus.OK, payload)
            return
        if parsed.path.endswith("/retry") and parsed.path.startswith("/api/runs/"):
            parts = parsed.path.strip("/").split("/")
            run_id = parts[2]
            try:
                payload = RUNS.retry_generation(run_id, data["config"], data["modelName"])
            except KeyError:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "Run not found."})
                return
            except Exception as exc:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._json_response(HTTPStatus.OK, payload)
            return
        if parsed.path.endswith("/report") and parsed.path.startswith("/api/runs/"):
            parts = parsed.path.strip("/").split("/")
            run_id = parts[2]
            try:
                payload = RUNS.export_report(run_id)
            except KeyError:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "Run not found."})
                return
            except Exception as exc:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._json_response(HTTPStatus.OK, payload)
            return
        if parsed.path == "/api/run":
            try:
                payload = RUNS.create_run(data)
            except Exception as exc:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._json_response(HTTPStatus.OK, payload)
            return
        if parsed.path.endswith("/evaluate") and parsed.path.startswith("/api/runs/"):
            parts = parsed.path.strip("/").split("/")
            run_id = parts[2]
            try:
                payload = RUNS.trigger_evaluation(run_id, data["config"], data.get("modelName"))
            except KeyError:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "Run not found."})
                return
            except Exception as exc:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._json_response(HTTPStatus.OK, payload)
            return
        self._json_response(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def log_message(self, format: str, *args) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _serve_file(self, path: Path, content_type: str, download_name: str | None = None) -> None:
        if not path.exists():
            self._json_response(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(data)

    def _json_response(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)


class ThreadedServer(ThreadingHTTPServer):
    daemon_threads = True


def run() -> int:
    server = ThreadedServer(("127.0.0.1", 0), AppHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    webbrowser.open(f"http://{host}:{port}/?v={uuid.uuid4().hex}")
    try:
        thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0
