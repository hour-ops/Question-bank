# 题库项目（湖北专升本英语 / C 语言 + 阿里云 ACA 大模型工程师）

> 唯一权威上下文见 `.tools\题库项目-决策记录.md`（v2）。**执行前必读其第 0 节与第 6 节**。

## 环境

- **解释器（必须用这个，64 位）**：
  `C:\Users\win11_vmusers\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`
  （PATH 里的 `python` 是 32 位，且 `python -m venv` 建不出 pip，**不要用**）
- **gcc（C 编程题编译校验）**：
  `C:\Users\win11_vmusers\Documents\deepseek-harness\default-workspace\.tools\gcc\mingw64\bin\gcc.exe`
- **凭据**：`.env`（`DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL=https://api.deepseek.com`）
  ⚠️ 官方 API **没有 Batch API**，判分走串行 `chat/completions`
  ⚠️ 思考档位只有 `low` / `high` / `max`；判分与生成用 `low`（省思考 token）

## 常用命令

```powershell
$PY = 'C:\Users\win11_vmusers\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$ROOT = 'C:\Users\win11_vmusers\Documents\deepseek-harness\default-workspace\题库项目'
Set-Location $ROOT

# 数据库初始化（幂等）
& $PY scripts\init_db.py --verify

# 全链路
& $PY scripts\fetch.py --subject all --dry-run     # 先 dry-run 看 URL 与预估
& $PY scripts\fetch.py --subject english
& $PY scripts\parse_inbox.py --dry-run             # 唯一入库入口
& $PY scripts\parse_inbox.py
& $PY scripts\validate_and_fill.py --dry-run       # 覆盖矩阵 + 预估成本
& $PY scripts\update_review_status.py output\review_queue.md
& $PY scripts\export_papers.py
& $PY scripts\sync_outbox.py --mock
& $PY scripts\update_daily_progress.py
& $PY scripts\sm2_scheduler.py

# Web UI
& $PY app\backend\app.py                            # 端口见 app\port.txt

# 备份 / 恢复
& $PY scripts\backup.py                             # VACUUM INTO → data\backup\<时间戳>\
# 恢复顺序（Windows 文件锁）：先停 Flask → 删 *.sqlite-wal/*.sqlite-shm → 覆盖主库
```

## 成本纪律（硬性）

- 预算 **¥19.46**（人民币），**含主会话 token**；余额 ≤ ¥3.9（花掉 80%）→ 写 `logs\checkpoints\` 后停止。
- 只有**阶段 6（校准）和阶段 7（补题生成）花钱**；其余阶段零 API 花费。
- 大批量生成**排空闲时段**（工作日 18:00 后 / 周末全天，价格减半）。
- 每个阶段边界用 `GET /user/balance` 取余额快照，记 `logs\cost_ledger.jsonl`。

## 目录
# Question-bank

这是一个基于大语言模型（LLM）的垂直领域 AI 应用，旨在解决专升本复习中主观题批改难、题库检索不准以及大模型调用成本高等痛点。本项目当前为 MVP（最小可行性产品）阶段，主要验证 RAG 检索与 Prompt 工程在复杂教育场景下的有效性。

## ✨ 核心特性与技术亮点

1. **自定义 Chunking 策略 (RAG)**：针对题目格式混乱、公式与特殊符号多的问题，放弃默认切分规则，自定义了文本切分策略，**严格保留题目内部空格与特殊字符边界**，确保了检索时上下文的完整性与语义准确度。
2. **提示词工程约束 (Prompt Engineering)**：为解决 AI 无法理解复杂人类指令的问题，重写了 System Prompt，并引入 **Few-Shot（少样本提示）** 正反例及严格的负面约束（要求什么/不要什么），大幅降低了模型输出的发散性。
3. **多温度采样判分 (Self-Consistency)**：针对大模型主观题评判标准不一（和稀泥）的问题，设计了**“判分人设提示词 + 多温度（Temperature）采样取平均值”**的评判路径。通过多次调用云端大模型 API 并取均值，极大提升了判分系统的客观性与稳定性。
4. **成本控制与模型路由 (Model Routing)**：在流程中引入模型路由机制。简单任务（如题干提取）调用轻量化模型，复杂任务（如主观题深度解析）才通过 API Key 调用云端高算力大模型，有效控制了整体 Token 消耗与调用成本。

## 🛠 技术栈与工具
*   **大模型 API**：DeepSeek API
*   **开发与编排工具**：DeepSeek Harness (DSH)
*   **核心逻辑**：RAG 检索增强、Prompt Engineering、Model Routing

## 📁 项目目录结构说明
*   `prompts/`：存放系统提示词（System Prompt）与 Few-Shot 约束样例。
*   `screenshots/`：存放工作流配置、多温度采样对比结果、模型路由配置的截图（已打码脱敏）。
*   `api_testing/`：存放大模型 API 请求与返回结果的示例记录。


## ⚠️ 已知缺陷与未来迭代计划 (Roadmap)
作为一个早期 MVP 版本，目前系统仍存在一些不足，这也是我个人后续开发的重点：
*   **[架构重构]**：当前逻辑依赖 DSH 进行半可视化编排。**下一步计划**：使用 **Python + FastAPI + LangChain** 从零手写重构后端逻辑，彻底摆脱对特定平台的依赖，实现代码级控制。
*   **[并发性能]**：多温度采样当前为串行执行，判分响应延迟较高。**下一步计划**：引入 Python `asyncio` 实现异步并发调用，降低系统响应时间。
*   **[复杂解析]**：当前切分策略对复杂表格和图片的支持较弱。**下一步计划**：引入专用的 PDF 表格解析库（如 Camelot）配合多模态大模型进行处理。
[功能扩展-开发中]：目前仅实现了题库检索和主观题判分。正在开发“知识点切片+云端大模型深度讲解”模块。计划实现：用户点击某道错题，系统自动召回关联的知识点切片，并调用云端大模型生成针对该知识点的详细解析，形成完整的“测-评-讲”业务闭环。(当前进度：已完成基本架构设计，正在调试云端 API 的流式输出与上下文拼接)。
---
*Created by [hour-ops] | 2026.10*

```

```
