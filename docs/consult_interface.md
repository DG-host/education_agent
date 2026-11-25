# 教学咨询接口（DeepSeek）

面向教师的自然语言教学咨询：模型以“初中数学教师/教研员”的角色回答，可选择性带入某学生的聚合诊断。咨询是工作台的**可选外部能力**，不进入 9 步确定性流水线，也不改变 `out/` 三份契约。

## 1. 代码位置

| 位置 | 作用 |
| --- | --- |
| `src/consult.py` | **核心**：配置读取、上下文白名单、系统提示词、OpenAI 客户端、错误映射、`--status` 自检 |
| `src/ui_server.py` | 本机 HTTP 接口 `/api/consult/status`、`/api/consult`；`UiServer(..., consult_service=...)` |
| `ui/js/consult.js` | 工作台“教学咨询”页面（`#/consult`） |
| `ui/index.html`、`ui/js/app.js` | 导航、路由、页面挂载/清理 |
| `config/consult.example.json` | 配置模板（入库，不含真实 Key） |
| `config/consult.json` | 你的实际配置（已加入 `.gitignore`，不入库） |
| `tests/test_consult.py` | 配置、上下文隐私、请求校验、错误映射的离线测试 |
| `tests/test_ui.py` | HTTP 接口与前端资源测试 |

## 2. 快速开始

### 2.1 配置 Key

方式一：环境变量（推荐临时使用）

```powershell
$env:DEEPSEEK_API_KEY = "sk-你的-key"
$env:DEEPSEEK_MODEL = "deepseek-chat"   # 可选
run_ui.cmd
```

方式二：本地配置文件（推荐长期使用）

1. 复制 `config/consult.example.json` 为 `config/consult.json`；
2. 填入 `api_key`；
3. 重新启动 `run_ui.cmd`，打开“教学咨询”页。

配置优先级：环境变量 > 配置文件 > 默认值。**Key 只在服务端读取，不进入浏览器、不写入仓库、不打印日志。**

打包版 `dist/智慧学伴.exe` 的配置文件固定在：

```text
%LOCALAPPDATA%\SmartCompanion\consult.json
```

也可以对打包版设置用户级环境变量 `DEEPSEEK_API_KEY`。

### 2.2 自检

```powershell
python src\consult.py --status
```

输出包含 `configured`、`library_available`、`model`、`config_path`、`config_source`，不包含 Key。

## 3. 配置项

`config/consult.example.json`：

```json
{
  "api_key": "",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-chat",
  "timeout_seconds": 60,
  "max_output_tokens": 1200
}
```

| 键 | 环境变量 | 默认 | 说明 |
| --- | --- | --- | --- |
| `api_key` | `DEEPSEEK_API_KEY` | 空 | 必填；空值/占位符视为未配置 |
| `base_url` | `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek OpenAI 兼容地址 |
| `model` | `DEEPSEEK_MODEL` | `deepseek-chat` | 也可配置其他兼容模型 |
| `timeout_seconds` | `DEEPSEEK_TIMEOUT` | 60 | 5–120 秒 |
| `max_output_tokens` | — | 1200 | 200–4000 |

依赖：`openai` Python 库（要求 1.x 及以上）。源码运行用的 bundled Python 已包含；其他环境执行：

```powershell
python -m pip install openai
```

未安装时，流水线仍可正常运行，只有咨询页报 `consult_unavailable`。

## 4. HTTP 接口

所有接口只监听回环地址，要求：

- `Host` 为 `127.0.0.1:<port>` 或 `localhost:<port>`；
- `X-DSH-UI: 1`；
- 如带 `Origin`，必须同源。

### 4.1 `GET /api/consult/status`

返回脱敏配置状态：

```json
{
  "schema_version": "consult.status/1",
  "configured": true,
  "library_available": true,
  "model": "deepseek-chat",
  "base_url": "https://api.deepseek.com",
  "config_path": "config/consult.json",
  "config_source": "file",
  "timeout_seconds": 60,
  "max_output_tokens": 1200,
  "max_history": 12,
  "message": "已配置，可发起咨询"
}
```

### 4.2 `POST /api/consult`

请求头：`Content-Type: application/json`、`X-DSH-UI: 1`。请求体上限 64 KB。

```json
{
  "question": "这名学生下一步先补什么？请给出两节课内的安排和观察点。",
  "student_id": "D03",
  "include_diagnosis": true,
  "history": [
    {"role": "user", "content": "上一问"},
    {"role": "assistant", "content": "上一答"}
  ]
}
```

字段：

- `question`：必填，1–4000 字。
- `student_id`：`include_diagnosis=true` 时必填，格式 `D` + 两位数字，且必须在当前诊断中。
- `include_diagnosis`：布尔，默认 `false`；为 `false` 时不发送学生数据。
- `history`：可选，最多 12 条，每条最多 2000 字，总长最多 12000 字；role 只能是 `user`/`assistant`。

成功返回：

```json
{
  "schema_version": "consult.reply/1",
  "reply": "……",
  "model": "deepseek-chat",
  "finish_reason": "stop",
  "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
  "elapsed_ms": 3210,
  "context": {
    "student_id": "D03",
    "include_diagnosis": true,
    "indicators": ["T01I1", "T01I2"],
    "materials": ["L01", "Q001"]
  }
}
```

### 4.3 PowerShell 示例

```powershell
$headers = @{
    "X-DSH-UI" = "1"
    "Content-Type" = "application/json"
}
$body = @{
    question = "这名学生下一步先补什么？"
    student_id = "D03"
    include_diagnosis = $true
    history = @()
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:8765/api/consult" `
    -Headers $headers `
    -Body $body
```

### 4.4 curl 示例

```bash
curl -s http://127.0.0.1:8765/api/consult/status \
  -H "X-DSH-UI: 1"

curl -s http://127.0.0.1:8765/api/consult \
  -H "X-DSH-UI: 1" \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"如何安排下一节课？\",\"include_diagnosis\":false}"
```

## 5. 上下文与隐私

默认只发送课程内容图谱。勾选“带入该生诊断”后，才发送该生的聚合字段：

- 学生编号、班级编号；
- 记录数、已评数、待评数、未作答数、节点覆盖度；
- 整体/节点得分率；
- 9 个指标的观测数、满分记录数、满分率、置信度；
- 诊断 flags、班级均分/覆盖；
- 已有建议的序号、材料、动作、理由、提示级别与 basis 摘要。

**不发送**：

- `data/raw/作答记录.csv` 中的学生最终作答、解答过程、评分点得分；
- 参考答案与参考解析；
- 学生姓名、联系方式、身份证号等个人信息。

系统提示词要求模型：只引用上下文真实编号；观测数 < 5 或无已评记录时标注低置信；不把“缺少记录”解释为“未掌握”；不输出可直接照抄的完整答案；建议供教师复核。

## 6. 错误码

| HTTP | code                                                                                              | 含义 / 处理                                             |
| ---- | ------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| 403  | `forbidden`                                                                                       | 缺少 `X-DSH-UI: 1` 或 Host/Origin 不合法                  |
| 409  | `consult_busy`                                                                                    | 上一请求仍在进行，稍后再试                                       |
| 413  | `payload_too_large`                                                                               | 请求体超过 64 KB                                         |
| 415  | `unsupported_media_type`                                                                          | 只接受 `application/json`                              |
| 422  | `invalid_question` / `invalid_history` / `unknown_field` / `student_required` / `invalid_student` | 请求参数不合法                                             |
| 429  | `consult_rate_limited`                                                                            | 上游限流，稍后再试                                           |
| 502  | `consult_auth_failed`                                                                             | Key 无效或无权限                                          |
| 502  | `consult_unreachable`                                                                             | 无法连接上游，检查网络/base_url                                |
| 502  | `consult_upstream_error` / `consult_empty_reply`                                                  | 上游失败或空回答                                            |
| 503  | `consult_unconfigured`                                                                            | 未配置 Key；按 `details.config_path` 配置                  |
| 503  | `consult_unavailable`                                                                             | 未安装 openai                                          |
| 503  | `consult_config_invalid`                                                                          | 配置文件不是合法 JSON 等                                     |
| 503  | `consult_context_missing`                                                                         | 勾选学生诊断但缺少 `out/diagnosis_all.json`，先跑 `run.cmd all` |
| 504  | `consult_timeout`                                                                                 | 上游超时，稍后重试                                           |

错误响应不会包含 Key 或完整上游响应。

## 7. 运行与验证

源码：

```powershell
run_ui.cmd
# 打开 http://127.0.0.1:8765/#/consult
```

打包：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_desktop.ps1
.\dist\智慧学伴.exe
```

测试：

```powershell
python -m unittest tests.test_consult -v
python -m unittest discover -s tests -q
node --check ui/js/consult.js
```

离线测试使用 fake OpenAI client，不消耗真实额度、不访问网络。真实调用需要你自行配置有效 Key；未配置时页面会显示配置路径与“未就绪”。

## 8. 边界

- 单轮请求/响应，非流式；对话只存在浏览器内存，最多 12 条，刷新即清空。
- 没有多用户登录、额度统计、审计日志或对话落库。
- 咨询结果不写回 `out/`，不影响诊断、建议、案例与报告。
- 不替代教师决策；生成内容需教师复核，遵守赛题“大模型生成内容合规校验”的要求。
- 页面不接收 Key 输入，避免 Key 进入浏览器历史、缓存或截图。
