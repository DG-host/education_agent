# -*- coding: utf-8 -*-
"""生成公开只读演示站点（demo/）。

只复制 ui/ 前端与一个脱敏快照；不复制 data/、out/、dist/ 或 config/。
生成后可用任意静态服务器预览，或把 demo/ 发布到静态托管。

用法：
    python src/demo_site.py
    python src/demo_site.py --out demo
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import common  # noqa: E402
import ui_server  # noqa: E402

DEMO_DIR = os.path.join(ROOT, "demo")
SNAPSHOT_NAME = "snapshot.json"
CONFIG_NAME = "demo-config.js"
UI_DIR = os.path.join(ROOT, "ui")


MASK = "（公开演示已隐去）"


def _sanitize_docs(snapshot: dict) -> None:
    """公开演示不展示质检命中的原始取值（可能含学生作答片段）。"""
    qc = (snapshot.get("docs") or {}).get("qc") or {}
    for finding in qc.get("findings") or []:
        for rule in finding.get("rules") or []:
            if "expected" in rule:
                rule["expected"] = MASK
            if "actual" in rule:
                rule["actual"] = MASK
            if "note" in rule:
                rule["note"] = ""


def _write_config(path: str) -> None:
    text = "/* 由 src/demo_site.py 生成：公开演示只读快照。 */\nwindow.DSH_DEMO = true;\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def build(demo_dir: str = DEMO_DIR, root: str = ROOT) -> dict:
    """生成 demo/，返回生成摘要；不修改 data/、out/ 或配置。"""
    root = os.path.abspath(root)
    demo_dir = os.path.abspath(demo_dir)
    ui_dir = os.path.join(root, "ui")
    if not os.path.isdir(ui_dir):
        raise FileNotFoundError("缺少前端目录：%s" % ui_dir)
    if demo_dir == root or demo_dir == ui_dir:
        raise ValueError("demo 目录不能是仓库根或 ui/ 本身")

    snapshot = ui_server.build_snapshot(root=root)
    meta = snapshot.setdefault("meta", {})
    meta["demo"] = True
    meta["demo_note"] = "公开只读演示；不含学生作答原文、参考答案或个人信息字段。"
    meta["run_enabled"] = False
    meta["run_disabled_reason"] = "公开演示站点为只读快照；重新分析请在本地源码目录运行 run.cmd all"
    meta["input_enabled"] = False
    meta["input_path"] = ""
    meta["input_exists"] = False
    if meta.get("generated_at"):
        snapshot["server_time"] = meta["generated_at"]
    _sanitize_docs(snapshot)

    if os.path.isdir(demo_dir):
        shutil.rmtree(demo_dir)
    shutil.copytree(ui_dir, demo_dir)
    _write_config(os.path.join(demo_dir, CONFIG_NAME))
    common.write_json(os.path.join(demo_dir, SNAPSHOT_NAME), snapshot)

    return {
        "demo_dir": demo_dir,
        "snapshot_bytes": os.path.getsize(os.path.join(demo_dir, SNAPSHOT_NAME)),
        "records": len(snapshot.get("records") or []),
        "students": meta.get("students"),
        "graph_nodes": meta.get("graph_nodes"),
        "graph_edges": meta.get("graph_edges"),
        "generated_at": meta.get("generated_at"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成公开只读演示站点")
    parser.add_argument("--out", default=DEMO_DIR, help="输出目录（默认仓库 demo/）")
    args = parser.parse_args(argv)
    info = build(args.out)
    print("演示站点已生成：%s" % info["demo_dir"])
    print("快照：%d 字节，%d 条记录，%s 名学生，%s 个图节点 / %s 条边"
          % (info["snapshot_bytes"], info["records"], info["students"],
             info["graph_nodes"], info["graph_edges"]))
    print("本地预览：python -m http.server 8000 --directory demo")
    print("打开：http://127.0.0.1:8000/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
