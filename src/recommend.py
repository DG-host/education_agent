# -*- coding: utf-8 -*-
"""recommend.py — 任务 3 个性化学习建议生成器。

输入（均由上游步骤产出）：
    out/content_map.json        任务 1：指标—材料对应
    out/diagnosis_all.json      任务 2：个体/群体诊断
    data/derived/作答记录_清洗版.csv  证据记录（已折叠修订版本）

输出：
    out/recommendations_all.json      40 名学生建议（批次契约）
    out/tables/recommendation_summary.csv
    examples/recommendation_<学生编号>.json  可选：单生样例（--example <学生编号>）

约束：
    * 每条建议必须挂 material_id + evidence_refs + hint_level + adjust_condition；
    * 不读取参考答案，从源头避免把答案写进建议；
    * generated_at 复用诊断时间戳，保证同输入输出字节一致。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (  # noqa: E402
    DERIVED, EXAMPLES, OUT, TABLES, STATUS_PENDING, STATUS_SCORED, STATUS_UNANSWERED,
    ensure_dirs, g, load_json, read_csv, sha256_file, to_float, to_int, write_csv, write_json,
)

CONTENT_MAP = os.path.join(OUT, "content_map.json")
DIAGNOSIS = os.path.join(OUT, "diagnosis_all.json")
CLEAN_DATASET = os.path.join(DERIVED, "作答记录_清洗版.csv")
BATCH_OUT = os.path.join(OUT, "recommendations_all.json")
SUMMARY_OUT = os.path.join(TABLES, "recommendation_summary.csv")

ACTION_CN = {"review": "复习", "practice": "练习", "variant": "变式", "observe": "观察"}
TYPE_RANK = {"选择题": 0, "填空题": 1, "解答题": 2}


def pct(value) -> str:
    if value is None:
        return "—"
    return "%.1f%%" % (float(value) * 100)


def _ratio(rec):
    got, full = to_float(g(rec, "得分")), to_float(g(rec, "满分"))
    if got is None or not full:
        return None
    return got / full


class Knowledge:
    """content_map 的只读索引。"""

    def __init__(self, content):
        self.content = content
        self.materials = {m["material_id"]: m for m in content["materials_index"]}
        self.indicators = {}
        self.indicator_order = []
        for topic in content["topics"]:
            for ind in topic["indicators"]:
                iid = ind["indicator_id"]
                self.indicators[iid] = {
                    "indicator_id": iid,
                    "topic_id": topic["topic_id"],
                    "observation": ind["observation"],
                    "materials": list(ind["material_ids"]),
                    "questions": [m for m in ind["material_ids"]
                                  if self.materials.get(m, {}).get("type") == "题目"],
                    "cards": [m for m in ind["material_ids"]
                              if self.materials.get(m, {}).get("type") == "学习卡"],
                }
                self.indicator_order.append(iid)

    def material(self, mid):
        return self.materials[mid]

    def qtype(self, mid):
        return self.materials.get(mid, {}).get("question_type") or "题目"

    def node_of(self, mid):
        scope = self.materials.get(mid, {}).get("node_scope") or []
        return scope[0] if scope else None


def fold_records(rows):
    latest = {}
    for row in rows:
        event = g(row, "作答事件编号")
        rev = to_int(g(row, "修订版本")) or 0
        old = latest.get(event)
        if old is None or rev > (to_int(g(old, "修订版本")) or 0):
            latest[event] = row
    return list(latest.values())


def pick_question(kb, iid, answered, used, quick=True, exclude=None, allow_used=False):
    ind = kb.indicators[iid]
    mids = [m for m in ind["questions"] if (allow_used or m not in used) and m != exclude]
    if not mids:
        return None

    def rank(mid):
        unseen = 0 if mid not in answered else 1
        qrank = TYPE_RANK.get(kb.qtype(mid), 3)
        return (unseen, qrank if quick else -qrank, mid)

    return sorted(mids, key=rank)[0]


def indicator_evidence(kb, iid, records, extra_mid=None):
    """指标 + 该指标最弱记录 + 节点，最多 3 个，全部符合 evidence_refs 正则。"""
    ind = kb.indicators[iid]
    mids = set(ind["materials"])
    related = [r for r in records if g(r, "材料编号") in mids]
    scored = [r for r in related if g(r, "评分状态") == STATUS_SCORED and _ratio(r) is not None]
    exact = [r for r in scored if g(r, "材料编号") == extra_mid]
    if exact:
        scored = exact
    scored.sort(key=lambda r: (_ratio(r), g(r, "记录编号")))
    refs = [iid]
    if scored:
        refs.append(g(scored[0], "记录编号"))
        node = g(scored[0], "节点编号")
    else:
        node = kb.node_of(extra_mid or (ind["questions"][0] if ind["questions"] else ind["materials"][0]))
    if node:
        refs.append(node)
    return refs[:3]


def build_student(kb, diag, s, records, group_mean):
    sid = s["student_id"]
    observed = s["observed"]
    overall = s["score_rate"]["overall"]
    stats = {x["indicator_id"]: x for x in s["by_indicator"]}
    observed_ids = set(stats)
    unanswered = [r for r in records if g(r, "评分状态") == STATUS_UNANSWERED]
    pending = [r for r in records if g(r, "评分状态") == STATUS_PENDING]
    answered = {g(r, "材料编号") for r in records if g(r, "评分状态") == STATUS_SCORED}
    used = set()
    items = []

    def add_item(mid, action, reason, evidence, hint, expected, adjust):
        if mid is None or mid in used or len(items) >= 6:
            return
        used.add(mid)
        items.append({
            "seq": len(items) + 1,
            "material_id": mid,
            "action": action,
            "reason": reason,
            "evidence_refs": evidence,
            "hint_level": hint,
            "expected_observation": expected,
            "adjust_condition": adjust,
        })

    def add_review(iid, why_prefix=""):
        ind = kb.indicators[iid]
        card = ind["cards"][0] if ind["cards"] else None
        if not card or card in used:
            return
        st = stats.get(iid, {"observed": 0, "rate": None, "confidence": "low"})
        if st["observed"] == 0:
            reason = "%s进入尚未观测的 %s（%s）：先回顾 %s 的概念与例题，再补充一次观察，不据此判定掌握。" % (
                why_prefix, iid, ind["observation"], card)
        else:
            reason = "%s%s（%s）观测 %d 条、满分率 %s，先回顾 %s 的概念与例题，重点看步骤而不是结论。" % (
                why_prefix, iid, ind["observation"], st["observed"], pct(st.get("rate")), card)
        add_item(card, "review", reason, indicator_evidence(kb, iid, records, card), "提示",
                 "能独立说出该指标的判定步骤，并指出自己上次卡在哪一步。",
                 "回顾后同类题正确率达到 70% 则进入练习；仍低于 50% 则换用教材对应页再讲一遍。")

    def add_practice(iid, action="practice", quick=True, exclude=None, why_prefix=""):
        ind = kb.indicators[iid]
        mid = pick_question(kb, iid, answered, used, quick=quick, exclude=exclude)
        if not mid:
            return None
        st = stats.get(iid)
        if st and st["observed"] > 0 and ("保持" in why_prefix or "迁移" in why_prefix):
            reason = "%s%s 的「%s」当前满分率 %s（n=%d）；用 %s（%s）换一个情境再练，检验能否稳定迁移。" % (
                why_prefix, iid, ind["observation"], pct(st["rate"]), st["observed"], mid, kb.qtype(mid))
        elif st and st["observed"] > 0:
            reason = "%s%s 的「%s」尚未稳定（满分率 %s，n=%d）；用 %s（%s）独立完成，按评分点自查。" % (
                why_prefix, iid, ind["observation"], pct(st["rate"]), st["observed"], mid, kb.qtype(mid))
        else:
            reason = "%s尚无 %s 的观测记录；用 %s（%s）补充一次独立观察，不据此直接判定掌握。" % (
                why_prefix, iid, mid, kb.qtype(mid))
        hint = "分步提示" if action == "practice" else "不给答案"
        add_item(mid, action, reason, indicator_evidence(kb, iid, records, mid), hint,
                 "能独立写出完整过程；若只看结果，记录正确率与卡住的步骤。",
                 "正确率低于 50% 回到学习卡补概念；达到 70% 再做同指标变式。")
        return mid

    def add_unanswered():
        for rec in sorted(unanswered, key=lambda r: g(r, "记录编号")):
            mid = g(rec, "材料编号")
            if mid not in kb.materials or mid in used:
                continue
            add_item(mid, "observe",
                     "记录 %s 为未作答，先用 %s（%s）独立尝试并写出思路，补齐观测后再判断，不直接视为未掌握。" % (
                         g(rec, "记录编号"), mid, kb.qtype(mid)),
                     [g(rec, "记录编号"), _iid_of(kb, mid), g(rec, "节点编号")],
                     "提示", "能给出至少一个可检验的解题入口，并说明卡在哪里。",
                     "若仍无法入手，先回到对应学习卡；若完成，按评分点核对并补一次同类题。")
            return True
        return False

    focus = None
    # 置信度闸门：n>=5 才把低满分率当作“需巩固”并安排练习/变式；
    # n<5 只安排复习与补充观察，避免把抽样波动写成结论（ADR D7）。
    weak = sorted([x for x in s["by_indicator"]
                   if x["observed"] >= 5 and x.get("rate") is not None and x["rate"] < 0.6],
                  key=lambda x: (x["rate"], -x["observed"], x["indicator_id"]))
    low_conf = sorted([x for x in s["by_indicator"]
                       if x["observed"] < 5 and x.get("rate") is not None and x["rate"] < 0.6],
                      key=lambda x: (x["rate"], x["indicator_id"]))
    uncovered = [iid for iid in kb.indicator_order if iid not in observed_ids]

    if observed["scored"] == 0:
        focus = kb.indicator_order[0]
        add_review(focus)
        add_practice(focus, action="observe")
        iid2 = kb.indicator_order[1]
        add_practice(iid2, action="observe")
    elif weak:
        focus = weak[0]["indicator_id"]
        add_review(focus)
        add_practice(focus)
        add_practice(focus, action="variant", quick=False, why_prefix="同指标变式：")
        if len(weak) > 1:
            second = weak[1]["indicator_id"]
            if kb.indicators[second]["cards"][0] != kb.indicators[focus]["cards"][0]:
                add_review(second)
            add_practice(second)
        if unanswered:
            add_unanswered()
        elif pending and len(items) < 6:
            rec = sorted(pending, key=lambda r: g(r, "记录编号"))[0]
            mid = g(rec, "材料编号")
            add_item(mid, "observe",
                     "记录 %s 待评分，暂不作为掌握依据；先观察 %s 的完成过程与步骤。" % (g(rec, "记录编号"), mid),
                     [g(rec, "记录编号"), _iid_of(kb, mid), g(rec, "节点编号")],
                     "提示", "能看到学生独立完成到哪一步、是否需要提示。",
                     "评分完成后用得分率替换本条观察；若低于 50% 转入对应指标复习。")
    elif low_conf:
        focus = low_conf[0]["indicator_id"]
        add_review(focus)
        add_practice(focus, action="observe")
        if len(low_conf) > 1:
            add_practice(low_conf[1]["indicator_id"], action="observe")
        if len(items) < 4:
            strong = [x for x in s["by_indicator"] if (x.get("rate") or 0) >= 0.8 and x["observed"] >= 5]
            if strong:
                add_practice(strong[0]["indicator_id"], action="variant", quick=False, why_prefix="保持已掌握指标：")
    else:
        if uncovered:
            focus = uncovered[0]
            add_review(focus)
            add_practice(focus, action="observe")
            if len(uncovered) > 1:
                add_practice(uncovered[1], action="observe")
            strong = [x for x in s["by_indicator"] if (x.get("rate") or 0) >= 0.8 and x["observed"] >= 5]
            if len(items) < 4 and strong:
                add_practice(strong[0]["indicator_id"], action="variant", quick=False, why_prefix="保持已掌握指标：")
        else:
            ranked = sorted([x for x in s["by_indicator"] if x.get("confidence") != "low"],
                            key=lambda x: ((x.get("rate") or 0), x["indicator_id"]))
            focus = ranked[0]["indicator_id"] if ranked else kb.indicator_order[0]
            if ranked:
                add_practice(focus, action="variant", quick=False, why_prefix="在稳定指标上做迁移：")
                add_practice(focus, action="variant", quick=False, why_prefix="换一个情境再迁移：")
            else:
                add_practice(focus, action="observe", why_prefix="观测仍不足：")
            add_review(focus)

    if not items:
        # 兜底：至少给一次观察，保证契约 items>=1
        focus = focus or kb.indicator_order[0]
        add_practice(focus, action="observe")

    focus_stat = stats.get(focus, {"observed": 0, "rate": None, "confidence": "low"})
    focus_obs = kb.indicators[focus]["observation"]

    # 明确不安排的材料
    not_rec = []
    strong_all = sorted([x for x in s["by_indicator"] if (x.get("rate") or 0) >= 0.8 and x["observed"] >= 5],
                        key=lambda x: (-(x["rate"] or 0), x["indicator_id"]))
    if strong_all:
        st = strong_all[0]
        mid = pick_question(kb, st["indicator_id"], answered, used, quick=False)
        if mid:
            not_rec.append({"material_id": mid,
                            "reason": "%s 满分率 %s（n=%d），本轮不重复同类题，把时间留给薄弱指标。" % (
                                st["indicator_id"], pct(st["rate"]), st["observed"])})
    if weak and len(not_rec) < 3:
        mid = pick_question(kb, focus, answered, used, quick=False)
        if mid:
            not_rec.append({"material_id": mid,
                            "reason": "%s 的步骤尚未稳定，暂不安排该综合题，避免一次跨太多步骤。" % focus})
    focus_ids = {_iid_of(kb, item["material_id"]) for item in items}
    if len(not_rec) < 3:
        later = [iid for iid in kb.indicator_order if iid not in observed_ids and iid not in focus_ids]
        if later:
            mid = pick_question(kb, later[0], answered, used, quick=True)
            if mid:
                not_rec.append({"material_id": mid,
                                "reason": "该生尚无 %s 的观测记录；本轮先处理前述薄弱点，该材料留到下一轮补充观察。" % later[0]})
    if not not_rec:
        mid = pick_question(kb, focus, answered, used, quick=False)
        if mid:
            not_rec.append({"material_id": mid,
                            "reason": "当前建议已覆盖主要薄弱点，该材料暂不重复安排。"})

    # 依据
    coverage = observed.get("coverage") or {}
    node_cov = "、".join("%s %s" % (node, pct(rate)) for node, rate in sorted(coverage.items()))
    basis = [
        "共 %d 条记录（已评 %d、待评 %d、未作答 %d），整体得分率 %s；节点覆盖 %s。" % (
            observed["records"], observed["scored"], observed["pending"], observed["unanswered"],
            pct(overall), node_cov or "暂无"),
    ]
    if focus_stat["observed"] > 0:
        basis.append("重点指标 %s（%s）：观测 %d 条、满分率 %s（置信度 %s）。" % (
            focus, focus_obs, focus_stat["observed"], pct(focus_stat.get("rate")), focus_stat.get("confidence", "low")))
    else:
        basis.append("重点指标 %s（%s）：尚无观测记录，先补充观察，不作掌握判断。" % (focus, focus_obs))
    if group_mean is not None and overall is not None:
        diff = (overall - group_mean) * 100
        basis.append("班级 %s 平均得分率 %s，该生%s %.1f 个百分点。" % (
            s["group_id"], pct(group_mean), "高于" if diff >= 0 else "低于", abs(diff)))
    flag_text = []
    if "insufficient_records" in s["flags"]:
        flag_text.append("记录数低于 5 条置信阈值，结论只作线索")
    if "low_coverage" in s["flags"]:
        flag_text.append("节点覆盖不足 20%，未覆盖内容不视为未掌握")
    if "unanswered_items" in s["flags"]:
        flag_text.append("存在未作答记录，按缺记录处理")
    if "pending_scoring" in s["flags"]:
        flag_text.append("存在待评分记录，暂不纳入得分率")
    if "single_node_only" in s["flags"]:
        flag_text.append("仅覆盖一个节点，跨节点表现待观察")
    if low_conf and low_conf[0]["indicator_id"] != focus:
        names = "、".join("%s（n=%d）" % (x["indicator_id"], x["observed"]) for x in low_conf[:2])
        basis.append("另有 %s仅有少量观测且未满分，暂不作为重点，先积累记录。" % names)
    if flag_text:
        basis.append("数据限制：" + "；".join(flag_text) + "。")

    check_mid = pick_question(kb, focus, answered, used, quick=True, allow_used=True)
    check_mid = check_mid or items[-1]["material_id"]
    next_check = {
        "when": "完成前 %d 项后（约 15–20 分钟）" % min(2, len(items)),
        "what": "用 %s 复测 %s（%s），记录正确率与步骤完整性；低于 50%% 回到学习卡，达到 70%% 进入下一指标。" % (
            check_mid, focus, focus_obs),
    }

    return {
        "schema_version": "0.1.0",
        "generated_at": diag["generated_at"],
        "student_id": sid,
        "basis": basis,
        "items": items,
        "not_recommended": not_rec[:3],
        "next_check": next_check,
    }


def _iid_of(kb, mid):
    for iid in kb.indicator_order:
        if mid in kb.indicators[iid]["materials"]:
            return iid
    return kb.indicator_order[0]


def generate():
    content = load_json(CONTENT_MAP)
    diag = load_json(DIAGNOSIS)
    _, rows, _ = read_csv(CLEAN_DATASET)
    records = fold_records(rows)
    by_student = {}
    for rec in records:
        by_student.setdefault(g(rec, "学生编号"), []).append(rec)
    kb = Knowledge(content)
    group_means = {x["group_id"]: x["score_rate_mean"] for x in diag["group_level"]["by_class"]}
    students = [build_student(kb, diag, s, by_student.get(s["student_id"], []), group_means.get(s["group_id"]))
                for s in sorted(diag["student_level"], key=lambda x: x["student_id"])]
    batch = {
        "schema_version": "0.1.0",
        "generated_at": diag["generated_at"],
        "source": {
            "diagnosis": "out/diagnosis_all.json",
            "diagnosis_sha256": sha256_file(DIAGNOSIS),
            "content_map": "out/content_map.json",
            "content_map_sha256": sha256_file(CONTENT_MAP),
            "policy": "每条建议对应具体指标与记录；不读取参考答案；信息不足时先观察",
        },
        "students": students,
    }
    return batch


def write_summary(batch, diag):
    header = ["学生编号", "班级", "整体得分率", "重点指标", "建议条数", "复习/练习/变式/观察", "材料序列"]
    info = {s["student_id"]: s for s in diag["student_level"]}
    rows = []
    for s in batch["students"]:
        actions = [i["action"] for i in s["items"]]
        focus = next((r for item in s["items"] for r in item["evidence_refs"] if r.startswith("T")), "")
        rows.append([
            s["student_id"],
            info.get(s["student_id"], {}).get("group_id", ""),
            pct(info.get(s["student_id"], {}).get("score_rate", {}).get("overall")),
            focus,
            len(s["items"]),
            "%d/%d/%d/%d" % tuple(actions.count(a) for a in ("review", "practice", "variant", "observe")),
            "→".join(i["material_id"] for i in s["items"]),
        ])
    write_csv(SUMMARY_OUT, header, rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成个性化学习建议")
    ap.add_argument("--example", metavar="STUDENT_ID", help="额外导出单个学生样例")
    ap.add_argument("--out", help="样例输出路径（配合 --example）")
    args = ap.parse_args(argv)
    ensure_dirs()
    batch = generate()
    write_json(BATCH_OUT, batch)
    write_summary(batch, load_json(DIAGNOSIS))
    print("已生成 %d 名学生的建议：%s" % (len(batch["students"]), os.path.relpath(BATCH_OUT, os.path.dirname(OUT))))
    if args.example:
        target = next((s for s in batch["students"] if s["student_id"] == args.example), None)
        if target is None:
            print("未找到学生 %s" % args.example, file=sys.stderr)
            return 1
        out = args.out or os.path.join(EXAMPLES, "recommendation_%s.json" % args.example)
        write_json(out, target)
        print("样例：%s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
