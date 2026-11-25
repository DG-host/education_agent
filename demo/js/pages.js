/* 五个页面的 HTML 组合。 */

import {
  actionBadge, badge, confidenceBadge, donut, esc, flagBadge, formatDate, heatClass,
  icon, num, pct, progress, rateTone, short, signedPct, statusBadge,
} from "./format.js";
import {
  allFlags, allGroups, classGapInfo, classIndicatorRow, filteredStudents, filterMaterials,
  getCase, getIndicatorMeta, getMaterial, getRecord, getRecommendation, getStudent,
  indicatorMaterials, indicatorObservation, materialTypes, maxClassIndicatorGap, meanCoverage,
  recordRate, recordsOfMaterial, recordsOfStudent, state, strongIndicators, weakIndicators,
} from "./data.js";
import {
  actionLine, card, caseLink, chip, classCard, empty, evidenceChips, guardItem,
  indicatorChip, kpi, materialChip, materialLink, pageHead, progressRow, recordChip,
  recordTable, sectionTitle, sourceRow, studentFlags, studentLink, table, traceStep,
} from "./components.js";
import { knowledgeGraphCard } from "./graph.js";

const n = (value, digits = 0) => num(value, digits);
const p = (value, digits = 1) => pct(value, digits);
const selected = (value, current) => (value === current ? " selected" : "");

const topicOrder = (topicId) => {
  const idx = state.topics.findIndex((t) => t.topic_id === topicId);
  return idx < 0 ? 99 : idx;
};

const classAvgOf = (student) => state.classStats.find((x) => x.group_id === student.group_id) || null;

const scoreRate = (student) => (student && student.score_rate ? student.score_rate.overall : null);

export const overviewPage = () => {
  const m = state.meta;
  const gap = classGapInfo();
  const maxGap = maxClassIndicatorGap();
  const trace = state.trace;
  const guard = state.guard;
  const qc = state.qc;
  const clean = state.clean;
  const caseCards = state.cases.map((c) => {
    const d = c.diagnosis || {};
    return '<a class="case-mini" href="#/cases/' + esc(c.student_id) + '">' +
      '<div class="row"><span class="case-role">' + esc(c.role_cn) + "</span>" +
      badge(c.group_id, "neutral") + "</div>" +
      '<div class="row"><span class="case-student">' + esc(c.student_id) + "</span>" +
      donut(d.overall, 46, 5, "得分率") + "</div>" +
      "<p>" + esc(short(c.selection_reason, 74)) + "</p>" +
      '<div class="row tiny muted"><span>已评 ' + n(d.scored) + " 条</span><span>·</span><span>覆盖 " +
      p(meanCoverage(state.studentById.get(c.student_id))) + "</span></div></a>";
  }).join("");

  const heat = state.topics.map((topic) => {
    const cells = (topic.indicators || []).map((ind) => {
      const st = state.indicatorStats.get(ind.indicator_id) || {};
      const rate = st.rate;
      return '<div class="heat-cell ' + heatClass(rate) + '" title="' + esc(ind.indicator_id + " " + ind.observation) + '">' +
        '<div class="hc-top"><span class="hc-rate num">' + esc(p(rate)) + "</span>" +
        confidenceBadge(st.confidence || "low") + "</div>" +
        '<div class="hc-meta">' + esc(short(ind.observation, 20)) + " · 观测 " + n(st.observed) + "</div></div>";
    }).join("");
    const label = '<div class="heat-row-label"><b class="mono">' + esc(topic.topic_id) + "</b><span class=\"tiny muted\">" + esc(short(topic.topic, 12)) + "</span></div>";
    return label + cells;
  }).join("");

  const issues = state.commonIssues.length ? state.commonIssues.map((x) => {
    const meta = getIndicatorMeta(x.indicator_id);
    return '<div class="issue"><span class="mono small">' + esc(x.indicator_id) + "</span>" +
      "<div><div class=\"small\">" + esc(meta ? meta.observation : x.indicator_id) + "</div>" +
      progress(x.rate) + "</div>" +
      '<span class="issue-rate num">' + esc(p(x.rate)) + "</span></div>";
  }).join("") : empty({ title: "暂无明显共性弱项", text: "当前指标观测样本不足，建议先补充记录。" });

  const hero = '<section class="hero"><div class="hero-row"><div>' +
    '<div class="eyebrow">本次分析快照 · ' + esc(formatDate(m.generated_at)) + "</div>" +
    "<h1>从学习内容，到学情诊断，再到可执行建议</h1>" +
    "<p>一堂课的判断不该只靠印象。工作台把 40 名学生的作答记录、9 项观察指标与 65 份材料串成一条可核对、可复测的证据链。</p>" +
    '<div class="hero-meta">' +
    "<div><span>数据范围</span><strong>" + n(m.students) + " 生 / " + n(m.groups) + " 班</strong></div>" +
    "<div><span>唯一作答事件</span><strong>" + n(m.unique_events) + " 条</strong></div>" +
    "<div><span>异常修正</span><strong>" + n(m.changes) + " 处</strong></div>" +
    "<div><span>个性化建议</span><strong>" + n(m.recommendations) + " 条</strong></div>" +
    "</div></div>" +
    '<div class="stack" style="min-width:160px">' +
    '<div class="row">' + badge("学习内容", "brand") + badge("学情诊断", "accent") + "</div>" +
    '<div class="row">' + badge("个性化建议", "ok") + "</div>" +
    '<div class="tiny" style="color:#BFE3DD">三任务闭环 · 证据可回溯</div>' +
    "</div></div></section>";

  const kpis = '<div class="kpi-grid">' +
    kpi({ label: "覆盖学生", value: n(m.students), unit: "人", sub: n(m.groups) + " 个模拟班级" }) +
    kpi({ label: "作答记录", value: n(m.raw_records), unit: "条", sub: "唯一事件 " + n(m.unique_events) + " 条" }) +
    kpi({ label: "异常与修正", value: n(m.changes), unit: "处", sub: n(m.anomalies) + " 条异常 → 清洗后 " + n(m.clean_anomalies), tone: "accent" }) +
    kpi({ label: "个性化建议", value: n(m.recommendations), unit: "条", sub: "覆盖 " + n(m.students) + " 名学生", tone: "ok" }) +
    kpi({ label: "典型案例", value: n(m.cases), unit: "个", sub: "巩固 / 数据不足 / 稳定", tone: "ok" }) +
    kpi({ label: "内容图谱", value: n(m.indicators), unit: "项指标", sub: n(m.topics) + " 个主题 · " + n(m.materials) + " 份材料" }) +
    "</div>";

  const overview = '<div class="overview-top">' +
    '<div class="card"><div class="card-head"><div><h2>两个模拟班：先看差异，再看个体</h2>' +
    "<p>班级均值只用于定位差异，不替代个体判断。</p></div>" +
    (gap ? badge("最大班差 " + p(Math.abs(gap.score_rate_gap)), "warn") : "") + "</div>" +
    '<div class="grid grid-2">' + state.classStats.map((row) => classCard(row, { gap })).join("") + "</div>" +
    (maxGap ? '<div class="gap-note" style="margin-top:10px">' + icon("target") + "<span>指标层面最大差异在 <b>" +
      esc(maxGap.indicator_id) + "</b>（" + esc(maxGap.pair[0]) + " " + p(maxGap.a.rate) + " vs " +
      esc(maxGap.pair[1]) + " " + p(maxGap.b.rate) + "，相差 <b>" + p(maxGap.gap) + "</b>）。</span></div>" : "") +
    "</div>" +
    '<div class="card"><div class="card-head"><div><h2>共性弱项</h2><p>按群体满分率升序，观测数 ≥ 10 的指标。</p></div>' +
    '<a class="btn btn-sm" href="#/content">查看指标依据 ' + icon("arrow") + "</a></div>" +
    '<div class="issue-list">' + issues + "</div>" +
    '<div class="callout" style="margin-top:12px"><strong>口径提醒</strong>满分率 = 满分记录 / 已评记录；覆盖度 = 已观测材料 / 节点可用题目。没有记录不等于没有掌握。</div>' +
    "</div></div>";

  const heatCard = '<div class="card"><div class="card-head"><div><h2>指标热力图</h2>' +
    "<p>3 个主题 × 3 项观察指标；颜色越暖，群体满分率越低。</p></div>" +
    '<div class="row tiny muted"><span class="heat-cell heat-0" style="padding:3px 7px;min-height:0">低</span><span class="heat-cell heat-4" style="padding:3px 7px;min-height:0">高</span></div></div>' +
    '<div class="heatmap"><div class="heat-grid"><div class="heat-head"></div>' +
    '<div class="heat-head">指标 I1</div><div class="heat-head">指标 I2</div><div class="heat-head">指标 I3</div>' +
    heat + "</div></div>" +
    '<div class="row tiny muted" style="margin-top:9px">' + icon("info") +
    "<span>单元格显示群体满分率与观测条数；置信度按 n &lt; 5 / 5–9 / ≥ 10 分为低 / 中 / 高。</span></div></div>";

  const caseCard = '<div class="card"><div class="card-head"><div><h2>典型案例</h2>' +
    "<p>三类学习需求各取一名：需要巩固、数据不足、稳定表现。</p></div>" +
    '<a class="btn btn-sm" href="#/cases">全部案例 ' + icon("arrow") + "</a></div>" +
    '<div class="case-strip">' + (caseCards || empty({ title: "暂无案例" })) + "</div></div>";

  const quality = '<div class="card"><div class="card-head"><div><h2>运行与质量</h2>' +
    "<p>每次运行都留下步骤、产物哈希与守卫结果。</p></div>" +
    '<a class="btn btn-sm" href="#/quality">查看轨迹 ' + icon("arrow") + "</a></div>" +
    '<div class="quality-strip">' +
    '<div class="quality-item"><span class="qmark">' + icon("alert") + "</span><div class=\"qtext\"><strong>质检 " + n(qc ? qc.anomaly_records : 0) + " 条异常</strong><span>清洗后 " + n(clean ? (clean.qc_after || {}).anomaly_records : 0) + " 条</span></div></div>" +
    '<div class="quality-item"><span class="qmark">' + icon("check") + "</span><div class=\"qtext\"><strong>修正 " + n(m.changes) + " 处</strong><span>逐单元格对账通过</span></div></div>" +
    '<div class="quality-item"><span class="qmark">' + icon("quality") + "</span><div class=\"qtext\"><strong>守卫 " + (guard && guard.status === "pass" ? "通过" : "待检查") + "</strong><span>" + (guard ? guard.checks.length : 0) + " 类检查</span></div></div>" +
    '<div class="quality-item"><span class="qmark">' + icon("play") + "</span><div class=\"qtext\"><strong>" + (trace ? trace.steps.length : 0) + " 步流水线</strong><span>" + (trace && trace.status === "ok" ? "运行通过" : "未运行") + "</span></div></div>" +
    "</div></div>";

  return hero + kpis + overview + '<div class="grid" style="margin-top:16px">' + heatCard + "</div>" +
    '<div class="grid" style="margin-top:16px">' + caseCard + "</div>" +
    '<div class="grid" style="margin-top:16px">' + quality + "</div>";
};

export const studentsPage = () => {
  const rows = filteredStudents();
  const groups = allGroups();
  const flags = allFlags();
  const total = state.students.length;
  const toolbar = '<div class="toolbar">' +
    '<div class="field"><label for="groupFilter">班级</label><select class="select" id="groupFilter" data-filter="group">' +
    '<option value="all"' + selected("all", state.filters.group) + ">全部</option>" +
    groups.map((g) => '<option value="' + esc(g) + '"' + selected(g, state.filters.group) + ">" + esc(g) + "</option>").join("") +
    "</select></div>" +
    '<div class="field"><label for="flagFilter">标记</label><select class="select" id="flagFilter" data-filter="flag">' +
    '<option value="all"' + selected("all", state.filters.flag) + ">全部</option>" +
    flags.map((f) => '<option value="' + esc(f) + '"' + selected(f, state.filters.flag) + ">" + esc(f) + "</option>").join("") +
    "</select></div>" +
    '<div class="field"><label for="sortFilter">排序</label><select class="select" id="sortFilter" data-filter="sort">' +
    [["id", "学生编号"], ["overall_asc", "得分率从低到高"], ["overall_desc", "得分率从高到低"], ["coverage_desc", "覆盖度"], ["records_desc", "记录数"]]
      .map(([v, label]) => '<option value="' + v + '"' + selected(v, state.filters.sort) + ">" + label + "</option>").join("") +
    "</select></div>" +
    (state.search ? '<button class="btn btn-sm" type="button" data-action="clear-search">清除搜索 “' + esc(short(state.search, 16)) + "”</button>" : "") +
    '<span class="count">显示 ' + rows.length + " / " + total + " 名学生</span></div>";

  const cards = rows.map((s) => {
    const overall = scoreRate(s);
    const cov = meanCoverage(s);
    const weak = weakIndicators(s).slice(0, 2);
    const flagList = (s.flags || []).slice(0, 3);
    return '<a class="student-card" href="#/students/' + esc(s.student_id) + '">' +
      '<div class="avatar">' + esc(s.student_id) + "</div>" +
      "<div><div class=\"row\"><span class=\"sc-name\">" + esc(s.student_id) + "</span>" +
      badge(s.group_id, "neutral") + "</div>" +
      '<div class="sc-meta">' + n((s.observed || {}).records) + " 条记录 · 覆盖 " + p(cov) + "</div>" +
      '<div class="sc-flags">' + flagList.map(flagBadge).join("") + "</div>" +
      '<div class="sc-bar">' + progress(overall) + "</div>" +
      '<div class="sc-foot"><span>得分率 ' + p(overall) + "</span><span>" +
      (weak.length ? "弱项 " + esc(weak.map((x) => x.indicator_id).join(" / ")) : "暂无显著弱项") + "</span></div></div>" +
      donut(overall, 56, 6, "得分率") +
      "</a>";
  }).join("");

  return pageHead({
    kicker: "任务 2 · 个体层面",
    title: "学生画像",
    lede: "按班级、标记与得分率筛选；点开任一学生，查看节点覆盖、9 项指标、建议时间线与逐条证据。",
  }) + toolbar +
    (rows.length ? '<div class="student-grid">' + cards + "</div>" :
      empty({ title: "没有匹配的学生", text: "清除搜索或调整筛选条件。" }) + '<div style="text-align:center;margin-top:12px"><button class="btn" type="button" data-action="clear-search">清除搜索 / 筛选</button></div>');
};

export const studentDetailPage = (studentId) => {
  const s = getStudent(studentId);
  if (!s) return notFoundPage("学生 " + studentId + " 不在快照中");
  const rec = getRecommendation(studentId);
  const records = recordsOfStudent(studentId);
  const overall = scoreRate(s);
  const cov = meanCoverage(s);
  const classAvg = classAvgOf(s);
  const weak = weakIndicators(s);
  const strong = strongIndicators(s);
  const items = (rec && rec.items) || [];
  const basis = (rec && rec.basis) || [];

  const head = '<div class="card">' +
    '<div class="breadcrumb">' + studentLink("", "学生画像") + icon("chevron") + "<span>" + esc(studentId) + "</span></div>" +
    '<div class="profile-head"><div class="avatar profile-avatar">' + esc(s.student_id) + "</div>" +
    '<div class="profile-title"><div class="eyebrow">个体画像 · ' + esc(s.group_id) + "</div><h1>" + esc(s.student_id) + "</h1>" +
    '<div class="sub">' + n((s.observed || {}).records) + " 条记录 · 节点覆盖 " + p(cov) +
    (classAvg ? " · 班级平均 " + p(classAvg.score_rate_mean) : "") + "</div>" +
    '<div class="row" style="margin-top:5px">' + ((s.flags || []).length ? s.flags.map(flagBadge).join("") : badge("无特殊标记", "neutral")) + "</div></div>" +
    '<div class="profile-stats">' +
    '<div class="profile-stat"><span>整体得分率</span><strong class="num">' + p(overall) + "</strong></div>" +
    '<div class="profile-stat"><span>已评 / 待评</span><strong class="num">' + n((s.observed || {}).scored) + " / " + n((s.observed || {}).pending) + "</strong></div>" +
    '<div class="profile-stat"><span>建议条数</span><strong class="num">' + n(items.length) + "</strong></div>" +
    "</div></div></div>";

  const nodeRows = Object.entries((s.observed || {}).coverage || {}).map(([node, coverage]) => {
    const rate = ((s.score_rate || {}).by_node || {})[node];
    return '<div class="card" style="box-shadow:none"><div class="card-head"><div><h3 class="mono">' + esc(node) + "</h3>" +
      '<p class="small">覆盖 ' + p(coverage) + " · 得分率 " + p(rate) + "</p></div>" +
      badge(coverage >= 0.4 ? "覆盖尚可" : "覆盖偏低", coverage >= 0.4 ? "ok" : "warn") + "</div>" +
      progressRow("覆盖度", coverage) + progressRow("得分率", rate) + "</div>";
  }).join("");

  const summary = card({
    title: "节点与指标",
    sub: "指标满分率按已评记录计算；低置信指标只适合观察，不宜直接排练习。",
    body: '<div class="grid grid-2" style="margin-bottom:12px">' + nodeRows + "</div>" +
      '<div class="indicator-list">' + (s.by_indicator || []).map((ind) => {
        const meta = getIndicatorMeta(ind.indicator_id);
        return '<div class="indicator-row ' + (ind.rate !== null && ind.rate < 0.6 ? "weak" : "") + '">' +
          '<div class="mono small">' + esc(ind.indicator_id) + "</div>" +
          '<div><div class="ind-name">' + esc(meta ? meta.observation : ind.indicator_id) + "</div>" +
          '<div class="ind-obs">观测 ' + n(ind.observed) + " · 满分 " + n(ind.correct) + "</div></div>" +
          '<div class="ind-bar">' + progress(ind.rate) + "</div>" +
          '<div class="ind-rate num">' + p(ind.rate) + "</div>" +
          '<div class="ind-conf">' + confidenceBadge(ind.confidence) + "</div></div>";
      }).join("") + "</div>" +
      '<div class="indicator-note">' + icon("info") + " 低置信（n &lt; 5）不等于低能力；本页把「需要巩固」与「需要补充观察」分开呈现。</div>",
  });

  const reco = card({
    title: "个性化学习建议",
    sub: "顺序即实施顺序；每条都带证据、观察点与调整条件。",
    actions: rec ? badge(items.length + " 条", "brand") : "",
    body: items.length ? '<div class="reco-list">' + items.map((item) => {
      const meta = getMaterial(item.material_id);
      return '<article class="reco"><div class="reco-head"><span class="reco-seq">' + n(item.seq) + "</span>" +
        '<span class="reco-material">' + esc(item.material_id) + "</span>" +
        (meta ? badge(meta.type, "neutral") : "") + actionBadge(item.action) +
        badge("提示：" + (item.hint_level || "—"), "brand") + "</div>" +
        '<p class="reco-reason">' + esc(item.reason) + "</p>" +
        '<div class="reco-meta">' +
        '<div class="meta-line"><dt>证据</dt><dd>' + evidenceChips(item.evidence_refs || [], { studentId }) + "</dd></div>" +
        '<div class="meta-line"><dt>观察点</dt><dd>' + esc(item.expected_observation || "—") + "</dd></div>" +
        '<div class="meta-line"><dt>调整条件</dt><dd>' + esc(item.adjust_condition || "—") + "</dd></div>" +
        "</div></article>";
    }).join("") + "</div>" :
      empty({ title: "暂无建议", text: "该生可能缺少已评记录；请先补充观察。" }),
  });

  const notReco = rec && (rec.not_recommended || []).length ?
    card({
      title: "本轮不推荐",
      sub: "不是永久排除，而是留到下一轮补充观察。",
      body: '<div class="not-reco">' + rec.not_recommended.map((x) =>
        '<div class="not-reco-item">' + materialChip(x.material_id) + "<div>" + esc(x.reason) + "</div></div>").join("") + "</div>",
    }) : "";

  const nextCheck = rec && rec.next_check ?
    '<div class="callout"><strong>复测安排</strong>' + esc(rec.next_check.when || "") + " · " + esc(rec.next_check.what || "") + "</div>" : "";

  const basisCard = card({
    title: "判断依据",
    sub: "来自诊断与建议生成器的可核对摘要。",
    body: basis.length ? '<ul class="basis-list">' + basis.map((b) => "<li>" + esc(b) + "</li>").join("") + "</ul>" :
      '<div class="note">暂无 basis 字段。</div>',
  });

  const classContext = classAvg ? card({
    title: "班级参照",
    sub: "群体均值用于定位差距，不替代个体证据。",
    body: progressRow("该生得分率", overall) + progressRow("班级平均", classAvg.score_rate_mean) +
      '<div class="gap-note">' + icon("target") + "<span>与班级平均相差 <b>" +
      esc(overall === null ? "—" : signedPct(Number(overall) - Number(classAvg.score_rate_mean))) + "</b>。</span></div>",
  }) : "";

  const evidence = card({
    title: "作答记录",
    sub: "只展示评分与节点字段，不展示作答原文与参考答案。",
    body: recordTable(records),
  });

  const reading = '<div class="card"><div class="card-head"><div><h2>怎么读这一页</h2><p>把「表现」与「建议」分开看。</p></div></div>' +
    '<div class="stack small">' +
    '<div>' + icon("info") + " <b>得分率</b>：得分 / 满分，反映已评记录上的表现。</div>" +
    '<div>' + icon("target") + " <b>满分率</b>：满分记录 / 已评记录，用于指标层面判断。</div>" +
    '<div>' + icon("alert") + " <b>低置信</b>：观测 n &lt; 5；只做回顾或观察，不直接排练习/变式。</div>" +
    '<div>' + icon("check") + " <b>可复测</b>：每条建议都给出观察点与调整条件。</div>" +
    "</div></div>";

  return head + '<div class="detail-layout" style="margin-top:16px"><div class="stack">' +
    summary + reco + notReco + nextCheck + "</div>" +
    '<div class="grid-side">' + basisCard + classContext + evidence + reading + "</div></div>";
};

export const casesPage = () => {
  const cmp = state.classComparison;
  const policy = (state.docs.cases || {}).selection_policy;
  const policyText = Array.isArray(policy)
    ? policy.map((x) => (x.label || x.role || "") + "：" + (x.rule || "")).join("；")
    : policy || "按已评记录、覆盖度与班级分布选择。";
  const cards = state.cases.map((c) => {
    const d = c.diagnosis || {};
    return '<a class="case-card" href="#/cases/' + esc(c.student_id) + '">' +
      '<div class="case-top"><div><div class="eyebrow">' + esc(c.role_cn) + "</div>" +
      '<span class="case-id">' + esc(c.student_id) + "</span> " + badge(c.group_id, "neutral") + "</div>" +
      donut(d.overall, 64, 7, "得分率") + "</div>" +
      '<p class="case-reason">' + esc(c.selection_reason) + "</p>" +
      '<div class="case-stats">' +
      '<div class="case-stat"><span>已评记录</span><strong>' + n(d.scored) + "</strong></div>" +
      '<div class="case-stat"><span>节点覆盖</span><strong>' + p(meanCoverage(state.studentById.get(c.student_id))) + "</strong></div>" +
      "</div>" +
      '<div class="row">' + (c.diagnosis.weak_indicators || []).slice(0, 2).map((x) => badge(x.indicator_id, "warn")).join("") +
      badge("查看证据链", "brand") + "</div></a>";
  }).join("");

  const classCards = (cmp ? cmp.by_class : state.classStats).map((row) => classCard(row, { gap: cmp ? cmp.gap : null })).join("");
  const groupIds = cmp && cmp.by_class ? cmp.by_class.map((x) => x.group_id) : [];
  const cmpRows = (cmp && cmp.by_indicator || []).map((row) => {
    const a = row[groupIds[0]] || {};
    const b = row[groupIds[1]] || {};
    const gap = Number(a.rate) - Number(b.rate);
    return {
      cells: [
        { html: '<span class="mono">' + esc(row.indicator_id) + "</span>" },
        { html: '<div class="compare-bar">' + progress(a.rate) + '<span class="num">' + p(a.rate) + "</span></div>" },
        { html: '<div class="compare-bar">' + progress(b.rate) + '<span class="num">' + p(b.rate) + "</span></div>" },
        { html: '<span class="' + (Math.abs(gap) >= 0.1 ? "badge badge-warn" : "badge badge-neutral") + '">' + esc(signedPct(gap)) + "</span>" },
      ],
    };
  });

  return pageHead({
    kicker: "任务 2 + 3 · 结果核对",
    title: "典型案例",
    lede: "三类学习需求各取一名，展示「学习要求 → 已有表现 → 学习建议」的对应关系，并把班级差异放在同一张参照系里。",
    actions: '<button class="btn" type="button" data-action="print">' + icon("print") + "打印本页</button>",
  }) +
    '<div class="card" style="margin-bottom:16px"><div class="card-head"><div><h2>为什么是这三名</h2>' +
    "<p>" + esc(policyText) + "</p></div></div>" +
    '<div class="case-grid">' + cards + "</div></div>" +
    '<div class="grid grid-2" style="margin-bottom:16px">' + classCards + "</div>" +
    card({
      title: "班级 × 指标对比",
      sub: "满分率并排对比；差值 ≥ 10pp 标记为需要关注。",
      body: table(
        [{ label: "指标" }, { label: groupIds[0] || "班级 A" }, { label: groupIds[1] || "班级 B" }, { label: "差值" }],
        cmpRows,
        { caption: "分班级指标满分率；样本量见内容图谱或诊断 JSON。" },
      ),
    }) +
    '<div class="callout" style="margin-top:14px"><strong>适用范围</strong>模拟数据只覆盖两个节点、抽样作答；案例用于核对分析链路与建议依据，不用于证明真实教学成效。</div>';
};

export const caseDetailPage = (studentId) => {
  const c = getCase(studentId);
  if (!c) return notFoundPage("案例 " + studentId + " 不在快照中");
  const s = getStudent(studentId);
  const d = c.diagnosis || {};
  const rec = c.recommendation || getRecommendation(studentId) || {};
  const cmp = state.classComparison;
  const classAvg = classAvgOf(s || { group_id: c.group_id });

  const chain = (c.evidence_chain || []).map((ev) => {
    const meta = getIndicatorMeta(ev.indicator_id);
    const diagInd = s ? (s.by_indicator || []).find((x) => x.indicator_id === ev.indicator_id) : null;
    const recordRows = (ev.records || []).map((r) => recordChip(r.record_id) + " " + badge(r.status, r.status === "已评分" ? "ok" : "neutral") +
      " <span class=\"tiny muted\">" + n(r.score, 1) + "/" + n(r.max_score, 1) + " · " + p(r.rate) + "</span>").join(" ");
    return '<div class="chain-item"><div class="chain-dot">' + n(ev.seq) + "</div><div class=\"chain-body\">" +
      '<div class="chain-head"><span class="chain-material">' + esc(ev.material_id) + "</span>" +
      (ev.material_type ? badge(ev.material_type, "neutral") : "") +
      (ev.question_type ? badge(ev.question_type, "neutral") : "") +
      badge(ev.topic_id || "—", "brand") +
      (ev.indicator_id ? badge(ev.indicator_id, "accent") : "") +
      (ev.action ? actionBadge(ev.action) : "") +
      (ev.hint_level ? badge("提示：" + ev.hint_level, "brand") : "") + "</div>" +
      '<div class="chain-cols">' +
      '<div class="chain-col"><h4>学习要求</h4><p>' + esc(meta ? meta.observation : ev.indicator_observation || "—") + "</p>" +
      (ev.standard ? '<div class="small muted">课标 ' + esc(ev.standard.cr_id) + " · PDF " + esc(ev.standard.pdf_pages) + " · 正文 " + esc(ev.standard.body_pages) + "</div>" : "") +
      (meta ? '<div class="small muted">教材 ' + esc(meta.textbook_pages || "—") + "</div>" : "") + "</div>" +
      '<div class="chain-col"><h4>已有表现</h4>' +
      (diagInd ? '<p>观测 ' + n(diagInd.observed) + " 条 · 满分 " + n(diagInd.correct) + " 条 · 满分率 " + p(diagInd.rate) + "</p>" +
        '<div class="small">' + confidenceBadge(diagInd.confidence) + "</div>" : '<p class="muted">该指标暂无个体观测。</p>') +
      '<div class="chain-records">' + (recordRows || '<span class="tiny muted">暂无记录</span>') + "</div></div>" +
      '<div class="chain-col"><h4>学习建议</h4><p>' + esc(ev.reason || "—") + "</p>" +
      '<div class="small muted">观察点：' + esc(ev.expected_observation || "—") + "</div>" +
      '<div class="small muted">调整：' + esc(ev.adjust_condition || "—") + "</div></div>" +
      "</div>" +
      '<div class="chain-foot"><div><span>证据引用</span>' + evidenceChips(ev.evidence_refs || [], { studentId }) + "</div>" +
      '<div><span>材料</span>' + materialChip(ev.material_id) + "</div></div>" +
      "</div></div>";
  }).join("");

  const items = (rec.items || []).map((item) =>
    '<div class="seq-item"><div class="seq-badge">' + badge("第 " + item.seq + " 步", "brand") + "</div>" +
    '<div class="seq-main">' + materialChip(item.material_id) +
    '<div class="small">' + actionBadge(item.action) + " " + esc(item.reason) + "</div>" +
    '<div class="tiny muted">观察点：' + esc(item.expected_observation || "—") + "</div></div></div>").join("");

  const cmpRows = (cmp && cmp.by_indicator || []).filter((row) => (d.weak_indicators || []).some((w) => w.indicator_id === row.indicator_id))
    .map((row) => {
      const a = row[(cmp.by_class[0] || {}).group_id] || {};
      const b = row[(cmp.by_class[1] || {}).group_id] || {};
      return {
        cells: [
          { html: '<span class="mono">' + esc(row.indicator_id) + "</span>" },
          { html: p(a.rate) }, { html: p(b.rate) }, { html: signedPct(Number(a.rate) - Number(b.rate)) },
        ],
      };
    });

  return '<div class="breadcrumb"><a href="#/cases">典型案例</a>' + icon("chevron") + "<span>" + esc(studentId) + "</span></div>" +
    '<div class="card case-detail-head" style="margin-bottom:16px">' +
    '<div><div class="case-role-badge">' + badge(c.role_cn || c.role, c.role === "remedial" ? "bad" : c.role === "stable" ? "ok" : "warn") + "</div>" +
    "<h1>" + esc(studentId) + " <span class=\"muted\" style=\"font-size:15px;font-weight:500\">" + esc(c.group_id) + "</span></h1>" +
    "<p class=\"muted\" style=\"margin:0 0 9px\">" + esc(c.selection_reason) + "</p>" +
    '<div class="row">' + (d.flags || []).map(flagBadge).join("") + "</div></div>" +
    '<div class="row">' + donut(d.overall, 92, 9, "得分率") +
    '<div class="profile-stats" style="margin:0">' +
    '<div class="profile-stat"><span>已评</span><strong>' + n(d.scored) + "</strong></div>" +
    '<div class="profile-stat"><span>覆盖</span><strong>' + p(meanCoverage(s)) + "</strong></div>" +
    "</div></div></div>" +
    '<div class="detail-layout"><div class="stack">' +
    card({ title: "学习要求 — 已有表现 — 学习建议", sub: "按建议顺序排列；每一行都能回到材料、指标与记录。", body: '<div class="chain">' + chain + "</div>" }) +
    card({ title: "建议顺序", sub: "先回顾，再练习；信息不足时先观察。", body: '<div class="stack">' + items + "</div>" }) +
    "</div><div class=\"grid-side\">" +
    card({ title: "诊断摘要", sub: "只列弱项与稳定项，完整数据见学生画像。",
      body: '<div class="stack">' +
        '<div><div class="eyebrow">需要巩固</div>' + ((d.weak_indicators || []).length ? (d.weak_indicators || []).map((x) =>
          '<div class="progress-row"><span class="label mono">' + esc(x.indicator_id) + "</span>" + progress(x.rate) +
          '<span class="value">' + p(x.rate) + "</span></div>").join("") : '<div class="note">无</div>') + "</div>" +
        '<div><div class="eyebrow">稳定表现</div>' + ((d.strong_indicators || []).length ? (d.strong_indicators || []).map((x) =>
          '<div class="progress-row"><span class="label mono">' + esc(x.indicator_id) + "</span>" + progress(x.rate) +
          '<span class="value">' + p(x.rate) + "</span></div>").join("") : '<div class="note">样本不足，暂无稳定项。</div>') + "</div>" +
        "</div>" }) +
    card({ title: "班级参照", sub: classAvg ? classAvg.group_id : "",
      body: cmpRows.length ? table([{ label: "指标" }, { label: (cmp.by_class[0] || {}).group_id || "A" }, { label: (cmp.by_class[1] || {}).group_id || "B" }, { label: "差值" }], cmpRows, { className: "table-compact" }) :
        '<div class="note">该生弱项暂无可比班级数据。</div>' }) +
    card({ title: "适用范围", sub: "", body: '<div class="note">案例用于核对「要求—表现—建议」的对应关系与依据，不用模拟数据证明真实教学成效。跨节点题集不同，节点间得分率不可直接排序。</div>' }) +
    "</div></div>";
};

export const contentPage = () => {
  const topics = state.topics.map((topic, index) => {
    const cards = (topic.indicators || []).map((ind) => {
      const stat = state.indicatorStats.get(ind.indicator_id) || {};
      return '<article class="indicator-card"><div class="ic-head"><span class="ic-id">' + esc(ind.indicator_id) + "</span>" +
        badge(ind.standard ? ind.standard.cr_id : "课标", "brand") + "</div>" +
        "<h3>" + esc(ind.observation) + "</h3>" +
        '<div class="ic-meta">' +
        "<div>课标页：PDF <b>" + esc(ind.standard ? ind.standard.pdf_pages : "—") + "</b> · 正文 <b>" + esc(ind.standard ? ind.standard.body_pages : "—") + "</b></div>" +
        "<div>教材页：<b>" + esc(ind.textbook_pages || "—") + "</b></div>" +
        "<div>群体满分率：<b>" + p(stat.rate) + "</b> · 观测 " + n(stat.observed) + "</div>" +
        "</div>" +
        '<div class="material-chips">' + (ind.material_ids || []).slice(0, 8).map((id) => materialChip(id)).join("") +
        ((ind.material_ids || []).length > 8 ? '<span class="tiny muted">+' + ((ind.material_ids || []).length - 8) + "</span>" : "") + "</div>" +
        '<div class="row tiny muted">' + (ind.evidence_required || []).map((x) => badge(x, "neutral")).join("") + "</div>" +
        "</article>";
    }).join("");
    return '<section class="topic-section"><div class="topic-head"><div class="topic-index">' + esc(topic.topic_id) + "</div>" +
      "<div><h2>" + esc(topic.topic) + "</h2><p>" + esc(topic.goal) + "</p></div></div>" +
      '<div class="indicator-cards">' + cards + "</div></section>";
  }).join("");

  const progression = state.topics.map((t) => t.topic_id).join(" → ");
  const materials = filterMaterials();
  const types = materialTypes();
  const rows = materials.map((m) => ({
    cells: [
      { html: materialChip(m.material_id) },
      { html: badge(m.type, "neutral") },
      { html: esc(m.topic_id || "—") },
      { html: esc(m.question_type || "—") },
      { html: esc(m.max_score ?? "—"), cls: "num" },
      { html: (m.node_scope || []).map((x) => badge(x, "neutral")).join(" ") },
      { html: (state.materialIndicators.get(m.material_id) || []).map((x) => indicatorChip(x.indicator_id)).join(" ") || '<span class="tiny muted">—</span>' },
    ],
  }));

  const materialFilter = '<div class="toolbar" style="margin:0 0 12px"><div class="field"><label for="materialType">材料类型</label>' +
    '<select class="select" id="materialType" data-filter="materialType"><option value="all"' + selected("all", state.filters.materialType) + ">全部</option>" +
    types.map((t) => '<option value="' + esc(t) + '"' + selected(t, state.filters.materialType) + ">" + esc(t) + "</option>").join("") +
    "</select></div><span class=\"count\">显示 " + materials.length + " / " + state.materialById.size + " 份材料</span></div>";

  const openQuestions = ((state.docs.content || {}).open_questions || []).map((q) =>
    "<li>" + esc(typeof q === "string" ? q : q.question || JSON.stringify(q)) + "</li>").join("");

  return pageHead({
    kicker: "任务 1 · 学习内容与要求",
    title: "内容图谱",
    lede: "3 个主题、9 项观察指标、65 份材料；每项指标都给出课标页、教材页与可用材料，便于后续诊断与建议复用。",
    actions: '<button class="btn" type="button" data-action="print">' + icon("print") + "打印本页</button>",
  }) +
    knowledgeGraphCard() +
    '<div class="topic-progress" style="margin-bottom:16px">' + icon("content") +
    "<span>主题递进：<b>" + esc(progression) + "</b>；先建立数与式，再进入方程与不等式，最后处理实际问题中的数据与推理。</span></div>" +
    topics +
    card({
      title: "材料索引",
      sub: "题目、教材与学习卡统一编号；点击材料查看所属指标与记录数。",
      body: materialFilter + table(
        ["材料", "类型", "主题", "题型", "满分", "可用节点", "对应指标"],
        rows,
        { caption: "材料来源为赛题原始资料；本工作台不展示参考答案。" },
      ),
    }) +
    (openQuestions ? '<div class="card" style="margin-top:16px"><div class="card-head"><div><h2>开放问题</h2>' +
      "<p>内容梳理中仍需人工确认的事项。</p></div></div><ul class=\"basis-list\">" + openQuestions + "</ul></div>" : "");
};

export const qualityPage = () => {
  const qc = state.qc || {};
  const clean = state.clean || {};
  const guard = state.guard;
  const trace = state.trace;
  const limitations = ((state.docs.diagnosis || {}).limitations || []);
  const steps = (trace && trace.steps) || [];
  const findings = qc.findings || [];
  const changes = clean.change_records || [];
  const checks = (guard && guard.checks) || [];

  const kpis = '<div class="kpi-grid" style="margin-bottom:16px">' +
    kpi({ label: "原始记录", value: n(qc.rows ?? state.meta.raw_records), unit: "条", sub: "唯一事件 " + n(qc.unique_events ?? state.meta.unique_events) }) +
    kpi({ label: "折叠修订", value: n(qc.revisions_folded ?? state.meta.revisions_folded), unit: "条", sub: "同事件取最高修订" }) +
    kpi({ label: "质检异常", value: n(qc.anomaly_records ?? state.meta.anomalies), unit: "条", sub: "QC01–QC19 规则命中", tone: "accent" }) +
    kpi({ label: "修正字段", value: n(clean.changes ?? state.meta.changes), unit: "处", sub: "未解决 " + n((clean.unresolved || []).length), tone: "accent" }) +
    kpi({ label: "清洗后异常", value: n((clean.qc_after || {}).anomaly_records ?? state.meta.clean_anomalies), unit: "条", sub: "逐单元格对账通过", tone: "ok" }) +
    kpi({ label: "守卫", value: guard && guard.status === "pass" ? "PASS" : "—", sub: checks.length + " 类检查", tone: "ok" }) +
    "</div>";

  const traceBody = steps.length ? '<div class="trace">' + steps.map(traceStep).join("") + "</div>" :
    empty({ title: "尚无运行轨迹", text: "运行 run.cmd all 后生成 out/agent_trace.json。" });

  const guardBody = checks.length ? '<div class="guard-list">' + checks.map(guardItem).join("") + "</div>" :
    empty({ title: "守卫报告缺失", text: "运行流水线后自动生成。" });

  const rulesBody = findings.length ? '<div class="rule-list">' + findings.map((f) =>
    '<div class="rule-item"><div class="rule-head"><span class="mono">' + esc(f.record_id) + "</span>" +
    badge(f.student_id, "neutral") + badge(f.material_id, "neutral") + badge(f.node_id, "neutral") +
    (f.rule_codes || []).map((c) => badge(c, "bad")).join("") + "</div>" +
    '<div class="rule-body">' + (f.rules || []).map((r) =>
      "<div><b>" + esc(r.code) + "</b> <span>" + esc(r.field || "") + "</span> " +
      esc(r.expected ?? "") + " → " + esc(r.actual ?? "") + (r.note ? " <span>" + esc(r.note) + "</span>" : "") + "</div>").join("") + "</div></div>").join("") + "</div>" :
    empty({ title: "无异常", text: "当前规则未命中。" });

  const changesBody = changes.length ? table(
    ["记录", "字段", "修正前", "修正后", "规则", "依据"],
    changes.map((x) => ({
      cells: [
        { html: '<span class="mono">' + esc(x.record_id) + "</span>" },
        { html: esc(x.field) },
        { html: '<span class="mono">' + esc(x.before) + "</span>" },
        { html: '<span class="mono">' + esc(x.after) + "</span>" },
        { html: badge(x.rule, "warn") },
        { html: esc(x.basis) },
      ],
    })),
    { caption: "所有修正都可在 data/derived/作答记录_变更记录.csv 中核对。" },
  ) : empty({ title: "无修正", text: "原始记录与清洗版一致。" });

  const limitationsBody = '<ul class="basis-list">' + (limitations.length ? limitations.map((x) =>
    "<li>" + esc(typeof x === "string" ? x : x.note || JSON.stringify(x)) + "</li>").join("") : "<li>暂无。</li>") + "</ul>";

  const sources = (state.snapshot && state.snapshot.sources || []).map(sourceRow).join("");
  const contract = card({
    title: "契约与版本",
    sub: "所有结构化结果先过 schema，再进入工作台。",
    body: '<div class="stack small">' +
      '<div class="row">' + badge("content_map", "brand") + badge("diagnosis", "brand") + badge("recommendation", "brand") + badge("ui.snapshot/1", "neutral") + "</div>" +
      '<div class="note">schema_version 固定 0.1.0；ID 沿用赛题原始编号；validate 步骤在 trace 中可核对。</div>' +
      (steps.find((x) => x.tool === "validate") ? '<div class="callout"><strong>validate</strong>' + esc(steps.find((x) => x.tool === "validate").summary) + "</div>" : "") +
      "</div>",
  });

  return pageHead({
    kicker: "任务 2 · 数据治理",
    title: "数据质量与运行轨迹",
    lede: "先把缺失、异常、重复记录说清楚，再谈学情判断。本页把质检规则、修正记录、守卫结果与 9 步轨迹放在一起，便于复核。",
    actions: '<button class="btn" type="button" data-action="run">' + icon("play") + "重新分析</button>" +
      '<button class="btn" type="button" data-action="print">' + icon("print") + "打印</button>",
  }) + kpis +
    '<div class="grid grid-main">' +
    '<div class="stack">' +
    card({ title: "9 步流水线", sub: trace ? "开始 " + formatDate(trace.started_at) + " · 结束 " + formatDate(trace.finished_at) : "", actions: trace ? badge(trace.status === "ok" ? "运行通过" : trace.status, trace.status === "ok" ? "ok" : "bad") : "", body: traceBody }) +
    card({ title: "质检异常", sub: "QC01–QC19 命中记录；异常清单见 data/derived/作答记录_异常清单.csv。", body: rulesBody }) +
    card({ title: "清洗修正", sub: "以评分点为准；不改学生答案；节点与事件编号联动。", body: changesBody }) +
    "</div>" +
    '<div class="grid-side">' +
    card({ title: "守卫层", sub: "学生覆盖、证据可解析、置信度不变量、答案与合规、个人信息。", body: guardBody }) +
    contract +
    card({ title: "限制与适用范围", sub: "判断边界写在结果里，而不是留在口头。", body: limitationsBody }) +
    card({ title: "产物与哈希", sub: "快照中的每个来源都可追溯到文件。", body: '<div class="source-list">' + sources + "</div>" }) +
    "</div></div>";
};

export const notFoundPage = (message = "页面不存在") =>
  '<div class="error-panel"><div class="card"><h1>找不到这个页面</h1>' +
  "<p class=\"muted\">" + esc(message) + "</p>" +
  '<p><a class="btn" href="#/overview">回到总览</a></p></div></div>';

/* ---------- 抽屉内容 ---------- */

export const drawerMaterial = (id) => {
  const m = getMaterial(id);
  if (!m) return empty({ title: "材料不存在", text: id });
  const inds = state.materialIndicators.get(id) || [];
  const recs = recordsOfMaterial(id);
  const nodeScope = (m.node_scope || []).map((x) => badge(x, "neutral")).join(" ");
  return '<div class="stack">' +
    '<div class="row">' + badge(m.type, m.type === "题目" ? "brand" : "neutral") +
    (m.question_type ? badge(m.question_type, "neutral") : "") + badge(m.topic_id || "—", "accent") + "</div>" +
    '<div class="grid grid-2">' +
    '<div class="card" style="box-shadow:none"><div class="kpi-label">满分</div><div class="kpi-value">' + n(m.max_score) + "</div></div>" +
    '<div class="card" style="box-shadow:none"><div class="kpi-label">可用节点</div><div class="kpi-value" style="font-size:17px">' + (nodeScope || "—") + "</div></div>" +
    "</div>" +
    '<div><div class="eyebrow">对应指标</div>' + (inds.length ? inds.map((x) =>
      '<div class="rule-item" style="margin-top:6px"><div class="rule-head">' + indicatorChip(x.indicator_id) +
      badge(x.topic_id, "neutral") + "</div><div class=\"rule-body\">" + esc(x.observation) + "</div></div>").join("") : '<div class="note">材料索引中未标注指标。</div>') + "</div>" +
    '<div><div class="eyebrow">作答记录</div>' +
    (recs.length ? '<div class="note">共 ' + recs.length + " 条记录；下表只展示评分字段。</div>" + recordTable(recs) : '<div class="note">该材料暂无作答记录。</div>') + "</div>" +
    '<div class="callout"><strong>合规</strong>本工作台不展示参考答案与作答原文；需要核对时请回到赛题原始资料与清洗版 CSV。</div>' +
    "</div>";
};

export const drawerIndicator = (id) => {
  const meta = getIndicatorMeta(id);
  if (!meta) return empty({ title: "指标不存在", text: id });
  const stat = state.indicatorStats.get(id) || {};
  const students = state.students.filter((s) => (s.by_indicator || []).some((x) => x.indicator_id === id && x.observed > 0))
    .sort((a, b) => {
      const ra = (a.by_indicator.find((x) => x.indicator_id === id) || {}).rate ?? 2;
      const rb = (b.by_indicator.find((x) => x.indicator_id === id) || {}).rate ?? 2;
      return ra - rb;
    });
  return '<div class="stack">' +
    '<div class="row">' + badge(id, "brand") + badge(meta.topic_id, "neutral") + confidenceBadge(stat.confidence) + "</div>" +
    "<h3 style=\"margin:0\">" + esc(meta.observation) + "</h3>" +
    '<div class="grid grid-2">' +
    '<div class="card" style="box-shadow:none"><div class="kpi-label">群体满分率</div><div class="kpi-value">' + p(stat.rate) + "</div></div>" +
    '<div class="card" style="box-shadow:none"><div class="kpi-label">观测 / 满分</div><div class="kpi-value" style="font-size:18px">' + n(stat.observed) + " / " + n(stat.correct) + "</div></div>" +
    "</div>" +
    '<div class="rule-item"><div class="rule-head">' + badge("课标 " + (meta.standard ? meta.standard.cr_id : "—"), "brand") +
    badge("PDF " + (meta.standard ? meta.standard.pdf_pages : "—"), "neutral") + badge("正文 " + (meta.standard ? meta.standard.body_pages : "—"), "neutral") +
    badge("教材 " + (meta.textbook_pages || "—"), "neutral") + "</div>" +
    '<div class="rule-body">可用材料：' + (meta.material_ids || []).map((x) => materialChip(x)).join(" ") + "</div></div>" +
    '<div><div class="eyebrow">观测到的学生</div>' + (students.length ? students.map((s) => {
      const x = s.by_indicator.find((i) => i.indicator_id === id) || {};
      return '<div class="source-row">' + studentLink(s.student_id) + "<span>" + p(x.rate) + " · n=" + n(x.observed) + "</span></div>";
    }).join("") : '<div class="note">暂无学生观测。</div>') + "</div>" +
    '<div class="callout"><strong>口径</strong>满分率 = 满分记录 / 已评记录；低置信（n &lt; 5）只做观察依据。</div>' +
    "</div>";
};

export const drawerRecord = (id) => {
  const r = getRecord(id);
  if (!r) return empty({ title: "记录不存在", text: id });
  return '<div class="stack">' +
    '<div class="row">' + badge(r.student_id, "brand") + statusBadge(r.status) + badge(r.node_id, "neutral") + materialChip(r.material_id) + "</div>" +
    '<div class="grid grid-2">' +
    '<div class="card" style="box-shadow:none"><div class="kpi-label">得分 / 满分</div><div class="kpi-value">' + n(r.score, 1) + " <small>/ " + n(r.max_score, 1) + "</small></div>" +
    progress(recordRate(r)) + "</div>" +
    '<div class="card" style="box-shadow:none"><div class="kpi-label">修订版本</div><div class="kpi-value">' + n(r.revision) + "</div>" +
    '<div class="note">同事件取最高修订。</div></div>' +
    "</div>" +
    '<div class="rule-item"><div class="rule-head">' + badge("记录 " + r.record_id, "neutral") + badge("提交 " + formatDate(r.submitted_at), "neutral") + "</div>" +
    '<div class="rule-body">主题 ' + esc(r.topic_id) + " · 节点 " + esc(r.node_id) + "</div></div>" +
    '<div class="row">' + studentLink(r.student_id, "查看学生画像 " + r.student_id) + "</div>" +
    '<div class="callout"><strong>隐私</strong>记录抽屉只展示评分与节点字段，不展示学生作答与参考答案。</div>' +
    "</div>";
};
