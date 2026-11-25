# -*- coding: utf-8 -*-
"""作答记录录入：与 data/raw/作答记录.csv 完全同构的解析、校验与落盘。

设计边界：
- 只写独立的录入副本（源码态 data/input/，打包态 LOCALAPPDATA），绝不改 data/raw/ 与 out/；
- 硬错误阻断保存，警告允许保存并由既有质检/清洗流水线继续处理；
- 列名、顺序、BOM、CRLF 全部沿用 common.COLUMNS 与 common.write_csv。

用法（HTTP 由 src/ui_server.py 暴露；这里只提供纯函数）：
    python -c "import record_input; print(record_input.template_text())"
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import os
import shutil
import sys
import tempfile

import common
import qc

INPUT_SCHEMA_VERSION = "input/1.0"
INPUT_FILE = "作答记录_录入.csv"
META_FILE = "作答记录_录入.meta.json"
HISTORY_DIR = "_history"
MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_ROWS = 10000
MODES = ("replace", "append")
REQUIRED_COLUMNS = (
    "记录编号", "学生编号", "材料编号", "主题编号", "节点编号", "作答事件编号",
    "修订版本", "模拟提交时间", "评分状态", "满分",
)
OPTIONAL_COLUMNS = ("得分", "学生最终作答", "解答过程", "评分点得分")


class InputError(Exception):
    """可映射为 HTTP 状态的输入错误。"""

    def __init__(self, code, message, status=422, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


def default_input_dir(root=common.ROOT):
    """源码态写仓库 data/input；打包态写用户目录，避免写 _MEIPASS。"""
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "SmartCompanion", "input")
    return os.path.join(os.path.abspath(root), "data", "input")


def input_path(input_dir=None, root=common.ROOT):
    return os.path.join(input_dir or default_input_dir(root), INPUT_FILE)


def meta_path(input_dir=None, root=common.ROOT):
    return os.path.join(input_dir or default_input_dir(root), META_FILE)


def display_path(path, root=common.ROOT):
    """仓库内返回相对路径；打包态返回绝对路径，便于用户定位。"""
    root = os.path.abspath(root)
    path = os.path.abspath(path)
    try:
        rel = os.path.relpath(path, root)
    except ValueError:
        return path
    if rel.startswith(".."):
        return path
    return rel.replace(os.sep, "/")


def template_text():
    sio = io.StringIO()
    writer = csv.writer(sio, lineterminator="\r\n")
    writer.writerow(common.COLUMNS)
    return sio.getvalue()


def template_bytes():
    return b"\xef\xbb\xbf" + template_text().encode("utf-8")


def csv_text(rows):
    """把 14 列字典行写成 CSV 文本（不含 BOM，供剪贴板/测试使用）。"""
    sio = io.StringIO()
    writer = csv.writer(sio, lineterminator="\r\n")
    writer.writerow(common.COLUMNS)
    for row in rows:
        writer.writerow([row.get(col, "") for col in common.COLUMNS])
    return sio.getvalue()


def _row_dict(values):
    return {col: ("" if value is None else str(value)) for col, value in zip(common.COLUMNS, values)}


def parse_csv_text(text):
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = [cell.strip().lstrip("\ufeff") for cell in next(reader)]
    except StopIteration:
        raise InputError("empty_payload", "内容为空，至少需要包含表头", 422)
    if header != common.COLUMNS:
        raise InputError(
            "header_mismatch",
            "表头必须与作答记录完全一致（14 列、顺序固定）",
            422,
            {"expected": common.COLUMNS, "actual": header},
        )
    rows = []
    for index, values in enumerate(reader, start=1):
        if not any(str(cell).strip() for cell in values):
            continue
        if len(values) != len(common.COLUMNS):
            raise InputError(
                "row_width",
                "第 %d 行有 %d 列，应为 %d 列" % (index, len(values), len(common.COLUMNS)),
                422,
                {"row": index, "expected": len(common.COLUMNS), "actual": len(values)},
            )
        rows.append(_row_dict(values))
    if not rows:
        raise InputError("empty_rows", "只有表头，没有数据行", 422)
    if len(rows) > MAX_ROWS:
        raise InputError("too_many_rows", "最多接收 %d 行" % MAX_ROWS, 413, {"rows": len(rows)})
    return rows, None


def parse_json_rows(payload):
    mode = None
    if isinstance(payload, dict):
        if "rows" not in payload:
            raise InputError("invalid_json", "顶层对象必须包含 rows 数组", 422)
        mode = payload.get("mode")
        items = payload.get("rows")
    elif isinstance(payload, list):
        items = payload
    else:
        raise InputError("invalid_json", "JSON 必须是数组或 {rows: [...]} 对象", 422)
    if mode is not None and mode not in MODES:
        raise InputError("invalid_mode", "mode 只能是 replace 或 append", 422, {"mode": mode})
    if not isinstance(items, list):
        raise InputError("invalid_json", "rows 必须是数组", 422)
    if not items:
        raise InputError("empty_rows", "rows 数组为空", 422)
    if len(items) > MAX_ROWS:
        raise InputError("too_many_rows", "最多接收 %d 行" % MAX_ROWS, 413, {"rows": len(items)})
    rows = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise InputError("invalid_json", "第 %d 行不是对象" % index, 422, {"row": index})
        missing = [col for col in common.COLUMNS if col not in item]
        if missing:
            raise InputError(
                "json_missing_field",
                "第 %d 行缺少字段" % index,
                422,
                {"row": index, "missing": missing},
            )
        extra = [key for key in item if key not in common.COLUMNS]
        if extra:
            raise InputError(
                "json_unknown_field",
                "第 %d 行包含未知字段" % index,
                422,
                {"row": index, "unknown": extra},
            )
        values = []
        for col in common.COLUMNS:
            value = item.get(col)
            if value is None:
                values.append("")
            elif isinstance(value, bool):
                values.append("true" if value else "false")
            else:
                values.append(str(value))
        rows.append(_row_dict(values))
    return rows, mode


def parse_payload(raw, content_type=""):
    if not isinstance(raw, (bytes, bytearray)):
        raise InputError("invalid_payload", "请求体必须是字节", 400)
    if len(raw) > MAX_BODY_BYTES:
        raise InputError("payload_too_large", "请求体超过 8MB", 413, {"limit": MAX_BODY_BYTES})
    base = (content_type or "").split(";", 1)[0].strip().lower()
    if base in ("application/json", "text/json"):
        try:
            text = bytes(raw).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InputError("invalid_encoding", "JSON 必须是 UTF-8", 400, {"error": str(exc)})
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InputError("invalid_json", "JSON 解析失败", 400,
                             {"line": exc.lineno, "column": exc.colno, "error": exc.msg})
        return parse_json_rows(payload)
    if base in ("", "text/csv", "text/plain", "application/csv", "application/octet-stream"):
        try:
            text = bytes(raw).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InputError("invalid_encoding", "CSV 必须是 UTF-8（可带 BOM）", 400, {"error": str(exc)})
        return parse_csv_text(text)
    raise InputError("unsupported_media_type", "只接收 text/csv 或 application/json", 415,
                     {"content_type": content_type})


def _parse_time(value):
    text = common.g(value, "模拟提交时间") if isinstance(value, dict) else str(value or "").strip()
    if not text:
        return None, "模拟提交时间为空"
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = _dt.datetime.fromisoformat(candidate)
    except ValueError:
        return None, "模拟提交时间不是 ISO 8601 格式"
    if dt.tzinfo is None:
        return dt, "模拟提交时间缺少时区（建议 +08:00）"
    return dt, None


def _parse_points_strict(text, material_id):
    """严格解析评分点；parse_points 会静默忽略非法片段，这里逐段报错。"""
    text = str(text or "").strip()
    if not text:
        return [], []
    errors = []
    points = []
    for chunk in text.replace(";", "；").split("；"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            errors.append(("points_syntax", "评分点缺少等号：%s" % chunk))
            continue
        left, right = chunk.split("=", 1)
        left = left.strip()
        right = right.strip()
        if "P" not in left:
            errors.append(("points_syntax", "评分点缺少 P 序号：%s" % chunk))
            continue
        prefix, index_text = left.rsplit("P", 1)
        if prefix != material_id:
            errors.append(("points_material", "评分点 %s 不属于材料 %s" % (prefix, material_id)))
            continue
        try:
            index = int(index_text)
        except ValueError:
            errors.append(("points_syntax", "评分点序号不是整数：%s" % chunk))
            continue
        if index < 1:
            errors.append(("points_syntax", "评分点序号必须从 1 开始：%s" % chunk))
            continue
        try:
            value = float(right)
        except ValueError:
            errors.append(("points_syntax", "评分点分值不是数字：%s" % chunk))
            continue
        if value < 0:
            errors.append(("points_syntax", "评分点分值不能为负：%s" % chunk))
            continue
        points.append((prefix, index, value))
    return points, errors


def summarize(rows, ctx=None):
    ctx = ctx or qc.load_context()
    students = set()
    groups = set()
    events = set()
    status_counts = {common.STATUS_SCORED: 0, common.STATUS_PENDING: 0, common.STATUS_UNANSWERED: 0}
    for row in rows:
        sid = common.g(row, "学生编号")
        if sid:
            students.add(sid)
            if sid in ctx["roster"]:
                groups.add(ctx["roster"][sid]["group_id"])
        event = common.g(row, "作答事件编号")
        if event:
            events.add(event)
        status = common.g(row, "评分状态")
        if status in status_counts:
            status_counts[status] += 1
    return {
        "rows": len(rows),
        "students": len(students),
        "groups": len(groups),
        "unique_events": len(events),
        "revisions_folded": max(0, len(rows) - len(events)),
        "status_counts": status_counts,
    }


def _qc_summary(rows):
    # qc.check 内部按仓库相对路径写报告；临时文件必须与 common.ROOT 同盘。
    temp_dir = common.DERIVED if os.path.isdir(common.DERIVED) else common.ROOT
    fd, path = tempfile.mkstemp(prefix=".record-input-", suffix=".csv", dir=temp_dir)
    os.close(fd)
    try:
        common.write_csv(path, common.COLUMNS, [[row.get(col, "") for col in common.COLUMNS] for row in rows])
        report, _, _ = qc.check(path)
        return {
            "rows": report.get("rows"),
            "unique_events": report.get("unique_events"),
            "revisions_folded": report.get("revisions_folded"),
            "anomaly_records": report.get("anomaly_records"),
            "rule_hits": report.get("rule_hits"),
            "status_counts": report.get("status_counts"),
        }
    except Exception as exc:  # 质检预览失败不阻断录入校验
        return {"error": str(exc)}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _add(collection, code, message, row=None, field=None, value=None):
    item = {"code": code, "message": message}
    if row is not None:
        item["row"] = row
    if field:
        item["field"] = field
    if value is not None and value != "":
        item["value"] = value
    collection.append(item)


def validate_rows(rows, include_qc=True):
    """逐行校验；返回 {ok, errors, warnings, stats, qc}。"""
    if not rows:
        raise InputError("empty_rows", "没有可校验的数据行", 422)
    ctx = qc.load_context()
    materials = ctx["materials"]
    roster = ctx["roster"]
    nodes = ctx["nodes"]
    errors = []
    warnings = []
    seen_records = {}
    seen_versions = {}
    stats = {common.STATUS_SCORED: 0, common.STATUS_PENDING: 0, common.STATUS_UNANSWERED: 0}
    students = set()
    groups = set()
    events = set()

    for index, row in enumerate(rows, start=1):
        row = {col: ("" if row.get(col) is None else str(row.get(col))) for col in common.COLUMNS}
        record_id = common.g(row, "记录编号")
        student_id = common.g(row, "学生编号")
        material_id = common.g(row, "材料编号")
        topic_id = common.g(row, "主题编号")
        node_id = common.g(row, "节点编号")
        event_id = common.g(row, "作答事件编号")
        revision_text = common.g(row, "修订版本")
        time_text = common.g(row, "模拟提交时间")
        status = common.g(row, "评分状态")
        score_text = common.g(row, "得分")
        max_text = common.g(row, "满分")
        points_text = common.g(row, "评分点得分")

        for col in REQUIRED_COLUMNS:
            if not common.g(row, col):
                _add(errors, "required", "%s 不能为空" % col, index, col)

        checks = (
            ("记录编号", record_id, "record"),
            ("学生编号", student_id, "student"),
            ("材料编号", material_id, "material"),
            ("主题编号", topic_id, "topic"),
            ("节点编号", node_id, "node"),
        )
        for col, value, key in checks:
            if value and not common.ID_RE[key].match(value):
                _add(errors, "id_format", "%s 格式不合法：%s" % (col, value), index, col, value)

        if student_id and student_id not in roster:
            _add(errors, "unknown_student", "学生编号不在模拟学生表中：%s" % student_id, index, "学生编号", student_id)
        elif student_id:
            groups.add(roster[student_id]["group_id"])
        if material_id and material_id not in materials:
            _add(errors, "unknown_material", "材料编号不在题目与材料表中：%s" % material_id, index, "材料编号", material_id)
        if node_id and node_id not in nodes:
            _add(errors, "unknown_node", "节点编号不在测验节点表中：%s" % node_id, index, "节点编号", node_id)

        material = materials.get(material_id) or {}
        node = nodes.get(node_id) or {}
        if topic_id and material and topic_id != material.get("topic_id"):
            _add(warnings, "topic_mismatch", "主题 %s 与材料主题 %s 不一致" % (topic_id, material.get("topic_id")),
                 index, "主题编号", topic_id)
        if material_id and node and material_id not in node.get("questions", []):
            _add(warnings, "material_not_in_node", "材料 %s 不在节点 %s 的可用题目中" % (material_id, node_id),
                 index, "材料编号", material_id)
        if material and material.get("type") != "题目":
            _add(warnings, "non_question_material", "材料 %s 类型为 %s，通常不是题目" % (material_id, material.get("type")),
                 index, "材料编号", material_id)

        expected_event = "%s-%s-%s" % (student_id, node_id, material_id)
        if event_id and event_id != expected_event:
            _add(errors, "event_mismatch", "作答事件编号应为 %s，收到 %s" % (expected_event, event_id),
                 index, "作答事件编号", event_id)

        revision = None
        try:
            revision = int(revision_text)
        except ValueError:
            revision = None
        if revision is None or revision < 1:
            _add(errors, "revision_invalid", "修订版本必须是正整数", index, "修订版本", revision_text)

        submitted, time_warning = _parse_time(row)
        if submitted is None:
            _add(errors, "time_invalid", time_warning or "模拟提交时间不合法", index, "模拟提交时间", time_text)
        elif time_warning:
            _add(warnings, "time_timezone", time_warning, index, "模拟提交时间", time_text)
        if submitted is not None and node.get("date"):
            try:
                node_date = _dt.date.fromisoformat(str(node["date"])[:10])
                if submitted.date() < node_date:
                    _add(warnings, "submit_before_node", "提交日期早于节点日期 %s" % node.get("date"),
                         index, "模拟提交时间", time_text)
            except ValueError:
                pass

        if status and status not in common.VALID_STATUS:
            _add(errors, "status_invalid", "评分状态只能是已评分/待评分/未作答", index, "评分状态", status)
        elif status in stats:
            stats[status] += 1

        max_score = common.to_float(max_text)
        if max_score is None or max_score <= 0:
            _add(errors, "max_score_invalid", "满分必须是大于 0 的数字", index, "满分", max_text)
        elif material and material.get("max_score") is not None:
            if abs(max_score - float(material["max_score"])) > 1e-9:
                _add(warnings, "max_score_mismatch",
                     "满分 %.4g 与材料满分 %.4g 不一致" % (max_score, float(material["max_score"])),
                     index, "满分", max_text)

        score = common.to_float(score_text)
        if status == common.STATUS_SCORED:
            if score is None:
                _add(errors, "score_required", "已评分记录必须填写得分", index, "得分", score_text)
            elif max_score is not None and score > max_score:
                _add(warnings, "score_over_max", "得分 %.4g 大于满分 %.4g" % (score, max_score),
                     index, "得分", score_text)
        elif status in (common.STATUS_PENDING, common.STATUS_UNANSWERED):
            if score_text:
                _add(errors, "score_not_allowed", "%s 记录不得填写得分" % status, index, "得分", score_text)
            if points_text:
                _add(errors, "points_not_allowed", "%s 记录不得填写评分点得分" % status, index, "评分点得分", points_text)

        points, point_errors = _parse_points_strict(points_text, material_id)
        for code, message in point_errors:
            _add(errors, code, message, index, "评分点得分", points_text)
        if points:
            indexes = [item[1] for item in points]
            if len(indexes) != len(set(indexes)):
                _add(errors, "points_duplicate", "评分点序号重复", index, "评分点得分", points_text)
            total = sum(item[2] for item in points)
            if score is not None and abs(total - score) > 1e-9:
                _add(warnings, "points_sum_mismatch",
                     "评分点合计 %.4g 与得分 %.4g 不一致" % (total, score),
                     index, "评分点得分", points_text)
            if max_score is not None and total > max_score + 1e-9:
                _add(warnings, "points_over_max", "评分点合计 %.4g 超过满分 %.4g" % (total, max_score),
                     index, "评分点得分", points_text)

        if record_id:
            if record_id in seen_records:
                _add(errors, "duplicate_record", "记录编号重复：%s" % record_id, index, "记录编号", record_id)
            else:
                seen_records[record_id] = index
        if event_id and revision is not None:
            key = (event_id, revision)
            if key in seen_versions:
                _add(errors, "duplicate_revision", "同一作答事件的修订版本重复：%s v%d" % (event_id, revision),
                     index, "修订版本", revision_text)
            else:
                seen_versions[key] = index
        if student_id:
            students.add(student_id)
        if event_id:
            events.add(event_id)

    result = {
        "ok": not errors,
        "rows": len(rows),
        "students": len(students),
        "groups": len(groups),
        "unique_events": len(events),
        "revisions_folded": max(0, len(rows) - len(events)),
        "status_counts": stats,
        "errors": sorted(errors, key=lambda item: (item.get("row") or 0, item.get("field") or "", item["code"])),
        "warnings": sorted(warnings, key=lambda item: (item.get("row") or 0, item.get("field") or "", item["code"])),
        "qc": _qc_summary(rows) if include_qc else None,
    }
    result["stats"] = {
        "rows": result["rows"],
        "students": result["students"],
        "groups": result["groups"],
        "unique_events": result["unique_events"],
        "revisions_folded": result["revisions_folded"],
        "status_counts": result["status_counts"],
    }
    return result


def load_current(input_dir=None, root=common.ROOT):
    directory = input_dir or default_input_dir(root)
    path = input_path(directory)
    if not os.path.isfile(path):
        return {
            "exists": False,
            "path": display_path(path, root),
            "header": common.COLUMNS,
            "rows": [],
            "meta": None,
            "stats": {"rows": 0, "students": 0, "groups": 0, "unique_events": 0,
                      "revisions_folded": 0, "status_counts": {}},
        }
    try:
        header, rows, file_meta = common.read_csv(path)
    except Exception as exc:
        raise InputError("invalid_dataset", "录入副本读取失败", 500, {"path": display_path(path, root), "error": str(exc)})
    if header != common.COLUMNS:
        raise InputError("invalid_dataset", "录入副本表头与作答记录不一致", 500,
                         {"path": display_path(path, root), "expected": common.COLUMNS, "actual": header})
    meta = file_meta
    meta_file = meta_path(directory)
    if os.path.isfile(meta_file):
        try:
            stored = common.load_json(meta_file)
            meta = {**file_meta, **stored}
        except Exception:
            pass
    return {
        "exists": True,
        "path": display_path(path, root),
        "header": header,
        "rows": rows,
        "meta": meta,
        "stats": summarize(rows),
    }


def save(rows, mode="replace", input_dir=None, root=common.ROOT, include_qc=True):
    if mode not in MODES:
        raise InputError("invalid_mode", "mode 只能是 replace 或 append", 422, {"mode": mode})
    directory = input_dir or default_input_dir(root)
    target = input_path(directory)
    os.makedirs(directory, exist_ok=True)

    combined = list(rows)
    if mode == "append":
        current = load_current(directory, root)
        if current["exists"]:
            combined = current["rows"] + combined
    if not combined:
        raise InputError("empty_rows", "没有可保存的数据行", 422)

    result = validate_rows(combined, include_qc=include_qc)
    if result["errors"]:
        raise InputError("validation_failed", "数据未通过校验，未保存", 422, {
            "errors": result["errors"], "warnings": result["warnings"], "stats": result["stats"],
        })

    ordered = sorted(combined, key=lambda item: common.g(item, "记录编号"))
    if os.path.isfile(target):
        history = os.path.join(directory, HISTORY_DIR, _dt.datetime.now().strftime("%Y%m%dT%H%M%S%f"))
        os.makedirs(history, exist_ok=True)
        shutil.copy2(target, os.path.join(history, INPUT_FILE))

    fd, temp_path = tempfile.mkstemp(prefix=".record-input-", suffix=".csv", dir=directory)
    os.close(fd)
    try:
        common.write_csv(temp_path, common.COLUMNS,
                         [[row.get(col, "") for col in common.COLUMNS] for row in ordered])
        os.replace(temp_path, target)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise

    meta = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "saved_at": common.now_iso(),
        "source": "workbench",
        "mode": mode,
        "rows": len(ordered),
        "students": result["students"],
        "groups": result["groups"],
        "unique_events": result["unique_events"],
        "revisions_folded": result["revisions_folded"],
        "status_counts": result["status_counts"],
        "sha256": common.sha256_file(target),
        "bytes": os.path.getsize(target),
    }
    common.write_json(meta_path(directory), meta)
    return {
        "dataset": display_path(target, root),
        "path": display_path(target, root),
        "meta": meta,
        "stats": result["stats"],
        "warnings": result["warnings"],
        "qc": result["qc"],
        "mode": mode,
    }


def export_bytes(input_dir=None, root=common.ROOT):
    path = input_path(input_dir or default_input_dir(root))
    if not os.path.isfile(path):
        raise InputError("not_found", "还没有保存过录入数据", 404, {"path": display_path(path, root)})
    with open(path, "rb") as fh:
        return fh.read()
