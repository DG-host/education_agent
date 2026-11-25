# -*- coding: utf-8 -*-
"""clean.py — 可追溯清洗引擎。

用法：
    python src/clean.py --check     # 默认：对账（不写 data/derived）
    python src/clean.py --apply     # 写清洗版 + 变更记录（先备份）

设计要点：
1. 只自动修 ADR 已定义的 5 类可机判问题；其余进人工队列，严格模式阻断。
2. 每条修复都写 (记录编号, 字段, 前值, 后值, 规则, 依据)，可逐条复核。
3. --check 与既有清洗版/变更记录逐单元格对账，确保清洗可复现。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (  # noqa: E402
    COLUMNS, DERIVED, OUT, RAW, STATUS_SCORED, TABLES, ensure_dirs, g, interval_ops,
    near_equal, norm_answer, now_iso, parse_points, read_csv, sha256_file, to_float,
    write_csv, write_json,
)

RAW_DATASET = os.path.join(RAW, "作答记录.csv")
CLEAN_DATASET = os.path.join(DERIVED, "作答记录_清洗版.csv")
CHANGE_LOG = os.path.join(DERIVED, "作答记录_变更记录.csv")
CHANGE_HEADER = ["序号", "记录编号", "涉及字段", "修改前", "修改后", "判定依据"]

RULES = {
    "R1": "主题跟随材料",
    "R2": "节点与作答事件一致",
    "R3": "客观题答案一致但未满分",
    "R4": "不等式解集端点反向",
    "R5": "总分以评分点明细为准",
}


def fmt_num(value) -> str:
    if value is None:
        return ""
    f = float(value)
    if abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    return ("%g" % f)


def points_text(points) -> str:
    return "；".join("%sP%d=%s" % (m, i, fmt_num(v)) for m, i, v in points)


def _load_context():
    from qc import load_context
    return load_context()


def _add_change(changes, record_id, field, before, after, rule, basis):
    changes.append({
        "record_id": record_id,
        "field": field,
        "before": before,
        "after": after,
        "rule": rule,
        "basis": basis,
    })


def plan(rows, ctx):
    """返回 (清洗后行, 变更列表, 未解决列表)。按行顺序执行 R1→R5。"""
    mat, nodes = ctx["materials"], ctx["nodes"]
    out_rows = []
    changes = []
    unresolved = []

    for src in rows:
        row = dict(src)
        rid = g(row, "记录编号")
        sid = g(row, "学生编号")
        mid = g(row, "材料编号")
        info = mat.get(mid)

        def set_field(field, new, rule, basis):
            old = g(row, field)
            if old == new:
                return
            row[field] = new
            _add_change(changes, rid, field, old, new, rule, basis)

        # R1 主题跟随材料
        if info and info.get("topic_id") and g(row, "主题编号") != info["topic_id"]:
            set_field("主题编号", info["topic_id"], "R1",
                      "材料清单中该材料的主题为 %s" % info["topic_id"])

        # R2 节点与作答事件一致
        nid = g(row, "节点编号")
        node = nodes.get(nid)
        if node is None:
            unresolved.append({"record_id": rid, "rule": "R2", "reason": "节点不在测验节点表中"})
        elif mid not in node["questions"]:
            cands = [n for n in sorted(nodes) if mid in nodes[n]["questions"]]
            submit = g(row, "模拟提交时间")[:10]
            exact = [n for n in cands if g_date(nodes[n]) == submit]
            target = None
            if len(exact) == 1:
                target = exact[0]
            elif len(cands) == 1:
                target = cands[0]
            if target is None:
                unresolved.append({"record_id": rid, "rule": "R2",
                                   "reason": "可用节点候选不唯一或日期不匹配"})
            else:
                set_field("节点编号", target, "R2",
                          "该材料可用题目属于 %s，提交日与节点测验日一致" % target)
                set_field("作答事件编号", "%s-%s-%s" % (sid, target, mid), "R2",
                          "随节点编号联动，保持 学生-节点-材料 一致")

        status = g(row, "评分状态")
        got = to_float(g(row, "得分"))
        full = to_float(g(row, "满分"))
        points = parse_points(g(row, "评分点得分"))

        # R3 客观题答案一致但未满分
        if (status == STATUS_SCORED and info and info.get("question_type") in ("填空题", "选择题")
                and got is not None and full is not None):
            ans, ref = norm_answer(g(row, "学生最终作答")), norm_answer(info.get("reference", ""))
            if ans and ref and ans == ref and got < full - 1e-9:
                if len(points) <= 1:
                    set_field("得分", fmt_num(full), "R3", "作答与参考答案一致，应按满分计")
                    if points:
                        set_field("评分点得分", points_text([(points[0][0], points[0][1], full)]), "R3",
                                  "总分与评分点同步置满分")
                else:
                    unresolved.append({"record_id": rid, "rule": "R3",
                                       "reason": "多评分点记录答案一致但未满分，需人工拆分"})

        # 重新读取，供后两条规则使用
        got = to_float(g(row, "得分"))
        full = to_float(g(row, "满分"))
        points = parse_points(g(row, "评分点得分"))

        # R4 不等式解集端点反向
        if status == STATUS_SCORED and got is not None and full is not None and got >= full - 1e-9:
            ops_a = interval_ops(norm_answer(g(row, "学生最终作答")))
            ops_b = interval_ops(norm_answer(info.get("reference", "")) if info else "")
            if ops_a and ops_b and ops_a != ops_b:
                new_score = full - 1.0
                if new_score < 0:
                    unresolved.append({"record_id": rid, "rule": "R4", "reason": "满分不足 1 分"})
                elif not points:
                    unresolved.append({"record_id": rid, "rule": "R4", "reason": "无评分点可扣减"})
                else:
                    new_points = list(points)
                    idx = None
                    for i in range(len(new_points) - 1, -1, -1):
                        if new_points[i][2] > 0:
                            idx = i
                            break
                    if idx is None:
                        unresolved.append({"record_id": rid, "rule": "R4", "reason": "评分点均为 0"})
                    else:
                        m, pi, pv = new_points[idx]
                        new_points[idx] = (m, pi, pv - 1.0)
                        set_field("得分", fmt_num(new_score), "R4", "解集端点方向与参考答案相反，扣减 1 分")
                        set_field("评分点得分", points_text(new_points), "R4", "第 %d 个评分点同步扣减 1 分" % (idx + 1))

        # R5 总分以评分点明细为准
        got = to_float(g(row, "得分"))
        full = to_float(g(row, "满分"))
        points = parse_points(g(row, "评分点得分"))
        if status == STATUS_SCORED and points:
            total = sum(p[2] for p in points)
            if got is None or abs(total - got) > 1e-9:
                if full is not None and total > full + 1e-9:
                    unresolved.append({"record_id": rid, "rule": "R5", "reason": "评分点合计超过满分"})
                else:
                    set_field("得分", fmt_num(total), "R5", "评分点合计 %s 与总分不符，以评分点为准" % fmt_num(total))
        elif status == STATUS_SCORED and not points and (got is None or full is None or got < 0 or got > full + 1e-9):
            unresolved.append({"record_id": rid, "rule": "R5", "reason": "无评分点且总分越界，无法机判"})

        out_rows.append(row)

    return out_rows, changes, unresolved


def g_date(node):
    return node.get("date", "")


def _read_change_log(path):
    if not os.path.exists(path):
        return []
    _, rows, _ = read_csv(path)
    return [
        (g(r, "记录编号"), g(r, "涉及字段"), g(r, "修改前"), g(r, "修改后"))
        for r in rows
    ]


def compare_to_derived(rows, changes):
    """与既有清洗版/变更记录对账，返回报告片段。"""
    report = {"clean": {}, "change_log": {}}
    if not os.path.exists(CLEAN_DATASET):
        report["clean"] = {"exists": False, "matches": False, "diff_cells": []}
    else:
        header, old, meta = read_csv(CLEAN_DATASET)
        diffs = []
        if header != COLUMNS:
            diffs.append({"field": "header", "before": "|".join(header), "after": "|".join(COLUMNS)})
        if len(old) != len(rows):
            diffs.append({"field": "row_count", "before": len(old), "after": len(rows)})
        for a, b in zip(old, rows):
            for col in COLUMNS:
                if g(a, col) != g(b, col):
                    diffs.append({"record_id": g(b, "记录编号"), "field": col,
                                  "before": g(a, col), "after": g(b, col)})
        report["clean"] = {
            "exists": True,
            "path": "data/derived/作答记录_清洗版.csv",
            "sha256": meta["sha256"],
            "matches": not diffs,
            "diff_cells": diffs[:20],
            "diff_count": len(diffs),
        }

    if not os.path.exists(CHANGE_LOG):
        report["change_log"] = {"exists": False, "matches": False, "missing": [], "extra": []}
    else:
        old = _read_change_log(CHANGE_LOG)
        new = [(c["record_id"], c["field"], c["before"], c["after"]) for c in changes]
        old_set, new_set = set(old), set(new)
        report["change_log"] = {
            "exists": True,
            "path": "data/derived/作答记录_变更记录.csv",
            "matches": old_set == new_set,
            "missing": sorted(new_set - old_set),
            "extra": sorted(old_set - new_set),
            "rows": len(old),
        }
    return report


def build_report(rows, changes, unresolved, raw_meta, compare):
    return {
        "schema_version": "0.1.0",
        "generated_at": now_iso(),
        "source": {
            "dataset": "作答记录.csv",
            "sha256": raw_meta["sha256"],
            "rows": len(rows),
        },
        "policy": "以评分点明细为准；不改学生答案；主题/节点/事件编号联动；未解决项进人工队列",
        "rules": RULES,
        "rows": len(rows),
        "changes": len(changes),
        "change_records": changes,
        "unresolved": unresolved,
        "compare": compare,
    }


def write_change_table(changes):
    ensure_dirs()
    write_csv(os.path.join(TABLES, "clean_changes.csv"),
              ["序号", "记录编号", "涉及字段", "修改前", "修改后", "规则", "判定依据"],
              [[i + 1, c["record_id"], c["field"], c["before"], c["after"], c["rule"], c["basis"]]
               for i, c in enumerate(changes)])


def check(verbose=True):
    _, rows, raw_meta = read_csv(RAW_DATASET)
    ctx = _load_context()
    clean_rows, changes, unresolved = plan(rows, ctx)
    compare = compare_to_derived(clean_rows, changes)
    report = build_report(clean_rows, changes, unresolved, raw_meta, compare)

    # 既有清洗版的质检结果（若存在）
    qc_after = None
    if os.path.exists(CLEAN_DATASET):
        from qc import check as qc_check
        qc_report, _, _ = qc_check(CLEAN_DATASET)
        qc_after = {"anomaly_records": qc_report["anomaly_records"], "passed": qc_report["anomaly_records"] == 0}
    report["qc_after"] = qc_after

    ensure_dirs()
    write_json(os.path.join(OUT, "clean_report.json"), report)
    write_change_table(changes)

    ok = (not unresolved and compare["clean"].get("matches") and
          compare["change_log"].get("matches") and (qc_after is None or qc_after["passed"]))
    if verbose:
        print("清洗对账：变更 %d 处，未解决 %d 条" % (len(changes), len(unresolved)))
        print("  清洗版逐单元格一致：%s（差异 %d）" % (compare["clean"].get("matches"), compare["clean"].get("diff_count", 0)))
        print("  变更记录集合一致：%s（缺 %d / 多 %d）" % (
            compare["change_log"].get("matches"),
            len(compare["change_log"].get("missing", [])),
            len(compare["change_log"].get("extra", []))))
        if qc_after is not None:
            print("  清洗版质检异常：%d" % qc_after["anomaly_records"])
        for u in unresolved:
            print("  ! %s %s %s" % (u["record_id"], u["rule"], u["reason"]))
        if not ok:
            print("清洗对账失败", file=sys.stderr)
    return 0 if ok else 1, report


def apply():
    _, rows, raw_meta = read_csv(RAW_DATASET)
    ctx = _load_context()
    clean_rows, changes, unresolved = plan(rows, ctx)
    if unresolved:
        print("存在未解决项，拒绝写入：%d 条" % len(unresolved), file=sys.stderr)
        for u in unresolved:
            print("  ! %s %s %s" % (u["record_id"], u["rule"], u["reason"]), file=sys.stderr)
        return 1

    ensure_dirs()
    backup = os.path.join(DERIVED, "_history", now_iso().replace(":", "").replace("+", "_"))
    os.makedirs(backup, exist_ok=True)
    for src in (CLEAN_DATASET, CHANGE_LOG):
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(backup, os.path.basename(src)))

    fd, tmp = tempfile.mkstemp(prefix=".clean_", suffix=".csv", dir=DERIVED)
    os.close(fd)
    try:
        write_csv(tmp, COLUMNS, [[g(r, c) for c in COLUMNS] for r in clean_rows])
        from qc import check as qc_check
        qc_report, _, _ = qc_check(tmp)
        if qc_report["anomaly_records"] != 0:
            print("清洗后仍有 %d 条异常，拒绝写入" % qc_report["anomaly_records"], file=sys.stderr)
            return 1
        os.replace(tmp, CLEAN_DATASET)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    write_csv(CHANGE_LOG, CHANGE_HEADER,
              [[i + 1, c["record_id"], c["field"], c["before"], c["after"],
                "%s %s：%s" % (c["rule"], RULES[c["rule"]], c["basis"])]
               for i, c in enumerate(changes)])

    print("已写入 %s：%d 行，%d 处变更" % (os.path.relpath(CLEAN_DATASET, os.path.dirname(DERIVED)), len(clean_rows), len(changes)))
    print("变更记录 %s；备份 %s" % (os.path.relpath(CHANGE_LOG, os.path.dirname(DERIVED)), os.path.relpath(backup, os.path.dirname(DERIVED))))
    # 以正式文件再做一次对账
    code, _ = check(verbose=False)
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(description="学情数据可追溯清洗")
    ap.add_argument("--check", action="store_true", help="只对账，不写 data/derived（默认行为）")
    ap.add_argument("--apply", action="store_true", help="写清洗版与变更记录")
    args = ap.parse_args(argv)
    if args.apply:
        return apply()
    code, _ = check(verbose=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
