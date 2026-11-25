# -*- coding: utf-8 -*-
"""ToolRegistry：把领域能力声明为可复用、可审计的工具。

每个工具声明：
    name        唯一名称
    description 面向计划与文档的用途说明
    consumes    前置产物（相对项目根，缺失则在执行前失败）
    produces    产物（执行后必须存在，记录 sha256）
    handler     (AgentContext) -> dict(summary, metrics, evidence)
"""
from __future__ import annotations

import contextlib
import io
import time
import traceback
from dataclasses import dataclass, field


class ToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: object
    consumes: tuple = ()
    produces: tuple = ()
    evidence: tuple = ()


@dataclass
class ToolResult:
    tool: str
    ok: bool
    summary: str = ""
    metrics: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)
    outputs: dict = field(default_factory=dict)
    stdout: str = ""
    error: str = ""
    elapsed_ms: int = 0

    def as_dict(self):
        return {
            "tool": self.tool,
            "ok": self.ok,
            "summary": self.summary,
            "metrics": self.metrics,
            "evidence": self.evidence,
            "outputs": self.outputs,
            "stdout": self.stdout,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
        }


class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, spec):
        if spec.name in self._tools:
            raise ToolError("工具重复注册：%s" % spec.name)
        self._tools[spec.name] = spec
        return spec

    def get(self, name):
        spec = self._tools.get(name)
        if spec is None:
            raise ToolError("未注册工具：%s（可用：%s）" % (name, "、".join(self.names())))
        return spec

    def names(self):
        return list(self._tools)

    def specs(self):
        return [self._tools[n] for n in self._tools]

    def call(self, name, ctx):
        spec = self.get(name)
        missing = [p for p in spec.consumes if not ctx.exists(p)]
        if missing:
            raise ToolError("%s 缺少前置产物：%s；请先运行 --task diagnose" % (
                name, "、".join(missing)))

        buf = io.StringIO()
        started = time.time()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                payload = spec.handler(ctx) or {}
        except Exception as exc:  # noqa: BLE001
            elapsed = int((time.time() - started) * 1000)
            return ToolResult(tool=name, ok=False, stdout=buf.getvalue(),
                              error="%s: %s" % (type(exc).__name__, exc),
                              elapsed_ms=elapsed)
        elapsed = int((time.time() - started) * 1000)

        missing_out = [p for p in spec.produces if not ctx.exists(p)]
        if missing_out:
            return ToolResult(tool=name, ok=False, stdout=buf.getvalue(),
                              error="工具未生成声明产物：%s" % "、".join(missing_out),
                              elapsed_ms=elapsed)

        outputs = {}
        for rel in spec.produces:
            digest = ctx.record(rel)
            if digest:
                outputs[rel] = digest
        evidence = list(spec.evidence) + list(payload.get("evidence") or [])
        return ToolResult(tool=name, ok=True,
                          summary=payload.get("summary", ""),
                          metrics=payload.get("metrics", {}),
                          evidence=evidence,
                          outputs=outputs,
                          stdout=buf.getvalue(),
                          elapsed_ms=elapsed)
