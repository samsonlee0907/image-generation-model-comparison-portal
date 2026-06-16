# Image Quality Evaluation

This document captures **how the portal scores image quality** — both the original methodology and the
refreshed, benchmark-aligned metric set that replaces it. Scoring uses an **LLM-as-judge** approach:
each generated image is sent to an evaluator model that returns a structured, per-dimension score with
notes, strengths, weaknesses, and a summary. The dimensions are **data-driven** — the evaluator system
prompt, the radar chart, and the comparison table are all generated from the maps in
[`models.py`](../src/image_generation_model_comparison_portal/models.py), so the metric set can be
expanded without touching routing or UI code.

## Part 1 — Original methodology (preserved)

The first version scored every image on a fixed list of **10 dimensions**, each on an integer scale of
**1–10**, plus an `overall_score`. Optionally, Azure AI Vision (CV) added object detection and
bounding-box overlays.

| # | Dimension | What it measured |
| --- | --- | --- |
| 1 | Prompt Adherence | Faithfulness to scene, subject, objects, constraints, intent. |
| 2 | Text Rendering | Legibility, spelling, believable letterforms. |
| 3 | Object Counting | Correct quantity of requested objects. |
| 4 | Spatial Reasoning | Correct positions/relationships and scene layout. |
| 5 | Anatomy | Body coherence: pose, limbs, hands, finger counts, ratios. |
| 6 | Physics & Realism | Plausible lighting, shadows, reflections, gravity, materials. |
| 7 | Color Accuracy | Requested palette and tonal relationships. |
| 8 | Fine Detail | Sharpness of small features, textures, edges. |
| 9 | Composition | Framing, balance, hierarchy, aesthetics. |
| 10 | Style Adherence | Match to requested artistic/photographic style. |

**Scoring mechanics (unchanged):** each dimension gets `1–10` plus a short note; an `overall_score`
summarizes the image; results may be augmented with CV analysis; bounding boxes are drawn when CV
detects objects.

**Known limitation:** the original list was an ad-hoc set rather than one grounded in published
text-to-image benchmarks, and it collapsed several distinct failure modes (object presence vs.
attribute binding vs. spatial vs. action) into coarse buckets like "Prompt Adherence" and "Spatial
Reasoning".

## Part 2 — Benchmark-aligned metric set (current)

The refreshed set keeps the LLM-as-judge approach and the `1–10` scale but maps the dimensions onto the
axes most widely used by public text-to-image benchmarks and leaderboards. This makes scores easier to
interpret against the literature and isolates the specific failure modes those benchmarks were designed
to expose.

### Benchmarks referenced

- **GenEval** — object-focused, compositional evaluation: single-object and two-object presence, object
  **counting**, relative **position**, and **color attribution** (attribute → object binding).
- **T2I-CompBench / T2I-CompBench++** — compositional generation across **attribute binding** (color,
  shape, texture), **spatial relationships**, **non-spatial relationships** (actions/interactions), and
  complex compositions.
- **DPG-Bench (Dense Prompt Graph)** — fidelity to **long, dense prompts** with many entities and
  attributes.
- **Aesthetic / human-preference** signals (e.g. aesthetic predictors and human-preference scoring) —
  overall **composition and visual appeal**.

### Current dimensions

| Key | Label | Radar | Benchmark axis modeled |
| --- | --- | --- | --- |
| `prompt_adherence` | Prompt Adherence | Prompt | Overall faithfulness incl. long/dense prompts (DPG-Bench). |
| `object_accuracy` | Object Accuracy | Objects | All requested entities present, none hallucinated (GenEval single/two-object). |
| `object_counting` | Object Counting | Count | Correct quantity per object (GenEval counting). |
| `attribute_binding` | Attribute Binding | Binding | Attributes bound to the right object (GenEval color attribution; T2I-CompBench). |
| `spatial_relationship` | Spatial Relationship | Spatial | Relative positions/layout (GenEval position; T2I-CompBench spatial). |
| `action_interaction` | Action & Interaction | Action | Non-spatial relationships: actions/verbs between subjects (T2I-CompBench non-spatial). |
| `text_rendering` | Text Rendering | Text | Legible, correctly spelled visible text. |
| `anatomy_proportions` | Anatomy | Anatomy | Whole-body coherence: pose, hands, finger counts, ratios. |
| `physics_realism` | Physics & Realism | Physics | Plausible lighting, shadows, gravity, materials. |
| `color_accuracy` | Color Accuracy | Color | Palette and tonal relationships reproduced consistently. |
| `fine_detail` | Fine Detail | Detail | Sharpness/fidelity of small features and textures. |
| `composition_aesthetics` | Composition & Aesthetics | Aesthetics | Framing, balance, hierarchy, appeal (human-preference style). |
| `style_adherence` | Style Adherence | Style | Match to requested artistic/photographic style. |

### What changed vs. the original

- **"Prompt Adherence" was split** into `prompt_adherence` (holistic/dense-prompt fidelity),
  `object_accuracy` (presence), and `attribute_binding` (the classic "red cube next to a blue sphere"
  failure mode) — mirroring GenEval and T2I-CompBench.
- **"Spatial Reasoning" was split** into `spatial_relationship` (positional) and `action_interaction`
  (non-spatial relations), matching T2I-CompBench's spatial vs. non-spatial split.
- **"Composition" became `composition_aesthetics`**, explicitly tied to human-preference/aesthetic
  signals.
- All other original dimensions were retained with sharper definitions.

### How the evaluator is driven

`DIM_LABELS`, `DIM_SHORT`, and `DIM_GUIDANCE` in `models.py` define the keys, radar labels, and the
per-dimension instructions injected into the evaluator system prompt (`services.py`). The benchmark
presets' `dim_map` annotations provide prompt-specific guidance per run. To add or revise a metric, edit
those maps — the schema the evaluator must return, the radar axes, and the comparison table update
automatically.

## Expanding the metric set later

Because the dimensions are data-driven, future work (e.g. adding an explicit "world-knowledge /
commonsense" axis, or per-benchmark sub-scores) is a matter of extending `DIM_LABELS` / `DIM_SHORT` /
`DIM_GUIDANCE`. The same LLM-as-judge pipeline the app already uses for image quality is the intended
foundation for richer, benchmark-style evaluation over time.
