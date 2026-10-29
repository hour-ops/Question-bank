# 题库项目 · 便携版

湖北专升本（英语 / C 语言）+ 阿里云 ACA 大模型工程师 题库与刷题系统。

## 一、快速开始（Windows）

1. 确认已安装 **Python 3.10 或更高版本**（命令行执行 `python --version` 能看到版本号即可）。
   - 没装的话去 <https://www.python.org/downloads/> 下载安装，**安装时务必勾选 "Add Python to PATH"**。
2. 双击 **`安装依赖.bat`**（只需一次，联网下载几十 MB 依赖）。
3. 双击 **`启动.bat`**。浏览器会自动打开 <http://127.0.0.1:5000/quiz>。
4. 关闭：在弹出的黑色窗口里按 `Ctrl+C`，或直接关掉窗口。

> 端口 5000 被占用时会自动改用 5001，实际端口写在 `app\port.txt`。

## 二、可选：配置 AI 判分 / 出题

系统**不配 key 也能用**（做题、组卷、看统计、错题复习全部可用）。
只有以下两件事需要 API key：
- **主观题 AI 判分**（英语语法填空/翻译/写作、C 语言改错/编程）
- **自动补题生成**

配置方法：把 `.env.example` 复制一份改名为 `.env`，填入自己的 key：

```
DEEPSEEK_API_KEY=sk-你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

> ⚠️ 本便携包**不含任何 API key**（出于安全考虑被刻意排除）。

## 三、目录说明

| 目录/文件 | 作用 |
|---|---|
| `启动.bat` / `安装依赖.bat` | 一键启动 / 装依赖 |
| `app/` | 网页应用（后端 Flask + 前端原生页面） |
| `data/` | 题库与作答数据库（SQLite，7 个库） |
| `config/` | 考纲、题型、判分标准、预算、路由等配置 |
| `scripts/` | 全部脚本（抓取/解析/判分/组卷/备份/审核…） |
| `docs/` | 界面设计与维护手册（含 15 条 ADR） |
| `DESIGN.md` | **项目设计书（权威上下文，17 章）** |
| `output/` | 组卷产物（Word/PDF/Excel/Anki/CSV） |
| `logs/` | 运行日志、检查点、成本账本 |
| `subjects/` | 考纲索引（ACA 6 模块 47 个知识点） |
| `tests/` | 测试套件（12 个文件，可离线跑） |

## 四、题库现状

- 共 **890 题**：英语 698｜武汉商学院 C 语言 48｜湖北理工学院 C 语言 48｜ACA 96
- 考纲覆盖缺口 **0**
- 英语六种题型齐全（语法填空/连词成句/阅读填空/阅读理解/翻译填空/写作），**无选择题**（考纲明令）

## 五、常用操作（进阶）

```bat
cd /d %~dp0
python scripts\export_papers.py            :: 组卷导出到 output\papers\
python scripts\backup.py                   :: 一致性快照到 data\backup\
python scripts\update_review_status.py output\review_queue.md   :: 回写人工审核结果
python .tools\final-acceptance.py          :: 跑全部测试做自检（若把 .tools 一并复制）
```

## 六、注意事项

- 定时任务（Windows 任务计划程序）**不会**随本包复制；需要在目标机重新注册：
  `scripts\setup_schtasks.ps1`（需管理员/或按说明调整其中的 Python 路径）。
- 数据库是 SQLite 单文件，直接复制 `data\*.sqlite` 即可迁移/备份。
- 本包面向 **Windows + 电脑端**；不含手机端适配。
