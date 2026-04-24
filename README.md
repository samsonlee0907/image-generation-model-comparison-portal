# Image Generation Model Comparison Portal

Image Generation Model Comparison Portal is an application for comparing image generation models side by side. It supports both text-to-image and image-edit workflows, benchmark prompt generation, concurrent evaluation, bounding-box visualization, and PPTX report export.

## What It Does

- Compares multiple image-generation deployments in one run.
- Supports text-to-image and image-edit benchmarking.
- Generates benchmark prompts and allows prompt refinement before execution.
- Runs generation, CV analysis, and evaluator scoring concurrently.
- Draws bounding boxes from CV output and lets users toggle them on or off.
- Provides retry actions for failed image generations.
- Exports generated images and evaluation results to PPTX.

## Requirements

- Python 3.11 or newer
- Access to Microsoft Foudnry to provision image generation model endpoints
- One evaluator deployment for benchmark generation and scoring. (e.g. GPT-5.4)
- Optional Azure AI Vision endpoint and key if you want CV analysis from a separate resource.
- One or more image-generation deployments to compare.

## Install And Run

The commands below assume a standard shell environment and a clone under your home directory.

```sh
git clone https://github.com/samsonlee0907/image-generation-model-comparison-portal.git
cd image-generation-model-comparison-portal
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
image-generation-model-comparison-portal
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
- Model rows
  Enable the image-generation deployments you want to compare and enter their deployment names.

![Portal Config](img/portal-config.png)

- `Models`
  Choose the models that you'd like to compare across (provided that your endpoints have been created in Microsoft Foundry) through selecting the right models by name and enter the deployment name created.

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
