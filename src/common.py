# -*- coding: utf-8 -*-
"""共享工具：路径、编码安全读写、稳定序列化、编号与评分点解析。

约定：
- 原始 CSV 为 UTF-8 with BOM + CRLF，多行引号字段原样保留，读后写回不改变编码骨架。
- 输出 JSON 一律 ensure_ascii=False、indent=2、LF 结尾、键序固定 → 两次运行字节相同。
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
DERIVED = os.path.join(ROOT, "data", "derived")
OUT = os.path.join(ROOT, "out")
TABLES = os.path.join(OUT, "tables")
SCHEMAS = os.path.join(ROOT, "schemas")
EXAMPLES = os.path.join(ROOT, "examples")

# 置信度门槛：同一指标的有效观测条数低于此值，只能给 low confidence。
MIN_N_FOR_CONFIDENCE = 5

STATUS_SCORED = "\u5df2\u8bc4\u5206"      # 已评分
STATUS_PENDING = "\u5f85\u8bc4\u5206"     # 待评分
STATUS_UNANSWERED = "\u672a\u4f5c\u7b54" # 未作答
VALID_STATUS = (STATUS_SCORED, STATUS_PENDING, STATUS_UNANSWERED)

COLUMNS = [
    "\u8bb0\u5f55\u7f16\u53f7", "\u5b66\u751f\u7f16\u53f7", "\u6750\u6599\u7f16\u53f7",
    "\u4e3b\u9898\u7f16\u53f7", "\u8282\u70b9\u7f16\u53f7", "\u4f5c\u7b54\u4e8b\u4ef6\u7f16\u53f7",
    "\u4fee\u8ba2\u7248\u672c", "\u6a21\u62df\u63d0\u4ea4\u65f6\u95f4", "\u8bc4\u5206\u72b6\u6001",
    "\u5f97\u5206", "\u6ee1\u5206", "\u5b66\u751f\u6700\u7ec8\u4f5c\u7b54",
    "\u89e3\u7b54\u8fc7\u7a0b", "\u8bc4\u5206\u70b9\u5f97\u5206",
]

ID_RE = {
    "student": re.compile(r"^D\d{2}$"),
    "material": re.compile(r"^[QBL]\d{3}$"),
    "topic": re.compile(r"^T0[1-3]$"),
    "indicator": re.compile(r"^T0[1-3]I[1-9]$"),
    "node": re.compile(r"^N\d{2}$"),
    "record": re.compile(r"^DR\d{4}$"),
}

POINT_RE = re.compile(r"([A-Z]\d{3})P(\d+)\s*=\s*([0-9.]+)")


def ensure_dirs() -> None:
    for d in (OUT, TABLES):
        os.makedirs(d, exist_ok=True)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: str):
    """返回 (header, rows, meta)。meta 记录 BOM 与换行风格，便于反向核对。"""
    with open(path, "rb") as f:
        blob = f.read()
    has_bom = blob.startswith(b"\xef\xbb\xbf")
    text = blob.decode("utf-8-sig")
    crlf = "\r\n" in text
    reader = csv.reader(io.StringIO(text, newline=""))
    rows_raw = list(reader)
    header = [c.strip() for c in rows_raw[0]] if rows_raw else []
    rows = [dict(zip(header, r)) for r in rows_raw[1:] if any(c.strip() for c in r)]
    meta = {"bom": has_bom, "crlf": crlf, "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
    return header, rows, meta


def write_csv(path: str, header, rows) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(buf.getvalue())


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")


def load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def g(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


def to_float(value: str):
    value = (value or "").strip()
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def to_int(value: str):
    f = to_float(value)
    return None if f is None else int(round(f))


def parse_points(text: str):
    """'\u8bc4\u5206\u70b9\u5f97\u5206' → [(material_id, point_index, value)]；空值返回 []。"""
    text = (text or "").strip()
    if not text:
        return []
    out = []
    for mid, idx, val in POINT_RE.findall(text):
        out.append((mid, int(idx), float(val)))
    return out


def ratio(num, den):
    if not den:
        return None
    return round(num / den, 4)


def confidence(n: int) -> str:
    if n >= MIN_N_FOR_CONFIDENCE * 2:
        return "high"
    if n >= MIN_N_FOR_CONFIDENCE:
        return "medium"
    return "low"


def now_iso() -> str:
    import datetime
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


CN_RE = re.compile(r"[\u4e00-\u9fff]")
UNIT_RE = re.compile(r"(元|人|只|个|厘米|米|千米|吨|岁|分钟|分|秒|度|平方米|立方米|件|本|支|元/支)")


def norm_answer(text: str) -> str:
    """把学生答案/参考答案归一化到可比较形态：去空白、去全角、去单位、去中文、去前导「x=」。"""
    s = (text or "").strip().replace("\u3000", "").replace(" ", "")
    for a, b in (("\uff1c", "<"), ("\uff1e", ">"), ("\uff08", "("), ("\uff09", ")"),
                 ("\uff0c", ","), ("\u3001", ","), ("\uff1b", ";"), ("\uff1a", ":"), ("\u3002", "")):
        s = s.replace(a, b)
    s = re.sub(r"^[a-zA-Z]=|^[a-zA-Z]:", "", s)
    s = UNIT_RE.sub("", s)
    s = CN_RE.sub("", s)
    s = s.replace("\u00d7", "*").replace("\u00b2", "^2").replace("\u2212", "-")
    return s.strip().lower()


def near_equal(a: str, b: str) -> bool:
    """去掉括号后仍相等即视为同一答案（(4x+6) 与 4x+6）。"""
    f = lambda x: x.replace("(", "").replace(")", "").replace("[", "").replace("]", "")
    return f(a) == f(b)


def interval_ops(text: str):
    """提取不等式解集的端点方向：[(数值, 相邻比较符)]，两侧比较符不成对时返回 []。"""
    s = (text or "").replace(" ", "").replace("\u3000", "")
    s = s.replace("\uff1c", "<").replace("\uff1e", ">")
    if not any(c in s for c in "<>"):
        return []
    ops = []
    for m in re.finditer(r"\d+(?:\.\d+)?", s):
        i, j = m.start(), m.end()
        left = s[i - 1] if i > 0 else ""
        right = s[j] if j < len(s) else ""
        if right in "<>\u2264\u2265":
            ops.append((m.group(0), right))
        elif left in "<>\u2264\u2265":
            ops.append((m.group(0), left))
    return sorted(ops) if len(ops) >= 2 else []


def norm_ws(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").replace("\u3000", " "))
