# -*- coding: utf-8 -*-
"""教学咨询：配置、上下文白名单、请求校验与错误映射（全部离线）。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

import common  # noqa: E402
import consult  # noqa: E402


def _write_fixtures(root):
    content = {
        "topics": [{
            "topic_id": "T01",
            "topic": "代数式与整式运算",
            "goal": "用代数式表示数量关系",
            "indicators": [{
                "indicator_id": "T01I1",
                "observation": "表示数量关系并代入求值",
                "standard": {"cr_id": "CR01"},
                "textbook_pages": "上册 68—109",
                "material_ids": ["L01", "Q001"],
            }],
        }],
        "materials_index": [{
            "material_id": "Q001",
            "type": "题目",
            "question_type": "填空题",
            "max_score": 3,
        }],
    }
    diag = {
        "student_level": [{
            "student_id": "D01",
            "group_id": "DC01",
            "observed": {"records": 3, "scored": 3, "pending": 0, "unanswered": 0,
                         "coverage": {"N01": 0.5}},
            "score_rate": {"overall": 0.5, "by_node": {"N01": 0.5}},
            "by_indicator": [{
                "indicator_id": "T01I1", "observed": 3, "correct": 1,
                "rate": 0.3333, "confidence": "low",
            }],
            "flags": ["insufficient_records"],
        }],
        "group_level": {
            "by_class": [{
                "group_id": "DC01", "students": 1, "records": 3,
                "coverage_mean": 0.5, "score_rate_mean": 0.5,
            }],
        },
    }
    recs = {
        "students": [{
            "student_id": "D01",
            "basis": ["记录 3 条，整体得分率 50.0%"],
            "items": [{
                "seq": 1,
                "material_id": "L01",
                "action": "review",
                "reason": "T01I1 观测 3 条，满分率 0.0%",
                "hint_level": "提示",
                "expected_observation": "不应发送",
                "adjust_condition": "不应发送",
            }],
        }],
    }
    common.write_json(os.path.join(root, "out", "content_map.json"), content)
    common.write_json(os.path.join(root, "out", "diagnosis_all.json"), diag)
    common.write_json(os.path.join(root, "out", "recommendations_all.json"), recs)


class FakeCompletions:
    def __init__(self, reply="建议先回顾学习卡，再做一道同类题。", error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="deepseek-chat",
        )


class FakeClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)


class ConsultTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        _write_fixtures(self.root)
        self.config_path = os.path.join(self.root, "config", "consult.json")
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as fh:
            json.dump({"api_key": "test-key", "model": "deepseek-chat"}, fh)
        self.completions = FakeCompletions()
        self.service = consult.ConsultService(
            self.root, config_path=self.config_path, env={},
            client_factory=lambda cfg: FakeClient(self.completions),
        )

    def tearDown(self):
        self.tmp.cleanup()


class TestConfig(ConsultTestBase):
    def test_status_does_not_expose_key(self):
        doc = self.service.status()
        self.assertTrue(doc["configured"])
        self.assertTrue(doc["library_available"])
        self.assertEqual(doc["model"], "deepseek-chat")
        self.assertNotIn("test-key", json.dumps(doc, ensure_ascii=False))

    def test_env_overrides_file(self):
        cfg = consult.load_config(
            self.root,
            self.config_path,
            {"DEEPSEEK_API_KEY": "env-key", "DEEPSEEK_MODEL": "env-model", "DEEPSEEK_TIMEOUT": "30"},
        )
        self.assertEqual(cfg["api_key"], "env-key")
        self.assertEqual(cfg["config_source"], "env")
        self.assertEqual(cfg["model"], "env-model")
        self.assertEqual(cfg["timeout_seconds"], 30)

    def test_missing_key_is_unconfigured(self):
        service = consult.ConsultService(self.root, config_path=os.path.join(self.root, "nope.json"), env={})
        doc = service.status()
        self.assertFalse(doc["configured"])
        with self.assertRaises(consult.ConsultError) as ctx:
            service.ask("怎么安排？")
        self.assertEqual(ctx.exception.status, 503)
        self.assertEqual(ctx.exception.code, "consult_unconfigured")

    def test_invalid_config_reports_error(self):
        with open(self.config_path, "w", encoding="utf-8") as fh:
            fh.write("{bad json")
        doc = self.service.status()
        self.assertFalse(doc["configured"])
        self.assertIn("JSON", doc["message"])
        with self.assertRaises(consult.ConsultError) as ctx:
            self.service.ask("怎么安排？")
        self.assertEqual(ctx.exception.code, "consult_config_invalid")


class TestContext(ConsultTestBase):
    def test_context_whitelist_and_privacy(self):
        ctx = self.service.build_context("D01", True)
        text = ctx["text"]
        self.assertIn("T01I1", text)
        self.assertIn("Q001", text)
        self.assertIn("DC01", text)
        for forbidden in ("学生最终作答", "参考答案", "解答过程", "expected_observation", "adjust_condition"):
            self.assertNotIn(forbidden, text)

    def test_context_without_student_has_no_student(self):
        ctx = self.service.build_context()
        self.assertIsNone(ctx["student_id"])
        self.assertNotIn("student_id", ctx["text"])

    def test_missing_diagnosis_is_an_error(self):
        os.remove(os.path.join(self.root, "out", "diagnosis_all.json"))
        with self.assertRaises(consult.ConsultError) as ctx:
            self.service.build_context("D01", True)
        self.assertEqual(ctx.exception.code, "consult_context_missing")

    def test_unknown_student_is_an_error(self):
        with self.assertRaises(consult.ConsultError) as ctx:
            self.service.build_context("D99", True)
        self.assertEqual(ctx.exception.code, "invalid_student")


class TestAsk(ConsultTestBase):
    def test_ask_returns_reply_and_usage(self):
        result = self.service.ask("这名学生下一步先补什么？", student_id="D01", include_diagnosis=True)
        self.assertEqual(result["schema_version"], "consult.reply/1")
        self.assertIn("建议", result["reply"])
        self.assertEqual(result["usage"]["total_tokens"], 15)
        self.assertEqual(result["context"]["student_id"], "D01")
        self.assertIn("T01I1", result["context"]["indicators"])
        call = self.completions.calls[0]
        self.assertEqual(call["model"], "deepseek-chat")
        self.assertEqual(call["stream"], False)
        self.assertEqual(call["messages"][-1]["content"], "这名学生下一步先补什么？")
        self.assertIn("初中数学教师", call["messages"][0]["content"])

    def test_history_is_passed_before_question(self):
        self.service.ask("追问", history=[{"role": "user", "content": "上一问"}, {"role": "assistant", "content": "上一答"}])
        messages = self.completions.calls[0]["messages"]
        self.assertEqual(messages[1]["content"], "上一问")
        self.assertEqual(messages[2]["content"], "上一答")
        self.assertEqual(messages[-1]["content"], "追问")

    def test_empty_reply_is_an_error(self):
        self.completions.reply = ""
        with self.assertRaises(consult.ConsultError) as ctx:
            self.service.ask("怎么安排？")
        self.assertEqual(ctx.exception.code, "consult_empty_reply")

    def test_auth_failure_mapping(self):
        err = RuntimeError("unauthorized")
        err.status_code = 401
        self.completions.error = err
        with self.assertRaises(consult.ConsultError) as ctx:
            self.service.ask("怎么安排？")
        self.assertEqual(ctx.exception.code, "consult_auth_failed")

    def test_timeout_mapping(self):
        self.completions.error = TimeoutError("timeout")
        with self.assertRaises(consult.ConsultError) as ctx:
            self.service.ask("怎么安排？")
        self.assertEqual(ctx.exception.code, "consult_timeout")

    def test_busy_lock(self):
        self.service._lock.acquire()
        try:
            with self.assertRaises(consult.ConsultError) as ctx:
                self.service.ask("怎么安排？")
        finally:
            self.service._lock.release()
        self.assertEqual(ctx.exception.code, "consult_busy")


class TestRequestValidation(unittest.TestCase):
    def test_unknown_field(self):
        with self.assertRaises(consult.ConsultError) as ctx:
            consult.normalize_request({"question": "x", "extra": 1})
        self.assertEqual(ctx.exception.code, "unknown_field")

    def test_history_limits_and_roles(self):
        with self.assertRaises(consult.ConsultError):
            consult._clean_history([{"role": "system", "content": "x"}])
        with self.assertRaises(consult.ConsultError):
            consult._clean_history([{"role": "user", "content": "x"}] * 13)

    def test_question_limits(self):
        with self.assertRaises(consult.ConsultError):
            consult._clean_question("")
        with self.assertRaises(consult.ConsultError):
            consult._clean_question("x" * (consult.MAX_QUESTION_CHARS + 1))


if __name__ == "__main__":
    unittest.main()
