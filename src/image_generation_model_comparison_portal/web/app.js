const state = {
  bootstrap: null,
  runId: null,
  run: null,
  pollTimer: null,
  promptGuidance: {
    text: { title: "", dimensionMap: {} },
    edit: { title: "", dimensionMap: {} },
  },
  editMask: {
    sourceDataUrl: "",
    sourceName: "",
    sourceCount: 0,
    sourceWidth: 0,
    sourceHeight: 0,
    bufferCanvas: null,
    drawing: false,
    lastPoint: null,
    mode: "paint",
    brushSize: 40,
  },
  radarColors: [
    "rgba(0, 216, 255, ",
    "rgba(255, 79, 154, ",
    "rgba(56, 211, 159, ",
    "rgba(255, 182, 72, ",
    "rgba(120, 160, 255, ",
    "rgba(157, 118, 255, ",
  ],
  modelOptions: [
    ["gpt-image-1", "GPT-Image-1"],
    ["gpt-image-1.5", "GPT-Image-1.5"],
    ["gpt-image-2", "GPT-Image-2"],
    ["flux-2-pro", "FLUX.2-pro"],
    ["flux-2-flex", "FLUX.2-flex"],
    ["flux-kontext-pro", "FLUX.1-Kontext-pro"],
    ["flux-pro-1.1", "FLUX-1.1-pro"],
    ["mai-image-2", "MAI-Image-2"],
    ["mai-image-2e", "MAI-Image-2e"],
  ],
};

const byId = (id) => document.getElementById(id);

function modelLabel(kind) {
  return state.modelOptions.find(([value]) => value === kind)?.[1] || kind;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed.");
  }
  return payload;
}

function initStaticOptions() {
  fillSelect(byId("globalAuthType"), ["apiKey", "bearer"]);
  fillSelect(byId("autoEval"), ["yes", "no"]);
  fillSelect(byId("evalDetail"), ["high", "low"]);
  fillSelect(byId("cvEnabled"), ["yes", "no"]);
  fillSelect(byId("textSize"), ["1024x1024", "1024x1536", "1536x1024", "auto"]);
  fillSelect(byId("textQuality"), ["high", "medium", "low"]);
  fillSelect(byId("outputFormat"), ["png", "jpeg"]);
  fillSelect(byId("editSize"), ["1024x1024", "1024x1536", "1536x1024"]);
}

function fillSelect(select, options) {
  select.innerHTML = "";
  options.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
}

function loadConfig(config) {
  byId("globalEndpoint").value = config.global_endpoint || "";
  byId("globalSecret").value = config.global_secret || "";
  byId("globalAuthType").value = config.global_auth_type || "apiKey";
  byId("gptApiVersion").value = config.gpt_api_version || "2025-04-01-preview";
  byId("fluxApiVersion").value = config.flux_api_version || "preview";
  byId("visionApiVersion").value = config.vision_api_version || "2023-10-01";
  byId("evalDeployment").value = config.eval_deployment || "";
  byId("autoEval").value = config.auto_eval || "yes";
  byId("evalDetail").value = config.eval_detail || "high";
  byId("cvEnabled").value = config.cv_enabled || "yes";
  byId("cvEndpoint").value = config.cv_endpoint || "";
  byId("cvSecret").value = config.cv_secret || "";
  renderModels(config.models || []);
}

function collectConfig() {
  return {
    global_endpoint: byId("globalEndpoint").value.trim(),
    global_secret: byId("globalSecret").value.trim(),
    global_auth_type: byId("globalAuthType").value,
    gpt_api_version: byId("gptApiVersion").value.trim(),
    flux_api_version: byId("fluxApiVersion").value.trim(),
    vision_api_version: byId("visionApiVersion").value.trim(),
    eval_deployment: byId("evalDeployment").value.trim(),
    auto_eval: byId("autoEval").value,
    eval_detail: byId("evalDetail").value,
    cv_enabled: byId("cvEnabled").value,
    cv_endpoint: byId("cvEndpoint").value.trim(),
    cv_secret: byId("cvSecret").value.trim(),
    models: collectModels(),
  };
}

function renderModels(models) {
  const list = byId("modelsList");
  list.innerHTML = "";
  models.forEach((model) => list.appendChild(buildModelRow(model)));
}

function buildModelRow(model = {}) {
  const node = byId("modelRowTemplate").content.firstElementChild.cloneNode(true);
  const enabled = node.querySelector(".model-enabled");
  const kind = node.querySelector(".model-kind");
  const deployment = node.querySelector(".model-deployment");
  state.modelOptions.forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    kind.appendChild(option);
  });
  enabled.checked = model.enabled !== false;
  kind.value = model.kind || "gpt-image-1";
  deployment.value = model.deployment || model.name || "";
  let priorLabel = modelLabel(kind.value);
  kind.addEventListener("change", () => {
    if (!deployment.value.trim() || deployment.value.trim() === priorLabel) {
      deployment.value = modelLabel(kind.value);
    }
    priorLabel = modelLabel(kind.value);
  });
  node.querySelector(".remove-model-btn").addEventListener("click", () => node.remove());
  return node;
}

function collectModels() {
  const raw = [...document.querySelectorAll(".model-row")].map((row) => ({
    enabled: row.querySelector(".model-enabled").checked,
    kind: row.querySelector(".model-kind").value,
    deployment: row.querySelector(".model-deployment").value.trim(),
  }));
  const counts = new Map();
  raw.forEach((model) => {
    const label = modelLabel(model.kind);
    counts.set(label, (counts.get(label) || 0) + 1);
  });
  const usedNames = new Set();
  return raw.map((model, index) => {
    const label = modelLabel(model.kind);
    let name = label;
    if ((counts.get(label) || 0) > 1) {
      name = `${label} · ${model.deployment || index + 1}`;
    }
    let suffix = 2;
    while (usedNames.has(name)) {
      name = `${label} · ${model.deployment || suffix}`;
      suffix += 1;
    }
    usedNames.add(name);
    return {
      ...model,
      name,
    };
  });
}

function enabledModels() {
  return collectModels().filter((model) => model.enabled);
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      byId(`tab-${button.dataset.tab}`).classList.add("active");
    });
  });
}

function setStatus(text) {
  byId("globalStatus").textContent = text;
}

function setProgress(done, total) {
  const width = total ? Math.round((done / total) * 100) : 0;
  byId("progressFill").style.width = `${width}%`;
}

function setRunButtonsDisabled(disabled) {
  byId("runTextBtn").disabled = disabled;
  byId("runEditBtn").disabled = disabled;
}

function showRequestOverlay(title, detail) {
  byId("requestOverlayTitle").textContent = title;
  byId("requestOverlayDetail").textContent = detail;
  byId("requestOverlay").classList.remove("hidden");
}

function hideRequestOverlay() {
  byId("requestOverlay").classList.add("hidden");
}

function canExportReport(run) {
  return Boolean(run && run.order.some((name) => run.results[name]?.generation));
}

function renderPreset(key) {
  renderPresetForMode(key, "text");
}

function renderPresetForMode(key, mode = activeTab()) {
  const preset = state.bootstrap.presets[key];
  if (mode === "edit") {
    byId("editPrompt").value = preset.prompt;
  } else {
    byId("textPrompt").value = preset.prompt;
  }
  renderBenchAnnotation(preset.title, preset.dim_map || {}, mode);
  getBenchElements(mode).status.textContent = `Loaded "${preset.title}".`;
}

function getBenchElements(mode = activeTab()) {
  if (mode === "edit") {
    return {
      idea: byId("editBenchIdea"),
      status: byId("editBenchStatus"),
      annotation: byId("editBenchAnnotation"),
      button: byId("editGenerateBenchmarkBtn"),
    };
  }
  return {
    idea: byId("benchIdea"),
    status: byId("benchStatus"),
    annotation: byId("benchAnnotation"),
    button: byId("generateBenchmarkBtn"),
  };
}

function renderBenchAnnotation(title, dimensionMap, mode = activeTab()) {
  state.promptGuidance[mode] = { title: title || "", dimensionMap: dimensionMap || {} };
  const labels = state.bootstrap.dimLabels;
  const grid = Object.keys(labels)
    .map((key) => `<div class="bench-tag"><span class="k">${escapeHtml(labels[key])}</span><span class="v">${escapeHtml(dimensionMap?.[key] || "—")}</span></div>`)
    .join("");
  getBenchElements(mode).annotation.innerHTML = `<div class="bench-title">${escapeHtml(title || "Benchmark")}</div><div class="bench-tag-grid">${grid}</div>`;
}

async function generateBenchmark(mode = activeTab()) {
  const bench = getBenchElements(mode);
  const idea = bench.idea.value.trim();
  if (!idea) {
    alert("Type a benchmark idea first.");
    return;
  }
  bench.button.disabled = true;
  bench.status.textContent = "Building benchmark...";
  try {
    const payload = await api("/api/benchmark", {
      method: "POST",
      body: JSON.stringify({ config: collectConfig(), idea }),
    });
    if (mode === "edit") {
      byId("editPrompt").value = payload.prompt || "";
    } else {
      byId("textPrompt").value = payload.prompt || "";
    }
    renderBenchAnnotation(payload.title || "Benchmark", payload.dimension_map || {}, mode);
    bench.status.textContent = `Loaded "${payload.title || "Benchmark"}".`;
  } catch (error) {
    bench.status.textContent = error.message;
  } finally {
    bench.button.disabled = false;
  }
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function readFiles(files) {
  const entries = [];
  for (const file of files) {
    entries.push({
      name: file.name,
      dataUrl: await readFileAsDataUrl(file),
    });
  }
  return entries;
}

function editMaskBuffer() {
  if (!state.editMask.bufferCanvas) {
    state.editMask.bufferCanvas = document.createElement("canvas");
    state.editMask.bufferCanvas.width = 1;
    state.editMask.bufferCanvas.height = 1;
  }
  return state.editMask.bufferCanvas;
}

function hasMaskPaint() {
  if (!state.editMask.sourceDataUrl) {
    return false;
  }
  const buffer = editMaskBuffer();
  const ctx = buffer.getContext("2d", { willReadFrequently: true });
  const pixels = ctx.getImageData(0, 0, buffer.width, buffer.height).data;
  for (let index = 3; index < pixels.length; index += 4) {
    if (pixels[index] > 0) {
      return true;
    }
  }
  return false;
}

function updateMaskMeta() {
  const fileMeta = byId("maskFileMeta");
  if (!state.editMask.sourceDataUrl) {
    fileMeta.textContent = "Select a source image to paint a mask.";
    return;
  }
  fileMeta.textContent = hasMaskPaint()
    ? `Mask ready for ${state.editMask.sourceName}.`
    : "No mask drawn.";
}

function setMaskMode(mode) {
  state.editMask.mode = mode;
  byId("maskPaintBtn").classList.toggle("active-tool", mode === "paint");
  byId("maskEraseBtn").classList.toggle("active-tool", mode === "erase");
}

function redrawMaskOverlay() {
  const canvas = byId("editMaskCanvas");
  const frame = byId("editPreviewFrame");
  if (!state.editMask.sourceDataUrl || frame.classList.contains("hidden")) {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width || 1, canvas.height || 1);
    return;
  }
  const rect = frame.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, width, height);
  ctx.drawImage(editMaskBuffer(), 0, 0, width, height);
  ctx.globalCompositeOperation = "source-in";
  ctx.fillStyle = "rgba(0, 216, 255, 0.35)";
  ctx.fillRect(0, 0, width, height);
  ctx.globalCompositeOperation = "source-over";
}

function clearMaskBuffer() {
  const buffer = editMaskBuffer();
  const ctx = buffer.getContext("2d");
  ctx.clearRect(0, 0, buffer.width, buffer.height);
  redrawMaskOverlay();
  updateMaskMeta();
}

function resetEditMaskEditor() {
  state.editMask.sourceDataUrl = "";
  state.editMask.sourceName = "";
  state.editMask.sourceCount = 0;
  state.editMask.sourceWidth = 0;
  state.editMask.sourceHeight = 0;
  state.editMask.drawing = false;
  state.editMask.lastPoint = null;
  const frame = byId("editPreviewFrame");
  frame.classList.add("hidden");
  byId("editPreviewImage").removeAttribute("src");
  byId("editPreviewEmpty").classList.remove("hidden");
  byId("editPreviewEmpty").textContent = "Select a source image to preview and paint a mask.";
  byId("editPreviewMeta").textContent = "Mask applies to the first selected image.";
  clearMaskBuffer();
}

function maskPoint(event) {
  const canvas = byId("editMaskCanvas");
  const rect = canvas.getBoundingClientRect();
  const scaleX = state.editMask.sourceWidth / rect.width;
  const scaleY = state.editMask.sourceHeight / rect.height;
  return {
    x: (event.clientX - rect.left) * scaleX,
    y: (event.clientY - rect.top) * scaleY,
    brush: state.editMask.brushSize * scaleX,
  };
}

function drawMaskStroke(from, to) {
  const buffer = editMaskBuffer();
  const ctx = buffer.getContext("2d");
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.lineWidth = Math.max(2, to.brush);
  if (state.editMask.mode === "erase") {
    ctx.globalCompositeOperation = "destination-out";
    ctx.strokeStyle = "rgba(0, 0, 0, 1)";
  } else {
    ctx.globalCompositeOperation = "source-over";
    ctx.strokeStyle = "rgba(255, 255, 255, 1)";
  }
  if (Math.abs(from.x - to.x) < 0.01 && Math.abs(from.y - to.y) < 0.01) {
    ctx.fillStyle = ctx.strokeStyle;
    ctx.beginPath();
    ctx.arc(to.x, to.y, ctx.lineWidth / 2, 0, Math.PI * 2);
    ctx.fill();
  } else {
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
  }
  ctx.restore();
  redrawMaskOverlay();
}

function beginMaskStroke(event) {
  if (!state.editMask.sourceDataUrl) {
    return;
  }
  event.preventDefault();
  const point = maskPoint(event);
  state.editMask.drawing = true;
  state.editMask.lastPoint = point;
  drawMaskStroke(point, point);
  byId("editMaskCanvas").setPointerCapture(event.pointerId);
}

function moveMaskStroke(event) {
  if (!state.editMask.drawing) {
    return;
  }
  event.preventDefault();
  const point = maskPoint(event);
  drawMaskStroke(state.editMask.lastPoint, point);
  state.editMask.lastPoint = point;
}

function endMaskStroke(event) {
  if (!state.editMask.drawing) {
    return;
  }
  event.preventDefault();
  state.editMask.drawing = false;
  state.editMask.lastPoint = null;
  updateMaskMeta();
}

async function loadEditPreview(fileList) {
  const files = [...fileList];
  byId("sourceFilesMeta").textContent = files.length ? files.map((file) => file.name).join(", ") : "No source images selected.";
  if (!files.length) {
    resetEditMaskEditor();
    return;
  }
  const primaryFile = files[0];
  const dataUrl = await readFileAsDataUrl(primaryFile);
  const image = byId("editPreviewImage");
  await new Promise((resolve, reject) => {
    image.onload = resolve;
    image.onerror = reject;
    image.src = dataUrl;
  });
  state.editMask.sourceDataUrl = dataUrl;
  state.editMask.sourceName = primaryFile.name;
  state.editMask.sourceCount = files.length;
  state.editMask.sourceWidth = image.naturalWidth || 1;
  state.editMask.sourceHeight = image.naturalHeight || 1;
  const buffer = editMaskBuffer();
  buffer.width = state.editMask.sourceWidth;
  buffer.height = state.editMask.sourceHeight;
  clearMaskBuffer();
  byId("editPreviewFrame").classList.remove("hidden");
  byId("editPreviewEmpty").classList.add("hidden");
  byId("editPreviewMeta").textContent = files.length > 1
    ? `Previewing ${primaryFile.name}. ${files.length - 1} additional source image(s) will still be sent when supported.`
    : `Previewing ${primaryFile.name}.`;
  redrawMaskOverlay();
}

async function buildEditMaskPayload() {
  if (!state.editMask.sourceDataUrl || !hasMaskPaint()) {
    return [];
  }
  const buffer = editMaskBuffer();
  const exportCanvas = document.createElement("canvas");
  exportCanvas.width = buffer.width;
  exportCanvas.height = buffer.height;
  const ctx = exportCanvas.getContext("2d");
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, exportCanvas.width, exportCanvas.height);
  ctx.globalCompositeOperation = "destination-out";
  ctx.drawImage(buffer, 0, 0);
  return [{
    name: "mask.png",
    dataUrl: exportCanvas.toDataURL("image/png"),
  }];
}

function activeTab() {
  return document.querySelector(".tab.active").dataset.tab;
}

async function startRun(mode) {
  const models = enabledModels();
  if (!models.length) {
    alert("Enable at least one model.");
    return;
  }
  const prompt = mode === "text" ? byId("textPrompt").value.trim() : byId("editPrompt").value.trim();
  if (!prompt) {
    alert("Prompt required.");
    return;
  }
  if (mode === "edit" && !byId("editSourceFiles").files.length) {
    alert("Edit mode requires source images.");
    return;
  }
  showRequestOverlay("Sending requests...", "Preparing the prompt, images, and backend run state.");
  setRunButtonsDisabled(true);
  byId("exportReportBtn").disabled = true;
  try {
    const payload = {
      config: collectConfig(),
      mode,
      prompt,
      promptGuidance: state.promptGuidance[mode] || { title: "", dimensionMap: {} },
      models,
      textSize: byId("textSize").value,
      textQuality: byId("textQuality").value,
      outputFormat: byId("outputFormat").value,
      editSize: byId("editSize").value,
      sourceFiles: mode === "edit" ? await readFiles(byId("editSourceFiles").files) : [],
      maskFiles: mode === "edit" ? await buildEditMaskPayload() : [],
    };
    const response = await api("/api/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.runId = response.runId;
    state.run = null;
    byId("resultsGrid").innerHTML = "";
    byId("comparisonTable").innerHTML = "No evaluations yet.";
    byId("comparisonTable").classList.add("empty");
    setStatus("Running...");
    byId("reEvalBtn").disabled = true;
    startPolling();
  } catch (error) {
    setStatus(error.message);
    alert(error.message);
  } finally {
    hideRequestOverlay();
    setRunButtonsDisabled(false);
  }
}

function startPolling() {
  stopPolling();
  refreshRun();
  state.pollTimer = window.setInterval(refreshRun, 1200);
}

function stopPolling() {
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

async function refreshRun() {
  if (!state.runId) {
    return;
  }
  const run = await api(`/api/runs/${state.runId}`);
  state.run = run;
  renderRun(run);
  if (run.status === "ready" && (run.phase === "complete" || run.phase === "idle")) {
    stopPolling();
    byId("reEvalBtn").disabled = false;
  }
}

function renderRun(run) {
  setStatus(`${run.progress.label} ${run.progress.done}/${run.progress.total}`);
  setProgress(run.progress.done, run.progress.total);
  byId("exportReportBtn").disabled = !canExportReport(run) || run.status === "running";
  const grid = byId("resultsGrid");
  if (!grid.children.length) {
    run.order.forEach((name) => grid.appendChild(buildResultCard(run.results[name])));
  }
  run.order.forEach((name) => updateResultCard(grid.querySelector(`[data-model="${cssEscape(name)}"]`), run.results[name]));
  renderComparison(run);
  renderLog(run.errorLog || []);
}

function buildResultCard(result) {
  const node = byId("resultCardTemplate").content.firstElementChild.cloneNode(true);
  node.dataset.model = result.model.name;
  node.dataset.bboxVisible = "true";
  node.querySelector(".download-btn").addEventListener("click", () => downloadResult(result.model.name));
  node.querySelector(".retry-btn").addEventListener("click", () => retryGeneration(result.model.name));
  node.querySelector(".eval-btn").addEventListener("click", () => triggerEvaluation(result.model.name));
  node.querySelector(".bbox-btn").addEventListener("click", () => {
    node.dataset.bboxVisible = node.dataset.bboxVisible === "true" ? "false" : "true";
    updateBboxButton(node);
    if (state.run?.results?.[result.model.name]) {
      renderPreview(node, state.run.results[result.model.name]);
    }
  });
  node.querySelector(".toggle-json-btn").addEventListener("click", () => {
    node.querySelector(".json-panel").classList.toggle("hidden");
  });
  updateBboxButton(node);
  return node;
}

function updateResultCard(node, result) {
  if (!node) {
    return;
  }
  node.querySelector(".result-title").textContent = result.model.name;
  const metaBits = [`${result.model.kind}`, result.model.deployment || "-"];
  if (result.generation?.editFallbackUsed) {
    metaBits.push("MAI edit fallback");
  }
  if (state.run?.promptGuidance?.usedEnrichment) {
    metaBits.push("Prompt enriched");
  }
  node.querySelector(".result-meta").textContent = metaBits.join(" | ");
  node.querySelector(".result-state").textContent = result.status || "Queued...";
  node.querySelector(".download-btn").disabled = !result.generation?.imageDataUrl;
  node.querySelector(".eval-btn").disabled = !result.generation?.imageDataUrl;
  const showRetry = Boolean(result.error && !result.generation?.imageDataUrl);
  const retryBtn = node.querySelector(".retry-btn");
  retryBtn.classList.toggle("hidden", !showRetry);
  retryBtn.disabled = state.run?.status === "running";
  renderMetrics(node.querySelector(".metrics-grid"), result.metrics || {});
  renderPreview(node, result);
  renderVision(node, result.cv);
  renderEvaluation(node, result.evaluation);
  node.querySelector(".json-generation").textContent = pretty(result.generation?.response);
  node.querySelector(".json-cv").textContent = pretty(result.cv?.raw || result.cv);
  node.querySelector(".json-eval").textContent = pretty(result.evaluation?.raw_payload || result.evaluation);
}

function renderMetrics(container, metrics) {
  const chips = [];
  const items = [
    ["Time", metrics.elapsedS != null ? `${Number(metrics.elapsedS).toFixed(2)}s` : "—"],
    ["Input", metrics.inputTokens != null ? metrics.inputTokens : "—"],
    ["Output", metrics.outputTokens != null ? metrics.outputTokens : "—"],
    ["Total", metrics.totalTokens != null ? metrics.totalTokens : "—"],
  ];
  container.innerHTML = "";
  items.forEach(([label, value]) => {
    const chip = document.createElement("div");
    chip.className = "metric-chip";
    chip.innerHTML = `<span class="label">${label}</span><span class="value">${value}</span>`;
    container.appendChild(chip);
  });
}

function renderPreview(node, result) {
  const image = node.querySelector(".result-image");
  const overlay = node.querySelector(".bbox-layer");
  const showBbox = node.dataset.bboxVisible !== "false";
  overlay.classList.toggle("hidden", !showBbox);
  if (!result.generation?.imageDataUrl) {
    image.classList.remove("has-image");
    image.removeAttribute("src");
    overlay.innerHTML = "";
    return;
  }
  if (image.src !== result.generation.imageDataUrl) {
    image.src = result.generation.imageDataUrl;
  }
  image.classList.add("has-image");
  const renderBoxes = () => {
    overlay.innerHTML = "";
    if (!showBbox || !result.cv?.objects?.length || !image.naturalWidth || !image.naturalHeight) {
      return;
    }
    const host = overlay.getBoundingClientRect();
    const imageRatio = Math.min(host.width / image.naturalWidth, host.height / image.naturalHeight);
    const drawWidth = image.naturalWidth * imageRatio;
    const drawHeight = image.naturalHeight * imageRatio;
    const offsetLeft = (host.width - drawWidth) / 2;
    const offsetTop = (host.height - drawHeight) / 2;
    result.cv.objects.forEach((box) => {
      const div = document.createElement("div");
      div.className = "bbox";
      div.style.left = `${offsetLeft + (box.x / image.naturalWidth) * drawWidth}px`;
      div.style.top = `${offsetTop + (box.y / image.naturalHeight) * drawHeight}px`;
      div.style.width = `${(box.w / image.naturalWidth) * drawWidth}px`;
      div.style.height = `${(box.h / image.naturalHeight) * drawHeight}px`;
      const label = document.createElement("span");
      label.className = "bbox-label";
      label.textContent = `${box.label} ${Math.round(box.confidence * 100)}%`;
      div.appendChild(label);
      overlay.appendChild(div);
    });
  };
  if (image.complete) {
    renderBoxes();
  } else {
    image.onload = renderBoxes;
  }
}

function renderVision(node, cv) {
  const target = node.querySelector(".vision-summary");
  if (!cv) {
    target.textContent = "CV pending.";
    return;
  }
  if (cv.error) {
    target.textContent = `CV error: ${cv.error}`;
    return;
  }
  const counts = Object.entries(cv.counts || {});
  const tags = (cv.tags || []).slice(0, 10).map((item) => `${item[0]} ${Math.round(item[1] * 100)}%`);
  const lines = [];
  lines.push(counts.length ? `Objects: ${counts.map(([name, count]) => `${name} x${count}`).join(", ")}` : "Objects: none");
  lines.push(tags.length ? `Tags: ${tags.join(", ")}` : "Tags: none");
  target.textContent = lines.join("\n");
}

function renderEvaluation(node, evaluation) {
  const target = node.querySelector(".eval-summary");
  const details = node.querySelector(".eval-details");
  const barsHost = node.querySelector(".eval-bars");
  if (!evaluation) {
    target.textContent = "Evaluation pending.";
    details.innerHTML = "";
    barsHost.innerHTML = "";
    return;
  }
  if (evaluation.error) {
    target.textContent = `Evaluation error: ${evaluation.error}`;
    details.innerHTML = "";
    barsHost.innerHTML = "";
    return;
  }
  const overall = Number(evaluation.overall_score || 0);
  const ringClass = overall >= 7.5 ? "high" : overall >= 5 ? "mid" : "low";
  const badges = [];
  if (evaluation.cv_augmented) {
    badges.push('<span class="mini-pill cv">CV augmented</span>');
  }
  if (evaluation.finish_reason === "length") {
    badges.push('<span class="mini-pill warn">Truncated</span>');
  }
  target.innerHTML = `<div class="eval-score-header"><div class="score-ring ${ringClass}">${overall.toFixed(1)}</div><div><div>${escapeHtml(evaluation.summary || "See dimension notes.")}</div><div class="eval-meta-badges">${badges.join("")}</div></div></div>`;
  const labels = state.bootstrap.dimLabels;
  const bars = Object.keys(labels).map((key) => {
    const score = evaluation.dimensions?.[key]?.score || 0;
    const note = evaluation.dimensions?.[key]?.note || "";
    const fillClass = score >= 7 ? "high" : score >= 5 ? "mid" : "low";
    return `<div class="eval-bar"><div class="eval-bar-label">${escapeHtml(labels[key])}</div><div class="eval-bar-track"><div class="eval-bar-fill ${fillClass}" style="width:${score * 10}%"></div></div><div class="eval-bar-score">${score}</div><div class="eval-bar-note">${escapeHtml(note)}</div></div>`;
  }).join("");
  barsHost.innerHTML = bars;
  const usage = evaluation.usage
    ? `<div class="eval-tokens">Eval tokens: In ${evaluation.usage.input_tokens ?? "—"} · Out ${evaluation.usage.output_tokens ?? "—"} · Total ${evaluation.usage.total_tokens ?? "—"}</div>`
    : "";
  details.innerHTML = `
    <div class="eval-highlights">
      <div class="eval-highlight-card"><strong>Strengths</strong><br>${escapeHtml((evaluation.strengths || []).join("; ") || "—")}</div>
      <div class="eval-highlight-card"><strong>Weaknesses</strong><br>${escapeHtml((evaluation.weaknesses || []).join("; ") || "—")}</div>
    </div>
    ${usage}
  `;
}

function renderComparison(run) {
  const tableHost = byId("comparisonTable");
  const emptyHost = byId("comparisonEmpty");
  const contentHost = byId("comparisonContent");
  const entries = run.order
    .map((name) => [name, run.results[name].evaluation])
    .filter((entry) => entry[1] && !entry[1].error);
  if (!entries.length) {
    emptyHost.classList.remove("hidden");
    contentHost.classList.add("hidden");
    tableHost.innerHTML = "";
    return;
  }
  emptyHost.classList.add("hidden");
  contentHost.classList.remove("hidden");
  const labels = state.bootstrap.dimLabels;
  const headers = entries.map(([name]) => `<th>${escapeHtml(name)}</th>`).join("");
  const rows = Object.entries(labels)
    .map(([key, label]) => {
      const scores = entries.map(([, evaluation]) => evaluation.dimensions[key]?.score || 0);
      const best = Math.max(...scores);
      return `<tr><td>${escapeHtml(label)}</td>${scores
        .map((score) => `<td class="${score === best && best > 0 ? "best" : ""}">${score}</td>`)
        .join("")}</tr>`;
    })
    .join("");
  const overall = entries.map(([, evaluation]) => Number(evaluation.overall_score || 0));
  const bestOverall = Math.max(...overall);
  const overallRow = `<tr><td>Overall</td>${overall
    .map((score) => `<td class="${score === bestOverall && bestOverall > 0 ? "best" : ""}">${score.toFixed(1)}</td>`)
    .join("")}</tr>`;
  const metricRows = [
    ["Time", entries.map(([name]) => run.results[name].metrics?.elapsedS != null ? `${Number(run.results[name].metrics.elapsedS).toFixed(2)}s` : "—")],
    ["Input", entries.map(([name]) => run.results[name].metrics?.inputTokens ?? "—")],
    ["Output", entries.map(([name]) => run.results[name].metrics?.outputTokens ?? "—")],
    ["Total", entries.map(([name]) => run.results[name].metrics?.totalTokens ?? "—")],
  ].map(([label, values]) => `<tr><td>${escapeHtml(label)}</td>${values.map((value) => `<td>${value}</td>`).join("")}</tr>`).join("");
  tableHost.innerHTML = `<table><thead><tr><th>Dimension</th>${headers}</tr></thead><tbody>${rows}${overallRow}${metricRows}</tbody></table>`;
  renderRadar(entries);
}

function renderLog(entries) {
  byId("logView").textContent = entries.map((item) => `${item.level} | ${item.model} | ${item.message}`).join("\n");
  byId("logBadge").textContent = String(entries.filter((item) => item.level === "ERROR").length);
}

async function retryGeneration(modelName) {
  if (!state.runId) {
    return;
  }
  showRequestOverlay("Retrying generation...", `Submitting a fresh generation request for ${modelName}.`);
  byId("exportReportBtn").disabled = true;
  try {
    await api(`/api/runs/${state.runId}/retry`, {
      method: "POST",
      body: JSON.stringify({ config: collectConfig(), modelName }),
    });
    setStatus(`Retrying ${modelName}...`);
    byId("reEvalBtn").disabled = true;
    startPolling();
  } catch (error) {
    setStatus(error.message);
    alert(error.message);
  } finally {
    hideRequestOverlay();
  }
}

async function exportReport() {
  if (!state.runId) {
    return;
  }
  showRequestOverlay("Building PPTX report...", "Collecting the generated images, scores, and metrics into a presentation.");
  byId("exportReportBtn").disabled = true;
  try {
    const payload = await api(`/api/runs/${state.runId}/report`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    const anchor = document.createElement("a");
    anchor.href = payload.downloadUrl;
    anchor.download = payload.fileName || "image-generation-model-comparison-portal-report.pptx";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setStatus("PPTX report ready.");
  } catch (error) {
    setStatus(error.message);
    alert(error.message);
  } finally {
    hideRequestOverlay();
    if (state.run) {
      byId("exportReportBtn").disabled = !canExportReport(state.run) || state.run.status === "running";
    }
  }
}

async function triggerEvaluation(modelName = null) {
  if (!state.runId) {
    return;
  }
  await api(`/api/runs/${state.runId}/evaluate`, {
    method: "POST",
    body: JSON.stringify({ config: collectConfig(), modelName }),
  });
  startPolling();
}

function downloadResult(modelName) {
  const result = state.run?.results?.[modelName];
  if (!result?.generation?.imageDataUrl) {
    return;
  }
  const link = document.createElement("a");
  link.href = result.generation.imageDataUrl;
  link.download = `${modelName}.${result.generation.mimeType === "image/jpeg" ? "jpg" : "png"}`;
  link.click();
}

function pretty(value) {
  return value ? JSON.stringify(value, null, 2) : "";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function cssEscape(value) {
  return String(value).replaceAll('"', '\\"');
}

function updateBboxButton(node) {
  const button = node.querySelector(".bbox-btn");
  button.textContent = node.dataset.bboxVisible === "false" ? "Show BBOX" : "Hide BBOX";
}

function renderRadar(entries) {
  const canvas = byId("radarCanvas");
  const legend = byId("radarLegend");
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(cx, cy) - 58;
  const labels = ["Prompt", "Text", "Count", "Spatial", "Anatomy", "Physics", "Color", "Detail", "Comp.", "Style"];
  const dimKeys = Object.keys(state.bootstrap.dimLabels);
  ctx.clearRect(0, 0, width, height);

  for (let level = 1; level <= 5; level += 1) {
    const r = radius * (level / 5);
    ctx.beginPath();
    for (let i = 0; i <= dimKeys.length; i += 1) {
      const angle = (-Math.PI / 2) + (i * 2 * Math.PI / dimKeys.length);
      const x = cx + r * Math.cos(angle);
      const y = cy + r * Math.sin(angle);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = level === 5 ? "#34516b" : "#1a3045";
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  dimKeys.forEach((_, index) => {
    const angle = (-Math.PI / 2) + (index * 2 * Math.PI / dimKeys.length);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + radius * Math.cos(angle), cy + radius * Math.sin(angle));
    ctx.strokeStyle = "#1d3e59";
    ctx.stroke();
    const lx = cx + (radius + 24) * Math.cos(angle);
    const ly = cy + (radius + 24) * Math.sin(angle);
    ctx.fillStyle = "#89a9c7";
    ctx.font = "bold 11px Segoe UI";
    ctx.textAlign = Math.abs(Math.cos(angle)) < 0.12 ? "center" : (Math.cos(angle) > 0 ? "left" : "right");
    ctx.textBaseline = Math.abs(Math.sin(angle)) < 0.12 ? "middle" : (Math.sin(angle) > 0 ? "top" : "bottom");
    ctx.fillText(labels[index], lx, ly);
  });

  entries.forEach(([name, evaluation], index) => {
    const color = state.radarColors[index % state.radarColors.length];
    ctx.beginPath();
    dimKeys.forEach((key, dimIndex) => {
      const score = Number(evaluation.dimensions?.[key]?.score || 0);
      const angle = (-Math.PI / 2) + (dimIndex * 2 * Math.PI / dimKeys.length);
      const r = radius * (score / 10);
      const x = cx + r * Math.cos(angle);
      const y = cy + r * Math.sin(angle);
      if (dimIndex === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fillStyle = `${color}0.13)`;
    ctx.strokeStyle = `${color}0.95)`;
    ctx.lineWidth = 2.5;
    ctx.fill();
    ctx.stroke();
    dimKeys.forEach((key, dimIndex) => {
      const score = Number(evaluation.dimensions?.[key]?.score || 0);
      const angle = (-Math.PI / 2) + (dimIndex * 2 * Math.PI / dimKeys.length);
      const r = radius * (score / 10);
      ctx.beginPath();
      ctx.arc(cx + r * Math.cos(angle), cy + r * Math.sin(angle), 3.5, 0, Math.PI * 2);
      ctx.fillStyle = `${color}1)`;
      ctx.fill();
    });
  });

  legend.innerHTML = entries.map(([name, evaluation], index) => `
    <div class="radar-item">
      <span class="radar-swatch" style="background:${state.radarColors[index % state.radarColors.length]}0.95)"></span>
      <span class="radar-name">${escapeHtml(name)}</span>
      <span class="radar-score">${Number(evaluation.overall_score || 0).toFixed(1)}</span>
    </div>
  `).join("");
}

function bindEvents() {
  byId("addModelBtn").addEventListener("click", () => {
    byId("modelsList").appendChild(buildModelRow());
  });
  byId("loadSampleBtn").addEventListener("click", () => renderModels(state.bootstrap.sampleModels));
  byId("saveConfigBtn").addEventListener("click", async () => {
    await api("/api/config", { method: "POST", body: JSON.stringify(collectConfig()) });
    setStatus("Config saved.");
  });
  byId("clearConfigBtn").addEventListener("click", () => loadConfig(state.bootstrap.config));
  byId("watchmakerBtn").addEventListener("click", () => renderPresetForMode("watchmaker", "text"));
  byId("neonBtn").addEventListener("click", () => renderPresetForMode("neon_ramen", "text"));
  byId("generateBenchmarkBtn").addEventListener("click", () => generateBenchmark("text"));
  byId("editWatchmakerBtn").addEventListener("click", () => renderPresetForMode("watchmaker", "edit"));
  byId("editNeonBtn").addEventListener("click", () => renderPresetForMode("neon_ramen", "edit"));
  byId("editGenerateBenchmarkBtn").addEventListener("click", () => generateBenchmark("edit"));
  byId("runTextBtn").addEventListener("click", () => startRun("text"));
  byId("runEditBtn").addEventListener("click", () => startRun("edit"));
  byId("exportReportBtn").addEventListener("click", () => exportReport());
  byId("reEvalBtn").addEventListener("click", () => triggerEvaluation(null));
  byId("copyLogBtn").addEventListener("click", () => navigator.clipboard.writeText(byId("logView").textContent));
  byId("clearLogBtn").addEventListener("click", () => {
    byId("logView").textContent = "";
    byId("logBadge").textContent = "0";
  });
  byId("editSourceFiles").addEventListener("change", async (event) => {
    await loadEditPreview(event.target.files);
  });
  byId("editBrushSize").addEventListener("input", (event) => {
    state.editMask.brushSize = Number(event.target.value || 40);
    byId("editBrushSizeValue").textContent = `${state.editMask.brushSize} px`;
  });
  byId("maskPaintBtn").addEventListener("click", () => setMaskMode("paint"));
  byId("maskEraseBtn").addEventListener("click", () => setMaskMode("erase"));
  byId("maskClearBtn").addEventListener("click", () => clearMaskBuffer());
  const maskCanvas = byId("editMaskCanvas");
  maskCanvas.addEventListener("pointerdown", beginMaskStroke);
  maskCanvas.addEventListener("pointermove", moveMaskStroke);
  maskCanvas.addEventListener("pointerup", endMaskStroke);
  maskCanvas.addEventListener("pointerleave", endMaskStroke);
  maskCanvas.addEventListener("pointercancel", endMaskStroke);
}

async function boot() {
  initStaticOptions();
  setupTabs();
  bindEvents();
  state.bootstrap = await api("/api/bootstrap");
  loadConfig(state.bootstrap.config);
  renderBenchAnnotation("Benchmark", {}, "text");
  renderBenchAnnotation("Benchmark", {}, "edit");
  setMaskMode("paint");
  updateMaskMeta();
  setStatus("Ready");
}

window.addEventListener("beforeunload", stopPolling);
window.addEventListener("resize", () => {
  if (state.run) {
    renderComparison(state.run);
    const grid = byId("resultsGrid");
    state.run.order.forEach((name) => updateResultCard(grid.querySelector(`[data-model="${cssEscape(name)}"]`), state.run.results[name]));
  }
  if (state.editMask.sourceDataUrl) {
    redrawMaskOverlay();
  }
});
window.addEventListener("load", boot);
