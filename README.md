# 智慧学伴 · 研发仓库（v0.1.0）

“学情诊断与个性化学习”赛题的研发底座：把三份输入（课程要求、材料清单、模拟作答记录）变成
**三份可机检的 JSON 契约**，并配一条**可复现、可核对**的质量基线。

第一天验收只看一条命令：`run.cmd` 全绿，且 `docs/quality_report.md` 里的数字与它打印的数字一一对应。

## 快速开始

```bat
run.cmd                 :: 若 PowerShell 执行策略已放开，也可直接 .\run.ps1
run.cmd qc              :: 只跑质检 + 基线
run.cmd content         :: 只重建内容地图
run.cmd validate        :: 只校验契约
run.cmd clean           :: 清空 out/ 再跑
```

解释器优先级：`$env:PYTHON` → DSH 自带 python（含 pandas / jsonschema）→ PATH 上的 python。
不需要 pip install，不引入第三方运行时依赖（`pandas` 仅质检脚本可选使用）。

## 目录

| 路径 | 放什么 | 谁改 |
| --- | --- | --- |
| `data/raw/` | 赛题原始数据，只读；`SHA256SUMS.txt` 锁版本 | 谁都不改 |
| `data/derived/` | 清洗版作答记录、异常清单、变更记录、质量分析报告 | B（数据官） |
| `schemas/` | 三份 JSON Schema（draft-07，`schema_version` 固定 0.1.0） | 契约评审后冻结 |
| `src/` | `common.py` 口径常量、`qc.py` 质检与诊断、`content_map.py` 内容地图、`validate.py` 契约校验 | B 改 qc/validate，A 改 content_map |
| `out/` | 所有机器产物（JSON + tables/*.csv），可由 `run.cmd clean` 重建 | 自动生成，不手改 |
| `examples/` | 输入样例与两份“单学生”输出样例（评委复核的入口） | C 维护 |
| `docs/` | 决策记录、质量报告、方案正文 | A/C |

## 三份契约

| 文件 | 回答什么问题 | 关键字段 | 消费者 |
| --- | --- | --- | --- |
| `out/content_map.json` | 这门课要求什么、材料怎么覆盖 | `topics[].indicators[]`、`standard{cr_id,pdf_pages,body_pages}`、`materials_index[]` | 任务 1 清单、任务 3 选材料 |
| `out/diagnosis_all.json` | 每个学生/每个群体现在什么水平、哪里没把握 | `student_level[].observed.coverage`、`by_indicator[].confidence`、`limitations[]` | 任务 2 摘要、任务 3 依据 |
| `examples/recommendation_D01.json` | 给某个学生下一步练什么、为什么、什么时候回头看 | `items[].{material_id,action,hint_level,evidence_refs}`、`next_check` | 任务 3 建议与调整 |

契约里所有编号沿用赛题原始口径（`T01–T03`、`T0xIx`、`Q001–Q054`、`B01–B08`、`L01–L03`、`D01–D40`、`DC01/DC02`、`N01/N02`），
不自造编码——换一份评测数据（10–20 名学生、100–400 条记录）时，只换 `data/raw/` 就能重跑。

## 数据口径（四个坑，写进代码而不是靠记性）

1. **修订版本**：同一 `作答事件编号` 有多版本时取 `修订版本` 最大值，旧版本折叠但不删除（`revisions_folded` 计数可核）。
2. **未观测 ≠ 答错**：`待评分` 与 `未作答` 不记 0 分，只进 `observed.pending/unanswered`；覆盖度用“有记录的材料数 ÷ 节点可用题目数”，并同时给 `union` 口径作对照。
3. **跨节点不可比**：不同测验节点的可用题目集合不同，只比指标层趋势，不比节点均分。
4. **覆盖率先行**：`confidence` 由观测条数决定（<5 低、<10 中、≥10 高），低置信结论必须写进 `notes` 而不是当成事实。

清洗规则（已与出题方口径对齐，见 `docs/decisions.md` D3–D5）：总分与评分点明细矛盾时，**以评分点明细为准下调总分，不改学生答案**；
改节点编号必须联动重写 `作答事件编号 = 学生-节点-材料`；每一处改动进 `作答记录_变更记录.csv`。

## 验收（7 条，全部可复跑）

| # | 断言 | 怎么看 |
| --- | --- | --- |
| 1 | `run.cmd` 从空 `out/` 跑通，退出码 0 | 四个 step 均打印 `ok` |
| 2 | 原始数据检出 **7** 条异常，记录编号集合与既有异常清单完全一致 | `out/tables/anomalies.csv` |
| 3 | 清洗版检出 **0** 条异常 | `out/baseline.json` 的 `after.anomaly_records = 0` |
| 4 | 两次运行字节一致 | 第 4 步 `两次运行字节一致` |
| 5 | 契约校验通过；删一个必填字段必须失败并打印 JSON Pointer | 删掉样例里的 `student_level[0].score_rate` 后跑 `validate.py --pair schemas/diagnosis.schema.json _tmp_bad.json` → 打印 `/student_level/0`、退出码 1 |
| 6 | `data/raw/` 与 `SHA256SUMS.txt` 一致 | 第 4 步 `SHA256SUMS 校验通过（8 个文件）` |
| 7 | `src/` 内零硬编码编号 | 第 4 步 `源码无硬编码编号` |

## 三人分工（第一天）

- **A 内容官**：`src/content_map.py`、`out/content_matrix_draft.csv`、`docs/design_v1.md` 的任务 1 章节；负责 8 份教材切片（B01–B08）的主题归属。
- **B 数据官**：`src/qc.py`、`src/validate.py`、`data/derived/`、`docs/quality_report.md`；负责异常判定与口径答疑。
- **C 工程与表达官**：`run.ps1`/`run.cmd`、`examples/`、`README.md`、演示脚本与视频分镜；负责“依据查看方式”的可演示性。

> 文件所有权见 `docs/decisions.md` D12；跨文件改动先改契约，再改实现。

## 已知边界（写进 open_questions，不藏着）

- 8 份教材切片未标主题，`materials_index[].topic_id` 输出 `null` 并列入待人工复核；
- 11 份材料（教材 + 3 张学习卡）不在任何测验节点的可用题目里，只作“学习建议材料”，不参与覆盖度分母；
- 模拟数据为抽样作答（每生 4–28 条），个体结论一律带 `confidence`，群体结论优先看指标层。
