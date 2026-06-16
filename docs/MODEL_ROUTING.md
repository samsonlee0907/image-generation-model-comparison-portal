# Model Routing

The portal no longer hard-codes a fixed list of model type + version pairs. Instead you onboard
**any** image-generation model by picking a **routing family** and entering your own deployment /
model identifier (plus optional endpoint / API-version / path overrides). This lets you add models
the app has never seen — for example `MAI-Image-2.5` — without any code change.

Routing is driven entirely by the registry in
[`src/image_generation_model_comparison_portal/providers.py`](../src/image_generation_model_comparison_portal/providers.py),
which is the single source of truth for the request URL, request body shape, auth header style, and
the response paths used to extract the produced image. The same registry powers the model dropdown in
the web UI and the per-family hints shown next to each model row.

## How a model row is routed

Each model row sends the following fields to the backend:

| Field | Required | Meaning |
| --- | --- | --- |
| `family` | yes | One of `gpt-image`, `flux`, `mai`, `custom`. Selects the routing rules below. |
| `deployment` | yes | The free-text identifier (Azure deployment name, FLUX model name, etc.). |
| `name` | no | Display name. Defaults to the deployment when blank. |
| `endpoint` | no | Per-model endpoint override. Falls back to the Global Endpoint. |
| `api_version` | no | Per-model API-version override. Falls back to the family default / global config. |
| `path` | no | Full request-path override (advanced / custom routes). |
| `model_id` | no | Value sent as `model` in the request body. Defaults to the deployment. |

Back-compat: configs saved by older versions only stored `{enabled, name, kind, deployment}`. On load,
`ModelConfig.__post_init__` derives the `family` from the legacy `kind` prefix
(`gpt-image*` → `gpt-image`, `flux*` → `flux`, `mai*` → `mai`), so existing setups keep working.

## Per-family differences

The families differ in **where the model is named** (URL path vs. request body), the **request body
schema**, the **auth header**, and **whether image edit is supported**.

### `gpt-image` — Azure OpenAI / Foundry

- **Generate URL:** `{endpoint}/openai/deployments/{deployment}/images/generations?api-version={api_version}`
- **Edit URL:** `{endpoint}/openai/deployments/{deployment}/images/edits?api-version={api_version}`
- **Routed by:** Azure **deployment name in the URL path**.
- **Auth:** `api-key: <key>` header.
- **Body:** JSON `{ model, prompt, n, quality, size }`; `gpt-image-2`+ also accepts `output_format`.
  Optional keys are dropped automatically on a `400` so older deployments still succeed.
- **Edit:** `multipart/form-data` with `image[]` and optional `mask`.
- **Response image:** `data[].b64_json`.
- **Supports edit:** yes.

### `flux` — Black Forest Labs

- **Generate / Edit URL:** `{endpoint}/providers/blackforestlabs/v1/{deployment}?api-version={api_version}`
- **Routed by:** the **Azure deployment name** in the URL path (e.g. `flux-2-pro` — lowercase, exactly
  as it appears in your endpoint URL). This is **not** the catalog name.
- **Auth:** sends both `api-key` and `Authorization: Bearer` (gateways accept either).
- **Body:** JSON `{ model, prompt, width, height, output_format, num_images }`. The body `model`
  defaults to the deployment name; if your gateway requires the **catalog** name (e.g. `FLUX.2-pro`),
  set it under **Advanced → Body model id**. Optional keys are progressively dropped on a `400`.
- **Edit:** same route; base64 source images embedded as `input_image` / `input_image_N`.
- **Response image:** `data[].b64_json|base64|image` or `result.b64_json|base64|image`.
- **Supports edit:** yes.

> Example matching a working curl: deployment (path) = `flux-2-pro`, Advanced → Body model id =
> `FLUX.2-pro`.

### `mai` — Microsoft MAI-Image

- **Generate URL:** `{endpoint}/mai/v1/images/generations` (fixed route — **no** `api-version`, **no**
  deployment path segment).
- **Routed by:** the fixed provider route; the model is named only in the body.
- **Auth:** `api-key: <key>` header.
- **Body:** JSON `{ model, prompt, width, height }`. Dimensions are clamped to `>= 768 px` and
  `<= ~1 MP`.
- **Response image:** `data[].b64_json`.
- **Supports edit:** **no** — edit requests transparently fall back to text-to-image.

> Newer MAI versions (e.g. `MAI-Image-2.5`) are onboarded by selecting the **MAI-Image** family and
> typing the new deployment name. No code change is required.

### `custom` — OpenAI-compatible / anything else

- **Default Generate URL:** `{endpoint}/openai/deployments/{deployment}/images/generations?api-version={api_version}`
- **Routed by:** whatever you put in the **Path override**. Placeholders `{endpoint}`, `{deployment}`,
  `{model_id}`, `{api_version}` are substituted.
- **Auth:** `api-key: <key>` header.
- **Body:** generic `{ model, prompt, size, n }`.
- **Response image:** tries `data[].b64_json|url|image`, `result.b64_json|image`, `image`, `b64_json`.
- **Supports edit:** no.

## Adding a new family

To teach the app a genuinely new backend (different URL shape or body), add a `ProviderSpec` entry to
`PROVIDERS` in `providers.py` and, if the body differs from the existing styles, add a matching branch
in `services.py` keyed by `body_style`. The UI, bootstrap payload, and this document's behavior all
update automatically from the registry.
