# 公开演示站点（demo/）

## 1. 这是什么

`demo/` 是工作台的**静态只读副本**：把 `ui/` 的前端文件与一次 `out/` 快照（`snapshot.json`）打包在一起，不依赖 Python、Node 或任何本地服务，放到任意静态托管上即可用浏览器打开。

- 可看：总览、学生画像、典型案例、内容图谱、数据质量五页；深链、搜索、材料/指标/记录抽屉、知识网络、打印。
- 不可用：数据录入（`#/input`）与教学咨询（`#/consult`）。演示页会把这两项隐藏，直接访问时显示“此页需要本地版”。
- 不写任何数据：没有 `/api/run`，没有 `/api/records`，没有 `/api/consult`；刷新只重新读取同一份 `snapshot.json`。

## 2. 生成

在仓库根目录执行：

```powershell
python src\demo_site.py --out demo
```

生成器做四件事：

1. 调 `src/ui_server.py` 的 `build_snapshot()`，得到与本地工作台一致的结构（含 `graph` 投影）；
2. 覆盖 `meta.demo=True`、`run_enabled=False`、`input_enabled=False`，并把 `server_time` 固定为快照的 `generated_at`；
3. 脱敏质检明细：`qc.findings[].rules[].expected/actual` 改为“（公开演示已隐去）”，`note` 置空；
4. 清空并重建 `demo/`，复制 `ui/` 的静态文件，写 `demo-config.js`（`window.DSH_DEMO = true`）与 `snapshot.json`。

生成后目录只应包含：

```text
demo/
  index.html
  demo-config.js
  snapshot.json
  css/styles.css
  js/*.js
```

不应包含 `data/`、`out/`、`config/`、`*.csv`、`*.exe`。可用 `tests/test_demo_site.py` 的断言核对。

## 3. 本地预览

```powershell
python -m http.server 8000 --directory demo
```

打开 <http://127.0.0.1:8000/>。不要直接双击 `demo/index.html`：浏览器会因 `file://` 的同源策略拒绝加载 ES Module 与 `snapshot.json`。

## 4. 发布到公网

主地址是 **GitHub Pages**：

```text
https://dg-host.github.io/education_agent/
```

Pages 由 `.github/workflows/pages.yml` 发布：push 到 `main` 且改动 `demo/` 时，Actions 把 `demo/` 作为制品上传，**不会把仓库根目录（含 data/raw）整体发布**。仓库 Pages 的 `build_type` 必须是 `workflow`。

更新流程：

1. 重新生成 `demo/`；
2. 提交并推送 `demo/` 到 `main`；
3. 等 Actions 的 “Deploy demo to GitHub Pages” 完成，打开上面的 URL。若浏览器仍显示旧页面，强制刷新（Ctrl+F5）。

备用地址（第三方 CDN，可能受网络或缓存影响）：

```text
https://raw.githack.com/DG-host/education_agent/main/demo/index.html
https://cdn.jsdelivr.net/gh/DG-host/education_agent@main/demo/index.html
```

> 发布前确认仓库为 public；Pages 与两个 CDN 都只读取公开仓库。若仓库改为 private，这些地址会失效。

## 5. 只读与隐私边界

- 演示站点**没有后端**，所有按钮只做前端路由、筛选、抽屉与打印；“重新分析”被隐藏，伪造 `POST /api/run` 也不会到达任何服务。
- `snapshot.json` 的记录字段只有 `src/ui_server.py` 的 10 项白名单（记录编号、学生编号、材料编号、主题编号、节点编号、修订版本、提交时间、评分状态、得分、满分），**不含学生最终作答、解答过程、评分点得分、参考答案**。
- 质检明细中的 `expected/actual` 已脱敏；但快照仍包含 `docs.clean.change_records` 的修正依据与 `sources.path` 的内部相对路径。这些是复核材料，不是作答原文。
- **仓库边界**：本仓库的 `data/raw/` 与 `data/derived/` 已被 git 跟踪，公开仓库本身可以访问这些文件。如果这些文件不能公开，必须把 `demo/` 放到**独立公开仓库**，或把数据文件移出公开仓库后再发布。仅靠 `demo/` 的脱敏不能改变仓库其他目录的可见性。
- 演示快照包含 40 名模拟学生（D01–D40），是赛题提供的模拟数据，不含真实学生个人信息；赛后按赛题要求删除。

## 6. 更新与回滚

- 数据更新：先跑 `run.cmd all` 生成最新 `out/`，再执行 `python src\demo_site.py --out demo`，提交 `demo/` 并推送；Pages workflow 会自动重新发布。
- 回滚：`git checkout <旧commit> -- demo` 后重新提交；或直接回退包含 `demo/` 的提交。
- 检查：`python -m unittest tests.test_demo_site -v`，5 项应全绿；再用 390/1366 宽度各看一遍总览与数据质量页，确认无横向滚动。

## 7. 排障

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 页面一直转圈 | `snapshot.json` 路径不对或未上传 | 确认 `demo/snapshot.json` 与 `index.html` 同级；Network 面板看 404 |
| 控制台报 CORS/模块加载失败 | 用 `file://` 直接打开 | 用静态服务器或公网 URL |
| 仍是旧数据 | Pages/CDN 缓存 | 强制刷新；确认 Actions 最新一次部署成功 |
| “此页需要本地版” | 演示版禁用了录入/咨询 | 属预期；本地版用 `run_ui.cmd` 或 EXE |
| 390 宽出现横向滚动 | 新页面未遵守 `min-width:0` | 检查 `.grid > *` 与 `.stack` 的 `min-width`，补 `minmax(0,1fr)` |

## 8. 相关文件

- `src/demo_site.py`：生成器
- `tests/test_demo_site.py`：5 项静态站点测试
- `ui/demo-config.js`：演示开关
- `ui/js/data.js`、`ui/js/app.js`：演示态分支
- `ui/css/styles.css`：`.demo-banner` 与 390 宽网格修复
- `.github/workflows/pages.yml`：GitHub Pages 部署
- `docs/ui_design.md`：页面与 API 设计
- `README.md`：运行入口与验收
