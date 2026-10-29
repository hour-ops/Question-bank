# DESIGN.md · 题库项目设计书（唯一权威上下文）

> 本文件是本项目**唯一权威设计上下文**。任何脚本、配置、判分逻辑与本文件冲突时，以本文件为准。
> 配套执行约束见 `.tools\题库项目-决策记录.md`（v2）。
> 版本 1.0 · 2026-10-11

## 1. 项目成败标准

**不是系统能跑，是题库覆盖考纲、判分能区分掌握程度、每道题有可追溯来源；数量与质量冲突时选质量。**

三条可验收的硬指标：
1. **覆盖**：每个已定义的考纲条目（知识点/考点）在 `questions` 表中有 ≥1 道 `approved` 或 `pending_review` 的题，`data/coverage_matrix.json` 可见逐条覆盖情况。
2. **区分度**：校准数据显示同一题型下 Flash 判分与人工/Pro 参考标准的**一致率 ≥85%**，且分数刻度能区分"全对/部分对/全错"（不是只有 0 和满分两个值）。
3. **可追溯**：每道题都有 `source_url` 或 `source_credit`，且 `fact_claim` / `fact_source` / `fact_verified` 三件套齐全；无法溯源的一律标 `未获取`。

## 2. 科目模块表

| 科目 | 全称 / 依据 | 题量 | 数据库 |
|---|---|---|---|
| `english` | 湖北专升本 英语 | 50 | `data/english.sqlite` |
| `c_wuhan` | 武汉商学院 C 语言（120 分 · 谭浩强第五版） | 50 | `data/c_wuhan.sqlite` |
| `c_hbpu` | 湖北理工学院 C 语言（150 分 · 祁文青 2018 版） | 50 | `data/c_hbpu.sqlite` |
| `aca_llm` | 阿里云 ACA 大模型工程师 V2.4 | 50 | `data/aca_llm.sqlite` |
| — | **合计** | **200** | 另含 `attempts.sqlite` / `cache.sqlite` / `generation_cache.sqlite` |

辅助库：`data/attempts.sqlite`（作答与判分队列）、`data/cache.sqlite`（抓取缓存与源统计）、`data/generation_cache.sqlite`（生成缓存）。

## 3. 英语题型与分值

| 题型 key | 名称 | 卷面题数 | 每题 | 分值 | 判分方式 | 判分模型 |
|---|---|---|---|---|---|---|
| `grammar_fill` | 语法填空 | 10 | 2 | 20 | LLM | `deepseek-flash` / effort `low` |
| `sentence_build` | 连词成句 | 6 | 2 | 12 | LLM | `deepseek-flash` / `low` |
| `reading_fill` | 阅读填空 | 10（2 篇） | 2 | 20 | LLM | `deepseek-flash` / `low` |
| `reading_qa` | 阅读理解（Part IV） | 10（2 篇） | 2 | 20 | LLM | `deepseek-flash` / `low` |
| `translation_fill` | 翻译填空 | 6 | 3 | 18 | LLM | `deepseek-flash` / `low` |
| `writing` | 写作 | 1 | 10 | 10 | LLM | `deepseek-v4-pro` / `high` |
| — | **合计** | **43 题** | | **100** | | |

**卷面信息**：满分 100 分、时长 120 分钟、闭卷笔试、**全部主观题**（填空/问答/翻译/写作）。
**来源**：`http://zsbzt.cn/assets/ExamGuide-pDvJF3qx.js`（第三方考纲解读，其自述引用《2026 年湖北省普通高等学校专升本〈大学英语〉考试要求》并基于 2020–2025 六套真题分析）。
⚠️ 该题数分布与早前假设的 50 题分布（10/8/8/9/15）**不一致，以本表为准**；本库 `target_count=50` 是**配额**（可覆盖多份卷面合计），不等于单份卷面题数。

**明确不做**：英语**没有选择题、没有判断题**（"题型范围：无选择题，无判断题，其他题型不限"）。任何以 A/B/C/D 形式产生的英语"题"视为解析错误，必须人工介入。

## 4. C 语言两校差异

| 项 | 武汉商学院（`c_wuhan`） | 湖北理工学院（`c_hbpu`） |
|---|---|---|
| 试卷总分 | **120 分** | **150 分** |
| 指定教材 | **谭浩强《C 程序设计》第五版** | **祁文青《C 程序设计》2018 版** |
| 题型 | 改错 / 程序填空 / 编程 | 改错 / 程序填空 / 编程 |
| 选择题 / 判断题 | **均无** | **均无** |
| 判分 | 改错、程序填空 → Flash(`low`)；编程 → Pro(`high`) + gcc 编译校验 | 同左 |

两校题目**分库存放**（`data/c_wuhan.sqlite` / `data/c_hbpu.sqlite`），同一考点在两校可各存一题（`subject` 不同 → `question_uid` 天然不同）。

## 5. ACA 考纲 V2.4

| 模块 | 权重 |
|---|---|
| 概念 | 18% |
| 提示词 | 20% |
| 增强 | 22% |
| 微调 | 12% |
| 合规 | 12% |
| Agent | 16% |
| **合计** | **100%** |

- 题型：**单选** + **多选**（无主观题）。
- 判分：**全部本地规则**（`config/aca_rules.json`），**不调用 LLM**，不参与判分校准。
- 覆盖统计按上表六个模块为一级考纲条目，`knowledge_point` 归属模块记入 `syllabus_ref`。
- ⚠️ 权重是**考纲分值权重**，不等于题量配额；题量配额仍为 50 题，按权重分配并允许 ±20% 浮动。

## 6. 数据库 Schema 摘要

**`questions`（4 个科目库各有 1 张）关键字段**：

| 字段 | 说明 |
|---|---|
| `id` / `question_uid` | 自增主键 / 业务唯一 id（见第 7 节），`UNIQUE` |
| `subject` / `school` / `year` / `textbook` | 科目、学校、年份、教材 |
| `source_type` / `source_url` / `source_credit` | 来源类型（`fetch`/`generate`/`smoke`/`judge_baseline`）、URL、来源署名 |
| `chapter` / `knowledge_point` / `syllabus_ref` | 章节、知识点、考纲条目引用（覆盖矩阵依据） |
| `question_type` / `stem` / `options` / `answer` / `explanation` | 题型、题干、选项（JSON）、答案、解析 |
| `difficulty` / `code_template` / `test_cases` | 难度（易/中/难）、C 代码模板、测试用例 |
| `status` | 见第 8 节枚举，默认 `raw` |
| `reviewed_by` / `version` / `quality_score` | 审核人、版本号、质量分 |
| `fact_claim` / `fact_source` / `fact_verified` | 防幻觉三件套（见第 15 节），`fact_verified` 默认 0 |

**其余表**：
- `wrong_book`（`question_uid` PK, `wrong_count`, `correct_streak`, `last_wrong_at`, `next_review_at`, `mastery`, `notes`, `updated_at`）
- `favorites` / `user_notes` / `daily_progress`（`date` PK, `total_done`, `correct_count`, `wrong_count`, `subjects`）/ `review_log`
- `attempts`（`attempt_id` PK, `question_uid`, `judge_score`, `judge_model`, `judge_reason`, `judge_prompt_version`, `elapsed_ms`, `synced`, `source_type`, `created_at`）
- `judge_queue`（`id` PK, `attempt_id`, `judge_status`, `batch_id`, `submitted_at`, `source_type` …）
- `fetched_urls`（`url` PK）/ **`source_stats`**（`subject`,`domain` PK, `fetched`, `hits`, `hit_rate`, `last_fetch_at`, `low_freq`）
- `gen_cache`（`cache_key` PK, `response`, `model`, `created_at`, `hit_count`）

所有库统一 `PRAGMA journal_mode=WAL` + `busy_timeout=30000`。
**入库唯一入口是 `scripts/parse_inbox.py`**，其余脚本一律不写 `questions` 表。

## 7. question_uid 规则与去重口径

**唯一入口**：`scripts/lib/uid.py`（禁止在别处重新实现哈希）。

```python
generate_uid(subject, source_url, stem) = sha256(f"{subject}:{source_url}:{stem[:50]}")[:16]
```

⚠️ **该规则含 `source_url`，同一道题从两个源抓到会得到两个 uid** → 因此必须配合二级指纹：

```python
content_fingerprint(subject, stem) = sha256(f"{subject}:{normalize_stem(stem)}")[:16]
# normalize_stem: NFKC 全角转半角 → 去空白 → 去标点 → 小写
```

**去重流程（入库前）**：
1. 先按 `generate_uid` 判源内重复 → 命中则跳过（同源同题）。
2. 再按 `content_fingerprint` 判跨源同题 → 命中则**不新建**，把新来源写入既有题的 `source_credit`（追加），保留**最早入库**的那条 uid。
3. 模糊兜底：`rapidfuzz.fuzz.token_set_ratio(归一化题干) > 0.9` 视为同题，合并规则同上。

## 8. status / judge_status 枚举（两套不混用）

**`questions.status`**（题目生命周期，6 值）：

| 值 | 含义 |
|---|---|
| `raw` | 刚入库、未解析（默认） |
| `parsed` | 解析完成、待覆盖检查 |
| `pending_review` | 待人工审核（含 AI 补题） |
| `approved` | 通过审核，可组卷 |
| `rejected` | 审核拒绝（原因写 `review_rejects.jsonl`） |
| `archived` | 归档（含判分基准题隔离） |

**`judge_queue.judge_status`**（判分任务生命周期，4 值）：

| 值 | 含义 |
|---|---|
| `pending` | 已入队待判 |
| `submitted` | 已提交（官方 API 无 Batch，此处语义为"已进入串行处理队列"） |
| `synced` | 判分结果已回写 attempts / wrong_book / daily_progress |
| `failed` | 判分失败（指数退避重试 3 次后） |

**硬约束**：两套枚举**不得混用**；UI 判分队列页必须呈现 `failed` 态并支持手动重投。

## 9. 任务清单与频率

照 `config/routing.json`：

| 任务 | routing key（`routing.json`） | 脚本 | 频率 |
|---|---|---|---|
| 抓取 | `fetch` | `scripts/fetch.py` | 每 2h |
| 解析入库 | `parse` | `scripts/parse_inbox.py` | 每 4h |
| 覆盖检查 + 补题 | `validate_and_fill` | `scripts/validate_and_fill.py` | 每天 03:00 |
| 组卷导出 | `export` | `scripts/export_papers.py` | 每天 03:30 |
| 判分同步 | `sync_outbox` | `scripts/sync_outbox.py` | 每 10min |
| 进度聚合 | `update_progress` | `scripts/update_daily_progress.py` | 每 1h |
| SM-2 排程 | `sm2_scheduler` | `scripts/sm2_scheduler.py` | 每 1h（错开 15min） |
| 备份 | `backup` | `scripts/backup.py` | 每周日 04:00 |

**安全约束**：定时任务中**只有 `--dry-run` 类安全任务自动执行**；任何**会调用付费 API 的生成**（`validate_and_fill.py` 非 dry-run）保持**人工触发**。Windows 用 `schtasks`（无 `crontab`）。

## 10. 判分机制

**两条通道（2026-10-12 起，用户需求 2）**：

| 通道 | 谁走这条 | 成本 | 落库 |
|---|---|---|---|
| **规则判分**（`scripts/judge_local.py`） | 答案**确定可判**的题：客观选择题、是非题、填空（语法/阅读/翻译/程序填空/改错）、连词成句、C 的"看程序写结果"短答案 | **0**（不联网、不计费） | `/api/submit` 当场写 `attempts` + `judge_queue(synced)` + `review_log`，并立刻重算当日 `daily_progress` |
| **AI 判分**（`scripts/sync_outbox.py`） | 写作、整段翻译、论述题、要求"编写函数"的整段代码、一道题多空的完形、题库无答案的残题 | 按 token 计费 | 入队 `pending` → `/api/judge_one`（单题即时）或 `/api/sync`（批量） |

**规则判分的口径（改前必读）**：
- 单一事实源 = `scripts/judge_local.py`；`app.py` 只调用它，不另写判分逻辑。
- 满分与"对错"口径与 `sync_outbox.full_score_for()` / `update_daily_progress.judge_correct()` **完全一致**
  （`judge_score >= full_score` 记正确）。
- **宁放不误**：拿不准一律 `gradeable=False` 交给 AI；空作答不判对错。
- 覆盖率体检 + 回归测试：`python scripts/judge_local.py --coverage`、`python tests/test_judge_local.py`。
  2026-10-12 实测：全库 **6,031 / 7,961（75.8%）** 可规则判分，"答对却判错"探针 **0 条**。

| 题型 | 判分方式 | 模型 / 档位 |
|---|---|---|
| ACA 单选、多选 | **本地规则**（`config/aca_rules.json` + `judge_local.py`） | 不调用模型 |
| 英语 客观选择 / 是非 / 连词成句 / 各类填空（答案唯一时） | **本地规则** | 不调用模型 |
| 英语 语法填空 / 阅读填空 / 翻译填空（**长答案或多空**时） | LLM 判分 | `deepseek-flash` / `low` |
| 英语 写作 | LLM 判分（三维度：内容/语言/结构） | `deepseek-v4-pro` / `high` |
| C 单选 / 是非 / 短答案"看程序写结果" | **本地规则** | 不调用模型 |
| C 论述型程序填空 / 改错 | LLM 判分 | `deepseek-flash` / `low` |
| C 编程（整段代码） | LLM 判分 **+ gcc 编译运行校验** | `deepseek-v4-pro` / `high` |

**平台事实（已实测，勿再试）**：
- 走官方 `https://api.deepseek.com`，模型 ID = `deepseek-flash` / `deepseek-v4-pro`。
- **官方没有 Batch API**（`/batches`、`/v1/batches`、`/beta/batches` 全 404）→ 判分走**串行 `chat/completions`**，`judge_status='submitted'` 表示"已进本地串行队列"。
- 思考档位只有 `low` / `high` / `max`（**无 `off`、无 `medium`**）；判分与批量生成一律 `low` 以省思考 token。
- gcc 路径：`.tools\gcc\mingw64\bin\gcc.exe`（MinGW-W64 x86_64 16.2.0）。

## 11. SM-2 复习机制

配置：`config/sm2_config.json`（`intervals_days=[1,3,7,14,30]`，`aca_exit_streak=2`，`downgrade_policy="step_back_one"`）。

| 事件 | 动作 |
|---|---|
| 首次答错 | `wrong_count+1`，`correct_streak=0`，`next_review_at = now + 1 天` |
| 答对且在复习档位 n | `correct_streak+1`，进入下一档 → `next_review_at = now + intervals[n+1]` |
| **中途再错（降级）** | **回退一档**（`step_back_one`，如 7 天档 → 回到 3 天档），`correct_streak=0`；**不是**重置到 1 天 |
| 到达最长档 30 天且答对 | 记 `mastery+1`，移出高频复习 |
| ACA 题连续答对 `aca_exit_streak=2` 次 | 移出错题本 |

| 档位 | 间隔 |
|---|---|
| 1 | 1 天 |
| 2 | 3 天 |
| 3 | 7 天 |
| 4 | 14 天 |
| 5 | 30 天 |

## 12. 生成质量三层验证

| 层 | 手段 | 成本 | 通过条件 |
|---|---|---|---|
| L1 格式校验 | **纯 Python**（不调模型）：JSON 可解析、必填字段非空、`question_type` 合法、分值在范围内、uid 唯一 | ¥0 | 全部通过才进 L2 |
| L2 事实验证 | `deepseek-flash` / `low`，逐题核对事实性主张与答案正确性 | 低 | 输出结构化 `{ok, reason}`，`ok=false` 退回重生成 |
| L3 交叉验证 | `deepseek-v4-pro` / `high`，**抽样 10%** 复核 | 中 | 抽样不一致率 >10% → 整批退回 |

**成本闸门（硬性）**：
- 预算 **¥19.46**（人民币，`config/cost_budget.json` 的 `total=20`），**含主会话 token**。
- 单批预估成本 > `budget.warning`（80%）→ **停下问用户**；余额 ≤ ¥3.9 → 写检查点后**停止**。
- 记账：`logs/cost_ledger.jsonl`（脚本侧逐条）+ 每阶段边界 `GET /user/balance` 余额快照。
- 大批量生成**排空闲时段**（北京时间工作日 09–12 / 14–18 为高峰，价格翻倍）。

## 13. 难度代理指标

难度一律由**机械指标**判定（可脚本计算，不靠 LLM 主观判断）。通用机械量：`stem` 字符数、空/错处数、考点标签数、跨段数、高危关键词命中（指针/递归/文件/结构体/虚拟语气/倒装/从句/跨模块）。

| 题型 | 易 | 中 | 难 |
|---|---|---|---|
| 语法填空 | 考点数=1 且 题干<80 字 且 空=1 | 考点数=2 或 80≤题干<200 或 空=2 | 考点数≥3 或 题干≥200 或 命中虚拟语气/倒装/从句 |
| 连词成句 | 词数≤6 | 词数 7–10 | 词数>10 或含从句 |
| 阅读填空 | 篇章<150 词 且 空≤5 | 150–300 词 或 空 6–8 | >300 词 或 空>8 |
| 阅读问答 | 答案 1 句、可直接摘录 | 需 2–3 句或简单推断 | 需概括/跨段/评价 |
| 翻译填空 | 单句≤10 词 | 11–20 词 | >20 词 或含习语/被动/从句 |
| 写作 | 字数要求≤80 | 81–120 | >120 或图表/议论文 |
| C 改错 | 错处 1 处 | 2 处 | ≥3 处 或涉及指针/内存 |
| C 程序填空 | 空 1–2 且单函数 | 空 3–4 或需循环嵌套 | 空≥5 或递归/指针 |
| C 编程 | 单循环/数组遍历 | 嵌套循环/字符串处理 | 递归/指针/结构体/文件 |
| ACA 单选 | 题干<100 字 且直接概念 | 需 2 步推理 | 跨模块综合 |
| ACA 多选 | 4 选项且同模块 | 跨 2 模块 | 需组合判断正确项 |

> 机械指标只能给**初判**；人工审核页可在 `difficulty` 上覆写。

## 14. 安全边界

**浏览器会话（ACA 抓取）**：
- ✅ 允许：读取页面文本、滚动、点击**白名单域名内**的导航链接、截图到 `inbox/aca_llm/screenshots/`。
- ❌ **禁止读取/导出 cookie、token、localStorage**；**禁止**打开 devtools；**禁止**代替用户登录；**禁止**点击退出/账户/支付/订阅；**禁止**访问白名单外域名。
- 工具层面内置浏览器**具备** `browser_auth`（可导出 cookie）→ 本项目**自律不调用**，并在代码审查时视为违规。
- 遇验证码/滑块/短信二次验证/页面无响应 → **暂停并请人工处理**（见第 17 节）。

**本地服务**：Flask 只绑 `127.0.0.1`（不得 `0.0.0.0`），`debug=False`（调试器可被本地页面触发 RCE）。

**凭据**：只放 `题库项目\.env`（已 gitignore），**不得**写入日志、报告、题库或对话。

**数据**：`excluded_domains`（`renrendoc.com`、`book118.com`）一律不抓；只保存考纲结构/知识点/可追溯来源，不整篇搬运付费内容。

## 15. 防幻觉硬约束

1. **拿不到就写 `未获取`**：任何无法从源文件/页面确证的信息，一律写字符串 `未获取`，**禁止**推测填空。
2. **结论必须标出处**：每条知识点/答案解析都要有 `source_url` 或 `source_credit`；无出处者不得进入 `approved`。
3. **`fact_claim` 三件套**：`fact_claim`（可核查的事实主张）+ `fact_source`（来源）+ `fact_verified`（0/1，默认 0）。
   - `fact_claim` / `fact_source` **只能来自源文件的显式头部标注**（`fact_claim: "..."` / `fact_source: "..."`），**不得**由正则"推断"。
   - AI 补题的 `fact_source` 只允许三类取值：① 真实白名单 URL ② 教材章节引用（**人工确认后**才可置 `fact_verified=1`）③ 显式 `AI生成-未验证`（强制 `fact_verified=0`，**不得进入组卷**）。
4. **禁止编造来源**：不得生成看起来像 URL 的字符串充当来源。

## 16. 明确不做

- ❌ 手写识别（OCR 仅用于既有截图的文本提取；**且不从截图 OCR 生成知识点**）
- ❌ 手机端适配（仅电脑端，最小点击区按 44px 而非 44dp）
- ❌ 社交功能 / 排行榜 / 课程推荐
- ❌ 选择题、判断题进入英语与 C 语言题库（与第 3、4 节冲突）
- ❌ 用 `off` / `medium` 思考档位（官方不支持）
- ❌ 依赖 Batch API（官方无此接口）

## 17. 人工介入条件

| 触发条件 | 处理 |
|---|---|
| 遇验证码 / 滑块 / 短信二次验证 | 立即暂停自动化，输出「请手动完成验证」，等用户回复「继续」 |
| 需要登录 / 二次登录 | 暂停，请用户在**本任务的浏览器窗口**完成登录 |
| 页面跳转到白名单外域名 | 暂停，输出「检测到跳转，是否继续？」由用户判断 |
| 连续 3 次点击无响应 | 截图 + 输出「页面无响应」，由用户检查 |
| 出现付款 / 订阅按钮 | **立即停止**，绝不点击，交用户处理 |
| 预算达 80%（≈¥16） | 停下问用户是否继续 |
| 预算达 100%（余额 ≤¥3.9） | **保存检查点并停止**，等用户充值后按检查点续跑 |
| 判分校准 3 轮仍不达标 | 停下问用户（附失败模式表） |
| 单阶段失败项超过该阶段失败预算 | 停下问用户 |
| 题库题量与考纲覆盖冲突 | **选质量**：宁可少题，不可缺来源 |
