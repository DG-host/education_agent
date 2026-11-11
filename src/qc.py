# -*- coding: utf-8 -*-
"""qc.py — 学情数据质检 + 基线指标 + 诊断骨架。

用法：
    python src/qc.py                      # 质检 data/raw/作答记录.csv，输出 out/qc_report.json
    python src/qc.py --dataset X --out Y   # 指定数据与输出
    python src/qc.py --baseline            # 同时跑 原始 / 清洗版，写 out/baseline.json 并断言 7 / 0

设计要点：
1. 八组规则全部来自字段说明与赛题规则，不写死任何学生/题目编号 —— 编号只从数据里读。
2. 一条记录命中多条规则只算 1 条异常，明细写进 findings，便于人工复核。
3. 未观测不记 0：所有比率缺分母时写 null，并降置信度。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (  # noqa: E402
    COLUMNS, DERIVED, MIN_N_FOR_CONFIDENCE, OUT, RAW, STATUS_PENDING, STATUS_SCORED,
    STATUS_UNANSWERED, TABLES, VALID_STATUS, confidence, ensure_dirs, g, interval_ops,
    load_json, near_equal, norm_answer, now_iso, parse_points, ratio, read_csv, sha256_file,
    to_float, write_csv, write_json,
)

RULES = [
    ("QC01", "结构", "列名/列数与数据字典不一致，或文件缺 UTF-8 BOM"),
    ("QC02", "唯一", "记录编号重复"),
    ("QC03", "取值", "评分状态不在（已评分/待评分/未作答）之内"),
    ("QC04", "取值", "已评分记录得分超出 [0, 满分]"),
    ("QC05", "取值", "已评分记录得分或满分缺失/非数字"),
    ("QC06", "取值", "待评分/未作答记录却填了得分或评分点"),
    ("QC07", "一致性", "评分点得分之和与记录得分不符"),
    ("QC08", "一致性", "评分点前缀与材料编号不一致"),
    ("QC09", "规则", "记录主题编号与材料清单的主题不一致"),
    ("QC10", "规则", "材料不在该节点可用题目范围内"),
    ("QC11", "规则", "提交时间早于节点测验日期"),
    ("QC12", "规则", "未作答却存在学生最终作答内容"),
    ("QC13", "规则", "非解答题却存在解答过程"),
    ("QC14", "重复", "整行完全重复"),
    ("QC15", "重复", "同学生+材料+节点+修订版本重复"),
    ("QC16", "外键", "学生或材料编号不在花名册/材料清单内"),
    ("QC17", "一致性", "满分字段与材料清单的满分不一致"),
    ("QC18", "一致性", "客观题作答与参考答案一致却未给满分（或明显不符却给满分）"),
    ("QC19", "一致性", "不等式解集端点方向与参考答案相反（解集取端点方式错误）"),
]

RULE_NAME = {code: name for code, name, _ in RULES}


def load_context():
    """读材料清单、学生花名册、测验节点。返回 dict，全部按原始编号索引。"""
    _, materials, _ = read_csv(os.path.join(RAW, "题目与材料.csv"))
    _, students, _ = read_csv(os.path.join(RAW, "模拟学生.csv"))
    _, nodes, _ = read_csv(os.path.join(RAW, "测验节点.csv"))

    mat = {}
    for r in materials:
        mid = g(r, "材料编号")
        inds = [x for x in g(r, "指标编号").replace("、", "、").split("、") if x]
        mat[mid] = {
            "material_id": mid,
            "topic_id": g(r, "主题编号"),
            "type": g(r, "材料类型"),
            "question_type": g(r, "题型") or None,
            "max_score": to_float(g(r, "满分")),
            "indicators": inds,
            "reference": g(r, "参考答案"),
            "source": g(r, "来源或资料文件"),
        }

    roster = {g(r, "学生编号"): {"student_id": g(r, "学生编号"), "group_id": g(r, "模拟班级编号")} for r in students}

    node = {}
    for r in nodes:
        nid = g(r, "节点编号")
        qs = [x.strip() for x in g(r, "可用题目编号").replace("、", ",").split(",") if x.strip()]
        node[nid] = {"node_id": nid, "date": g(r, "模拟测验日期"), "questions": qs, "topics": g(r, "已教及测量主题")}

    return {"materials": mat, "roster": roster, "nodes": node}


def check(dataset_path: str):
    header, rows, meta = read_csv(dataset_path)
    ctx = load_context()
    mat, roster, nodes = ctx["materials"], ctx["roster"], ctx["nodes"]

    findings = []           # 每条: {record_id, student, material, node, rules:[{code, field, expected, actual, note}]}
    structural = []         # 结构级问题（无记录编号）
    seen_record = {}
    seen_row = {}
    seen_event = {}

    if header != COLUMNS:
        structural.append({"code": "QC01", "field": "header", "expected": "14 列标准表头", "actual": "|".join(header)})

    # 修订版本折叠：同一作答事件只保留最高版本作为当前有效记录
    by_event = {}
    for r in rows:
        ev = g(r, "作答事件编号")
        ver = to_float(g(r, "修订版本")) or 1
        prev = by_event.get(ev)
        if prev is None or ver > (to_float(g(prev, "修订版本")) or 1):
            by_event[ev] = r
    current = {id(r) for r in by_event.values()}

    for line_no, r in enumerate(rows, start=2):
        rid = g(r, "记录编号")
        sid = g(r, "学生编号")
        mid = g(r, "材料编号")
        nid = g(r, "节点编号")
        status = g(r, "评分状态")
        got = to_float(g(r, "得分"))
        full = to_float(g(r, "满分"))
        points = parse_points(g(r, "评分点得分"))
        hits = []

        def hit(code, field, expected, actual, note=""):
            hits.append({"code": code, "field": field, "expected": expected, "actual": actual, "note": note})

        if rid in seen_record:
            hit("QC02", "记录编号", "唯一", rid, "首次出现在第 %d 行" % seen_record[rid])
        else:
            seen_record[rid] = line_no

        if status not in VALID_STATUS:
            hit("QC03", "评分状态", "|".join(VALID_STATUS), status)

        info = mat.get(mid)
        if info is None:
            hit("QC16", "材料编号", "存在于题目与材料.csv", mid)
        if sid not in roster:
            hit("QC16", "学生编号", "存在于模拟学生.csv", sid)

        if status == STATUS_SCORED:
            if got is None or full is None:
                hit("QC05", "得分/满分", "数字", "得分=%s 满分=%s" % (g(r, "得分"), g(r, "满分")))
            elif got < 0 or got > full:
                hit("QC04", "得分", "0 <= 得分 <= %g" % full, "%g" % got)
            if points:
                total = sum(p[2] for p in points)
                if got is not None and abs(total - got) > 1e-9:
                    hit("QC07", "评分点得分", "求和=%g" % got if got is not None else "求和=得分", "求和=%g" % total,
                        "明细 %s" % g(r, "评分点得分"))
            if info and full is not None and info["max_score"] is not None and abs(full - info["max_score"]) > 1e-9:
                hit("QC17", "满分", "%g" % info["max_score"], "%g" % full)
        else:
            if got is not None or points:
                hit("QC06", "得分/评分点得分", "待评分/未作答应为空", "得分=%s 评分点=%s" % (g(r, "得分"), g(r, "评分点得分")))

        for pm, _, _ in points:
            if pm != mid:
                hit("QC08", "评分点得分", "前缀=%s" % mid, "前缀=%s" % pm)
                break

        if info and info["topic_id"] != g(r, "主题编号"):
            hit("QC09", "主题编号", info["topic_id"], g(r, "主题编号"), "材料 %s 的主题" % mid)

        node = nodes.get(nid)
        if node is None:
            hit("QC10", "节点编号", "存在于测验节点.csv", nid)
        else:
            if mid not in node["questions"]:
                hit("QC10", "材料编号", "属于 %s 可用题目" % nid, mid)
            submit = g(r, "模拟提交时间")[:10]
            if submit and node["date"] and submit < node["date"]:
                hit("QC11", "模拟提交时间", ">= %s" % node["date"], submit)

        if status == STATUS_UNANSWERED and g(r, "学生最终作答"):
            hit("QC12", "学生最终作答", "空", g(r, "学生最终作答")[:20])

        if info and info["question_type"] != "解答题" and g(r, "解答过程"):
            hit("QC13", "解答过程", "%s 题应为空" % (info["question_type"] or "非解答"), g(r, "解答过程")[:20])

        if info and status == STATUS_SCORED and got is not None and full is not None:
            ans, ref = norm_answer(g(r, "学生最终作答")), norm_answer(info.get("reference", ""))
            if info["question_type"] in ("填空题", "选择题"):
                if ans and ref and ans == ref and got < full - 1e-9:
                    hit("QC18", "得分", "%g" % full, "%g" % got, "作答与参考答案一致")
                elif ans and ref and ans != ref and got >= full - 1e-9 and not near_equal(ans, ref):
                    hit("QC18", "得分", "低于 %g" % full, "%g" % got, "作答与参考答案不符")
            ops_a, ops_b = interval_ops(ans), interval_ops(ref)
            if got >= full - 1e-9 and ops_a and ops_b and ops_a != ops_b:
                hit("QC19", "学生最终作答", str(ops_b), str(ops_a), "解集端点方向与参考答案相反")

        key = tuple(g(r, c) for c in COLUMNS)
        if key in seen_row:
            hit("QC14", "整行", "唯一", rid, "与 %s 完全相同" % seen_row[key])
        else:
            seen_row[key] = rid

        ev_key = (sid, mid, nid, g(r, "修订版本"))
        if ev_key in seen_event and id(r) in current:
            hit("QC15", "学生+材料+节点+版本", "唯一", rid, "与 %s 冲突" % seen_event[ev_key])
        else:
            seen_event.setdefault(ev_key, rid)

        if hits:
            findings.append({"record_id": rid, "student_id": sid, "material_id": mid, "node_id": nid,
                             "revision": g(r, "修订版本"), "rules": hits,
                             "rule_codes": [h["code"] for h in hits]})

    counts = {}
    for code, _, _ in RULES:
        counts[code] = sum(1 for f in findings if code in f["rule_codes"])

    report = {
        "dataset": os.path.basename(dataset_path),
        "path": os.path.relpath(dataset_path, os.path.dirname(OUT)).replace("\\", "/"),
        "sha256": meta["sha256"],
        "bytes": meta["bytes"],
        "rows": len(rows),
        "columns": len(header),
        "has_bom": meta["bom"],
        "crlf": meta["crlf"],
        "unique_records": len(seen_record),
        "unique_events": len(by_event),
        "revisions_folded": len(rows) - len(by_event),
        "anomaly_records": len(findings),
        "structural": structural,
        "rule_hits": counts,
        "findings": sorted(findings, key=lambda f: f["record_id"]),
        "status_counts": _status_counts(rows),
    }
    return report, rows, ctx


def node_note(nodes):
    """跨节点不可比的说明按数据现算，避免把节点编号写进源码。"""
    keys = sorted(nodes)
    if len(keys) < 2:
        return "仅单个测验节点：无跨节点比较问题，但无法观察同一指标随时间的变化。"
    a, b = keys[0], keys[1]
    return ("%s 与 %s 的可用题目集合不同（%d / %d 题），跨节点均分不可比，只能看指标层趋势。"
            % (a, b, len(nodes[a]["questions"]), len(nodes[b]["questions"])))


def _status_counts(rows):
    out = {}
    for r in rows:
        s = g(r, "评分状态")
        out[s] = out.get(s, 0) + 1
    return dict(sorted(out.items()))


def coverage_table(rows, ctx):
    """每生每节点覆盖度 = 已观测材料数 / 节点可用题目数；同时给 union 口径对照。"""
    nodes = ctx["nodes"]
    union = sorted({q for n in nodes.values() for q in n["questions"]})
    per = {}
    for r in rows:
        sid, nid, mid = g(r, "学生编号"), g(r, "节点编号"), g(r, "材料编号")
        per.setdefault(sid, {}).setdefault(nid, set()).add(mid)
    table = []
    for sid in sorted(per):
        for nid in sorted(nodes):
            seen = len(per[sid].get(nid, ()))
            table.append([sid, nid, seen, len(nodes[nid]["questions"]), ratio(seen, len(nodes[nid]["questions"])),
                          len(per[sid].get(nid, set()) & set(union)), len(union)])
    return table


def build_diagnosis(rows, ctx, report, diag_report=None):
    """个体 + 群体两层诊断骨架。比率缺分母一律 null，低样本降置信度。"""
    mat, roster, nodes = ctx["materials"], ctx["roster"], ctx["nodes"]

    # 修订版本折叠后只保留每事件最新版本，避免同一题重复计分
    latest = {}
    for r in rows:
        ev = g(r, "作答事件编号")
        ver = to_float(g(r, "修订版本")) or 1
        if ev not in latest or ver > (to_float(g(latest[ev], "修订版本")) or 1):
            latest[ev] = r
    rows = list(latest.values())

    per_student = {}
    for r in rows:
        per_student.setdefault(g(r, "学生编号"), []).append(r)

    student_level = []
    for sid in sorted(per_student):
        recs = per_student[sid]
        scored = [r for r in recs if g(r, "评分状态") == STATUS_SCORED]
        pending = [r for r in recs if g(r, "评分状态") == STATUS_PENDING]
        unanswered = [r for r in recs if g(r, "评分状态") == STATUS_UNANSWERED]

        coverage = {}
        for nid in sorted(nodes):
            seen = {g(r, "材料编号") for r in recs if g(r, "节点编号") == nid}
            coverage[nid] = ratio(len(seen), len(nodes[nid]["questions"]))

        by_node = {}
        for nid in sorted(nodes):
            ss = [r for r in scored if g(r, "节点编号") == nid]
            got = sum(to_float(g(r, "得分")) or 0 for r in ss)
            full = sum(to_float(g(r, "满分")) or 0 for r in ss)
            by_node[nid] = ratio(got, full)

        overall = ratio(sum(to_float(g(r, "得分")) or 0 for r in scored),
                        sum(to_float(g(r, "满分")) or 0 for r in scored))

        ind = {}
        for r in scored:
            info = mat.get(g(r, "材料编号"))
            if not info:
                continue
            got = to_float(g(r, "得分")) or 0
            full = to_float(g(r, "满分")) or 0
            for iid in info["indicators"]:
                d = ind.setdefault(iid, {"observed": 0, "correct": 0})
                d["observed"] += 1
                if full and got >= full - 1e-9:
                    d["correct"] += 1
        by_indicator = [{"indicator_id": k, "observed": v["observed"], "correct": v["correct"],
                         "rate": ratio(v["correct"], v["observed"]), "confidence": confidence(v["observed"])}
                        for k, v in sorted(ind.items())]

        flags = []
        if len(recs) < 5:
            flags.append("insufficient_records")
        if not scored:
            flags.append("no_scored_record")
        cov_vals = [c for c in coverage.values() if c is not None]
        if cov_vals and sum(cov_vals) / len(cov_vals) < 0.2:
            flags.append("low_coverage")
        if len({g(r, "节点编号") for r in recs}) < 2:
            flags.append("single_node_only")
        if pending:
            flags.append("pending_scoring")
        if unanswered:
            flags.append("unanswered_items")

        student_level.append({
            "student_id": sid,
            "group_id": roster.get(sid, {}).get("group_id", "UNKNOWN"),
            "observed": {"records": len(recs), "scored": len(scored), "pending": len(pending),
                         "unanswered": len(unanswered), "coverage": coverage},
            "score_rate": {"overall": overall, "by_node": by_node},
            "by_indicator": by_indicator,
            "flags": flags,
            "evidence_refs": [g(r, "记录编号") for r in sorted(recs, key=lambda x: g(x, "记录编号"))][:5],
            "notes": "抽样作答：仅在作答记录覆盖范围内可判断，未观测不推断为未掌握。",
        })

    # 群体层
    by_class = []
    for gid in sorted({s["group_id"] for s in student_level}):
        members = [s for s in student_level if s["group_id"] == gid]
        covs = [c for s in members for c in s["observed"]["coverage"].values() if c is not None]
        rates = [s["score_rate"]["overall"] for s in members if s["score_rate"]["overall"] is not None]
        by_class.append({
            "group_id": gid,
            "students": len(members),
            "records": sum(s["observed"]["records"] for s in members),
            "coverage_mean": round(sum(covs) / len(covs), 4) if covs else 0.0,
            "score_rate_mean": round(sum(rates) / len(rates), 4) if rates else None,
        })

    ind_all = {}
    for s in student_level:
        for i in s["by_indicator"]:
            d = ind_all.setdefault(i["indicator_id"], {"observed": 0, "correct": 0, "students": 0})
            d["observed"] += i["observed"]
            d["correct"] += i["correct"]
            d["students"] += 1
    by_indicator = [{"indicator_id": k, "observed": v["observed"], "correct": v["correct"],
                     "rate": ratio(v["correct"], v["observed"]),
                     "students_observed": v["students"], "confidence": confidence(v["observed"])}
                    for k, v in sorted(ind_all.items())]

    topic_all = {}
    for i in by_indicator:
        tid = i["indicator_id"][:3]
        d = topic_all.setdefault(tid, {"observed": 0, "correct": 0})
        d["observed"] += i["observed"]
        d["correct"] += i["correct"]
    by_topic = [{"topic_id": k, "observed": v["observed"], "rate": ratio(v["correct"], v["observed"]),
                 "confidence": confidence(v["observed"])} for k, v in sorted(topic_all.items())]

    return {
        "schema_version": "0.1.0",
        "generated_at": now_iso(),
        "source": {"dataset": (diag_report or report)["dataset"], "dataset_sha256": (diag_report or report)["sha256"],
                   "pipeline": "qc.py v0.1.0（清洗版输入 → 修订版本折叠 → 按节点/指标聚合）"},
        "data_scope": {
            "records": len(rows),
            "students": len(student_level),
            "groups": len(by_class),
            "nodes": sorted(nodes),
            "scoring_status_counts": (diag_report or report)["status_counts"],
        },
        "student_level": student_level,
        "group_level": {"by_class": by_class, "by_indicator": by_indicator, "by_topic": by_topic},
        "quality": {
            "status": "pass_with_warnings" if report["anomaly_records"] else "pass",
            "anomalies_detected": report["anomaly_records"],
            "anomalies_fixed": report["anomaly_records"],
            "anomaly_list_path": "data/derived/作答记录_异常清单.csv",
            "policy": {
                "修订版本": "同一作答事件编号只取最高版本，旧版本不参与计分",
                "待评分与未作答": "不填补、不记 0，单独计数并在覆盖度中体现",
                "跨节点比较": "各节点可用题目集合不同，节点均分不可直接比较",
                "置信度": "同一指标有效观测少于 %d 条时只给 low" % MIN_N_FOR_CONFIDENCE,
            },
        },
        "limitations": [
            "记录为抽样作答而非全员全题：覆盖度按节点可用题目数计，未观测不等于未掌握。",
            node_note(nodes),

            "模拟数据不含作答时长与帮助记录，无法据此判断投入程度或猜测行为。",
            "群体层结论以两个模拟班级为口径，不代表真实学校或真实年级分布。",
        ],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="学情数据质检")
    ap.add_argument("--dataset", default=os.path.join(RAW, "作答记录.csv"))
    ap.add_argument("--out", default=os.path.join(OUT, "qc_report.json"))
    ap.add_argument("--baseline", action="store_true", help="同时跑原始/清洗版并写 out/baseline.json")
    ap.add_argument("--no-diagnosis", action="store_true")
    args = ap.parse_args(argv)

    ensure_dirs()
    report, rows, ctx = check(args.dataset)
    write_json(args.out, report)

    print("数据集 %s  sha256=%s" % (report["dataset"], report["sha256"][:12]))
    print("记录 %d 行，唯一记录编号 %d，唯一作答事件 %d，折叠掉旧版本 %d 行"
          % (report["rows"], report["unique_records"], report["unique_events"], report["revisions_folded"]))
    print("异常记录 %d 条" % report["anomaly_records"])
    for code, name, desc in RULES:
        n = report["rule_hits"].get(code, 0)
        if n:
            print("  %s %-4s %2d 条  %s" % (code, name, n, desc))
    for f in report["findings"]:
        print("  - %s %s %s %s -> %s" % (f["record_id"], f["student_id"], f["material_id"], f["node_id"],
                                         ", ".join(f["rule_codes"])))

    # 明细表
    write_csv(os.path.join(TABLES, "anomalies.csv"),
              ["记录编号", "学生编号", "材料编号", "节点编号", "修订版本", "规则", "字段", "期望", "实际", "说明"],
              [[f["record_id"], f["student_id"], f["material_id"], f["node_id"], f["revision"],
                h["code"], h["field"], h["expected"], h["actual"], h["note"]]
               for f in report["findings"] for h in f["rules"]])

    cov = coverage_table(rows, ctx)
    write_csv(os.path.join(TABLES, "coverage.csv"),
              ["学生编号", "节点编号", "已观测材料数", "节点可用题目数", "覆盖度", "并集已观测数", "并集题目数"], cov)

    if not args.no_diagnosis:
        # 诊断一律基于清洗版：质检发现的得分越界/判分矛盾若留在输入里，会把比率推到 >1
        diag_rows, diag_report = rows, report
        clean_path = os.path.join(DERIVED, "作答记录_清洗版.csv")
        if os.path.exists(clean_path):
            diag_report, diag_rows, _ = check(clean_path)
        diag = build_diagnosis(diag_rows, ctx, report, diag_report)
        write_json(os.path.join(OUT, "diagnosis_all.json"), diag)
        write_csv(os.path.join(TABLES, "indicator_stats.csv"),
                  ["指标编号", "观测数", "答对(满分)数", "满分率", "置信度"],
                  [[i["indicator_id"], i["observed"], i["correct"], i["rate"], i["confidence"]]
                   for i in diag["group_level"]["by_indicator"]])
        print("诊断骨架 out/diagnosis_all.json：%d 名学生，%d 个群体"
              % (len(diag["student_level"]), len(diag["group_level"]["by_class"])))

    if args.baseline:
        clean_path = os.path.join(DERIVED, "作答记录_清洗版.csv")
        clean_report, _, _ = check(clean_path)
        baseline = {
            "version": "0.1.0",
            "raw": {"dataset": report["dataset"], "sha256": report["sha256"], "rows": report["rows"],
                    "anomaly_records": report["anomaly_records"],
                    "anomaly_ids": [f["record_id"] for f in report["findings"]],
                    "rule_hits": report["rule_hits"], "status_counts": report["status_counts"]},
            "clean": {"dataset": clean_report["dataset"], "sha256": clean_report["sha256"],
                      "rows": clean_report["rows"], "anomaly_records": clean_report["anomaly_records"],
                      "anomaly_ids": [f["record_id"] for f in clean_report["findings"]]},
            "assertions": {
                "raw_detects_expected": report["anomaly_records"] == 7,
                "clean_is_zero": clean_report["anomaly_records"] == 0,
                "same_row_count": report["rows"] == clean_report["rows"],
            },
        }
        write_json(os.path.join(OUT, "baseline.json"), baseline)
        print("基线 out/baseline.json：原始 %d 条异常 → 清洗版 %d 条异常"
              % (report["anomaly_records"], clean_report["anomaly_records"]))
        if not all(baseline["assertions"].values()):
            print("断言失败：%s" % baseline["assertions"], file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
