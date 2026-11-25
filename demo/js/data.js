/* 快照加载与派生索引。所有页面只从这里取数据。 */

import { clamp } from "./format.js";

const DEMO = typeof window !== "undefined" && window.DSH_DEMO === true;

export class SnapshotError extends Error {
  constructor(message, status = 0, code = "unknown", details = {}) {
    super(message);
    this.name = "SnapshotError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export const state = {
  snapshot: null,
  meta: {},
  docs: {},
  records: [],
  recordsById: new Map(),
  recordsByStudent: new Map(),
  recordsByMaterial: new Map(),
  students: [],
  studentById: new Map(),
  recByStudent: new Map(),
  cases: [],
  caseByStudent: new Map(),
  graph: null,
  topics: [],
  topicById: new Map(),
  indicatorMeta: new Map(),
  indicatorStats: new Map(),
  materialById: new Map(),
  materialIndicators: new Map(),
  classStats: [],
  classComparison: null,
  commonIssues: [],
  nodeList: [],
  qc: null,
  clean: null,
  guard: null,
  trace: null,
  filters: { group: "all", flag: "all", sort: "id", materialType: "all" },
  search: "",
  loading: false,
  error: null,
  lastLoadedAt: null,
  run: { state: "idle", started_at: null, finished_at: null, exit_code: null, log_tail: [] },
  pollTimer: null,
};

const groupBy = (items, keyFn) => {
  const map = new Map();
  for (const item of items) {
    const key = keyFn(item);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(item);
  }
  return map;
};

const mean = (values) => {
  const nums = values.map(Number).filter(Number.isFinite);
  if (!nums.length) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
};

const safeArray = (value) => (Array.isArray(value) ? value : []);

export const loadSnapshot = async () => {
  state.loading = true;
  state.error = null;
  const endpoint = DEMO ? new URL("../snapshot.json", import.meta.url).href : "/api/snapshot";
  const response = await fetch(endpoint, { cache: "no-store" });
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const err = body && body.error ? body.error : {};
    const e = new SnapshotError(
      err.message || "快照载入失败（HTTP " + response.status + "）",
      response.status,
      err.code || "http_error",
      err.details || {},
    );
    state.loading = false;
    state.error = e;
    throw e;
  }
  indexSnapshot(body);
  state.loading = false;
  state.lastLoadedAt = new Date();
  return body;
};

export const indexSnapshot = (snapshot) => {
  const docs = snapshot.docs || {};
  const diag = docs.diagnosis || {};
  const content = docs.content || {};
  const recs = docs.recommendations || {};
  const casesDoc = docs.cases || {};

  state.snapshot = snapshot;
  state.meta = snapshot.meta || {};
  state.docs = docs;
  state.graph = snapshot.graph || null;
  state.records = safeArray(snapshot.records);
  state.qc = docs.qc || null;
  state.clean = docs.clean || null;
  state.guard = docs.guard || null;
  state.trace = docs.trace || null;

  state.recordsById = new Map(state.records.map((r) => [r.record_id, r]));
  state.recordsByStudent = groupBy(state.records, (r) => r.student_id);
  state.recordsByMaterial = groupBy(state.records, (r) => r.material_id);

  state.students = safeArray(diag.student_level)
    .slice()
    .sort((a, b) => String(a.student_id).localeCompare(String(b.student_id), "zh-CN", { numeric: true }));
  state.studentById = new Map(state.students.map((s) => [s.student_id, s]));

  state.recByStudent = new Map(
    safeArray(recs.students).map((r) => [r.student_id, r]),
  );

  state.cases = safeArray(casesDoc.cases);
  state.caseByStudent = new Map(state.cases.map((c) => [c.student_id, c]));

  state.topics = safeArray(content.topics);
  state.topicById = new Map(state.topics.map((t) => [t.topic_id, t]));
  state.indicatorMeta = new Map();
  state.materialIndicators = new Map();
  for (const topic of state.topics) {
    for (const ind of safeArray(topic.indicators)) {
      state.indicatorMeta.set(ind.indicator_id, { ...ind, topic_id: topic.topic_id, topic: topic.topic });
      for (const mid of safeArray(ind.material_ids)) {
        if (!state.materialIndicators.has(mid)) state.materialIndicators.set(mid, []);
        state.materialIndicators.get(mid).push({ indicator_id: ind.indicator_id, observation: ind.observation, topic_id: topic.topic_id });
      }
    }
  }

  state.materialById = new Map(safeArray(content.materials_index).map((m) => [m.material_id, m]));

  state.classStats = safeArray((diag.group_level || {}).by_class);
  state.nodeList = safeArray((diag.data_scope || {}).nodes);
  state.indicatorStats = new Map(
    safeArray((diag.group_level || {}).by_indicator).map((x) => [x.indicator_id, x]),
  );
  state.classComparison = casesDoc.class_comparison || null;

  state.commonIssues = Array.from(state.indicatorStats.values())
    .filter((x) => x.rate !== null && x.rate !== undefined && (x.observed || 0) >= 10)
    .sort((a, b) => Number(a.rate) - Number(b.rate))
    .slice(0, 3);

  state.search = "";
  state.filters = { group: "all", flag: "all", sort: "id", materialType: "all" };
};

export const getStudent = (id) => state.studentById.get(id) || null;
export const getRecommendation = (id) => state.recByStudent.get(id) || null;
export const getCase = (id) => state.caseByStudent.get(id) || null;
export const getTopic = (id) => state.topicById.get(id) || null;
export const getIndicatorMeta = (id) => state.indicatorMeta.get(id) || null;
export const getMaterial = (id) => state.materialById.get(id) || null;
export const getRecord = (id) => state.recordsById.get(id) || null;
export const recordsOfStudent = (id) => state.recordsByStudent.get(id) || [];
export const recordsOfMaterial = (id) => state.recordsByMaterial.get(id) || [];

export const meanCoverage = (student) => {
  const cov = Object.values((student && student.observed && student.observed.coverage) || {});
  return mean(cov);
};

export const weakIndicators = (student) => {
  if (!student) return [];
  return safeArray(student.by_indicator)
    .filter((x) => x.rate !== null && x.rate !== undefined && Number(x.rate) < 0.6 && x.observed > 0)
    .sort((a, b) => {
      const ca = a.confidence === "low" ? 1 : 0;
      const cb = b.confidence === "low" ? 1 : 0;
      return ca - cb || Number(a.rate) - Number(b.rate) || Number(b.observed) - Number(a.observed);
    });
};

export const strongIndicators = (student) => {
  if (!student) return [];
  return safeArray(student.by_indicator)
    .filter((x) => x.rate !== null && x.rate !== undefined && Number(x.rate) >= 0.75 && x.observed >= 5)
    .sort((a, b) => Number(b.rate) - Number(a.rate) || Number(b.observed) - Number(a.observed));
};

export const studentSearchBlob = (student) => {
  if (student._blob) return student._blob;
  const parts = [student.student_id, student.group_id, ...safeArray(student.flags)];
  for (const ind of safeArray(student.by_indicator)) parts.push(ind.indicator_id);
  for (const ind of weakIndicators(student)) {
    const meta = getIndicatorMeta(ind.indicator_id);
    if (meta) parts.push(meta.observation);
  }
  const rec = getRecommendation(student.student_id);
  if (rec) {
    parts.push(...safeArray(rec.basis));
    for (const item of safeArray(rec.items)) parts.push(item.material_id, item.reason);
  }
  const recs = recordsOfStudent(student.student_id);
  for (const r of recs) parts.push(r.material_id, r.record_id);
  student._blob = parts.join(" ").toLowerCase();
  return student._blob;
};

export const filteredStudents = () => {
  const q = state.search.trim().toLowerCase();
  const group = state.filters.group;
  const flag = state.filters.flag;
  const sort = state.filters.sort;
  let rows = state.students.filter((s) => {
    if (group !== "all" && s.group_id !== group) return false;
    if (flag !== "all" && !safeArray(s.flags).includes(flag)) return false;
    if (q && !studentSearchBlob(s).includes(q)) return false;
    return true;
  });
  const sorters = {
    id: (a, b) => String(a.student_id).localeCompare(String(b.student_id), "zh-CN", { numeric: true }),
    overall_desc: (a, b) => (Number(b.score_rate.overall) || 0) - (Number(a.score_rate.overall) || 0),
    overall_asc: (a, b) => (Number(a.score_rate.overall) || 0) - (Number(b.score_rate.overall) || 0),
    coverage_desc: (a, b) => (meanCoverage(b) || 0) - (meanCoverage(a) || 0),
    records_desc: (a, b) => (b.observed.records || 0) - (a.observed.records || 0),
  };
  rows = rows.slice().sort(sorters[sort] || sorters.id);
  return rows;
};

export const allFlags = () => {
  const set = new Set();
  for (const s of state.students) for (const f of safeArray(s.flags)) set.add(f);
  return Array.from(set).sort();
};

export const allGroups = () => {
  const set = new Set(state.students.map((s) => s.group_id));
  return Array.from(set).sort();
};

export const classGapInfo = () => {
  const cmp = state.classComparison;
  if (cmp && cmp.gap) return cmp.gap;
  if (state.classStats.length >= 2) {
    const [a, b] = state.classStats;
    return {
      pair: [a.group_id, b.group_id],
      score_rate_gap: Number(a.score_rate_mean) - Number(b.score_rate_mean),
      coverage_gap: Number(a.coverage_mean) - Number(b.coverage_mean),
    };
  }
  return null;
};

export const maxClassIndicatorGap = () => {
  const rows = safeArray(state.classComparison && state.classComparison.by_indicator);
  let best = null;
  for (const row of rows) {
    const keys = Object.keys(row).filter((k) => k !== "indicator_id");
    if (keys.length < 2) continue;
    const a = row[keys[0]];
    const b = row[keys[1]];
    if (!a || !b || a.rate === null || b.rate === null) continue;
    const gap = Math.abs(Number(a.rate) - Number(b.rate));
    if (!best || gap > best.gap) best = { indicator_id: row.indicator_id, gap, pair: [keys[0], keys[1]], a, b };
  }
  return best;
};

export const classIndicatorRow = (indicatorId) => {
  const row = safeArray(state.classComparison && state.classComparison.by_indicator)
    .find((x) => x.indicator_id === indicatorId);
  return row || null;
};

export const filterMaterials = () => {
  const rows = Array.from(state.materialById.values());
  const type = state.filters.materialType;
  return rows
    .filter((m) => type === "all" || m.type === type)
    .sort((a, b) => String(a.material_id).localeCompare(String(b.material_id), "zh-CN", { numeric: true }));
};

export const materialTypes = () => {
  const set = new Set(Array.from(state.materialById.values()).map((m) => m.type));
  return Array.from(set).sort();
};

export const indicatorTopic = (indicatorId) => {
  const meta = getIndicatorMeta(indicatorId);
  return meta ? meta.topic_id : "—";
};

export const indicatorObservation = (indicatorId) => {
  const meta = getIndicatorMeta(indicatorId);
  return meta ? meta.observation : "";
};

export const indicatorMaterials = (indicatorId) => {
  const meta = getIndicatorMeta(indicatorId);
  return meta ? safeArray(meta.material_ids) : [];
};

export const recordRate = (r) => {
  if (!r || !r.max_score) return null;
  return clamp(Number(r.score) / Number(r.max_score));
};

export const formatStudentName = (id) => {
  const s = getStudent(id);
  return s ? s.student_id : id;
};
