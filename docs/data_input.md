# 数据录入接口（input/1.0）

> 面向“把新一批作答记录交给工作台”的场景：输入字段、列序、编码与 `data/raw/作答记录.csv` **完全一致**。
> 录入数据写入独立副本，不修改原始赛题数据，也不自动进入官方诊断结果。

## 1. 定位与边界

| 项目 | 约定 |
| --- | --- |
| 输入 | 14 列 CSV（UTF-8，可带 BOM）或同字段 JSON |
| 副本 | 源码态 `data/input/作答记录_录入.csv`；打包态 `%LOCALAPPDATA%/SmartCompanion/input/` |
| 元数据 | 同目录 `作答记录_录入.meta.json`，记录保存时间、行数、SHA256、分组统计 |
| 备份 | 每次覆盖/追加前，旧文件复制到 `data/input/_history/<时间戳>/` |
| 官方链路 | **不自动合并**；诊断仍读 `data/derived/作答记录_清洗版.csv` |
| 原始数据 | `data/raw/` 只读，接口没有写入路径 |

这样设计的原因：赛题原始数据是唯一真相，评委复核要求“同一输入哈希 → 同一结果”；录入是“实验/演练”入口，
必须与正式产物隔离。录入页的“当前副本”可以导出，再由教师决定是否走正式清洗流程。

## 2. 快速使用

1. 双击 `run_ui.cmd`，左侧导航进入 **数据录入**（`#/input`）。
2. 点“下载表头模板”，或直接把整表 CSV 粘贴进编辑器，点“只校验”。
3. 看到“通过”后点“校验并保存”；覆盖前会二次确认。
4. 需要从外部程序写入时，用下文的 HTTP 接口。

## 3. 14 列契约

列名与顺序固定，缺失、重排、改名都会被拒绝：

| # | 字段 | 必填 | 说明 |
| --- | --- | --- | --- |
| 1 | 记录编号 | 是 | `DR0001`–`DR9999`，全表唯一 |
| 2 | 学生编号 | 是 | `D01`–`D40`，必须在 `模拟学生.csv` 中 |
| 3 | 材料编号 | 是 | `Q001`–`Q054` / `B01`–`B08` / `L01`–`L03` |
| 4 | 主题编号 | 是 | `T01`–`T03` |
| 5 | 节点编号 | 是 | `N01`/`N02`，必须在 `测验节点.csv` 中 |
| 6 | 作答事件编号 | 是 | 必须等于 `学生-节点-材料`，如 `D01-N01-Q015` |
| 7 | 修订版本 | 是 | 正整数；同一事件 + 版本不可重复 |
| 8 | 模拟提交时间 | 是 | ISO 8601，带时区，如 `2026-01-20T08:56:22+08:00` |
| 9 | 评分状态 | 是 | `已评分` / `待评分` / `未作答` |
| 10 | 得分 | 条件 | `已评分` 必填；`待评分`/`未作答` 必须为空 |
| 11 | 满分 | 是 | 大于 0 的数字 |
| 12 | 学生最终作答 | 否 | 可含换行；CSV 中按标准引号转义 |
| 13 | 解答过程 | 否 | 可含多行；CSV 中按标准引号转义 |
| 14 | 评分点得分 | 条件 | 形如 `Q015P1=1；Q015P2=0；Q015P3=0`，中文分号 |

评分点规则：前缀必须等于 `材料编号`；序号从 1 开始且不可重复；逐项分值不得为负。

## 4. 输入格式

- **CSV**：`Content-Type: text/csv`（或 `text/plain`）；表头必须与上表完全一致；
  允许 UTF-8 BOM；文件写出固定为 **UTF-8 BOM + CRLF**；多行引号字段按标准 CSV 处理。
- **JSON**：`Content-Type: application/json`，两种形态：

  - 直接数组：`[{"记录编号":"DR0001", ...}, ...]`；
  - 包装对象：`{"rows":[...], "mode":"replace"}`，`mode` 可为 `replace`/`append`。

  JSON 每行必须 14 个字段齐全，不允许未知字段。
- 上限：请求体 8 MB、最多 10000 行；空表头/只有表头/空数组都会返回 422。

## 5. HTTP 接口

所有接口仅监听 `127.0.0.1`，并要求：

- `Host` 为 `127.0.0.1:<端口>` 或 `localhost:<端口>`；
- 若带 `Origin`，必须同源；
- 必须带请求头 `X-DSH-UI: 1`（防止浏览器跨站表单误触发）。

| 方法 | 路径 | 作用 | 成功 |
| --- | --- | --- | --- |
| GET | `/api/records` | 读取当前副本（存在性、行、meta、统计） | 200 |
| GET | `/api/records/template` | 下载 14 列表头模板 | 200，CSV BOM |
| GET | `/api/records/export` | 导出当前副本 | 200，CSV |
| POST | `/api/records/validate` | 只校验，不落盘 | 200 |
| POST | `/api/records?mode=replace` | 校验并整体替换 | 201 |
| POST | `/api/records?mode=append` | 校验后追加到当前副本 | 201 |

校验不通过返回 **422**，响应体为 `{"error":{"code":"validation_failed","details":{"errors":[...],"warnings":[...],"stats":{...}}}}`。
读取/导出没有副本时返回 **404**；请求体超限返回 **413**；缺 `Content-Length` 返回 **411**。

### PowerShell 示例

```powershell
$base = "http://127.0.0.1:8765"
$h = @{ "X-DSH-UI" = "1" }

# 下载模板
Invoke-WebRequest -Uri "$base/api/records/template" -Headers $h -OutFile "template.csv"

# 只校验（CSV 文件）
$csv = Get-Content -Raw -Encoding UTF8 "new_records.csv"
Invoke-RestMethod -Method Post -Uri "$base/api/records/validate" -Headers $h `
  -ContentType "text/csv; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($csv))

# 校验并替换当前副本（确认后再执行）
Invoke-RestMethod -Method Post -Uri "$base/api/records?mode=replace" -Headers $h `
  -ContentType "text/csv; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($csv))
```

### curl 示例

```bat
curl.exe -H "X-DSH-UI: 1" -o template.csv http://127.0.0.1:8765/api/records/template
curl.exe -H "X-DSH-UI: 1" -H "Content-Type: text/csv; charset=utf-8" ^
  --data-binary "@new_records.csv" http://127.0.0.1:8765/api/records/validate
```

## 6. 校验分级：硬错误 vs 警告

**硬错误阻断保存**（返回 422，副本保持不变）：

| 错误码 | 含义 |
| --- | --- |
| `required` | 必填列为空 |
| `id_format` | 编号格式不合法 |
| `unknown_student` / `unknown_material` / `unknown_node` | 外键不在花名册/材料表/节点表 |
| `event_mismatch` | 作答事件编号不等于 `学生-节点-材料` |
| `revision_invalid` | 修订版本不是正整数 |
| `time_invalid` | 提交时间不是带时区的 ISO 8601 |
| `status_invalid` | 评分状态不在三值内 |
| `score_required` / `score_not_allowed` | 已评分缺分 / 待评分或未作答却有分 |
| `points_not_allowed` | 待评分或未作答却填了评分点 |
| `points_syntax` / `points_material` / `points_duplicate` | 评分点语法、归属或重复问题 |
| `duplicate_record` / `duplicate_revision` | 记录编号重复 / 事件+版本重复 |
| `max_score_invalid` | 满分不是大于 0 的数字 |

**警告允许保存**，交给既有质检/清洗链路继续处理：

| 警告码 | 含义 |
| --- | --- |
| `topic_mismatch` | 主题与材料主题不一致 |
| `material_not_in_node` | 材料不在该节点可用题目中 |
| `non_question_material` | 材料类型不是题目 |
| `max_score_mismatch` | 满分与材料满分不一致 |
| `score_over_max` | 得分大于满分 |
| `points_sum_mismatch` / `points_over_max` | 评分点合计与得分/满分不一致 |
| `submit_before_node` | 提交日期早于节点日期 |
| `time_timezone` | 提交时间缺时区 |

为什么允许“带警告保存”：原始 806 行本身就有 7 条异常（QC04/QC07/QC09/QC10/QC18/QC19），
如果警告也阻断，就无法把真实数据导入工作台演示“先发现、再处理”。警告会逐条显示，保存后仍可在数据质量页追踪。

## 7. 保存、备份与回滚

1. 保存前先对合并后的全部行做一次完整校验；有硬错误直接拒绝，不写文件。
2. 旧副本复制到 `data/input/_history/<YYYYMMDDTHHMMSSffffff>/作答记录_录入.csv`。
3. 新文件先写同目录临时文件，再 `os.replace` 原子替换；失败不会留下半个文件。
4. 按 `记录编号` 排序后写出，固定 UTF-8 BOM + CRLF。
5. 同步写 meta：`schema_version`、`saved_at`、`mode`、`rows`、`students`、`groups`、`unique_events`、
   `revisions_folded`、`status_counts`、`sha256`、`bytes`。

回滚：把历史目录里的 CSV 复制回 `data/input/作答记录_录入.csv` 即可；不需要改数据库或缓存。

## 8. 与官方流水线的关系

- 录入副本 **不会**自动替换 `data/raw/作答记录.csv`，也不会触发 `run.cmd all`；
- 教师在数据录入页确认后，可导出 CSV，按正式流程走清洗/质检；正式诊断仍只读清洗版；
- 这样“演练数据”和“交付数据”不会混在一起，评委复核时能明确说明数据使用范围。

## 9. 安全与隐私

- 服务只绑定回环地址，不接受局域网访问；写操作必须带 `X-DSH-UI: 1` 并通过 Host/Origin 检查。
- 录入页编辑器会显示学生作答原文，属于本地工作区；工作台快照接口仍只暴露 10 个白名单字段，不含答案/参考答案。
- 不要将 `data/input/` 或导出的 CSV 提交到公开仓库；`.gitignore` 已排除该目录。
- 赛题数据仅限本次比赛使用，赛后按赛题组要求删除。

## 10. 测试与验收

```bat
python -m unittest tests.test_record_input -v   :: 17 项：模板/解析/硬错误/警告/保存/备份/回滚
python -m unittest tests.test_ui -v             :: 22 项：含录入 HTTP 接口、知识图谱投影与静态资源
```

人工验收：

1. 原始 `data/raw/作答记录.csv` 整表粘贴 → 只校验：`806 行 / 40 生 / 799 事件 / 0 错误 / 7 警告`。
2. 保存后导出，字节与原始文件一致（SHA256 见变更记录）。
3. 删除必填列、改错事件编号各试一次：返回 422，旧副本不变。
4. 追加一行后，`_history/` 出现备份，meta 的 `rows` 与 `sha256` 同步更新。