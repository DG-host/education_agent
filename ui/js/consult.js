/* 教学咨询页：向 DeepSeek 提问，可选带入学生聚合诊断。 */

import { card, empty, pageHead } from "./components.js";
import { badge, esc, icon } from "./format.js";
import { state } from "./data.js";

const MAX_HISTORY = 12;
let turns = [];
let status = null;
let pending = null;
let mounted = false;

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

const toast = (message, tone = "") => {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = message;
  el.className = "toast" + (tone ? " " + tone : "");
  el.hidden = false;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { el.hidden = true; }, 3400);
};

const studentById = (sid) => (state.students || []).find((s) => s.student_id === sid) || null;

const studentOptions = () => {
  const students = state.students || [];
  if (!students.length) return '<option value="">（快照未载入）</option>';
  return '<option value="">不指定学生</option>' + students.map((s) =>
    '<option value="' + esc(s.student_id) + '">' + esc(s.student_id) + " · " + esc(s.group_id || "") + "</option>"
  ).join("");
};

const statusView = (err = null) => {
  if (err) {
    return '<div class="consult-status-head">' + badge("读取失败", "bad") + "</div>" +
      '<p class="consult-status-text">' + esc(err.message || "无法读取配置状态") + "</p>" +
      '<button class="btn btn-ghost" type="button" data-consult-action="reload-status">' + icon("refresh") + "<span>重新检查</span></button>";
  }
  if (!status) {
    return '<div class="consult-status-head">' + badge("读取中", "neutral") + "</div>" +
      '<p class="consult-status-text">正在检查本机配置…</p>';
  }
  const ready = Boolean(status.configured && status.library_available);
  const source = status.config_source === "env" ? "环境变量" : status.config_source === "file" ? "配置文件" : "未配置";
  return '<div class="consult-status-head">' + badge(ready ? "可咨询" : "未就绪", ready ? "ok" : "warn") +
    '<button class="btn btn-ghost" type="button" data-consult-action="reload-status">' + icon("refresh") + "<span>重新检查</span></button></div>" +
    '<div class="consult-status-grid">' +
      '<div><span>模型</span><b class="mono">' + esc(status.model || "—") + "</b></div>" +
      "<div><span>Key 来源</span><b>" + esc(source) + "</b></div>" +
      '<div><span>接口地址</span><b class="mono">' + esc(status.base_url || "—") + "</b></div>" +
      "<div><span>超时</span><b>" + esc(status.timeout_seconds || "—") + " 秒</b></div>" +
    "</div>" +
    '<p class="consult-status-text">' + esc(status.message || "") + "</p>" +
    '<div class="consult-config-path"><span>配置文件</span><code>' + esc(status.config_path || "—") + "</code></div>" +
    '<div class="callout small">API Key 只在本机服务端读取：可设置环境变量 <code>DEEPSEEK_API_KEY</code>，或编辑上面的配置文件。不会写入浏览器、仓库或回答。</div>';
};

const renderStatus = (err = null) => {
  const el = document.getElementById("consultStatus");
  if (el) el.innerHTML = statusView(err);
  updateSendState();
};

const contextView = () => {
  const include = document.getElementById("consultInclude");
  const select = document.getElementById("consultStudent");
  const box = document.getElementById("consultContext");
  if (!box) return;
  if (!include || !include.checked) {
    box.innerHTML = '<div class="consult-context-line">' + icon("info") + "<span>默认不发送任何学生数据。只有勾选后才带入该生的聚合诊断。</span></div>";
    if (select) select.disabled = true;
    return;
  }
  if (select) select.disabled = false;
  const sid = select ? select.value : "";
  if (!sid) {
    box.innerHTML = '<div class="consult-context-line">' + icon("alert") + "<span>请选择一个学生，或取消勾选。</span></div>";
    return;
  }
  const student = studentById(sid);
  if (!student) {
    box.innerHTML = '<div class="consult-context-line">' + icon("alert") + "<span>快照中没有该学生。</span></div>";
    return;
  }
  const observed = student.observed || {};
  const overall = (student.score_rate || {}).overall;
  const weak = (student.by_indicator || []).filter((i) => i.rate !== null && i.rate < 0.6).length;
  box.innerHTML =
    '<div class="consult-context-line">' + icon("shield") + "<span>只发送聚合诊断，不含作答原文、参考答案或个人信息。</span></div>" +
    '<div class="consult-context-facts">' +
      '<div><span>学生</span><b class="mono">' + esc(student.student_id) + "</b></div>" +
      '<div><span>班级</span><b>' + esc(student.group_id || "—") + "</b></div>" +
      '<div><span>记录 / 已评</span><b>' + esc(observed.records ?? "—") + " / " + esc(observed.scored ?? "—") + "</b></div>" +
      '<div><span>整体得分率</span><b>' + esc(overall === null || overall === undefined ? "—" : (Number(overall) * 100).toFixed(1) + "%") + "</b></div>" +
      '<div><span>低分指标</span><b>' + esc(weak) + " 个</b></div>" +
    "</div>";
};

const updateSendState = () => {
  const btn = document.getElementById("consultSend");
  const text = document.getElementById("consultQuestion");
  const count = document.getElementById("consultCount");
  if (count && text) count.textContent = text.value.length + " / 4000";
  if (!btn) return;
  const ready = Boolean(status && status.configured && status.library_available);
  btn.disabled = Boolean(pending) || !ready || !text || !text.value.trim();
  btn.innerHTML = icon(pending ? "refresh" : "send") + "<span>" + (pending ? "请求中…" : "发送") + "</span>";
};

const errorView = (err) => {
  const code = (err.body && err.body.error && err.body.error.code) || "";
  const details = (err.body && err.body.error && err.body.error.details) || {};
  const map = {
    consult_unconfigured: "还没有配置 DeepSeek API Key。请设置环境变量或编辑配置文件后点“重新检查”。",
    consult_unavailable: "当前 Python 环境没有 openai 库；请先安装 openai。",
    consult_auth_failed: "API Key 无效或没有权限，请检查 Key 是否填对。",
    consult_rate_limited: "请求过于频繁，请稍后再试。",
    consult_timeout: "模型响应超时，请稍后重试。",
    consult_unreachable: "无法连接模型服务，请检查网络与接口地址。",
    consult_busy: "上一个咨询还在进行，请稍后再试。",
    student_required: "勾选“带入该生诊断”后必须选择学生。",
    invalid_student: "学生编号无效或不在当前诊断中。",
  };
  const hint = map[code] || err.message || "请求失败，请稍后重试。";
  return '<div class="callout bad small"><strong>咨询未完成</strong><div>' + esc(hint) + "</div>" +
    (code ? '<div class="mono tiny">' + esc(code) + (err.status ? " · HTTP " + esc(err.status) : "") + "</div>" : "") +
    (details.config_path ? '<div class="mono tiny">配置：' + esc(details.config_path) + "</div>" : "") +
    "</div>";
};

const renderError = (err) => {
  const el = document.getElementById("consultError");
  if (!el) return;
  el.innerHTML = err ? errorView(err) : "";
};

const renderThread = () => {
  const el = document.getElementById("consultThread");
  if (!el) return;
  if (!turns.length) {
    el.innerHTML = empty({ title: "还没有对话", text: "可以先问一个教学问题，例如“这名学生下一步先补什么？”" });
    return;
  }
  el.innerHTML = turns.map((turn, index) => {
    const isUser = turn.role === "user";
    const meta = isUser ? "你" : [turn.model, turn.elapsed_ms ? turn.elapsed_ms + " ms" : "", turn.usage && turn.usage.total_tokens ? turn.usage.total_tokens + " tokens" : ""].filter(Boolean).join(" · ");
    return '<article class="consult-turn ' + (isUser ? "is-user" : "is-assistant") + '">' +
      '<div class="consult-role">' + (isUser ? "提问" : "回答") + '<span>' + esc(meta) + "</span></div>" +
      '<div class="consult-bubble">' + esc(turn.content) + "</div>" +
      (isUser ? "" : '<div class="consult-turn-foot"><button class="btn btn-ghost btn-xs" type="button" data-consult-action="copy" data-index="' + index + '">' + icon("copy") + "<span>复制回答</span></button></div>") +
      "</article>";
  }).join("");
  el.scrollTop = el.scrollHeight;
};

const historyForRequest = () => turns.slice(-MAX_HISTORY).map((turn) => ({ role: turn.role, content: turn.content }));

const loadStatus = async () => {
  try {
    status = await api("/api/consult/status");
    if (!mounted) return;
    renderStatus();
    contextView();
  } catch (err) {
    status = null;
    if (mounted) renderStatus(err);
  }
};

const sendQuestion = async () => {
  if (pending) return;
  const text = document.getElementById("consultQuestion");
  const includeEl = document.getElementById("consultInclude");
  const select = document.getElementById("consultStudent");
  if (!text) return;
  const question = text.value.trim();
  if (!question) return;
  const include = Boolean(includeEl && includeEl.checked);
  const studentId = include && select ? select.value : "";
  if (include && !studentId) {
    toast("请先选择学生，或取消勾选", "bad");
    return;
  }
  renderError(null);
  pending = new AbortController();
  updateSendState();
  const body = { question, history: historyForRequest(), include_diagnosis: include };
  if (studentId) body.student_id = studentId;
  try {
    const result = await api("/api/consult", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: pending.signal,
    });
    turns.push({ role: "user", content: question });
    turns.push({
      role: "assistant",
      content: result.reply,
      model: result.model,
      elapsed_ms: result.elapsed_ms,
      usage: result.usage,
      context: result.context,
    });
    if (turns.length > MAX_HISTORY) turns = turns.slice(-MAX_HISTORY);
    text.value = "";
    renderThread();
    updateSendState();
  } catch (err) {
    if (err.name !== "AbortError") renderError(err);
  } finally {
    pending = null;
    updateSendState();
  }
};

const clearThread = () => {
  turns = [];
  renderThread();
  renderError(null);
  updateSendState();
};

const copyReply = (index) => {
  const turn = turns[index];
  if (!turn || !turn.content) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(turn.content).then(() => toast("已复制回答", "ok")).catch(() => toast("复制失败", "bad"));
  } else {
    toast(turn.content, "", 4000);
  }
};

const onRootClick = (event) => {
  const el = event.target.closest("[data-consult-action]");
  if (!el) return;
  const action = el.dataset.consultAction;
  if (action === "reload-status") loadStatus();
  else if (action === "clear") clearThread();
  else if (action === "copy") copyReply(Number(el.dataset.index));
  else if (action === "prompt") {
    const text = document.getElementById("consultQuestion");
    if (text) {
      text.value = el.dataset.prompt || "";
      text.focus();
      updateSendState();
    }
  }
};

export const consultPage = () => {
  const actions = '<button class="btn btn-ghost" type="button" data-consult-action="clear">' + icon("refresh") + "<span>清空对话</span></button>";
  return pageHead({
    kicker: "教学咨询 · DeepSeek 可选",
    title: "教学咨询",
    lede: "以初中数学教师/教研员的视角提问。回答结合课程内容与可选的学生聚合诊断，给出判断依据、教学动作、材料或题目、观察点与调整条件。",
    actions,
  }) +
  '<div id="consultRoot" class="consult-layout grid grid-main">' +
    '<div class="stack">' +
      card({
        title: "提问",
        sub: "按 Ctrl+Enter 发送；回答由模型生成，请教师复核后使用。",
        body:
          '<form id="consultForm" class="consult-form">' +
            '<textarea id="consultQuestion" class="consult-editor" maxlength="4000" spellcheck="false" ' +
              'placeholder="例如：这名学生下一步先补什么？请给出两节课内的安排和观察点。"></textarea>' +
            '<div class="consult-toolbar">' +
              '<span class="consult-count" id="consultCount">0 / 4000</span>' +
              '<button class="btn btn-primary" type="submit" id="consultSend" disabled>' + icon("send") + "<span>发送</span></button>" +
            "</div>" +
            '<div class="consult-chips">' +
              '<button class="chip chip-button" type="button" data-consult-action="prompt" data-prompt="如何给这名学生安排下一节课？请说明先补什么、用什么材料、怎么观察。">下一节课怎么排</button>' +
              '<button class="chip chip-button" type="button" data-consult-action="prompt" data-prompt="这个指标为什么是共性弱项？请结合统计说明，并给出课堂层面的调整。">共性弱项怎么讲</button>' +
              '<button class="chip chip-button" type="button" data-consult-action="prompt" data-prompt="这份建议对学生是否太难或太容易？请给出降阶和加难两种调整。">建议难度怎么调</button>' +
              '<button class="chip chip-button" type="button" data-consult-action="prompt" data-prompt="如果证据不足，我应该补充哪些观察或练习？请给出可执行的记录方式。">证据不足怎么办</button>' +
            "</div>" +
          "</form>" +
          '<div id="consultError" class="consult-error" aria-live="polite"></div>',
      }) +
      card({
        title: "对话",
        sub: "对话只保存在当前浏览器内存；刷新或离开页面后不保留。",
        body: '<div id="consultThread" class="consult-thread" aria-live="polite">' +
          empty({ title: "还没有对话", text: "可以先问一个教学问题，例如“这名学生下一步先补什么？”" }) + "</div>",
      }) +
    "</div>" +
    '<div class="grid-side">' +
      card({ title: "模型状态", sub: "Key 只在本机服务端读取", body: '<div id="consultStatus" class="consult-status">' + statusView() + "</div>" }) +
      card({
        title: "学生上下文",
        sub: "默认不发送学生数据；勾选后只发送聚合诊断",
        body:
          '<div class="consult-field"><label for="consultStudent">学生</label>' +
            '<select id="consultStudent" class="select" disabled>' + studentOptions() + "</select></div>" +
          '<label class="consult-check"><input id="consultInclude" type="checkbox"> 带入该生诊断</label>' +
          '<div id="consultContext" class="consult-context">' +
            '<div class="consult-context-line">' + icon("info") + "<span>默认不发送任何学生数据。只有勾选后才带入该生的聚合诊断。</span></div>" +
          "</div>" +
          '<div class="callout small">发送字段仅限：学生编号、班级、记录数/已评数、覆盖度、指标观测数与得分率、标记、已有建议摘要。不含作答原文、评分点、参考答案或个人信息。</div>',
      }) +
      card({
        title: "使用边界",
        sub: "建议供教师复核，不替代教师决策",
        body:
          '<ul class="consult-rules">' +
            "<li>模型以初中数学教师/教研员角色回答，重点给教学动作与观察点。</li>" +
            "<li>观测数 &lt; 5 或无已评记录时必须说明低置信，不把缺记录当作未掌握。</li>" +
            "<li>不生成学生可直接照抄的完整答案；不输出参考答案原文。</li>" +
            "<li>不保存对话；不把 Key 写入浏览器或仓库。</li>" +
          "</ul>",
      }) +
    "</div>" +
  "</div>";
};

export const mountConsultPage = () => {
  mounted = true;
  const root = document.getElementById("consultRoot");
  const form = document.getElementById("consultForm");
  const text = document.getElementById("consultQuestion");
  const include = document.getElementById("consultInclude");
  const select = document.getElementById("consultStudent");
  if (root) root.addEventListener("click", onRootClick);
  if (form) form.addEventListener("submit", (event) => { event.preventDefault(); sendQuestion(); });
  if (text) {
    text.addEventListener("input", updateSendState);
    text.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        sendQuestion();
      }
    });
  }
  if (include) include.addEventListener("change", contextView);
  if (select) select.addEventListener("change", contextView);
  renderThread();
  contextView();
  updateSendState();
  loadStatus();
};

export const destroyConsultPage = () => {
  mounted = false;
  if (pending) {
    pending.abort();
    pending = null;
  }
};
