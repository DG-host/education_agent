# 智慧学伴 · 基础智能体框架技术文档

版本：v1.0 ｜ 日期：2026-11-16 ｜ 仓库：smart-companion ｜ 状态：可运行基线

## 0. 一句话结论

本框架把“学习内容梳理—学情诊断—个性化建议”三项赛题任务组织成一条**可编排、可核对、可泛化**的确定性流水线：原始数据只读进入，经可追溯清洗、19 条规则质检、内容图谱、个体/群体诊断、规则化建议、5 类守卫、三案例与报告，最后通过 JSON Schema 契约闸门；运行过程写 trace，每条建议可沿 evidence_refs 回溯到记录、指标或节点。所有数字由代码计算，9 步主流水线不调用大模型，也不需要密钥；教学咨询是独立的可选层（见 §7.4），不参与任何产物生成。

## 1. 需求拆解

### 1.1 三项任务与框架落点

| 赛题任务 | 框架落点 | 主要产物 | 章节 |
| --- | --- | --- | --- |
| 任务 1 学习内容与要求梳理 | content_map 构建 + 覆盖统计 | out/content_map.json、out/tables/coverage.csv | §5.1 |
| 任务 2 学生学习情况分析 | 清洗对账 → 质检 → 个体/群体诊断 | 清洗版与变更记录、out/qc_report.json、out/diagnosis_all.json | §5.2 |
| 任务 3 个性化学习建议 | 信号识别 → 选材 → 组单 → 守卫 → 三案例 | out/recommendations_all.json、out/cases.json、out/report.md | §5.3、§5.4 |

### 1.2 评分项承接矩阵（16 项）

| 评分维度 | 评分项 | 承接模块 | 核对方式 |
| --- | --- | --- | --- |
| 学习内容与要求梳理质量 | 内容理解 | content_map 的三主题、九指标、课标/教材/题目出处 | 打开 content_map.json 逐指标核对 |
| 同上 | 范围覆盖 | 65 份材料全部入 materials_index；节点覆盖表 | coverage.csv 与材料清单对账 |
| 同上 | 材料依据 | standard{cr_id,pdf_pages,body_pages}、textbook_pages、material_ids | 每个指标都有非空出处 |
| 同上 | 组织与使用 | 契约化 JSON，下游 recommend 直接消费 | validate 契约校验 + 下游读取 |
| 学生学习情况分析质量 | 数据处理 | clean.py 五类规则 + 变更记录 + 哈希 | clean --check 复现 10 处变更 |
| 同上 | 表现描述 | 个体 observed/score_rate/by_indicator；群体 by_class/by_indicator/by_topic | diagnosis_all.json |
| 同上 | 问题识别与依据 | 弱指标信号 + evidence_refs + 置信度 | 每条信号可回查记录 |
| 同上 | 分析呈现 | report.md 表格 + 三案例 | 报告数字与 JSON 一致 |
| 个性化学习建议质量 | 建议适切 | 置信度闸门 + 已满分排除 + 未做题优先 | 逐生人工抽查、guard 校验 |
| 同上 | 理由与依据 | reason 引用观测数/满分率/记录编号；evidence_refs 强制非空 | guard 逐条解析 |
| 同上 | 回应不同需求 | 需要巩固/数据不足/稳定表现三类案例；低覆盖降级为观察 | cases.json 三类互异 |
| 同上 | 实施与调整 | seq 先后顺序、next_check、adjust_condition | 建议卡逐条可执行 |
| 文档与演示质量 | 文档完整 | 本文 + README + 字段说明 + 样例 | 目录核对 |
| 同上 | 表达清晰 | 固定章节、表格、术语表 | 评审可读性 |
| 同上 | 演示完整、时长合规 | v1 提供 CLI 演示路径；视频/PPT 由交付阶段补齐 | 后续版本 |
| 同上 | 复核材料充分 | trace、evidence 索引、86 项单测、输入输出样例、本地工作台、公开演示 | 按 §6.2 抽查 |

## 2. 现有基线

### 2.1 输入与已有资产

- 数据：data/raw 六张表（作答记录、题目与材料、课程要求、测验节点、模拟学生、字段说明）+ SHA256SUMS 只读校验；data/derived 有清洗版、异常清单、变更记录、质量分析报告。
- 规模：40 名学生（DC01 21、DC02 19）；806 行记录、799 个作答事件、7 条修订版本折叠；原始异常 7 条，清洗后 0 条；10 处字段修正；65 份材料；3 主题 9 指标 2 节点。
- 已有能力：common.py 的口径与编码工具；qc.py 的 QC01–QC19、覆盖表与诊断构建；content_map.py 的内容图谱；validate.py 的 Draft7 契约校验。
- 已有契约：content_map / diagnosis / recommendation 三份 0.1.0 schema，additionalProperties=false。

### 2.2 本版新增

| 模块 | 作用 |
| --- | --- |
| src/clean.py | 五类规则可追溯清洗；--check 与既有清洗版逐单元格对账，--apply 先备份再原子替换 |
| src/recommend.py | 40 名学生建议批次生成；置信度闸门；单生样例导出 |
| src/guards.py | 5 类守卫：学生覆盖、证据可解析、置信度不变量、答案与合规、个人信息 |
| src/cases.py | 三类案例选择、记录级证据链、DC01/DC02 班级与指标对比 |
| src/report.py | 由结构化产物汇总 Markdown 报告，不手填数字 |
| src/agent/* | ToolSpec / ToolRegistry / Plan / AgentRuntime / CLI / trace |
| schemas/recommendation_batch.schema.json | 建议批次契约，逐生复用单生 recommendation schema |
| tests/test_pipeline.py | 11 项回归：清洗、内容、诊断、建议、守卫、契约、计划、硬编码、案例、确定性 |
| src/graph_model.py + tests/test_graph_model.py | 内容图谱的知识网络投影（72 节点/83 边）与 4 项确定性测试，不新增流水线步骤 |
| src/record_input.py | 与作答记录同构的 14 列录入、硬错误/警告分级、独立副本与备份 |
| src/consult.py | 可选教学咨询：DeepSeek/OpenAI SDK、配置读取、聚合上下文、错误映射；不写回产物 |
| tests/test_record_input.py / tests/test_consult.py | 录入 17 项、咨询 17 项回归 |

### 2.3 复用边界

- 不重写 qc/content_map 的口径，只在其上封装工具。
- 不修改 data/raw；清洗只写 data/derived，且先备份。
- 不改三份既有契约的 0.1.0 字段；新增批次契约与 trace 产物。
- 主流水线不引入第三方运行时依赖（沿用 jsonschema；pandas 可用但核心路径不依赖）；可选教学咨询使用 `openai` SDK，未安装/未配置时咨询页禁用，其余功能不受影响。

## 3. 总体架构

### 3.1 五层结构

~~~mermaid
flowchart LR
  A[输入治理层<br/>raw 只读 + SHA256 + clean] --> B[领域能力层<br/>content / qc / diagnose / recommend]
  B --> C[工具注册层<br/>ToolSpec + consumes/produces]
  C --> D[编排运行时<br/>Plan 顺序执行 + trace]
  D --> E[证据与合规层<br/>guard / cases / report / validate]
  D --> F[(out 产物)]
  E --> F
~~~

- **输入治理层**：固定 raw 路径、校验清单哈希、清洗规则与变更血缘。
- **领域能力层**：内容图谱、清洗对账、质检、诊断、建议、案例、报告，输入数据、输出 dict 或文件。
- **工具注册层**：每个能力声明名称、用途、前置产物、产物与证据；调用前检查前置，调用后检查产物并记哈希。
- **编排运行时**：按计划顺序执行，逐步打印、失败即停，写 trace 与步骤表。
- **证据与合规层**：守卫建议证据与不变量，生成案例与报告，最后按契约校验。

### 3.2 数据流

~~~mermaid
flowchart LR
  RAW[data/raw 原始 CSV] --> CLN[clean.py 对账]
  CLN --> DER[data/derived 清洗版 + 变更记录]
  RAW --> CM[content_map.py]
  DER --> QC[qc.py 质检与诊断]
  QC --> DIAG[diagnosis_all.json]
  CM --> REC[recommend.py]
  DIAG --> REC
  DER --> REC
  REC --> GUARD[guards.py]
  GUARD --> CASES[cases.py]
  GUARD --> REP[report.py]
  CASES --> REP
  REP --> VAL[validate.py]
  REC --> VAL
  CM --> VAL
  VAL --> OUT[(out/)]
~~~

编号贯穿全链：学生 D01–D40、班级 DC01/DC02、主题 T01–T03、指标 T0xIx、节点 N01/N02、材料 Q001–Q054/L01–L03/B01–B08、记录 DR0001 起、作答事件“学生-节点-材料”。

### 3.3 设计原则

- **确定性优先**：数字、排序、选材全部由代码计算；同输入两次运行关键产物字节一致。
- **证据链一等公民**：每条建议必须有可解析证据；每次运行有 trace 与产物哈希。
- **清洗规则有边界**：只自动修 ADR 已定义的 5 类；其余进人工队列，严格模式阻断。
- **契约只增不改**：既有三份 schema 不动；新增批次契约，不擅自扩字段。
- **交互只做 CLI**：不做 Web/图表；“选学生→诊断→建议→依据”用命令与 JSON 路径完成。

## 4. 核心对象与接口

### 4.1 ToolSpec / ToolResult / Context

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: object
    consumes: tuple = ()   # 前置产物（相对仓库根）
    produces: tuple = ()   # 执行后必须存在的产物
    evidence: tuple = ()   # 该工具承担的核对声明

@dataclass
class ToolResult:
    tool: str
    ok: bool
    summary: str
    metrics: dict
    evidence: list
    outputs: dict          # 产物路径 -> sha256
    stdout: str
    error: str
    elapsed_ms: int

class AgentContext:
    root: str
    trace_path: str
    dry_run: bool
    artifacts: dict        # 本次运行累计产物 -> sha256
```

`ToolRegistry.call(name, ctx)` 的行为：

1. 检查 `consumes` 全部存在，缺失时抛 `ToolError` 并提示先跑哪个任务；
2. 捕获 handler 的 stdout/stderr，异常转为失败结果，不让半成品继续；
3. 检查 `produces` 全部生成，记录每个产物的 sha256；
4. 返回统一 `ToolResult`，运行时据此打印与写 trace。

### 4.2 计划

`PlanStep(tool, why)` 只做顺序计划，不引入 DAG 依赖：

| 任务 | 计划 |
| --- | --- |
| all | clean → content → qc → diagnose → recommend → guard → cases → report → validate |
| diagnose | clean → content → qc → diagnose |
| recommend | recommend → guard → cases → report → validate |
| report | cases → report → validate |
| validate | validate |

每一步的 `why` 写在 `src/agent/plans.py`，既供 CLI 展示，也进 trace，答辩时可逐条解释。

### 4.3 trace 结构

运行结束写 `out/agent_trace.json`；失败时也写，`status=failed`，并保留已完成步骤。

```json
{
  "schema_version": "0.1.0",
  "task": "all",
  "started_at": "2026-11-16T16:45:00+08:00",
  "finished_at": "2026-11-16T16:45:02+08:00",
  "status": "ok",
  "error": "",
  "plan": [{"seq": 1, "tool": "clean", "why": "..."}],
  "steps": [{"seq": 1, "tool": "clean", "ok": true, "summary": "...", "metrics": {},
             "evidence": [], "outputs": {"out/clean_report.json": "..."},
             "stdout": "", "error": "", "elapsed_ms": 50, "why": "..."}],
  "artifacts": {"out/content_map.json": "..."},
  "guardrails": {"raw_inputs_read_only": true, "diagnosis_on_cleaned_dataset": true,
                 "contract_validation_required": true,
                 "recommendation_evidence_required": true,
                 "reference_answer_not_used_for_recommendation": true}
}
```

步骤表 `out/tables/agent_steps.csv` 同步记录序号、工具、结果、耗时、摘要、证据与产物。
v1 的 trace 是自描述 JSON，尚未单独建 schema；下一步可补 `schemas/agent_trace.schema.json`。

### 4.4 CLI

```text
python src/agent/run.py --task all
python src/agent/run.py --task diagnose --dry-run
python src/agent/run.py --task recommend
python src/agent/run.py --list-tools
python src/agent/run.py --trace out/agent_trace.json
```

- `--task` 取 all / diagnose / recommend / report / validate；
- `--dry-run` 只打印计划与理由，不执行；
- `--list-tools` 列出工具、前置与产物；
- 退出码 0/1；任一步失败即停，不自动跳过。

## 5. 三条任务链

### 5.1 任务 1：内容与要求梳理

- 输入：课程要求.csv、题目与材料.csv、测验节点.csv。
- 输出：content_map.json（3 主题、9 指标、65 材料、source.files 哈希）与 content_matrix_draft.csv。
- 每个指标带：课标整理编号、课标 PDF 页/正文页、教材正文页、观察指标、material_ids、证据要求。
- 教材未标主题时 `materials_index[].topic_id = null` 并进 `open_questions`，不猜（ADR D10）。
- 覆盖度分母是节点可用题目数；11 份材料（8 教材 + 3 学习卡）不在任何节点题目里，只作学习材料，不进分母。

### 5.2 任务 2：清洗、质检与诊断

清洗规则按顺序执行，逐条写变更记录（记录编号、字段、前值、后值、规则、依据）：

| 规则 | 条件 | 动作 | 边界 |
| --- | --- | --- | --- |
| R1 主题跟随材料 | 记录主题 ≠ 材料主题 | 改为材料主题 | 材料必须存在 |
| R2 节点/事件一致 | 材料不在当前节点可用题目 | 取“可用题目含该材料且节点日期=提交日期”的唯一节点；否则唯一候选 | 候选不唯一进人工队列 |
| R3 答案一致未满分 | 填空/选择题归一化后与参考答案一致且得分<满分 | 得分=满分，单评分点同步置满分 | 多评分点进人工队列 |
| R4 区间端点反向 | 满分但解集端点与参考相反 | 扣 1 分，末位评分点置 0 使合计吻合 | 无评分点进人工队列 |
| R5 总分与评分点不符 | 有评分点且合计≠得分 | 得分=合计 | 合计越界进人工队列 |

- `clean.py --check` 默认只对账：10 处修正、0 未解决、清洗版逐单元格一致、变更记录集合一致、清洗版质检 0 异常。
- `--apply` 先备份到 `data/derived/_history/<时间戳>/`，临时文件写清洗版，质检 0 异常才原子替换。
- 质检沿用 QC01–QC19；诊断只读清洗版，避免“拿原始异常算出错分数”。
- 个体：observed（records/scored/pending/unanswered/coverage）、score_rate（overall/by_node）、by_indicator（observed/correct/rate/confidence）、flags、evidence_refs（最多 5 条记录）、notes。
- 群体：by_class（学生数/记录数/覆盖均值/得分率均值）、by_indicator、by_topic。
- 置信度：观测数 ≥10 高、5–9 中、<5 低；缺失、待评、未作答均按信息不足处理，不记 0 分。
- 诊断 `quality` 记录原始 7 条异常（`pass_with_warnings`）、修正 7 条、清洗后 0 条。

### 5.3 任务 3：个性化建议

信号按优先级：

| 优先级 | 信号 | 触发 | 生成动作 |
| --- | --- | --- | --- |
| S1 | 无已评记录 | `observed.scored = 0` | 学习卡 review + 两条 observe |
| S2 | 需巩固指标 | `observed >= 5 且 rate < 0.6` | review + practice + variant，必要时补第二指标 |
| S3 | 低置信弱项 | `observed < 5 且 rate < 0.6` | review + observe，不排练习/变式 |
| S4 | 未观测指标 | 指标从未出现记录 | review + observe |
| S5 | 稳定指标 | 无弱项，且 `observed >= 5、rate >= 0.8` | variant 做迁移；无覆盖则先补观察 |
| S6 | 待评/未作答 | 状态为待评分/未作答 | observe，说明“暂不作为掌握依据” |

选材规则：

1. 材料必须出现在 content_map 该指标的 `material_ids` 中；
2. 学习卡 → review；题目 → practice 或 variant；
3. 同一学生同一材料不重复；每条建议最多 3 个 evidence_refs；
4. 已做过的题排在未做题之后；练习优先选择/填空，变式优先解答题；
5. 每生 1–6 条，seq 连续；顺序固定 review → practice → variant → observe；
6. 不读取参考答案；建议文案不出现答案数值，只描述可观察行为。

文案：`reason` 由指标观测数、满分率、置信度、记录编号现算；`expected_observation` 描述可观察行为；`adjust_condition` 按“仍错→降级/补前置，达到 70%→进阶”；`next_check` 以“完成前 1–2 项后（约 15–20 分钟）”表述。

兜底：无任何信号时生成 1 条 observe，保证 `items >= 1`。批次输出 `out/recommendations_all.json`，外层带诊断/内容图谱 sha256；单生样例由 `--example` 覆盖 `examples/recommendation_D01.json`。

### 5.4 三案例与报告

- **需要巩固型**：已评记录 ≥10 中整体得分率最低者（本数据为 D03）。
- **数据不足型**：记录数 <10 或带 `insufficient_records` 标志中记录最少者（本数据为 D17，4 条、N02 覆盖 0）。
- **稳定表现型**：已评 ≥10、平均覆盖 ≥0.2 中，优先选尚未出现的班级，再取得分率最高者（本数据为 D36）。
- 三类强制不同学生；`out/cases.json` 含每个案例的诊断摘录、建议序列、记录级证据链（得分/满分/状态/节点）与 DC01/DC02 对比。
- `out/report.md` 全部数字读自 JSON/CSV：数据质检、内容图谱、班级与指标、三案例、适用范围、复现命令。
- 当前实测：DC01 57.6% / 覆盖 29.9%，DC02 54.5% / 覆盖 28.7%，差 3.1 个百分点；共性弱项 T01I3 20.0%、T03I3 39.3%、T02I3 43.9%。

## 6. 证据链与核对

### 6.1 引用类型

| 前缀 | 含义 | 解析目标 |
| --- | --- | --- |
| DR#### | 记录编号 | 清洗版作答记录，且必须属于该学生 |
| T0xIx | 指标编号 | content_map.topics[].indicators[] |
| N0x | 节点编号 | 测验节点.csv |

材料引用走 `item.material_id`，不混入 evidence_refs。

### 6.2 如何核对一条建议

1. 打开 `out/recommendations_all.json`，定位学生与 seq；
2. 取 evidence_refs 中任一 DR，在 `data/derived/作答记录_清洗版.csv` 查到原始作答、得分、评分点；
3. 取 T0xIx，在 `out/content_map.json` 查到观察指标、课标页、教材页、关联材料；
4. 取 N0x，在 `data/raw/测验节点.csv` 查到节点日期与可用题目；
5. 对照 `out/report.md` 的同生摘要与 `out/cases.json` 的入选理由；
6. 检查 `out/guard_report.json` 中该生所在批次是否 5 类检查全过。

## 7. 守卫与合规

### 7.1 五类守卫

| 守卫 | 检查 | 失败后果 |
| --- | --- | --- |
| 学生覆盖 | 建议批次人数 = 诊断人数；每人至少 1 条 | 阻断 |
| 证据可解析 | material_id 存在；DR 存在且属于该学生；T/N 存在 | 阻断 |
| 置信度不变量 | 低置信指标不得 practice/variant；无已评只能 observe | 阻断 |
| 答案与合规 | reason/expected_observation/adjust_condition 不含参考答案原文（长度 ≥5） | 阻断 |
| 个人信息 | 手机号、邮箱、18 位身份证正则 | 阻断 |

### 7.2 置信度动作闸门

- n>=5 的弱指标才允许排练习与变式；
- n<5 的弱指标只允许复习与补观察；
- 无已评记录的学生全部 observe；
- 待评分、未作答只作观察，不写成“未掌握”。

这把“缺少记录不等于未掌握”从文档承诺变成代码不变量。

### 7.3 数据安全与知识产权

- 原始数据只读，SHA256 校验；清洗只写派生目录；赛后按赛题要求删除。
- 不引入真实学生个人信息；模拟数据不外传。
- 开源组件与版本：Python 3.12.14、jsonschema 4.26.0、pandas 3.0.3（仅辅助）、Markdown/JSON 标准库、openai（可选咨询）；无预训练模型权重。
- 9 步主流水线不调用大模型；教学咨询层在用户显式勾选后才发送某学生的聚合摘要，不发送作答原文、参考答案或个人信息；模型输出只作教师复核建议，不写回契约与产物。

### 7.4 可选教学咨询层

- 代码位置：`src/consult.py`（服务）、`ui/js/consult.js`（页面）、`/api/consult/status` 与 `/api/consult`（接口）；配置模板 `config/consult.example.json`。
- 角色：以初中数学教师/教研员视角回答教学问题，要求区分观测与推断、低置信必须标注、不输出可直接照抄的完整答案、不替代教师决策。
- 上下文：默认只发课程内容、指标、课标与材料编号；只有用户勾选学生时才追加该生的聚合诊断（记录数、已评数、覆盖度、指标观测数与得分率、标记、已有建议摘要），不发作答原文、评分点、参考答案或个人信息。
- 配置：`DEEPSEEK_API_KEY` 等环境变量优先，其次 `config/consult.json`，缺省 `https://api.deepseek.com` + `deepseek-chat`；Key 只在服务端读取，不进入浏览器、不写日志。
- 边界：非流式、单实例、对话不持久化；输出只作为教师复核建议，不写回 `out/`、不改诊断/建议/契约，也不增加第 10 个 agent 步骤。

## 8. 泛化与鲁棒性

### 8.1 换一份同口径数据

1. 替换 data/raw 六张表并更新 SHA256SUMS；
2. 运行 `run.cmd`；
3. 若列名/枚举变化，工具在读取阶段报缺失列或非法值，不静默降级。

### 8.2 降级矩阵

| 情况 | 行为 |
| --- | --- |
| 学生无已评记录 | 诊断 no_scored_record；建议只给 observe |
| 节点只有 1 个 | 诊断 single_node_only；不比较跨节点趋势 |
| 指标观测 <5 | 置信度低；只作描述，不作强结论 |
| 材料缺参考答案 | 跳过答案一致性规则，记录 open question |
| 节点候选不唯一 | 清洗进人工队列；严格模式阻断 |
| 建议批次某生为空 | 兜底 observe；守卫仍会检查 1–6 条 |

### 8.3 失败处理

- 单步异常带工具名与错误信息抛出；默认停止，避免半成品被误用。
- 工具调用前检查前置产物，调用后检查声明产物。
- 清洗 `--apply` 先备份、临时文件、质检通过再原子替换。
- 契约校验失败打印 JSON Pointer，退出码 1。

## 9. 运行与产物

### 9.1 命令

```text
run.cmd                      # 智能体 9 步 + 86 项测试 + 自检
run_ui.cmd                   # 本地教研工作台（七页，只读快照，可后台重跑）
run.cmd agent                # 只跑智能体 9 步
run.cmd qc                   # 质检 + 基线
run.cmd content              # 内容图谱
run.cmd diagnose             # 清洗 → 内容 → 质检 → 诊断
run.cmd recommend            # 建议 → 守卫 → 案例 → 报告 → 契约
run.cmd report               # 案例 → 报告 → 契约
run.cmd validate             # 五份契约校验
run.cmd clean                # 清空 out/
python src/clean.py --check  # 清洗对账（默认）
python src/clean.py --apply  # 写清洗版（先备份）
python src/recommend.py --example D05
python src/consult.py --status  # 咨询配置脱敏自检
python src/demo_site.py --out demo  # 生成只读公开演示站点
```

### 9.2 产物清单

| 路径 | 内容 |
| --- | --- |
| out/content_map.json | 内容图谱（3 主题 / 9 指标 / 65 材料） |
| out/diagnosis_all.json | 全体诊断（40 生，个体 + 群体） |
| out/recommendations_all.json | 全体建议（40 生，1–6 条/人） |
| out/guard_report.json | 5 类守卫结果 |
| out/cases.json | 三案例 + 班级对比 |
| out/report.md | Markdown 分析报告 |
| out/agent_trace.json | 运行追踪（计划、步骤、产物哈希、guardrails） |
| out/clean_report.json | 清洗对账结果与人工队列 |
| out/qc_report.json | 质检结果与规则命中 |
| out/tables/*.csv | 异常、覆盖、指标、清洗变更、建议摘要、案例证据、班级、报告指标、步骤表 |
| examples/diagnosis_D01.json | 单生诊断样例 |
| examples/recommendation_D01.json | 单生建议样例（程序生成） |

一次全量运行登记 18 个产物；`out/tables/agent_steps.csv` 另记步骤耗时。
本地工作台不新增机器产物，只读上述文件与清洗版 CSV；页面、API 与安全边界见 `docs/ui_design.md`。

### 9.3 环境与耗时

- 解释器优先级：$env:PYTHON → 捆绑 Python → PATH；捆绑版本 3.12.14。
- 单测：`python -m unittest discover -s tests -v`。
- 全链在本机约 1–2 秒（806 行数据）；可选咨询需 `openai` 与 DeepSeek Key，未安装/未配置时仅该页禁用。

## 10. 质量与验收

### 10.1 五道闸门

1. **数据闸门**：raw SHA256SUMS 全匹配；清洗后 0 异常、806 行不变。
2. **契约闸门**：content_map、diagnosis、recommendation 单生、推荐批次、单生样例共 5 个文件通过 Draft7；失败即阻断。
3. **守卫闸门**：学生覆盖、证据、置信度不变量、答案合规、个人信息 5 类检查。
4. **确定性闸门**：qc_report / baseline / content_map 双跑字节一致；建议生成两次字节一致。
5. **测试闸门**：86 项 unittest 全绿（11 流水线 + 17 录入 + 29 UI/HTTP + 3 桌面入口 + 4 知识图谱投影 + 17 咨询 + 5 公开演示站点）；src 递归零硬编码编号。

### 10.2 验收清单

- `run.cmd` 从空 out 跑通，退出码 0，9 步全过；
- 40 名学生全部有建议且逐生通过 schema；
- cases.json 三类互异，DC01/DC02 对比有指标层说明；
- 任取一条建议可按 §6.2 回溯；
- `clean --check` 复现 10 处变更、0 异常、806 行；
- guard_report.json 5 类检查全 pass；
- trace 有计划、步骤、产物哈希与 guardrails；
- 文档、README、字段说明、样例齐备；
- `run_ui.cmd` 七页可开（含内容图谱知识网络、数据录入、教学咨询），深链/搜索/打印可用，503 缺产物提示正确，三档视口无整页溢出（图谱画布自身横向滚动）；
- `demo/` 静态站点五页可开，无录入/咨询/重跑，390/1366 无整页横向滚动。

### 10.3 已知限制

- 清洗只覆盖 5 类可机判修复，其余异常需人工裁定；
- 建议是规则化方案，不是教学效果证明；需教师按 adjust_condition 调整；
- 选材优先同指标未做题，但 v1 未按“最近节点”过滤跨节点题，教师需按进度取舍；
- 主流水线不调用大模型，文案优先准确而非文采；教学咨询为可选外部服务，未配置时禁用，不替代教师决策；
- 可视化以配套本地工作台实现（见 `docs/ui_design.md`），视频、PPT 在交付阶段补齐。
- 工作台一次加载 806 条记录，未做分页；重跑为单实例，不做并发队列。

## 11. 版本路线

| 版本 | 内容 |
| --- | --- |
| v1（本文） | 确定性框架、5 份契约文件、三案例、守卫、trace、本地工作台、知识网络、数据录入、教学咨询、公开演示、86 项单测 |
| v1.1 | 按最近节点过滤选材；补 agent_trace schema；教师调整记录 |
| v2 | 可选 LLM 文字改写 + 合规守卫；知识关联图；PDF/视频素材 |

## 附录 A 术语

- **作答事件**：学生-节点-材料的唯一组合，修订版本取最高。
- **覆盖度**：该节点已观测材料数 / 节点可用题目数。
- **置信度**：按指标观测数分低/中/高（5/10 阈值）。
- **满分率**：满分记录数 / 已评记录数，不等同于得分率。
- **守卫**：产物落盘前的强制检查，失败即阻断。
- **trace**：一次运行的计划、步骤、产物哈希与 guardrails 记录。

## 附录 B 文件清单

- 新增：docs/agent_framework_v1.md、docs/ui_design.md、docs/data_input.md、docs/consult_interface.md、docs/desktop_app.md、docs/public_demo.md、src/clean.py、src/recommend.py、src/guards.py、src/cases.py、src/report.py、src/ui_server.py、src/record_input.py、src/consult.py、src/desktop.py、src/graph_model.py、src/demo_site.py、src/agent/*、ui/*、demo/*、run_ui.cmd、build_desktop.ps1、config/consult.example.json、schemas/recommendation_batch.schema.json、tests/*。
- 修改：src/validate.py、src/common.py（frozen ROOT）、run.ps1、README.md、docs/decisions.md、.gitignore。
- 不动：data/raw/*、out/ 三份业务契约与 9 步流水线产物口径。
