"""本地桌面入口：内置快照服务 + 原生 WebView 窗口。

源码运行：
    python src/desktop.py
    python src/desktop.py --browser      # 回退默认浏览器
    python src/desktop.py --port 0       # 测试随机端口

打包运行：
    build_desktop.ps1 生成 dist/智慧学伴.exe
    单文件内嵌 ui/、out/ 与清洗版 CSV，双击即用，不依赖 Python。
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import ui_server  # noqa: E402

APP_NAME = "智慧学伴 · 教研工作台"
WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900
MIN_SIZE = (1024, 720)


def bundle_root():
    """打包后从 _MEIPASS 读取内嵌快照；源码运行使用仓库根目录。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return ui_server.ROOT


def create_server(port=8765, root=None):
    root = os.path.abspath(root or bundle_root())
    last_error = None
    for candidate in ui_server._port_candidates(port):
        try:
            return ui_server.UiServer(("127.0.0.1", candidate), ui_server.UiHandler, root=root)
        except OSError as exc:
            last_error = exc
    raise SystemExit("无法启动本地服务（端口 %s）：%s" % (port, last_error))


def wait_ready(port, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def _wait_forever(server):
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


def _log(message):
    if sys.stdout is not None:
        try:
            print(message)
        except Exception:
            pass


def _run_browser(url, server):
    webbrowser.open(url)
    _log("工作台已启动：%s" % url)
    _log("关闭本窗口或按 Ctrl+C 停止服务。")
    _wait_forever(server)


def _run_window(url, server):
    try:
        import webview  # 延迟导入，缺少依赖时回退浏览器
    except Exception as exc:
        _log("未安装 pywebview（%s），回退默认浏览器。" % exc)
        _run_browser(url, server)
        return

    try:
        window = webview.create_window(
            APP_NAME,
            url,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=MIN_SIZE,
            background_color="#F4F7F7",
            text_select=True,
        )
        webview.start(debug=bool(os.environ.get("SMART_COMPANION_DEBUG")))
        # 正常关闭窗口后，释放后台服务。
        server.shutdown()
        server.server_close()
        del window
    except Exception as exc:
        _log("原生窗口启动失败（%s），回退默认浏览器。" % exc)
        _run_browser(url, server)


def run(port=8765, browser=False):
    server = create_server(port)
    url = "http://127.0.0.1:%d/" % server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if not wait_ready(server.server_port):
        server.server_close()
        raise SystemExit("本地服务未能在预期时间内就绪：%s" % url)
    if browser:
        _run_browser(url, server)
    else:
        _run_window(url, server)


def main(argv=None):
    ap = argparse.ArgumentParser(description="智慧学伴·教研工作台（本地桌面程序）")
    ap.add_argument("--port", type=int, default=8765, help="端口，默认 8765；被占用时自动顺延")
    ap.add_argument("--browser", action="store_true", help="不建原生窗口，改用默认浏览器")
    args = ap.parse_args(argv)
    run(args.port, browser=args.browser)


if __name__ == "__main__":
    main()
