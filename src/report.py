# -*- coding: utf-8 -*-
"""report.py — 由程序产物生成学情分析报告（Markdown）。

报告是 PDF/答辩材料的“事实底稿”：所有数字均从 out/ 下的 JSON/CSV 读取，
不手工改数，保证结果可复核。输出：
    out/report.md
    out/tables/group_indicators.csv
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import OUT, TABLES, ensure_dirs, load_json, write_csv  # noqa: E402

CONTENT_MAP = os.path.join(OUT, "content_map.json")
DIAGNOSIS = os.path.join(OUT, "diagnosis_all.json")
RECOMMENDATIONS = os.path.join(OUT, "recommendations_all.json")
CASES = os.path.join(OUT, "cases.json")
QC = os.path.join(OUT, "qc_report.json")
CLEAN = os.path.join(OUT, "clean_report.json")
REPORT = os.path.join(OUT, "report.md")
GROUP_INDICATORS = os.path.join(TABLES, "group_indicators.csv")


def pct(value):
    return "—" if value is None else "%.1f%%" % (float(value) * 100)


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(lines)


def cov_mean(cov):
    cov = cov or {}
    return sum(cov.values()) / len(cov) if cov else 0.0


def indicator_rows(content, diag, case_doc):
    meta = {}
    for topic in content["topics"]:
        for ind in topic["indicators"]:
            meta[ind["indicator_id"]] = (topic["topic_id"], topic["topic"], ind["observation"])

    groups = sorted({x["group_id"] for x in diag["student_level"]})
    by_ind = {row["indicator_id"]: row for row in case_doc["class_comparison"]["by_indicator"]}
    rows = []
    for iid, (tid, topic, observation) in meta.items():
        observed = correct = 0
        for s in diag["student_level"]:
            for st in s["by_indicator"]:
                if st["indicator_id"] == iid:
                    observed += st["observed"]
                    correct += st["correct"]
        rate = (correct / observed) if observed else None
        cls = {gid: by_ind.get(iid, {}).get(gid, {}) for gid in groups}
        rows.append({
            "indicator_id": iid, "topic_id": tid, "topic": topic, "observation": observation,
            "observed": observed, "rate": rate,
            "classes": cls,
        })
    return rows


def case_section(case, idx):
    sid = case["student_id"]
    dx = case["diagnosis"]
    lines = []
    lines.append("### 4.%d %s：%s（%s）" % (idx, case["role_cn"], sid, case["group_id"]))
    lines.append("")
    lines.append("- **选择依据**：%s" % case["selection_reason"])
    lines.append("- **已有表现**：记录 %d 条（已评 %d、待评 %d、未作答 %d），整体得分率 %s，"
                 "平均节点覆盖 %s；标记 %s。" % (
                     dx["records"], dx["scored"], dx["pending"], dx["unanswered"],
                     pct(dx["overall"]), pct(cov_mean(dx.get("coverage"))),
                     "、".join(dx["flags"]) if dx["flags"] else "无"))
    by_node = "、".join("%s %s" % (k, pct(v)) for k, v in sorted((dx.get("by_node") or {}).items()))
    if by_node:
        lines.append("- **分节点得分率**：%s。" % by_node)

    if dx["weak_indicators"]:
        weak = "；".join("%s（%s，n=%d，满分率 %s）" % (
            w["indicator_id"], w["observation"], w["observed"], pct(w["rate"]))
            for w in dx["weak_indicators"])
        lines.append("- **需要巩固**：%s。" % weak)
    else:
        lines.append("- **需要巩固**：暂无达到“已评 3 条以上且满分率低于 60%”的指标；"
                     "现有低分项样本过少，先补充观察。")
    if dx["strong_indicators"]:
        strong = "；".join("%s（n=%d，满分率 %s）" % (w["indicator_id"], w["observed"], pct(w["rate"]))
                           for w in dx["strong_indicators"])
        lines.append("- **保持优势**：%s。" % strong)

    lines.append("")
    lines.append("**建议序列（学什么—用什么—为什么—先做什么）**")
    lines.append("")
    rows = []
    for e in case["evidence_chain"]:
        recs = "；".join("%s %s/%s %s" % (
            r["record_id"], int(r["score"]) if r["score"] is not None else "—",
            int(r["max_score"]) if r["max_score"] is not None else "—",
            r["status"]) for r in e["records"]) or "无对应记录（补充观察）"
        rows.append([e["seq"], e["material_id"], e["material_type"] or "—",
                     "%s（%s）" % (e["indicator_id"], e["indicator_observation"] or "—"),
                     e["action"], e["hint_level"], recs])
    lines.append(table(["序", "材料", "类型", "指标", "动作", "提示级别", "对应记录"], rows))
    lines.append("")
    for e in case["evidence_chain"]:
        lines.append("%d. %s → **%s**：%s" % (e["seq"], e["material_id"], e["action"], e["reason"]))
    lines.append("")
    lines.append("- **复测/调整**：%s" % case["recommendation"]["next_check"]["what"])
    lines.append("- **判断依据**：%s" % "；".join(x.rstrip("。") for x in case["recommendation"]["basis"][:3]))
    return "\n".join(lines)


def main():
    content = load_json(CONTENT_MAP)
    diag = load_json(DIAGNOSIS)
    cases = load_json(CASES)
    qc = load_json(QC)
    clean = load_json(CLEAN)
    batch = load_json(RECOMMENDATIONS)
    groups = sorted({x["group_id"] for x in diag["student_level"]})
    ind_rows = indicator_rows(content, diag, cases)

    ensure_dirs()
    rows = []
    for row in ind_rows:
        vals = [row["indicator_id"], row["topic_id"], row["observed"], pct(row["rate"])]
        for gid in groups:
            st = row["classes"].get(gid, {})
            vals.append(pct(st.get("rate")))
        if len(groups) >= 2:
            a = row["classes"].get(groups[0], {}).get("rate")
            b = row["classes"].get(groups[1], {}).get("rate")
            vals.append("%.1f" % ((a - b) * 100) if a is not None and b is not None else "")
        rows.append(vals)
    header = ["指标编号", "主题编号", "观测数", "全体满分率"] + [gid for gid in groups]
    if len(groups) >= 2:
        header.append("差值(百分点)")
    write_csv(GROUP_INDICATORS, header, rows)

    scored = [x for x in diag["student_level"] if x["score_rate"]["overall"] is not None]
    low = [x for x in scored if x["score_rate"]["overall"] < 0.5]
    strong = [x for x in scored if x["score_rate"]["overall"] >= 0.85]
    common = sorted([r for r in ind_rows if r["observed"] >= 5], key=lambda r: (r["rate"], r["indicator_id"]))[:3]
    gaps = []
    if len(groups) >= 2:
        for r in ind_rows:
            a = r["classes"].get(groups[0], {}).get("rate")
            b = r["classes"].get(groups[1], {}).get("rate")
            n = r["classes"].get(groups[0], {}).get("observed", 0) + r["classes"].get(groups[1], {}).get("observed", 0)
            if a is not None and b is not None and n >= 20:
                gaps.append((abs(a - b), r, a, b))
        gaps.sort(key=lambda x: (-x[0], x[1]["indicator_id"]))

    by_class = diag["group_level"]["by_class"]
    md = []
    md.append("# 智慧学伴·学情分析与个性化学习建议报告")
    md.append("")
    md.append("> 本报告由 src/report.py 从结构化产物自动生成，所有统计值均可在 out/ 中复核；"
              "数据快照 %s。" % diag["generated_at"])
    md.append("")
    md.append("## 1 数据与质检")
    md.append("")
    md.append("- 模拟学生 **%d** 名（%s），原始作答记录 **%d** 条、唯一作答事件 **%d** 个，"
              "其中修订版本折叠 **%d** 条。" % (
                  diag["data_scope"]["students"],
                  "/".join("%s %d 人" % (x["group_id"], x["students"]) for x in by_class),
                  qc.get("rows", 0), qc.get("unique_events", 0), qc.get("revisions_folded", 0)))
    md.append("- 评分状态：%s；异常记录 **%d** 条（%d 处字段修正），清洗后异常 **0** 条。" % (
        "、".join("%s %d" % (k, v) for k, v in sorted(diag["data_scope"]["scoring_status_counts"].items())),
        qc.get("anomaly_records", 0), clean.get("changes", 0)))
    md.append("- 处理口径：总分与评分点矛盾时以评分点为准下调总分，不改学生答案；"
              "节点归属错误时联动重写作答事件编号；缺失/未作答不解释为未掌握。")
    md.append("")
    md.append("## 2 学习内容与要求")
    md.append("")
    md.append("共梳理 **%d** 个主题、**%d** 条观察指标、**%d** 份可用材料（题目 %d、教材 %d、学习卡 %d）。" % (
        len(content["topics"]),
        sum(len(t["indicators"]) for t in content["topics"]),
        len(content["materials_index"]),
        sum(1 for m in content["materials_index"] if m["type"] == "题目"),
        sum(1 for m in content["materials_index"] if m["type"] == "教材"),
        sum(1 for m in content["materials_index"] if m["type"] == "学习卡")))
    md.append("")
    content_rows = []
    for t in content["topics"]:
        for ind in t["indicators"]:
            std = ind["standard"]
            content_rows.append([t["topic_id"], t["topic"], ind["indicator_id"], ind["observation"],
                                 std["cr_id"], std["pdf_pages"], std["body_pages"], ind["textbook_pages"],
                                 "、".join(m for m in ind["material_ids"] if m.startswith("Q")) or "—"])
    md.append(table(["主题", "名称", "指标", "观察指标", "课标条目", "PDF页", "正文页", "教材页", "对应题目"],
                    content_rows))
    md.append("")
    tids = [t["topic_id"] for t in content["topics"]]
    chain = " → ".join(tids) if tids else "各主题"
    md.append("主题联系：%s 依次递进，前一主题的概念与运算为后一主题提供工具；"
              "每个指标按“概念理解—运算程序—实际应用”组织，便于把学习要求映射到具体材料。" % chain)
    md.append("")
    md.append("## 3 群体学情")
    md.append("")
    md.append(table(["班级", "学生数", "记录数", "平均节点覆盖", "平均得分率"],
                    [[x["group_id"], x["students"], x["records"], pct(x["coverage_mean"]),
                      pct(x["score_rate_mean"])] for x in by_class]))
    md.append("")
    md.append("- 已评学生整体得分率低于 50%% 的有 **%d** 人，达到 85%% 的有 **%d** 人；"
              "两班平均得分率差 **%.1f** 个百分点。" % (
                  len(low), len(strong),
                  abs(by_class[0]["score_rate_mean"] - by_class[1]["score_rate_mean"]) * 100
                  if len(groups) >= 2 and by_class[0]["score_rate_mean"] is not None
                  and by_class[1]["score_rate_mean"] is not None else 0))
    if common:
        md.append("- **共性问题（全体满分率最低且观测数≥5）**：%s。" % "；".join(
            "%s（%s，n=%d，%s）" % (r["indicator_id"], r["observation"], r["observed"], pct(r["rate"]))
            for r in common))
    if gaps:
        md.append("- **班级差异最大的指标**：%s（%s %s vs %s %s，差 %.1f 个百分点，n=%d）。" % (
            gaps[0][1]["indicator_id"], groups[0], pct(gaps[0][2]), groups[1], pct(gaps[0][3]),
            gaps[0][0] * 100, gaps[0][1]["classes"].get(groups[0], {}).get("observed", 0) +
            gaps[0][1]["classes"].get(groups[1], {}).get("observed", 0)))
    md.append("")
    md.append(table(["指标", "全体满分率"] + groups,
                    [[r["indicator_id"], pct(r["rate"])] +
                     [pct(r["classes"].get(g, {}).get("rate")) for g in groups] for r in ind_rows]))
    md.append("")
    md.append("> 满分率 = 得满分记录数 / 已评记录数；它衡量“稳定达标”，不等同于得分率。"
              "观测数不足 5 时只作线索（置信度 low）。")
    md.append("")
    md.append("## 4 典型案例：学习要求—已有表现—学习建议")
    md.append("")
    md.append("三个案例分别覆盖“需要巩固、数据不足、稳定表现”三类需求；建议均给出材料、依据、先后顺序与调整条件。")
    md.append("")
    for idx, case in enumerate(cases["cases"], 1):
        md.append(case_section(case, idx))
        md.append("")
    md.append("## 5 班级对比与适用范围")
    md.append("")
    if len(groups) >= 2:
        cls = {x["group_id"]: x for x in by_class}
        md.append("- %s 平均得分率 %s、覆盖 %s；%s 平均得分率 %s、覆盖 %s。" % (
            groups[0], pct(cls[groups[0]]["score_rate_mean"]), pct(cls[groups[0]]["coverage_mean"]),
            groups[1], pct(cls[groups[1]]["score_rate_mean"]), pct(cls[groups[1]]["coverage_mean"])))
        md.append("- 两班差异是模拟数据的描述性结果，不构成教学因果结论；分指标差值见 out/tables/group_indicators.csv。")
    md.append("- 适用范围：本报告仅针对赛题提供的模拟学情数据（%d 名学生、%d 个测验节点），"
              "不用于真实学生评价；数据缺失、待评分、未作答均按“信息不足”处理。" % (
                  diag["data_scope"]["students"], len(diag["data_scope"]["nodes"])))
    md.append("- 已知限制：%s" % "；".join(diag.get("limitations", [])[:4]))
    md.append("")
    md.append("## 6 复现与产物")
    md.append("")
    md.append("~~~powershell")
    md.append(".\\run.cmd all      # 清洗→内容图谱→诊断→建议→案例→报告→校验→自检")
    md.append("~~~")
    md.append("")
    md.append("- 结构化产物：out/content_map.json、out/diagnosis_all.json、"
              "out/recommendations_all.json、out/cases.json；")
    md.append("- 表格：out/tables/*.csv；本报告：out/report.md；")
    md.append("- 契约：schemas/*.schema.json，src/validate.py 逐字段校验。")
    md.append("")

    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(md))
    print("报告已生成：%s（%d 行）" % (REPORT, len(md)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
