# -*- coding: utf-8 -*-
"""cases.py — 选择三类典型案例并展开“学习要求—已有表现—学习建议”证据链。

输出：
    out/cases.json                 三案例 + 班级对比（答辩/报告共用）
    out/tables/case_evidence.csv   每条建议对应的材料、指标、记录
    out/tables/class_summary.csv   两班总体对比
    out/tables/class_indicators.csv 分指标班级对比

案例选择规则（确定性）：
    1) 巩固型：已评记录 >= 10 中整体得分率最低者；
    2) 数据不足型：记录数 < 10 或带 insufficient_records 标志者中记录最少者；
    3) 稳定型：已评 >= 10 且覆盖达标者中，优先选尚未出现的班级，再取得分率最高者。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (  # noqa: E402
    DERIVED, OUT, STATUS_SCORED, TABLES, ensure_dirs, g, load_json, read_csv, to_float, to_int,
    write_csv, write_json,
)

CONTENT_MAP = os.path.join(OUT, "content_map.json")
DIAGNOSIS = os.path.join(OUT, "diagnosis_all.json")
RECOMMENDATIONS = os.path.join(OUT, "recommendations_all.json")
CLEAN_DATASET = os.path.join(DERIVED, "作答记录_清洗版.csv")
CASES_OUT = os.path.join(OUT, "cases.json")
EVIDENCE_TABLE = os.path.join(TABLES, "case_evidence.csv")
CLASS_SUMMARY = os.path.join(TABLES, "class_summary.csv")
CLASS_INDICATORS = os.path.join(TABLES, "class_indicators.csv")

ROLES = [
    ("remedial", "需要巩固", "已评记录 >= 10 中整体得分率最低，用于展示薄弱点定位到具体指标与材料。"),
    ("insufficient", "数据不足", "记录数 < 10 或带 insufficient_records 标志，用于说明“缺记录不等于未掌握”。"),
    ("stable", "稳定表现", "已评 >= 10 且覆盖达标，优先选另一个班级，用于展示变式/迁移与班级对照。"),
]


def pct(value):
    return "—" if value is None else "%.1f%%" % (float(value) * 100)


def fold(rows):
    latest = {}
    for row in rows:
        event = g(row, "作答事件编号")
        rev = to_int(g(row, "修订版本")) or 0
        old = latest.get(event)
        if old is None or rev > (to_int(g(old, "修订版本")) or 0):
            latest[event] = row
    return list(latest.values())


def coverage_mean(s):
    cov = s["observed"].get("coverage") or {}
    return sum(cov.values()) / len(cov) if cov else 0.0


def select_cases(students):
    chosen = []
    remaining = list(students)

    def take(role, label, reason, candidate):
        candidate = dict(candidate)
        candidate["_role"] = role
        candidate["_role_cn"] = label
        candidate["_selection_reason"] = reason
        chosen.append(candidate)
        remaining[:] = [x for x in remaining if x["student_id"] != candidate["student_id"]]
        return candidate

    pool = [s for s in remaining if s["observed"]["scored"] >= 10]
    remedial = min(pool, key=lambda s: ((s["score_rate"]["overall"]), s["student_id"]))
    take("remedial", "需要巩固",
         "已评 %d 条、整体得分率 %s，是需要优先巩固的低分案例。" % (
             remedial["observed"]["scored"], pct(remedial["score_rate"]["overall"])), remedial)

    pool = [s for s in remaining if s["observed"]["records"] < 10 or "insufficient_records" in s["flags"]]
    if not pool:
        pool = [s for s in remaining if s["observed"]["records"] <= 12]
    insufficient = min(pool, key=lambda s: (s["observed"]["records"], s["student_id"]))
    take("insufficient", "数据不足",
         "仅 %d 条记录、平均节点覆盖 %s，低于 5 条置信阈值，用来说明“缺记录不判未掌握”。" % (
             insufficient["observed"]["records"], pct(coverage_mean(insufficient))), insufficient)

    used_groups = {s["group_id"] for s in chosen}
    pool = [s for s in remaining if s["observed"]["scored"] >= 10 and coverage_mean(s) >= 0.2]
    balanced = [s for s in pool if s["group_id"] not in used_groups]
    if balanced:
        stable = max(balanced, key=lambda s: (s["score_rate"]["overall"], s["student_id"]))
    else:
        stable = max(pool, key=lambda s: (s["score_rate"]["overall"], s["student_id"]))
    take("stable", "稳定表现",
         "已评 %d 条、整体得分率 %s、平均覆盖 %s，作为稳定表现与迁移任务的对照。" % (
             stable["observed"]["scored"], pct(stable["score_rate"]["overall"]), pct(coverage_mean(stable))),
         stable)
    return chosen


def indicator_meta(content):
    meta = {}
    for topic in content["topics"]:
        for ind in topic["indicators"]:
            meta[ind["indicator_id"]] = {
                "topic_id": topic["topic_id"],
                "topic": topic["topic"],
                "observation": ind["observation"],
                "standard": ind["standard"],
                "materials": ind["material_ids"],
            }
    return meta


def class_stats(students, indicator_ids, groups):
    out = []
    for iid in indicator_ids:
        row = {"indicator_id": iid}
        for group in groups:
            observed = correct = n_students = 0
            for s in students:
                if s["group_id"] != group:
                    continue
                for st in s["by_indicator"]:
                    if st["indicator_id"] == iid:
                        observed += st["observed"]
                        correct += st["correct"]
                        n_students += 1
            row[group] = {
                "students": n_students,
                "observed": observed,
                "rate": (correct / observed) if observed else None,
            }
        out.append(row)
    return out


def build_evidence(item, kb, meta, record_index):
    refs = item["evidence_refs"]
    iid = next((r for r in refs if r.startswith("T")), None)
    if iid is None:
        iid = next((i for i, m in meta.items() if item["material_id"] in m["materials"]), "")
    material = kb["materials_index"].get(item["material_id"], {})
    records = []
    for ref in refs:
        if not ref.startswith("DR") or ref not in record_index:
            continue
        rec = record_index[ref]
        got, full = to_float(g(rec, "得分")), to_float(g(rec, "满分"))
        records.append({
            "record_id": ref,
            "node_id": g(rec, "节点编号"),
            "status": g(rec, "评分状态"),
            "score": got,
            "max_score": full,
            "rate": (got / full) if (got is not None and full) else None,
        })
    info = meta.get(iid, {})
    return {
        "seq": item["seq"],
        "material_id": item["material_id"],
        "material_type": material.get("type"),
        "question_type": material.get("question_type"),
        "topic_id": material.get("topic_id"),
        "indicator_id": iid,
        "indicator_observation": info.get("observation"),
        "standard": info.get("standard"),
        "action": item["action"],
        "hint_level": item["hint_level"],
        "reason": item["reason"],
        "evidence_refs": refs,
        "records": records,
        "expected_observation": item["expected_observation"],
        "adjust_condition": item["adjust_condition"],
    }


def main():
    content = load_json(CONTENT_MAP)
    diag = load_json(DIAGNOSIS)
    batch = load_json(RECOMMENDATIONS)
    _, rows, _ = read_csv(CLEAN_DATASET)
    record_index = {g(r, "记录编号"): r for r in fold(rows)}
    kb = {"materials_index": {m["material_id"]: m for m in content["materials_index"]}}
    meta = indicator_meta(content)
    rec_by_student = {r["student_id"]: r for r in batch["students"]}

    selected = select_cases(diag["student_level"])
    cases = []
    for s in selected:
        rec = rec_by_student[s["student_id"]]
        weak = sorted([x for x in s["by_indicator"] if (x.get("rate") or 0) < 0.6],
                      key=lambda x: ((x["rate"] or 0), -x["observed"], x["indicator_id"]))
        strong = sorted([x for x in s["by_indicator"] if (x.get("rate") or 0) >= 0.8 and x["observed"] >= 3],
                        key=lambda x: (-(x["rate"] or 0), x["indicator_id"]))
        cases.append({
            "role": s["_role"],
            "role_cn": s["_role_cn"],
            "student_id": s["student_id"],
            "group_id": s["group_id"],
            "selection_reason": s["_selection_reason"],
            "diagnosis": {
                "records": s["observed"]["records"],
                "scored": s["observed"]["scored"],
                "pending": s["observed"]["pending"],
                "unanswered": s["observed"]["unanswered"],
                "coverage": s["observed"]["coverage"],
                "overall": s["score_rate"]["overall"],
                "by_node": s["score_rate"]["by_node"],
                "flags": s["flags"],
                "weak_indicators": [
                    {"indicator_id": x["indicator_id"], "observation": meta[x["indicator_id"]]["observation"],
                     "observed": x["observed"], "rate": x["rate"], "confidence": x["confidence"]}
                    for x in weak[:4]
                ],
                "strong_indicators": [
                    {"indicator_id": x["indicator_id"], "observed": x["observed"], "rate": x["rate"]}
                    for x in strong[:3]
                ],
            },
            "recommendation": rec,
            "evidence_chain": [build_evidence(item, kb, meta, record_index) for item in rec["items"]],
        })

    groups = sorted({s["group_id"] for s in diag["student_level"]})
    indicator_ids = [iid for t in content["topics"] for iid in [x["indicator_id"] for x in t["indicators"]]]
    by_class = diag["group_level"]["by_class"]
    gap = None
    if len(by_class) >= 2:
        a, b = by_class[0], by_class[1]
        gap = {
            "pair": [a["group_id"], b["group_id"]],
            "score_rate_gap": (a["score_rate_mean"] - b["score_rate_mean"])
            if a["score_rate_mean"] is not None and b["score_rate_mean"] is not None else None,
            "coverage_gap": (a["coverage_mean"] - b["coverage_mean"])
            if a["coverage_mean"] is not None and b["coverage_mean"] is not None else None,
        }

    doc = {
        "schema_version": "0.1.0",
        "generated_at": diag["generated_at"],
        "selection_policy": [{"role": r, "label": label, "rule": rule} for r, label, rule in ROLES],
        "cases": cases,
        "class_comparison": {
            "by_class": by_class,
            "gap": gap,
            "by_indicator": class_stats(diag["student_level"], indicator_ids, groups),
        },
    }
    ensure_dirs()
    write_json(CASES_OUT, doc)

    ev_rows = []
    for c in cases:
        for e in c["evidence_chain"]:
            ev_rows.append([
                c["role_cn"], c["student_id"], e["seq"], e["material_id"],
                e["material_type"], e["question_type"], e["indicator_id"], e["action"],
                "；".join(e["evidence_refs"]),
                "；".join(r["record_id"] for r in e["records"]),
            ])
    write_csv(EVIDENCE_TABLE,
              ["案例类型", "学生编号", "序号", "材料编号", "材料类型", "题型", "指标编号", "建议动作", "证据编号", "记录编号"],
              ev_rows)

    write_csv(CLASS_SUMMARY,
              ["班级", "学生数", "记录数", "平均节点覆盖", "平均得分率"],
              [[x["group_id"], x["students"], x["records"], pct(x["coverage_mean"]), pct(x["score_rate_mean"])]
               for x in by_class])

    rows_out = []
    for row in doc["class_comparison"]["by_indicator"]:
        for group in groups:
            st = row[group]
            rows_out.append([row["indicator_id"], group, st["students"], st["observed"],
                             st["rate"] if st["rate"] is not None else ""])
    write_csv(CLASS_INDICATORS,
              ["指标编号", "班级", "观测学生数", "观测记录数", "满分率"], rows_out)

    print("已选案例：%s" % "、".join("%s(%s)" % (c["student_id"], c["role_cn"]) for c in cases))
    print("班级对比：%s" % "；".join("%s %s / 覆盖 %s" % (
        x["group_id"], pct(x["score_rate_mean"]), pct(x["coverage_mean"])) for x in by_class))
    if gap and gap["score_rate_gap"] is not None:
        print("得分率差（%s - %s）：%.1f 个百分点" % (
            gap["pair"][0], gap["pair"][1], gap["score_rate_gap"] * 100))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
