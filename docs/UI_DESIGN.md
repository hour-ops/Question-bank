# UI_DESIGN.md · 界面设计（题库项目）

> 配套 `DESIGN.md`（业务规则）与 `.tools\题库项目-决策记录.md`（执行约束）。
> 版本 1.0 · 仅电脑端

## 1. 技术形态

- 后端 **Flask**（`app/backend/app.py`），仅绑定 **`127.0.0.1`**，`debug=False`。
- 入口地址：**http://127.0.0.1:5000/quiz**（端口被占用则回退 5001，**并把实际端口写入 `app/port.txt`**；所有验收脚本必须读 `port.txt`，不得硬编码 5000）。
- 前端：`app/frontend/`，**纯原生 HTML/CSS/JS，零框架、零 CDN**，所有静态资源本地化。
- **仅电脑端**（不做移动端适配）；最小点击区按 **44px**（不是移动端的 44dp）。

## 2. 页面结构

| 路由 | 页面 | 说明 |
|---|---|---|
| `/` | 首页 | 科目入口、今日进度、复习待办 |
| `/quiz` | 刷题 | 主答题界面（按科目/题型/难度筛选） |
| `/analysis` | 结果分析 | 各科正确率、题型分布、知识点薄弱项 |
| `/compare` | 复盘对比 | 本次 vs 历史、错题对照 |
| `/queue` | 判分队列 | `judge_queue` 实时状态（见第 3 节） |
| `/settings` | 设置 | 模型档位、批量大小、预算显示、端口信息 |
| `/review` | 人工审核 | 一屏一题（见第 7 节） |

后端接口：`GET /api/questions`、`GET /api/attempts`、`GET /api/progress`、`GET /api/papers`、`POST /api/submit`、`POST /api/sync`、`POST /review/action`。

## 3. 判分状态机

**主流程三态 + 异常态**（与 `judge_queue.judge_status` 的四值枚举严格对应，不得混用 `questions.status`）：

| 状态 | 徽标 | 含义 | 界面动作 |
|---|---|---|---|
| `pending` | 灰 · 待判 | 已入队 | 显示"排队中" |
| `submitted` | 蓝 · 处理中 | 已进入串行判分队列 | 显示进度/预计 |
| `synced` | 绿 · 已完成 | 结果已回写 attempts/wrong_book/daily_progress | 展示分数与解析 |
| **`failed`** | **红 · 失败** | 判分失败（重试 3 次后） | **显示失败原因 + "手动重投"按钮** |

> ⚠️ 原设计只画了三态，会导致失败任务在界面上"消失"。**必须呈现 `failed` 并可重投**。

## 4. 色彩规范

| 用途 | 色值 |
|---|---|
| 主色（按钮/链接/选中） | `#2563EB` |
| 正确 | `#10B981` |
| 错误 | `#EF4444` |
| 待复习 | `#F59E0B` |
| 页面底色 / 卡片 | `#F8FAFC` / `#FFFFFF` |
| 正文 / 次要文字 | `#0F172A` / `#64748B` |

## 5. 交互规范

- **单选即跳**：选中选项后立即提交并进入下一题（无需点"确认"）。
- **多选手动提交**：多选需显式点击"提交本题"。
- **答错红色闪烁**：错误反馈用 `#EF4444` 闪烁 2 次（≤400ms），不用持续动画以免干扰。
- **最小点击区 44px**，键盘可达（Tab/Enter）。
- 答题提交后禁用重复提交；网络失败给出明确提示与重试按钮。
- 复习题（SM-2 到期）在题号旁显示 `#F59E0B` 待复习标记。

## 6. 判分流程

```
用户提交 → POST /api/submit → 写 attempts + judge_queue(pending)
   → [串行判分队列] → judge_queue(submitted)
   → 判分完成 → 回写 attempts / wrong_book / daily_progress → judge_queue(synced)
   → 答错则进入 SM-2（next_review_at = now + 1 天，见 DESIGN.md 第 11 节）
失败（重试 3 次）→ judge_queue(failed) → 界面红标 + 手动重投
```

> ⚠️ 官方 API **没有 Batch API**，因此 `submitted` 的真实含义是"已进入本地串行队列"，**没有远端批次可轮询**。

## 7. 人工审核页 /review

- **一屏一题**，展示：题干、选项/模板、答案、解析、`source_url`、`fact_claim`/`fact_source`/`fact_verified`、相似题提示（跨源去重命中时）。
- **三个按钮**：**通过**（→ `approved`）、**拒绝**（→ `rejected`）、**修改**（就地编辑后保存 → 仍为 `pending_review` 或直接 `approved`）。
- **拒绝必须选择原因**（下拉：答案错误 / 来源不可信 / 表述歧义 / 重复题 / 超纲 / 格式问题 / 其他），原因写入 `logs/review_rejects.jsonl`。
  ⚠️ **拒绝原因不得写入 `config/distractors.json`** —— 后者只存干扰项。
- 审核动作写 `review_log`，并更新 `questions.reviewed_by` / `version`。
- 支持键盘快捷键：`A` 通过、`R` 拒绝、`E` 修改、`←/→` 切题。

## 8. 不适用范围

- ❌ 手写识别（不接入 OCR；图片题一律人工录入）
- ❌ 手机端适配（仅电脑端，最小点击区 44px）
- ❌ 社交 / 排行榜 / 课程推荐
- ❌ 用户注册登录体系（单机自用，不引入鉴权复杂度）
