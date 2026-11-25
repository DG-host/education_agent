# -*- coding: utf-8 -*-
"""可视化工作台：快照、HTTP 接口、静态资源与后台运行管理。

运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

import common  # noqa: E402
import consult  # noqa: E402
import record_input  # noqa: E402
import ui_server  # noqa: E402


class QuietHandler(ui_server.UiHandler):
    def log_message(self, fmt, *args):
        pass


class FakeRunner:
    def __init__(self, start_ok=True):
        self.start_ok = start_ok
        self.calls = 0

    def start(self):
        self.calls += 1
        return self.start_ok

    def status(self):
        return {
            "state": "idle",
            "started_at": None,
            "finished_at": None,
            "exit_code": None,
            "log_tail": [],
        }


class FakeConsult:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def status(self):
        return {
            "schema_version": "consult.status/1",
            "configured": self.error is None,
            "library_available": True,
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
            "config_path": "config/consult.json",
            "config_source": "file",
            "timeout_seconds": 60,
            "max_output_tokens": 1200,
            "max_history": 12,
            "message": "已配置，可发起咨询" if self.error is None else self.error.message,
        }

    def ask(self, question, history=None, student_id=None, include_diagnosis=False):
        question = consult._clean_question(question)
        history = consult._clean_history(history)
        self.calls.append({
            "question": question, "history": history,
            "student_id": student_id, "include_diagnosis": include_diagnosis,
        })
        if self.error is not None:
            raise self.error
        return {
            "schema_version": "consult.reply/1",
            "reply": "建议先回顾学习卡，再做一道同类题。",
            "model": "deepseek-chat",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "elapsed_ms": 1,
            "context": {"student_id": student_id, "include_diagnosis": include_diagnosis,
                        "indicators": [], "materials": []},
        }


def _start_server(runner, input_dir=None, consult_service=None):
    server = ui_server.UiServer(
        ("127.0.0.1", 0), QuietHandler, root=ROOT, runner=runner,
        input_dir=input_dir, consult_service=consult_service,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _request(port, method, path, headers=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read()
        return resp.status, dict(resp.getheaders()), data
    finally:
        conn.close()


class TestSnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = ui_server._core_missing(ROOT)
        if missing:
            raise unittest.SkipTest("需要先跑 run.cmd all：缺 " + ", ".join(missing))
        cls.snapshot = ui_server.build_snapshot(ROOT)

    def test_meta_counts(self):
        meta = self.snapshot["meta"]
        self.assertEqual(meta["students"], 40)
        self.assertEqual(meta["groups"], 2)
        self.assertEqual(meta["raw_records"], 806)
        self.assertEqual(meta["clean_records"], 806)
        self.assertEqual(meta["unique_events"], 799)
        self.assertEqual(meta["anomalies"], 7)
        self.assertEqual(meta["clean_anomalies"], 0)
        self.assertEqual(meta["changes"], 10)
        self.assertEqual(meta["recommendations"], 135)
        self.assertEqual(meta["cases"], 3)
        self.assertEqual(meta["topics"], 3)
        self.assertEqual(meta["indicators"], 9)
        self.assertEqual(meta["materials"], 65)

    def test_graph_projection(self):
        graph = self.snapshot["graph"]
        self.assertEqual(graph["version"], "content_graph/1")
        meta = graph["meta"]
        self.assertEqual(meta["node_counts"]["total"], 72)
        self.assertEqual(meta["node_counts"]["material"], 57)
        self.assertEqual(meta["edge_counts"]["total"], 83)
        self.assertEqual(meta["edge_counts"]["indicator_material"], 63)
        self.assertEqual(meta["skeleton_nodes"], 15)
        self.assertEqual(meta["skeleton_edges"], 20)
        self.assertEqual(meta["resources"], 57)
        self.assertEqual(len(graph["nodes"]), 72)
        self.assertEqual(len(graph["edges"]), 83)
        ids = [node["id"] for node in graph["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual({node["kind"] for node in graph["nodes"]},
                         {"topic", "indicator", "standard", "material"})
        self.assertEqual([item["material_id"] for item in meta["excluded_materials"]],
                         ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08"])
        self.assertEqual(self.snapshot["meta"]["graph_nodes"], 72)
        self.assertEqual(self.snapshot["meta"]["graph_edges"], 83)
        self.assertEqual(self.snapshot["meta"]["graph_resources"], 57)

    def test_records_are_whitelisted(self):
        records = self.snapshot["records"]
        self.assertEqual(len(records), 806)
        expected = {key for key, _ in ui_server.RECORD_FIELDS}
        for rec in records[:20]:
            self.assertEqual(set(rec), expected)
        self.assertEqual(len({r["record_id"] for r in records}), 806)
        self.assertEqual([r["record_id"] for r in records], sorted(r["record_id"] for r in records))
        forbidden = {"学生最终作答", "解答过程", "评分点得分", "参考答案", "参考解析"}
        for rec in records[:20]:
            self.assertFalse(forbidden & set(rec))

    def test_docs_and_sources(self):
        docs = self.snapshot["docs"]
        for name in ("content", "diagnosis", "recommendations", "cases", "qc", "clean"):
            self.assertIn(name, docs)
        self.assertIn("clean_dataset", [row["name"] for row in self.snapshot["sources"]])
        self.assertGreaterEqual(len(self.snapshot["sources"]), 7)
        self.assertEqual(self.snapshot["schema_version"], "ui.snapshot/1")

    def test_missing_core_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ui_server.SnapshotError) as ctx:
                ui_server.build_snapshot(tmp)
        exc = ctx.exception
        self.assertEqual(exc.status, 503)
        self.assertEqual(exc.code, "artifacts_missing")
        self.assertEqual(len(exc.details["missing"]), len(ui_server.CORE_ARTIFACTS))

    def test_optional_artifacts_degrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            for _, rel in ui_server.CORE_ARTIFACTS:
                src = os.path.join(ROOT, *rel.split("/"))
                dst = os.path.join(tmp, *rel.split("/"))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
            snap = ui_server.build_snapshot(tmp)
        self.assertIsNone(snap["docs"]["guard"])
        self.assertIsNone(snap["docs"]["trace"])
        self.assertEqual(sorted(w["path"] for w in snap["warnings"]),
                         sorted([ui_server.GUARD_PATH, ui_server.TRACE_PATH]))


class TestHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.thread = _start_server(FakeRunner(start_ok=True))
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def test_health(self):
        status, headers, body = _request(self.port, "GET", "/api/health")
        self.assertEqual(status, 200)
        doc = json.loads(body)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["version"], "ui/1.0")
        self.assertTrue(doc["artifacts_ready"])
        self.assertEqual(doc["missing"], [])
        self.assertIn("Content-Security-Policy", headers)

    def test_snapshot(self):
        status, headers, body = _request(self.port, "GET", "/api/snapshot")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(headers.get("Cache-Control"), "no-store")
        doc = json.loads(body)
        self.assertEqual(len(doc["records"]), 806)
        self.assertEqual(doc["meta"]["students"], 40)

    def test_index_and_static(self):
        status, headers, body = _request(self.port, "GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b'src="js/app.js"', body)
        self.assertIn(b'href="css/styles.css"', body)
        self.assertNotIn(b"http://", body)
        self.assertNotIn(b"https://", body)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])

        status, headers, body = _request(self.port, "GET", "/css/styles.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", headers["Content-Type"])
        self.assertIn(b".card", body)

    def test_head_has_no_body(self):
        status, headers, body = _request(self.port, "HEAD", "/")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertGreater(int(headers["Content-Length"]), 0)

    def test_unknown_api_and_traversal(self):
        status, _, body = _request(self.port, "GET", "/api/nope")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["error"]["code"], "not_found")

        status, _, _ = _request(self.port, "GET", "/..%2f..%2fREADME.md")
        self.assertEqual(status, 404)
        status, _, _ = _request(self.port, "GET", "/nope.js")
        self.assertEqual(status, 404)
        status, _, _ = _request(self.port, "GET", "/js/../index.html")
        self.assertEqual(status, 200)

    def test_run_requires_local_header(self):
        status, _, body = _request(self.port, "POST", "/api/run")
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"]["code"], "forbidden")

        status, _, _ = _request(self.port, "POST", "/api/run", {
            "X-DSH-UI": "1", "Origin": "http://evil.example",
        })
        self.assertEqual(status, 403)

        status, _, _ = _request(self.port, "POST", "/api/run", {
            "X-DSH-UI": "1", "Host": "evil.example",
        })
        self.assertEqual(status, 403)

    def test_run_accepted_and_status(self):
        origin = "http://127.0.0.1:%d" % self.port
        status, _, body = _request(self.port, "POST", "/api/run", {
            "X-DSH-UI": "1", "Origin": origin,
        })
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(body)["state"], "idle")

        status, _, body = _request(self.port, "GET", "/api/run/status")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["state"], "idle")

    def test_run_conflict(self):
        server, thread = _start_server(FakeRunner(start_ok=False))
        try:
            status, _, body = _request(server.server_port, "POST", "/api/run", {
                "X-DSH-UI": "1",
                "Origin": "http://127.0.0.1:%d" % server.server_port,
            })
            self.assertEqual(status, 409)
            self.assertEqual(json.loads(body)["error"]["code"], "already_running")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)



class TestConsultHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeConsult()
        cls.server, cls.thread = _start_server(FakeRunner(start_ok=True), consult_service=cls.fake)
        cls.port = cls.server.server_port
        cls.headers = {"X-DSH-UI": "1"}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def _post(self, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        merged = {**self.headers, "Content-Type": "application/json"}
        if headers:
            merged.update(headers)
        return _request(self.port, "POST", "/api/consult", merged, body)

    def test_status_requires_local_header(self):
        status, _, body = _request(self.port, "GET", "/api/consult/status")
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"]["code"], "forbidden")
        status, _, body = _request(self.port, "GET", "/api/consult/status", self.headers)
        self.assertEqual(status, 200)
        doc = json.loads(body)
        self.assertEqual(doc["schema_version"], "consult.status/1")
        self.assertTrue(doc["configured"])
        self.assertNotIn("test-key", body.decode("utf-8"))

    def test_post_requires_local_header(self):
        body = json.dumps({"question": "怎么安排？"}, ensure_ascii=False).encode("utf-8")
        status, _, raw = _request(self.port, "POST", "/api/consult", {
            "Content-Type": "application/json",
        }, body)
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(raw)["error"]["code"], "forbidden")

    def test_post_success(self):
        status, headers, body = self._post({
            "question": "这名学生下一步先补什么？",
            "student_id": "D01",
            "include_diagnosis": True,
            "history": [{"role": "user", "content": "上一问"}],
        })
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        doc = json.loads(body)
        self.assertEqual(doc["schema_version"], "consult.reply/1")
        self.assertIn("建议", doc["reply"])
        self.assertEqual(doc["usage"]["total_tokens"], 15)
        self.assertEqual(self.fake.calls[-1]["student_id"], "D01")
        self.assertEqual(self.fake.calls[-1]["include_diagnosis"], True)
        self.assertEqual(self.fake.calls[-1]["history"], [{"role": "user", "content": "上一问"}])

    def test_post_validation(self):
        status, _, body = self._post({"question": ""})
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(body)["error"]["code"], "invalid_question")
        status, _, body = self._post({"question": "x", "extra": 1})
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(body)["error"]["code"], "unknown_field")

    def test_post_rejects_non_json(self):
        status, _, _ = _request(self.port, "POST", "/api/consult", {
            **self.headers, "Content-Type": "text/plain",
        }, b"hello")
        self.assertEqual(status, 415)

    def test_unconfigured_returns_503(self):
        fake = FakeConsult(consult.ConsultError("consult_unconfigured", "未配置", 503))
        server, thread = _start_server(FakeRunner(start_ok=True), consult_service=fake)
        try:
            body = json.dumps({"question": "怎么安排？"}, ensure_ascii=False).encode("utf-8")
            status, _, raw = _request(server.server_port, "POST", "/api/consult", {
                "X-DSH-UI": "1", "Content-Type": "application/json",
            }, body)
            self.assertEqual(status, 503)
            self.assertEqual(json.loads(raw)["error"]["code"], "consult_unconfigured")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


class TestRecordInputHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.server, cls.thread = _start_server(FakeRunner(start_ok=True), input_dir=cls.tmp.name)
        cls.port = cls.server.server_port
        cls.headers = {"X-DSH-UI": "1"}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.tmp.cleanup()

    def _csv(self):
        row = {
            "记录编号": "DR0001",
            "学生编号": "D01",
            "材料编号": "Q015",
            "主题编号": "T01",
            "节点编号": "N01",
            "作答事件编号": "D01-N01-Q015",
            "修订版本": "1",
            "模拟提交时间": "2026-01-20T08:56:22+08:00",
            "评分状态": "已评分",
            "得分": "2",
            "满分": "3",
            "学生最终作答": "4a+7b",
            "解答过程": "1. 原式=6a-3b-2a-4b\n2. =4a-7b。",
            "评分点得分": "Q015P1=1；Q015P2=1；Q015P3=0",
        }
        return record_input.csv_text([row]).encode("utf-8")

    def test_records_requires_local_header(self):
        status, _, body = _request(self.port, "GET", "/api/records")
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"]["code"], "forbidden")
        status, _, body = _request(self.port, "GET", "/api/records", self.headers)
        self.assertEqual(status, 200)
        doc = json.loads(body)
        self.assertEqual(doc["schema_version"], "input.view/1")
        self.assertIsInstance(doc["exists"], bool)

    def test_template_validate_save_export(self):
        status, headers, body = _request(self.port, "GET", "/api/records/template", self.headers)
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(body.decode("utf-8-sig").split("\r\n")[0].split(","), common.COLUMNS)

        status, _, body = _request(self.port, "POST", "/api/records/validate", {
            **self.headers, "Content-Type": "text/csv; charset=utf-8",
        }, self._csv())
        self.assertEqual(status, 200)
        doc = json.loads(body)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["rows"], 1)
        self.assertEqual(len(doc["preview"]), 1)

        status, _, body = _request(self.port, "POST", "/api/records?mode=replace", {
            **self.headers, "Content-Type": "text/csv; charset=utf-8",
        }, self._csv())
        self.assertEqual(status, 201)
        saved = json.loads(body)
        self.assertEqual(saved["rows"], 1)
        self.assertEqual(saved["mode"], "replace")

        status, _, body = _request(self.port, "GET", "/api/records/export", self.headers)
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
        self.assertIn("DR0001", body.decode("utf-8-sig"))

        status, _, body = _request(self.port, "GET", "/api/records", self.headers)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["exists"])

    def test_save_rejects_hard_errors(self):
        bad = self._csv().decode("utf-8").replace("D01", "D99", 1)
        status, _, body = _request(self.port, "POST", "/api/records?mode=replace", {
            **self.headers, "Content-Type": "text/csv; charset=utf-8",
        }, bad.encode("utf-8"))
        self.assertEqual(status, 422)
        doc = json.loads(body)
        self.assertEqual(doc["error"]["code"], "validation_failed")
        self.assertTrue(doc["error"]["details"]["errors"])

    def test_save_requires_local_header(self):
        status, _, body = _request(self.port, "POST", "/api/records?mode=replace", {
            "Content-Type": "text/csv; charset=utf-8",
        }, self._csv())
        self.assertEqual(status, 403)

class TestFrontendAssets(unittest.TestCase):
    def test_input_page_assets(self):
        path = os.path.join(ROOT, "ui", "js", "input.js")
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("export const inputPage", text)
        self.assertIn("/api/records/validate", text)
        self.assertIn("/api/records/template", text)
        self.assertIn("/api/records/export", text)
        with open(os.path.join(ROOT, "ui", "index.html"), "r", encoding="utf-8") as fh:
            html = fh.read()
        self.assertIn('href="#/input"', html)
        self.assertIn('data-route="input"', html)

    def test_graph_assets(self):
        with open(os.path.join(ROOT, "ui", "js", "graph.js"), "r", encoding="utf-8") as fh:
            graph = fh.read()
        for token in ("export const knowledgeGraphCard", "export const mountKnowledgeGraph",
                      "export const destroyKnowledgeGraph", "graphSvg"):
            self.assertIn(token, graph)
        for name, token in (("pages.js", "knowledgeGraphCard()"),
                            ("app.js", "mountKnowledgeGraph()"),
                            ("data.js", "state.graph")):
            with open(os.path.join(ROOT, "ui", "js", name), "r", encoding="utf-8") as fh:
                self.assertIn(token, fh.read())
        with open(os.path.join(ROOT, "ui", "css", "styles.css"), "r", encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn(".graph-stage", css)
        self.assertIn(".gnode.is-selected", css)

    def test_consult_page_assets(self):
        with open(os.path.join(ROOT, "ui", "js", "consult.js"), "r", encoding="utf-8") as fh:
            text = fh.read()
        for token in ("export const consultPage", "export const mountConsultPage",
                      "export const destroyConsultPage", "/api/consult/status",
                      "/api/consult", "DEEPSEEK_API_KEY"):
            self.assertIn(token, text)
        with open(os.path.join(ROOT, "ui", "index.html"), "r", encoding="utf-8") as fh:
            html = fh.read()
        self.assertIn('href="#/consult"', html)
        self.assertIn('data-route="consult"', html)
        with open(os.path.join(ROOT, "ui", "js", "app.js"), "r", encoding="utf-8") as fh:
            app = fh.read()
        self.assertIn("mountConsultPage()", app)
        self.assertIn("destroyConsultPage()", app)
        with open(os.path.join(ROOT, "ui", "css", "styles.css"), "r", encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn(".consult-thread", css)
        self.assertIn(".consult-status", css)

    def test_no_external_urls_or_inline_script(self):
        for base, _, files in os.walk(os.path.join(ROOT, "ui")):
            for name in files:
                if not name.endswith((".html", ".css", ".js", ".mjs")):
                    continue
                path = os.path.join(base, name)
                with open(path, "r", encoding="utf-8") as fh:
                    text = fh.read()
                # SVG 命名空间是 XML 标识符，不是网络请求；其余外部 URL 一律禁止。
                text = text.replace("http://www.w3.org/2000/svg", "")
                self.assertIsNone(re.search(r"https?://", text), path)
        with open(os.path.join(ROOT, "ui", "index.html"), "r", encoding="utf-8") as fh:
            html = fh.read()
        self.assertEqual(html.count("<script"), 2)
        self.assertIn('<script src="demo-config.js"></script>', html)
        self.assertIn('<script type="module" src="js/app.js"></script>', html)
        self.assertLess(html.index("demo-config.js"), html.index("js/app.js"))
        self.assertNotIn("onclick=", html)


class TestRunManager(unittest.TestCase):
    def test_captures_log_and_exit(self):
        code = "import time; print('one', flush=True); time.sleep(0.2); print('two', flush=True)"
        runner = ui_server.RunManager(ROOT, [sys.executable, "-u", "-c", code])
        self.assertTrue(runner.start())
        deadline = time.time() + 10
        while time.time() < deadline:
            status = runner.status()
            if status["state"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual(status["state"], "succeeded", status)
        self.assertEqual(status["exit_code"], 0)
        self.assertIn("one", status["log_tail"])
        self.assertIn("two", status["log_tail"])


if __name__ == "__main__":
    unittest.main()
