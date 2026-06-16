# Image Generation Model Comparison Portal

Image Generation Model Comparison Portal is an application for comparing image generation models side by side. It supports both text-to-image and image-edit workflows, benchmark prompt generation, concurrent evaluation, bounding-box visualization, a dedicated content-safety probe, and PPTX report export.

Models are onboarded **flexibly**: instead of choosing from a fixed list of hard-coded type + version
pairs, you pick a routing **family** and enter your own deployment / model identifier — so new models
such as `MAI-Image-2.5` work without any code change.

## What It Does

- Compares multiple image-generation deployments in one run.
- Lets you add any model by routing **family** + free-text deployment (with optional endpoint / API-version / path overrides).
- Supports text-to-image and image-edit benchmarking.
- Generates benchmark prompts and allows prompt refinement before execution.
- Runs generation, CV analysis, and evaluator scoring concurrently.
- Scores image quality on a **benchmark-aligned, data-driven** metric set (GenEval / T2I-CompBench / DPG-Bench axes).
- Provides a separate **Content Safety** probe that tests model gating across severity tiers and moderates produced images with Azure AI Content Safety.
- Draws bounding boxes from CV output and lets users toggle them on or off.
- Provides retry actions for failed image generations.
- Exports generated images and evaluation results to PPTX.

## Documentation

- [Model Routing](docs/MODEL_ROUTING.md) — how each family routes its API path + request body, and how to add models/families.
- [Image Quality Evaluation](docs/IMAGE_QUALITY_EVALUATION.md) — original methodology plus the refreshed, benchmark-aligned metrics.
- [Content Safety Evaluation](docs/CONTENT_SAFETY_EVALUATION.md) — the severity-tiered safety probe and Azure AI Content Safety moderation.

## Evaluation Dimensions

Each generated image is scored on a **data-driven set of dimensions**, with an integer score from **1 to 10** for each dimension, plus an **overall score**, notes, strengths, weaknesses, and a summary. The dimensions are aligned with widely used public text-to-image benchmarks (GenEval, T2I-CompBench, DPG-Bench) and can be expanded without code changes to routing or UI. See [Image Quality Evaluation](docs/IMAGE_QUALITY_EVALUATION.md) for the full list, benchmark provenance, and how the original 10-dimension methodology maps onto the current set.

## Requirements

- Python 3.11 or newer
- Access to Microsoft Foudnry to provision image generation model endpoints
- One evaluator deployment for benchmark generation and scoring. (e.g. GPT-5.4)
- Optional Azure AI Vision endpoint and key if you want CV analysis from a separate resource.
- One or more image-generation deployments to compare.

## Install And Run

Running on Windows:
```powershell
git clone https://github.com/samsonlee0907/foundry-model-upgrade-benchmark-tool.git
cd foundry-model-upgrade-benchmark-tool
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m image_generation_model_comparison_portal.main
```

Running on Mac/Linux:
```sh
git clone https://github.com/samsonlee0907/foundry-model-upgrade-benchmark-tool.git
cd foundry-model-upgrade-benchmark-tool
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m image_generation_model_comparison_portal.main
```

The app starts a local server and opens in your browser automatically.

## Configure The App

Set these values before starting a comparison:

- `Resource Endpoint`
  Your Azure AI Foundry or Azure OpenAI endpoint.
- `API Key`
  The credential for that endpoint.
- `Evaluator LLM`
  The model used to generate benchmark prompts and score image quality.
- `CV Endpoint` and `CV API Key`
  Optional if you want to use a separate Azure AI Vision resource.
- `Content Safety Endpoint`, `Content Safety Key`, `Content Safety API Version`
  Optional Azure AI Content Safety resource used by the Content Safety probe to moderate produced images and prompt text. Defaults to API version `2024-09-01`.
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
3. Paint the edit mask directly in the built-in mask panel.
4. Enter the edit prompt or generate a benchmark prompt.
5. Click `Generate Edit and Compare`.

![Image Edit Workflow](img/image-edit-workflow.png)

## Content Safety Flow

1. Open the `Content Safety` tab.
2. Select the severity-tiered (L1–L5) prompts to probe across the Hate / Sexual / Violence / Self-Harm categories.
3. Optionally enable `Also scan prompt text`.
4. Click `Run Content Safety Probe`.
5. For each model × prompt the portal reports whether the model **gated** the request or **produced** an image, and moderates any produced image with Azure AI Content Safety (per-category severities).

See [Content Safety Evaluation](docs/CONTENT_SAFETY_EVALUATION.md) for the probe design, severity scale, and responsible-use notes.

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
