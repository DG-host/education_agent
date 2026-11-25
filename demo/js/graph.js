/* 内容图谱 · 知识网络：确定性布局、SVG 渲染与交互。 */

import { card } from "./components.js";
import {
  badge, confidenceBadge, esc, icon, pct, progress, rateTone, short,
} from "./format.js";
import { state } from "./data.js";

const NS = "http://www.w3.org/2000/svg";
const W = 1000;
const H = 640;
const RADIUS = { topic: 26, indicator: 14, standard: 11, material: 5 };
const LABEL = { topic: "主题", indicator: "指标", standard: "课标", material: "材料" };
const KIND_ORDER = ["topic", "indicator", "standard", "material"];
const EDGE_ORDER = ["topic_indicator", "indicator_standard", "indicator_material", "topic_progression"];

let current = null;

const text = (value) => String(value ?? "");
const escText = (value) => esc(text(value));

const splitLabel = (value, limit = 9) => {
  const chars = Array.from(text(value));
  const lines = [];
  while (chars.length && lines.length < 2) lines.push(chars.splice(0, limit).join(""));
  if (chars.length) lines[lines.length - 1] = lines[lines.length - 1].slice(0, Math.max(1, limit - 1)) + "…";
  return lines.length ? lines : [""];
};

const clamp = (value, lo, hi) => Math.min(hi, Math.max(lo, value));

const edgeId = (edge) => edge.id || (edge.kind + ":" + edge.source + "->" + edge.target);

const graphMeta = () => {
  const graph = state.graph || {};
  const meta = graph.meta || {};
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph.edges) ? graph.edges : [];
  return { graph, meta, nodes, edges };
};

export const knowledgeGraphCard = () => {
  const { graph, meta, nodes } = graphMeta();
  if (!nodes.length) {
    return card({
      title: "知识网络",
      sub: "把主题、指标、课标与材料串成可核对的关系图；旧快照没有图谱投影时显示此提示。",
      cls: "graph-card",
      body: '<div class="graph-empty"><strong>当前快照没有知识网络</strong>' +
        '<p>重新运行分析后，内容图谱会带上主题、指标、课标与材料的关系投影。</p></div>',
    });
  }
  const counts = meta.node_counts || {};
  return card({
    title: "知识网络",
    sub: "默认只看知识骨架；材料层按需展开。边只来自 content_map 的显式出处，不猜教材归属。",
    cls: "graph-card",
    actions: '<div class="graph-head-count"><b>' + escText(counts.total || nodes.length) + "</b> 个节点 · <b>" +
      escText((meta.edge_counts || {}).total || 0) + "</b> 条关系</div>",
    body: '<div class="graph-shell" id="knowledgeGraph" data-graph-version="' + escText(graph.version || "") + '">' +
      '<div class="graph-toolbar" role="toolbar" aria-label="知识网络工具">' +
        '<div class="graph-search"><label class="sr-only" for="graphSearch">搜索知识节点</label>' +
          '<span class="graph-search-icon" aria-hidden="true">' + icon("search") + "</span>" +
          '<input id="graphSearch" type="search" autocomplete="off" spellcheck="false" placeholder="搜索主题 / 指标 / 材料" />' +
        "</div>" +
        '<button class="btn btn-sm graph-toggle" type="button" data-graph-toggle="materials" aria-pressed="false" aria-label="显示或隐藏材料" title="显示或隐藏材料">' +
          icon("network") + "<span>显示材料</span></button>" +
        '<button class="btn btn-sm graph-toggle" type="button" data-graph-toggle="rate" aria-pressed="false" aria-label="按群体满分率给指标着色" title="按群体满分率给指标着色">' +
          icon("target") + "<span>按满分率着色</span></button>" +
        '<span class="graph-spacer"></span>' +
        '<button class="btn btn-sm graph-icon-btn" type="button" data-graph-action="zoom-out" aria-label="缩小" title="缩小">' + icon("minus") + "</button>" +
        '<button class="btn btn-sm graph-icon-btn" type="button" data-graph-action="fit" aria-label="适配视图" title="适配视图">' + icon("fit") + "</button>" +
        '<button class="btn btn-sm graph-icon-btn" type="button" data-graph-action="zoom-in" aria-label="放大" title="放大">' + icon("plus") + "</button>" +
        '<button class="btn btn-sm graph-icon-btn" type="button" data-graph-action="fullscreen" aria-label="全屏" title="全屏">' + icon("expand") + "</button>" +
      "</div>" +
      '<div class="graph-stage" id="graphStage">' +
        '<svg id="graphSvg" viewBox="0 0 1000 640" role="img" tabindex="0" aria-label="知识网络图：主题、指标、课标与材料的关系">' +
          '<defs><marker id="graphArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">' +
            '<path d="M0 0L10 5L0 10z" fill="currentColor"></path></marker></defs>' +
          '<g id="graphEdges"></g><g id="graphNodes"></g>' +
        "</svg>" +
        '<div class="graph-empty" id="graphEmpty" hidden></div>' +
        '<div class="graph-status" id="graphStatus" aria-live="polite"></div>' +
      "</div>" +
      '<aside class="graph-detail" id="graphDetail" aria-live="polite">' +
        '<div class="graph-detail-empty"><strong>点选一个节点</strong><p>查看它的上下游关系、材料出处与学情统计。也可以先搜索指标编号。</p></div>' +
      "</aside>" +
      '<div class="graph-legend">' +
        '<span class="graph-legend-item"><i class="dot dot-topic"></i>主题</span>' +
        '<span class="graph-legend-item"><i class="dot dot-indicator"></i>指标</span>' +
        '<span class="graph-legend-item"><i class="dot dot-standard"></i>课标</span>' +
        '<span class="graph-legend-item"><i class="dot dot-material"></i>材料</span>' +
        '<span class="graph-legend-item graph-legend-note">实线=显式出处，虚线=学习进阶</span>' +
      "</div>" +
      '<div class="graph-footnote" id="graphFootnote">' +
        "<span>骨架 " + escText(meta.skeleton_nodes || 0) + " 个节点 / " + escText(meta.skeleton_edges || 0) + " 条关系；" +
        "材料层 " + escText(meta.resources || 0) + " 份。</span>" +
        ((meta.excluded_materials || []).length ? "<span>教材切片 " +
          escText((meta.excluded_materials || []).length) + " 份未标主题/指标，不进入图，避免猜测挂接。</span>" : "") +
      "</div>" +
    "</div>",
  });
};

const createSvg = (name, attrs = {}) => {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  }
  return node;
};

const nodeSearchBlob = (node, nodesById) => {
  const parts = [node.id, node.ref, node.label, node.kind, LABEL[node.kind] || node.kind];
  if (node.topic_id) parts.push(node.topic_id);
  if (node.cr_id) parts.push(node.cr_id);
  if (node.material_type) parts.push(node.material_type);
  if (node.question_type) parts.push(node.question_type);
  for (const indicatorId of node.indicator_ids || []) {
    const indicator = nodesById.get("indicator:" + indicatorId);
    if (indicator) parts.push(indicator.label);
  }
  return parts.join(" ").toLowerCase();
};

const TOPIC_Y = 96;
const INDICATOR_Y = 300;
const STANDARD_Y = 540;

const buildLayout = (nodes, edges) => {
  const positions = new Map();
  const topics = nodes.filter((node) => node.kind === "topic").sort((a, b) => a.ref.localeCompare(b.ref));
  const indicators = nodes.filter((node) => node.kind === "indicator");
  const standards = nodes.filter((node) => node.kind === "standard");
  const materials = nodes.filter((node) => node.kind === "material");
  const topicAnchor = new Map();
  const indicatorTopic = new Map();
  const standardTopic = new Map();

  topics.forEach((node, index) => {
    const spread = topics.length > 1 ? 668 / (topics.length - 1) : 0;
    const x = topics.length > 1 ? 166 + spread * index : W / 2;
    topicAnchor.set(node.id, { x, y: TOPIC_Y });
    positions.set(node.id, { x, y: TOPIC_Y });
  });

  for (const edge of edges) {
    if (edge.kind !== "topic_indicator") continue;
    const indicator = indicators.find((node) => node.id === edge.target);
    const topic = topicAnchor.get(edge.source);
    if (indicator && topic) indicatorTopic.set(indicator.id, topic);
  }

  for (const node of indicators) {
    const parent = indicatorTopic.get(node.id);
    if (!parent) continue;
    const siblings = indicators.filter((item) => indicatorTopic.get(item.id) === parent)
      .sort((a, b) => a.ref.localeCompare(b.ref));
    const index = siblings.indexOf(node);
    const spread = siblings.length > 1 ? Math.min(112, 320 / (siblings.length - 1)) : 0;
    const x = parent.x + (index - (siblings.length - 1) / 2) * spread;
    positions.set(node.id, { x: clamp(x, 52, W - 52), y: INDICATOR_Y });
  }

  for (const edge of edges) {
    if (edge.kind !== "indicator_standard") continue;
    const parent = indicatorTopic.get(edge.source);
    if (parent) standardTopic.set(edge.target, parent);
  }

  for (const node of standards) {
    const parent = standardTopic.get(node.id);
    if (!parent) continue;
    positions.set(node.id, { x: parent.x, y: STANDARD_Y });
  }

  const groups = new Map();
  for (const node of materials) {
    const owner = (node.indicator_ids || [])[0];
    if (!owner) continue;
    if (!groups.has(owner)) groups.set(owner, []);
    groups.get(owner).push(node);
  }
  for (const [owner, group] of groups) {
    const parent = positions.get("indicator:" + owner);
    if (!parent) continue;
    group.sort((a, b) => a.ref.localeCompare(b.ref));
    group.forEach((node, index) => {
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / group.length;
      positions.set(node.id, {
        x: clamp(parent.x + Math.cos(angle) * 54, 14, W - 14),
        y: clamp(parent.y + Math.sin(angle) * 54, 52, H - 40),
      });
    });
  }

  for (const node of nodes) {
    if (!positions.has(node.id)) positions.set(node.id, { x: W / 2, y: H / 2 });
  }
  return positions;
};

const colorClass = (node, rateMode) => {
  if (node.kind === "indicator" && rateMode) {
    const stat = state.indicatorStats.get(node.ref) || {};
    return "rate-" + rateTone(stat.rate);
  }
  return "kind-" + node.kind;
};

const renderLines = (group, graph, positions, visible, selected, focus, stateUi) => {
  group.replaceChildren();
  const edgeEls = new Map();
  const neighbors = new Set();
  if (selected) {
    for (const edge of graph.edges) {
      if (edge.source === selected) neighbors.add(edge.target);
      else if (edge.target === selected) neighbors.add(edge.source);
    }
  }
  for (const edge of graph.edges) {
    if (!visible.has(edge.source) || !visible.has(edge.target)) continue;
    const a = positions.get(edge.source);
    const b = positions.get(edge.target);
    if (!a || !b) continue;
    const line = createSvg("line", {
      x1: a.x.toFixed(1), y1: a.y.toFixed(1), x2: b.x.toFixed(1), y2: b.y.toFixed(1),
      class: "gedge gedge-" + edge.kind + (edge.kind === "topic_progression" ? " gedge-arrow" : ""),
      "data-edge": edgeId(edge),
    });
    if (edge.kind === "topic_progression") line.setAttribute("marker-end", "url(#graphArrow)");
    if (selected) {
      const active = edge.source === selected || edge.target === selected;
      line.classList.toggle("is-active", active);
      line.classList.toggle("is-dim", !active);
      if (focus && !active) line.classList.add("is-hidden");
    }
    group.appendChild(line);
    edgeEls.set(edgeId(edge), line);
  }
  return { edgeEls, neighbors };
};

const renderNodes = (group, graph, positions, visible, selected, focus, stateUi, nodesById) => {
  group.replaceChildren();
  const nodeEls = new Map();
  const neighbors = new Set();
  if (selected) {
    for (const edge of graph.edges) {
      if (edge.source === selected) neighbors.add(edge.target);
      else if (edge.target === selected) neighbors.add(edge.source);
    }
  }
  for (const node of graph.nodes) {
    if (!visible.has(node.id)) continue;
    const pos = positions.get(node.id);
    if (!pos) continue;
    const radius = RADIUS[node.kind] || 8;
    const g = createSvg("g", {
      class: "gnode gnode-" + node.kind + " " + colorClass(node, stateUi.rateMode),
      transform: "translate(" + pos.x.toFixed(1) + " " + pos.y.toFixed(1) + ")",
      "data-graph-node": node.id,
      tabindex: "0",
      role: "button",
      "aria-label": (LABEL[node.kind] || node.kind) + " " + node.ref + "：" + node.label,
    });
    const title = createSvg("title");
    title.textContent = (LABEL[node.kind] || node.kind) + " " + node.ref + " · " + node.label;
    g.appendChild(title);
    const halo = createSvg("circle", { r: radius + 7, class: "gnode-halo" });
    g.appendChild(halo);
    const dot = createSvg("circle", { r: radius, class: "gnode-dot" });
    g.appendChild(dot);
    if (node.kind === "material") {
      g.appendChild(createSvg("circle", { r: 13, class: "gnode-hit" }));
    }
    const labelGroup = createSvg("g", { class: "gnode-label" });
    const lines = node.kind === "material" ? [node.ref] : splitLabel(node.label, node.kind === "topic" ? 10 : 9);
    lines.forEach((lineText, index) => {
      const label = createSvg("text", {
        x: 0,
        y: radius + 17 + index * 14,
        "text-anchor": "middle",
        class: "g-label g-label-" + node.kind,
      });
      label.textContent = lineText;
      labelGroup.appendChild(label);
    });
    g.appendChild(labelGroup);
    if (selected) {
      const active = node.id === selected || neighbors.has(node.id);
      g.classList.toggle("is-selected", node.id === selected);
      g.classList.toggle("is-neighbor", node.id !== selected && neighbors.has(node.id));
      g.classList.toggle("is-dim", !active);
      if (focus && !active) g.classList.add("is-hidden");
    }
    if (stateUi.hits && stateUi.hits.size) g.classList.toggle("is-hit", stateUi.hits.has(node.id));
    group.appendChild(g);
    nodeEls.set(node.id, g);
  }
  return { nodeEls, neighbors };
};

const detailNeighbors = (graph, id) => {
  const result = [];
  for (const edge of graph.edges) {
    if (edge.source === id) result.push({ edge, id: edge.target, dir: "out" });
    else if (edge.target === id) result.push({ edge, id: edge.source, dir: "in" });
  }
  return result;
};

const detailButton = (node) =>
  '<button class="chip chip-button" type="button" data-graph-node="' + escText(node.id) + '">' +
  escText(node.ref) + "</button>";

const detailActions = (node) => {
  if (node.kind === "indicator") {
    return '<button class="btn btn-sm" type="button" data-action="indicator" data-id="' + escText(node.ref) + '">' +
      icon("arrow") + "<span>打开指标详情</span></button>";
  }
  if (node.kind === "material") {
    return '<button class="btn btn-sm" type="button" data-action="material" data-id="' + escText(node.ref) + '">' +
      icon("arrow") + "<span>打开材料详情</span></button>";
  }
  return "";
};

const detailBody = (node, graph, ui) => {
  const nodesById = new Map(graph.nodes.map((item) => [item.id, item]));
  const neighbors = detailNeighbors(graph, node.id);
  const relation = neighbors.length
    ? '<div class="graph-relations">' + neighbors.map((item) => {
      const other = nodesById.get(item.id);
      const direction = item.dir === "out" ? "→" : "←";
      return '<div class="graph-relation"><span class="graph-relation-dir" aria-hidden="true">' + direction + "</span>" +
        '<span class="graph-relation-kind">' + escText(item.edge.label) + "</span>" +
        (other ? detailButton(other) : '<span class="mono">' + escText(item.id) + "</span>") + "</div>";
    }).join("") + "</div>"
    : '<div class="note">暂无相邻节点。</div>';

  let facts = "";
  if (node.kind === "indicator") {
    const stat = state.indicatorStats.get(node.ref) || {};
    const meta = state.indicatorMeta.get(node.ref) || {};
    facts = '<div class="graph-facts">' +
      '<div><span>观察指标</span><b>' + escText(meta.observation || node.label) + "</b></div>" +
      '<div><span>课标</span><b class="mono">' + escText(node.cr_id || "—") + "</b></div>" +
      '<div><span>课标页</span><b>PDF ' + escText(meta.standard ? meta.standard.pdf_pages : "—") +
        " · 正文 " + escText(meta.standard ? meta.standard.body_pages : "—") + "</b></div>" +
      '<div><span>教材页</span><b>' + escText(node.textbook_pages || meta.textbook_pages || "—") + "</b></div>" +
      '<div><span>群体满分率</span><b class="num">' + pct(stat.rate) + "</b>" + progress(stat.rate) + "</div>" +
      '<div><span>观测 / 置信度</span><b>' + escText(stat.observed ?? "—") + " · " +
        (stat.confidence ? confidenceBadge(stat.confidence) : "—") + "</b></div></div>";
  } else if (node.kind === "topic") {
    facts = '<div class="graph-facts"><div><span>主题目标</span><b>' + escText(node.goal || "—") + "</b></div></div>";
  } else if (node.kind === "standard") {
    facts = '<div class="graph-facts">' +
      '<div><span>课标编号</span><b class="mono">' + escText(node.ref) + "</b></div>" +
      '<div><span>PDF 页</span><b>' + escText(node.pdf_pages || "—") + "</b></div>" +
      '<div><span>正文页</span><b>' + escText(node.body_pages || "—") + "</b></div></div>";
  } else {
    const material = state.materialById.get(node.ref) || {};
    const records = state.recordsByMaterial.get(node.ref) || [];
    facts = '<div class="graph-facts">' +
      '<div><span>材料类型</span><b>' + escText(node.material_type || material.type || "—") +
        (node.question_type ? " · " + escText(node.question_type) : "") + "</b></div>" +
      '<div><span>主题 / 满分</span><b>' + escText(node.topic_id || material.topic_id || "—") +
        " · " + escText(material.max_score ?? "—") + "</b></div>" +
      '<div><span>可用节点</span><b>' + ((material.node_scope || []).length ? material.node_scope.map(escText).join("、") : "—") + "</b></div>" +
      '<div><span>作答记录</span><b class="num">' + records.length + " 条</b></div></div>";
  }

  return '<div class="graph-detail-head"><div><div class="eyebrow">' + escText(LABEL[node.kind] || node.kind) +
    "</div><h3>" + escText(node.ref) + "</h3></div>" +
    '<button class="icon-btn" type="button" data-graph-action="clear" aria-label="关闭节点详情" title="关闭">' +
    icon("close") + "</button></div>" +
    '<p class="graph-detail-title">' + escText(node.kind === "material" ? short(node.label, 32) : node.label) + "</p>" +
    facts + relation +
    '<div class="graph-detail-actions">' + detailButtons(node, ui) + "</div>";
};

const detailButtons = (node, ui) => {
  const actions = [];
  if (ui.selected) actions.push('<button class="btn btn-sm" type="button" data-graph-action="focus">' +
    icon("target") + "<span>" + (ui.focus ? "返回全图" : "只看相邻") + "</span></button>");
  actions.push(detailActions(node));
  return actions.join("");
};

const emptyDetail = () => '<div class="graph-detail-empty"><strong>点选一个节点</strong>' +
  "<p>查看它的上下游关系、材料出处与学情统计。也可以先搜索指标编号。</p></div>";

export const mountKnowledgeGraph = () => {
  destroyKnowledgeGraph();
  const shell = document.getElementById("knowledgeGraph");
  if (!shell) return;
  const { graph, meta, nodes, edges } = graphMeta();
  if (!nodes.length) return;

  const svg = document.getElementById("graphSvg");
  const edgesGroup = document.getElementById("graphEdges");
  const nodesGroup = document.getElementById("graphNodes");
  const detail = document.getElementById("graphDetail");
  const status = document.getElementById("graphStatus");
  const search = document.getElementById("graphSearch");
  const empty = document.getElementById("graphEmpty");
  if (!svg || !edgesGroup || !nodesGroup || !detail) return;

  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const positions = buildLayout(nodes, edges);
  const visibleAll = new Set(nodes.map((node) => node.id));
  const visibleSkeleton = new Set(nodes.filter((node) => node.kind !== "material").map((node) => node.id));
  const view = { x: 0, y: 0, w: W, h: H };
  const ui = {
    showMaterials: false,
    rateMode: false,
    selected: null,
    focus: false,
    hits: new Set(),
    query: "",
    view,
    nodeEls: new Map(),
    edgeEls: new Map(),
    cleanup: [],
  };

  const visible = () => (ui.showMaterials ? visibleAll : visibleSkeleton);

  const updateViewBox = () => {
    svg.setAttribute("viewBox", view.x.toFixed(1) + " " + view.y.toFixed(1) + " " + view.w.toFixed(1) + " " + view.h.toFixed(1));
    shell.classList.toggle("graph-zoomed", view.w < 860);
  };

  const pointFromEvent = (event) => {
    const matrix = svg.getScreenCTM();
    if (!matrix) return { x: 0, y: 0 };
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    return point.matrixTransform(matrix.inverse());
  };

  const setStatus = () => {
    if (!status) return;
    const count = visible().size;
    const total = nodes.length;
    let message = (ui.showMaterials ? "全部 " : "知识骨架 ") + count + " 个节点";
    if (ui.showMaterials) message += " · " + edges.length + " 条关系";
    if (ui.selected) {
      const node = nodesById.get(ui.selected);
      if (node) message += " · 已选 " + node.ref;
    }
    status.textContent = message + "（共 " + total + " 个节点）";
  };

  const applyClasses = () => {
    shell.classList.toggle("graph-rate-mode", ui.rateMode);
    shell.classList.toggle("graph-focus-mode", ui.focus && Boolean(ui.selected));
    shell.classList.toggle("graph-searching", Boolean(ui.query));
    for (const [id, el] of ui.nodeEls) {
      el.classList.toggle("is-selected", id === ui.selected);
      el.classList.toggle("is-hit", ui.hits.has(id));
    }
    setStatus();
  };

  const render = () => {
    const shown = visible();
    const edgeResult = renderLines(edgesGroup, graph, positions, shown, ui.selected, ui.focus, ui);
    const nodeResult = renderNodes(nodesGroup, graph, positions, shown, ui.selected, ui.focus, ui, nodesById);
    ui.edgeEls = edgeResult.edgeEls;
    ui.nodeEls = nodeResult.nodeEls;
    ui.neighbors = nodeResult.neighbors;
    detail.innerHTML = ui.selected ? detailBody(nodesById.get(ui.selected), graph, ui) : emptyDetail();
    if (empty) {
      empty.hidden = shown.size > 0;
      empty.textContent = shown.size ? "" : "当前筛选下没有节点。";
    }
    applyClasses();
  };

  const select = (id) => {
    const node = nodesById.get(id);
    if (!node) return;
    if (node.kind === "material" && !ui.showMaterials) {
      ui.showMaterials = true;
      const toggle = shell.querySelector('[data-graph-toggle="materials"]');
      if (toggle) { toggle.setAttribute("aria-pressed", "true"); toggle.classList.add("is-on"); }
    }
    ui.selected = id;
    ui.focus = false;
    render();
    const cardEl = shell.closest(".graph-card");
    if (cardEl) cardEl.classList.add("has-selection");
  };

  const clear = () => {
    ui.selected = null;
    ui.focus = false;
    render();
    const cardEl = shell.closest(".graph-card");
    if (cardEl) cardEl.classList.remove("has-selection");
  };

  const zoomAt = (factor, anchor) => {
    const point = anchor || { x: view.x + view.w / 2, y: view.y + view.h / 2 };
    const nextW = clamp(view.w / factor, 260, W * 1.4);
    const nextH = nextW * (H / W);
    const ratio = nextW / view.w;
    view.x = point.x - (point.x - view.x) * ratio;
    view.y = point.y - (point.y - view.y) * ratio;
    view.w = nextW;
    view.h = nextH;
    updateViewBox();
  };

  const fit = () => {
    view.x = 0; view.y = 0; view.w = W; view.h = H;
    updateViewBox();
  };

  const doSearch = () => {
    const query = ui.query.trim().toLowerCase();
    ui.hits = new Set();
    if (query) {
      for (const node of nodes) {
        if (nodeSearchBlob(node, nodesById).includes(query)) ui.hits.add(node.id);
      }
    }
    render();
    if (query && status) {
      status.textContent = "搜索到 " + ui.hits.size + " 个节点；回车选中第一个。";
    }
  };

  const setToggle = (name, value) => {
    if (name === "materials") {
      ui.showMaterials = Boolean(value);
      if (!ui.showMaterials && ui.selected && nodesById.get(ui.selected) && nodesById.get(ui.selected).kind === "material") {
        ui.selected = null;
      }
    } else if (name === "rate") {
      ui.rateMode = Boolean(value);
    }
    const toggle = shell.querySelector('[data-graph-toggle="' + name + '"]');
    if (toggle) {
      toggle.setAttribute("aria-pressed", ui[name === "materials" ? "showMaterials" : "rateMode"] ? "true" : "false");
      toggle.classList.toggle("is-on", Boolean(ui[name === "materials" ? "showMaterials" : "rateMode"]));
    }
    render();
  };

  const toggleFocus = () => {
    if (!ui.selected) return;
    ui.focus = !ui.focus;
    render();
  };

  const toggleFullscreen = async () => {
    const target = shell;
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (target.requestFullscreen) await target.requestFullscreen();
      else target.classList.toggle("is-expanded");
    } catch {
      target.classList.toggle("is-expanded");
    }
    syncFullscreenButton();
  };

  const syncFullscreenButton = () => {
    const button = shell.querySelector('[data-graph-action="fullscreen"]');
    if (!button) return;
    const active = document.fullscreenElement === shell || shell.classList.contains("is-expanded");
    button.innerHTML = icon(active ? "collapse" : "expand");
    button.setAttribute("aria-label", active ? "退出全屏" : "全屏");
    button.setAttribute("title", active ? "退出全屏" : "全屏");
  };

  const onShellClick = (event) => {
    const toggle = event.target.closest("[data-graph-toggle]");
    if (toggle) {
      const name = toggle.dataset.graphToggle;
      if (name === "materials") setToggle("materials", !ui.showMaterials);
      else if (name === "rate") setToggle("rate", !ui.rateMode);
      return;
    }
    const action = event.target.closest("[data-graph-action]");
    if (action) {
      const name = action.dataset.graphAction;
      if (name === "zoom-in") zoomAt(1.25);
      else if (name === "zoom-out") zoomAt(0.8);
      else if (name === "fit") fit();
      else if (name === "fullscreen") toggleFullscreen();
      else if (name === "clear") clear();
      else if (name === "focus") toggleFocus();
      return;
    }
    const nodeButton = event.target.closest("[data-graph-node]");
    if (nodeButton) {
      select(nodeButton.dataset.graphNode);
    }
  };

  const onSvgClick = (event) => {
    if (ui.suppressClick) { ui.suppressClick = false; return; }
    const nodeEl = event.target.closest("[data-graph-node]");
    if (nodeEl) {
      select(nodeEl.dataset.graphNode);
      return;
    }
    if (!event.target.closest("[data-graph-action]")) clear();
  };

  const onSvgKeydown = (event) => {
    const nodeEl = event.target.closest("[data-graph-node]");
    if (nodeEl && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      select(nodeEl.dataset.graphNode);
      return;
    }
    if (event.key === "+" || event.key === "=") { event.preventDefault(); zoomAt(1.25); }
    else if (event.key === "-" || event.key === "_") { event.preventDefault(); zoomAt(0.8); }
    else if (event.key === "0") { event.preventDefault(); fit(); }
    else if (event.key === "Escape") {
      if (ui.selected) { event.preventDefault(); clear(); }
    }
  };

  let pointer = null;
  const onSvgPointerDown = (event) => {
    if (event.button !== 0) return;
    if (event.pointerType === "touch" && window.matchMedia("(max-width: 680px)").matches) return;
    const nodeEl = event.target.closest("[data-graph-node]");
    if (nodeEl) {
      const id = nodeEl.dataset.graphNode;
      const point = pointFromEvent(event);
      pointer = { kind: "node", id, last: point, moved: false };
      try { svg.setPointerCapture(event.pointerId); } catch { /* ignore */ }
      event.preventDefault();
      return;
    }
    if (event.target.closest("[data-graph-action]")) return;
    pointer = {
      kind: "pan",
      clientX: event.clientX,
      clientY: event.clientY,
      viewX: view.x,
      viewY: view.y,
      unit: view.w / Math.max(1, svg.getBoundingClientRect().width),
      moved: false,
    };
    try { svg.setPointerCapture(event.pointerId); } catch { /* ignore */ }
  };

  const onSvgPointerMove = (event) => {
    if (!pointer) return;
    if (pointer.kind === "node") {
      const point = pointFromEvent(event);
      const dx = point.x - pointer.last.x;
      const dy = point.y - pointer.last.y;
      if (Math.abs(dx) + Math.abs(dy) > 0.6) pointer.moved = true;
      const pos = positions.get(pointer.id);
      if (pos) {
        pos.x = clamp(pos.x + dx, 36, W - 36);
        pos.y = clamp(pos.y + dy, 36, H - 36);
        const el = ui.nodeEls.get(pointer.id);
        if (el) el.setAttribute("transform", "translate(" + pos.x.toFixed(1) + " " + pos.y.toFixed(1) + ")");
        updateConnectedEdges(pointer.id);
      }
      pointer.last = point;
      return;
    }
    const dx = event.clientX - pointer.clientX;
    const dy = event.clientY - pointer.clientY;
    if (Math.abs(dx) + Math.abs(dy) > 2) pointer.moved = true;
    view.x = pointer.viewX - dx * pointer.unit;
    view.y = pointer.viewY - dy * pointer.unit;
    updateViewBox();
  };

  const updateConnectedEdges = (id) => {
    for (const edge of edges) {
      if (edge.source !== id && edge.target !== id) continue;
      const line = ui.edgeEls.get(edgeId(edge));
      if (!line) continue;
      const a = positions.get(edge.source);
      const b = positions.get(edge.target);
      if (!a || !b) continue;
      line.setAttribute("x1", a.x.toFixed(1));
      line.setAttribute("y1", a.y.toFixed(1));
      line.setAttribute("x2", b.x.toFixed(1));
      line.setAttribute("y2", b.y.toFixed(1));
    }
  };

  const onSvgPointerUp = (event) => {
    if (!pointer) return;
    const wasNode = pointer.kind === "node";
    const moved = pointer.moved;
    const id = pointer.id;
    pointer = null;
    try { svg.releasePointerCapture(event.pointerId); } catch { /* ignore */ }
    if (moved) ui.suppressClick = true;
    if (wasNode && !moved && id) {
      ui.suppressClick = true;
      select(id);
    }
  };

  const onWheel = (event) => {
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1.12 : 0.89;
    zoomAt(factor, pointFromEvent(event));
  };

  const onSearchInput = () => {
    ui.query = search ? search.value : "";
    doSearch();
  };

  const onSearchKey = (event) => {
    if (event.key === "Enter") {
      const first = Array.from(ui.hits)[0];
      if (first) { event.preventDefault(); select(first); }
    } else if (event.key === "Escape") {
      if (search) search.value = "";
      ui.query = "";
      doSearch();
    }
  };

  const onFullscreenChange = () => {
    syncFullscreenButton();
    if (document.fullscreenElement && document.fullscreenElement !== shell) {
      shell.classList.remove("is-expanded");
    }
  };

  const onDocumentKeydown = (event) => {
    if (event.key !== "Escape") return;
    if (document.fullscreenElement === shell) return;
    if (ui.selected) clear();
  };

  shell.addEventListener("click", onShellClick);
  svg.addEventListener("click", onSvgClick);
  svg.addEventListener("keydown", onSvgKeydown);
  svg.addEventListener("pointerdown", onSvgPointerDown);
  svg.addEventListener("pointermove", onSvgPointerMove);
  svg.addEventListener("pointerup", onSvgPointerUp);
  svg.addEventListener("pointercancel", onSvgPointerUp);
  svg.addEventListener("wheel", onWheel, { passive: false });
  if (search) {
    search.addEventListener("input", onSearchInput);
    search.addEventListener("keydown", onSearchKey);
  }
  document.addEventListener("fullscreenchange", onFullscreenChange);
  document.addEventListener("keydown", onDocumentKeydown);

  ui.cleanup.push(() => {
    shell.removeEventListener("click", onShellClick);
    svg.removeEventListener("click", onSvgClick);
    svg.removeEventListener("keydown", onSvgKeydown);
    svg.removeEventListener("pointerdown", onSvgPointerDown);
    svg.removeEventListener("pointermove", onSvgPointerMove);
    svg.removeEventListener("pointerup", onSvgPointerUp);
    svg.removeEventListener("pointercancel", onSvgPointerUp);
    svg.removeEventListener("wheel", onWheel);
    if (search) {
      search.removeEventListener("input", onSearchInput);
      search.removeEventListener("keydown", onSearchKey);
    }
    document.removeEventListener("fullscreenchange", onFullscreenChange);
    document.removeEventListener("keydown", onDocumentKeydown);
    if (document.fullscreenElement === shell) document.exitFullscreen().catch(() => {});
  });

  current = ui;
  updateViewBox();
  render();
  if (meta && meta.excluded_materials && meta.excluded_materials.length) {
    const footnote = document.getElementById("graphFootnote");
    if (footnote) footnote.title = "教材切片未标主题/指标，不进入图。";
  }
  syncFullscreenButton();
  setStatus();
};

export const destroyKnowledgeGraph = () => {
  if (!current) return;
  for (const fn of current.cleanup) {
    try { fn(); } catch { /* ignore */ }
  }
  current = null;
};