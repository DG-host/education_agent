"""智慧学伴·教研工作台：零依赖本地可视化服务。

只读读取 out/ 与清洗版 CSV，生成浏览器可消费的快照；
可选通过 POST /api/run 调用现有 9 步智能体流水线。

用法：
    python src/ui_server.py
    python src/ui_server.py --no-browser --port 8765
    python src/ui_server.py --port 0          # 测试用随机端口
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from common import load_json, now_iso, read_csv, sha256_file, to_float, to_int  # noqa: E402
import record_input  # noqa: E402
import graph_model  # noqa: E402
import consult as consult_mod  # noqa: E402

UI_VERSION = "ui/1.0"
SNAPSHOT_VERSION = "ui.snapshot/1"
UI_ROOT = os.path.join(ROOT, "ui")
IS_FROZEN = bool(getattr(sys, "frozen", False))
RUN_DISABLED_REASON = "打包版内嵌只读快照；重新分析请在源码目录运行 run.cmd all"
TRACE_PATH = "out/agent_trace.json"
GUARD_PATH = "out/guard_report.json"
CLEAN_DATASET = "data/derived/作答记录_清洗版.csv"

# 核心产物缺失时整站不可用；可选产物缺失只降级对应页面。
CORE_ARTIFACTS = [
    ("content", "out/content_map.json"),
    ("diagnosis", "out/diagnosis_all.json"),
    ("recommendations", "out/recommendations_all.json"),
    ("cases", "out/cases.json"),
    ("qc", "out/qc_report.json"),
    ("clean", "out/clean_report.json"),
    ("clean_dataset", CLEAN_DATASET),
]
OPTIONAL_ARTIFACTS = [
    ("guard", GUARD_PATH),
    ("trace", TRACE_PATH),
]

RECORD_FIELDS = [
    ("record_id", "记录编号"),
    ("student_id", "学生编号"),
    ("material_id", "材料编号"),
    ("topic_id", "主题编号"),
    ("node_id", "节点编号"),
    ("revision", "修订版本"),
    ("submitted_at", "模拟提交时间"),
    ("status", "评分状态"),
    ("score", "得分"),
    ("max_score", "满分"),
]


class SnapshotError(Exception):
    """快照构建失败；status 决定 HTTP 状态码。"""

    def __init__(self, code, message, status=500, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


def _rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def _resolve(root, rel):
    return os.path.join(root, *rel.split("/"))


def _artifact_rows(root, specs):
    rows = []
    for name, rel in specs:
        full = _resolve(root, rel)
        if not os.path.isfile(full):
            continue
        rows.append({
            "name": name,
            "path": rel,
            "bytes": os.path.getsize(full),
            "sha256": sha256_file(full),
        })
    return rows


def _read_json(path, label):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise SnapshotError("artifacts_missing", "缺少 %s" % label, 503,
                            {"missing": [label], "hint": "run.cmd all"})
    except json.JSONDecodeError as exc:
        raise SnapshotError("invalid_json", "%s 不是合法 JSON" % label, 500,
                            {"path": label, "line": exc.lineno, "column": exc.colno})
    except OSError as exc:
        raise SnapshotError("read_failed", "无法读取 %s" % label, 500,
                            {"path": label, "error": str(exc)})


def _read_records(root):
    path = _resolve(root, CLEAN_DATASET)
    if not os.path.isfile(path):
        raise SnapshotError("artifacts_missing", "缺少清洗版作答记录", 503,
                            {"missing": [CLEAN_DATASET], "hint": "run.cmd all"})
    try:
        header, rows, _ = read_csv(path)
    except Exception as exc:  # csv 编码/结构问题统一报 500
        raise SnapshotError("invalid_dataset", "清洗版作答记录读取失败", 500,
                            {"path": CLEAN_DATASET, "error": str(exc)})
    missing = [col for _, col in RECORD_FIELDS if col not in header]
    if missing:
        raise SnapshotError("invalid_dataset", "清洗版缺少必要列", 500,
                            {"path": CLEAN_DATASET, "missing_columns": missing})
    out = []
    for row in rows:
        rec = {}
        for key, col in RECORD_FIELDS:
            value = row.get(col, "")
            if key == "revision":
                rec[key] = to_int(value)
            elif key in ("score", "max_score"):
                rec[key] = to_float(value)
            else:
                rec[key] = value
        out.append(rec)
    out.sort(key=lambda r: r.get("record_id") or "")
    return out


def build_snapshot(root=ROOT, input_dir=None):
    """构建浏览器快照；纯函数，便于测试。"""
    root = os.path.abspath(root)
    input_dir = os.path.abspath(input_dir) if input_dir else record_input.default_input_dir(root)
    input_file = record_input.input_path(input_dir)
    missing = [rel for _, rel in CORE_ARTIFACTS if not os.path.isfile(_resolve(root, rel))]
    if missing:
        raise SnapshotError(
            "artifacts_missing",
            "分析产物不完整，请先运行 run.cmd all",
            503,
            {"missing": missing, "hint": "run.cmd all"},
        )

    docs = {}
    for name, rel in CORE_ARTIFACTS:
        if name == "clean_dataset":
            continue
        docs[name] = _read_json(_resolve(root, rel), rel)

    for name, rel in OPTIONAL_ARTIFACTS:
        full = _resolve(root, rel)
        docs[name] = _read_json(full, rel) if os.path.isfile(full) else None

    records = _read_records(root)
    diag = docs.get("diagnosis") or {}
    qc = docs.get("qc") or {}
    clean = docs.get("clean") or {}
    content = docs.get("content") or {}
    graph = graph_model.build(content)
    recs = docs.get("recommendations") or {}
    cases = docs.get("cases") or {}

    scope = diag.get("data_scope") or {}
    topics = content.get("topics") or []
    indicators = sum(len(t.get("indicators") or []) for t in topics)
    materials = content.get("materials_index") or []
    students = recs.get("students") or []
    rec_count = sum(len(s.get("items") or []) for s in students)
    case_list = cases.get("cases") or []

    changes = clean.get("changes")
    if isinstance(changes, list):
        change_count = len(changes)
    elif isinstance(changes, int):
        change_count = changes
    else:
        change_count = len(clean.get("change_records") or [])

    qc_after = clean.get("qc_after") or {}
    warnings = []
    for name, rel in OPTIONAL_ARTIFACTS:
        if docs.get(name) is None:
            warnings.append({"code": "optional_artifact_missing", "path": rel})

    meta = {
        "generated_at": diag.get("generated_at"),
        "students": scope.get("students") or len(diag.get("student_level") or []),
        "groups": scope.get("groups") or len((diag.get("group_level") or {}).get("by_class") or []),
        "raw_records": qc.get("rows") or len(records),
        "clean_records": len(records),
        "unique_events": scope.get("records"),
        "revisions_folded": qc.get("revisions_folded"),
        "anomalies": qc.get("anomaly_records"),
        "clean_anomalies": qc_after.get("anomaly_records"),
        "changes": change_count,
        "recommendations": rec_count,
        "cases": len(case_list),
        "topics": len(topics),
        "indicators": indicators,
        "materials": len(materials),
        "graph_nodes": graph["meta"]["node_counts"]["total"],
        "graph_edges": graph["meta"]["edge_counts"]["total"],
        "graph_resources": graph["meta"]["resources"],
        "run_enabled": not IS_FROZEN,
        "run_disabled_reason": RUN_DISABLED_REASON if IS_FROZEN else None,
        "input_enabled": True,
        "input_path": record_input.display_path(input_file, root),
        "input_exists": os.path.isfile(input_file),
    }

    sources = _artifact_rows(root, CORE_ARTIFACTS)
    for name, rel in OPTIONAL_ARTIFACTS:
        if docs.get(name) is not None:
            full = _resolve(root, rel)
            sources.append({
                "name": name,
                "path": rel,
                "bytes": os.path.getsize(full),
                "sha256": sha256_file(full),
            })

    return {
        "schema_version": SNAPSHOT_VERSION,
        "server_time": now_iso(),
        "meta": meta,
        "sources": sources,
        "docs": docs,
        "graph": graph,
        "records": records,
        "warnings": warnings,
    }


def _core_missing(root=ROOT):
    root = os.path.abspath(root)
    return [rel for _, rel in CORE_ARTIFACTS if not os.path.isfile(_resolve(root, rel))]


class RunManager:
    """单实例后台运行 9 步流水线，保持最近 200 行日志。"""

    def __init__(self, root=ROOT, command=None, enabled=None):
        self.root = os.path.abspath(root)
        self.enabled = (not IS_FROZEN) if enabled is None else bool(enabled)
        self.disabled_reason = None if self.enabled else RUN_DISABLED_REASON
        self.command = command or [
            sys.executable,
            os.path.join(self.root, "src", "agent", "run.py"),
            "--task", "all",
        ]
        self._lock = threading.Lock()
        self._proc = None
        self._thread = None
        self._state = "idle"
        self._started_at = None
        self._finished_at = None
        self._exit_code = None
        self._log = collections.deque(maxlen=200)

    def start(self):
        if not self.enabled:
            with self._lock:
                self._state = "disabled"
                self._log.clear()
                self._log.append(self.disabled_reason or "当前版本不支持重新分析")
            return False
        with self._lock:
            if self._state == "running":
                return False
            self._log.clear()
            self._state = "running"
            self._started_at = now_iso()
            self._finished_at = None
            self._exit_code = None
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            try:
                self._proc = __import__("subprocess").Popen(
                    self.command,
                    cwd=self.root,
                    env=env,
                    stdout=__import__("subprocess").PIPE,
                    stderr=__import__("subprocess").STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    shell=False,
                )
            except Exception as exc:
                self._state = "failed"
                self._finished_at = now_iso()
                self._exit_code = -1
                self._log.append("启动失败：%s" % exc)
                return True
            self._thread = threading.Thread(target=self._read, args=(self._proc,), daemon=True)
            self._thread.start()
            return True

    def _read(self, proc):
        try:
            if proc.stdout is not None:
                for line in proc.stdout:
                    self._log.append(line.rstrip("\r\n"))
            code = proc.wait()
        except Exception as exc:
            code = -1
            self._log.append("读取日志失败：%s" % exc)
        finally:
            if proc.stdout is not None:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
        with self._lock:
            self._exit_code = code
            self._state = "succeeded" if code == 0 else "failed"
            self._finished_at = now_iso()

    def status(self):
        with self._lock:
            return {
                "state": self._state,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "exit_code": self._exit_code,
                "enabled": self.enabled,
                "reason": self.disabled_reason,
                "log_tail": list(self._log),
            }


class UiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler, root=ROOT, runner=None, input_dir=None, consult_service=None):
        super().__init__(addr, handler)
        self.root = os.path.abspath(root)
        self.runner = runner or RunManager(self.root)
        self.input_dir = os.path.abspath(input_dir) if input_dir else record_input.default_input_dir(self.root)
        self.consult = consult_service or consult_mod.ConsultService(self.root)


class UiHandler(BaseHTTPRequestHandler):
    server_version = "SmartCompanionUI/1.0"
    protocol_version = "HTTP/1.1"

    MIME = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".mjs": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".ico": "image/x-icon",
        ".txt": "text/plain; charset=utf-8",
    }

    def log_message(self, fmt, *args):
        stream = sys.stderr
        if stream is None:
            return
        try:
            stream.write("[ui] %s - %s\n" % (self.address_string(), fmt % args))
        except Exception:
            pass

    def _security_headers(self):
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")

    def _send_json(self, status, payload, cache="no-store"):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_error(self, status, code, message, details=None):
        self._send_json(status, {"error": {"code": code, "message": message, "details": details or {}}})

    def _send_bytes(self, status, body, content_type, cache="no-cache", headers=None):
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _ui_file(self, path):
        root = os.path.realpath(os.path.join(self.server.root, "ui"))
        rel = unquote(path).lstrip("/")
        if rel in ("", "index.html"):
            target = os.path.join(root, "index.html")
        else:
            target = os.path.realpath(os.path.join(root, *rel.split("/")))
        root_real = os.path.realpath(root)
        if target != root_real and not target.startswith(root_real + os.sep):
            return None
        if not os.path.isfile(target):
            return None
        return target

    def _health(self):
        missing = _core_missing(self.server.root)
        generated_at = None
        diag_path = _resolve(self.server.root, "out/diagnosis_all.json")
        try:
            with open(diag_path, "r", encoding="utf-8") as fh:
                generated_at = json.load(fh).get("generated_at")
        except Exception:
            generated_at = None
        self._send_json(200, {
            "ok": True,
            "version": UI_VERSION,
            "port": self.server.server_port,
            "snapshot_at": generated_at,
            "artifacts_ready": not missing,
            "missing": missing,
        })

    def _snapshot(self):
        try:
            self._send_json(200, build_snapshot(self.server.root))
        except SnapshotError as exc:
            self._send_error(exc.status, exc.code, exc.message, exc.details)

    def _static(self, path):
        target = self._ui_file(path)
        if target is None:
            self._send_error(404, "not_found", "资源不存在", {"path": path})
            return
        try:
            with open(target, "rb") as fh:
                body = fh.read()
        except OSError as exc:
            self._send_error(500, "read_failed", "静态文件读取失败", {"error": str(exc)})
            return
        ext = os.path.splitext(target)[1].lower()
        self._send_bytes(200, body, self.MIME.get(ext, "application/octet-stream"))

    def _read_body(self, max_bytes=None):
        limit = record_input.MAX_BODY_BYTES if max_bytes is None else int(max_bytes)
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise record_input.InputError("length_required", "需要 Content-Length", 411)
        try:
            length = int(raw_length)
        except ValueError:
            raise record_input.InputError("length_required", "Content-Length 不是整数", 411)
        if length <= 0:
            raise record_input.InputError("length_required", "请求体为空", 411)
        if length > limit:
            raise record_input.InputError("payload_too_large", "请求体超过上限", 413,
                                          {"limit": limit})
        return self.rfile.read(length)

    def _records(self):
        if not self._local_ok():
            self._send_error(403, "forbidden", "只允许本机工作台读取录入副本",
                             {"hint": "需要 X-DSH-UI: 1 且 Host/Origin 合法"})
            return
        try:
            current = record_input.load_current(self.server.input_dir, self.server.root)
            self._send_json(200, {
                "schema_version": "input.view/1",
                **current,
            })
        except record_input.InputError as exc:
            self._send_error(exc.status, exc.code, exc.message, exc.details)

    def _template(self):
        if not self._local_ok():
            self._send_error(403, "forbidden", "只允许本机工作台下载模板",
                             {"hint": "需要 X-DSH-UI: 1 且 Host/Origin 合法"})
            return
        self._send_bytes(
            200, record_input.template_bytes(), "text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="answer_records_template.csv"'},
        )

    def _export(self):
        if not self._local_ok():
            self._send_error(403, "forbidden", "只允许本机工作台导出录入副本",
                             {"hint": "需要 X-DSH-UI: 1 且 Host/Origin 合法"})
            return
        try:
            body = record_input.export_bytes(self.server.input_dir, self.server.root)
        except record_input.InputError as exc:
            self._send_error(exc.status, exc.code, exc.message, exc.details)
            return
        self._send_bytes(
            200, body, "text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="answer_records.csv"'},
        )

    def _consult_status(self):
        if not self._local_ok():
            self._send_error(403, "forbidden", "只允许本机工作台读取咨询配置",
                             {"hint": "需要 X-DSH-UI: 1 且 Host/Origin 合法"})
            return
        try:
            self._send_json(200, self.server.consult.status())
        except consult_mod.ConsultError as exc:
            self._send_error(exc.status, exc.code, exc.message, exc.details)
        except Exception:
            self._send_error(500, "consult_status_failed", "无法读取咨询配置状态")

    def _consult(self):
        if not self._local_ok():
            self._send_error(403, "forbidden", "只允许本机工作台发起咨询",
                             {"hint": "需要 X-DSH-UI: 1 且 Host/Origin 合法"})
            return
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type != "application/json":
            self._send_error(415, "unsupported_media_type", "咨询接口只接受 application/json")
            return
        try:
            raw = self._read_body(consult_mod.MAX_REQUEST_BYTES)
        except record_input.InputError as exc:
            self._send_error(exc.status, exc.code, exc.message, exc.details)
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError:
            self._send_error(422, "invalid_encoding", "请求体必须是 UTF-8")
            return
        except json.JSONDecodeError as exc:
            self._send_error(422, "invalid_json", "请求体不是合法 JSON",
                             {"line": exc.lineno, "column": exc.colno})
            return
        try:
            request = consult_mod.normalize_request(payload)
            result = self.server.consult.ask(**request)
        except consult_mod.ConsultError as exc:
            self._send_error(exc.status, exc.code, exc.message, exc.details)
            return
        except Exception:
            self._send_error(500, "consult_failed", "咨询处理失败")
            return
        self._send_json(200, result)

    def _validate_records(self):
        if not self._local_ok():
            self._send_error(403, "forbidden", "只允许本机工作台校验录入数据",
                             {"hint": "需要 X-DSH-UI: 1 且 Host/Origin 合法"})
            return
        try:
            raw = self._read_body()
            rows, _ = record_input.parse_payload(raw, self.headers.get("Content-Type", ""))
            result = record_input.validate_rows(rows)
        except record_input.InputError as exc:
            self._send_error(exc.status, exc.code, exc.message, exc.details)
            return
        if result["errors"]:
            self._send_error(422, "validation_failed", "数据校验未通过", {
                "errors": result["errors"],
                "warnings": result["warnings"],
                "stats": result["stats"],
            })
            return
        self._send_json(200, {
            "ok": True,
            "rows": result["rows"],
            "preview": rows[:10],
            "errors": result["errors"],
            "warnings": result["warnings"],
            "stats": result["stats"],
            "qc": result["qc"],
        })

    def _save_records(self):
        if not self._local_ok():
            self._send_error(403, "forbidden", "只允许本机工作台保存录入数据",
                             {"hint": "需要 X-DSH-UI: 1 且 Host/Origin 合法"})
            return
        try:
            raw = self._read_body()
            rows, payload_mode = record_input.parse_payload(raw, self.headers.get("Content-Type", ""))
            query = parse_qs(urlsplit(self.path).query)
            mode = (query.get("mode") or [payload_mode or "replace"])[0]
            saved = record_input.save(rows, mode=mode, input_dir=self.server.input_dir, root=self.server.root)
        except record_input.InputError as exc:
            self._send_error(exc.status, exc.code, exc.message, exc.details)
            return
        self._send_json(201, {
            "ok": True,
            "rows": saved["meta"]["rows"],
            **saved,
        })

    def _local_ok(self):
        port = self.server.server_port
        host = (self.headers.get("Host") or "").lower()
        allowed_hosts = {"127.0.0.1:%d" % port, "localhost:%d" % port}
        if host not in allowed_hosts:
            return False
        origin = self.headers.get("Origin")
        if origin:
            allowed_origins = {"http://127.0.0.1:%d" % port, "http://localhost:%d" % port}
            if origin.lower() not in allowed_origins:
                return False
        return (self.headers.get("X-DSH-UI") or "") == "1"

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._health()
        elif path == "/api/snapshot":
            self._snapshot()
        elif path == "/api/run/status":
            self._send_json(200, self.server.runner.status())
        elif path == "/api/consult/status":
            self._consult_status()
        elif path == "/api/records":
            self._records()
        elif path == "/api/records/template":
            self._template()
        elif path == "/api/records/export":
            self._export()
        elif path.startswith("/api/"):
            self._send_error(404, "not_found", "接口不存在")
        elif path == "/favicon.ico":
            self._send_bytes(204, b"", "image/x-icon")
        else:
            self._static(path)

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/api/consult":
            self._consult()
            return
        if path == "/api/records/validate":
            self._validate_records()
            return
        if path == "/api/records":
            self._save_records()
            return
        if path != "/api/run":
            self._send_error(404, "not_found", "接口不存在")
            return
        if not self._local_ok():
            self._send_error(403, "forbidden", "只允许本机工作台发起运行", {"hint": "需要 X-DSH-UI: 1 且 Host/Origin 合法"})
            return
        if not getattr(self.server.runner, "enabled", True):
            self._send_error(409, "read_only_build", getattr(self.server.runner, "disabled_reason", None) or "只读版本")
            return
        started = self.server.runner.start()
        status = self.server.runner.status()
        if not started:
            self._send_json(409, {"error": {"code": "already_running", "message": "分析正在运行"}, "run": status})
            return
        self._send_json(202, {"state": status["state"], "started_at": status["started_at"]})

    def do_OPTIONS(self):
        self._send_error(405, "method_not_allowed", "不支持 OPTIONS")


def _port_candidates(start, count=11):
    if start == 0:
        return [0]
    return list(range(start, min(start + count, 65536)))


def serve(port=8765, no_browser=False, input_dir=None):
    last_error = None
    server = None
    for candidate in _port_candidates(port):
        try:
            server = UiServer(("127.0.0.1", candidate), UiHandler, input_dir=input_dir)
            break
        except OSError as exc:
            last_error = exc
            continue
    if server is None:
        raise SystemExit("无法启动本地服务：%s。请用 --port 指定其他端口。" % last_error)

    url = "http://127.0.0.1:%d/" % server.server_port
    print("智慧学伴·教研工作台已启动：%s" % url)
    print("按 Ctrl+C 停止；数据来自 out/，不会修改原始数据。")
    print("录入副本：%s" % record_input.display_path(record_input.input_path(server.input_dir), server.root))
    print("教学咨询配置：%s" % consult_mod.display_path(consult_mod.default_config_path(server.root), server.root))
    if not no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止…")
    finally:
        server.server_close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="智慧学伴·教研工作台（本地浏览器）")
    ap.add_argument("--port", type=int, default=8765, help="端口，默认 8765；被占用时自动尝试后续端口")
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    ap.add_argument("--input-dir", default=None, help="录入副本目录，默认 data/input 或用户数据目录")
    args = ap.parse_args(argv)
    serve(args.port, no_browser=args.no_browser, input_dir=args.input_dir)


if __name__ == "__main__":
    main()
