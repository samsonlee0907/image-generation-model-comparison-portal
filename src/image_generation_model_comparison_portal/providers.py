"""Data-driven provider/routing registry.

This module is the single source of truth for how the portal routes an image
request to the correct backend. Instead of hard-coding model *versions*, the
portal only needs to know the *routing family* a deployment belongs to. A user
can then add any new model (for example ``mai-image-2.5``) by selecting its
family and entering their own deployment/endpoint — no code change required.

Each :class:`ProviderSpec` documents the path template, request-body style,
auth header style, default API version, and response shapes for one family.
The same registry feeds:

* :mod:`services` — to build the request URL and parse the response.
* the web UI — to populate the family dropdown and field hints.
* ``docs/MODEL_ROUTING.md`` — generated/kept in sync with these specs.

See ``docs/MODEL_ROUTING.md`` for a human-readable summary of the differences.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderSpec:
    """Describes how one routing family talks to its backend."""

    id: str
    label: str
    description: str
    # Auth header style: "api-key" (Azure api-key header), "bearer"
    # (Authorization: Bearer), or "api-key+bearer" (send both — FLUX accepts
    # either depending on the gateway).
    auth: str
    # URL templates. Placeholders: {endpoint} {deployment} {model_id} {api_version}
    generate_template: str
    edit_template: str | None
    # Body builders are implemented in services.py keyed by body_style.
    body_style: str
    supports_edit: bool
    # Which AppConfig api-version field supplies the default for this family.
    api_version_field: str
    default_api_version: str
    # Ordered list of dotted paths (within the JSON response) to try when
    # extracting the base64/url image payload. "[]" means "first list item".
    response_image_paths: tuple[str, ...]
    # UI hints.
    identifier_label: str
    identifier_placeholder: str
    notes: str = ""
    # Optional substrings that a deployment/body-model must contain for image
    # *edit* to be available, when ``supports_edit`` is True but only some
    # versions of the family support editing (e.g. MAI image edit requires
    # MAI-Image-2.5 or newer). Empty means "all versions of this family edit".
    edit_version_markers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "auth": self.auth,
            "supports_edit": self.supports_edit,
            "edit_version_markers": list(self.edit_version_markers),
            "identifier_label": self.identifier_label,
            "identifier_placeholder": self.identifier_placeholder,
            "notes": self.notes,
        }


PROVIDERS: dict[str, ProviderSpec] = {
    "gpt-image": ProviderSpec(
        id="gpt-image",
        label="GPT-Image (Azure OpenAI)",
        description=(
            "Azure OpenAI / Foundry image deployments such as gpt-image-1, "
            "gpt-image-1.5, gpt-image-2 and future versions."
        ),
        auth="api-key",
        generate_template="{endpoint}/openai/deployments/{deployment}/images/generations?api-version={api_version}",
        edit_template="{endpoint}/openai/deployments/{deployment}/images/edits?api-version={api_version}",
        body_style="gpt-image",
        supports_edit=True,
        api_version_field="gpt_api_version",
        default_api_version="2025-04-01-preview",
        response_image_paths=("data.[].b64_json",),
        identifier_label="Deployment Name",
        identifier_placeholder="my-gpt-image-deployment",
        notes=(
            "Routed by Azure deployment name in the URL path. JSON body with "
            "prompt/model/n/quality/size; gpt-image-2+ also accepts output_format. "
            "Edits use multipart/form-data with image[] and an optional mask. "
            "gpt-image is the only family here that supports true mask-based "
            "inpainting — the mask's transparent/white pixels mark the region to "
            "regenerate while the rest of the image is preserved."
        ),
    ),
    "flux": ProviderSpec(
        id="flux",
        label="FLUX (Black Forest Labs)",
        description=(
            "Black Forest Labs FLUX models served through the Foundry "
            "blackforestlabs provider route (FLUX.2-pro, FLUX.2-flex, "
            "FLUX.1-Kontext-pro, FLUX-1.1-pro, and newer)."
        ),
        auth="api-key+bearer",
        generate_template="{endpoint}/providers/blackforestlabs/v1/{deployment}?api-version={api_version}",
        edit_template="{endpoint}/providers/blackforestlabs/v1/{deployment}?api-version={api_version}",
        body_style="flux",
        supports_edit=True,
        api_version_field="flux_api_version",
        default_api_version="preview",
        response_image_paths=(
            "data.[].b64_json",
            "data.[].base64",
            "data.[].image",
            "result.b64_json",
            "result.base64",
            "result.image",
        ),
        identifier_label="Deployment Name",
        identifier_placeholder="flux-2-pro",
        notes=(
            "The URL routes by the Azure *deployment name* path segment (e.g. "
            "'flux-2-pro' — lowercase, as it appears in your endpoint URL), NOT "
            "the catalog name. The request body 'model' defaults to the same "
            "deployment name; if your gateway requires the catalog name (e.g. "
            "'FLUX.2-pro'), set it under Advanced -> 'Body model id'. "
            "Edits are instruction/reference-based: source images are embedded as "
            "base64 input_image / input_image_N (FLUX.2 accepts up to 8-10 "
            "references) and guided purely by the prompt. FLUX on Foundry has no "
            "separate mask channel (masked inpainting lives in the FLUX.1 Fill "
            "model, which is not in the Foundry catalog), so any uploaded mask is "
            "ignored for FLUX."
        ),
    ),
    "mai": ProviderSpec(
        id="mai",
        label="MAI-Image (Microsoft)",
        description=(
            "Microsoft MAI image models on Foundry (MAI-Image-2, MAI-Image-2e, "
            "MAI-Image-2.5, MAI-Image-2.5-Flash, and future versions)."
        ),
        auth="api-key",
        generate_template="{endpoint}/mai/v1/images/generations",
        edit_template="{endpoint}/mai/v1/images/edits",
        body_style="mai",
        supports_edit=True,
        edit_version_markers=("2.5",),
        api_version_field="",
        default_api_version="",
        response_image_paths=("data.[].b64_json",),
        identifier_label="Deployment Name",
        identifier_placeholder="mai-image-2.5",
        notes=(
            "Generation uses the fixed route /mai/v1/images/generations (no "
            "api-version, no deployment path segment); JSON body with "
            "model/prompt/width/height, dimensions clamped to >=768 px and "
            "<= ~1 MP. Image edit is instruction-based via "
            "/mai/v1/images/edits (multipart image + prompt) and is only "
            "available on MAI-Image-2.5 / 2.5-Flash; MAI-Image-2 / 2e are "
            "generation-only and fall back to text-to-image. MAI has no mask "
            "channel, so any uploaded mask is ignored."
        ),
    ),
    "custom": ProviderSpec(
        id="custom",
        label="Custom (OpenAI-compatible)",
        description=(
            "Any OpenAI-compatible images/generations endpoint. Supply your own "
            "endpoint, path template and identifier to onboard a model the portal "
            "does not know about yet."
        ),
        auth="api-key",
        generate_template="{endpoint}/openai/deployments/{deployment}/images/generations?api-version={api_version}",
        edit_template=None,
        body_style="openai-compatible",
        supports_edit=False,
        api_version_field="gpt_api_version",
        default_api_version="2025-04-01-preview",
        response_image_paths=(
            "data.[].b64_json",
            "data.[].url",
            "data.[].image",
            "result.b64_json",
            "result.image",
            "image",
            "b64_json",
        ),
        identifier_label="Model / Deployment",
        identifier_placeholder="my-custom-model",
        notes=(
            "Use the optional 'Path Template' override to point at a non-standard "
            "route. Placeholders {endpoint} {deployment} {model_id} {api_version} "
            "are substituted. Body is a generic {model, prompt, size, n} payload."
        ),
    ),
}

DEFAULT_FAMILY = "gpt-image"


# Legacy ``kind`` prefixes -> routing family, for back-compat with saved configs.
_KIND_PREFIX_TO_FAMILY = (
    ("gpt-image", "gpt-image"),
    ("flux-", "flux"),
    ("mai-", "mai"),
)


def family_from_kind(kind: str | None) -> str:
    """Map a legacy ``kind`` string to a routing family."""

    value = (kind or "").strip().lower()
    for prefix, family in _KIND_PREFIX_TO_FAMILY:
        if value.startswith(prefix):
            return family
    return DEFAULT_FAMILY


def get_provider(family: str | None) -> ProviderSpec:
    """Return the :class:`ProviderSpec` for ``family`` (falling back safely)."""

    return PROVIDERS.get((family or "").strip(), PROVIDERS[DEFAULT_FAMILY])


def provider_options() -> list[dict[str, Any]]:
    """Serializable provider metadata for the web UI bootstrap payload."""

    return [spec.to_dict() for spec in PROVIDERS.values()]


def spec_supports_edit(spec: ProviderSpec, *identifiers: str) -> bool:
    """Whether image edit is available for a deployment of ``spec``.

    Most families either support edit for every version or not at all. Some
    (e.g. MAI image) only support edit from a given version onward; in that case
    ``spec.edit_version_markers`` lists substrings and at least one must appear
    in the deployment/body-model ``identifiers`` for edit to be available.
    """

    if not spec.supports_edit or not spec.edit_template:
        return False
    if not spec.edit_version_markers:
        return True
    blob = " ".join(value.lower() for value in identifiers if value)
    return any(marker.lower() in blob for marker in spec.edit_version_markers)


def extract_image(payload: dict[str, Any], spec: ProviderSpec) -> str | None:
    """Walk ``spec.response_image_paths`` to find a base64/url image string."""

    for path in spec.response_image_paths:
        value = _dig(payload, path)
        if isinstance(value, str) and value:
            return value
    return None


def _dig(payload: Any, path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if current is None:
            return None
        if part == "[]":
            if isinstance(current, list) and current:
                current = current[0]
            else:
                return None
            continue
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current
