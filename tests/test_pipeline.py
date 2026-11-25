# -*- coding: utf-8 -*-
"""基础回归：清洗对账、契约、建议证据、守卫、计划与确定性。

运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)
sys.path.insert(0, ROOT)

import cases  # noqa: E402
import clean  # noqa: E402
import content_map  # noqa: E402
import guards  # noqa: E402
import qc  # noqa: E402
import recommend  # noqa: E402
import validate  # noqa: E402
from agent.plans import PLANS  # noqa: E402
from agent.tools import build_registry  # noqa: E402

ID_RE = re.compile(r"(\bD0\d\b|\bQ0\d\d\b|\bT0[1-3]\b|\bN0\d\b|\bDR\d{4}\b)")


class TestClean(unittest.TestCase):
    def test_reconciles_existing_derived(self):
        code, rep = clean.check(verbose=False)
        self.assertEqual(code, 0)
        self.assertEqual(rep["changes"], 10)
        self.assertEqual(rep["unresolved"], [])
        self.assertTrue(rep["compare"]["clean"]["matches"])
        self.assertTrue(rep["compare"]["change_log"]["matches"])
        self.assertEqual(rep["qc_after"]["anomaly_records"], 0)


class TestContentMap(unittest.TestCase):
    def setUp(self):
        self.doc = content_map.build()

    def test_counts(self):
        self.assertEqual(len(self.doc["topics"]), 3)
        self.assertEqual(sum(len(t["indicators"]) for t in self.doc["topics"]), 9)
        self.assertEqual(len(self.doc["materials_index"]), 65)

    def test_every_indicator_has_source(self):
        for topic in self.doc["topics"]:
            for ind in topic["indicators"]:
                self.assertTrue(ind["standard"]["cr_id"])
                self.assertTrue(ind["standard"]["pdf_pages"])
                self.assertTrue(ind["standard"]["body_pages"])
                self.assertTrue(ind["material_ids"])


class TestDiagnosis(unittest.TestCase):
    def test_individual_and_group(self):
        path = os.path.join(clean.DERIVED, os.path.basename(clean.CLEAN_DATASET))
        report, rows, ctx = qc.check(path)
        diag = qc.build_diagnosis(rows, ctx, report, report)
        self.assertEqual(len(diag["student_level"]), 40)
        self.assertEqual(len(diag["group_level"]["by_class"]), 2)
        self.assertEqual(len(diag["group_level"]["by_indicator"]), 9)
        for s in diag["student_level"]:
            self.assertTrue(0.0 <= s["observed"]["coverage"].get("N01", 0) <= 1.0)
            self.assertIn(s["by_indicator"][0]["confidence"], ("low", "medium", "high"))


class TestRecommendation(unittest.TestCase):
    def setUp(self):
        self.batch = recommend.generate()
        self.cm = content_map.build()
        self.materials = {m["material_id"] for m in self.cm["materials_index"]}

    def test_every_student_has_items(self):
        self.assertEqual(len(self.batch["students"]), 40)
        for s in self.batch["students"]:
            self.assertGreaterEqual(len(s["items"]), 1)
            self.assertLessEqual(len(s["items"]), 6)
            self.assertEqual([it["seq"] for it in s["items"]], list(range(1, len(s["items"]) + 1)))
            for item in s["items"]:
                self.assertIn(item["material_id"], self.materials)
                self.assertTrue(item["evidence_refs"])
                self.assertTrue(any(re.match(r"^T0[1-3]I[1-9]$", ref)
                                    for ref in item["evidence_refs"]))

    def test_deterministic(self):
        again = recommend.generate()
        self.assertEqual(json.dumps(self.batch, ensure_ascii=False, sort_keys=True),
                         json.dumps(again, ensure_ascii=False, sort_keys=True))


class TestGuards(unittest.TestCase):
    def test_guard_passes(self):
        if not os.path.exists(os.path.join(ROOT, "out", "recommendations_all.json")):
            self.skipTest("需要先跑 run.cmd all")
        rep = guards.check(ROOT)
        self.assertEqual(rep["status"], "pass", rep["errors"])
        self.assertEqual(len(rep["checks"]), 5)


class TestContracts(unittest.TestCase):
    def test_all_contracts(self):
        if not os.path.exists(os.path.join(ROOT, "out", "recommendations_all.json")):
            self.skipTest("需要先跑 run.cmd all")
        self.assertEqual(validate.main([]), 0)


class TestPlan(unittest.TestCase):
    def test_every_plan_tool_registered(self):
        registry = build_registry()
        names = {spec.name for spec in registry.specs()}
        for task, tools in PLANS.items():
            for tool in tools:
                self.assertIn(tool, names, "%s 引用了未注册工具 %s" % (task, tool))
        self.assertIn("guard", PLANS["all"])
        self.assertEqual(PLANS["all"][-1], "validate")

    def test_no_hardcoded_ids_in_src(self):
        hits = []
        for base, _, files in os.walk(SRC):
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(base, name)
                with open(path, encoding="utf-8") as f:
                    for lineno, line in enumerate(f, 1):
                        if ID_RE.search(line):
                            hits.append("%s:%d" % (os.path.relpath(path, ROOT), lineno))
        self.assertEqual(hits, [], "源码出现具体编号：%s" % hits)


class TestCaseSelection(unittest.TestCase):
    def test_roles_are_distinct(self):
        if not os.path.exists(os.path.join(ROOT, "out", "cases.json")):
            self.skipTest("需要先跑 run.cmd all")
        with open(os.path.join(ROOT, "out", "cases.json"), encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(len(doc["cases"]), 3)
        ids = [c["student_id"] for c in doc["cases"]]
        self.assertEqual(len(set(ids)), 3)


if __name__ == "__main__":
    unittest.main()
