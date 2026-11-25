# -*- coding: utf-8 -*-
"""guards.py — 产物落盘前的守卫。

四类检查（任一失败退出码 1，阻断交付）：
1. 证据：material_id / evidence_refs 可解析，DR 必须属于该学生；
2. 不变量：低置信指标不排 practice/variant，无已评记录只能 observe；
3. 合规：建议文字不得出现参考答案原文；
4. 个人信息：手机号、邮箱、18 位身份证。
"""
from __future__ import annotations

import argparse
import json
import os
import re

from common import DERIVED, OUT, ROOT, RAW, read_csv, sha256_file, write_json

REC_FILE = "作答记录_清洗版.csv"
MATERIAL_FILE = "题目与材料.csv"
NODE_FILE = "测验节点.csv"
RECOMMENDATIONS = os.path.join(OUT, "recommendations_all.json")
CONTENT_MAP = os.path.join(OUT, "content_map.json")
DIAGNOSIS = os.path.join(OUT, "diagnosis_all.json")
REPORT = os.path.join(OUT, "guard_report.json")

ACTIONS = {"review", "practice", "variant", "observe"}
HINTS = {"提示", "分步提示", "不给答案"}
DR_RE = re.compile(r"^DR\d{4}$")
IND_RE = re.compile(r"^T0[1-3]I[1-9]$")
NODE_RE = re.compile(r"^N\d{2}$")
PHONE_RE = re.compile(r"1[3-9]\d{9}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
ID_RE = re.compile(r"\d{17}[\dXx]")
TEXT_FIELDS = ("reason", "expected_observation", "adjust_condition")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _texts(item):
    for field in TEXT_FIELDS:
        value = item.get(field)
        if isinstance(value, str):
            yield field, value


def check(root=None):
    root = root or ROOT
    cm = _load(os.path.join(root, CONTENT_MAP))
    diag = _load(os.path.join(root, DIAGNOSIS))
    rec = _load(os.path.join(root, RECOMMENDATIONS))
    _, rec_rows, _ = read_csv(os.path.join(root, DERIVED, REC_FILE))
    _, mat_rows, _ = read_csv(os.path.join(root, RAW, MATERIAL_FILE))
    _, node_rows, _ = read_csv(os.path.join(root, RAW, NODE_FILE))

    materials = {m["material_id"]: m for m in cm["materials_index"]}
    indicators = {i["indicator_id"] for t in cm["topics"] for i in t["indicators"]}
    nodes = {r["节点编号"] for r in node_rows}
    by_record = {r["记录编号"]: r for r in rec_rows}
    answers = [(r["材料编号"], (r.get("参考答案") or "").strip()) for r in mat_rows]
    students = {s["student_id"]: s for s in diag["student_level"]}

    errors = []
    checks = []

    def add(name, errs, detail):
        checks.append({
            "name": name,
            "status": "pass" if not errs else "fail",
            "errors": len(errs),
            "detail": detail,
        })
        errors.extend(errs)

    if len(rec.get("students", [])) != len(students):
        add("学生覆盖", ["建议批次 %d 人，诊断 %d 人" % (len(rec.get("students", [])), len(students))],
            "40 名学生全部有建议")
    else:
        add("学生覆盖", [], "%d 名学生全部有建议" % len(students))

    ref_errors = []
    invariant_errors = []
    compliance_errors = []
    pii_errors = []
    for s in rec.get("students", []):
        sid = s.get("student_id")
        if sid not in students:
            ref_errors.append("%s 不在诊断中" % sid)
            continue
        scored = students[sid]["observed"]["scored"]
        conf = {x["indicator_id"]: x["confidence"] for x in students[sid]["by_indicator"]}
        items = s.get("items", [])
        if not items:
            ref_errors.append("%s 没有建议" % sid)
        if len(items) > 6:
            ref_errors.append("%s 建议 %d 条，超过 6 条" % (sid, len(items)))
        for pos, item in enumerate(items, 1):
            mid = item.get("material_id")
            action = item.get("action")
            if item.get("seq") != pos:
                ref_errors.append("%s 第 %d 条 seq=%r 不连续" % (sid, pos, item.get("seq")))
            if mid not in materials:
                ref_errors.append("%s 材料 %r 不在内容图谱" % (sid, mid))
            if action not in ACTIONS:
                ref_errors.append("%s 动作 %r 非法" % (sid, action))
            if item.get("hint_level") not in HINTS:
                ref_errors.append("%s 提示等级 %r 非法" % (sid, item.get("hint_level")))
            refs = item.get("evidence_refs") or []
            if not refs:
                ref_errors.append("%s 第 %d 条无证据" % (sid, pos))
            for ref in refs:
                if DR_RE.match(ref):
                    row = by_record.get(ref)
                    if row is None:
                        ref_errors.append("%s 记录 %s 不存在" % (sid, ref))
                    elif row["学生编号"] != sid:
                        ref_errors.append("%s 记录 %s 属于 %s" % (sid, ref, row["学生编号"]))
                elif IND_RE.match(ref):
                    if ref not in indicators:
                        ref_errors.append("%s 指标 %s 不存在" % (sid, ref))
                elif NODE_RE.match(ref):
                    if ref not in nodes:
                        ref_errors.append("%s 节点 %s 不存在" % (sid, ref))
                else:
                    ref_errors.append("%s 证据 %r 不符合 DR/T/N 三类" % (sid, ref))
            low_refs = [r for r in refs if IND_RE.match(r) and conf.get(r) == "low"]
            if action in ("practice", "variant") and low_refs:
                invariant_errors.append("%s %s 作用于低置信指标 %s" % (sid, action, ",".join(low_refs)))
            if scored == 0 and action != "observe":
                invariant_errors.append("%s 无已评记录却排 %s" % (sid, action))
            for field, text in _texts(item):
                if PHONE_RE.search(text) or EMAIL_RE.search(text) or ID_RE.search(text):
                    pii_errors.append("%s 第 %d 条 %s 含个人信息" % (sid, pos, field))
                for mat_id, ans in answers:
                    if len(ans) >= 5 and ans in text:
                        compliance_errors.append("%s 第 %d 条 %s 含 %s 参考答案" % (sid, pos, field, mat_id))
        for entry in s.get("not_recommended", []):
            if entry.get("material_id") not in materials:
                ref_errors.append("%s not_recommended 材料 %r 不存在" % (sid, entry.get("material_id")))

    add("证据可解析", ref_errors, "material_id、DR/T/N 引用与归属")
    add("置信度不变量", invariant_errors, "n<5 不排练习/变式；无已评只观察")
    add("答案与合规", compliance_errors, "建议文字不含参考答案原文")
    add("个人信息", pii_errors, "手机号 / 邮箱 / 身份证")

    report = {
        "schema_version": "0.1.0",
        "generated_at": diag.get("generated_at", ""),
        "source": {
            "content_map": {"path": CONTENT_MAP, "sha256": sha256_file(os.path.join(root, CONTENT_MAP))},
            "diagnosis": {"path": DIAGNOSIS, "sha256": sha256_file(os.path.join(root, DIAGNOSIS))},
            "recommendations": {"path": RECOMMENDATIONS, "sha256": sha256_file(os.path.join(root, RECOMMENDATIONS))},
            "records": {"path": os.path.join(DERIVED, REC_FILE)},
        },
        "status": "pass" if not errors else "fail",
        "checks": checks,
        "errors": errors,
        "warnings": [],
    }
    write_json(os.path.join(root, REPORT), report)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="建议产物守卫")
    ap.parse_args(argv)
    rep = check()
    print("守卫 %s：%s" % (rep["status"], "；".join(
        "%s=%s" % (c["name"], c["status"]) for c in rep["checks"])))
    for err in rep["errors"][:20]:
        print("  - %s" % err)
    return 0 if rep["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
