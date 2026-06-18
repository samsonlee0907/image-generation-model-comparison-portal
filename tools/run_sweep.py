#!/usr/bin/env python3
"""One-shot full-matrix sweep runner for the comparison portal.

Instead of clicking through the console for every theme, quality tier, and test
type, this script drives the portal's own services layer headlessly and writes
the results straight into the ``portal-exports/`` tree that
``tools/aggregate_report.py`` reads by default.

For every requested quality tier it runs the four image-generation themes and
the four image-edit scenarios; the content-safety set of tests is run once (its
prompts do not depend on the image quality tier). FLUX safety probes explicitly
send Black Forest Labs' documented default ``safety_tolerance=2`` so Azure
omitted-parameter behavior does not affect the safety comparison. Each run is
exported into the matching ``portal-exports/<generation|edit|safety>/`` sub-folder.

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
    python tools/run_sweep.py --clean              # archive prior runs, then sweep fresh
    python tools/run_sweep.py --dry-run            # print the plan, run nothing

The saved portal config (``~/.image_generation_model_comparison_portal/config.json``)
and its enabled models are reused. ``--reference`` overrides the source image for
the edit scenarios (default: ``test-reports/results/ImageEditTest/ReferenceImage.png``).
"""

from __future__ import annotations

import argparse
import base64
import shutil
import sys
import time
from datetime import datetime, timezone
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
DEFAULT_MISSING_RETRY_ATTEMPTS = 6
DEFAULT_MISSING_RETRY_DELAY = 1.5

# Where the portal writes its run exports, and where --clean moves prior runs.
EXPORT_ROOT = REPO_ROOT / "portal-exports"
EXPORT_CATEGORIES = ("generation", "edit", "safety")
ARCHIVE_ROOT = REPO_ROOT / "portal-exports-archive"


def _has_quality_knob(model: dict) -> bool:
    return (model.get("family") or "").strip() in QUALITY_KNOB_FAMILIES


def _clean_exports(dry_run: bool = False) -> None:
    """Move any existing portal-exports run folders into a timestamped archive.

    The aggregated report globs ``portal-exports/**/results.json`` recursively, so
    leaving older runs in place would mix model sets (e.g. a 4-model run alongside
    a fresh 6-model run). This archives prior runs *outside* the results tree so a
    sweep starts from a clean slate without deleting anything.
    """
    pending: list[tuple[str, Path]] = []
    for category in EXPORT_CATEGORIES:
        cat_dir = EXPORT_ROOT / category
        if not cat_dir.is_dir():
            continue
        for child in sorted(cat_dir.iterdir()):
            pending.append((category, child))

    if not pending:
        print("Clean data : portal-exports already empty — nothing to archive.")
        # Still ensure the category folders exist for the upcoming run.
        if not dry_run:
            for category in EXPORT_CATEGORIES:
                (EXPORT_ROOT / category).mkdir(parents=True, exist_ok=True)
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    dest_root = ARCHIVE_ROOT / stamp
    counts: dict[str, int] = {}
    for category, child in pending:
        counts[category] = counts.get(category, 0) + 1
    summary = ", ".join(f"{counts[c]} {c}" for c in EXPORT_CATEGORIES if counts.get(c))
    if dry_run:
        print(f"Clean data : would archive {len(pending)} run folder(s) ({summary}) -> "
              f"{dest_root.relative_to(REPO_ROOT)}")
        return

    print(f"Clean data : archiving {len(pending)} run folder(s) ({summary}) -> "
          f"{dest_root.relative_to(REPO_ROOT)}")
    for category, child in pending:
        target_dir = dest_root / category
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(child), str(target_dir / child.name))
    # Recreate empty category folders so the run writes into a fresh tree.
    for category in EXPORT_CATEGORIES:
        (EXPORT_ROOT / category).mkdir(parents=True, exist_ok=True)


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


def _missing_generation_models(run: dict) -> list[str]:
    missing: list[str] = []
    results = run.get("results") or {}
    for name in run.get("order") or []:
        row = results.get(name) or {}
        if not row.get("generation"):
            missing.append(name)
    return missing


def _retry_missing_images(
    runs: RunManager,
    run_id: str,
    config: AppConfig,
    timeout: float,
    retry_attempts: int,
    retry_delay: float,
) -> dict:
    run = runs.get_run(run_id)
    missing = _missing_generation_models(run)
    if not missing or retry_attempts <= 0:
        return run

    cfg = config.to_dict()
    for attempt in range(1, retry_attempts + 1):
        if not missing:
            break
        print(
            f"  retry pass {attempt}/{retry_attempts}: missing image for "
            + ", ".join(missing),
            flush=True,
        )
        for model_name in list(missing):
            row = (run.get("results") or {}).get(model_name) or {}
            status = row.get("status") or "Unknown"
            err = row.get("error")
            detail = f" ({err})" if err else ""
            print(f"    - retry {model_name}: {status}{detail}", flush=True)
            runs.retry_generation(run_id, cfg, model_name)
            run = _wait_for_run(runs, run_id, timeout)
            if retry_delay > 0:
                time.sleep(retry_delay)
        run = runs.get_run(run_id)
        missing = _missing_generation_models(run)
    return run


def _run_generation(
    runs: RunManager,
    config: AppConfig,
    models: list[dict],
    preset_key: str,
    quality: str,
    timeout: float,
    retry_attempts: int,
    retry_delay: float,
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
    final_run = _retry_missing_images(runs, run_id, config, timeout, retry_attempts, retry_delay)
    missing = _missing_generation_models(final_run)
    if missing:
        raise RuntimeError(
            f"Missing generated image after retries ({len(missing)} model(s)): {', '.join(missing)}"
        )
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
    retry_attempts: int,
    retry_delay: float,
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
    final_run = _retry_missing_images(runs, run_id, config, timeout, retry_attempts, retry_delay)
    missing = _missing_generation_models(final_run)
    if missing:
        raise RuntimeError(
            f"Missing generated image after retries ({len(missing)} model(s)): {', '.join(missing)}"
        )
    return runs.export_results(run_id)


def _run_safety(runs: RunManager, config: AppConfig, models: list[dict], timeout: float) -> dict:
    payload = {"config": config.to_dict(), "models": models, "promptIds": []}
    run_id = runs.create_safety_run(payload)["runId"]
    _wait_for_run(runs, run_id, timeout)
    return runs.export_results(run_id)


def _print_plan(
    qualities: list[str],
    skip_edit: bool,
    skip_safety: bool,
    models: list[dict],
    best_tier: str | None,
    multi_tier: bool,
    retry_attempts: int,
) -> None:
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
        print("  safety      : full set of tests (run once; FLUX sends BFL default safety_tolerance=2)")
    print(f"  Retries     : up to {retry_attempts} extra pass(es) for any model missing image output")
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
    parser.add_argument("--skip-safety", action="store_true", help="Skip the content-safety tests.")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Archive any existing portal-exports run folders into portal-exports-archive/<UTC stamp>/ "
             "before the sweep, so the report is built only from this fresh run (non-destructive).",
    )
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
    parser.add_argument(
        "--retry-missing-attempts",
        type=int,
        default=DEFAULT_MISSING_RETRY_ATTEMPTS,
        help=f"Retry passes for models that finish without a generated image (default: {DEFAULT_MISSING_RETRY_ATTEMPTS}).",
    )
    parser.add_argument(
        "--retry-missing-delay",
        type=float,
        default=DEFAULT_MISSING_RETRY_DELAY,
        help=f"Seconds to pause between per-model retries (default: {DEFAULT_MISSING_RETRY_DELAY}).",
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

    _print_plan(
        qualities,
        args.skip_edit,
        args.skip_safety,
        models,
        best_tier,
        multi_tier,
        max(0, int(args.retry_missing_attempts)),
    )
    if args.clean:
        _clean_exports(dry_run=args.dry_run)
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
                    result = _run_generation(
                        runs,
                        config,
                        tier_models,
                        preset_key,
                        quality,
                        args.poll_timeout,
                        max(0, int(args.retry_missing_attempts)),
                        max(0.0, float(args.retry_missing_delay)),
                    )
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
                            max(0, int(args.retry_missing_attempts)),
                            max(0.0, float(args.retry_missing_delay)),
                        )
                        print(f"  exported -> {result.get('folder')}")
                        exports.append(result.get("folder", ""))
                    except Exception as exc:  # noqa: BLE001
                        print(f"  FAILED: {exc}", file=sys.stderr)
                        failures.append(label)
        if not args.skip_safety:
            print("\n=== safety (full set of tests) ===", flush=True)
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
