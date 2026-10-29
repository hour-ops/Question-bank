# MAINTENANCE.md · 维护手册（题库项目）

> 配套 `DESIGN.md`（业务规则）、`docs/UI_DESIGN.md`（界面）、`.tools\题库项目-决策记录.md`（执行约束）。
> 版本 1.0 · 2026-10-11

## 1. ADR 记录（ADR-001 ~ ADR-015）

### ADR-001 入库唯一入口
`scripts/parse_inbox.py` 是**唯一**写 `questions` 表的脚本，其余脚本只读或写其它表。
**后果**：题库写入路径可审计、可重放；任何绕过入口的写入视为缺陷。

### ADR-002 uid 含来源 + 二级指纹去重
`question_uid = sha256(subject:source_url:stem[:50])[:16]`；因为含 `source_url`，同题跨源会产生两个 uid，故引入
`content_fingerprint(subject, normalized_stem)` 作为跨源同题判定，命中则合并来源、保留最早 uid。
**后果**：既保证源内唯一，又能避免跨源重复题虚增题量。

### ADR-003 两套状态枚举严格分离
`questions.status`（6 值：raw/parsed/pending_review/approved/rejected/archived）与
`judge_queue.judge_status`（4 值：pending/submitted/synced/failed）**不得混用**。
**后果**：题目生命周期与判分任务生命周期解耦；UI 上分属不同页面。

### ADR-004 批量生成 + 生成缓存
按题型的 `batch` 参数批量生成（ACA 8 / 英语语法 5 / 写作 3 / C 改错 5 / C 编程 3），
生成前查 `gen_cache`，命中直接返回；每批附上一批题干摘要以防重复。
**后果**：减少往返与重复生成；缓存命中率直接决定成本。

### ADR-005 分题型路由（模型 + 思考档位）
由 `config/routing.json` 的 `generate` 段声明每题型用 `deepseek-flash`（`effort=low`）还是 `deepseek-v4-pro`（`effort=high`）。
**后果**：主观/复杂题用强模型，机械题用便宜模型；⚠️ 思考 token 按输出计费，判分与批量生成必须 `low`。

### ADR-006 少样本蒸馏
从**已审核通过**的题中抽取同题型范例（每题型 2–3 条）作为 few-shot 附在生成 prompt 里，而非全库拼接。
**后果**：提升格式与风格一致性；范例数量受控，避免 prompt 膨胀。

### ADR-007 事实三层验证
L1 格式校验（纯 Python，¥0）→ L2 事实验证（flash/low）→ L3 交叉验证（pro/high，**抽样 10%**）。
**后果**：把最贵的验证限制在抽样的 10%；L1 不过的题不进 L2（先省后花）。

### ADR-008 检查点机制
每个阶段边界写 `logs/checkpoints/<stage>.json`（含题量、余额、产物、blocker），并在 `logs/cost_ledger.jsonl` 记余额快照。
**后果**：任何时刻中断都能续跑；成本可归因到阶段。

### ADR-009 官方无 Batch API → 串行判分队列
实测 `/batches`、`/v1/batches`、`/beta/batches` 全 404。判分改为**串行 `chat/completions` + 本地队列**，
`judge_status='submitted'` 表示"已进本地队列"。
**后果**：删除了原设计的轮询逻辑；判分吞吐取决于串行速率与并发上限（flash 2500 / pro 500）。

### ADR-010 ACA 本地规则判分
ACA 单选/多选全部按 `config/aca_rules.json` 本地判分，**不调用 LLM**，也不参与判分校准。
**后果**：ACA 判分零成本、零延迟、完全确定；校准工作量集中在英语与 C 语言。

### ADR-011 浏览器会话安全边界
ACA 抓取只用内置浏览器读页面/滚动/点击白名单内链接/截图；**禁止**读 cookie/token/localStorage、
禁止开 devtools、禁止代替登录、禁止点击支付/订阅。内置浏览器具备 `browser_auth` 能力，本项目**自律不调用**。
**后果**：把"能力"与"授权"分离；违规视为缺陷。

### ADR-012 定时任务用 Windows 任务计划程序
本机 Windows **无 `crontab`**；原计划依赖的 `dsh-cron-scheduler` 插件因包自身 bug 无法激活（引用了不存在的 `dsh-cron`）已撤除。
改用 `schtasks`（8 个任务），且**定时任务只跑 `--dry-run` 类安全动作**，付费生成保持人工触发。
**后果**：调度不依赖 DSH 常开、不消耗 agent token；⚠️ schtasks 默认**仅当用户登录时运行**。

### ADR-013 SQLite 一致性备份与恢复
备份用 `VACUUM INTO` 或 `Connection.backup()`（**不得**直接复制正在使用的库文件）；
恢复必须**先停 Flask → 删 `*.sqlite-wal` / `*.sqlite-shm` → 覆盖主库**（Windows 文件锁会导致 `WinError 32`）。
**后果**：快照一致、恢复可重复；恢复会覆盖测试期所有数据，故恢复前须确认无真实数据要保留。

### ADR-014 成本闸门与时段策略
预算 **¥19.46**（人民币，含主会话 token）；达 **80%（¥16）** 停下问用户，余额 **≤¥3.9** 写检查点并停止。
大批量生成排**空闲时段**（北京时间工作日 09–12 / 14–18 为高峰，价格翻倍）。
**后果**：重活成本可降一半；预算耗尽时项目可续跑而非报废。

### ADR-015 前端原生 + 本地服务收敛
前端纯原生 HTML/CSS/JS、静态资源全部本地化（不引 CDN）；Flask 只绑 `127.0.0.1` 且 `debug=False`。
**后果**：不依赖外网 CDN、无构建链；不把改状态的接口暴露到局域网。

## 2. 参数速查表

| 参数 | 值 | 位置 |
|---|---|---|
| API 端点 | `https://api.deepseek.com` | `.env` → `DEEPSEEK_BASE_URL` |
| 模型 | `deepseek-flash` / `deepseek-v4-pro` | `config/routing.json` |
| 思考档位 | `low`（判分/生成）· `high`（写作/编程/标准） | `config/routing.json` |
| 预算 | `total=20` `currency=CNY` `warning=0.8` `stop=1.0` | `config/cost_budget.json` |
| 批量大小 | ACA 8 / 语法 5 / 写作 3 / C改错 5 / C编程 3 | `config/routing.json` |
| 去重阈值 | 相似度 `> 0.9` 视为同题 | `scripts/parse_inbox.py` |
| SM-2 间隔 | `[1,3,7,14,30]` 天，`aca_exit_streak=2`，降级 `step_back_one` | `config/sm2_config.json` |
| 备份保留 | 最近 **7** 份 | `scripts/backup.py` |
| 日志轮转 | `logs/cron.log` > **10MB** → `cron.log.1` | `scripts/backup.py` |
| 抓取节流 | 串行 + 间隔 ≥2s + 遵守 robots.txt | `scripts/fetch.py` |
| 失败源冷却 | 14 天不重试（按 domain） | `scripts/fetch.py` |
| 低频源阈值 | 命中率 < 0.2 → 每周只抓 1 次 | `scripts/fetch.py` |
| 三层验证 | L1 全量 / L2 全量 / L3 抽样 **10%** | `scripts/validate_and_fill.py` |
| 服务端口 | 5000（占用回退 5001），写入 `app/port.txt` | `app/backend/app.py` |
| 解释器 | 64 位 DSH 捆绑 Python 3.12 | `.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe` |
| gcc | MinGW-W64 x86_64 16.2.0 | `.tools\gcc\mingw64\bin\gcc.exe` |

## 3. 修改指南

| 想改什么 | 改哪里 |
|---|---|
| **改预算** | `config/cost_budget.json` 的 `total` / `warning` / `stop` / `subjects`；同步 `DESIGN.md` 第 12 节与 `README.md` |
| **改判分规则** | 判分 prompt 在 `config/judge_prompt.json`（改 `version` 号并留旧版）；ACA 规则在 `config/aca_rules.json`；模型/档位在 `config/routing.json` 的 `generate` 与 `config/taxonomy.json` 的 `question_types[*].model/effort` |
| **加/改科目** | ① `config/taxonomy.json` 增科目块 ② `config/source_whitelist.json` 增域名/keywords ③ `scripts/init_db.py` 的 `SUBJECTS` 增名并重跑 ④ `DESIGN.md` 第 2 节表格 |
| **加/改题型** | `config/taxonomy.json` 的 `question_types`（含 `paper_score`、`judge`、`model`、`effort`）；同步 `DESIGN.md` 第 3/4/10 节与难度指标第 13 节 |
| **改 UI** | `docs/UI_DESIGN.md`（设计）+ `app/frontend/`（实现）；色彩/点击区/状态机三处不得与 DESIGN 冲突 |
| **改路由/频率** | `config/routing.json` 的 `schedules`；改完**必须同步重建 schtasks 任务**（见第 5 节） |
| **恢复手机端** | 在 `docs/UI_DESIGN.md` 删除"不适用"条目；给 `app/frontend/` 加 viewport meta 与栅格断点；最小点击区保持 44px；`DESIGN.md` 第 16 节移除对应"不做"项 |
| **换 API 供应商** | `.env` 的 `DEEPSEEK_BASE_URL` / `DEEPSEEK_API_KEY`；确认新端点支持的模型 ID 与思考档位，并重跑 `tests/` 全部自检 |
| **改 gcc 路径** | `.tools\gcc\mingw64\bin\gcc.exe`；如换版本，同步 `README.md`、`MAINTENANCE.md` 与本表 |

## 4. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-11 | 1.0 | 建立项目骨架：7 个 SQLite、8 个 config、`scripts/lib/uid.py`、`scripts/init_db.py` |
| 2026-10-11 | 1.0 | `DESIGN.md`（17 章）与本文档、`docs/UI_DESIGN.md` 建立 |
| 2026-10-11 | 1.0 | 复核修正：思考档位 `low/high/max`（无 `off`/`medium`）、官方无 Batch API、预算改人民币 ¥20、`-1` 冒烟移至阶段 8 之后 |

## 5. 常见问题（FAQ）

**Q1. 用哪个 Python？**
必须用 64 位捆绑解释器：`.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`。
PATH 里的 `python` 是**32 位**，且 `python -m venv` 装不出 pip，不要用。

**Q2. 为什么没有 `.venv`？**
本机 venv 的 `ensurepip` 失败（venv 里没有 pip），依赖直接装进 64 位捆绑 Python。
装依赖用**清华镜像**加速：`-i https://pypi.tuna.tsinghua.edu.cn/simple`；pip 需要 `danger-full-access`。

**Q3. 为什么判分不用 Batch API？**
官方 `api.deepseek.com` **没有** `/batches`（全 404）。判分走串行 `chat/completions` + 本地队列。

**Q4. 思考档位为什么没有 `medium` / `off`？**
官方 `deepseek-flash` 只支持 `low` / `high` / `max`（默认 `high`）。文档里出现 `off`/`medium` 一律是错的。

**Q5. 图片题能自动识别吗？**
不能。`tesseract` 未安装且已决定不装；`parse_inbox.py` 遇到 `png` 只记录文件名并标 `未获取`。

**Q6. 端口 5000 被占用怎么办？**
`app.py` 自动回退 5001 并写入 `app/port.txt`。**所有测试脚本读 `port.txt`**，不要硬编码。

**Q7. 恢复备份后数据不对？**
检查是否漏删 `*.sqlite-wal` / `*.sqlite-shm`（残留 WAL 会被重放）。恢复前必须**先停 Flask**，否则 Windows 文件锁报 `WinError 32`。

**Q8. 怎么查余额 / 花了多少？**
`node .tools\check-balance.mjs`（只读，0 成本），或在项目里 `GET {base}/user/balance`。

**Q9. 定时任务不触发？**
`schtasks` 默认**仅当用户登录时运行**；锁屏/注销不执行。需要检查 `schtasks /query /tn "题库\*" /v /fo LIST`。

**Q10. C 编程题怎么校验？**
用 `.tools\gcc\mingw64\bin\gcc.exe` 编译 + 运行 `test_cases`；编译/运行失败即判 0 分并记录原因。

## 6. 文件索引

| 路径 | 作用 |
|---|---|
| `DESIGN.md` | 业务权威设计（17 章） |
| `docs/UI_DESIGN.md` / `docs/MAINTENANCE.md` | 界面设计 / 维护手册 |
| `config/taxonomy.json` | 科目、题型、分值、判分模型与档位 |
| `config/judge_prompt.json` | 判分 prompt 版本与内容 |
| `config/aca_rules.json` | ACA 本地判分规则 |
| `config/sm2_config.json` | SM-2 间隔与降级策略 |
| `config/source_whitelist.json` | 白名单域名、keywords、搜索模板、排除域名 |
| `config/cost_budget.json` | 预算与闸门 |
| `config/routing.json` | 任务频率 + 分题型生成参数 |
| `config/distractors.json` | 干扰项库（**不含**拒绝原因） |
| `scripts/init_db.py` | 7 库初始化（幂等） |
| `scripts/lib/uid.py` | uid 与跨源指纹唯一实现 |
| `scripts/fetch.py` | 抓取（缓存/白名单/节流/失败冷却/低频源） |
| `scripts/parse_inbox.py` | **唯一入库入口** |
| `scripts/validate_and_fill.py` | 覆盖矩阵 + 补题 + 三层验证 |
| `scripts/export_papers.py` | 组卷导出（docx/pdf/xlsx/anki/CSV-BOM） |
| `scripts/sync_outbox.py` | 判分队列串行处理与回写（`--mock`） |
| `scripts/update_daily_progress.py` | 日进度聚合 |
| `scripts/sm2_scheduler.py` | SM-2 排程 |
| `scripts/update_review_status.py` | 审核结果回写 |
| `scripts/backup.py` | 一致性备份 + 日志轮转 |
| `app/backend/app.py` | Flask 后端 |
| `app/frontend/` | 原生前端 |
| `tests/` | 自检与 smoke test |
| `logs/checkpoints/` · `logs/cost_ledger.jsonl` | 检查点与成本账本 |
| `inbox/{subject}/` | 抓取/素材落地（解析输入） |
| `subjects/{subject}/` | 科目级索引（如 `syllabus_index.json`） |
| `output/papers/` | 组卷产物 |

## 7. 成本优化手册

**官方价目（元 / 百万 tokens）**

| 项 | flash 空闲 | flash 高峰 | pro 空闲 | pro 高峰 |
|---|---|---|---|---|
| 输入·缓存命中 | 0.02 | 0.04 | 0.15 | 0.30 |
| 输入·未命中 | 1 | 2 | 4.5 | 9 |
| 输出 | 4 | 8 | 13.5 | 27 |

**四条具体优化手段**

1. **批量生成**：`generate.batch` = ACA 8 / 语法 5 / 写作 3 / C改错 5 / C编程 3。批量越大，单题摊到的 prompt 前缀越少；
   但批太大易出现"批内重复"与格式漂移，故上限 8。每批附上一批题干摘要防重复。
2. **缓存命中**：`generation_cache.sqlite` 的 `gen_cache` 以 `cache_key`（题型+题干归一化+模型+prompt 版本）命中即返回，
   不重复计费；判分侧的缓存命中靠**固定 prompt 前缀**（同一 `judge_prompt.version` 不要中途改动）。
3. **少样本蒸馏**：每题型只抽 **2–3** 条已审核范例（`status='approved'`）作 few-shot；范例固定后**不要再改**，否则破坏输入缓存前缀。
4. **分题型路由**：机械题一律 `deepseek-flash` + `effort=low`；只有写作、C 编程、判分标准生成用 `deepseek-v4-pro` + `high`。

**两个最容易烧钱的坑**

- **思考 token 按输出计费**：同样的题，`effort=high` 的输出 token 可能是 `low` 的 2–5 倍。判分/生成**必须** `low`。
- **高峰时段翻倍**：北京时间工作日 **09–12 / 14–18** 是高峰；大批量生成排到 **18:00 后或周末**，直接省一半。

**预算闸门**：`warning=0.8`（≈¥16 停下问用户）、`stop=1.0`（余额 ≤¥3.9 写检查点停止）。
