import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const [inputPath, outputPath] = process.argv.slice(2);

if (!inputPath || !outputPath) {
  console.error("Usage: node report_builder.mjs <input.json> <output.pptx>");
  process.exit(1);
}

const COLORS = {
  bg: "#071626",
  bg2: "#0B2034",
  panel: "#0D243A",
  panel2: "#12314E",
  line: "#1C4A70",
  text: "#EAF7FF",
  muted: "#8EAFC5",
  cyan: "#00D8FF",
  pink: "#FF4F9A",
  green: "#38D39F",
  amber: "#FFB648",
  red: "#FF6B7F",
  transparent: "#00000000",
};

function textShape(slide, {
  text,
  left,
  top,
  width,
  height,
  fontSize = 20,
  color = COLORS.text,
  fill = COLORS.transparent,
  lineFill = COLORS.transparent,
  lineWidth = 0,
  bold = false,
  typeface = "Poppins",
  align = "left",
  radius = false,
  insets = { left: 14, right: 14, top: 12, bottom: 12 },
}) {
  const shape = slide.shapes.add({
    geometry: radius ? "roundRect" : "rect",
    position: { left, top, width, height },
    fill,
    line: { style: "solid", fill: lineFill, width: lineWidth },
  });
  shape.text = String(text ?? "");
  shape.text.fontSize = fontSize;
  shape.text.color = color;
  shape.text.bold = bold;
  shape.text.typeface = typeface;
  shape.text.alignment = align;
  shape.text.insets = insets;
  return shape;
}

function metricCard(slide, { label, value, left, top, width, fill, accent }) {
  textShape(slide, {
    text: `${label}\n${value}`,
    left,
    top,
    width,
    height: 84,
    fontSize: 16,
    fill,
    lineFill: accent,
    lineWidth: 1,
    radius: true,
  });
}

function scoreColor(value) {
  const score = Number(value || 0);
  if (score >= 7.5) return COLORS.green;
  if (score >= 5) return COLORS.amber;
  return COLORS.red;
}

function fmt(value, fallback = "—") {
  return value == null || value === "" ? fallback : String(value);
}

function dimensionText(run, evaluation, keys) {
  return keys.map((key) => {
    const label = run.dimLabels?.[key] || key;
    const score = evaluation?.dimensions?.[key]?.score;
    return `${label}: ${fmt(score)}`;
  }).join("\n");
}

function cvSnapshot(result) {
  if (!result.cv) {
    return "CV pending.";
  }
  if (result.cv.error) {
    return `CV error: ${result.cv.error}`;
  }
  const counts = Object.entries(result.cv.counts || {});
  const tags = (result.cv.tags || []).slice(0, 8).map((item) => `${item[0]} ${Math.round(item[1] * 100)}%`);
  const lines = [];
  lines.push(counts.length ? `Objects: ${counts.map(([name, count]) => `${name} x${count}`).join(", ")}` : "Objects: none");
  lines.push(tags.length ? `Tags: ${tags.join(", ")}` : "Tags: none");
  return lines.join("\n");
}

async function main() {
  const raw = await fs.readFile(inputPath, "utf8");
  const run = JSON.parse(raw);
  const generated = run.order
    .map((name) => run.results[name])
    .filter((result) => result?.generation?.imageDataUrl);

  if (!generated.length) {
    throw new Error("No generated results were available for report export.");
  }

  const failed = run.order
    .map((name) => run.results[name])
    .filter((result) => result?.error && !result?.generation?.imageDataUrl);

  const ranked = [...generated].sort((a, b) => {
    const aScore = Number(a.evaluation?.overall_score || 0);
    const bScore = Number(b.evaluation?.overall_score || 0);
    return bScore - aScore;
  });

  const presentation = Presentation.create({
    slideSize: { width: 1280, height: 720 },
  });

  const cover = presentation.slides.add();
  cover.background.fill = COLORS.bg;
  textShape(cover, {
    text: "Image Generation Model Comparison Portal Report",
    left: 56,
    top: 40,
    width: 620,
    height: 60,
    fontSize: 32,
    bold: true,
  });
  textShape(cover, {
    text: `Run ${run.id} • ${generated.length} generated • ${failed.length} failed`,
    left: 56,
    top: 98,
    width: 520,
    height: 34,
    fontSize: 14,
    color: COLORS.muted,
  });
  textShape(cover, {
    text: run.prompt || "",
    left: 56,
    top: 150,
    width: 720,
    height: 230,
    fontSize: 18,
    fill: COLORS.panel,
    lineFill: COLORS.line,
    lineWidth: 1,
    radius: true,
    typeface: "Lato",
  });
  textShape(cover, {
    text: `Prompt Guidance\n${fmt(run.promptGuidance?.summary, "No enrichment summary available.")}\n\nBenchmark\n${fmt(run.promptGuidance?.title, "Custom prompt")}`,
    left: 812,
    top: 150,
    width: 412,
    height: 230,
    fontSize: 18,
    fill: COLORS.panel2,
    lineFill: COLORS.cyan,
    lineWidth: 1,
    radius: true,
    typeface: "Lato",
  });
  const leaderboard = ranked.slice(0, 5).map((result, index) => {
    const score = Number(result.evaluation?.overall_score || 0).toFixed(1);
    return `${index + 1}. ${result.model.name}  •  ${score}`;
  }).join("\n");
  textShape(cover, {
    text: `Top Results\n${leaderboard || "No evaluations yet."}`,
    left: 56,
    top: 414,
    width: 580,
    height: 230,
    fontSize: 18,
    fill: COLORS.panel,
    lineFill: COLORS.line,
    lineWidth: 1,
    radius: true,
    typeface: "Lato",
  });
  textShape(cover, {
    text: failed.length
      ? `Generation Failures\n${failed.map((result) => `${result.model.name}: ${result.error}`).join("\n")}`
      : "Generation Failures\nNone",
    left: 664,
    top: 414,
    width: 560,
    height: 230,
    fontSize: 18,
    fill: COLORS.panel,
    lineFill: COLORS.line,
    lineWidth: 1,
    radius: true,
    typeface: "Lato",
  });

  const comparison = presentation.slides.add();
  comparison.background.fill = COLORS.bg;
  textShape(comparison, {
    text: "Comparison Snapshot",
    left: 56,
    top: 40,
    width: 500,
    height: 52,
    fontSize: 28,
    bold: true,
  });
  textShape(comparison, {
    text: ranked.map((result, index) => {
      const evaluation = result.evaluation;
      const metrics = result.metrics || {};
      return `${index + 1}. ${result.model.name}
Overall: ${evaluation ? Number(evaluation.overall_score || 0).toFixed(1) : "—"}   Time: ${fmt(metrics.elapsedS != null ? `${Number(metrics.elapsedS).toFixed(2)}s` : null)}
Tokens: ${fmt(metrics.totalTokens)}   Deployment: ${fmt(result.model.deployment)}
Summary: ${fmt(evaluation?.summary, "Evaluation pending.")}`;
    }).join("\n\n"),
    left: 56,
    top: 112,
    width: 1168,
    height: 552,
    fontSize: 18,
    fill: COLORS.panel,
    lineFill: COLORS.line,
    lineWidth: 1,
    radius: true,
    typeface: "Lato",
  });

  for (const result of generated) {
    const slide = presentation.slides.add();
    slide.background.fill = COLORS.bg;
    const evaluation = result.evaluation;
    const overall = Number(evaluation?.overall_score || 0);

    textShape(slide, {
      text: result.model.name,
      left: 40,
      top: 26,
      width: 560,
      height: 46,
      fontSize: 28,
      bold: true,
    });
    textShape(slide, {
      text: `${result.model.kind} • ${fmt(result.model.deployment)}`,
      left: 40,
      top: 70,
      width: 540,
      height: 26,
      fontSize: 13,
      color: COLORS.muted,
    });
    const image = slide.images.add({
      dataUrl: result.generation.imageDataUrl,
      fit: "contain",
      alt: result.model.name,
    });
    image.position = { left: 40, top: 120, width: 670, height: 520 };

    metricCard(slide, {
      label: "Overall",
      value: evaluation ? overall.toFixed(1) : "—",
      left: 748,
      top: 120,
      width: 148,
      fill: COLORS.panel2,
      accent: scoreColor(overall),
    });
    metricCard(slide, {
      label: "Time",
      value: result.metrics?.elapsedS != null ? `${Number(result.metrics.elapsedS).toFixed(2)}s` : "—",
      left: 914,
      top: 120,
      width: 148,
      fill: COLORS.panel2,
      accent: COLORS.cyan,
    });
    metricCard(slide, {
      label: "Tokens",
      value: fmt(result.metrics?.totalTokens),
      left: 1080,
      top: 120,
      width: 144,
      fill: COLORS.panel2,
      accent: COLORS.pink,
    });

    textShape(slide, {
      text: `Evaluation Summary\n${fmt(evaluation?.summary, "Evaluation pending.")}`,
      left: 748,
      top: 220,
      width: 476,
      height: 104,
      fontSize: 17,
      fill: COLORS.panel,
      lineFill: COLORS.line,
      lineWidth: 1,
      radius: true,
      typeface: "Lato",
    });
    textShape(slide, {
      text: `Strengths\n${fmt((evaluation?.strengths || []).join("; "), "—")}\n\nWeaknesses\n${fmt((evaluation?.weaknesses || []).join("; "), "—")}`,
      left: 748,
      top: 338,
      width: 476,
      height: 132,
      fontSize: 16,
      fill: COLORS.panel,
      lineFill: COLORS.line,
      lineWidth: 1,
      radius: true,
      typeface: "Lato",
    });
    textShape(slide, {
      text: `Dimension Scores\n${dimensionText(run, evaluation, Object.keys(run.dimLabels || {}).slice(0, 5))}`,
      left: 748,
      top: 486,
      width: 228,
      height: 178,
      fontSize: 14,
      fill: COLORS.panel,
      lineFill: COLORS.line,
      lineWidth: 1,
      radius: true,
      typeface: "Lato",
    });
    textShape(slide, {
      text: `Dimension Scores\n${dimensionText(run, evaluation, Object.keys(run.dimLabels || {}).slice(5, 10))}`,
      left: 996,
      top: 486,
      width: 228,
      height: 178,
      fontSize: 14,
      fill: COLORS.panel,
      lineFill: COLORS.line,
      lineWidth: 1,
      radius: true,
      typeface: "Lato",
    });
    textShape(slide, {
      text: cvSnapshot(result),
      left: 40,
      top: 650,
      width: 670,
      height: 46,
      fontSize: 12,
      color: COLORS.muted,
      typeface: "Lato",
    });
  }

  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(outputPath);
}

main().catch((error) => {
  console.error(error?.stack || String(error));
  process.exit(1);
});
