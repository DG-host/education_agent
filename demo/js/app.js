/* 工作台入口：快照载入、hash 路由、筛选、抽屉与后台重跑。 */

import { esc, formatDate, hydrateIcons, icon } from "./format.js";
import { loadSnapshot, state } from "./data.js";
import {
  caseDetailPage, casesPage, contentPage, notFoundPage, overviewPage,
  qualityPage, studentDetailPage, studentsPage,
  drawerIndicator, drawerMaterial, drawerRecord,
} from "./pages.js";
import { inputPage, mountInputPage } from "./input.js";
import { consultPage, destroyConsultPage, mountConsultPage } from "./consult.js";
import { destroyKnowledgeGraph, mountKnowledgeGraph } from "./graph.js";

const DEMO = typeof window !== "undefined" && window.DSH_DEMO === true;

const main = document.getElementById("main");
const nav = document.getElementById("nav");
const globalSearch = document.getElementById("globalSearch");
const runBtn = document.getElementById("runBtn");
const refreshBtn = document.getElementById("refreshBtn");
const toastEl = document.getElementById("toast");
const drawer = document.getElementById("drawer");
const drawerTitle = document.getElementById("drawerTitle");
const drawerKicker = document.getElementById("drawerKicker");
const drawerBody = document.getElementById("drawerBody");
const drawerPanel = drawer.querySelector(".drawer-panel");

let toastTimer = null;
let searchTimer = null;
let pollTimer = null;
let drawerReturnFocus = null;

const routeTitles = {
  overview: "总览",
  students: "学生画像",
  cases: "典型案例",
  content: "内容图谱",
  input: "数据录入",
  consult: "教学咨询",
  quality: "数据质量",
};

const parseRoute = () => {
  const raw = String(location.hash || "").replace(/^#\/?/, "").replace(/\/+$/, "");
  if (!raw) return { name: "overview", id: "" };
  const parts = raw.split("/").filter(Boolean).map((x) => {
    try { return decodeURIComponent(x); } catch { return x; }
  });
  return { name: parts[0] || "overview", id: parts[1] || "" };
};

const currentRoute = () => parseRoute();

const toast = (message, tone = "", ms = 3200) => {
  if (!toastEl) return;
  toastEl.textContent = message;
  toastEl.className = "toast" + (tone ? " " + tone : "");
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.hidden = true; }, ms);
};

const setRunUi = () => {
  if (!runBtn) return;
  if (DEMO) { runBtn.hidden = true; return; }
  const running = state.run.state === "running";
  const readOnly = state.meta && state.meta.run_enabled === false;
  runBtn.disabled = running || readOnly;
  runBtn.title = readOnly ? (state.meta.run_disabled_reason || "当前版本为只读快照") : "";
  const label = running ? "分析中…" : (readOnly ? "只读快照" : "重新分析");
  runBtn.innerHTML = icon(running ? "refresh" : "play") + "<span>" + label + "</span>";
};

const updateChrome = (route) => {
  const meta = state.meta || {};
  const snapshotText = meta.generated_at ? formatDate(meta.generated_at) : "快照未载入";
  const topbarSnapshot = document.getElementById("topbarSnapshot");
  if (topbarSnapshot) topbarSnapshot.textContent = snapshotText;
  const side = document.getElementById("sidebarSnapshot");
  if (side) side.textContent = snapshotText;
  const sideSource = document.getElementById("sidebarSource");
  if (sideSource) sideSource.textContent = (meta.students ?? "—") + " 名学生 · " + (meta.groups ?? "—") + " 个班级";
  const title = routeTitles[route.name] || "教研工作台";
  const topbarTitle = document.getElementById("topbarTitle");
  if (topbarTitle) topbarTitle.textContent = title;
  document.title = title + " · 智慧学伴教研工作台";

  nav.querySelectorAll(".nav-item").forEach((a) => {
    const active = a.dataset.route === route.name;
    a.classList.toggle("active", active);
    if (active) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
};

const renderError = (err) => {
  const details = (err && err.details) || {};
  const missing = Array.isArray(details.missing) ? details.missing : [];
  const hint = DEMO ? "demo/snapshot.json" : (details.hint || "run.cmd all");
  const code = err && err.code ? err.code : "unknown";
  const status = err && err.status ? err.status : "—";
  const intro = DEMO
    ? "演示站点只读 <code>demo/snapshot.json</code>；若文件尚未生成，请先在本机运行 <code>python src/demo_site.py</code>，再重新发布。"
    : "工作台只读 <code>out/</code> 与清洗版 CSV；如果尚未运行流水线，请先执行下面的命令，再刷新。";
  const actions = DEMO
    ? '<button class="btn btn-primary" type="button" data-action="refresh">' + icon("refresh") + "重试</button>"
    : '<button class="btn btn-primary" type="button" data-action="run">' + icon("play") + "运行分析</button>" +
      '<button class="btn" type="button" data-action="refresh">' + icon("refresh") + "重试</button>";
  main.innerHTML = '<div class="error-panel"><div class="card">' +
    '<div class="eyebrow">快照不可用</div><h1>暂时读不到分析快照</h1>' +
    "<p class=\"muted\">" + intro + "</p>" +
    "<pre>" + esc(hint) + "</pre>" +
    (missing.length ? '<div class="callout"><strong>缺失产物</strong><div class="mono small">' + missing.map(esc).join("<br>") + "</div></div>" : "") +
    '<div class="row" style="margin-top:12px">' + actions + "</div>" +
    '<div class="note" style="margin-top:12px">错误码 ' + esc(code) + " · HTTP " + esc(status) + "</div>" +
    "</div></div>";
  main.focus();
};

const renderRoute = ({ scroll = true } = {}) => {
  destroyKnowledgeGraph();
  destroyConsultPage();
  const route = currentRoute();
  updateChrome(route);
  setRunUi();
  if (DEMO && (route.name === "input" || route.name === "consult")) {
    main.innerHTML = '<div class="error-panel"><div class="card">' +
      '<div class="eyebrow">公开演示</div><h1>此页需要本地版</h1>' +
      '<p class="muted">公开站点只提供只读分析快照，不连接本地后端，也不会接收任何录入数据或 API Key。数据录入与教学咨询请在本机运行 <code>run_ui.cmd</code>。</p>' +
      '<p class="muted">演示站点仍可查看总览、学生画像、典型案例、内容图谱与数据质量。</p>' +
      '<a class="btn btn-primary" href="#/overview">回到总览</a></div></div>';
    hydrateIcons(main);
    if (scroll) window.scrollTo({ top: 0, behavior: "auto" });
    return;
  }
  if (route.name === "input") {
    main.innerHTML = inputPage();
    hydrateIcons(main);
    mountInputPage();
    if (scroll) window.scrollTo({ top: 0, behavior: "auto" });
    return;
  }
  if (route.name === "consult") {
    main.innerHTML = consultPage();
    hydrateIcons(main);
    mountConsultPage();
    if (scroll) window.scrollTo({ top: 0, behavior: "auto" });
    return;
  }
  if (state.error) {
    renderError(state.error);
    return;
  }
  if (!state.snapshot) return;
  let html = "";
  if (route.name === "overview") html = overviewPage();
  else if (route.name === "students") html = route.id ? studentDetailPage(route.id) : studentsPage();
  else if (route.name === "cases") html = route.id ? caseDetailPage(route.id) : casesPage();
  else if (route.name === "content") html = contentPage();
  else if (route.name === "quality") html = qualityPage();
  else html = notFoundPage("路由 " + route.name + " 不存在");
  main.innerHTML = html;
  hydrateIcons(main);
  if (route.name === "content") mountKnowledgeGraph();
  if (scroll) window.scrollTo({ top: 0, behavior: "auto" });
};

const refresh = async ({ scroll = false } = {}) => {
  const hadSnapshot = Boolean(state.snapshot);
  try {
    await loadSnapshot();
    renderRoute({ scroll: false });
    if (hadSnapshot) toast("快照已刷新", "ok", 1800);
  } catch (err) {
    if (["input", "consult"].includes(currentRoute().name)) renderRoute({ scroll: false });
    else renderError(err);
  }
};

const openDrawer = (kicker, title, body) => {
  drawerReturnFocus = document.activeElement;
  drawerKicker.textContent = kicker;
  drawerTitle.textContent = title;
  drawerBody.innerHTML = body;
  hydrateIcons(drawerBody);
  drawer.hidden = false;
  document.body.style.overflow = "hidden";
  drawerPanel.focus();
};

const closeDrawer = () => {
  drawer.hidden = true;
  document.body.style.overflow = "";
  drawerBody.innerHTML = "";
  if (drawerReturnFocus && typeof drawerReturnFocus.focus === "function") drawerReturnFocus.focus();
  drawerReturnFocus = null;
};

const showRunLog = () => {
  const run = state.run || {};
  const lines = (run.log_tail || []).join("\n") || "（暂无日志）";
  openDrawer("流水线", "运行状态", '<div class="stack">' +
    '<div class="row">' + stateBadge(run.state) + '<span class="mono small">exit=' + esc(run.exit_code ?? "—") + "</span></div>" +
    '<div class="note">开始 ' + esc(formatDate(run.started_at)) + " · 结束 " + esc(formatDate(run.finished_at)) + "</div>" +
    "<pre style=\"white-space:pre-wrap;background:#0B4F4A;color:#EAF6F3;padding:12px;border-radius:10px;max-height:52vh;overflow:auto;font-size:11px\">" + esc(lines) + "</pre>" +
    '<div class="note">运行完成后工作台会自动刷新快照。</div></div>');
};

const stateBadge = (s) => {
  const map = {
    idle: ["未运行", "neutral"],
    running: ["运行中", "warn"],
    succeeded: ["已完成", "ok"],
    failed: ["失败", "bad"],
  };
  const [label, tone] = map[s] || [s || "未知", "neutral"];
  return '<span class="badge badge-' + tone + '">' + esc(label) + "</span>";
};

const pollRun = async () => {
  try {
    const res = await fetch("/api/run/status", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    state.run = await res.json();
    setRunUi();
    if (state.run.state === "running") {
      pollTimer = setTimeout(pollRun, 1200);
      return;
    }
    clearTimeout(pollTimer);
    pollTimer = null;
    if (state.run.state === "succeeded") {
      toast("分析完成，正在刷新快照…", "ok", 2200);
      await refresh({ scroll: false });
    } else if (state.run.state === "failed") {
      toast("分析失败，打开日志查看原因", "bad", 4200);
      showRunLog();
    }
  } catch (err) {
    clearTimeout(pollTimer);
    pollTimer = null;
    toast("无法读取运行状态：" + err.message, "bad", 4200);
  }
};

const startRun = async () => {
  if (DEMO) {
    toast("公开演示为只读快照；重新分析请运行本地版。", "", 4200);
    return;
  }
  if (state.run.state === "running") {
    toast("分析正在运行中，请稍候。", "");
    return;
  }
  setRunUi();
  state.run = { ...state.run, state: "running" };
  setRunUi();
  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-DSH-UI": "1" },
      body: "{}",
    });
    const body = await res.json().catch(() => null);
    if (res.status === 409 && body && body.error && body.error.code === "read_only_build") {
      state.run = { ...state.run, state: "idle" };
      setRunUi();
      toast(body.error.message || "当前版本为只读快照。", "", 5200);
      return;
    }
    if (res.status === 409) {
      toast("已有分析在运行，继续等待结果。", "");
      pollRun();
      return;
    }
    if (!res.ok) {
      state.run = { ...state.run, state: "failed" };
      setRunUi();
      toast((body && body.error && body.error.message) || "启动失败（HTTP " + res.status + "）", "bad", 4200);
      return;
    }
    toast("已启动后台分析；完成后自动刷新。", "ok", 2400);
    pollRun();
  } catch (err) {
    state.run = { ...state.run, state: "failed" };
    setRunUi();
    toast("无法启动分析：" + err.message, "bad", 4200);
  }
};

const onSearch = () => {
  const value = globalSearch.value;
  const pos = globalSearch.selectionStart;
  state.search = value;
  const route = currentRoute();
  if (!state.snapshot) return;
  if (route.name !== "students") {
    if (!location.hash.startsWith("#/students")) location.hash = "#/students";
    else renderRoute({ scroll: false });
  } else {
    renderRoute({ scroll: false });
  }
  requestAnimationFrame(() => {
    const input = document.getElementById("globalSearch");
    if (input) {
      input.focus();
      const p = Math.min(pos ?? value.length, input.value.length);
      input.setSelectionRange(p, p);
    }
  });
};

const onSearchKey = (event) => {
  if (event.key === "Enter") {
    const q = globalSearch.value.trim();
    if (!q) return;
    const exact = state.studentById.get(q.toUpperCase());
    if (exact) {
      globalSearch.blur();
      location.hash = "#/students/" + exact.student_id;
    }
  }
};

const handleAction = (action, el) => {
  if (action === "material") openDrawer("材料", el.dataset.id, drawerMaterial(el.dataset.id));
  else if (action === "indicator") openDrawer("指标", el.dataset.id, drawerIndicator(el.dataset.id));
  else if (action === "record") openDrawer("记录", el.dataset.id, drawerRecord(el.dataset.id));
  else if (action === "node") openDrawer("节点", el.dataset.id,
    '<div class="stack"><p>节点 <b class="mono">' + esc(el.dataset.id) + "</b> 的题目集与测验日期见 <code>data/raw/测验节点.csv</code>。</p>" +
    '<div class="callout"><strong>口径</strong>节点覆盖度 = 已观测材料 / 节点可用题目；跨节点题集不同，得分率不可直接排序。</div></div>');
  else if (action === "print") window.print();
  else if (action === "refresh") refresh({ scroll: false });
  else if (action === "run") startRun();
  else if (action === "show-run-log") showRunLog();
  else if (action === "clear-search") {
    state.search = "";
    globalSearch.value = "";
    state.filters = { ...state.filters, group: "all", flag: "all" };
    renderRoute({ scroll: false });
  } else if (action === "copy") {
    const text = el.dataset.copy || "";
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => toast("已复制：" + text, "ok", 1600)).catch(() => toast("复制失败", "bad"));
    } else {
      toast(text, "", 3000);
    }
  }
};

document.addEventListener("click", (event) => {
  const close = event.target.closest("[data-close-drawer]");
  if (close) {
    event.preventDefault();
    closeDrawer();
    return;
  }
  const el = event.target.closest("[data-action]");
  if (el) {
    event.preventDefault();
    handleAction(el.dataset.action, el);
  }
});

document.addEventListener("change", (event) => {
  const select = event.target.closest("[data-filter]");
  if (!select) return;
  const key = select.dataset.filter;
  state.filters = { ...state.filters, [key]: select.value };
  renderRoute({ scroll: false });
});

globalSearch.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(onSearch, 140);
});
globalSearch.addEventListener("keydown", onSearchKey);
runBtn.addEventListener("click", startRun);
refreshBtn.addEventListener("click", () => refresh({ scroll: false }));

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (!drawer.hidden) closeDrawer();
    return;
  }
  if (event.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
    event.preventDefault();
    globalSearch.focus();
  }
});

window.addEventListener("hashchange", () => {
  if (state.snapshot || ["input", "consult"].includes(currentRoute().name)) renderRoute({ scroll: true });
});

const boot = async () => {
  hydrateIcons(document);
  if (DEMO) {
    document.body.classList.add("is-demo");
    const banner = document.getElementById("demoBanner");
    if (banner) banner.hidden = false;
    if (runBtn) runBtn.hidden = true;
    nav.querySelectorAll('[data-route="input"], [data-route="consult"]').forEach((a) => {
      a.hidden = true;
    });
  } else {
    setRunUi();
    try {
      const status = await fetch("/api/run/status", { cache: "no-store" });
      if (status.ok) {
        state.run = await status.json();
        setRunUi();
        if (state.run.state === "running") pollRun();
      }
    } catch {
      /* 运行状态不影响快照阅读 */
    }
  }
  if (!location.hash) history.replaceState(null, "", "#/overview");
  try {
    await loadSnapshot();
    renderRoute({ scroll: false });
  } catch (err) {
    if (["input", "consult"].includes(currentRoute().name)) renderRoute({ scroll: false });
    else renderError(err);
  }
};

boot();
