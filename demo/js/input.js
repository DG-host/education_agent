/* 数据录入页：与作答记录完全同构的 CSV/JSON 校验与保存。 */

import { card, empty, kpi, pageHead, table } from "./components.js";
import { esc, short } from "./format.js";

const COLUMNS = [
  "记录编号", "学生编号", "材料编号", "主题编号", "节点编号", "作答事件编号",
  "修订版本", "模拟提交时间", "评分状态", "得分", "满分", "学生最终作答", "解答过程", "评分点得分",
];

const api = async (path, options = {}) => {
  const headers = new Headers(options.headers || {});
  headers.set("X-DSH-UI", "1");
  const res = await fetch(path, { ...options, headers, cache: "no-store" });
  const text = await res.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = null; }
  if (!res.ok) {
    const err = new Error((body && body.error && body.error.message) || ("HTTP " + res.status));
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
};

const downloadBlob = (blob, filename) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
};

const toast = (message, tone = "") => {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = message;
  el.className = "toast" + (tone ? " " + tone : "");
  el.hidden = false;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { el.hidden = true; }, 3400);
};

const issueList = (items, title, tone) => {
  if (!items || !items.length) return "";
  const shown = items.slice(0, 60);
  const rows = shown.map((item) => {
    const where = [];
    if (item.row) where.push("第 " + item.row + " 行");
    if (item.field) where.push(item.field);
    return '<li class="issue-item ' + tone + '">' +
      '<span class="issue-where">' + esc(where.join(" · ") || "整体") + "</span>" +
      '<span class="issue-msg">' + esc(item.message || item.code || "") + "</span>" +
      '<span class="mono tiny">' + esc(item.code || "") + "</span></li>";
  }).join("");
  return '<div class="issue-block"><div class="issue-head"><strong>' + esc(title) + "</strong>" +
    '<span class="badge badge-' + (tone === "bad" ? "bad" : "warn") + '">' + items.length + "</span>" +
    (items.length > shown.length ? '<span class="tiny muted">仅列出前 ' + shown.length + " 条</span>" : "") +
    '</div><ul class="issue-list">' + rows + "</ul></div>";
};

const previewTable = (rows) => {
  if (!rows || !rows.length) return empty({ title: "暂无预览", text: "校验或载入后可查看前 10 行。" });
  const body = rows.slice(0, 10).map((row) =>
    COLUMNS.map((col) => ({ text: short(row[col], 48) }))
  );
  return table(COLUMNS, body, { className: "table-input-preview", minWidth: "1500px" });
};

export const inputPage = () => {
  const actions =
    '<button class="btn btn-ghost" type="button" data-input-action="template">' +
    '<span data-icon="download" aria-hidden="true"></span><span>下载表头模板</span></button>' +
    '<button class="btn btn-ghost" type="button" data-input-action="export">' +
    '<span data-icon="upload" aria-hidden="true"></span><span>导出当前副本</span></button>';

  return pageHead({
    kicker: "输入接口 · 与作答记录同构",
    title: "数据录入",
    lede: "接收与 data/raw/作答记录.csv 完全相同的 14 列 CSV，或同字段 JSON。只写独立录入副本，不改原始赛题数据，也不污染 out/ 分析产物。",
    actions,
  }) +
  '<div class="grid grid-main">' +
    '<div class="stack">' +
      card({
        title: "1. 粘贴或上传整表",
        sub: "表头必须 14 列且顺序一致；支持多行引号字段。保存后写 UTF-8 BOM + CRLF。",
        body:
          '<div class="input-toolbar">' +
            '<label class="btn btn-ghost input-file" for="inputFile">' +
              '<span data-icon="upload" aria-hidden="true"></span><span>选择 CSV 文件</span>' +
              '<input id="inputFile" type="file" accept=".csv,text/csv" hidden>' +
            "</label>" +
            '<button class="btn btn-ghost" type="button" data-input-action="load">载入当前副本</button>' +
            '<button class="btn btn-ghost" type="button" data-input-action="clear">清空</button>' +
            '<span class="input-count" id="inputCount">0 字符</span>' +
          "</div>" +
          '<textarea id="inputText" class="input-editor" spellcheck="false" wrap="off" ' +
            'placeholder="把 14 列 CSV 粘贴到这里；第一行必须是表头。也可以点上方选择文件。"></textarea>' +
          '<div class="input-actions">' +
            '<div class="mode-toggle" role="radiogroup" aria-label="写入方式">' +
              '<label><input type="radio" name="inputMode" value="replace" checked> 覆盖当前副本</label>' +
              '<label><input type="radio" name="inputMode" value="append"> 追加到当前副本</label>' +
            "</div>" +
            '<button class="btn" type="button" data-input-action="validate">' +
              '<span data-icon="check" aria-hidden="true"></span><span>只校验</span></button>' +
            '<button class="btn btn-primary" type="button" data-input-action="save">' +
              '<span data-icon="database" aria-hidden="true"></span><span>校验并保存</span></button>' +
          "</div>" +
          '<div class="callout small">校验分两级：<b>硬错误</b>阻断保存（表头、编号、外键、状态、评分点语法、重复记录等）；<b>警告</b>允许保存（主题不符、满分不符、评分点合计与得分不符等），交给既有 9 步流水线继续质检与清洗。</div>',
      }) +
      card({
        title: "2. 校验结果",
        sub: "错误必须逐条修正；警告不阻断保存，但应确认是否已知。",
        body: '<div id="inputResult">' + empty({ title: "尚未校验", text: "粘贴数据后点“只校验”或“校验并保存”。" }) + "</div>",
      }) +
      card({
        title: "前 10 行预览",
        sub: "只用于核对列与内容；完整数据以保存后的录入副本为准。",
        body: '<div id="inputPreview">' + empty({ title: "暂无预览", text: "校验或载入后可查看前 10 行。" }) + "</div>",
        cls: "input-preview-card",
      }) +
    "</div>" +
    '<div class="stack">' +
      card({
        title: "当前录入副本",
        sub: "独立于 data/raw/；每次保存前会备份旧文件到 _history/。",
        body: '<div id="inputCurrent">' + empty({ title: "正在读取…", text: "当前副本状态" }) + "</div>",
      }) +
      card({
        title: "接口",
        sub: "均要求本机访问与 X-DSH-UI: 1；请求体上限 8MB、10000 行。",
        body:
          '<div class="api-list mono small">' +
            '<div><span class="badge badge-neutral">GET</span> <code>/api/records</code><span>读取当前副本</span></div>' +
            '<div><span class="badge badge-neutral">GET</span> <code>/api/records/template</code><span>下载 14 列表头</span></div>' +
            '<div><span class="badge badge-neutral">GET</span> <code>/api/records/export</code><span>导出当前副本</span></div>' +
            '<div><span class="badge badge-ok">POST</span> <code>/api/records/validate</code><span>校验，不落盘</span></div>' +
            '<div><span class="badge badge-ok">POST</span> <code>/api/records?mode=replace|append</code><span>校验并保存</span></div>' +
          "</div>" +
          '<div class="note small">Content-Type 用 <code>text/csv; charset=utf-8</code> 或 <code>application/json</code>。JSON 形状：<code>{"rows":[{...14 列...}],"mode":"replace"}</code>。</div>',
      }) +
    "</div>" +
  "</div>";
};

const renderCurrent = (current) => {
  const box = document.getElementById("inputCurrent");
  if (!box) return;
  if (!current || !current.exists) {
    box.innerHTML = empty({ title: "尚未保存录入副本", text: "粘贴整表并通过校验后保存，这里会显示行数、学生数与哈希。" }) +
      '<div class="note small">默认路径：<span class="mono">' + esc(current && current.path || "data/input/作答记录_录入.csv") + "</span></div>";
    return;
  }
  const stats = current.stats || {};
  const meta = current.meta || {};
  box.innerHTML =
    '<div class="kpi-grid kpi-grid-2">' +
      kpi({ label: "记录行", value: String(stats.rows ?? "—"), sub: "唯一事件 " + String(stats.unique_events ?? "—") }) +
      kpi({ label: "学生", value: String(stats.students ?? "—"), sub: "班级 " + String(stats.groups ?? "—") }) +
    "</div>" +
    '<div class="input-meta small">' +
      '<div><span class="muted">路径</span> <span class="mono">' + esc(current.path) + "</span></div>" +
      '<div><span class="muted">保存时间</span> ' + esc(meta.saved_at || "—") + "</div>" +
      '<div><span class="muted">SHA256</span> <span class="mono" title="' + esc(meta.sha256 || "") + '">' +
        esc(short(meta.sha256 || "—", 24)) + "</span></div>" +
    "</div>" +
    '<div class="row" style="margin-top:10px"><button class="btn btn-sm" type="button" data-input-action="load">载入编辑器</button>' +
    '<button class="btn btn-sm" type="button" data-input-action="export">导出 CSV</button></div>';
};

const renderResult = (data) => {
  const box = document.getElementById("inputResult");
  const preview = document.getElementById("inputPreview");
  if (!box) return;
  const errors = (data && data.errors) || [];
  const warnings = (data && data.warnings) || [];
  const stats = (data && data.stats) || {};
  const qc = (data && data.qc) || {};
  const ok = data && data.ok && !errors.length;
  const head = '<div class="input-result-head">' +
    (ok ? '<span class="badge badge-ok">通过</span>' : '<span class="badge badge-bad">未通过</span>') +
    '<span class="mono small">' + String(stats.rows ?? data.rows ?? 0) + " 行</span>" +
    '<span class="mono small">' + String(stats.students ?? 0) + " 名学生</span>" +
    '<span class="mono small">' + String(stats.unique_events ?? 0) + " 个事件</span>" +
    '<span class="tiny muted">错误 ' + errors.length + " · 警告 " + warnings.length + "</span></div>";
  const qcLine = qc && !qc.error
    ? '<div class="note small">质检预览：异常记录 <b>' + esc(qc.anomaly_records ?? "—") + "</b>；" +
      "规则命中 " + (qc.rule_hits ? Object.entries(qc.rule_hits).filter(([, n]) => n).map(([k, n]) => esc(k) + "=" + n).join("、") || "无" : "—") + "</div>"
    : (qc && qc.error ? '<div class="note small">质检预览不可用：' + esc(qc.error) + "</div>" : "");
  box.innerHTML = head + qcLine +
    issueList(errors, "硬错误（阻断保存）", "bad") +
    issueList(warnings, "警告（可保存）", "warn") +
    (ok ? '<div class="callout small">校验通过。' + (data.saved ? "已写入录入副本。" : "可以继续保存。") + "</div>" : "");
  if (preview) preview.innerHTML = previewTable(data.preview || []);
};

const textarea = () => document.getElementById("inputText");

const setBusy = (busy) => {
  document.querySelectorAll("[data-input-action]").forEach((btn) => {
    if (["validate", "save", "load", "template", "export"].includes(btn.dataset.inputAction)) btn.disabled = busy;
  });
};

const loadCurrent = async () => {
  try {
    const current = await api("/api/records");
    renderCurrent(current);
    return current;
  } catch (err) {
    const box = document.getElementById("inputCurrent");
    if (box) box.innerHTML = '<div class="callout bad small">读取失败：' + esc(err.message) + "</div>";
    return null;
  }
};

const fillFromExport = async () => {
  const res = await fetch("/api/records/export", { headers: { "X-DSH-UI": "1" }, cache: "no-store" });
  if (!res.ok) {
    let message = "HTTP " + res.status;
    try { const body = await res.json(); message = (body.error && body.error.message) || message; } catch { /* ignore */ }
    throw new Error(message);
  }
  const text = await res.text();
  return text.replace(/^﻿/, "");
};

const updateCount = () => {
  const el = document.getElementById("inputCount");
  if (el) el.textContent = (textarea()?.value.length || 0).toLocaleString("zh-CN") + " 字符";
};

const runValidate = async () => {
  const text = textarea()?.value || "";
  if (!text.trim()) { toast("先粘贴或载入 CSV 数据", ""); return; }
  setBusy(true);
  try {
    const data = await api("/api/records/validate", {
      method: "POST",
      headers: { "Content-Type": "text/csv; charset=utf-8" },
      body: text,
    });
    renderResult(data);
    toast("校验通过", "ok", 2000);
  } catch (err) {
    const detail = (err.body && err.body.error && err.body.error.details) || {};
    renderResult({ ok: false, errors: detail.errors || [], warnings: detail.warnings || [], stats: detail.stats || {}, preview: [] });
    toast("校验未通过：" + err.message, "bad", 4200);
  } finally {
    setBusy(false);
  }
};

const runSave = async () => {
  const text = textarea()?.value || "";
  if (!text.trim()) { toast("先粘贴或载入 CSV 数据", ""); return; }
  const modeEl = document.querySelector('input[name="inputMode"]:checked');
  const mode = modeEl ? modeEl.value : "replace";
  if (mode === "replace" && !window.confirm("覆盖当前录入副本？旧文件会自动备份到 _history/。")) return;
  setBusy(true);
  try {
    const data = await api("/api/records?mode=" + encodeURIComponent(mode), {
      method: "POST",
      headers: { "Content-Type": "text/csv; charset=utf-8" },
      body: text,
    });
    renderResult({ ok: true, rows: data.rows, stats: data.stats, warnings: data.warnings || [], qc: data.qc, preview: [], saved: true });
    toast("已保存 " + data.rows + " 行到录入副本", "ok", 3000);
    await loadCurrent();
  } catch (err) {
    const detail = (err.body && err.body.error && err.body.error.details) || {};
    renderResult({ ok: false, errors: detail.errors || [], warnings: detail.warnings || [], stats: detail.stats || {}, preview: [] });
    toast("保存失败：" + err.message, "bad", 4200);
  } finally {
    setBusy(false);
  }
};

const runTemplate = async () => {
  setBusy(true);
  try {
    const res = await fetch("/api/records/template", { headers: { "X-DSH-UI": "1" }, cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    downloadBlob(await res.blob(), "作答记录_模板.csv");
    toast("模板已下载", "ok", 2000);
  } catch (err) {
    toast("下载失败：" + err.message, "bad", 3800);
  } finally { setBusy(false); }
};

const runExport = async () => {
  setBusy(true);
  try {
    const res = await fetch("/api/records/export", { headers: { "X-DSH-UI": "1" }, cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    downloadBlob(await res.blob(), "作答记录_录入.csv");
    toast("当前副本已导出", "ok", 2000);
  } catch (err) {
    toast("导出失败：" + err.message, "bad", 3800);
  } finally { setBusy(false); }
};

const runLoad = async () => {
  setBusy(true);
  try {
    const text = await fillFromExport();
    const editor = textarea();
    if (editor) { editor.value = text; updateCount(); }
    toast("已载入当前副本", "ok", 2200);
  } catch (err) {
    toast("载入失败：" + err.message, "bad", 4200);
  } finally { setBusy(false); }
};

const clearEditor = () => {
  const editor = textarea();
  if (editor) { editor.value = ""; updateCount(); editor.focus(); }
};

const onAction = (action) => {
  if (action === "validate") runValidate();
  else if (action === "save") runSave();
  else if (action === "template") runTemplate();
  else if (action === "export") runExport();
  else if (action === "load") runLoad();
  else if (action === "clear") clearEditor();
};

document.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-input-action]");
  if (!btn) return;
  event.preventDefault();
  onAction(btn.dataset.inputAction);
});

document.addEventListener("change", (event) => {
  if (event.target.id !== "inputFile") return;
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    const editor = textarea();
    if (editor) {
      editor.value = String(reader.result || "").replace(/^﻿/, "");
      updateCount();
    }
    toast("已读取 " + file.name, "ok", 2200);
  };
  reader.onerror = () => toast("读取文件失败", "bad", 3200);
  reader.readAsText(file, "utf-8");
});

document.addEventListener("input", (event) => {
  if (event.target.id === "inputText") updateCount();
});

export const mountInputPage = () => {
  const editor = textarea();
  if (!editor) return;
  updateCount();
  loadCurrent();
};
