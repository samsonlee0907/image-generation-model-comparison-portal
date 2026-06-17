#!/usr/bin/env python3
"""One-shot full-matrix sweep runner for the comparison portal.

Instead of clicking through the console for every theme, quality tier, and test
type, this script drives the portal's own services layer headlessly and writes
the results straight into the ``portal-exports/`` tree that
``tools/aggregate_report.py`` reads by default.

For every requested quality tier it runs the four image-generation themes and
the four image-edit scenarios; the content-safety battery is run once (its
prompts do not depend on the image quality tier). Each run is exported into the
matching ``portal-exports/<generation|edit|safety>/`` sub-folder.

Models whose routing family exposes no quality control (e.g. MAI-Image) send a
byte-identical request at every tier, so the sweep generates them only **once** —
at the best-effort (highest requested) tier, which is where the aggregated report
judges every model — instead of redundantly re-generating them for each tier.
Models with a quality knob (GPT-Image, FLUX) are swept across all tiers.

Usage::

    python tools/run_sweep.py                      # low, medium, high + edits + safety
    python tools/run_sweep.py --qualities high     # only the high tier
    python tools/run_sweep.py --skip-edit          # generation + safety only
    python tools/run_sweep.py --skip-safety        # generation + edit only
    python tools/run_sweep.py --dry-run            # print the plan, run nothing

The saved portal config (``~/.image_generation_model_comparison_portal/config.json``)
and its enabled models are reused. ``--reference`` overrides the source image for
the edit scenarios (default: ``test-reports/results/ImageEditTest/ReferenceImage.png``).
"""

from __future__ import annotations

import argparse
import base64
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from image_generation_model_comparison_portal.config import load_config  # noqa: E402
from image_generation_model_comparison_portal.models import (  # noqa: E402
    AppConfig,
    BENCHMARK_PRESETS,
    sample_models,
)
from image_generation_model_comparison_portal.webapp import RunManager  # noqa: E402

GENERATION_PRESETS = ["watchmaker", "cartoon_3d", "storyboard_comic", "data_chart"]
EDIT_PRESETS = [
    "edit_style_change",
    "edit_add_text",
    "edit_object_background",
    "edit_business_attire",
]
QUALITY_ALIASES = {"mid": "medium", "med": "medium"}
VALID_QUALITIES = ("low", "medium", "high")
QUALITY_RANK = {"low": 0, "medium": 1, "high": 2}
# Families that expose a quality control the sweep can turn up tier-by-tier.
# Mirrors QUALITY_KNOB_FAMILIES in tools/aggregate_report.py. Families NOT listed
# here (e.g. MAI-Image) send an identical request at every tier, so the sweep
# generates them only once instead of once per tier.
QUALITY_KNOB_FAMILIES = {"gpt-image", "flux"}
DEFAULT_REFERENCE = REPO_ROOT / "test-reports" / "results" / "ImageEditTest" / "ReferenceImage.png"
DEFAULT_POLL_TIMEOUT = 1200  # seconds per run


def _has_quality_knob(model: dict) -> bool:
    return (model.get("family") or "").strip() in QUALITY_KNOB_FAMILIES


def _normalize_quality(value: str) -> str:
    value = value.strip().lower()
    value = QUALITY_ALIASES.get(value, value)
    if value not in VALID_QUALITIES:
        raise argparse.ArgumentTypeError(
            f"Unsupported quality '{value}'. Choose from {', '.join(VALID_QUALITIES)} (mid = medium)."
        )
    return value


def _data_url(path: Path) -> str:
    raw = path.read_bytes()
    suffix = path.suffix.lower()
    mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _enabled_models(config: AppConfig) -> list[dict]:
    return [model.to_dict() for model in config.models if model.enabled]


def _wait_for_run(runs: RunManager, run_id: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        run = runs.get_run(run_id)
        if run.get("status") != "running":
            return run
        if time.monotonic() > deadline:
            raise TimeoutError(f"Run {run_id} did not finish within {timeout:.0f}s.")
        time.sleep(2.0)


def _run_generation(
    runs: RunManager,
    config: AppConfig,
    models: list[dict],
    preset_key: str,
    quality: str,
    timeout: float,
) -> dict:
    preset = BENCHMARK_PRESETS[preset_key]
    payload = {
        "config": config.to_dict(),
        "mode": "text",
        "prompt": preset["prompt"],
        "models": models,
        "promptGuidance": {"title": preset["title"], "dimensionMap": preset.get("dim_map", {})},
        "textSize": "1024x1024",
        "textQuality": quality,
        "outputFormat": "png",
    }
    run_id = runs.create_run(payload)["runId"]
    _wait_for_run(runs, run_id, timeout)
    return runs.export_results(run_id)


def _run_edit(
    runs: RunManager,
    config: AppConfig,
    models: list[dict],
    preset_key: str,
    quality: str,
    reference_data_url: str,
    reference_name: str,
    timeout: float,
) -> dict:
    preset = BENCHMARK_PRESETS[preset_key]
    payload = {
        "config": config.to_dict(),
        "mode": "edit",
        "prompt": preset["prompt"],
        "models": models,
        "promptGuidance": {"title": preset["title"], "dimensionMap": preset.get("dim_map", {})},
        "editSize": "1024x1024",
        "textQuality": quality,
        "outputFormat": "png",
        "sourceFiles": [{"name": reference_name, "dataUrl": reference_data_url}],
    }
    run_id = runs.create_run(payload)["runId"]
    _wait_for_run(runs, run_id, timeout)
    return runs.export_results(run_id)


def _run_safety(runs: RunManager, config: AppConfig, models: list[dict], timeout: float) -> dict:
    payload = {"config": config.to_dict(), "models": models, "promptIds": []}
    run_id = runs.create_safety_run(payload)["runId"]
    _wait_for_run(runs, run_id, timeout)
    return runs.export_results(run_id)


def _print_plan(qualities: list[str], skip_edit: bool, skip_safety: bool,
                models: list[dict], best_tier: str | None, multi_tier: bool) -> None:
    def names(subset: list[dict]) -> str:
        return ", ".join(m.get("name") or m.get("deployment") or "model" for m in subset) or "(none)"

    knob = [m for m in models if _has_quality_knob(m)]
    fixed = [m for m in models if not _has_quality_knob(m)]
    print("Sweep plan")
    print(f"  Models      : {names(models)}")
    print(f"  Qualities   : {', '.join(qualities)}")
    if multi_tier and fixed:
        print(f"  Quality knob: {names(knob)} - swept low->high")
        print(f"  No knob      : {names(fixed)} - generated once at '{best_tier}' (identical request per tier)")
    gen_cells = 0
    edit_cells = 0
    for quality in qualities:
        members = models if (not multi_tier or quality == best_tier) else knob
        if not members:
            print(f"  [{quality}] generation: (skipped — no models with a quality knob)")
            continue
        gen_cells += len(GENERATION_PRESETS) * len(members)
        print(f"  [{quality}] generation: {', '.join(GENERATION_PRESETS)} x [{names(members)}]")
        if not skip_edit:
            edit_cells += len(EDIT_PRESETS) * len(members)
            print(f"  [{quality}] edit      : {', '.join(EDIT_PRESETS)} x [{names(members)}]")
    if not skip_safety:
        print("  safety      : full battery (run once)")
    print(f"  Image cells : {gen_cells} generation, {edit_cells} edit "
          f"(each model that lacks a quality knob is generated once, not per tier)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--qualities",
        nargs="+",
        type=_normalize_quality,
        default=list(VALID_QUALITIES),
        help="Quality tiers to sweep for generation/edit (default: low medium high; 'mid' = medium).",
    )
    parser.add_argument("--skip-edit", action="store_true", help="Skip the image-edit scenarios.")
    parser.add_argument("--skip-safety", action="store_true", help="Skip the content-safety battery.")
    parser.add_argument(
        "--reference",
        type=Path,
        default=DEFAULT_REFERENCE,
        help="Source image for edit scenarios (default: test-reports/results/ImageEditTest/ReferenceImage.png).",
    )
    parser.add_argument(
        "--poll-timeout",
        type=float,
        default=DEFAULT_POLL_TIMEOUT,
        help=f"Seconds to wait for each run to finish (default: {DEFAULT_POLL_TIMEOUT}).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and exit without running.")
    args = parser.parse_args(argv)

    # De-duplicate qualities while preserving order.
    qualities: list[str] = []
    for quality in args.qualities:
        if quality not in qualities:
            qualities.append(quality)

    config = load_config()
    if config is None:
        print(
            "No saved portal config found. Open the portal once to configure your endpoint,\n"
            "secret, evaluator LLM and models, then re-run the sweep.",
            file=sys.stderr,
        )
        return 2
    # The aggregated report needs evaluation scores, so force auto-eval on for the sweep.
    config.auto_eval = "yes"

    models = _enabled_models(config)
    if not models:
        print("No enabled models in the saved config. Enable at least one model first.", file=sys.stderr)
        return 2

    # Split the enabled models by whether they expose a quality control. Models
    # without one (e.g. MAI-Image) send an identical request at every tier, so we
    # generate them only once — at the best-effort (highest requested) tier, which
    # is where the aggregated report judges every model. Knob-capable models are
    # swept across all requested tiers.
    multi_tier = len(qualities) > 1
    best_tier = max(qualities, key=lambda q: QUALITY_RANK.get(q, 0)) if qualities else None
    knob_models = [m for m in models if _has_quality_knob(m)]

    def models_for(quality: str) -> list[dict]:
        if not multi_tier or quality == best_tier:
            return models
        return knob_models

    need_edit = not args.skip_edit
    if need_edit and not args.reference.exists():
        print(f"Edit reference image not found: {args.reference}", file=sys.stderr)
        print("Pass --reference <path> or --skip-edit.", file=sys.stderr)
        return 2

    _print_plan(qualities, args.skip_edit, args.skip_safety, models, best_tier, multi_tier)
    if args.dry_run:
        return 0

    reference_data_url = _data_url(args.reference) if need_edit else ""
    reference_name = args.reference.name if need_edit else ""

    runs = RunManager()
    exports: list[str] = []
    failures: list[str] = []
    try:
        for quality in qualities:
            tier_models = models_for(quality)
            if not tier_models:
                print(f"\n=== generation @ {quality}: skipped (no models with a quality knob) ===", flush=True)
                continue
            for preset_key in GENERATION_PRESETS:
                label = f"generation/{preset_key} @ {quality}"
                print(f"\n=== {label} ===", flush=True)
                try:
                    result = _run_generation(runs, config, tier_models, preset_key, quality, args.poll_timeout)
                    print(f"  exported -> {result.get('folder')}")
                    exports.append(result.get("folder", ""))
                except Exception as exc:  # noqa: BLE001 - report and continue
                    print(f"  FAILED: {exc}", file=sys.stderr)
                    failures.append(label)
            if not args.skip_edit:
                for preset_key in EDIT_PRESETS:
                    label = f"edit/{preset_key} @ {quality}"
                    print(f"\n=== {label} ===", flush=True)
                    try:
                        result = _run_edit(
                            runs,
                            config,
                            tier_models,
                            preset_key,
                            quality,
                            reference_data_url,
                            reference_name,
                            args.poll_timeout,
                        )
                        print(f"  exported -> {result.get('folder')}")
                        exports.append(result.get("folder", ""))
                    except Exception as exc:  # noqa: BLE001
                        print(f"  FAILED: {exc}", file=sys.stderr)
                        failures.append(label)
        if not args.skip_safety:
            print("\n=== safety (full battery) ===", flush=True)
            try:
                result = _run_safety(runs, config, models, args.poll_timeout)
                print(f"  exported -> {result.get('folder')}")
                exports.append(result.get("folder", ""))
            except Exception as exc:  # noqa: BLE001
                print(f"  FAILED: {exc}", file=sys.stderr)
                failures.append("safety")
    finally:
        runs.shutdown()

    print("\nSweep complete.")
    print(f"  Exports : {len([item for item in exports if item])}")
    if failures:
        print(f"  Failures: {len(failures)} ({', '.join(failures)})", file=sys.stderr)
    print("\nBuild the aggregated report with:")
    print("  python tools/aggregate_report.py --out test-reports/aggregate-report.html \\")
    print("    --md-out test-reports/aggregate-report.md")
    print("(reads portal-exports/ by default)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
