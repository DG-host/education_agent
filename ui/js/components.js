/* 可复用 HTML 片段。页面模块只负责组合，不直接拼复杂结构。 */

import {
  actionBadge, badge, confidenceBadge, donut, esc, flagBadge, icon, num,
  pct, progress, rateTone, short, statusBadge,
} from "./format.js";
import { getIndicatorMeta, getMaterial, recordRate } from "./data.js";

export const pageHead = ({ kicker = "", title, lede = "", actions = "" }) =>
  '<div class="page-head"><div>' +
  (kicker ? '<div class="eyebrow">' + esc(kicker) + "</div>" : "") +
  "<h1>" + esc(title) + "</h1>" +
  (lede ? '<p class="lede">' + esc(lede) + "</p>" : "") +
  "</div>" + (actions ? '<div class="page-actions">' + actions + "</div>" : "") + "</div>";

export const card = ({ title = "", sub = "", actions = "", body = "", cls = "", flush = false }) =>
  '<section class="card ' + esc(cls) + (flush ? " flush" : "") + '">' +
  (title || actions ? '<div class="card-head"><div>' +
    (title ? "<h2>" + esc(title) + "</h2>" : "") +
    (sub ? "<p>" + esc(sub) + "</p>" : "") +
    "</div>" + (actions || "") + "</div>" : "") +
  body + "</section>";

export const kpi = ({ label, value, unit = "", sub = "", tone = "" }) =>
  '<div class="kpi ' + esc(tone) + '">' +
  '<div class="kpi-label">' + esc(label) + "</div>" +
  '<div class="kpi-value num">' + esc(value) + (unit ? "<small>" + esc(unit) + "</small>" : "") + "</div>" +
  (sub ? '<div class="kpi-sub">' + esc(sub) + "</div>" : "") +
  "</div>";

export const empty = ({ title = "暂无数据", text = "" } = {}) =>
  '<div class="empty"><strong>' + esc(title) + "</strong>" + (text ? "<div>" + esc(text) + "</div>" : "") + "</div>";

export const sectionTitle = (title, hint = "", actions = "") =>
  '<div class="section-title"><h2>' + esc(title) + "</h2>" +
  (actions || (hint ? '<span class="hint">' + esc(hint) + "</span>" : "")) + "</div>";

export const chip = (text, { tone = "", action = "", id = "", extra = "", title = "" } = {}) => {
  const attrs = [];
  if (action) attrs.push('data-action="' + esc(action) + '"');
  if (id) attrs.push('data-id="' + esc(id) + '"');
  if (extra) attrs.push(extra);
  return '<button class="chip chip-button ' + esc(tone) + '" type="button" ' + attrs.join(" ") +
    (title ? ' title="' + esc(title) + '"' : "") + ">" + esc(text) + "</button>";
};

export const materialChip = (id, extra = "") =>
  chip(id, { action: "material", id, extra, title: "查看材料 " + id });

export const indicatorChip = (id, extra = "") =>
  chip(id, { action: "indicator", id, extra, title: "查看指标 " + id });

export const recordChip = (id, extra = "") =>
  chip(id, { action: "record", id, extra, title: "查看记录 " + id });

export const evidenceChips = (refs = [], { studentId = "", limit = 8 } = {}) => {
  const parts = [];
  for (const ref of refs.slice(0, limit)) {
    if (/^DR\d{4}$/.test(ref)) parts.push(recordChip(ref, studentId ? 'data-student="' + esc(studentId) + '"' : ""));
    else if (/^T0[1-3]I[1-9]$/.test(ref)) parts.push(indicatorChip(ref));
    else if (/^N0\d$/.test(ref)) parts.push(chip(ref, { action: "node", id: ref, title: "查看节点说明" }));
    else parts.push(chip(ref));
  }
  if (refs.length > limit) parts.push('<span class="tiny muted">+' + (refs.length - limit) + "</span>");
  return '<div class="evidence-line">' + parts.join("") + "</div>";
};

export const progressRow = (label, rate, right = null) =>
  '<div class="progress-row"><span class="label">' + esc(label) + "</span>" +
  progress(rate) + '<span class="value">' + esc(right ?? pct(rate)) + "</span></div>";

export const studentLink = (id, html = null, cls = "") =>
  '<a class="' + esc(cls) + '" href="#/students/' + esc(id) + '">' + (html ?? esc(id)) + "</a>";

export const caseLink = (id, html = null, cls = "") =>
  '<a class="' + esc(cls) + '" href="#/cases/' + esc(id) + '">' + (html ?? esc(id)) + "</a>";

export const materialLink = (id) =>
  '<button class="chip chip-button" type="button" data-action="material" data-id="' + esc(id) + '">' + esc(id) + "</button>";

export const studentFlags = (flags = []) =>
  flags.length ? '<div class="row">' + flags.map(flagBadge).join("") + "</div>" : '<span class="tiny muted">无特殊标记</span>';

export const table = (headers, rows, { caption = "", className = "", minWidth = "" } = {}) => {
  const head = headers.map((h) => {
    if (typeof h === "string") return "<th>" + esc(h) + "</th>";
    return '<th class="' + esc(h.cls || "") + '">' + esc(h.label) + "</th>";
  }).join("");
  const body = rows.length
    ? rows.map((row) => {
      const cells = (row.cells || row).map((cell) => {
        if (cell && typeof cell === "object" && !Array.isArray(cell)) {
          return '<td class="' + esc(cell.cls || "") + '">' + (cell.html ?? esc(cell.text ?? "")) + "</td>";
        }
        return "<td>" + (cell ?? "") + "</td>";
      }).join("");
      return '<tr class="' + esc(row.cls || "") + '">' + cells + "</tr>";
    }).join("")
    : '<tr><td colspan="' + headers.length + '">' + empty({ title: "没有匹配记录", text: "调整筛选条件后再试。" }) + "</td></tr>";
  return '<div class="table-wrap"><table class="' + esc(className) + '"' +
    (minWidth ? ' style="min-width:' + esc(minWidth) + '"' : "") + ">" +
    (caption ? '<caption class="table-caption">' + esc(caption) + "</caption>" : "") +
    "<thead><tr>" + head + "</tr></thead><tbody>" + body + "</tbody></table></div>";
};

export const recordTable = (records = []) => table(
  ["记录", "材料", "节点", "修订", "评分状态", "得分", "满分", "满分率"],
  records.slice().sort((a, b) => String(a.record_id).localeCompare(String(b.record_id), "zh-CN", { numeric: true }))
    .map((r) => ({
      cells: [
        { html: '<span class="mono">' + esc(r.record_id) + "</span>" },
        { html: materialChip(r.material_id) },
        { html: esc(r.node_id) },
        { html: esc(r.revision ?? "—"), cls: "num" },
        { html: statusBadge(r.status) },
        { html: esc(num(r.score, 1)), cls: "num" },
        { html: esc(num(r.max_score, 1)), cls: "num" },
        { html: '<div class="compare-bar">' + progress(recordRate(r)) + '<span class="num">' + esc(pct(recordRate(r), 1)) + "</span></div>" },
      ],
    })),
  { caption: "记录仅展示评分与节点信息，不展示学生作答原文。" },
);

export const classCard = (row, { gap = null } = {}) => {
  const name = row.group_id;
  return '<div class="card class-card">' +
    '<div class="class-name"><div><div class="eyebrow">模拟班级</div><strong>' + esc(name) + "</strong></div>" +
    badge(row.students + " 名学生", "brand") + "</div>" +
    '<div class="class-metrics">' +
    '<div class="class-metric"><span>平均得分率</span><strong class="num">' + esc(pct(row.score_rate_mean)) + "</strong>" +
    progress(row.score_rate_mean, null, "lg") + "</div>" +
    '<div class="class-metric"><span>平均覆盖度</span><strong class="num">' + esc(pct(row.coverage_mean)) + "</strong>" +
    progress(row.coverage_mean, null, "lg") + "</div>" +
    "</div>" +
    '<div class="gap-note">' + icon("info") + "<span>记录 <b>" + esc(num(row.records)) + "</b> 条；覆盖度=已观测材料 / 节点可用题目。</span></div>" +
    (gap ? '<div class="gap-note">' + icon("target") + "<span>与对照班相差 <b>" + esc(pct(Math.abs(gap.score_rate_gap))) + "</b>；覆盖度相差 " + esc(pct(Math.abs(gap.coverage_gap))) + "。</span></div>" : "") +
    "</div>";
};

export const indicatorMini = (indicator) => {
  const meta = getIndicatorMeta(indicator.indicator_id);
  return '<div class="indicator-row ' + (indicator.rate !== null && indicator.rate < 0.6 ? "weak" : "") + '">' +
    "<div><div class=\"mono small\">" + esc(indicator.indicator_id) + "</div></div>" +
    '<div><div class="ind-name">' + esc(meta ? meta.observation : indicator.indicator_id) + "</div>" +
    '<div class="ind-obs">观测 ' + esc(num(indicator.observed)) + " 条 · 满分 " + esc(num(indicator.correct)) + " 条</div></div>" +
    '<div class="ind-bar">' + progress(indicator.rate) + "</div>" +
    '<div class="ind-rate num">' + esc(pct(indicator.rate)) + "</div>" +
    '<div class="ind-conf">' + confidenceBadge(indicator.confidence) + "</div>" +
    "</div>";
};

export const actionLine = (action) => actionBadge(action);

export const traceStep = (step) =>
  '<div class="trace-step">' +
  '<div class="trace-dot ' + (step.ok ? "" : "bad") + '">' + (step.ok ? icon("check") : icon("alert")) + "</div>" +
  '<div><div class="t-name"><b>' + esc(step.tool) + "</b>" + badge("第 " + step.seq + " 步", "neutral") +
  (step.ok ? badge("通过", "ok") : badge("失败", "bad")) + "</div>" +
  '<div class="t-summary">' + esc(step.summary || "—") + "</div>" +
  (step.evidence && step.evidence.length ? '<div class="trace-evidence">' + step.evidence.map((x) => badge(x, "neutral")).join("") + "</div>" : "") +
  (step.why ? '<div class="t-why">' + esc(step.why) + "</div>" : "") +
  "</div>" +
  '<div class="t-time">' + esc(num(step.elapsed_ms)) + " ms</div>" +
  "</div>";

export const guardItem = (check) =>
  '<div class="guard-item"><div class="gmark">' + (check.status === "pass" ? icon("check") : icon("alert")) + "</div>" +
  "<div><b>" + esc(check.name) + "</b><span>" + esc(check.detail || "") + (check.errors ? " · " + check.errors + " 个错误" : "") + "</span></div>" +
  badge(check.status === "pass" ? "通过" : "未通过", check.status === "pass" ? "ok" : "bad") +
  "</div>";

export const sourceRow = (source) =>
  '<div class="source-row"><span class="mono">' + esc(source.path) + "</span>" +
  '<span class="mono" title="' + esc(source.sha256) + '">' + esc(String(source.sha256 || "").slice(0, 12)) + "… · " + esc(num(source.bytes)) + " B</span></div>";

export const ruleRow = (finding) =>
  '<div class="rule-item"><div class="rule-head"><span class="mono">' + esc(finding.record_id) + "</span>" +
  badge(finding.student_id, "neutral") + badge(finding.material_id, "neutral") + badge(finding.node_id, "neutral") +
  (finding.rule_codes || []).map((c) => badge(c, "bad")).join("") + "</div>" +
  '<div class="rule-body">' + (finding.rules || []).map((r) =>
    "<div><b>" + esc(r.code) + "</b> <span>" + esc(r.field || "") + "</span> " +
    esc(r.expected ?? "") + " → " + esc(r.actual ?? "") + (r.note ? " <span>" + esc(r.note) + "</span>" : "") + "</div>",
  ).join("") + "</div></div>";

export const miniMaterial = (id) => {
  const m = getMaterial(id);
  return m ? esc(m.type) + " · " + esc(m.material_id) : esc(id);
};

export const statusDot = (ok) => '<span class="dot" style="width:7px;height:7px;border-radius:50%;display:inline-block;background:' +
  (ok ? "#15803D" : "#BE123C") + '"></span>';
