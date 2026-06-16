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
    "cartoon_3d": {
        "title": "3D Cartoon Chef",
        "prompt": (
            "A vibrant 3D animated cartoon scene in the polished style of a modern Pixar feature film. A "
            "chubby orange tabby cat character stands upright on two legs in a sunny kitchen, with big "
            "expressive green eyes and rounded, exaggerated proportions. It proudly holds up a wooden tray "
            "carrying exactly three stacked blueberry pancakes topped with one melting pat of butter. The "
            "cat wears a small red-and-white striped apron printed with the text 'CHEF MILO'. Behind it, "
            "exactly two cartoon mice in blue overalls peek out from an open cupboard. Render with soft "
            "global illumination, gentle subsurface scattering on the fur and skin, smooth rounded glossy "
            "surfaces, shallow depth of field, and a warm pastel palette of cream, butter yellow, and sky "
            "blue, with playful cinematic 3D animation lighting."
        ),
        "dim_map": {
            "prompt_adherence": "Sunny kitchen, upright tabby chef, tray of pancakes, mice, and apron text all honored.",
            "object_accuracy": "Cat chef, tray, pancakes, butter, apron, two mice, and cupboard all present.",
            "object_counting": "Exactly 3 pancakes, 1 pat of butter, and 2 mice in overalls.",
            "attribute_binding": "Orange fur, green eyes, red-and-white apron, blue overalls bound to the right characters.",
            "spatial_relationship": "Cat in foreground holding tray up, mice peeking from cupboard behind it.",
            "action_interaction": "Cat actively presenting the tray while the mice peek out and watch.",
            "text_rendering": "Apron must clearly read CHEF MILO with believable printed lettering.",
            "anatomy_proportions": "Stylized exaggerated cartoon proportions should stay consistent and appealing.",
            "physics_realism": "Soft shadows, glossy highlights, and melting butter should read as plausible CG.",
            "color_accuracy": "Cream, butter yellow, sky blue, and orange fur should stay clean and warm.",
            "fine_detail": "Fur strands, pancake texture, fabric folds, and subsurface skin need polish.",
            "composition_aesthetics": "Centered hero framing with playful balance and soft background bokeh.",
            "style_adherence": "Glossy 3D animated feature-film look rather than flat 2D or photoreal.",
        },
    },
    "storyboard_comic": {
        "title": "Comic Storyboard",
        "prompt": (
            "A 2D comic-book storyboard laid out as exactly four equal panels in a 2x2 grid separated by "
            "thin black gutters, drawn in a clean flat cel-shaded ink style with bold outlines and halftone "
            "shading dots. The story follows a young girl detective named Mia and her robot dog Bolt, kept "
            "visually consistent across every panel. Panel 1 (top-left): Mia kneels and finds a torn map on "
            "the floor; a yellow caption box reads 'MORNING: A clue!'. Panel 2 (top-right): Mia and Bolt "
            "walk into a dark forest; her white speech bubble says 'This way, Bolt!'. Panel 3 (bottom-left): "
            "they discover a glowing treasure chest; Bolt's speech bubble says 'BEEP! Gold!'. Panel 4 "
            "(bottom-right): Mia triumphantly holds up a golden key; a caption box reads 'THE END?'. Use "
            "bright primary comic colors and clearly legible hand-lettered English text in every bubble and "
            "caption, with a coherent left-to-right, top-to-bottom narrative flow."
        ),
        "dim_map": {
            "prompt_adherence": "All four scripted panels, captions, and the Mia-and-Bolt storyline must be followed in order.",
            "object_accuracy": "Torn map, dark forest, glowing chest, and golden key each appear in their panel.",
            "object_counting": "Exactly 4 panels in a 2x2 grid, each with its specified caption or bubble.",
            "attribute_binding": "Yellow caption boxes, white speech bubbles, golden key bound to the correct elements.",
            "spatial_relationship": "Panels read top-left, top-right, bottom-left, bottom-right with clean gutters.",
            "action_interaction": "Mia finds, walks, discovers, then lifts the key while Bolt follows along.",
            "text_rendering": "Every caption and bubble (e.g. 'This way, Bolt!', 'THE END?') must be legible and correct.",
            "anatomy_proportions": "Mia and Bolt keep consistent, believable cartoon proportions across panels.",
            "physics_realism": "Lighting (dark forest, glowing chest) should stay consistent within each panel.",
            "color_accuracy": "Bright primary comic palette should stay clean and consistent between panels.",
            "fine_detail": "Bold outlines, halftone dots, and lettering should be crisp and readable.",
            "composition_aesthetics": "Balanced four-panel layout with clear narrative pacing and focal points.",
            "style_adherence": "Flat cel-shaded 2D comic-book look rather than painterly or 3D rendering.",
        },
    },
    "data_chart": {
        "title": "Data Chart",
        "prompt": (
            "A clean, precise data-visualization infographic on a plain white background showing a single "
            "vertical bar chart titled 'QUARTERLY REVENUE 2025' in bold black sans-serif. The chart has "
            "exactly four bars labeled Q1, Q2, Q3, Q4 along the x-axis, and a y-axis labeled 'Revenue (USD "
            "millions)' with horizontal gridlines at 0, 20, 40, 60, and 80. The bars reach exactly these "
            "heights with these colors: Q1 = 30 in blue (#2563EB), Q2 = 45 in green (#16A34A), Q3 = 55 in "
            "amber (#F59E0B), and Q4 = 70 in red (#DC2626). Each bar has its exact numeric value printed in "
            "black directly above it. A small legend in the top-right corner maps each color to its quarter. "
            "Use a crisp anti-aliased flat vector style with accurate proportional bar heights, perfectly "
            "horizontal gridlines, and sharp, legible numeric and axis labels."
        ),
        "dim_map": {
            "prompt_adherence": "Title, axis labels, four quarters, exact values, and color mapping must all match.",
            "object_accuracy": "Bar chart, axes, gridlines, value labels, and color legend all present.",
            "object_counting": "Exactly 4 bars and 5 gridlines (0/20/40/60/80) with one value label per bar.",
            "attribute_binding": "Blue Q1, green Q2, amber Q3, red Q4 bound to the correct quarters.",
            "spatial_relationship": "Bars sit on the x-axis at correct heights; legend in the top-right.",
            "action_interaction": "N/A — a static chart; focus on accurate encoding of the data.",
            "text_rendering": "Title, axis labels, value numbers (30/45/55/70), and legend text must be exact and legible.",
            "anatomy_proportions": "N/A — bar proportions must instead match their stated numeric values.",
            "physics_realism": "Flat vector chart; gridlines and bars should be clean and undistorted.",
            "color_accuracy": "Bar colors should match the specified blue, green, amber, and red hex values.",
            "fine_detail": "Sharp anti-aliased edges, aligned gridlines, and tidy numeric labels.",
            "composition_aesthetics": "Balanced infographic layout with clear title, axes, and legend.",
            "style_adherence": "Clean flat data-viz vector style rather than photoreal or hand-drawn.",
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


def sample_models() -> list[ModelConfig]:
    return [
        ModelConfig(enabled=True, family="gpt-image", deployment="gpt-image-1"),
        ModelConfig(enabled=True, family="gpt-image", deployment="gpt-image-1.5"),
        ModelConfig(enabled=False, family="gpt-image", deployment="gpt-image-2"),
        ModelConfig(enabled=True, family="flux", deployment="flux-2-pro", model_id="FLUX.2-pro"),
        ModelConfig(enabled=False, family="flux", deployment="flux-2-flex", model_id="FLUX.2-flex"),
        ModelConfig(enabled=False, family="flux", deployment="flux-1-kontext-pro", model_id="FLUX.1-Kontext-pro"),
        ModelConfig(enabled=False, family="flux", deployment="flux-1.1-pro", model_id="FLUX-1.1-pro"),
        ModelConfig(enabled=True, family="mai", deployment="MAI-Image-2"),
        ModelConfig(enabled=False, family="mai", deployment="MAI-Image-2e"),
        ModelConfig(enabled=False, family="mai", deployment="MAI-Image-2.5"),
    ]
