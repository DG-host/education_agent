# -*- coding: utf-8 -*-
"""validate.py — 契约校验：所有产出必须能被 JSON Schema 机检通过。

用法：
    python src/validate.py            # 校验 out/ 与 examples/ 下的默认清单
    python src/validate.py --pair schema.json data.json   # 只校验一对

失败时打印 JSON Pointer 并以非 0 退出，便于 CI/脚本拦截。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import EXAMPLES, OUT, ROOT, SCHEMAS, load_json  # noqa: E402

try:
    import jsonschema
except ImportError:  # pragma: no cover
    print("缺少 jsonschema：请使用 run.ps1 选定的解释器运行", file=sys.stderr)
    raise SystemExit(2)

DEFAULT_PAIRS = [
    ("content_map.schema.json", os.path.join(OUT, "content_map.json")),
    ("diagnosis.schema.json", os.path.join(OUT, "diagnosis_all.json")),
    ("diagnosis.schema.json", os.path.join(EXAMPLES, "diagnosis_D01.json")),
    ("recommendation.schema.json", os.path.join(EXAMPLES, "recommendation_D01.json")),
]


def check_pair(schema_path, data_path):
    schema = load_json(schema_path)
    data = load_json(data_path)
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    return errors


def pointer(err):
    path = "/".join(str(p) for p in err.absolute_path)
    return "/" + path if path else "/"


def main(argv=None):
    ap = argparse.ArgumentParser(description="契约校验")
    ap.add_argument("--pair", nargs=2, metavar=("SCHEMA", "DATA"))
    ap.add_argument("--schema-dir", default=SCHEMAS)
    args = ap.parse_args(argv)

    pairs = [(args.pair[0], args.pair[1])] if args.pair else DEFAULT_PAIRS
    failed = 0
    for schema_name, data_path in pairs:
        # --pair 的路径按“当前目录”解释（命令行直觉）；默认清单按 schema 目录解释
        if os.path.isabs(schema_name):
            schema_path = schema_name
        elif args.pair:
            schema_path = os.path.abspath(schema_name)
        else:
            schema_path = os.path.join(args.schema_dir, schema_name)
        if not os.path.exists(schema_path):
            print("缺 schema: %s" % schema_path, file=sys.stderr)
            failed += 1
            continue
        if not os.path.exists(data_path):
            print("缺数据: %s" % data_path, file=sys.stderr)
            failed += 1
            continue
        errors = check_pair(schema_path, data_path)
        label = os.path.relpath(data_path, ROOT).replace("\\", "/")
        if errors:
            failed += 1
            print("FAIL %s (%d 处)" % (label, len(errors)))
            for e in errors[:10]:
                print("  %s %s" % (pointer(e), e.message))
        else:
            print("ok   %s" % label)
    if failed:
        print("契约校验失败：%d 个文件不合规" % failed, file=sys.stderr)
        return 1
    print("契约校验通过：%d 个文件" % len(pairs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
