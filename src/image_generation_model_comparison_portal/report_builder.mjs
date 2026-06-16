import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const [inputPath, outputPath] = process.argv.slice(2);

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

// --- Text fitting -----------------------------------------------------------
// The presentation library renders fixed-size shapes and does NOT reflow or
// shrink text that exceeds a shape, so long evaluation summaries used to spill
// past their boxes and overlap neighbours. These helpers estimate how much
// space a string needs and pick the largest font (down to a floor) that fits,
// truncating with an ellipsis only as a last resort. Factors are deliberately
// conservative (slightly over-estimating the space text needs) so the result
// never overflows.
const CHAR_WIDTH_FACTOR = 0.48;
const LINE_HEIGHT_FACTOR = 1.3;

function wrappedLineCount(text, fontSize, usableWidth) {
  const perLine = Math.max(1, Math.floor(usableWidth / (fontSize * CHAR_WIDTH_FACTOR)));
  let total = 0;
  for (const rawLine of String(text ?? "").split("\n")) {
    const words = rawLine.split(/\s+/).filter(Boolean);
    if (words.length === 0) {
      total += 1; // preserve blank lines
      continue;
    }
    let curLen = 0;
    let lineCount = 1;
    for (const word of words) {
      let wLen = word.length;
      if (curLen === 0) {
        while (wLen > perLine) {
          lineCount += 1;
          wLen -= perLine;
        }
        curLen = wLen;
      } else if (curLen + 1 + wLen <= perLine) {
        curLen += 1 + wLen;
      } else {
        lineCount += 1;
        while (wLen > perLine) {
          lineCount += 1;
          wLen -= perLine;
        }
        curLen = wLen;
      }
    }
    total += lineCount;
  }
  return Math.max(1, total);
}

function maxLinesFor(fontSize, usableHeight) {
  return Math.max(1, Math.floor(usableHeight / (fontSize * LINE_HEIGHT_FACTOR)));
}

function truncateToFit(text, fontSize, usableWidth, usableHeight) {
  const maxLines = maxLinesFor(fontSize, usableHeight);
  if (wrappedLineCount(text, fontSize, usableWidth) <= maxLines) {
    return text;
  }
  const tokens = String(text ?? "").split(/(\s+)/); // keep whitespace tokens
  let lo = 0;
  let hi = tokens.length;
  let best = "";
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const candidate = tokens.slice(0, mid).join("").replace(/\s+$/, "") + "\u2026";
    if (wrappedLineCount(candidate, fontSize, usableWidth) <= maxLines) {
      best = candidate;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return best || "\u2026";
}

function fitText(text, { width, height, insets, fontSize, minFontSize }) {
  const usableWidth = Math.max(8, width - (insets.left + insets.right));
  const usableHeight = Math.max(8, height - (insets.top + insets.bottom));
  const floor = Math.min(minFontSize, fontSize);
  for (let f = fontSize; f >= floor; f -= 1) {
    if (wrappedLineCount(text, f, usableWidth) <= maxLinesFor(f, usableHeight)) {
      return { text, fontSize: f };
    }
  }
  return { text: truncateToFit(text, floor, usableWidth, usableHeight), fontSize: floor };
}

function textShape(slide, options) {
  const {
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
    autofit = false,
    minFontSize,
  } = options;

  let renderText = String(text ?? "");
  let renderFontSize = fontSize;
  if (autofit) {
    const floor = minFontSize ?? Math.max(11, Math.round(fontSize * 0.6));
    const fitted = fitText(renderText, { width, height, insets, fontSize, minFontSize: floor });
    renderText = fitted.text;
    renderFontSize = fitted.fontSize;
  }

  const shape = slide.shapes.add({
    geometry: radius ? "roundRect" : "rect",
    position: { left, top, width, height },
    fill,
    line: { style: "solid", fill: lineFill, width: lineWidth },
  });
  shape.text = renderText;
  shape.text.fontSize = renderFontSize;
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
    width: 720,
    height: 92,
    fontSize: 32,
    bold: true,
    autofit: true,
    minFontSize: 22,
  });
  textShape(cover, {
    text: `Run ${run.id} • ${generated.length} generated • ${failed.length} failed`,
    left: 56,
    top: 136,
    width: 720,
    height: 28,
    fontSize: 14,
    color: COLORS.muted,
    autofit: true,
    minFontSize: 11,
  });
  textShape(cover, {
    text: run.prompt || "",
    left: 56,
    top: 176,
    width: 720,
    height: 222,
    fontSize: 18,
    fill: COLORS.panel,
    lineFill: COLORS.line,
    lineWidth: 1,
    radius: true,
    typeface: "Lato",
    autofit: true,
    minFontSize: 11,
  });
  textShape(cover, {
    text: `Prompt Guidance\n${fmt(run.promptGuidance?.summary, "No enrichment summary available.")}\n\nBenchmark\n${fmt(run.promptGuidance?.title, "Custom prompt")}`,
    left: 812,
    top: 176,
    width: 412,
    height: 222,
    fontSize: 18,
    fill: COLORS.panel2,
    lineFill: COLORS.cyan,
    lineWidth: 1,
    radius: true,
    typeface: "Lato",
    autofit: true,
    minFontSize: 11,
  });
  const leaderboard = ranked.slice(0, 5).map((result, index) => {
    const score = Number(result.evaluation?.overall_score || 0).toFixed(1);
    return `${index + 1}. ${result.model.name}  •  ${score}`;
  }).join("\n");
  textShape(cover, {
    text: `Top Results\n${leaderboard || "No evaluations yet."}`,
    left: 56,
    top: 420,
    width: 580,
    height: 230,
    fontSize: 18,
    fill: COLORS.panel,
    lineFill: COLORS.line,
    lineWidth: 1,
    radius: true,
    typeface: "Lato",
    autofit: true,
    minFontSize: 12,
  });
  textShape(cover, {
    text: failed.length
      ? `Generation Failures\n${failed.map((result) => `${result.model.name}: ${result.error}`).join("\n")}`
      : "Generation Failures\nNone",
    left: 664,
    top: 420,
    width: 560,
    height: 230,
    fontSize: 18,
    fill: COLORS.panel,
    lineFill: COLORS.line,
    lineWidth: 1,
    radius: true,
    typeface: "Lato",
    autofit: true,
    minFontSize: 12,
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
    autofit: true,
    minFontSize: 11,
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
      width: 690,
      height: 46,
      fontSize: 28,
      bold: true,
      autofit: true,
      minFontSize: 18,
    });
    textShape(slide, {
      text: `${result.model.kind} • ${fmt(result.model.deployment)}`,
      left: 40,
      top: 70,
      width: 690,
      height: 26,
      fontSize: 13,
      color: COLORS.muted,
      autofit: true,
      minFontSize: 10,
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
      top: 216,
      width: 476,
      height: 120,
      fontSize: 16,
      fill: COLORS.panel,
      lineFill: COLORS.line,
      lineWidth: 1,
      radius: true,
      typeface: "Lato",
      autofit: true,
      minFontSize: 11,
    });
    textShape(slide, {
      text: `Strengths\n${fmt((evaluation?.strengths || []).join("; "), "—")}\n\nWeaknesses\n${fmt((evaluation?.weaknesses || []).join("; "), "—")}`,
      left: 748,
      top: 348,
      width: 476,
      height: 150,
      fontSize: 15,
      fill: COLORS.panel,
      lineFill: COLORS.line,
      lineWidth: 1,
      radius: true,
      typeface: "Lato",
      autofit: true,
      minFontSize: 11,
    });
    textShape(slide, {
      text: `Dimension Scores\n${dimensionText(run, evaluation, Object.keys(run.dimLabels || {}).slice(0, 5))}`,
      left: 748,
      top: 510,
      width: 228,
      height: 154,
      fontSize: 14,
      fill: COLORS.panel,
      lineFill: COLORS.line,
      lineWidth: 1,
      radius: true,
      typeface: "Lato",
      autofit: true,
      minFontSize: 10,
    });
    textShape(slide, {
      text: `Dimension Scores\n${dimensionText(run, evaluation, Object.keys(run.dimLabels || {}).slice(5, 10))}`,
      left: 996,
      top: 510,
      width: 228,
      height: 154,
      fontSize: 14,
      fill: COLORS.panel,
      lineFill: COLORS.line,
      lineWidth: 1,
      radius: true,
      typeface: "Lato",
      autofit: true,
      minFontSize: 10,
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
      autofit: true,
      minFontSize: 9,
    });
  }

  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(outputPath);
}

const invokedDirectly =
  process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (invokedDirectly) {
  if (!inputPath || !outputPath) {
    console.error("Usage: node report_builder.mjs <input.json> <output.pptx>");
    process.exit(1);
  }
  main().catch((error) => {
    console.error(error?.stack || String(error));
    process.exit(1);
  });
}

export { wrappedLineCount, maxLinesFor, truncateToFit, fitText };
