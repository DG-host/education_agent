# -*- coding: utf-8 -*-
"""数据录入：14 列契约、解析、硬错误/警告分级、保存与回滚。

运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

import common  # noqa: E402
import record_input  # noqa: E402

RAW = os.path.join(common.RAW, "作答记录.csv")


def base_row(**changes):
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
    row.update(changes)
    return row


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def error_codes(rows):
    result = record_input.validate_rows(rows, include_qc=False)
    return {item["code"] for item in result["errors"]}, {item["code"] for item in result["warnings"]}


class TestTemplateAndParse(unittest.TestCase):
    def test_template_is_utf8_bom_crlf(self):
        raw = record_input.template_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        text = raw.decode("utf-8-sig")
        self.assertIn("\r\n", text)
        header = text.split("\r\n")[0].split(",")
        self.assertEqual(header, common.COLUMNS)
        self.assertEqual(len(header), 14)

    def test_csv_roundtrip_keeps_multiline_quotes(self):
        row = base_row()
        text = record_input.csv_text([row])
        parsed, mode = record_input.parse_csv_text("\ufeff" + text)
        self.assertIsNone(mode)
        self.assertEqual(parsed[0]["解答过程"], row["解答过程"])
        self.assertEqual(parsed[0]["评分点得分"], row["评分点得分"])

    def test_blank_line_is_ignored(self):
        text = record_input.csv_text([base_row()]) + "\r\n"
        parsed, _ = record_input.parse_csv_text(text)
        self.assertEqual(len(parsed), 1)

    def test_header_must_match_exactly(self):
        with self.assertRaises(record_input.InputError) as ctx:
            record_input.parse_csv_text("记录编号,学生编号\r\nDR0001,D01\r\n")
        self.assertEqual(ctx.exception.code, "header_mismatch")

    def test_row_width(self):
        text = record_input.template_text() + ",".join(["x"] * 13) + "\r\n"
        with self.assertRaises(record_input.InputError) as ctx:
            record_input.parse_csv_text(text)
        self.assertEqual(ctx.exception.code, "row_width")

    def test_only_header_is_empty_rows(self):
        with self.assertRaises(record_input.InputError) as ctx:
            record_input.parse_csv_text(record_input.template_text())
        self.assertEqual(ctx.exception.code, "empty_rows")

    def test_json_array_and_wrapper(self):
        payload = json.dumps([base_row()], ensure_ascii=False).encode("utf-8")
        rows, mode = record_input.parse_payload(payload, "application/json; charset=utf-8")
        self.assertIsNone(mode)
        self.assertEqual(rows[0]["记录编号"], "DR0001")
        payload = json.dumps({"rows": [base_row()], "mode": "append"}, ensure_ascii=False).encode("utf-8")
        rows, mode = record_input.parse_payload(payload, "application/json")
        self.assertEqual(mode, "append")
        self.assertEqual(len(rows), 1)

    def test_json_missing_and_unknown_fields(self):
        missing = base_row()
        missing.pop("学生最终作答")
        with self.assertRaises(record_input.InputError) as ctx:
            record_input.parse_json_rows([missing])
        self.assertEqual(ctx.exception.code, "json_missing_field")
        extra = base_row()
        extra["额外列"] = "x"
        with self.assertRaises(record_input.InputError) as ctx:
            record_input.parse_json_rows([extra])
        self.assertEqual(ctx.exception.code, "json_unknown_field")

    def test_invalid_mode_and_media_type(self):
        with self.assertRaises(record_input.InputError) as ctx:
            record_input.parse_payload(b'{"rows": [], "mode": "merge"}', "application/json")
        self.assertEqual(ctx.exception.code, "invalid_mode")
        with self.assertRaises(record_input.InputError) as ctx:
            record_input.parse_payload(b"x", "application/xml")
        self.assertEqual(ctx.exception.code, "unsupported_media_type")


class TestValidation(unittest.TestCase):
    def test_raw_806_rows_zero_errors_seven_warnings(self):
        header, rows, meta = common.read_csv(RAW)
        self.assertEqual(header, common.COLUMNS)
        result = record_input.validate_rows(rows)
        self.assertTrue(result["ok"], result["errors"][:3])
        self.assertEqual(result["rows"], 806)
        self.assertEqual(result["students"], 40)
        self.assertEqual(result["groups"], 2)
        self.assertEqual(result["unique_events"], 799)
        self.assertEqual(result["revisions_folded"], 7)
        self.assertEqual(len(result["warnings"]), 7)
        self.assertEqual(result["qc"]["anomaly_records"], 7)
        self.assertEqual(result["status_counts"]["已评分"], 795)
        self.assertEqual(result["status_counts"]["待评分"], 6)
        self.assertEqual(result["status_counts"]["未作答"], 5)

    def test_hard_errors_are_reported(self):
        cases = {
            "required": base_row(**{"记录编号": ""}),
            "id_format": base_row(**{"学生编号": "X01"}),
            "unknown_student": base_row(**{"学生编号": "D99"}),
            "unknown_material": base_row(**{"材料编号": "Q999"}),
            "unknown_node": base_row(**{"节点编号": "N99"}),
            "event_mismatch": base_row(**{"作答事件编号": "D01-N01-Q016"}),
            "revision_invalid": base_row(**{"修订版本": "0"}),
            "time_invalid": base_row(**{"模拟提交时间": "2026-13-01T08:00:00+08:00"}),
            "status_invalid": base_row(**{"评分状态": "已批改"}),
            "score_required": base_row(**{"得分": ""}),
            "score_not_allowed": base_row(**{"评分状态": "待评分", "得分": "1"}),
            "points_not_allowed": base_row(**{"评分状态": "未作答", "得分": "", "评分点得分": "Q015P1=1"}),
            "points_syntax": base_row(**{"评分点得分": "Q015P1"}),
            "points_material": base_row(**{"评分点得分": "Q016P1=1"}),
            "points_duplicate": base_row(**{"评分点得分": "Q015P1=1；Q015P1=1"}),
        }
        for expected, row in cases.items():
            with self.subTest(expected=expected):
                codes, _ = error_codes([row])
                self.assertIn(expected, codes)
        duplicate = [base_row(), base_row()]
        codes, _ = error_codes(duplicate)
        self.assertIn("duplicate_record", codes)
        versions = [base_row(), base_row(**{"记录编号": "DR0002"})]
        codes, _ = error_codes(versions)
        self.assertIn("duplicate_revision", codes)

    def test_warnings_do_not_block(self):
        row = base_row(**{
            "主题编号": "T02",
            "得分": "10",
            "满分": "1",
            "评分点得分": "Q015P1=1；Q015P2=0；Q015P3=0",
        })
        result = record_input.validate_rows([row], include_qc=False)
        self.assertTrue(result["ok"])
        codes = {item["code"] for item in result["warnings"]}
        self.assertIn("topic_mismatch", codes)
        self.assertIn("score_over_max", codes)
        self.assertIn("points_sum_mismatch", codes)

    def test_material_not_in_node_warning(self):
        row = base_row(**{"材料编号": "Q038", "作答事件编号": "D01-N01-Q038", "满分": "1"})
        codes, warnings = error_codes([row])
        self.assertNotIn("unknown_material", codes)
        self.assertIn("material_not_in_node", warnings)


class TestSaveAndLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_replace_append_and_backup(self):
        first = record_input.save([base_row()], mode="replace", input_dir=self.dir, include_qc=False)
        self.assertEqual(first["meta"]["rows"], 1)
        path = record_input.input_path(self.dir)
        self.assertTrue(os.path.isfile(path))
        with open(path, "rb") as fh:
            self.assertTrue(fh.read().startswith(b"\xef\xbb\xbf"))
        loaded = record_input.load_current(self.dir)
        self.assertTrue(loaded["exists"])
        self.assertEqual(loaded["rows"][0]["记录编号"], "DR0001")
        self.assertEqual(loaded["meta"]["schema_version"], "input/1.0")

        second = record_input.save(
            [base_row(**{"记录编号": "DR0002", "材料编号": "Q027", "主题编号": "T02",
                         "作答事件编号": "D01-N01-Q027", "得分": "1", "满分": "1",
                         "评分点得分": "Q027P1=1"})],
            mode="append", input_dir=self.dir, include_qc=False,
        )
        self.assertEqual(second["meta"]["rows"], 2)
        history = os.path.join(self.dir, record_input.HISTORY_DIR)
        self.assertTrue(os.listdir(history))
        self.assertEqual(record_input.export_bytes(self.dir), read_bytes(path))

    def test_invalid_save_keeps_previous_file(self):
        record_input.save([base_row()], mode="replace", input_dir=self.dir, include_qc=False)
        before = read_bytes(record_input.input_path(self.dir))
        with self.assertRaises(record_input.InputError) as ctx:
            record_input.save([base_row(**{"学生编号": "X01"})], mode="replace",
                              input_dir=self.dir, include_qc=False)
        self.assertEqual(ctx.exception.status, 422)
        self.assertEqual(ctx.exception.code, "validation_failed")
        self.assertEqual(read_bytes(record_input.input_path(self.dir)), before)

    def test_invalid_mode_and_empty_save(self):
        with self.assertRaises(record_input.InputError) as ctx:
            record_input.save([base_row()], mode="merge", input_dir=self.dir)
        self.assertEqual(ctx.exception.code, "invalid_mode")
        with self.assertRaises(record_input.InputError) as ctx:
            record_input.save([], mode="replace", input_dir=self.dir)
        self.assertEqual(ctx.exception.code, "empty_rows")

    def test_empty_current(self):
        current = record_input.load_current(self.dir)
        self.assertFalse(current["exists"])
        self.assertEqual(current["stats"]["rows"], 0)
        self.assertEqual(current["header"], common.COLUMNS)


if __name__ == "__main__":
    unittest.main()
