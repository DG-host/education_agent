# -*- coding: utf-8 -*-
"""智能体 CLI：按计划调用工具，输出 trace 与证据链。

用法：
    python src/agent/run.py --task all
    python src/agent/run.py --task diagnose --dry-run
    python src/agent/run.py --list-tools
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
ROOT = os.path.dirname(SRC)
sys.path.insert(0, SRC)
sys.path.insert(0, ROOT)

from agent.context import AgentContext  # noqa: E402
from agent.plans import PLANS, build_plan  # noqa: E402
from agent.registry import ToolError  # noqa: E402
from agent.runtime import AgentRuntime  # noqa: E402
from agent.tools import build_registry  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="智慧学伴基础智能体")
    ap.add_argument("--task", default="all", choices=sorted(PLANS), help="任务计划")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不执行")
    ap.add_argument("--list-tools", action="store_true", help="列出已注册工具")
    ap.add_argument("--trace", default="out/agent_trace.json", help="trace 输出（相对项目根）")
    args = ap.parse_args(argv)

    registry = build_registry()
    if args.list_tools:
        for spec in registry.specs():
            print("%-9s %s" % (spec.name, spec.description))
            print("  前置：%s" % ("、".join(spec.consumes) or "无"))
            print("  产物：%s" % ("、".join(spec.produces) or "无"))
        return 0

    try:
        plan = build_plan(args.task)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    ctx = AgentContext(ROOT, os.path.join(ROOT, args.trace), dry_run=args.dry_run)
    runtime = AgentRuntime(ctx, registry, plan, args.task)
    try:
        return runtime.run()
    except ToolError as exc:
        print("智能体失败：%s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
