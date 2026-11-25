# 本地桌面程序（v1）

版本：v1.0 ｜ 日期：2026-11-25 ｜ 仓库：smart-companion

## 1. 定位

把已有的“教研工作台”打包成一个**双击即用**的 Windows 单文件程序：

- 不需要安装 Python，不需要启动命令行，不需要手动打开浏览器；
- 原生 WebView 窗口（Edge WebView2），窗口标题为“智慧学伴 · 教研工作台”；
- 单文件内嵌 `ui/`、`out/` 与 `data/derived/作答记录_清洗版.csv`，默认不联网；
- 面向材料评审、现场演示和评委复核；源码版仍保留完整 9 步流水线与“重新分析”。

产物：`dist/智慧学伴.exe`（PyInstaller onefile，约 12 MB）。

## 2. 构建

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_desktop.ps1
# 排错时保留控制台：
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_desktop.ps1 -Console
```

构建脚本行为：

1. 解释器优先级 `$env:PYTHON` → DSH 自带 Python → PATH；
2. 在仓库内创建 `.venv-build`，安装 PyInstaller 与 pywebview（不改系统 Python）；
3. 以 `src/desktop.py` 为入口执行 PyInstaller：
   `--onefile`、`--windowed`、`--collect-all webview`；
   `--add-data ui;ui`、`out;out`、`data/derived;data/derived`；
4. 复制为 `dist/智慧学伴.exe`，打印体积。

本次构建环境：Python 3.12.14、PyInstaller 6.22.3、pywebview 6.2.1、pythonnet 3.2.1；
WebView2 Runtime 157/158（Windows 10/11 通常已自带）。

## 3. 运行

- 双击 `dist/智慧学伴.exe`。
- 程序在 `127.0.0.1` 上选一个空闲端口（默认从 8765 起顺延），启动本地快照与录入服务；
- 创建原生窗口加载 `http://127.0.0.1:<port>/`；关闭窗口时停止服务。
- 源码调试：
  ```bat
  python src\desktop.py
  python src\desktop.py --browser
  python src\desktop.py --port 0
  ```
- 若系统缺少 WebView2 或 pywebview 启动失败，会自动回退默认浏览器并打印原因。

## 4. 数据与写入边界

- 打包时把 `out/` 快照、清洗版 CSV、`data/raw/` 三表与 `ui/` 嵌入 onefile；运行时从 PyInstaller 的临时解压目录读取。
- 程序**不修改**内嵌的 `out/`、`data/raw/` 或任何原始数据。
- 唯一写路径是“数据录入”副本：源码态 `data/input/`，打包态 `%LOCALAPPDATA%\SmartCompanion\input\`；
  保存前备份到同目录 `_history/<时间戳>/`，不写 `_MEIPASS`。
- “重新分析”在打包版中停用：服务端返回 `409 read_only_build`，页面按钮显示“只读快照”并给出原因。
  这是刻意设计——onefile 内的 Python 不是可复跑的源码环境，避免给评委一个会失败的按钮。
- 需要重跑流水线时，在源码目录执行 `run.cmd all`，再重新执行 `build_desktop.ps1` 生成新快照。
- 页面仍只暴露 10 个白名单记录字段，不含作答原文、参考答案、评分点明细；不引入真实学生个人信息。

## 5. 结构

| 文件 | 作用 |
| --- | --- |
| `src/desktop.py` | 桌面入口：解析根目录、启动 `UiServer` 线程、创建 pywebview 窗口、关闭时释放服务 |
| `src/ui_server.py` | 复用既有快照/静态服务/API；新增 `IS_FROZEN`、`run_enabled`、录入/咨询路由与禁用重跑管理器 |
| `src/consult.py` | 可选教学咨询：DeepSeek/OpenAI SDK、配置读取、学生聚合摘要、错误映射；不参与流水线产物 |
| `config/consult.example.json` | 咨询配置模板；真实 `config/consult.json` 不入库，打包态读 `%LOCALAPPDATA%\SmartCompanion\consult.json` |
| `build_desktop.ps1` | 构建脚本（虚拟环境、PyInstaller 参数、产物重命名） |
| `tests/test_desktop.py` | 3 项回归：源码根目录、禁用运行管理器、冻结快照标记 |
| `ui/` | 七页工作台静态资源（含内容图谱知识网络、数据录入、教学咨询），随包内嵌；`demo/` 另由 `src/demo_site.py` 生成，不参与打包 |

桌面入口不复制业务逻辑：快照构建、记录白名单、HTTP 安全头、静态防穿越全部复用 `ui_server.py`。

## 6. 安全

- 服务只绑定 `127.0.0.1`，不监听局域网；
- 仅允许本机 `Host`、同源 `Origin` 与 `X-DSH-UI: 1` 发起 `POST /api/run`、录入写接口与咨询接口；
- CSP `default-src 'self'`，无内联脚本、无外部字体/图表库；
- 除用户显式发起教学咨询外，打包版不主动联网；不写注册表、不安装服务；录入副本与咨询配置写到 `%LOCALAPPDATA%\SmartCompanion`；
- onefile 启动时解压到系统临时目录，退出后由 PyInstaller 清理；不对临时目录做持久化假设。

## 7. 验证记录

- `python -m unittest discover -s tests -q`：**86 项全绿**（11 流水线 + 17 录入 + 29 UI/HTTP + 3 桌面 + 4 知识图谱投影 + 17 咨询 + 5 公开演示站点）；构建脚本额外安装 `openai` 与 `--collect-all openai`。
- 打包版 `--browser --port 8797`：
  `/api/health` 返回 `ok=true`、`artifacts_ready=true`；
  `/api/snapshot` 返回 40 名学生、806 条记录、`meta.run_enabled=false`；
  首页 200、静态资源 200；`/api/records/template` 200（195 字节 BOM+CRLF），
  806 行 CSV `POST /api/records?mode=replace` 返回 201，写入 `%LOCALAPPDATA%\SmartCompanion\input`。
- 打包版原生窗口：进程主窗口标题为“智慧学伴 · 教研工作台”，
  WebView 实际拉取 `/api/snapshot` 与全部静态模块，服务端日志无 4xx/5xx。
- 打包版知识网络（`--browser --port 8914`）：`/api/snapshot.meta` 返回 `graph_nodes=72`、`graph_edges=83`、`graph_resources=57`；`graph.version=content_graph/1`，excluded 教材 8 份；`/js/graph.js` 为最新三列布局资源；首页与 `/api/health` 均 200，`run_enabled=false`。
- 打包版咨询（`--browser --port 8915`，2026-11-25 重建）：`/api/health` 200；`/api/consult/status` 200、`configured=false`、`library_available=true`、`config_path=%LOCALAPPDATA%\SmartCompanion\consult.json`；`POST /api/consult` 未配置时 503；`/api/snapshot` 仍为 40 生/2 班/806 记录/`run_enabled=false`；`/js/consult.js` 200。
- Windows windowed 子系统的 `sys.stderr` / `sys.stdout` 可能为 `None`；`UiHandler.log_message` 与 `desktop._log` 已做空值保护，避免请求因访问日志写入失败而被重置连接。
- 最终构建（含可选咨询依赖）：`dist/智慧学伴.exe` 22,703,146 字节，SHA256 `A6E23658099DAA9A4FEB8C4DE31A0A1E61874DC8D7C2804DF0ED378597488138`。
- 源码版 `python src\desktop.py --port 8795` 同样加载成功。
- 现有 `run.cmd` 的 9 步流水线、契约校验、selfcheck 不受影响。

## 8. 已知边界

- 仅面向 Windows（PyInstaller 与 WebView2 组合）；macOS/Linux 需另建入口。
- 单文件每次启动都需解压，比源码版慢约 1–3 秒。
- 未做代码签名，部分机器首次运行可能触发 SmartScreen“更多信息 → 仍要运行”。
- 打包版的分析结果是**只读快照**；数据更新后必须重新构建，不能靠页面按钮重跑。
- 打包版支持“数据录入”副本（写用户目录），但不会自动并入官方诊断/建议。
- 若目标机器缺少 WebView2 Runtime，程序回退默认浏览器；此时仍是本地服务，不联网。
- `dist/`、`build/`、`.venv-build/` 不纳入版本管理；构建可重复，但产物不入库。
