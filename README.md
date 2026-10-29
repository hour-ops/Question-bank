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

```
docs/ config/ data/{,.backup,generation_cache}/ output/{papers}/ logs/{,checkpoints}/
app/{backend,frontend}/ scripts/{,lib}/ tests/{fixtures/smoke}/ 
inbox/{english,c_wuhan,c_hbpu,aca_llm/screenshots}/ subjects/{english,c_wuhan,c_hbpu,aca_llm}/
```
