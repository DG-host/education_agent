# 智慧学伴 · 智能体研发仓库（v0.7.0）

“学情诊断与个性化学习”赛题的研发底座：把三类输入（课程要求、材料清单、模拟作答记录）
变成**三份可机检的 JSON 契约**，再由一条**可复现、可核对、带证据链**的智能体流水线
完成内容梳理、学情诊断和个性化建议。

一条命令验收：`run.cmd` 全绿。可视化工作台：双击 `run_ui.cmd`；单文件桌面程序：`dist\智慧学伴.exe`；
只读公开演示：`demo/` 静态站点（见下文）。工作台内含与作答记录同构的**数据录入接口**（页面 `#/input`，API `/api/records`）与可选的**教学咨询**（页面 `#/consult`，DeepSeek）。

## 快速开始

```bat
run.cmd                 :: 智能体全流程 + 回归测试 + 自检（推荐）
run_ui.cmd              :: 打开本地“教研工作台”（分析快照只读，可后台重跑）
run.cmd agent           :: 只跑智能体流水线（9 步）
run.cmd qc              :: 只跑质检 + 基线
run.cmd content         :: 只重建内容地图
run.cmd diagnose        :: 只跑清洗 → 内容 → 质检 → 诊断
run.cmd recommend       :: 只跑建议 → 守卫 → 案例 → 报告 → 契约
run.cmd report          :: 只跑案例 → 报告 → 契约
run.cmd validate        :: 只校验五份契约文件
run.cmd clean           :: 清空 out/（不重跑）
python src\demo_site.py --out demo   :: 生成只读静态演示站点
```

解释器优先级：`$env:PYTHON` → DSH 自带 python（含 jsonschema）→ PATH 上的 python。
流水线不需要 pip install，也不依赖大模型 API 或密钥——所有结论由确定性规则与统计生成，可离线复跑。
可选的“教学咨询”页才需要 DeepSeek Key；不配置时其余功能不受影响。

`run.cmd` 的三个阶段：

1. **agent**：9 步流水线，任何一步失败即停，写 `out/agent_trace.json`；
2. **tests**：86 项 unittest 回归（11 项流水线 + 17 项录入接口 + 29 项 UI/HTTP + 3 项桌面入口 + 4 项知识图谱投影 + 17 项教学咨询 + 5 项公开演示站点）；
3. **selfcheck**：原始数据 SHA256、源码零硬编码编号、关键产物双跑字节一致。

## 目录

| 路径 | 放什么 | 谁改 |
| --- | --- | --- |
| `data/raw/` | 赛题原始数据，只读；`SHA256SUMS.txt` 锁版本 | 谁都不改 |
| `data/derived/` | 清洗版作答记录、异常清单、变更记录、质量分析报告 | B（数据官） |
| `schemas/` | 三份单生契约 + 建议批次契约（draft-07，`schema_version` 固定 0.1.0） | 契约评审后冻结 |
| `src/` | 领域能力：`common.py` / `clean.py` / `qc.py` / `content_map.py` / `graph_model.py` / `recommend.py` / `guards.py` / `cases.py` / `report.py` / `validate.py` / `record_input.py` / `consult.py` | 各模块 owner |
| `src/agent/` | 编排运行时：`registry.py` / `plans.py` / `tools.py` / `runtime.py` / `context.py` / `run.py` | C（工程与表达官） |
| `tests/` | 86 项回归测试（清洗对账、契约、建议证据、守卫、计划、确定性；录入解析/校验/备份；UI 快照/HTTP/RunManager；知识图谱投影；教学咨询配置/上下文/错误映射；桌面入口；演示站点生成与脱敏） | C |
| `out/` | 所有机器产物（JSON + tables/*.csv），可由 `run.cmd clean` 重建 | 自动生成，不手改 |
| `examples/` | 输入样例与两份“单学生”输出样例（评委复核的入口） | C 维护 |
| `ui/` | 本地浏览器工作台：`index.html`、`demo-config.js`、`css/styles.css`、`js/{app,data,pages,components,format,input,graph,consult}.js` | C |
| `demo/` | 公开演示静态站点：`index.html`、`snapshot.json`、`demo-config.js`、`css/`、`js/`，无后端、无作答原文 | C |
| `src/demo_site.py` | 从 `ui/` + 一次快照生成 `demo/`，覆盖只读标记并脱敏质检明细 | C |
| `src/ui_server.py` | 只读快照 + 静态服务 + 数据录入 API + 后台重跑，仅监听 127.0.0.1 | C |
| `src/desktop.py` | 桌面入口：原生 WebView 窗口（pywebview），缺依赖时回退浏览器 | C |
| `build_desktop.ps1` | 构建单文件 `dist\智慧学伴.exe`（内嵌 `ui/`、`out/`、清洗版 CSV、原始三表） | C |
| `docs/` | 决策记录、质量报告、智能体框架文档、UI 设计说明、数据录入说明、教学咨询说明、公开演示说明、方案正文 | A/C |

## 智能体流水线

| # | 工具 | 做什么 | 主要产物 |
| --- | --- | --- | --- |
| 1 | `clean` | 原始数据与清洗版逐单元格对账，核对 10 处修正与变更记录 | `out/clean_report.json`、`out/tables/clean_changes.csv` |
| 2 | `content` | 课程要求 → 主题/指标/材料索引 | `out/content_map.json` |
| 3 | `qc` | 19 条规则质检，统计异常与覆盖 | `out/qc_report.json`、`out/tables/{anomalies,coverage,indicator_stats}.csv` |
| 4 | `diagnose` | 个体 + 群体两层学情诊断 | `out/diagnosis_all.json`、`examples/diagnosis_D01.json` |
| 5 | `recommend` | 40 名学生个性化建议批次 | `out/recommendations_all.json`、`examples/recommendation_D01.json` |
| 6 | `guard` | 证据、置信度、答案泄露、个人信息、覆盖 5 类守卫 | `out/guard_report.json` |
| 7 | `cases` | 三类典型案例与证据链、班级对比 | `out/cases.json`、`out/tables/{case_evidence,class_summary,class_indicators}.csv` |
| 8 | `report` | 汇总 Markdown 分析报告 | `out/report.md`、`out/tables/group_indicators.csv` |
| 9 | `validate` | 五份契约按 JSON Schema 校验 | 退出码 0/1 |

一次全量运行产出 18 个文件，步骤、耗时、产物哈希与守卫结论都写进 `out/agent_trace.json`。
查看工具清单与计划：

```bat
python src\agent\run.py --list-tools
python src\agent\run.py --task recommend --dry-run
```

## 本地桌面程序（单文件 EXE）

`dist\智慧学伴.exe` 是双击即用的本地程序：内置 Python 运行时、原生 WebView 窗口、`ui/` 与当前分析快照，
不要求目标机器安装 Python，也不依赖浏览器地址栏。每次启动会解压内置资源，约需数秒。

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_desktop.ps1
```

- 构建脚本在 `.venv-build` 安装 PyInstaller + pywebview + openai，不改系统环境；产物约 20–25 MB（含教学咨询依赖，本次 22.7 MB）。
- 打包版面向**演示与复核**：分析快照只读，“重新分析”停用；需要重跑时用源码版 `run.cmd all`。
- 依赖 Windows 10/11 自带的 Edge WebView2 Runtime；缺失时自动回退默认浏览器。
- 源码调试：`python src\desktop.py`；强制浏览器：`python src\desktop.py --browser`。
- 设计与构建说明见 `docs\desktop_app.md`。

## 公开演示（只读静态站点）

`demo/` 是工作台的静态副本：把 `ui/` 与一次 `out/` 快照（`snapshot.json`）打包，不需要 Python 或本地服务，
可直接放到 raw.githack / jsDelivr 等静态托管上，Mac 与手机浏览器都能看。

```text
https://raw.githack.com/DG-host/education_agent/main/demo/index.html
```

- 只开放总览、学生画像、典型案例、内容图谱、数据质量五页；“数据录入”与“教学咨询”在演示版隐藏，访问时显示“此页需要本地版”。
- 没有后端写接口，没有 `/api/run`；“重新分析”隐藏，刷新只重读同一份 `snapshot.json`。
- 记录仍是 10 个白名单字段，不含作答原文、解答过程、参考答案；质检 `expected/actual` 已脱敏。
- 仓库 `data/raw/` 与 `data/derived/` 本身是公开仓库的一部分；若这些文件不能公开，必须把 `demo/` 放到独立公开仓库。
- 生成、发布、更新、回滚与排障见 `docs/public_demo.md`。

## 可视化工作台

双击 `run_ui.cmd`（等价于 `run.ps1 -Task ui`），启动 `http://127.0.0.1:8765/` 并自动打开浏览器。
服务只监听回环地址：默认只读 `out/` 与 `data/derived/作答记录_清洗版.csv`；页面上的“重新分析”才会调用
既有 9 步流水线，运行中重复点击返回 409，不会并发。只有“数据录入”页会写**独立副本** `data/input/`，
不碰原始数据与官方产物。

| 页面 | 路由 | 看什么 |
| --- | --- | --- |
| 总览 | `#/overview` | 数据规模、两班对比、3×3 指标热力图、共性弱项、案例入口 |
| 学生画像 | `#/students` / `#/students/D03` | 40 生筛选、节点与 9 指标、建议时间线、证据记录、复测安排 |
| 典型案例 | `#/cases` / `#/cases/D03` | 三角色对照、“学习要求—已有表现—学习建议”、班级参照 |
| 内容图谱 | `#/content` | 知识网络骨架（3 主题 + 9 指标 + 3 课标）、65 材料索引、课标页/教材页/可用题目 |
| 数据质量 | `#/quality` | 质检异常、10 处修正、守卫 5 类、9 步轨迹、产物哈希 |
| 数据录入 | `#/input` | 粘贴/上传与作答记录同构的 14 列 CSV，校验、保存、导出当前副本 |
| 教学咨询 | `#/consult` | 向 DeepSeek 提问；可选带入某学生聚合诊断，回答按教学动作/材料/观察点组织 |

- 前端是原生 ES Module，无 npm / 构建链 / 图表库；图表用 CSS 与内联 SVG。
- 内容图谱页的“知识网络”默认只画知识骨架，材料层按需展开；边只来自 `content_map` 的显式出处，教材切片 B01–B08 未标主题/指标时不画，避免猜测挂接。
- 图谱布局为确定性三列（主题→指标→课标），材料以主指标环绕；无 `Math.random` 与力导向，双跑位置一致；移动端在画布内横向滚动。
- 记录只暴露 10 个白名单字段，不含作答原文、参考答案与评分点明细。
- 缺产物时页面返回 503 并列出缺失文件与 `run.cmd all` 提示。
- 需要固定端口或不自动开浏览器：`python src\ui_server.py --port 8790 --no-browser`。
- 数据录入页与 `/api/records` 的字段、错误码、备份与回滚见 `docs/data_input.md`。
- 教学咨询页、`/api/consult` 与 Key 配置见 `docs/consult_interface.md`。
- UI 设计、API 与安全边界见 `docs/ui_design.md`。

### 五层结构

1. **输入治理层**：原始/清洗/产物三分离，SHA256 锁版本，清洗改动可对账。
2. **领域能力层**：内容图谱、质检、诊断、建议、守卫、案例、报告，各自是纯函数或薄 CLI。
3. **工具注册层**：每个能力登记为 `ToolSpec(name, description, handler, consumes, produces, evidence)`；
   调用前检查前置产物是否存在，调用后记录 stdout/stderr 与产物哈希。
4. **编排运行时层**：`PlanStep(tool, why)` 组成计划，逐步执行、失败即停，写 trace 与步骤表。
5. **证据与合规层**：建议必须带 `evidence_refs`；守卫拦截低置信动作、答案泄露和个人信息。

## 契约

| 文件 | 回答什么问题 | 关键字段 | 消费者 |
| --- | --- | --- | --- |
| `out/content_map.json` | 这门课要求什么、材料怎么覆盖 | `topics[].indicators[]`、`standard{cr_id,pdf_pages,body_pages}`、`materials_index[]` | 任务 1 清单、任务 3 选材料 |
| `out/diagnosis_all.json` | 每个学生/每个群体现在什么水平、哪里没把握 | `student_level[].observed.coverage`、`by_indicator[].confidence`、`limitations[]` | 任务 2 摘要、任务 3 依据 |
| `out/recommendations_all.json` | 40 名学生的建议批次 | `students[].items[].{material_id,action,hint_level,evidence_refs,adjust_condition}` | 任务 3 交付、批量复核 |
| `examples/diagnosis_D01.json` | 单生诊断样例 | 同诊断契约 | 评委复核入口 |
| `examples/recommendation_D01.json` | 单生建议样例 | 同建议契约 | 评委复核入口 |

契约里所有编号沿用赛题原始口径（`T01–T03`、`T0xIx`、`Q001–Q054`、`B01–B08`、`L01–L03`、`D01–D40`、`DC01/DC02`、`N01/N02`），
不自造编码——换一份评测数据（10–20 名学生、100–400 条记录）时，只换 `data/raw/` 就能重跑。

## 数据录入接口

工作台“数据录入”页（`#/input`）或 HTTP API 接收与 `data/raw/作答记录.csv` **完全同构**的 14 列 CSV
（`记录编号,学生编号,材料编号,主题编号,节点编号,作答事件编号,修订版本,模拟提交时间,评分状态,得分,满分,学生最终作答,解答过程,评分点得分`），
也接受同字段 JSON。保存为 **UTF-8 BOM + CRLF**，多行引号字段原样保留。

| 方法与路径 | 作用 |
| --- | --- |
| `GET /api/records` | 当前录入副本（记录、meta、行数/学生数/唯一事件统计） |
| `GET /api/records/template` | 下载 14 列表头模板（BOM + CRLF） |
| `GET /api/records/export` | 导出当前副本 CSV |
| `POST /api/records/validate` | 只校验，不落盘；返回错误、警告、统计与质检预览 |
| `POST /api/records?mode=replace\|append` | 校验并保存；硬错误返回 422，不覆盖旧副本 |

- 写独立副本 `data/input/作答记录_录入.csv` 与 `.meta.json`，每次保存前备份到 `data/input/_history/<时间戳>/`；不碰 `data/raw/` 与 `out/`。
- **硬错误**（表头/列数、必填、ID 与外键、事件编号、修订版本、状态、得分与评分点互斥、重复记录）阻断保存。
- **警告**（主题不符、材料不在节点、满分不符、得分超满分、评分点合计≠得分）允许保存并原样列出；原始 806 行本就带 7 条异常，必须支持“带警告导入”。
- 录入副本只供工作台核对与导出，**不自动并入官方诊断/建议**；清洗、诊断、建议仍读 `data/derived/作答记录_清洗版.csv`，由既有 9 步流水线负责。
- 接口仅监听回环地址，要求同源 `Origin` 与 `X-DSH-UI: 1`；请求体上限 8 MB、10000 行。

字段、错误码、PowerShell/curl 示例与回滚方式见 `docs/data_input.md`。

## 教学咨询（可选 DeepSeek）

“教学咨询”页（`#/consult`）让教师用自然语言提问，模型以初中数学教师/教研员角色回答；
可选勾选“带入该生诊断”，只发送聚合统计，不发送作答原文、参考答案或个人信息。

```powershell
$env:DEEPSEEK_API_KEY = "sk-你的-key"
run_ui.cmd
```

也可复制 `config/consult.example.json` 为 `config/consult.json` 并填入 Key；该文件已加入 `.gitignore`。
打包版读取 `%LOCALAPPDATA%\SmartCompanion\consult.json`。

| 方法与路径 | 作用 |
| --- | --- |
| `GET /api/consult/status` | 脱敏配置状态（是否配置、模型、配置路径，不含 Key） |
| `POST /api/consult` | 提问；支持 `student_id`、`include_diagnosis`、最多 12 条历史 |

- 仅回环地址 + `X-DSH-UI: 1`；请求体上限 64 KB；单实例串行，避免并发耗尽额度。
- 未配置 Key、缺 `openai`、上游 401/429/超时分别返回明确错误码；不会把 Key 写入浏览器或日志。
- 咨询不进入 9 步流水线，不写 `out/`；结果供教师复核，不替代教师决策。
- 接口、上下文白名单、错误码与示例见 `docs/consult_interface.md`。

## 数据口径（四个坑，写进代码而不是靠记性）

1. **修订版本**：同一 `作答事件编号` 有多版本时取 `修订版本` 最大值，旧版本折叠但不删除（`revisions_folded` 计数可核）。
2. **未观测 ≠ 答错**：`待评分` 与 `未作答` 不记 0 分，只进 `observed.pending/unanswered`；覆盖度用“有记录的材料数 ÷ 节点可用题目数”。
3. **跨节点不可比**：不同测验节点的可用题目集合不同，只比指标层趋势，不比节点均分。
4. **覆盖率先行**：`confidence` 由观测条数决定（<5 低、<10 中、≥10 高）；低置信指标只允许“复习/补观察”，
   不允许直接刷题；无已评记录的学生只给 `observe`。

清洗规则（已与出题方口径对齐，见 `docs/decisions.md` D3–D5）：总分与评分点明细矛盾时，**以评分点明细为准下调总分，不改学生答案**；
改节点编号必须联动重写 `作答事件编号 = 学生-节点-材料`；每一处改动进 `作答记录_变更记录.csv`。

## 验收（12 条，全部可复跑）

| # | 断言 | 怎么看 |
| --- | --- | --- |
| 1 | `run.cmd` 从空 `out/` 跑通，退出码 0 | 三个阶段均打印 `ok` / `全部通过` |
| 2 | 智能体 9 步全过 | `out/agent_trace.json` 的 `status = ok`、`steps` 长度 9 |
| 3 | 原始数据检出 **7** 条异常，记录编号集合与既有异常清单完全一致 | `out/tables/anomalies.csv` |
| 4 | 清洗版检出 **0** 条异常；10 处修正与变更记录逐项一致 | `out/clean_report.json`、`out/tables/clean_changes.csv` |
| 5 | 建议守卫 5 类检查全过 | `out/guard_report.json` 的 `status = pass` |
| 6 | 五份契约校验通过；删一个必填字段必须失败并打印 JSON Pointer | `python src\validate.py`；删字段后退出码 1、打印 `/student_level/0` |
| 7 | 两次运行字节一致（质检 / 基线 / 内容图谱） | selfcheck 的 `两次运行字节一致` |
| 8 | `data/raw/` 与 `SHA256SUMS.txt` 一致 | selfcheck 的 `SHA256SUMS 校验通过（8 个文件）` |
| 9 | `src/` 递归零硬编码编号；86 项测试全绿（11 流水线 + 17 录入 + 29 UI/HTTP + 3 桌面 + 4 图谱 + 17 咨询 + 5 演示站点） | `run.cmd` 的 tests 阶段 + selfcheck |
| 10 | `run_ui.cmd` 启动七页工作台；390/1366/1920 无整页横向滚动；缺产物显示 503 | `tests/test_ui.py` + 浏览器人工验收 |
| 11 | 录入接口：模板/校验/保存/导出可用；806 行 0 错误 7 警告；非法行 422 且不覆盖旧副本 | `tests/test_record_input.py`、`tests/test_ui.py` |
| 12 | 咨询页：未配置 Key 显示路径与原因；配置后可提问；勾选诊断才发送学生聚合字段 | `tests/test_consult.py`、`tests/test_ui.py` + 浏览器人工验收 |
| 13 | 公开演示：`demo/` 无后端、无作答原文；五页可加载；390/1366 无整页横向滚动 | `tests/test_demo_site.py` + 公网 URL 人工验收 |

## 扩展方式

新增一个能力只需三步：

1. 在 `src/` 写纯函数或 `main()`，产物路径用常量声明；
2. 在 `src/agent/tools.py` 注册 `ToolSpec`（声明 `consumes` / `produces`），
   在 `src/agent/plans.py` 把工具插进对应计划并写清 `why`；
3. 在 `tests/test_pipeline.py` 增加断言，跑 `run.cmd` 确认 9 步与确定性不变；UI 改动同时跑 `python -m unittest tests.test_ui`。

## 三人分工

- **A 内容官**：`src/content_map.py`、`out/content_map.json`、任务 1 章节；负责 8 份教材切片（B01–B08）的主题归属。
- **B 数据官**：`src/clean.py`、`src/qc.py`、`src/validate.py`、`data/derived/`；负责异常判定与口径答疑。
- **C 工程与表达官**：`src/agent/`、`src/guards.py`、`src/ui_server.py`、`ui/`、`run.ps1`/`run.cmd`/`run_ui.cmd`、`tests/`、`examples/`、README 与演示脚本。

> 文件所有权见 `docs/decisions.md` D12；跨文件改动先改契约，再改实现。

## 已知边界（写进 open_questions，不藏着）

- 8 份教材切片未标主题，`materials_index[].topic_id` 输出 `null` 并列入待人工复核；
- 11 份材料（教材 + 3 张学习卡）不在任何测验节点的可用题目里，只作“学习建议材料”，不参与覆盖度分母；
- 模拟数据为抽样作答（每生 4–28 条），个体结论一律带 `confidence`，群体结论优先看指标层；
- 报告中的“满分率”是满分记录数 ÷ 已评记录数，不等同于得分率；
- 确定性流水线不调用大模型；“教学咨询”页可选接入 DeepSeek，不写契约、不进入诊断/建议；
- 工作台默认只读；仅“数据录入”页写独立副本 `data/input/`，录入副本不会自动进入官方诊断/建议；咨询对话只存在浏览器内存；
- 工作台为单机演示：一次加载 806 条记录，未做分页/多用户；窄屏宽表可横向滚动。
- 公开演示只脱敏 `demo/snapshot.json`，不会改变仓库其他目录的可见性；`data/raw/`、`data/derived/` 若不能公开，必须用独立公开仓库承载 `demo/`。
