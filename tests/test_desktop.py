# -*- coding: utf-8 -*-
"""桌面打包入口：根目录解析、只读构建标记与运行管理器降级。

运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

import desktop  # noqa: E402
import ui_server  # noqa: E402


class DesktopEntryTest(unittest.TestCase):
    def test_source_bundle_root_is_repo_root(self):
        self.assertEqual(os.path.abspath(desktop.bundle_root()), os.path.abspath(ROOT))

    def test_run_manager_can_be_disabled(self):
        runner = ui_server.RunManager(root=ROOT, enabled=False)
        self.assertFalse(runner.enabled)
        self.assertFalse(runner.start())
        status = runner.status()
        self.assertEqual(status["state"], "disabled")
        self.assertFalse(status["enabled"])
        self.assertTrue(status["reason"])

    def test_frozen_snapshot_marks_run_disabled(self):
        original = ui_server.IS_FROZEN
        ui_server.IS_FROZEN = True
        try:
            snapshot = ui_server.build_snapshot(ROOT)
        finally:
            ui_server.IS_FROZEN = original
        self.assertFalse(snapshot["meta"]["run_enabled"])
        self.assertTrue(snapshot["meta"]["run_disabled_reason"])
        self.assertEqual(snapshot["meta"]["students"], 40)
        self.assertEqual(len(snapshot["records"]), 806)


if __name__ == "__main__":
    unittest.main()
