from __future__ import annotations

import base64
import copy
import json
import math
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from image_generation_model_comparison_portal.models import (
    AppConfig,
    BoundingBox,
    CvResult,
    DIM_KEYS,
    DIM_LABELS,
    EvalDimension,
    EvalResult,
    GenerationResult,
    ModelConfig,
    Usage,
)


BENCH_SYS = (
    "You are a benchmark prompt engineer for AI image generation. Given a theme, generate a prompt "
    "(~120-180 words) that stress-tests all 10 dimensions. Include visible text, exact counts, spatial "
    "positions, anatomy, light/shadows, colors, textures, and camera parameters. Respond with JSON only in "
    'this exact schema: {"prompt":"...","title":"2-4 words","dimension_map":{"prompt_adherence":"<15w>",'
    '"text_rendering":"<15w>","object_counting":"<15w>","spatial_reasoning":"<15w>","anatomy_proportions":"<15w>",'
    '"physics_realism":"<15w>","color_accuracy":"<15w>","fine_detail":"<15w>","composition_aesthetics":"<15w>",'
    '"style_adherence":"<15w>"}}'
)

EVAL_SYS = """You are an expert AI image evaluator. Score 10 dimensions with integer scores from 1 to 10.
You receive: 1) the original prompt, 2) the generated image, 3) optional Azure AI Vision analysis.
When CV data is provided, cross-reference detected object counts against prompt quantities. CV may miss small or occluded objects, so use it as evidence, not as the only source.
For images containing people, do not depend on face identity, facial detail, or facial sharpness because safety filtering or model behavior may blur, mask, or suppress faces before analysis.
In the anatomy_proportions dimension, prioritize whole-body coherence: gesture, pose, limb placement, shoulder-to-arm-to-hand ratios, hand structure, visible finger counts, body balance, and subject placement in frame.
If faces are obscured or low-detail, do not penalize that by itself unless the prompt explicitly requires recognizable facial identity or facial expression and the rest of the body evidence also fails.
Every dimension must include "score" and "note". Provide "strengths" with 2 items, "weaknesses" with 2 items, and "summary" with 2-3 sentences.
Respond with JSON only in this shape:
{"overall_score":7.5,"dimensions":{"prompt_adherence":{"score":8,"note":"..."},"text_rendering":{"score":6,"note":"..."},"object_counting":{"score":9,"note":"..."},"spatial_reasoning":{"score":7,"note":"..."},"anatomy_proportions":{"score":8,"note":"..."},"physics_realism":{"score":7,"note":"..."},"color_accuracy":{"score":9,"note":"..."},"fine_detail":{"score":8,"note":"..."},"composition_aesthetics":{"score":8,"note":"..."},"style_adherence":{"score":7,"note":"..."}},"strengths":["s1","s2"],"weaknesses":["w1","w2"],"summary":"2-3 sentences."}"""

PROMPT_ENRICH_SYS = """You are a prompt enrichment assistant for AI image generation benchmarking.
Your job is to preserve the user's intent while rewriting it into a richer production-ready image prompt and to derive 10-dimension quality targets for later evaluation.
If source images are provided, first infer the important visual anchors that should be preserved unless the edit request explicitly changes them.
When the prompt includes people, make anatomy_proportions targets focus on pose, gesture, limb ratios, hand structure, and finger visibility rather than face identity or facial detail.
Return JSON only in this shape:
{"enriched_prompt":"...","summary":"1-2 sentences","source_summary":"...","dimension_map":{"prompt_adherence":"...","text_rendering":"...","object_counting":"...","spatial_reasoning":"...","anatomy_proportions":"...","physics_realism":"...","color_accuracy":"...","fine_detail":"...","composition_aesthetics":"...","style_adherence":"..."}}"""


def is_gpt(kind: str) -> bool:
    return kind.startswith("gpt-image")


def is_flux(kind: str) -> bool:
    return kind.startswith("flux-")


def is_mai(kind: str) -> bool:
    return kind.startswith("mai-")


def flux_name(model: ModelConfig) -> str:
    mapping = {
        "flux-2-pro": "FLUX.2-pro",
        "flux-2-flex": "FLUX.2-flex",
        "flux-kontext-pro": "FLUX.1-Kontext-pro",
        "flux-pro-1.1": "FLUX-1.1-pro",
    }
    canonical = mapping.get(model.kind, model.kind)
    raw = (model.deployment or "").strip()
    if not raw:
        return canonical
    normalized = "".join(ch for ch in raw.lower() if ch.isalnum())
    aliases = {
        canonical.lower().replace(".", "").replace("-", ""),
        model.kind.lower().replace(".", "").replace("-", ""),
        canonical.lower().replace(".", "").replace("-", "").replace("_", ""),
    }
    if normalized in aliases:
        return canonical
    return raw


def parse_size(value: str | None) -> tuple[int, int]:
    if not value or value == "auto":
        return 1024, 1024
    width_str, height_str = value.split("x", 1)
    return int(width_str), int(height_str)


def pretty_json(payload: dict[str, Any] | list[Any] | None) -> str:
    if payload is None:
        return ""
    return json.dumps(payload, indent=2, ensure_ascii=False)


class ApiClient:
    def __init__(self, config: AppConfig):
        self.config = config
        self.timeout = 180

    def _timeout_for(self, operation: str, kind: str | None = None) -> int:
        if operation in {"generate", "edit"}:
            if kind == "gpt-image-2":
                return 600
            if kind and kind.startswith("gpt-image"):
                return 420
            return 300
        if operation == "eval":
            return 240
        return self.timeout

    def _endpoint(self) -> str:
        return self.config.global_endpoint.rstrip("/")

    def _vision_endpoint(self) -> str:
        return (self.config.cv_endpoint or self.config.global_endpoint).rstrip("/")

    def _secret(self) -> str:
        return self.config.global_secret.strip()

    def _vision_secret(self) -> str:
        return (self.config.cv_secret or self.config.global_secret).strip()

    def _headers(self, kind: str, json_content: bool = True) -> dict[str, str]:
        headers: dict[str, str] = {}
        if json_content:
            headers["Content-Type"] = "application/json"
        secret = self._secret()
        if self.config.global_auth_type == "apiKey":
            headers["api-key"] = secret
            if is_flux(kind):
                headers["Authorization"] = f"Bearer {secret}"
        else:
            headers["Authorization"] = f"Bearer {secret}"
        return headers

    def _vision_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/octet-stream"}
        secret = self._vision_secret()
        if self.config.global_auth_type == "apiKey":
            headers["Ocp-Apim-Subscription-Key"] = secret
        else:
            headers["Authorization"] = f"Bearer {secret}"
        return headers

    def _read_json(self, response: requests.Response) -> dict[str, Any]:
        try:
            return response.json()
        except Exception:
            return {}

    def _error_message(self, response: requests.Response, payload: dict[str, Any]) -> str:
        return (
            payload.get("error", {}).get("message")
            or payload.get("message")
            or f"HTTP {response.status_code}"
        )

    def _raise_for_payload(self, response: requests.Response, payload: dict[str, Any]) -> None:
        if response.ok:
            return
        message = self._error_message(response, payload)
        raise RuntimeError(message)

    def _extract_usage(self, payload: dict[str, Any]) -> Usage | None:
        usage = payload.get("usage")
        if not usage:
            return None
        input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
        output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
        total_tokens = usage.get("total_tokens")
        if total_tokens is None and input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens
        return Usage(input_tokens, output_tokens, total_tokens)

    def _chat_url(self, deployment: str) -> str:
        return (
            f"{self._endpoint()}/openai/deployments/{quote(deployment, safe='')}"
            f"/chat/completions?api-version={quote(self.config.gpt_api_version, safe='')}"
        )

    def _request_flux_json(self, url: str, kind: str, body: dict[str, Any], canonical_model: str | None = None) -> tuple[requests.Response, dict[str, Any], dict[str, Any]]:
        timeout = self._timeout_for("generate", kind)
        candidates: list[dict[str, Any]] = [copy.deepcopy(body)]
        if canonical_model and canonical_model != body.get("model"):
            canonical_body = copy.deepcopy(body)
            canonical_body["model"] = canonical_model
            candidates.append(canonical_body)
        compact_candidates: list[dict[str, Any]] = []
        for candidate in list(candidates):
            no_output = copy.deepcopy(candidate)
            no_output.pop("output_format", None)
            compact_candidates.append(no_output)
            no_output_num = copy.deepcopy(no_output)
            no_output_num.pop("num_images", None)
            compact_candidates.append(no_output_num)

        seen: set[str] = set()
        last_response: requests.Response | None = None
        last_payload: dict[str, Any] = {}
        last_body: dict[str, Any] = body
        for candidate in [*candidates, *compact_candidates]:
            fingerprint = json.dumps(candidate, sort_keys=True)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            response = requests.post(url, headers=self._headers(kind, True), json=candidate, timeout=timeout)
            payload = self._read_json(response)
            if response.ok:
                return response, payload, candidate
            last_response = response
            last_payload = payload
            last_body = candidate
            if response.status_code != 400:
                break
        assert last_response is not None
        return last_response, last_payload, last_body

    def _generation_url(self, model: ModelConfig) -> str:
        endpoint = self._endpoint()
        if is_gpt(model.kind):
            return (
                f"{endpoint}/openai/deployments/{quote(model.deployment, safe='')}"
                f"/images/generations?api-version={quote(self.config.gpt_api_version, safe='')}"
            )
        if is_flux(model.kind):
            return (
                f"{endpoint}/providers/blackforestlabs/v1/{model.kind}"
                f"?api-version={quote(self.config.flux_api_version or 'preview', safe='')}"
            )
        if is_mai(model.kind):
            return f"{endpoint}/mai/v1/images/generations"
        raise RuntimeError(f"Unsupported model kind: {model.kind}")

    def prepare_prompt(
        self,
        prompt: str,
        mode: str,
        dimension_map: dict[str, str] | None = None,
        source_image_data_urls: list[str] | None = None,
    ) -> dict[str, Any]:
        dimension_map = dimension_map or {}
        source_image_data_urls = source_image_data_urls or []
        if not self.config.eval_deployment:
            return {
                "enriched_prompt": prompt,
                "summary": "",
                "source_summary": "",
                "dimension_map": dimension_map,
                "used_enrichment": False,
            }
        user_lines = [
            f"Mode: {mode}",
            "Original prompt:",
            prompt,
        ]
        if dimension_map:
            user_lines.extend(
                [
                    "",
                    "Existing quality targets:",
                    *[f"- {DIM_LABELS[key]}: {dimension_map.get(key, '')}" for key in DIM_KEYS],
                ]
            )
        if mode == "edit":
            user_lines.extend(
                [
                    "",
                    "For edit mode, preserve the important identity, layout, and scene anchors from the source image unless the user explicitly asks to change them.",
                    "Blend those preserved anchors into the rewritten prompt so a text-to-image fallback can reproduce the intended edit.",
                ]
            )
        content: list[dict[str, Any]] = []
        if source_image_data_urls:
            for data_url in source_image_data_urls[:4]:
                content.append({"type": "image_url", "image_url": {"url": data_url, "detail": "high"}})
        content.append({"type": "text", "text": "\n".join(user_lines)})
        payload = {
            "model": self.config.eval_deployment,
            "max_completion_tokens": 2200,
            "temperature": 0.45,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": PROMPT_ENRICH_SYS},
                {"role": "user", "content": content},
            ],
        }
        response = requests.post(
            self._chat_url(self.config.eval_deployment),
            headers=self._headers("gpt", True),
            json=payload,
            timeout=self._timeout_for("eval"),
        )
        data = self._read_json(response)
        self._raise_for_payload(response, data)
        content_text = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        parsed = json.loads(content_text)
        merged_dimension_map = {key: str((parsed.get("dimension_map") or {}).get(key) or dimension_map.get(key) or "") for key in DIM_KEYS}
        return {
            "enriched_prompt": str(parsed.get("enriched_prompt") or prompt),
            "summary": str(parsed.get("summary") or ""),
            "source_summary": str(parsed.get("source_summary") or ""),
            "dimension_map": merged_dimension_map,
            "used_enrichment": True,
        }

    def _edit_url(self, model: ModelConfig) -> str:
        endpoint = self._endpoint()
        if is_gpt(model.kind):
            return (
                f"{endpoint}/openai/deployments/{quote(model.deployment, safe='')}"
                f"/images/edits?api-version={quote(self.config.gpt_api_version, safe='')}"
            )
        if is_flux(model.kind):
            return (
                f"{endpoint}/providers/blackforestlabs/v1/{model.kind}"
                f"?api-version={quote(self.config.flux_api_version or 'preview', safe='')}"
            )
        raise RuntimeError(f"Unsupported edit model kind: {model.kind}")

    def generate_benchmark(self, idea: str) -> dict[str, Any]:
        if not self.config.eval_deployment:
            raise RuntimeError("Set Evaluator LLM first.")
        url = (
            f"{self._endpoint()}/openai/deployments/{quote(self.config.eval_deployment, safe='')}"
            f"/chat/completions?api-version={quote(self.config.gpt_api_version, safe='')}"
        )
        payload = {
            "model": self.config.eval_deployment,
            "max_completion_tokens": 1500,
            "temperature": 0.85,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": BENCH_SYS},
                {"role": "user", "content": f'Theme: "{idea}"'},
            ],
        }
        response = requests.post(url, headers=self._headers("gpt", True), json=payload, timeout=self.timeout)
        data = self._read_json(response)
        self._raise_for_payload(response, data)
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        return json.loads(content)

    def generate_text(
        self,
        model: ModelConfig,
        prompt: str,
        size: str,
        quality: str,
        output_format: str,
    ) -> GenerationResult:
        started = time.perf_counter()
        url = self._generation_url(model)
        width, height = parse_size(size)
        if is_gpt(model.kind):
            body: dict[str, Any] = {
                "prompt": prompt,
                "model": model.kind,
                "n": 1,
                "quality": quality,
            }
            if size != "auto":
                body["size"] = size
            if model.kind == "gpt-image-2":
                body["output_format"] = output_format
            response = requests.post(url, headers=self._headers(model.kind, True), json=body, timeout=self._timeout_for("generate", model.kind))
            data = self._read_json(response)
            self._raise_for_payload(response, data)
            image_b64 = data.get("data", [{}])[0].get("b64_json")
            if not image_b64:
                raise RuntimeError("No image in response.")
            mime = "image/jpeg" if output_format == "jpeg" and model.kind == "gpt-image-2" else "image/png"
            return GenerationResult(
                model_name=model.name,
                model_kind=model.kind,
                image_b64=image_b64,
                mime_type=mime,
                elapsed_s=round(time.perf_counter() - started, 2),
                usage=self._extract_usage(data),
                url=url,
                request_payload=body,
                response_payload=data,
            )
        if is_flux(model.kind):
            canonical = flux_name(ModelConfig(name=model.name, kind=model.kind, deployment="", enabled=model.enabled))
            body = {
                "model": flux_name(model),
                "prompt": prompt,
                "width": width,
                "height": height,
                "output_format": output_format,
                "num_images": 1,
            }
            response, data, used_body = self._request_flux_json(url, model.kind, body, canonical)
            self._raise_for_payload(response, data)
            item = data.get("data", [{}])[0] or data.get("result", {})
            image_b64 = item.get("b64_json") or item.get("base64") or item.get("image")
            if not image_b64:
                raise RuntimeError("No image in response.")
            mime = "image/jpeg" if output_format == "jpeg" else "image/png"
            return GenerationResult(
                model_name=model.name,
                model_kind=model.kind,
                image_b64=image_b64,
                mime_type=mime,
                elapsed_s=round(time.perf_counter() - started, 2),
                usage=None,
                url=url,
                request_payload=used_body,
                response_payload=data,
            )
        if is_mai(model.kind):
            width = max(768, width)
            height = max(768, height)
            if width * height > 1_048_576:
                ratio = math.sqrt(1_048_576 / (width * height))
                width = math.floor(width * ratio / 16) * 16
                height = math.floor(height * ratio / 16) * 16
            body = {"model": model.deployment, "prompt": prompt, "width": width, "height": height}
            response = requests.post(url, headers=self._headers(model.kind, True), json=body, timeout=self._timeout_for("generate", model.kind))
            data = self._read_json(response)
            self._raise_for_payload(response, data)
            image_b64 = data.get("data", [{}])[0].get("b64_json")
            if not image_b64:
                raise RuntimeError("No image in response.")
            return GenerationResult(
                model_name=model.name,
                model_kind=model.kind,
                image_b64=image_b64,
                mime_type="image/png",
                elapsed_s=round(time.perf_counter() - started, 2),
                usage=None,
                url=url,
                request_payload=body,
                response_payload=data,
            )
        raise RuntimeError(f"Unsupported model kind: {model.kind}")

    def generate_edit(
        self,
        model: ModelConfig,
        prompt: str,
        source_paths: list[str],
        mask_path: str | None,
        size: str,
        output_format: str,
    ) -> GenerationResult:
        started = time.perf_counter()
        if is_mai(model.kind):
            raise RuntimeError("MAI models do not support edit in this app.")
        url = self._edit_url(model)
        if is_flux(model.kind):
            if model.kind not in {"flux-2-pro", "flux-2-flex", "flux-kontext-pro"}:
                raise RuntimeError("This FLUX model does not support image edit.")
            limit = {"flux-2-flex": 10, "flux-2-pro": 8, "flux-kontext-pro": 1}[model.kind]
            if not source_paths or len(source_paths) > limit:
                raise RuntimeError(f"Need 1-{limit} source images for {model.kind}.")
            canonical = flux_name(ModelConfig(name=model.name, kind=model.kind, deployment="", enabled=model.enabled))
            body: dict[str, Any] = {
                "model": flux_name(model),
                "prompt": prompt,
                "output_format": output_format,
            }
            for index, path in enumerate(source_paths, start=1):
                key = "input_image" if index == 1 else f"input_image_{index}"
                body[key] = base64.b64encode(Path(path).read_bytes()).decode("ascii")
            response, data, used_body = self._request_flux_json(url, model.kind, body, canonical)
            self._raise_for_payload(response, data)
            item = data.get("data", [{}])[0] or data.get("result", {})
            image_b64 = item.get("b64_json") or item.get("base64") or item.get("image")
            if not image_b64:
                raise RuntimeError("No image in response.")
            return GenerationResult(
                model_name=model.name,
                model_kind=model.kind,
                image_b64=image_b64,
                mime_type="image/jpeg" if output_format == "jpeg" else "image/png",
                elapsed_s=round(time.perf_counter() - started, 2),
                usage=None,
                url=url,
                request_payload=used_body,
                response_payload=data,
            )
        if not source_paths:
            raise RuntimeError("Source image required.")
        data = {
            "prompt": prompt,
            "model": model.kind,
            "size": size,
            "n": "1",
            "quality": "high",
        }
        files: list[tuple[str, tuple[str, bytes, str]]] = []
        files.append(("image[]", ("source.png", Path(source_paths[0]).read_bytes(), "image/png")))
        if mask_path:
            files.append(("mask", ("mask.png", Path(mask_path).read_bytes(), "image/png")))
        response = requests.post(
            url,
            headers=self._headers(model.kind, False),
            data=data,
            files=files,
            timeout=self._timeout_for("edit", model.kind),
        )
        payload = self._read_json(response)
        self._raise_for_payload(response, payload)
        image_b64 = payload.get("data", [{}])[0].get("b64_json")
        if not image_b64:
            raise RuntimeError("No image in response.")
        request_payload = copy.deepcopy(data)
        request_payload["image_files"] = [Path(path).name for path in source_paths]
        if mask_path:
            request_payload["mask_file"] = Path(mask_path).name
        return GenerationResult(
            model_name=model.name,
            model_kind=model.kind,
            image_b64=image_b64,
            mime_type="image/png",
            elapsed_s=round(time.perf_counter() - started, 2),
            usage=self._extract_usage(payload),
            url=url,
            request_payload=request_payload,
            response_payload=payload,
        )

    def analyze_image(self, image_b64: str, model_name: str) -> CvResult:
        image_bytes = base64.b64decode(image_b64)
        url = (
            f"{self._vision_endpoint()}/computervision/imageanalysis:analyze"
            f"?features=objects,tags&api-version={quote(self.config.vision_api_version, safe='')}"
        )
        response = requests.post(url, headers=self._vision_headers(), data=image_bytes, timeout=self._timeout_for("cv"))
        payload = self._read_json(response)
        self._raise_for_payload(response, payload)
        objects: list[BoundingBox] = []
        for item in payload.get("objectsResult", {}).get("values", []):
            box = item.get("boundingBox") or {}
            label = (
                item.get("tags", [{}])[0].get("name")
                or item.get("name")
                or "unknown"
            )
            confidence = (
                item.get("tags", [{}])[0].get("confidence")
                or item.get("confidence")
                or 0.0
            )
            objects.append(
                BoundingBox(
                    label=str(label),
                    confidence=float(confidence),
                    x=float(box.get("x", 0)),
                    y=float(box.get("y", 0)),
                    w=float(box.get("w", box.get("width", 0))),
                    h=float(box.get("h", box.get("height", 0))),
                )
            )
        tags = []
        for item in payload.get("tagsResult", {}).get("values", []):
            confidence = float(item.get("confidence", 0))
            if confidence >= 0.5:
                tags.append((str(item.get("name", "unknown")), confidence))
        return CvResult(objects=objects, tags=tags, raw_payload=payload)

    def summarize_cv_for_eval(self, cv_result: CvResult | None) -> str:
        if cv_result is None:
            return ""
        parts: list[str] = []
        counts = cv_result.object_counts()
        if counts:
            rendered = ", ".join(f"{name}: {count}" for name, count in counts.items())
            parts.append(f"DETECTED OBJECTS ({sum(counts.values())} total): {rendered}")
        else:
            parts.append("DETECTED OBJECTS: None detected.")
        if cv_result.tags:
            parts.append("SCENE TAGS: " + ", ".join(name for name, _ in cv_result.tags))
        return "\n".join(parts)

    def evaluate_image(
        self,
        image_data_url: str,
        prompt: str,
        model_name: str,
        cv_result: CvResult | None,
        generation_prompt: str | None = None,
        dimension_map: dict[str, str] | None = None,
        source_summary: str | None = None,
    ) -> EvalResult:
        if not self.config.eval_deployment:
            raise RuntimeError("Set Evaluator LLM first.")
        url = self._chat_url(self.config.eval_deployment)
        cv_summary = self.summarize_cv_for_eval(cv_result)
        user_text = f'Original user prompt:\n"""{prompt}"""\n\nEvaluate the image. All fields are mandatory.'
        if generation_prompt and generation_prompt.strip() and generation_prompt.strip() != prompt.strip():
            user_text += f'\n\nGeneration prompt actually used:\n"""{generation_prompt}"""'
        if source_summary:
            user_text += f"\n\nSource-image preservation summary:\n{source_summary}"
        if dimension_map:
            rendered_targets = "\n".join(f"- {DIM_LABELS[key]}: {dimension_map.get(key) or '—'}" for key in DIM_KEYS)
            user_text += f"\n\nQUALITY TARGETS FOR THE 10 DIMENSIONS:\n{rendered_targets}"
        if cv_summary:
            user_text += (
                "\n\n--- COMPUTER VISION ANALYSIS ---\n"
                f"{cv_summary}\n"
                "--- END CV ---\n"
                "Cross-reference detected objects against prompt quantities."
            )
        payload = {
            "model": self.config.eval_deployment,
            "max_completion_tokens": 4000,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": EVAL_SYS},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_data_url,
                                "detail": self.config.eval_detail,
                            },
                        },
                    ],
                },
            ],
        }
        redacted_request = copy.deepcopy(payload)
        image_ref = redacted_request["messages"][1]["content"][1]["image_url"]["url"]
        if len(image_ref) > 96:
            redacted_request["messages"][1]["content"][1]["image_url"]["url"] = image_ref[:96] + "..."
        response = requests.post(url, headers=self._headers("gpt", True), json=payload, timeout=self._timeout_for("eval"))
        raw_payload = self._read_json(response)
        self._raise_for_payload(response, raw_payload)
        content = raw_payload.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Evaluator returned invalid JSON.") from exc
        dimensions: dict[str, EvalDimension] = {}
        for key in DIM_KEYS:
            item = data.get("dimensions", {}).get(key, {})
            score = int(item.get("score", 0) or 0)
            note = str(item.get("note") or ("Adequate." if score >= 7 else "Needs improvement."))
            dimensions[key] = EvalDimension(score=score, note=note)
        strengths = [str(item) for item in data.get("strengths", []) if str(item).strip()]
        if not strengths:
            strengths = sorted(
                DIM_KEYS,
                key=lambda key: dimensions[key].score,
                reverse=True,
            )[:2]
            strengths = [f"{DIM_LABELS[key]} ({dimensions[key].score}/10)" for key in strengths]
        weaknesses = [str(item) for item in data.get("weaknesses", []) if str(item).strip()]
        if not weaknesses:
            weaknesses = sorted(DIM_KEYS, key=lambda key: dimensions[key].score)[:2]
            weaknesses = [f"{DIM_LABELS[key]} ({dimensions[key].score}/10)" for key in weaknesses]
        usage = self._extract_usage(raw_payload)
        stored_payload = copy.deepcopy(raw_payload)
        stored_payload["_request"] = redacted_request
        return EvalResult(
            overall_score=float(data.get("overall_score", 0) or 0),
            dimensions=dimensions,
            strengths=strengths,
            weaknesses=weaknesses,
            summary=str(data.get("summary") or "See dimension notes."),
            finish_reason=str(raw_payload.get("choices", [{}])[0].get("finish_reason", "unknown")),
            cv_augmented=bool(cv_summary),
            usage=usage,
            raw_payload=stored_payload,
        )


def image_data_url(mime_type: str, image_b64: str) -> str:
    return f"data:{mime_type};base64,{image_b64}"
