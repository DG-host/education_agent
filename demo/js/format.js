/* 轻量格式化与内联图标；无第三方依赖。 */

export const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));

export const clamp = (value, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, Number(value) || 0));

export const num = (value, digits = 0) => {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
};

export const pct = (value, digits = 1) => {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return (n * 100).toFixed(digits) + "%";
};

export const signedPct = (value, digits = 1) => {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return (n >= 0 ? "+" : "") + (n * 100).toFixed(digits) + "pp";
};

export const short = (text, max = 28) => {
  const s = String(text ?? "").trim();
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
};

export const formatDate = (value, withTime = true) => {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const pad = (n) => String(n).padStart(2, "0");
  const date = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  if (!withTime) return date;
  return date + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
};

export const dateOnly = (value) => formatDate(value, false);

export const rateTone = (rate) => {
  if (rate === null || rate === undefined) return "neutral";
  const n = Number(rate);
  if (!Number.isFinite(n)) return "neutral";
  if (n >= 0.75) return "ok";
  if (n >= 0.5) return "warn";
  return "bad";
};

export const heatClass = (rate) => {
  if (rate === null || rate === undefined) return "heat-na";
  const n = Number(rate);
  if (!Number.isFinite(n)) return "heat-na";
  if (n >= 0.8) return "heat-4";
  if (n >= 0.6) return "heat-3";
  if (n >= 0.4) return "heat-2";
  if (n >= 0.2) return "heat-1";
  return "heat-0";
};

export const badge = (text, tone = "neutral", extra = "") =>
  '<span class="badge badge-' + tone + (extra ? " " + extra : "") + '">' + esc(text) + "</span>";

export const actionLabel = {
  review: "回顾",
  practice: "练习",
  variant: "变式",
  observe: "观察",
};

export const actionTone = {
  review: "brand",
  practice: "accent",
  variant: "warn",
  observe: "neutral",
};

export const actionBadge = (action) =>
  badge(actionLabel[action] || action || "—", actionTone[action] || "neutral");

export const confidenceLabel = { low: "低置信", medium: "中置信", high: "高置信" };
export const confidenceTone = { low: "warn", medium: "neutral", high: "ok" };
export const confidenceBadge = (confidence) =>
  badge(confidenceLabel[confidence] || confidence || "—", confidenceTone[confidence] || "neutral");

export const flagLabel = {
  insufficient_records: "记录不足",
  low_coverage: "覆盖偏低",
  single_node_only: "单节点",
  pending_scoring: "有待评分",
  unanswered_items: "有未作答",
  no_scored_record: "无已评记录",
};

export const flagBadge = (flag) => {
  const tone = flag === "insufficient_records" || flag === "no_scored_record" || flag === "low_coverage"
    ? "warn" : flag === "pending_scoring" || flag === "unanswered_items" ? "neutral" : "neutral";
  return badge(flagLabel[flag] || flag, tone);
};

export const statusTone = { "已评分": "ok", "待评分": "warn", "未作答": "bad" };
export const statusBadge = (status) => badge(status || "—", statusTone[status] || "neutral");

export const roleTone = { remedial: "bad", insufficient: "warn", stable: "ok" };

export const indicatorLabel = (id) => id || "—";

export const progress = (rate, tone = null, extra = "") => {
  const width = rate === null || rate === undefined ? 0 : Math.round(clamp(rate) * 1000) / 10;
  const cls = tone || rateTone(rate);
  return '<div class="progress ' + (cls === "neutral" ? "" : cls) + (extra ? " " + extra : "") +
    '" role="img" aria-label="比例 ' + esc(pct(rate)) + '"><span style="width:' + width + '%"></span></div>';
};

export const donut = (rate, size = 76, stroke = 8, caption = "得分率") => {
  const valid = rate !== null && rate !== undefined && Number.isFinite(Number(rate));
  const value = valid ? clamp(rate) : 0;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const color = valid ? ({ ok: "#15803D", warn: "#D97706", bad: "#BE123C" }[rateTone(value)]) : "#C4D6D2";
  return '<div class="donut" style="width:' + size + "px;height:" + size + 'px">' +
    '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + " " + size + '" aria-hidden="true">' +
    '<circle cx="' + size / 2 + '" cy="' + size / 2 + '" r="' + r + '" fill="none" stroke="#E3EEEC" stroke-width="' + stroke + '"/>' +
    '<circle cx="' + size / 2 + '" cy="' + size / 2 + '" r="' + r + '" fill="none" stroke="' + color +
    '" stroke-width="' + stroke + '" stroke-linecap="round" stroke-dasharray="' + (c * value).toFixed(2) + " " + c.toFixed(2) + '"/>' +
    "</svg>" +
    '<div class="donut-label"><strong>' + esc(valid ? pct(value, 0) : "—") + "</strong><span>" + esc(caption) + "</span></div>" +
    "</div>";
};

export const icon = (name) => {
  const paths = {
    overview: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    students: '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 20c.6-3.4 2.7-5.2 5.5-5.2s4.9 1.8 5.5 5.2"/><path d="M16 5.2a3 3 0 0 1 0 5.8"/><path d="M17.6 14.9c2 .5 3.3 2.1 3.8 4.6"/>',
    cases: '<path d="M4 7.5A2.5 2.5 0 0 1 6.5 5H10l1.7 2H18a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2H6.5A2.5 2.5 0 0 1 4 17z"/><path d="M8 12h8M8 15.5h5"/>',
    content: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v18H6.5A2.5 2.5 0 0 1 4 18.5z"/><path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v18h4.5a2.5 2.5 0 0 0 2.5-2.5z"/><path d="M11 3v18"/>',
    quality: '<path d="M12 3l7 3v5.3c0 4.3-2.6 7.5-7 9.7-4.4-2.2-7-5.4-7-9.7V6z"/><path d="M8.6 12.1l2.2 2.2 4.6-4.7"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.2"/><path d="M15.2 15.2L21 21"/>',
    refresh: '<path d="M20 11a8 8 0 1 0-2.1 6.4"/><path d="M20 4v7h-7"/>',
    play: '<path d="M8 5.5v13l10-6.5z"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    alert: '<path d="M12 3l9.5 17H2.5z"/><path d="M12 9v4.5"/><circle cx="12" cy="17" r=".8" fill="currentColor" stroke="none"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><circle cx="12" cy="7.6" r=".9" fill="currentColor" stroke="none"/>',
    print: '<path d="M7 9V4h10v5"/><rect x="4" y="9" width="16" height="7" rx="2"/><path d="M7 14h10v6H7z"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5.2l3.2 2"/>',
    arrow: '<path d="M5 12h14M14 7l5 5-5 5"/>',
    chevron: '<path d="M9 6l6 6-6 6"/>',
    link: '<path d="M10 13.5a4 4 0 0 0 5.7 0l2.6-2.6a4 4 0 0 0-5.7-5.7L11.4 6.4"/><path d="M14 10.5a4 4 0 0 0-5.7 0l-2.6 2.6a4 4 0 0 0 5.7 5.7l1.2-1.2"/>',
    book: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16.5H6.5A2.5 2.5 0 0 0 4 22z"/><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>',
    target: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/>',
    upload: '<path d="M12 16V4"/><path d="M7 9l5-5 5 5"/><path d="M4 16v3h16v-3"/>',
    download: '<path d="M12 4v12"/><path d="M7 11l5 5 5-5"/><path d="M4 16v3h16v-3"/>',
    database: '<ellipse cx="12" cy="5.5" rx="7.5" ry="2.8"/><path d="M4.5 5.5v13c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8v-13"/><path d="M4.5 12c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    minus: '<path d="M5 12h14"/>',
    expand: '<path d="M8 4H4v4M16 4h4v4M20 16v4h-4M4 16v4h4"/>',
    collapse: '<path d="M4 8h4V4M20 8h-4V4M20 16h-4v4M4 16h4v4"/>',
    network: '<circle cx="6" cy="6" r="2.2"/><circle cx="18" cy="7" r="2.2"/><circle cx="12" cy="18" r="2.2"/><path d="M8 7l7.8-.7M7.2 8l3.6 8M16.6 9l-3.4 7.2"/>',
    fit: '<path d="M9 4H4v5M15 4h5v5M20 15v5h-5M4 15v5h5"/><rect x="8" y="8" width="8" height="8" rx="1.5"/>',
    chat: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H9l-5 4z"/><path d="M8 8h8M8 11.5h5"/>',
    send: '<path d="M4 11.5L20 4l-7.5 16-2.2-6.3z"/><path d="M10.3 13.7L20 4"/>',
    shield: '<path d="M12 3l7 3v5.3c0 4.3-2.6 7.5-7 9.7-4.4-2.2-7-5.4-7-9.7V6z"/><path d="M9 12l2 2 4-4.5"/>',
    copy: '<rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6.5A2.5 2.5 0 0 0 13.5 4H6.5A2.5 2.5 0 0 0 4 6.5v7A2.5 2.5 0 0 0 6.5 16H8"/>',
  };
  return '<svg class="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' +
    (paths[name] || paths.info) + "</svg>";
};

export const hydrateIcons = (root = document) => {
  root.querySelectorAll("[data-icon]").forEach((node) => {
    if (node.dataset.iconDone) return;
    node.innerHTML = icon(node.dataset.icon);
    node.dataset.iconDone = "1";
  });
};
