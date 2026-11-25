# -*- coding: utf-8 -*-
"""公开演示站点（demo/）的构造与边界测试。"""
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

import common  # noqa: E402
import demo_site  # noqa: E402
import ui_server  # noqa: E402


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


class TestDemoSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.demo = os.path.join(cls.tmp.name, "demo")
        cls.info = demo_site.build(cls.demo)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_build_creates_only_frontend_and_snapshot(self):
        self.assertTrue(os.path.isfile(os.path.join(self.demo, "index.html")))
        self.assertTrue(os.path.isfile(os.path.join(self.demo, "js", "app.js")))
        self.assertTrue(os.path.isfile(os.path.join(self.demo, "css", "styles.css")))
        self.assertTrue(os.path.isfile(os.path.join(self.demo, "demo-config.js")))
        self.assertTrue(os.path.isfile(os.path.join(self.demo, "snapshot.json")))
        self.assertFalse(os.path.exists(os.path.join(self.demo, "data")))
        self.assertFalse(os.path.exists(os.path.join(self.demo, "out")))
        self.assertFalse(os.path.exists(os.path.join(self.demo, "config")))
        for base, _dirs, files in os.walk(self.demo):
            for name in files:
                self.assertFalse(name.lower().endswith((".csv", ".exe")), name)

    def test_snapshot_meta_and_records_are_read_only(self):
        doc = json.loads(_read(os.path.join(self.demo, "snapshot.json")))
        meta = doc["meta"]
        self.assertTrue(meta["demo"])
        self.assertFalse(meta["run_enabled"])
        self.assertFalse(meta["input_enabled"])
        self.assertEqual(meta["input_path"], "")
        self.assertEqual(len(doc["records"]), 806)
        self.assertEqual(meta["students"], 40)
        self.assertEqual(meta["graph_nodes"], 72)
        self.assertEqual(meta["graph_edges"], 83)
        expected = {key for key, _label in ui_server.RECORD_FIELDS}
        self.assertEqual(set(doc["records"][0].keys()), expected)

    def test_snapshot_contains_no_answer_or_personal_fields(self):
        doc = json.loads(_read(os.path.join(self.demo, "snapshot.json")))
        raw = json.dumps(doc, ensure_ascii=False)
        for key in ("学生最终作答", "解答过程", "评分点得分"):
            self.assertNotIn('"' + key + '":', raw)
        self.assertNotIn("[('2', '<')", raw)
        qc = (doc.get("docs") or {}).get("qc") or {}
        for finding in qc.get("findings") or []:
            for rule in finding.get("rules") or []:
                if "actual" in rule:
                    self.assertEqual(rule["actual"], demo_site.MASK)
                if "expected" in rule:
                    self.assertEqual(rule["expected"], demo_site.MASK)
                self.assertEqual(rule.get("note", ""), "")
        self.assertIsNone(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", raw))

    def test_demo_config_and_relative_assets(self):
        html = _read(os.path.join(self.demo, "index.html"))
        config = _read(os.path.join(self.demo, "demo-config.js"))
        self.assertIn("window.DSH_DEMO = true;", config)
        self.assertIn('src="demo-config.js"', html)
        self.assertIn('src="js/app.js"', html)
        self.assertIn('href="css/styles.css"', html)
        self.assertNotIn('src="/js/app.js"', html)
        self.assertNotIn('href="/css/styles.css"', html)
        self.assertIn("noindex", html)

    def test_build_is_byte_stable(self):
        other = os.path.join(self.tmp.name, "demo2")
        demo_site.build(other)
        self.assertEqual(
            _read(os.path.join(self.demo, "snapshot.json")),
            _read(os.path.join(other, "snapshot.json")),
        )
        self.assertEqual(
            _read(os.path.join(self.demo, "demo-config.js")),
            _read(os.path.join(other, "demo-config.js")),
        )


if __name__ == "__main__":
    unittest.main()
