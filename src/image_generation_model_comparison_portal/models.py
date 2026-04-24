from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


DIM_LABELS = {
    "prompt_adherence": "Prompt Adherence",
    "text_rendering": "Text Rendering",
    "object_counting": "Object Counting",
    "spatial_reasoning": "Spatial Reasoning",
    "anatomy_proportions": "Anatomy",
    "physics_realism": "Physics & Realism",
    "color_accuracy": "Color Accuracy",
    "fine_detail": "Fine Detail",
    "composition_aesthetics": "Composition",
    "style_adherence": "Style Adherence",
}
DIM_KEYS = list(DIM_LABELS.keys())

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
            "text_rendering": "Card must clearly read Caliber 72 with believable printed lettering.",
            "object_counting": "Exactly 3 finished watches, 2 open movements, 1 loupe, 1 screwdriver hand pose.",
            "spatial_reasoning": "Workbench layout and left-side task light should stay coherent and readable.",
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
            "text_rendering": "Blue sign and MISO 12 board should be readable and correctly formed.",
            "object_counting": "Exactly 4 lanterns, 1 chef, 2 customers, and 3 ramen bowls.",
            "spatial_reasoning": "Chef behind counter, customers seated, bowls foreground, signs overhead.",
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
    enabled: bool = True
    name: str = ""
    kind: str = "gpt-image-1"
    deployment: str = ""

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
            "models": [model.to_dict() for model in self.models],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        models = [ModelConfig(**item) for item in data.get("models", [])]
        payload = {key: value for key, value in data.items() if key != "models"}
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


def sample_models() -> list[ModelConfig]:
    return [
        ModelConfig(True, "GPT-Image-1", "gpt-image-1", "gpt-image-1"),
        ModelConfig(True, "GPT-Image-1.5", "gpt-image-1.5", "gpt-image-1.5"),
        ModelConfig(False, "GPT-Image-2", "gpt-image-2", "gpt-image-2"),
        ModelConfig(True, "FLUX.2-pro", "flux-2-pro", "FLUX.2-pro"),
        ModelConfig(False, "FLUX.2-flex", "flux-2-flex", "FLUX.2-flex"),
        ModelConfig(False, "FLUX.1-Kontext-pro", "flux-kontext-pro", "FLUX.1-Kontext-pro"),
        ModelConfig(False, "FLUX-1.1-pro", "flux-pro-1.1", "FLUX-1.1-pro"),
        ModelConfig(False, "MAI-Image-2", "mai-image-2", "MAI-Image-2"),
        ModelConfig(False, "MAI-Image-2e", "mai-image-2e", "MAI-Image-2e"),
    ]
