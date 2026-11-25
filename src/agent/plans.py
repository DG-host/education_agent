# -*- coding: utf-8 -*-
"""计划层：把任务拆成有序工具步骤，并写明每一步的理由。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanStep:
    tool: str
    why: str


REASONS = {
    "clean": "原始数据只读；总分与评分点矛盾时以评分点为准，所有修正可追溯",
    "content": "把课标条目、教材页、题目与指标映射成可复核的内容图谱",
    "qc": "19 条结构/唯一/取值/一致性/重复/外键规则，先量化异常再清洗",
    "diagnose": "个体与群体两层摘要；缺失、待评、未作答均按信息不足处理",
    "recommend": "按指标弱点选材料，每条建议带指标、记录、节点证据与调整条件",
    "guard": "落盘前查证据可解析、低置信不排练习、无答案泄露与个人信息",
    "cases": "选需要巩固/数据不足/稳定表现三类案例，展开证据链与班级对比",
    "report": "生成可复核的 Markdown 事实底稿，供 PDF、视频与答辩引用",
    "validate": "契约闸门：产物逐字段通过 JSON Schema，失败即阻断交付",
}

PLANS = {
    "all": ["clean", "content", "qc", "diagnose", "recommend", "guard", "cases", "report", "validate"],
    "diagnose": ["clean", "content", "qc", "diagnose"],
    "recommend": ["recommend", "guard", "cases", "report", "validate"],
    "report": ["cases", "report", "validate"],
    "validate": ["validate"],
}


def build_plan(task):
    if task not in PLANS:
        raise ValueError("未知任务：%s（可用：%s）" % (task, "、".join(PLANS)))
    return [PlanStep(tool=t, why=REASONS[t]) for t in PLANS[task]]
