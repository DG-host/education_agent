# -*- coding: utf-8 -*-
"""content_map.py — 任务1：把课程要求、材料清单、测验节点拼成可机读的内容地图。

产出：
    out/content_map.json          符合 schemas/content_map.schema.json
    out/content_matrix_draft.csv  材料 × 指标 的草稿矩阵，供内容官人工复核

原则：编号全部沿用赛题原始编号；指标归属只从材料表读取，不从题干猜。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (  # noqa: E402
    OUT, RAW, TABLES, ensure_dirs, g, read_csv, sha256_file, to_int, write_csv, write_json,
)

FILES_FOR_HASH = ["课程要求.csv", "题目与材料.csv", "测验节点.csv", "作答记录.csv"]


def split_ids(text: str):
    return [x.strip() for x in (text or "").replace("、", ",").split(",") if x.strip()]


def build():
    _, req, _ = read_csv(os.path.join(RAW, "课程要求.csv"))
    _, mats, _ = read_csv(os.path.join(RAW, "题目与材料.csv"))
    _, nodes, _ = read_csv(os.path.join(RAW, "测验节点.csv"))

    node_scope = {}
    for r in nodes:
        nid = g(r, "节点编号")
        for mid in split_ids(g(r, "可用题目编号")):
            node_scope.setdefault(mid, []).append(nid)

    materials_index = []
    by_indicator = {}
    for r in mats:
        mid = g(r, "材料编号")
        inds = split_ids(g(r, "指标编号"))
        materials_index.append({
            "material_id": mid,
            "type": g(r, "材料类型"),
            "topic_id": g(r, "主题编号") or None,
            "question_type": g(r, "题型") or None,
            "max_score": to_int(g(r, "满分")),
            "node_scope": node_scope.get(mid, []),
        })
        for iid in inds:
            by_indicator.setdefault(iid, []).append(mid)

    topics = []
    order = []
    for r in req:
        tid = g(r, "主题编号")
        if tid not in order:
            order.append(tid)
            topics.append({"topic_id": tid, "topic": g(r, "主题"), "goal": g(r, "主题目标"), "indicators": []})
        idx = order.index(tid)
        pages = g(r, "课标文件页／正文页").replace("／", "/").split("/")
        topics[idx]["indicators"].append({
            "indicator_id": g(r, "指标编号"),
            "observation": g(r, "观察指标"),
            "standard": {
                "cr_id": g(r, "课标整理编号"),
                "pdf_pages": pages[0].strip() if pages else "",
                "body_pages": pages[1].strip() if len(pages) > 1 else "",
            },
            "textbook_pages": g(r, "教材正文页"),
            "material_ids": sorted(by_indicator.get(g(r, "指标编号"), [])),
            "evidence_required": ["作答记录", "评分点得分", "节点可用题目"],
        })

    # 教材切片在材料表中未标主题，只能按「课程级证据」挂到全部指标，归属待人工判定
    if any(m["type"] == "教材" for m in materials_index):
        for t in topics:
            for ind in t["indicators"]:
                ind["evidence_required"].append("教材切片")

    no_indicator = [m["material_id"] for m in materials_index if not split_ids(
        next((g(r, "指标编号") for r in mats if g(r, "材料编号") == m["material_id"]), ""))]
    no_node = [m["material_id"] for m in materials_index if not m["node_scope"]]

    open_questions = []
    if no_indicator:
        open_questions.append(
            "%d 份材料在材料表中没有指标编号（%s），指标归属需内容官按切片正文人工判定后回填。"
            % (len(no_indicator), "、".join(no_indicator)))
    if no_node:
        open_questions.append(
            "%d 份材料未被任何测验节点纳入（%s），只能作为学习建议材料，不能作为学情证据。"
            % (len(no_node), "、".join(no_node)))
    open_questions.append("课标页码已按「PDF 页/正文页」拆分，答辩前需与课程标准原文逐条核对。")
    open_questions.append("学习卡 L 系列覆盖同主题全部指标，属复习型材料，不计入得分统计。")

    return {
        "schema_version": "0.1.0",
        "source": {
            "curriculum_requirements": "课程要求.csv",
            "materials": "题目与材料.csv",
            "nodes": "测验节点.csv",
            "files": {f: sha256_file(os.path.join(RAW, f)) for f in FILES_FOR_HASH},
        },
        "topics": topics,
        "materials_index": materials_index,
        "open_questions": open_questions,
    }


def matrix_rows(doc):
    """材料 × 指标 草稿矩阵：一行一份材料，列出归属指标与可用节点，供人工复核。"""
    rows = []
    ind_of = {}
    for t in doc["topics"]:
        for i in t["indicators"]:
            for mid in i["material_ids"]:
                ind_of.setdefault(mid, []).append(i["indicator_id"])
    for m in sorted(doc["materials_index"], key=lambda x: x["material_id"]):
        inds = ind_of.get(m["material_id"], [])
        rows.append([
            m["material_id"], m["topic_id"] or "未标注", m["type"], m["question_type"] or "",
            "" if m["max_score"] is None else m["max_score"],
            "、".join(sorted(inds)),
            "待归属" if not inds else "已归属",
            "、".join(m["node_scope"]) if m["node_scope"] else "未纳入测验",
            "是" if not inds else "否",
        ])
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成内容地图")
    ap.add_argument("--out", default=os.path.join(OUT, "content_map.json"))
    args = ap.parse_args(argv)

    ensure_dirs()
    doc = build()
    write_json(args.out, doc)

    rows = matrix_rows(doc)
    write_csv(os.path.join(TABLES, "content_matrix_draft.csv"),
              ["材料编号", "主题编号", "材料类型", "题型", "满分", "指标编号", "归属状态", "可用节点", "需人工复核"],
              rows)

    n_ind = sum(len(t["indicators"]) for t in doc["topics"])
    print("内容地图：%d 个主题 / %d 个指标 / %d 份材料" % (len(doc["topics"]), n_ind, len(doc["materials_index"])))
    for t in doc["topics"]:
        print("  %s %s：%d 个指标，材料 %d 份" % (t["topic_id"], t["topic"],
              len(t["indicators"]), len({m for i in t["indicators"] for m in i["material_ids"]})))
    print("  待归属材料 %d 份，未纳入测验 %d 份" % (sum(1 for r in rows if r[6] == "待归属"),
                                            sum(1 for r in rows if r[7] == "未纳入测验")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
