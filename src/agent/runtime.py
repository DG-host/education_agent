# -*- coding: utf-8 -*-
"""运行时：执行计划、做前置/产物检查、记录证据链与 trace。"""
from __future__ import annotations

import os
import traceback

from common import ensure_dirs, now_iso, write_csv, write_json

from .registry import ToolError

TRACE = "out/agent_trace.json"
STEPS_TABLE = "out/tables/agent_steps.csv"


class AgentRuntime:
    def __init__(self, ctx, registry, plan, task):
        self.ctx = ctx
        self.registry = registry
        self.plan = plan
        self.task = task
        self.steps = []

    def run(self):
        ensure_dirs()
        if self.ctx.dry_run:
            print("计划（%s）：" % self.task)
            for i, step in enumerate(self.plan, 1):
                print("  %d. %-9s %s" % (i, step.tool, step.why))
            return 0

        started = now_iso()
        status = "ok"
        error = ""
        for i, step in enumerate(self.plan, 1):
            spec = self.registry.get(step.tool)
            print("[%d/%d] %s — %s" % (i, len(self.plan), spec.name, spec.description))
            try:
                result = self.registry.call(spec.name, self.ctx)
            except ToolError as exc:
                result = None
                error = str(exc)
                status = "failed"
                print("  ! %s" % error)
                self.steps.append({
                    "seq": i, "tool": spec.name, "why": step.why, "ok": False,
                    "summary": "", "metrics": {}, "evidence": list(spec.evidence),
                    "outputs": {}, "stdout": "", "error": error, "elapsed_ms": 0,
                })
                break
            except Exception as exc:  # noqa: BLE001
                error = "%s: %s" % (type(exc).__name__, exc)
                status = "failed"
                print("  ! %s" % error)
                self.steps.append({
                    "seq": i, "tool": spec.name, "why": step.why, "ok": False,
                    "summary": "", "metrics": {}, "evidence": list(spec.evidence),
                    "outputs": {}, "stdout": traceback.format_exc(), "error": error, "elapsed_ms": 0,
                })
                break

            log = (result.stdout or "").strip()
            if log:
                for line in log.splitlines():
                    print("  | %s" % line)
            if not result.ok:
                status = "failed"
                error = result.error
                print("  ! %s" % error)
            else:
                print("  ok %s（%d ms）" % (result.summary, result.elapsed_ms))
            entry = result.as_dict()
            entry.update({"seq": i, "why": step.why})
            self.steps.append(entry)
            if status != "ok":
                break

        trace = {
            "schema_version": "0.1.0",
            "task": self.task,
            "started_at": started,
            "finished_at": now_iso(),
            "status": status,
            "error": error,
            "plan": [{"seq": i, "tool": s.tool, "why": s.why} for i, s in enumerate(self.plan, 1)],
            "steps": self.steps,
            "artifacts": dict(sorted(self.ctx.artifacts.items())),
            "guardrails": {
                "raw_inputs_read_only": True,
                "diagnosis_on_cleaned_dataset": True,
                "contract_validation_required": True,
                "recommendation_evidence_required": True,
                "reference_answer_not_used_for_recommendation": True,
            },
        }
        write_json(self.ctx.trace_path, trace)
        write_csv(os.path.join(self.ctx.root, STEPS_TABLE),
                  ["序号", "工具", "结果", "耗时ms", "摘要", "证据", "产物"],
                  [[s["seq"], s["tool"], "ok" if s["ok"] else "FAIL", s["elapsed_ms"],
                    s["summary"], "；".join(s["evidence"]), "；".join(sorted(s["outputs"]))]
                   for s in self.steps])
        print("")
        print("trace：%s（%s，%d 步）" % (
            os.path.relpath(self.ctx.trace_path, self.ctx.root), status, len(self.steps)))
        if status != "ok":
            print("失败：%s" % error)
            return 1
        print("全部步骤通过，产物 %d 个" % len(self.ctx.artifacts))
        return 0
