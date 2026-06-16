from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from image_generation_model_comparison_portal.providers import family_from_kind


# Image-quality evaluation dimensions.
#
# The set is aligned with the most widely used public text-to-image benchmarks
# and leaderboards rather than an ad-hoc list. See
# ``docs/IMAGE_QUALITY_EVALUATION.md`` for the methodology and benchmark
# provenance of each dimension. Dimensions are data-driven: the evaluator
# system prompt, the radar chart, and the comparison table are all generated
# from these maps, so new metrics can be added here without touching routing
# or UI code.
DIM_LABELS = {
    "prompt_adherence": "Prompt Adherence",
    "object_accuracy": "Object Accuracy",
    "object_counting": "Object Counting",
    "attribute_binding": "Attribute Binding",
    "spatial_relationship": "Spatial Relationship",
    "action_interaction": "Action & Interaction",
    "text_rendering": "Text Rendering",
    "anatomy_proportions": "Anatomy",
    "physics_realism": "Physics & Realism",
    "color_accuracy": "Color Accuracy",
    "fine_detail": "Fine Detail",
    "composition_aesthetics": "Composition & Aesthetics",
    "style_adherence": "Style Adherence",
}
DIM_KEYS = list(DIM_LABELS.keys())

# Compact labels for the radar chart axes.
DIM_SHORT = {
    "prompt_adherence": "Prompt",
    "object_accuracy": "Objects",
    "object_counting": "Count",
    "attribute_binding": "Binding",
    "spatial_relationship": "Spatial",
    "action_interaction": "Action",
    "text_rendering": "Text",
    "anatomy_proportions": "Anatomy",
    "physics_realism": "Physics",
    "color_accuracy": "Color",
    "fine_detail": "Detail",
    "composition_aesthetics": "Aesthetics",
    "style_adherence": "Style",
}

# Per-dimension guidance injected into the evaluator system prompt. Each entry
# notes the benchmark axis the dimension is modeled on.
DIM_GUIDANCE = {
    "prompt_adherence": "Overall faithfulness to the full prompt, including long/dense descriptions (DPG-Bench).",
    "object_accuracy": "Every requested object/entity is present; nothing missing or hallucinated (GenEval single/two-object).",
    "object_counting": "Correct quantity of each requested object (GenEval counting).",
    "attribute_binding": "Each attribute (color, material, texture, shape) is bound to the correct object (GenEval color attribution; T2I-CompBench attribute binding).",
    "spatial_relationship": "Correct relative positions and layout: left/right, above/below, foreground/background (GenEval position; T2I-CompBench spatial).",
    "action_interaction": "Correct non-spatial relationships: actions, interactions, and verbs between subjects (T2I-CompBench non-spatial).",
    "text_rendering": "Visible text is legible, correctly spelled, and believably formed.",
    "anatomy_proportions": "Whole-body coherence: pose, gesture, limb/hand structure, finger counts, body ratios.",
    "physics_realism": "Plausible lighting, shadows, reflections, gravity, and material behavior.",
    "color_accuracy": "Requested palette and tonal relationships reproduced consistently.",
    "fine_detail": "Sharpness and fidelity of small features, textures, edges, and micro-structure.",
    "composition_aesthetics": "Framing, balance, visual hierarchy, and overall aesthetic appeal (human-preference style).",
    "style_adherence": "Match to the requested artistic or photographic style.",
}

# Legacy fixed model list (kept for the deprecated PySide6 desktop UI). The web
# portal now uses the flexible provider families in ``providers.py`` instead.
MODEL_OPTIONS = [
    ("gpt-image-1", "GPT-Image-1"),
    ("gpt-image-1.5", "GPT-Image-1.5"),
    ("gpt-image-2", "GPT-Image-2"),
    ("flux-2-pro", "FLUX.2-pro"),
    ("flux-2-flex", "FLUX.2-flex"),
    ("flux-kontext-pro", "FLUX.1-Kontext-pro"),
    ("flux-pro-1.1", "FLUX-1.1-pro"),
    ("mai-image-2", "MAI-Image-2"),
    ("mai-image-2e", "MAI-Image-2e"),
]

BENCHMARK_PRESETS = {
    "watchmaker": {
        "title": "The Watchmaker",
        "prompt": (
            "A professional studio photograph of an elderly Asian watchmaker with weathered hands and "
            "wire-rimmed glasses, carefully assembling a mechanical pocket watch at a wooden workbench. "
            "His left hand shows exactly five fingers holding a jeweler screwdriver. On the bench sit "
            "exactly three finished pocket watches, two open watch movements, one brass loupe, and a "
            "small handwritten card reading 'Caliber 72'. Warm task lighting from camera left creates "
            "realistic highlights on polished metal and soft shadows across the oak surface. Capture as "
            "a 50mm f/2 portrait with crisp micro-detail, true skin texture, visible gear teeth, shallow "
            "depth of field, and a restrained amber-and-brass palette."
        ),
        "dim_map": {
            "prompt_adherence": "Exact elderly watchmaker scene, bench props, visible text, lens and lighting cues.",
            "object_accuracy": "Watchmaker, watches, movements, loupe, screwdriver, and card all present.",
            "object_counting": "Exactly 3 finished watches, 2 open movements, 1 loupe, 1 screwdriver hand pose.",
            "attribute_binding": "Brass loupe, oak bench, wire-rimmed glasses bound to the correct objects.",
            "spatial_relationship": "Workbench layout and left-side task light should stay coherent and readable.",
            "action_interaction": "Watchmaker actively assembling the watch while holding the screwdriver.",
            "text_rendering": "Card must clearly read Caliber 72 with believable printed lettering.",
            "anatomy_proportions": "Hands, fingers, posture, and facial proportions should look natural.",
            "physics_realism": "Metal reflections, shadows, and shallow depth should behave physically.",
            "color_accuracy": "Warm amber, oak wood, brass, and skin tones should stay controlled.",
            "fine_detail": "Gear teeth, skin texture, screws, and watch parts need crisp fidelity.",
            "composition_aesthetics": "Portrait framing should balance subject, props, and negative space.",
            "style_adherence": "Professional studio editorial realism rather than stylized illustration.",
        },
    },
    "neon_ramen": {
        "title": "Neon Ramen",
        "prompt": (
            "A rainy cyberpunk alley ramen stand at night with exactly four red lanterns hanging overhead, "
            "one chef behind the counter, and two seated customers in yellow raincoats. Steam rises from "
            "three ceramic ramen bowls in the foreground. A bright blue vertical sign reads '夜麺' and a "
            "small menu board shows the text 'MISO 12'. Wet pavement reflects orange neon, pink billboards, "
            "and teal vending machine light. Compose as a cinematic 35mm street photograph with realistic "
            "rain streaks, consistent reflections, strong depth, and dense surface texture."
        ),
        "dim_map": {
            "prompt_adherence": "Respect alley ramen setup, lantern count, customers, menu text, and neon palette.",
            "object_accuracy": "Lanterns, chef, customers, bowls, sign, and menu board all present.",
            "object_counting": "Exactly 4 lanterns, 1 chef, 2 customers, and 3 ramen bowls.",
            "attribute_binding": "Yellow raincoats, red lanterns, blue sign bound to the right objects.",
            "spatial_relationship": "Chef behind counter, customers seated, bowls foreground, signs overhead.",
            "action_interaction": "Chef serving, customers seated and eating under the rain.",
            "text_rendering": "Blue sign and MISO 12 board should be readable and correctly formed.",
            "anatomy_proportions": "Human figures should hold natural posture and believable proportions.",
            "physics_realism": "Rain, steam, and wet reflections should align with light sources.",
            "color_accuracy": "Orange, pink, blue, teal, and yellow should separate cleanly.",
            "fine_detail": "Steam wisps, noodles, wet pavement, and surface textures need detail.",
            "composition_aesthetics": "Foreground bowls and alley depth should create cinematic framing.",
            "style_adherence": "Neo-noir street photography rather than flat illustration.",
        },
    },
}


@dataclass(slots=True)
class ModelConfig:
    """A single image-generation deployment to compare.

    The model is identified by its *routing family* plus a free-text
    ``deployment`` identifier, so any new model version can be onboarded without
    code changes. Optional ``endpoint``/``api_version``/``path`` overrides allow
    pointing a single row at a different resource or a non-standard route.

    ``kind`` is retained only for backward compatibility with configs saved by
    older versions of the portal.
    """

    enabled: bool = True
    name: str = ""
    family: str = ""
    deployment: str = ""
    model_id: str = ""
    endpoint: str = ""
    api_version: str = ""
    path: str = ""
    kind: str = ""

    def __post_init__(self) -> None:
        if not self.family:
            self.family = family_from_kind(self.kind)
        if not self.model_id:
            # FLUX routes by model name; GPT/MAI route by deployment. In both
            # cases the body "model" defaults to the identifier the user typed,
            # falling back to the legacy kind for old configs.
            self.model_id = self.deployment or self.kind
        if not self.kind:
            self.kind = self.family
        if not self.name:
            self.name = self.deployment or self.kind or self.family

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelConfig":
        allowed = {field_name for field_name in cls.__slots__}
        payload = {key: value for key, value in data.items() if key in allowed}
        return cls(**payload)

    def body_model(self) -> str:
        return (self.model_id or self.deployment or self.kind or "").strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AppConfig:
    global_endpoint: str = ""
    global_secret: str = ""
    global_auth_type: str = "apiKey"
    gpt_api_version: str = "2025-04-01-preview"
    flux_api_version: str = "preview"
    vision_api_version: str = "2023-10-01"
    cv_endpoint: str = ""
    cv_secret: str = ""
    eval_deployment: str = ""
    auto_eval: str = "yes"
    eval_detail: str = "high"
    cv_enabled: str = "yes"
    cs_endpoint: str = ""
    cs_secret: str = ""
    cs_api_version: str = "2024-09-01"
    models: list[ModelConfig] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_endpoint": self.global_endpoint,
            "global_secret": self.global_secret,
            "global_auth_type": self.global_auth_type,
            "gpt_api_version": self.gpt_api_version,
            "flux_api_version": self.flux_api_version,
            "vision_api_version": self.vision_api_version,
            "cv_endpoint": self.cv_endpoint,
            "cv_secret": self.cv_secret,
            "eval_deployment": self.eval_deployment,
            "auto_eval": self.auto_eval,
            "eval_detail": self.eval_detail,
            "cv_enabled": self.cv_enabled,
            "cs_endpoint": self.cs_endpoint,
            "cs_secret": self.cs_secret,
            "cs_api_version": self.cs_api_version,
            "models": [model.to_dict() for model in self.models],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        models = [ModelConfig.from_dict(item) for item in data.get("models", [])]
        allowed = {field_name for field_name in cls.__slots__ if field_name != "models"}
        payload = {key: value for key, value in data.items() if key in allowed}
        return cls(models=models, **payload)


@dataclass(slots=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(slots=True)
class GenerationResult:
    model_name: str
    model_kind: str
    image_b64: str
    mime_type: str
    elapsed_s: float
    usage: Usage | None
    url: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]


@dataclass(slots=True)
class BoundingBox:
    label: str
    confidence: float
    x: float
    y: float
    w: float
    h: float


@dataclass(slots=True)
class CvResult:
    objects: list[BoundingBox]
    tags: list[tuple[str, float]]
    raw_payload: dict[str, Any]

    def object_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.objects:
            counts[item.label] = counts.get(item.label, 0) + 1
        return counts


@dataclass(slots=True)
class EvalDimension:
    score: int
    note: str


@dataclass(slots=True)
class EvalResult:
    overall_score: float
    dimensions: dict[str, EvalDimension]
    strengths: list[str]
    weaknesses: list[str]
    summary: str
    finish_reason: str
    cv_augmented: bool
    usage: Usage | None
    raw_payload: dict[str, Any]


@dataclass(slots=True)
class ResultRecord:
    model: ModelConfig
    generation: GenerationResult | None = None
    cv_result: CvResult | None = None
    eval_result: EvalResult | None = None
    error: str | None = None


@dataclass(slots=True)
class SafetyCategory:
    """One Azure AI Content Safety category result (severity 0/2/4/6)."""

    category: str
    severity: int


@dataclass(slots=True)
class SafetyResult:
    """Outcome of the content-safety path for one model x prompt."""

    # "blocked"  -> the model/provider refused to generate (content filter).
    # "generated" -> an image came back; it was then moderated.
    # "error"    -> a non-safety failure (network, auth, etc.).
    outcome: str
    blocked: bool
    block_reason: str
    image_categories: list[SafetyCategory]
    prompt_categories: list[SafetyCategory]
    max_image_severity: int
    raw_payload: dict[str, Any]


def sample_models() -> list[ModelConfig]:
    return [
        ModelConfig(enabled=True, family="gpt-image", deployment="gpt-image-1"),
        ModelConfig(enabled=True, family="gpt-image", deployment="gpt-image-1.5"),
        ModelConfig(enabled=False, family="gpt-image", deployment="gpt-image-2"),
        ModelConfig(enabled=True, family="flux", deployment="FLUX.2-pro"),
        ModelConfig(enabled=False, family="flux", deployment="FLUX.2-flex"),
        ModelConfig(enabled=False, family="flux", deployment="FLUX.1-Kontext-pro"),
        ModelConfig(enabled=False, family="flux", deployment="FLUX-1.1-pro"),
        ModelConfig(enabled=True, family="mai", deployment="MAI-Image-2"),
        ModelConfig(enabled=False, family="mai", deployment="MAI-Image-2e"),
        ModelConfig(enabled=False, family="mai", deployment="MAI-Image-2.5"),
    ]
