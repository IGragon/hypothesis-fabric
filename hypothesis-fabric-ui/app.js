const CANVAS = {
  width: 3200,
  height: 2200,
  nodeGap: 24,
  minScale: 0.32,
  maxScale: 1.65,
  scaleStep: 0.12,
  stageMargin: 22
};

const typeNames = {
  hypothesis: "гипотеза",
  source: "источник",
  experiment: "опыт",
  risk: "риск"
};

const STAGE_LABELS = {
  indexing: "Индексация файлов (OCR, эмбеддинги)",
  kpi_parse: "KPI-разбор",
  retrieve: "Поиск оснований",
  generate: "Генерация гипотез",
  cite_bind: "Привязка цитат",
  score: "Оценка и ранжирование",
  constraint_check: "Проверка ограничений",
  explain: "Обоснование",
  export: "Экспорт"
};
const STAGE_ORDER = [
  "indexing", "kpi_parse", "retrieve", "generate", "cite_bind",
  "score", "constraint_check", "explain", "export"
];
const PIPELINE_STAGES = STAGE_ORDER.filter((s) => s !== "indexing");

const API = "";
const FEATURE_KEYS = ["effect", "feasibility", "novelty", "risk", "realizability"];
const FEATURE_LABELS = {
  effect: "Эффект", feasibility: "Реализ.", novelty: "Новизна",
  risk: "Риск", realizability: "Осущ."
};
const DEFAULT_WEIGHTS = {
  effect: 25, feasibility: 30, novelty: 25, risk: 10, realizability: 10
};

const state = {
  selected: null,
  filter: "all",
  search: "",
  decision: "на ревью",
  traceMode: false,
  runId: null,
  sessionId: null,
  running: false,
  layout: { left: 420, right: 360 },
  view: { scale: 1, focus: false },
  weights: { ...DEFAULT_WEIGHTS },
  external: { web: true, mp: false, citrination: false, nims: false },
  uploadedFiles: [],
  hypotheses: [],
  nodes: [],
  edges: [],
  pinned: new Set(),
  pollTimer: null
};

const els = {
  appShell: document.querySelector(".app-shell"),
  goalInput: document.getElementById("goalInput"),
  constraintsInput: document.getElementById("constraintsInput"),
  sourceStack: document.getElementById("sourceStack"),
  sourceCount: document.getElementById("sourceCount"),
  fileInput: document.getElementById("fileInput"),
  dropZone: document.getElementById("dropZone"),
  examplesList: document.getElementById("examplesList"),
  heroMetrics: document.getElementById("heroMetrics"),
  nodesLayer: document.getElementById("nodesLayer"),
  edgeLayer: document.getElementById("edgeLayer"),
  canvasStage: document.getElementById("canvasStage"),
  canvasSpace: document.getElementById("canvasSpace"),
  canvasGrid: document.getElementById("canvasGrid"),
  canvasEmpty: document.getElementById("canvasEmpty"),
  zoomValue: document.getElementById("zoomValue"),
  rankList: document.getElementById("rankList"),
  rankCount: document.getElementById("rankCount"),
  rightPanel: document.getElementById("rightPanel"),
  selectedKind: document.getElementById("selectedKind"),
  selectedTitle: document.getElementById("selectedTitle"),
  selectedSummary: document.getElementById("selectedSummary"),
  selectedScore: document.getElementById("selectedScore"),
  selectedConfidence: document.getElementById("selectedConfidence"),
  metricBars: document.getElementById("metricBars"),
  mechanismText: document.getElementById("mechanismText"),
  justificationText: document.getElementById("justificationText"),
  expectedEffectText: document.getElementById("expectedEffectText"),
  whyItMattersText: document.getElementById("whyItMattersText"),
  bestPracticesText: document.getElementById("bestPracticesText"),
  actionableNowText: document.getElementById("actionableNowText"),
  noveltyText: document.getElementById("noveltyText"),
  risksText: document.getElementById("risksText"),
  uncertaintyText: document.getElementById("uncertaintyText"),
  effectCauseList: document.getElementById("effectCauseList"),
  evidenceList: document.getElementById("evidenceList"),
  roadmapList: document.getElementById("roadmapList"),
  constraintWarnings: document.getElementById("constraintWarnings"),
  decisionState: document.getElementById("decisionState"),
  searchInput: document.getElementById("searchInput"),
  runState: document.getElementById("runState"),
  runChip: document.getElementById("runChip"),
  filterTabs: document.getElementById("filterTabs"),
  generateBtn: document.getElementById("generateBtn"),
  exportBtn: document.getElementById("exportBtn"),
  exportPopover: document.getElementById("exportPopover"),
  progressModal: document.getElementById("progressModal"),
  progressPercent: document.getElementById("progressPercent"),
  progressFill: document.getElementById("progressFill"),
  progressElapsed: document.getElementById("progressElapsed"),
  stageList: document.getElementById("stageList"),
  exampleModal: document.getElementById("exampleModal"),
  exampleBody: document.getElementById("exampleBody"),
  exampleModalTitle: document.getElementById("exampleModalTitle")
};

const weightInputs = {
  effect: document.getElementById("weight_effect"),
  feasibility: document.getElementById("weight_feasibility"),
  novelty: document.getElementById("weight_novelty"),
  risk: document.getElementById("weight_risk"),
  realizability: document.getElementById("weight_realizability")
};

const externalInputs = {
  web: document.getElementById("src_web"),
  mp: document.getElementById("src_mp"),
  citrination: document.getElementById("src_citrination"),
  nims: document.getElementById("src_nims")
};

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(API + path, opts);
  const txt = await r.text();
  let data = null;
  try { data = txt ? JSON.parse(txt) : null; } catch (e) { data = txt; }
  if (!r.ok) throw new Error(`${r.status} ${typeof data === "string" ? data : JSON.stringify(data)}`);
  return data;
}

async function apiUpload(path, files) {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  const r = await fetch(API + path, { method: "POST", body: fd });
  if (!r.ok) throw new Error(`upload ${r.status}`);
  return r.json();
}

async function apiDownload(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`download ${r.status}`);
  return r.blob();
}

function allNodes() {
  return [...state.nodes, ...state.hypotheses];
}

function score(item) {
  if (item.type !== "hypothesis") return Math.round(item.confidence || 0);
  const feats = item.features || {};
  const total = Object.values(state.weights).reduce((s, v) => s + v, 0) || 1;
  let val = 0;
  for (const k of FEATURE_KEYS) {
    const f = feats[k];
    if (f === undefined) continue;
    const w = state.weights[k] || 0;
    val += f * w;
  }
  return Math.min(100, Math.max(0, Math.round((val / total) * 100)));
}

function selectedItem() {
  if (!state.selected) return state.hypotheses[0] || null;
  return allNodes().find((n) => n.id === state.selected) || state.hypotheses[0] || null;
}

function typeLabel(type) {
  return typeNames[type] || type;
}

function fileType(type) {
  return `<span class="file-type ${type}">${type.toUpperCase()}</span>`;
}

function fileIcon(name) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  if (ext.includes("xls")) return "xls";
  if (ext.includes("doc")) return "doc";
  if (ext.includes("pdf")) return "pdf";
  if (["png", "jpg", "jpeg", "bmp", "tiff", "webp"].includes(ext)) return "png";
  return "file";
}

function renderSources() {
  els.sourceCount.textContent = `${state.uploadedFiles.length} файл(ов)`;
  if (!state.uploadedFiles.length) {
    els.sourceStack.innerHTML = `<em style="color:#8a93a6;font-size:12px">файлы не добавлены</em>`;
    return;
  }
  els.sourceStack.innerHTML = state.uploadedFiles.map((f) => `
    <div class="source-row">
      ${fileType(fileIcon(f.name))}
      <div>
        <strong>${f.name}</strong>
        <span>${(f.size / 1024).toFixed(0)} КБ</span>
      </div>
      <span class="chip">${fileIcon(f.name)}</span>
    </div>
  `).join("");
}

function renderMetrics() {
  const best = rankedHypotheses()[0];
  const total = state.hypotheses.length;
  const metrics = [
    ["Сгенерировано", `${total}`, "гипотез в выдаче"],
    ["Лучшая оценка", best ? `${score(best)} / 100` : "—", best ? best.title.slice(0, 48) : "запустите анализ"],
    ["Запуск", state.runId || "—", state.running ? "в процессе" : "ожидание"],
    ["Этапов", state.running ? "обработка…" : "готово", "8 этапов пайплайна"]
  ];
  els.heroMetrics.innerHTML = metrics.map(([label, value, note]) => `
    <article class="metric-card">
      <span>${label}</span>
      <strong>${value}</strong>
      <em>${note}</em>
    </article>
  `).join("");
}

function addFiles(files) {
  for (const f of files) state.uploadedFiles.push(f);
  renderSources();
}

function renderExamplesList(examples) {
  if (!examples.length) {
    els.examplesList.innerHTML = `<em style="color:#8a93a6;font-size:12px">примеры не найдены</em>`;
    return;
  }
  els.examplesList.innerHTML = examples.map((ex, i) => `
    <button class="example-btn" type="button" data-idx="${i}">
      <strong>${ex.name}</strong>
      <em>${ex.output_file ? ex.output_file : "текстовое описание"}</em>
    </button>
  `).join("");
  els.examplesList.querySelectorAll(".example-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ex = examples[Number(btn.dataset.idx)];
      openExample(ex);
    });
  });
}

function openExample(ex) {
  els.exampleModalTitle.textContent = ex.name || "Пример готового вывода";
  els.exampleBody.textContent = ex.output_text || "(текст примера недоступен)";
  els.exampleModal.classList.remove("hidden");
}

async function loadExamples() {
  try {
    const data = await api("GET", "/examples");
    renderExamplesList(data.examples || []);
  } catch (e) {
    els.examplesList.innerHTML = `<em style="color:#d9534f;font-size:12px">ошибка загрузки: ${e.message}</em>`;
  }
}

function matchesFilter(item) {
  const filterOk = state.filter === "all" || item.type === state.filter;
  const text = `${item.title} ${item.summary} ${(item.tags || []).join(" ")}`.toLowerCase();
  const searchOk = !state.search || text.includes(state.search.toLowerCase());
  return filterOk && searchOk;
}

function autoLayout() {
  const cols = 4;
  const colW = 320;
  const rowH = 180;
  const margin = 60;
  state.hypotheses.forEach((h, i) => {
    if (h.userPlaced) return;
    h.x = margin + (i % cols) * colW;
    h.y = margin + Math.floor(i / cols) * rowH + 320;
  });
  state.nodes.forEach((n, i) => {
    if (n.userPlaced) return;
    n.x = margin + (i % cols) * colW;
    n.y = margin + Math.floor(i / cols) * rowH;
  });
}

function renderNodes() {
  els.nodesLayer.innerHTML = allNodes().map((item) => {
    const isHidden = !matchesFilter(item);
    const itemScore = score(item);
    const selected = item.id === state.selected ? "selected" : "";
    const hidden = isHidden ? "hidden" : "";
    const scoreLabel = item.type === "hypothesis" ? itemScore : typeLabel(item.type);
    const scoreClass = item.type === "hypothesis" ? "metric-score" : "type-score";
    const tip = item.type === "hypothesis"
      ? "Кликните, чтобы открыть гипотезу справа. Карточку можно перетаскивать."
      : "Кликните, чтобы открыть узел справа. Карточку можно перетаскивать.";
    return `
      <article class="node-card ${selected} ${hidden}" data-id="${item.id}" data-tip="${tip}" style="left:${item.x}px; top:${item.y}px;">
        <button class="node-delete" data-id="${item.id}" data-tip="Удалить карточку с холста" type="button">×</button>
        <div class="node-head">
          <h3>${item.title}</h3>
          <div class="node-score ${scoreClass}">${scoreLabel}</div>
        </div>
        <p>${item.summary || ""}</p>
        <div class="node-tags">
          ${(item.tags || []).slice(0, 4).map((t) => `<span class="mini-tag">${t}</span>`).join("")}
        </div>
      </article>
    `;
  }).join("");

  els.nodesLayer.querySelectorAll(".node-card").forEach((card) => {
    card.addEventListener("pointerdown", startDrag);
    card.addEventListener("click", (event) => {
      if (event.detail !== 0 && card.dataset.dragged === "true") {
        card.dataset.dragged = "false";
        return;
      }
      selectNode(card.dataset.id);
    });
  });

  els.nodesLayer.querySelectorAll(".node-delete").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteNode(btn.dataset.id);
    });
  });
  els.canvasEmpty.style.display = allNodes().length ? "none" : "block";
  renderEdges();
}

function nodeSize(item) {
  const card = els.nodesLayer.querySelector(`[data-id="${item.id}"]`);
  return { width: card?.offsetWidth || 258, height: card?.offsetHeight || 148 };
}

function cardRect(item, padding = 0) {
  const { width, height } = nodeSize(item);
  return {
    left: item.x - padding, top: item.y - padding,
    right: item.x + width + padding, bottom: item.y + height + padding,
    cx: item.x + width / 2, cy: item.y + height / 2, width, height
  };
}

function perimeterAnchor(rect, targetRect) {
  const dx = targetRect.cx - rect.cx;
  const dy = targetRect.cy - rect.cy;
  const halfWidth = Math.max(1, rect.width / 2);
  const halfHeight = Math.max(1, rect.height / 2);
  if (Math.abs(dx) < 0.01 && Math.abs(dy) < 0.01) return { x: rect.right, y: rect.cy, side: "right" };
  const scaleX = halfWidth / Math.abs(dx || 0.01);
  const scaleY = halfHeight / Math.abs(dy || 0.01);
  if (scaleX <= scaleY) {
    return { x: dx >= 0 ? rect.right : rect.left, y: rect.cy + dy * scaleX, side: dx >= 0 ? "right" : "left" };
  }
  return { x: rect.cx + dx * scaleY, y: dy >= 0 ? rect.bottom : rect.top, side: dy >= 0 ? "bottom" : "top" };
}

function sideAnchors(fromRect, toRect) {
  return [perimeterAnchor(fromRect, toRect), perimeterAnchor(toRect, fromRect)];
}

function edgePath(start, end) {
  const horizontal = start.side === "left" || start.side === "right";
  const forwardGap = horizontal
    ? start.side === "right" ? end.x - start.x : start.x - end.x
    : start.side === "bottom" ? end.y - start.y : start.y - end.y;
  const distance = forwardGap > 0 ? Math.max(18, Math.min(160, forwardGap * 0.5)) : 0;
  const vectors = { right: [distance, 0], left: [-distance, 0], bottom: [0, distance], top: [0, -distance] };
  const [c1x, c1y] = vectors[start.side];
  const [c2x, c2y] = vectors[end.side];
  return `M ${start.x} ${start.y} C ${start.x + c1x} ${start.y + c1y}, ${end.x + c2x} ${end.y + c2y}, ${end.x} ${end.y}`;
}

function clampNode(item) {
  const { width, height } = nodeSize(item);
  item.x = Math.max(0, Math.min(CANVAS.width - width, item.x));
  item.y = Math.max(0, Math.min(CANVAS.height - height, item.y));
}

function applyNodePositions() {
  allNodes().forEach((item) => {
    const card = els.nodesLayer.querySelector(`[data-id="${item.id}"]`);
    if (!card) return;
    card.style.left = `${item.x}px`;
    card.style.top = `${item.y}px`;
  });
}

function rectsOverlap(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

function separatePair(a, b, activeItem) {
  const rectA = cardRect(a, CANVAS.nodeGap / 2);
  const rectB = cardRect(b, CANVAS.nodeGap / 2);
  if (!rectsOverlap(rectA, rectB)) return false;
  const overlapX = Math.min(rectA.right - rectB.left, rectB.right - rectA.left);
  const overlapY = Math.min(rectA.bottom - rectB.top, rectB.bottom - rectA.top);
  const signX = rectA.cx <= rectB.cx ? 1 : -1;
  const signY = rectA.cy <= rectB.cy ? 1 : -1;
  const amount = (Math.min(overlapX, overlapY) || CANVAS.nodeGap) + 6;
  const moveA = activeItem !== a;
  const moveB = activeItem !== b;
  if (!moveA && !moveB) return false;
  if (overlapX <= overlapY) {
    if (moveA && moveB) { a.x -= signX * amount / 2; b.x += signX * amount / 2; }
    else if (moveA) a.x -= signX * amount; else b.x += signX * amount;
  } else if (moveA && moveB) {
    a.y -= signY * amount / 2; b.y += signY * amount / 2;
  } else if (moveA) a.y -= signY * amount; else b.y += signY * amount;
  clampNode(a); clampNode(b);
  return true;
}

function resolveCollisions(activeItem = null) {
  const nodes = allNodes();
  for (let pass = 0; pass < 28; pass += 1) {
    let changed = false;
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        changed = separatePair(nodes[i], nodes[j], activeItem) || changed;
      }
    }
    if (!changed) break;
  }
  applyNodePositions();
  renderEdges();
}

function renderEdges() {
  const nodeMap = Object.fromEntries(allNodes().map((n) => [n.id, n]));
  const paths = state.edges.map((e) => {
    const a = nodeMap[e.source];
    const b = nodeMap[e.target];
    if (!a || !b || !matchesFilter(a) || !matchesFilter(b)) return "";
    const [start, end] = sideAnchors(cardRect(a), cardRect(b));
    const trace = state.traceMode && (e.source === state.selected || e.target === state.selected);
    return `<path class="${trace ? "trace" : ""}" d="${edgePath(start, end)}"></path>`;
  }).join("");
  els.edgeLayer.innerHTML = paths;
}

function renderInspector() {
  const item = selectedItem();
  if (!item) {
    els.selectedKind.textContent = "—";
    els.selectedTitle.textContent = "Выберите гипотезу";
    els.selectedSummary.textContent = "";
    els.selectedScore.textContent = "—";
    els.selectedConfidence.textContent = "";
    els.metricBars.innerHTML = "";
    els.mechanismText.textContent = "";
    els.justificationText.textContent = "";
    els.expectedEffectText.textContent = "";
    els.whyItMattersText.textContent = "";
    els.bestPracticesText.textContent = "";
    els.actionableNowText.textContent = "";
    els.noveltyText.textContent = "";
    els.risksText.textContent = "";
    els.uncertaintyText.textContent = "";
    els.effectCauseList.innerHTML = "";
    els.evidenceList.innerHTML = "";
    els.roadmapList.innerHTML = "";
    els.constraintWarnings.innerHTML = "";
    els.constraintWarnings.classList.remove("has-warnings");
    els.decisionState.textContent = "на ревью";
    return;
  }
  const itemScore = score(item);
  els.selectedKind.textContent = typeLabel(item.type);
  els.selectedTitle.textContent = item.title || "";
  els.selectedSummary.textContent = item.summary || "";
  els.selectedScore.textContent = item.type === "hypothesis" ? itemScore : (item.confidence || 0);
  els.selectedConfidence.textContent = item.confidence != null ? `${Math.round(item.confidence)}% доверие` : "";
  els.mechanismText.textContent = item.mechanism || "";
  els.justificationText.textContent = item.justification || "";
  els.expectedEffectText.textContent = item.expectedEffect || "";
  els.whyItMattersText.textContent = item.whyItMatters || "";
  els.bestPracticesText.textContent = item.bestPractices || "";
  els.actionableNowText.textContent = item.actionableNow || "";
  els.noveltyText.textContent = item.novelty || "";
  els.risksText.textContent = item.risks || "";
  els.uncertaintyText.textContent = item.uncertainty || "";

  els.effectCauseList.innerHTML = (item.effectCauseExamples || []).map((ex) => `<li>${ex}</li>`).join("");

  const feats = item.features || (item.type === "hypothesis" ? {} : null);
  if (feats) {
    els.metricBars.innerHTML = FEATURE_KEYS.map((k) => {
      const v = feats[k] != null ? Math.round(feats[k] * 100) : 0;
      return `<div class="bar-row"><span>${FEATURE_LABELS[k]}</span><div class="bar-track"><div class="bar-fill" style="width:${v}%"></div></div><b>${v}</b></div>`;
    }).join("");
  } else {
    els.metricBars.innerHTML = "";
  }

  els.evidenceList.innerHTML = (item.evidence || []).map((ev) => `
    <div class="evidence-row" data-tip="${ev[2] || ""}">
      ${fileType(ev[0])}
      <div><strong>${ev[1]}</strong><span>${ev[2] || ""}</span></div>
      <span class="chip">${ev[0]}</span>
    </div>
  `).join("");

  els.roadmapList.innerHTML = (item.roadmap || []).map((step, i) => `
    <div class="road-step"><span class="road-num">${i + 1}</span><span>${step}</span></div>
  `).join("");

  const cv = item.constraintViolations || [];
  const blockEl = document.getElementById("constraintWarningsBlock");
  if (cv.length) {
    blockEl.classList.add("has-warnings");
    els.constraintWarnings.innerHTML = cv.map((v) => `<li>${v}</li>`).join("");
  } else {
    blockEl.classList.remove("has-warnings");
    els.constraintWarnings.innerHTML = "";
  }

  els.decisionState.textContent = state.decision;
}

function rankedHypotheses() {
  return [...state.hypotheses].sort((a, b) => score(b) - score(a));
}

function renderRankList() {
  const ranked = rankedHypotheses();
  els.rankCount.textContent = `${ranked.length} гипотез`;
  els.rankList.innerHTML = ranked.slice(0, 8).map((item, i) => `
    <article class="rank-item ${item.id === state.selected ? "active" : ""}" data-id="${item.id}">
      <div class="rank-index">${i + 1}</div>
      <div>
        <strong>${item.title}</strong>
        <span>оценка ${score(item)} · ${(item.tags || []).slice(0, 2).join(" · ") || "—"}</span>
      </div>
      <span class="chip cyan">${item.confidence != null ? Math.round(item.confidence) : score(item)}%</span>
    </article>
  `).join("");
  els.rankList.querySelectorAll(".rank-item").forEach((el) => {
    el.addEventListener("click", () => selectNode(el.dataset.id));
  });
}

function renderWeights() {
  Object.entries(weightInputs).forEach(([key, input]) => {
    input.value = state.weights[key];
    document.getElementById(`${key}Value`).textContent = state.weights[key];
  });
  Object.entries(externalInputs).forEach(([key, input]) => {
    input.checked = !!state.external[key];
  });
}

function renderCanvasView() {
  const scale = state.view.scale;
  document.documentElement.style.setProperty("--canvas-width", `${CANVAS.width}px`);
  document.documentElement.style.setProperty("--canvas-height", `${CANVAS.height}px`);
  document.documentElement.style.setProperty("--canvas-scale", `${scale}`);
  els.canvasSpace.style.width = `${CANVAS.width * scale}px`;
  els.canvasSpace.style.height = `${CANVAS.height * scale}px`;
  els.edgeLayer.setAttribute("width", `${CANVAS.width}`);
  els.edgeLayer.setAttribute("height", `${CANVAS.height}`);
  els.edgeLayer.setAttribute("viewBox", `0 0 ${CANVAS.width} ${CANVAS.height}`);
  els.zoomValue.textContent = `${Math.round(scale * 100)}%`;
}

function setCanvasScale(nextScale, anchorEvent = null) {
  const next = Math.max(CANVAS.minScale, Math.min(CANVAS.maxScale, nextScale));
  const previous = state.view.scale;
  if (Math.abs(next - previous) < 0.001) return;
  const stage = els.canvasStage;
  const rect = stage.getBoundingClientRect();
  const anchorX = anchorEvent ? anchorEvent.clientX - rect.left : stage.clientWidth / 2;
  const anchorY = anchorEvent ? anchorEvent.clientY - rect.top : stage.clientHeight / 2;
  const logicalX = (stage.scrollLeft + anchorX) / previous;
  const logicalY = (stage.scrollTop + anchorY) / previous;
  state.view.scale = next;
  renderCanvasView();
  stage.scrollTo({ left: logicalX * next - anchorX, top: logicalY * next - anchorY, behavior: "auto" });
}

function fitCanvasView(smooth = true) {
  const visible = allNodes().filter(matchesFilter);
  if (!visible.length) {
    state.view.scale = 1;
    renderCanvasView();
    return;
  }
  const rects = visible.map(cardRect);
  const bounds = rects.reduce((acc, r) => ({
    left: Math.min(acc.left, r.left), top: Math.min(acc.top, r.top),
    right: Math.max(acc.right, r.right), bottom: Math.max(acc.bottom, r.bottom)
  }), { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity });
  const width = Math.max(1, bounds.right - bounds.left);
  const height = Math.max(1, bounds.bottom - bounds.top);
  const pad = 96;
  const targetScale = Math.max(CANVAS.minScale, Math.min(CANVAS.maxScale, Math.min(
    (els.canvasStage.clientWidth - pad) / width, (els.canvasStage.clientHeight - pad) / height)));
  state.view.scale = Number.isFinite(targetScale) ? targetScale : 1;
  renderCanvasView();
  const centerX = (bounds.left + width / 2) * state.view.scale;
  const centerY = (bounds.top + height / 2) * state.view.scale;
  els.canvasStage.scrollTo({
    left: Math.max(0, centerX - els.canvasStage.clientWidth / 2 + CANVAS.stageMargin),
    top: Math.max(0, centerY - els.canvasStage.clientHeight / 2 + CANVAS.stageMargin),
    behavior: smooth ? "smooth" : "auto"
  });
}

function toggleFocusMode() {
  state.view.focus = !state.view.focus;
  els.appShell.classList.toggle("canvas-focus", state.view.focus);
  const button = document.getElementById("focusBtn");
  button.textContent = state.view.focus ? "Панели" : "Фокус";
  setTimeout(() => fitCanvasView(true), 220);
}

function renderLayout() {
  document.documentElement.style.setProperty("--left-col", `${state.layout.left}px`);
  document.documentElement.style.setProperty("--right-col", `${state.layout.right}px`);
}

function renderAll() {
  renderLayout();
  renderCanvasView();
  renderSources();
  renderMetrics();
  renderNodes();
  renderInspector();
  renderRankList();
  renderWeights();
}

function deleteNode(id) {
  state.hypotheses = state.hypotheses.filter((h) => h.id !== id);
  state.sources = state.sources.filter((s) => s.id !== id);
  if (state.selected === id) state.selected = null;
  renderNodes();
  renderRankList();
  renderInspector();
}

function clearCanvas() {
  state.hypotheses = [];
  state.sources = [];
  state.edges = [];
  state.selected = null;
  state.pinned.clear();
  renderNodes();
  renderRankList();
  renderInspector();
}

function selectNode(id) {
  state.selected = id;
  const item = selectedItem();
  if (item && item.type === "hypothesis") {
    state.decision = state.pinned.has(id) ? "в плане" : "на ревью";
  }
  renderNodes();
  renderInspector();
  renderRankList();
}

function startDrag(event) {
  const card = event.currentTarget;
  const id = card.dataset.id;
  const item = allNodes().find((n) => n.id === id);
  if (!item) return;
  card.setPointerCapture(event.pointerId);
  card.classList.add("dragging");
  const startX = event.clientX;
  const startY = event.clientY;
  const originX = item.x;
  const originY = item.y;
  let moved = false;
  function move(ev) {
    const dx = (ev.clientX - startX) / state.view.scale;
    const dy = (ev.clientY - startY) / state.view.scale;
    if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
    item.x = originX + dx;
    item.y = originY + dy;
    clampNode(item);
    resolveCollisions(item);
  }
  function up() {
    card.classList.remove("dragging");
    card.dataset.dragged = moved ? "true" : "false";
    if (moved) item.userPlaced = true;
    card.removeEventListener("pointermove", move);
    card.removeEventListener("pointerup", up);
    card.removeEventListener("pointercancel", up);
  }
  card.addEventListener("pointermove", move);
  card.addEventListener("pointerup", up);
  card.addEventListener("pointercancel", up);
}

function setRunState(label, kind = "ready") {
  els.runState.innerHTML = `<span class="pulse"></span><span>${label}</span>`;
  if (kind === "running") {
    els.runChip.classList.remove("green");
    els.runChip.classList.add("cyan");
    els.runChip.textContent = "обработка";
  } else if (kind === "error") {
    els.runChip.classList.remove("green", "cyan");
    els.runChip.classList.add("amber");
    els.runChip.textContent = "ошибка";
  } else {
    els.runChip.classList.remove("cyan", "amber");
    els.runChip.classList.add("green");
    els.runChip.textContent = "онлайн";
  }
}

function showToast(title, message) {
  const stack = document.getElementById("toastStack");
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = `<strong>${title}</strong><span>${message}</span>`;
  stack.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(8px)";
    setTimeout(() => toast.remove(), 220);
  }, 3800);
}

function configPayload() {
  return {
    weight_novelty: state.weights.novelty / 100,
    weight_feasibility: state.weights.feasibility / 100,
    weight_effect: state.weights.effect / 100,
    weight_risk: state.weights.risk / 100,
    weight_realizability: state.weights.realizability / 100,
    external_search: buildExternalMode()
  };
}

function buildExternalMode() {
  const list = Object.entries(state.external).filter(([, v]) => v).map(([k]) => k);
  return list.length ? list.join(",") : "none";
}

async function runAnalysis() {
  const problem = els.goalInput.value.trim();
  const constraints = els.constraintsInput.value.trim();
  if (!problem) {
    showToast("Нет данных", "Опишите технологическую проблему");
    return;
  }

  if (state.running) {
    stopPolling();
    state.running = false;
  }

  state.running = true;
  els.generateBtn.disabled = true;
  els.generateBtn.textContent = "Идёт анализ…";
  setRunState("создание сессии", "running");

  try {
    const sess = await api("POST", "/sessions", { problem, constraints });
    state.sessionId = sess.session_id;

    if (state.uploadedFiles.length) {
      setRunState("загрузка файлов", "running");
      await apiUpload(`/sessions/${state.sessionId}/upload`, state.uploadedFiles);
    }

    setRunState("запуск пайплайна", "running");
    const runResp = await api("POST", `/sessions/${state.sessionId}/run`, {
      problem, constraints, config: configPayload()
    });
    state.runId = runResp.run_id;
    showProgress();
    startPolling();
  } catch (e) {
    state.running = false;
    els.generateBtn.disabled = false;
    els.generateBtn.textContent = "Запустить анализ";
    setRunState("ошибка", "error");
    showToast("Ошибка запуска", e.message);
  }
}

function showProgress() {
  els.stageList.innerHTML = STAGE_ORDER.map((s) => `
    <div class="stage-row pending" data-stage="${s}">
      <span class="ico">○</span>
      <span class="name">${STAGE_LABELS[s]}</span>
    </div>
  `).join("");
  // Mark indexing as running immediately — backend is doing OCR/embeddings
  const indexRow = els.stageList.querySelector('[data-stage="indexing"]');
  if (indexRow) {
    indexRow.className = "stage-row running";
    indexRow.querySelector(".ico").textContent = "•";
  }
  els.progressFill.style.width = "0%";
  els.progressPercent.textContent = "0%";
  els.progressElapsed.textContent = "0:00";
  els.progressModal.classList.remove("hidden");
}

const runStartTime = { value: 0 };
let elapsedTimer = null;

function startPolling() {
  runStartTime.value = Date.now();
  if (state.pollTimer) clearInterval(state.pollTimer);
  if (elapsedTimer) clearInterval(elapsedTimer);
  state.pollTimer = setInterval(pollOnce, 1500);
  elapsedTimer = setInterval(updateElapsed, 500);
  pollOnce();
  updateElapsed();
}

function updateElapsed() {
  if (!state.running) return;
  const sec = Math.floor((Date.now() - runStartTime.value) / 1000);
  const mm = Math.floor(sec / 60);
  const ss = sec % 60;
  els.progressElapsed.textContent = `${mm}:${String(ss).padStart(2, "0")}`;
}

async function pollOnce() {
  if (!state.sessionId || !state.runId) return;
  try {
    const data = await api("GET", `/sessions/${state.sessionId}/runs/${state.runId}/stages`);
    const backendStages = data.stages || [];

    // Synthesize the "indexing" stage:
    // - "running" while any pipeline stage is still "pending" and none is "done" yet
    // - "done" once at least one pipeline stage is "done" or "running"
    const pipeDone = backendStages.some((s) => s.status === "done");
    const pipeRunning = backendStages.some((s) => s.status === "running");
    const pipeError = backendStages.some((s) => s.status === "error");
    const indexingStatus = (pipeDone || pipeRunning || pipeError) ? "done" : "running";

    const allStages = [
      { stage: "indexing", status: indexingStatus },
      ...backendStages
    ];

    applyStageState(allStages);

    let doneCount = 0;
    let hasError = false;
    for (const s of allStages) {
      if (s.status === "done") doneCount += 1;
      if (s.status === "error") hasError = true;
    }
    const total = STAGE_ORDER.length;
    const pct = Math.round((doneCount / total) * 100);
    els.progressFill.style.width = `${pct}%`;
    els.progressPercent.textContent = `${pct}%`;
    if (hasError) {
      stopPolling();
      await finishRun(true);
    } else if (doneCount >= total) {
      stopPolling();
      await finishRun(false);
    }
  } catch (e) {
    // tolerate transient poll errors
  }
}

function stopPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
  if (elapsedTimer) clearInterval(elapsedTimer);
  elapsedTimer = null;
}

function applyStageState(stages) {
  const byStage = Object.fromEntries(stages.map((s) => [s.stage, s.status]));
  const errByStage = Object.fromEntries(stages.map((s) => [s.stage, s.error]));
  STAGE_ORDER.forEach((s) => {
    const row = els.stageList.querySelector(`[data-stage="${s}"]`);
    if (!row) return;
    const st = byStage[s] || "pending";
    row.className = `stage-row ${st}`;
    const ico = row.querySelector(".ico");
    ico.textContent = st === "done" ? "✓" : st === "error" ? "✕" : st === "running" ? "•" : "○";
    let errEl = row.querySelector(".err");
    if (st === "error" && errByStage[s]) {
      if (!errEl) {
        errEl = document.createElement("span");
        errEl.className = "err";
        row.appendChild(errEl);
      }
      errEl.textContent = String(errByStage[s]).slice(0, 80);
    } else if (errEl) {
      errEl.remove();
    }
  });
}

async function finishRun(hasError) {
  state.running = false;
  els.generateBtn.disabled = false;
  els.generateBtn.textContent = "Запустить анализ";
  if (hasError) {
    setRunState("ошибка", "error");
    showToast("Ошибка пайплайна", "См. детали в окне прогресса");
    setTimeout(() => els.progressModal.classList.add("hidden"), 2500);
    return;
  }
  setRunState("готово");
  setTimeout(() => els.progressModal.classList.add("hidden"), 1200);
  showToast("Анализ завершён", "Гипотезы сгенерированы и ранжированы");
  await loadResult();
}

async function loadResult() {
  try {
    const result = await api("GET", `/sessions/${state.sessionId}/runs/${state.runId}`);
    state.hypotheses = [];
    state.nodes = [];
    state.edges = [];
    (result.ranked || []).forEach((eh, i) => mapHypothesis(eh, i));
    autoLayout();
    // graph edges (cites/influences)
    await loadGraphEdges();
    state.selected = state.hypotheses[0]?.id || null;
    renderAll();
    resolveCollisions();
    setTimeout(() => fitCanvasView(true), 100);
  } catch (e) {
    showToast("Ошибка", `чтение результата: ${e.message}`);
  }
}

async function loadGraphEdges() {
  try {
    const g = await api("GET", `/sessions/${state.sessionId}/runs/${state.runId}/graph`);
    const want = new Set(allNodes().map((n) => n.id));
    // ensure graph nodes (sources/kg) exist on canvas
    (g.nodes || []).forEach((n) => {
      if (want.has(n.id)) return;
      let type = "source";
      if (n.label === "Hypothesis") type = "hypothesis";
      else if (n.label === "KG") type = "experiment";
      state.nodes.push({
        id: n.id, type,
        title: n.name || n.id,
        summary: n.label || "",
        confidence: Math.round((n.score || 0) * 100),
        tags: [],
        evidence: [],
        roadmap: [],
        x: 60, y: 60
      });
    });
    state.edges = (g.edges || []).filter((e) => {
      const ids = new Set(allNodes().map((n) => n.id));
      return ids.has(e.source) && ids.has(e.target);
    }).map((e) => ({ source: e.source, target: e.target }));
  } catch (e) {
    // graph optional
  }
}

function mapHypothesis(eh, idx) {
  const scored = eh.scored || {};
  const hyp = scored.hypothesis || {};
  const feats = scored.features || {};
  const scoreVal = scored.score || 0;
  const id = `hyp_${idx}`;
  const tags = deriveTags(hyp.claim);

  const evidence = Object.entries(scored.cited_refs || {}).map(([cid, chunk]) => {
    const meta = chunk.meta || {};
    const doc = meta.doc_id || chunk.doc_id || cid;
    const ext = meta.url ? "url" : fileIcon(String(doc));
    return [ext, String(doc), chunk.text || meta.url || ""];
  });
  const externalUrls = eh.external_urls || [];
  externalUrls.forEach((u, i) => evidence.push(["url", u, "внешний источник"]));

  const roadmapLines = splitLines(eh.verification_plan);
  const effectCause = eh.effect_cause_examples || [];

  state.hypotheses.push({
    id,
    type: "hypothesis",
    title: hyp.claim || `Гипотеза ${idx + 1}`,
    summary: hyp.expected_effect || "",
    mechanism: hyp.mechanism || "",
    justification: eh.justification || "",
    expectedEffect: hyp.expected_effect || "",
    whyItMatters: eh.why_it_matters || "",
    bestPractices: eh.best_practices || "",
    actionableNow: eh.actionable_now || "",
    novelty: eh.novelty || "",
    risks: eh.risks || "",
    uncertainty: eh.uncertainty || "",
    effectCauseExamples: effectCause,
    features: normFeats(feats),
    confidence: Math.round(scoreVal * 100),
    tags,
    evidence,
    roadmap: roadmapLines,
    constraintViolations: eh.constraint_violations || [],
    x: 60, y: 60
  });
  extractEmbeddedSections(state.hypotheses[state.hypotheses.length - 1]);
}

function normFeats(feats) {
  const out = {};
  for (const k of FEATURE_KEYS) {
    if (feats[k] != null) out[k] = Math.max(0, Math.min(1, feats[k]));
  }
  return out;
}

function deriveTags(claim) {
  if (!claim) return [];
  const words = claim.toLowerCase().split(/[^a-zа-яё0-9]+/i).filter((w) => w.length > 4);
  return words.slice(0, 3);
}

function splitLines(text) {
  if (!text) return [];
  return text.split(/\n+|(?:\d+\.\s)/).map((s) => s.trim()).filter(Boolean);
}

const SECTION_SPLIT_MAP = {
  justification: "justification",
  обоснование: "justification",
  uncertainty: "uncertainty",
  неопределённость: "uncertainty",
  "verification plan": "verification",
  verification_plan: "verification",
  "план проверки": "verification",
  "effect cause examples": "effectCause",
  effect_cause_examples: "effectCause",
  "эффект-причина": "effectCause",
  "general approach": "generalApproach",
  general_approach: "generalApproach",
  "общий подход": "generalApproach",
  "actionable now": "actionableNow",
  actionable_now: "actionableNow",
  "что делать сейчас": "actionableNow",
  "why it matters": "whyItMatters",
  why_it_matters: "whyItMatters",
  "почему это важно": "whyItMatters",
  "best practices": "bestPractices",
  best_practices: "bestPractices",
  "лучшие практики": "bestPractices",
  novelty: "novelty",
  новизна: "novelty",
  risks: "risks",
  риски: "risks",
};

function extractEmbeddedSections(hyp) {
  const just = hyp.justification || "";
  if (!just.includes("#") && !just.match(/^(justification|обоснование|uncertainty|risks|novelty)\b/im)) return;
  const lines = just.split("\n");
  const sections = {};
  let current = null;
  for (const line of lines) {
    const stripped = line.trim();
    const headerMatch = stripped.match(/^#+\s*(.+)$/i);
    if (headerMatch) {
      const key = SECTION_SPLIT_MAP[headerMatch[1].toLowerCase().replace(/[:\-_]/g, " ").trim()];
      if (key) { current = key; continue; }
    }
    if (!stripped) continue;
    if (current === "effectCause") {
      if (!sections.effectCause) sections.effectCause = [];
      const item = stripped.replace(/^[-*•]\s*/, "").trim();
      if (item) sections.effectCause.push(item);
    } else if (current) {
      sections[current] = (sections[current] || "") + " " + stripped;
      sections[current] = sections[current].trim();
    } else {
      sections.justification = (sections.justification || "") + " " + stripped;
      sections.justification = sections.justification.trim();
    }
  }
  if (sections.justification) hyp.justification = sections.justification;
  if (sections.uncertainty) hyp.uncertainty = sections.uncertainty;
  if (sections.verification) hyp.roadmap = splitLines(sections.verification);
  if (sections.effectCause) hyp.effectCauseExamples = sections.effectCause;
  if (sections.generalApproach) hyp.generalApproach = sections.generalApproach;
  if (sections.actionableNow) hyp.actionableNow = sections.actionableNow;
  if (sections.whyItMatters) hyp.whyItMatters = sections.whyItMatters;
  if (sections.bestPractices) hyp.bestPractices = sections.bestPractices;
  if (sections.novelty) hyp.novelty = sections.novelty;
  if (sections.risks) hyp.risks = sections.risks;
}

async function exportFormat(fmt) {
  if (!state.sessionId || !state.runId) {
    showToast("Нет результата", "Сначала запустите анализ");
    return;
  }
  if (fmt === "jira" || fmt === "youtrack") {
    try {
      const data = await api("POST", `/sessions/${state.sessionId}/runs/${state.runId}/export/${fmt}`, {});
      showToast(fmt === "jira" ? "Экспорт в Jira" : "Экспорт в YouTrack", `Отправлено задач: ${data.count || 0}`);
      if ((data.exported || [])[0]?.status === "mocked") {
        showToast("Mock", `${fmt} не настроен — возвращён mock-ответ`);
      }
    } catch (e) {
      showToast("Ошибка экспорта", e.message);
    }
    return;
  }
  try {
    const blob = await apiDownload(`/sessions/${state.sessionId}/runs/${state.runId}/export/download?format=${fmt}`);
    const names = { md: "report.md", json: "hypotheses.json", docx: "report.docx", pdf: "report.pdf", csv: "hypotheses.csv" };
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = names[fmt] || `export.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("Экспорт готов", `Скачан ${names[fmt] || fmt}`);
  } catch (e) {
    showToast("Ошибка экспорта", e.message);
  }
}

async function sendFeedback(label) {
  const item = selectedItem();
  if (!item || !state.sessionId || !state.runId) return;
  const claim = item.title || "";
  try {
    await api("POST", `/sessions/${state.sessionId}/runs/${state.runId}/feedback`, {
      claim, label, expert_id: "ui"
    });
    showToast("Фидбек сохранён", `${label}: ${claim.slice(0, 50)}`);
    if (label === "accepted") { state.pinned.add(item.id); state.decision = "принято"; }
    else if (label === "rejected") { state.pinned.delete(item.id); state.decision = "отклонено"; }
    else { state.decision = "скорректировано"; }
    renderInspector();
  } catch (e) {
    showToast("Ошибка фидбека", e.message);
  }
}

function applyLayout(left, right) {
  state.layout.left = Math.max(280, Math.min(620, Math.round(left)));
  state.layout.right = Math.max(260, Math.min(680, Math.round(right)));
  renderLayout();
  renderEdges();
}

function startColumnResize(event) {
  const side = event.currentTarget.dataset.side;
  const resizer = event.currentTarget;
  const startX = event.clientX;
  const startLeft = state.layout.left;
  const startRight = state.layout.right;
  const isPointer = event.type.startsWith("pointer");
  const moveTarget = isPointer ? resizer : window;
  const moveEvent = isPointer ? "pointermove" : "mousemove";
  const upEvent = isPointer ? "pointerup" : "mouseup";
  event.preventDefault();
  resizer.classList.add("dragging");
  if (isPointer) resizer.setPointerCapture(event.pointerId);
  function move(ev) {
    const dx = ev.clientX - startX;
    if (side === "left") applyLayout(startLeft + dx, state.layout.right);
    else applyLayout(state.layout.left, startRight - dx);
  }
  function up() {
    resizer.classList.remove("dragging");
    moveTarget.removeEventListener(moveEvent, move);
    moveTarget.removeEventListener(upEvent, up);
  }
  moveTarget.addEventListener(moveEvent, move);
  moveTarget.addEventListener(upEvent, up);
}

function setupTooltips() {
  const tooltip = document.getElementById("tooltipLayer");
  function moveTooltip(event) {
    if (!tooltip.classList.contains("visible")) return;
    const margin = 14;
    const rect = tooltip.getBoundingClientRect();
    let x = event.clientX + 14;
    let y = event.clientY + 14;
    if (x + rect.width + margin > window.innerWidth) x = event.clientX - rect.width - 14;
    if (y + rect.height + margin > window.innerHeight) y = event.clientY - rect.height - 14;
    tooltip.style.transform = `translate(${Math.max(margin, x)}px, ${Math.max(margin, y)}px) scale(1)`;
  }
  document.addEventListener("mouseover", (event) => {
    const target = event.target.closest("[data-tip]");
    if (!target) return;
    tooltip.textContent = target.dataset.tip;
    tooltip.classList.add("visible");
    moveTooltip(event);
  });
  document.addEventListener("mousemove", moveTooltip);
  document.addEventListener("mouseout", (event) => {
    if (!event.target.closest("[data-tip]")) return;
    tooltip.classList.remove("visible");
  });
}

function setHelp(open) {
  document.getElementById("helpModal").classList.toggle("hidden", !open);
}

function setupEvents() {
  els.searchInput.addEventListener("input", () => {
    state.search = els.searchInput.value.trim();
    renderNodes();
  });

  els.filterTabs.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-filter]");
    if (!button) return;
    state.filter = button.dataset.filter;
    els.filterTabs.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    renderNodes();
  });

  Object.entries(weightInputs).forEach(([key, input]) => {
    input.addEventListener("input", () => {
      state.weights[key] = Number(input.value);
      document.getElementById(`${key}Value`).textContent = state.weights[key];
      renderMetrics();
      renderInspector();
      renderRankList();
      renderNodes();
    });
  });

  Object.entries(externalInputs).forEach(([key, input]) => {
    input.addEventListener("change", () => {
      state.external[key] = input.checked;
    });
  });

  document.getElementById("resetWeightsBtn").addEventListener("click", () => {
    state.weights = { ...DEFAULT_WEIGHTS };
    renderWeights();
    renderAll();
  });

  document.getElementById("generateBtn").addEventListener("click", runAnalysis);
  els.exportBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    els.exportPopover.classList.toggle("open");
  });
  els.exportPopover.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-fmt]");
    if (!btn) return;
    els.exportPopover.classList.remove("open");
    exportFormat(btn.dataset.fmt);
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".export-wrap")) els.exportPopover.classList.remove("open");
  });

  document.getElementById("helpBtn").addEventListener("click", () => setHelp(true));
  document.getElementById("closeHelpBtn").addEventListener("click", () => setHelp(false));
  document.getElementById("helpModal").addEventListener("click", (e) => {
    if (e.target.id === "helpModal") setHelp(false);
  });
  document.getElementById("closeExampleBtn").addEventListener("click", () => {
    els.exampleModal.classList.add("hidden");
  });
  els.exampleModal.addEventListener("click", (e) => {
    if (e.target.id === "exampleModal") els.exampleModal.classList.add("hidden");
  });
  document.getElementById("focusBtn").addEventListener("click", toggleFocusMode);
  document.getElementById("fitBtn").addEventListener("click", () => fitCanvasView(true));
  document.getElementById("zoomInBtn").addEventListener("click", () => setCanvasScale(state.view.scale + CANVAS.scaleStep));
  document.getElementById("zoomOutBtn").addEventListener("click", () => setCanvasScale(state.view.scale - CANVAS.scaleStep));
  document.getElementById("clearCanvasBtn").addEventListener("click", () => { if (allNodes().length) { clearCanvas(); showToast("Холст очищен", "Все карточки удалены"); } });
  els.canvasStage.addEventListener("wheel", (event) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    setCanvasScale(state.view.scale + (event.deltaY < 0 ? CANVAS.scaleStep : -CANVAS.scaleStep), event);
  }, { passive: false });

  document.getElementById("pinBtn").addEventListener("click", () => {
    if (!state.selected) return;
    state.pinned.add(state.selected);
    state.decision = "в плане";
    renderInspector();
    showToast("В плане", "Гипотеза закреплена для проверки");
  });
  document.getElementById("approveBtn").addEventListener("click", () => sendFeedback("accepted"));
  document.getElementById("rejectBtn").addEventListener("click", () => sendFeedback("rejected"));
  document.getElementById("adjustBtn").addEventListener("click", () => sendFeedback("adjusted"));

  ["leftResizer", "rightResizer"].forEach((id) => {
    const resizer = document.getElementById(id);
    resizer.addEventListener("pointerdown", startColumnResize);
  });

  // file upload
  els.dropZone.addEventListener("click", () => els.fileInput.click());
  els.fileInput.addEventListener("change", () => {
    if (els.fileInput.files.length) addFiles(Array.from(els.fileInput.files));
    els.fileInput.value = "";
  });
  els.dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    els.dropZone.classList.add("drag");
  });
  els.dropZone.addEventListener("dragleave", () => els.dropZone.classList.remove("drag"));
  els.dropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    els.dropZone.classList.remove("drag");
    if (event.dataTransfer.files.length) addFiles(Array.from(event.dataTransfer.files));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setHelp(false);
      els.exampleModal.classList.add("hidden");
    }
    const isEditable = ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) || event.target.isContentEditable;
    if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !isEditable) {
      event.preventDefault();
      els.searchInput.focus();
      els.searchInput.select();
    }
  });
}

setupTooltips();
setupEvents();
renderAll();
loadExamples();
setRunState("готов к запуску");