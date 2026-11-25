# -*- coding: utf-8 -*-
"""领域工具：把清洗、内容图谱、质检、诊断、建议、案例、报告、契约封装为 ToolSpec。"""
from __future__ import annotations

import os

import cases
import clean
import content_map as content
import guards as guard_mod
import qc
import recommend as rec
import report as report_mod
import validate as validate_mod
from common import OUT, TABLES, ensure_dirs, load_json, write_csv, write_json

from .registry import ToolError, ToolRegistry, ToolSpec

RAW_DATASET = "data/raw/作答记录.csv"
CLEAN_DATASET = "data/derived/作答记录_清洗版.csv"
CLEAN_REPORT = "out/clean_report.json"
CLEAN_CHANGES = "out/tables/clean_changes.csv"
CONTENT_MAP = "out/content_map.json"
CONTENT_MATRIX = "out/content_matrix_draft.csv"
QC_REPORT = "out/qc_report.json"
ANOMALIES = "out/tables/anomalies.csv"
COVERAGE = "out/tables/coverage.csv"
DIAGNOSIS = "out/diagnosis_all.json"
INDICATOR_STATS = "out/tables/indicator_stats.csv"
RECOMMENDATIONS = "out/recommendations_all.json"
RECOMMENDATION_SUMMARY = "out/tables/recommendation_summary.csv"
GUARD_REPORT = "out/guard_report.json"
CASES = "out/cases.json"
CASE_EVIDENCE = "out/tables/case_evidence.csv"
CLASS_SUMMARY = "out/tables/class_summary.csv"
CLASS_INDICATORS = "out/tables/class_indicators.csv"
REPORT = "out/report.md"
GROUP_INDICATORS = "out/tables/group_indicators.csv"
EXAMPLE_DIAGNOSIS = "examples/diagnosis_D01.json"
EXAMPLE_RECOMMENDATION = "examples/recommendation_D01.json"


def _abs(rel):
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        rel.replace("/", os.sep))


def run_clean(ctx):
    code, rep = clean.check(verbose=False)
    if code != 0:
        raise ToolError("清洗对账失败：未解决 %d 条" % len(rep.get("unresolved", [])))
    n_changes = rep.get("changes", 0)
    n_unresolved = len(rep.get("unresolved", []))
    evidence = [
        "清洗修正 %d 处字段、未解决 %d 条" % (n_changes, n_unresolved),
        "清洗版逐单元格一致=%s，变更记录一致=%s" % (
            rep.get("compare", {}).get("clean", {}).get("matches"),
            rep.get("compare", {}).get("change_log", {}).get("matches")),
    ]
    return {
        "summary": "清洗对账通过：%d 处修正" % n_changes,
        "metrics": {"changes": n_changes,
                    "unresolved": n_unresolved,
                    "qc_after": (rep.get("qc_after") or {}).get("anomaly_records")},
        "evidence": evidence,
    }


def run_content(ctx):
    ensure_dirs()
    doc = content.build()
    write_json(_abs(CONTENT_MAP), doc)
    write_csv(_abs(CONTENT_MATRIX),
              ["材料编号", "主题编号", "材料类型", "题型", "满分", "指标编号", "归属状态", "可用节点", "需人工复核"],
              content.matrix_rows(doc))
    n_ind = sum(len(t["indicators"]) for t in doc["topics"])
    return {
        "summary": "内容图谱：%d 主题 / %d 指标 / %d 材料" % (
            len(doc["topics"]), n_ind, len(doc["materials_index"])),
        "metrics": {"topics": len(doc["topics"]), "indicators": n_ind,
                    "materials": len(doc["materials_index"])},
        "evidence": ["课标条目与教材页已写入 content_map.json",
                     "待人工判定项 %d 条" % len(doc.get("open_questions", []))],
    }


def run_qc(ctx):
    code = qc.main(["--no-diagnosis"])
    if code != 0:
        raise ToolError("质检失败")
    rep = load_json(_abs(QC_REPORT))
    return {
        "summary": "质检：原始 %d 条 / 唯一事件 %d 个 / 异常记录 %d 条" % (
            rep["rows"], rep["unique_events"], rep["anomaly_records"]),
        "metrics": {"rows": rep["rows"], "unique_events": rep["unique_events"],
                    "revisions_folded": rep["revisions_folded"],
                    "anomaly_records": rep["anomaly_records"],
                    "rule_kinds": len(rep.get("rule_hits", {}))},
        "evidence": ["异常清单 out/tables/anomalies.csv",
                     "覆盖度 out/tables/coverage.csv"],
    }


def run_diagnose(ctx):
    raw = load_json(_abs(QC_REPORT))
    diag_report, diag_rows, diag_ctx = qc.check(_abs(CLEAN_DATASET))
    diag = qc.build_diagnosis(diag_rows, diag_ctx, raw, diag_report)
    write_json(_abs(DIAGNOSIS), diag)
    write_csv(_abs(INDICATOR_STATS),
              ["指标编号", "观测数", "答对(满分)数", "满分率", "置信度"],
              [[i["indicator_id"], i["observed"], i["correct"], i["rate"], i["confidence"]]
               for i in diag["group_level"]["by_indicator"]])
    return {
        "summary": "学情诊断：%d 名学生 / %d 个班级 / %d 条指标" % (
            len(diag["student_level"]), len(diag["group_level"]["by_class"]),
            len(diag["group_level"]["by_indicator"])),
        "metrics": {"students": len(diag["student_level"]),
                    "groups": len(diag["group_level"]["by_class"]),
                    "indicators": len(diag["group_level"]["by_indicator"]),
                    "quality": diag["quality"]["status"]},
        "evidence": ["诊断只读清洗版；缺失不判未掌握",
                     "限制 %d 条已写入 limitations" % len(diag.get("limitations", []))],
    }


def run_recommend(ctx):
    batch = rec.generate()
    write_json(_abs(RECOMMENDATIONS), batch)
    rec.write_summary(batch, load_json(_abs(DIAGNOSIS)))
    actions = {}
    for s in batch["students"]:
        for item in s["items"]:
            actions[item["action"]] = actions.get(item["action"], 0) + 1
    return {
        "summary": "学习建议：%d 名学生 / %d 条" % (len(batch["students"]), sum(actions.values())),
        "metrics": {"students": len(batch["students"]), "items": sum(actions.values()),
                    "actions": actions},
        "evidence": ["每条建议至少 1 个 evidence_refs（指标/记录/节点）",
                     "材料仅从内容图谱索引选择，不读取参考答案"],
    }


def run_guard(ctx):
    rep = guard_mod.check()
    if rep["status"] != "pass":
        raise ToolError("建议守卫失败：%s" % "；".join(rep["errors"][:3]))
    return {
        "summary": "守卫通过：%d 类检查" % len(rep["checks"]),
        "metrics": {"checks": len(rep["checks"]), "errors": 0},
        "evidence": ["%s=%s" % (c["name"], c["status"]) for c in rep["checks"]],
    }


def run_cases(ctx):
    code = cases.main()
    if code != 0:
        raise ToolError("案例生成失败")
    doc = load_json(_abs(CASES))
    return {
        "summary": "典型案例：%s" % "、".join("%s(%s)" % (c["student_id"], c["role_cn"]) for c in doc["cases"]),
        "metrics": {"cases": len(doc["cases"]),
                    "classes": len(doc["class_comparison"]["by_class"])},
        "evidence": ["每个案例含诊断摘录、建议序列、记录级证据链",
                     "班级对比 out/tables/class_indicators.csv"],
    }


def run_report(ctx):
    code = report_mod.main()
    if code != 0:
        raise ToolError("报告生成失败")
    path = _abs(REPORT)
    return {
        "summary": "分析报告：%d 字节" % os.path.getsize(path),
        "metrics": {"bytes": os.path.getsize(path)},
        "evidence": ["报告数字全部来自结构化产物，可回溯到 JSON/CSV"],
    }


def run_validate(ctx):
    code = validate_mod.main([])
    if code != 0:
        raise ToolError("契约校验失败")
    return {
        "summary": "契约校验：5 个文件通过",
        "metrics": {"files": 5},
        "evidence": ["content_map / diagnosis / recommendation / batch / 单生样例"],
    }


def build_registry():
    r = ToolRegistry()
    r.register(ToolSpec(
        "clean", "对账原始数据与清洗版，核对 10 处修正与变更记录",
        run_clean, consumes=(RAW_DATASET, CLEAN_DATASET),
        produces=(CLEAN_REPORT, CLEAN_CHANGES),
        evidence=("以评分点明细为准，不改答案",)))
    r.register(ToolSpec(
        "content", "生成学习内容与要求图谱",
        run_content, consumes=("data/raw/课程要求.csv", "data/raw/题目与材料.csv", "data/raw/测验节点.csv"),
        produces=(CONTENT_MAP, CONTENT_MATRIX),
        evidence=("课标条目与教材页可追溯",)))
    r.register(ToolSpec(
        "qc", "19 条规则质检并输出异常/覆盖表",
        run_qc, consumes=(RAW_DATASET,), produces=(QC_REPORT, ANOMALIES, COVERAGE),
        evidence=("异常记录逐条可核对",)))
    r.register(ToolSpec(
        "diagnose", "生成个体与群体学情诊断",
        run_diagnose, consumes=(CLEAN_DATASET, QC_REPORT),
        produces=(DIAGNOSIS, INDICATOR_STATS),
        evidence=("诊断输入为清洗版",)))
    r.register(ToolSpec(
        "recommend", "生成个性化学习建议批次",
        run_recommend, consumes=(CONTENT_MAP, DIAGNOSIS, CLEAN_DATASET),
        produces=(RECOMMENDATIONS, RECOMMENDATION_SUMMARY),
        evidence=("建议与指标/记录/节点绑定",)))
    r.register(ToolSpec(
        "guard", "校验建议的证据、置信度不变量、答案泄露与个人信息",
        run_guard, consumes=(CONTENT_MAP, DIAGNOSIS, RECOMMENDATIONS, CLEAN_DATASET),
        produces=(GUARD_REPORT,),
        evidence=("失败即阻断，不允许把不可核对建议交付",)))
    r.register(ToolSpec(
        "cases", "选择三类案例并展开证据链",
        run_cases, consumes=(CONTENT_MAP, DIAGNOSIS, RECOMMENDATIONS, CLEAN_DATASET),
        produces=(CASES, CASE_EVIDENCE, CLASS_SUMMARY, CLASS_INDICATORS),
        evidence=("案例覆盖不同学习需求",)))
    r.register(ToolSpec(
        "report", "生成 Markdown 学情分析报告",
        run_report, consumes=(CONTENT_MAP, DIAGNOSIS, CASES, QC_REPORT, CLEAN_REPORT),
        produces=(REPORT, GROUP_INDICATORS),
        evidence=("报告数字与 JSON/CSV 一致",)))
    r.register(ToolSpec(
        "validate", "按 JSON Schema 校验全部契约",
        run_validate, consumes=(CONTENT_MAP, DIAGNOSIS, RECOMMENDATIONS, EXAMPLE_DIAGNOSIS,
                                EXAMPLE_RECOMMENDATION, CASES),
        produces=(), evidence=("失败即阻断交付",)))
    return r
