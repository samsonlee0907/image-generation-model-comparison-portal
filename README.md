# Image Generation Model Comparison Portal

Image Generation Model Comparison Portal is an application for comparing image generation models side by side. It supports both text-to-image and image-edit workflows, benchmark prompt generation, concurrent evaluation, bounding-box visualization, a dedicated content-safety probe, and PPTX report export.

Models are onboarded **flexibly**: instead of choosing from a fixed list of hard-coded type + version
pairs, you pick a routing **family** and enter your own deployment / model identifier — so new models
such as `MAI-Image-2.5` work without any code change.

> 📊 **See the models compared:** read the latest [aggregated comparison report](test-reports/aggregate-report.md) for a quick, GitHub-rendered view of how every model behaves on image-generation quality, content safety, pricing, and capacity — no download required.

## What It Does

- Compares multiple image-generation deployments in one run.
- Lets you add any model by routing **family** + free-text deployment (with optional endpoint / API-version / path overrides).
- Supports text-to-image and image-edit benchmarking.
- Generates benchmark prompts and allows prompt refinement before execution.
- Runs generation, CV analysis, and evaluator scoring concurrently.
- Scores image quality on a **benchmark-aligned, data-driven** metric set (GenEval / T2I-CompBench / DPG-Bench axes).
- Provides a separate **Content Safety** probe that observes each model's baseline gating behavior across severity tiers (does the model produce an image or block the request).
- Lets you **customize the content-safety prompt set** — rewrite the whole set or edit a single prompt with a descriptive instruction, driven by an optional dedicated **prompt-modification model** (falls back to the evaluator LLM).
- Draws bounding boxes from CV output and lets users toggle them on or off.
- Provides retry actions for failed image generations, plus a per-cell **Retry** on individual content-safety error cards.
- Exports generated images and evaluation results to PPTX, plus a dedicated **content-safety review PPTX** (severity legend, per-model outcome matrix, and the produced images for human review).
- Exports generated images plus a `results.json` manifest to a local folder for notebook analysis.
- Exports content-safety probe outcomes (gating results + ungated images) to a `safety-results.json` manifest.
- Aggregates exported generation, image-edit, and **content-safety** runs into one [comparison report](test-reports/aggregate-report.md) (self-contained HTML + GitHub-readable Markdown) via `tools/aggregate_report.py`.
- Runs the **whole matrix headlessly** (generation + edit across quality tiers, plus safety once) with `tools/run_sweep.py`, exporting straight into the report-ready `portal-exports/` layout.
- Retries rate-limited (HTTP 429, 60s backoff) and transient (502/503/504, dropped connections, timeouts; short backoff) requests automatically.

## Documentation

- [Model Routing](docs/MODEL_ROUTING.md) — how each family routes its API path + request body, and how to add models/families.
- [Image Quality Evaluation](docs/IMAGE_QUALITY_EVALUATION.md) — the 13-dimension, benchmark-aligned metric set (GenEval / T2I-CompBench / DPG-Bench axes).
- [Content Safety Evaluation](docs/CONTENT_SAFETY_EVALUATION.md) — the severity-tiered probe that observes each model's baseline content-safety gating behavior.

## Evaluation Dimensions

Each generated image is scored on a **data-driven set of 13 dimensions**, with an integer score from **1 to 10** for each dimension, plus an **overall score**, notes, strengths, weaknesses, and a summary. The dimensions are aligned with widely used public text-to-image benchmarks (GenEval, T2I-CompBench, DPG-Bench) and can be expanded without code changes to routing or UI. See [Image Quality Evaluation](docs/IMAGE_QUALITY_EVALUATION.md) for the full list and benchmark provenance.

## Requirements

- Python 3.11 or newer
- Access to Microsoft Foudnry to provision image generation model endpoints
- One evaluator deployment for benchmark generation and scoring. (e.g. GPT-5.4)
- Optional Azure AI Vision endpoint and key if you want CV analysis from a separate resource.
- One or more image-generation deployments to compare.

## Install And Run

Running on Windows PowerShell:
```powershell
git clone https://github.com/samsonlee0907/image-generation-model-comparison-portal.git
cd image-generation-model-comparison-portal
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
image-generation-model-comparison-portal
```

If PowerShell blocks `.venv\Scripts\Activate.ps1`, run this once and then activate the environment again:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Running on macOS/Linux:
```sh
git clone https://github.com/samsonlee0907/image-generation-model-comparison-portal.git
cd image-generation-model-comparison-portal
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
image-generation-model-comparison-portal
```

The app starts a local server and opens in your browser automatically. After installation, the module form also works on every platform:

```sh
python -m image_generation_model_comparison_portal.main
```

## Configure The App

Set these values before starting a comparison:

- `Resource Endpoint`
  Your Azure AI Foundry or Azure OpenAI endpoint.
- `API Key`
  The credential for that endpoint.
- `Evaluator LLM`
  The model used to generate benchmark prompts and score image quality. A GPT-5.x
  reasoning deployment (e.g. GPT-5.4) is recommended; the app sends
  `reasoning_effort=high` and omits `temperature` for reasoning models.
- `Prompt modification model` *(optional)*
  A dedicated deployment used for prompt generation/refinement and content-safety
  prompt regeneration. Leave blank to reuse the Evaluator LLM.
- `CV Endpoint` and `CV API Key`
  Optional if you want to use a separate Azure AI Vision resource.
- Model rows
  Enable the image-generation deployments you want to compare. For each row pick a **Family** (GPT-Image, FLUX, MAI-Image, or Custom) and enter your **deployment / model identifier**. Use **Advanced** to override the endpoint, API version, request path, or body model id per model.

![Portal Config](img/portal-config.png)

- `Models`
  Add a row per model, choose its routing family, and type the deployment/model name created in Microsoft Foundry (or any compatible endpoint). New models — including versions the app has never seen, like `MAI-Image-2.5` — are onboarded just by typing the name; no code change is needed. See [Model Routing](docs/MODEL_ROUTING.md) for how each family routes its requests.

![Model Selection](img/portal-model-selection.png)

## Text-To-Image Flow

1. Open the `Text to Image` tab.
2. Enter a prompt directly or use `Generate Benchmark`.
3. Optionally use the sample benchmark helpers.
![Text to Image Workflow](img/text-to-image-workflow.png)
4. Click `Generate and Compare`.
5. Review the generated image grid and evaluation output.


## Image Edit Flow

1. Open the `Image Edit` tab.
2. Upload a source image.
3. Paint the edit mask directly in the built-in mask panel. **The mask only applies to `gpt-image`,
   which supports true mask-based inpainting.** FLUX and MAI edits are instruction/reference-based and
   ignore the mask, so describe the change fully in the prompt.
4. Enter the edit prompt or load one of the edit scenario presets — **Style Change** (realistic →
   painting, retain all details), **Add Tagline Text** (overlay a Microsoft Foundry tagline, retain
   all details), **Object + Background** (keep a target object, replace only the background), or
   **Business Attire** (restyle people's clothing to business formal, keep identities and scene).
5. Click `Generate Edit and Compare`.

Edit support by family: `gpt-image` (mask inpainting), `flux` (instruction/reference, no mask), and
`mai` (instruction edit on `MAI-Image-2.5` / `2.5-Flash` and newer; `MAI-Image-2` / `2e` fall back to
text-to-image). See [`docs/MODEL_ROUTING.md`](docs/MODEL_ROUTING.md) for the per-family edit routes.

When auto-evaluation is enabled for an edit run, the evaluator LLM receives **both** the original
source image and each model's edited result, so it can score how faithfully the requested change was
applied **and** how well the original details, objects, identities, and context were retained.

![Image Edit Workflow](img/image-edit-workflow.png)

## Content Safety Flow

1. Open the `Content Safety` tab.
2. (Optional) Use **Customize Safety Prompts** to tailor the prompt set: type a descriptive instruction and **Regenerate All Prompts**, or press **Edit** on a single prompt to revise just that cell. The prompt-modification model is used (falling back to the evaluator LLM); the severity ladder, categories, and levels are preserved. **Reset to Defaults** restores the built-in prompt set.
3. Select the severity-tiered (L1–L5) prompts to probe across the Hate / Sexual / Violence / Self-Harm categories.
4. Click `Run Content Safety Probe`.
5. For each model × prompt the portal reports the model's **baseline behavior** — whether the model **gated** the request (input or output filtered) or **produced** an image. No external moderation service is called; the signal is the model's own default guardrails.
6. Use `Export PPTX Report` on the safety panel to build a **human-review deck**: a severity legend, a per-model `category × level` outcome matrix, and the actually-produced images so a reviewer can judge whether produced content is appropriate.

See [Content Safety Evaluation](docs/CONTENT_SAFETY_EVALUATION.md) for the probe design, severity tiers, and responsible-use notes.

## Results And Analysis

After a run, the portal shows:

- generated images
- CV and evaluator summaries
- per-dimension scoring
- radar visualization
- bounding box overlays
- retry actions for failed runs
![Text to Image Workflow Result](img/text-to-image-workflow-result.png)
![Results Analysis](img/results-analysis.png)

## PPTX Reporting

Use `Export PPTX Report` to generate a presentation containing the run prompt, generated images, and evaluation results.

![PPTX Report Export](img/pptx-report-export.png)

## Exporting Images + JSON

Use `Export Images + JSON` to write the run's generated images to a local
folder together with a single machine-readable manifest for downstream
analysis (e.g. a Python notebook that aggregates multiple iterations).

Each export is written to `portal-exports/<category>/<timestamp>-<runId>/`,
where `<category>` is `generation` or `edit` (chosen from the run mode) so the
three test types land in separate trees the report tool can scan directly:

```
portal-exports/generation/20240101-120000-abc123/
  results.json          # run metadata + one record per model
  images/<model>.png    # one file per produced image
```

`results.json` schema (`schemaVersion: 1`):

- `runId`, `exportedAt`, `mode`, `modeLabel` — run identity and category
  (`Text-to-Image` / `Image Edit`).
- `prompt`, `effectivePrompt`, `promptGuidance` — the prompt actually sent.
- `config` — run configuration with any API keys redacted.
- `results[]` — per model: `model` (keys redacted), `status`, `error`,
  `imagePath` (relative path into `images/`, or `null` when no image was
  produced), `imageMimeType`, `metrics`, `generation` (request/response/url),
  `cv`, and `evaluation` (per-dimension scores). Joining `imagePath` to the
  scores in the same record lets a notebook line up each image with its
  metrics across runs.

The `portal-exports/` folder is git-ignored.

## Exporting Content-Safety Results

When viewing a content-safety probe, use `Export Results + JSON` on the safety
panel to write the gating outcomes to a local folder for analysis. Because a
safety run probes each model with a set of escalating-severity prompts
(rather than a single benchmark image), it gets its own manifest and only saves
the images that models actually produced (i.e. did **not** gate).

Each export is written to `portal-exports/safety/safety-<timestamp>-<runId>/`:

```
portal-exports/safety/safety-20240101-120000-abc123/
  safety-results.json                  # per model x per prompt outcomes
  images/<model>__<promptId>.png       # only for ungated ("Produced") cells
```

`safety-results.json` schema (`schemaVersion: 1`, `kind: "safety"`):

- `runId`, `exportedAt`, `models` — run identity and the models probed.
- `summary` — `total`, `gated`, `produced`, `error` counts across all cells.
- `config` — run configuration with any API keys redacted.
- `results[]` — per model x prompt cell: `model` (keys redacted), `promptId`,
  `category`, `level`, `levelLabel` (`L1`-`L5`, or `L5+` for the adversarial
  tier), `label`, `technique`, `prompt`, `expectation`, `status`, `outcome`
  (`blocked` / `generated` / `error`), `blocked`, `blockReason`, `error`, and
  `imagePath` (relative path into `images/`, or `null` for gated/errored cells).

The `portal-exports/` folder is git-ignored.

## Automated Sweep

Instead of clicking through the console for every theme, quality tier, and test
type, run the whole matrix headlessly with `tools/run_sweep.py`. It drives the
portal's own services layer using your saved config + enabled models and writes
results straight into the report-ready `portal-exports/` layout.

```
python tools/run_sweep.py                   # low + medium + high generation/edit, safety once
python tools/run_sweep.py --qualities high  # only the high tier
python tools/run_sweep.py --skip-edit       # generation + safety only
python tools/run_sweep.py --skip-safety     # generation + edit only
python tools/run_sweep.py --dry-run         # print the plan, run nothing
```

For each requested quality tier it runs the four generation themes and the four
edit scenarios; the content-safety tests run once (its prompts do not depend
on the image quality tier). Evaluation is forced on so the runs carry scores.
The edit scenarios use `test-reports/results/ImageEditTest/ReferenceImage.png`
as the source image by default — override with `--reference <path>`. When the
sweep finishes, build the aggregated report with `tools/aggregate_report.py`
(which reads `portal-exports/` by default).



Generation, image-edit, and content-safety requests automatically retry two
classes of transient failure before surfacing an error:

- **Rate limits** (HTTP 429 / throttling). Azure image rate limits are enforced
  per minute, so the app waits a fixed 60 seconds between attempts, up to 5
  retries. While waiting, the affected result card shows a
  `Rate limited, waiting 60s (n/5)` status.
- **Transient transport / server errors** (HTTP 502/503/504, dropped or reset
  connections, timeouts). These usually clear within seconds, so the app retries
  quickly (8 seconds apart, up to 5 times) and shows a
  `Service busy, retrying 8s (n/5)` status. FLUX endpoints in particular can
  return 503 during cold-start/overload, so the extra attempts give them time to
  recover.

Content-safety gates and other permanent errors are never retried. Safety probes
additionally run one request at a time per model (four model tracks in parallel)
to avoid flooding a shared endpoint.

If a safety probe still ends in an error after the automatic retries (e.g. a
model that stays unavailable for minutes), each errored result card shows a
**Retry** button that re-probes just that one model/prompt cell on demand.
