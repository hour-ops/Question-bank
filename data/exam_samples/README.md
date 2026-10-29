# data/exam_samples —— 真题样板库

全部真题按「**科目 / 题型**」整理，供 AI 生成题目时对照：**题目 + 知识点 + 标准答案 + 解析**。

生成脚本：`scripts/export_exam_samples.py`（纯本地、零 API 花费、可重复运行）

```powershell
python scripts/export_exam_samples.py                 # 重新生成全部
python scripts/export_exam_samples.py --dry-run       # 只统计不写盘
python scripts/export_exam_samples.py --per-type 20   # 改每题型上限（默认 40）
python scripts/export_exam_samples.py --no-dedupe     # 关闭同题干去重
python scripts/export_exam_samples.py --proof         # 生成后打印材料型整组证明
```

## 目录

```
data/exam_samples/
  _index.json                 总索引：各科目/题型样例数、来源卷、知识点覆盖、校验结果
  _knowledge_map.json         题型 ↔ 知识点 映射（来自三个既有知识点库，未新增知识点）
  english/<type>.json         16 个题型（cloze / dialogue / grammar_fill / …）
  c_common/<type>.json        6 个题型（single_choice / program_fill / programming / …）
  aca_llm/_NO_REAL_EXAM.json  ACA 无官方真题 → 如实留空 + 说明
```

## 每个题型文件的字段

| 字段 | 含义 |
|---|---|
| `subject` / `type` / `type_name_cn` / `how` | 科目、题型 key、中文名、作答说明（取自 `config/display.json`） |
| `knowledge_points` | 该题型对应的知识点（英语=题型维度+语言知识维度；C=该题型实际考过的 15 个知识点及样例数） |
| `type_raw_values` | 原始真题里出现过的题型名（零改写，便于回溯） |
| `rules` / `stats` / `exams` | 取样规则、统计、来源卷分布 |
| `samples[]` | 样例数组 |

每条 `sample`：

| 字段 | 含义 |
|---|---|
| `stem` | 题干（**材料型题为空串**，题干在各空的 `stem` 里） |
| `answer` | 标准答案（材料型题为全部答案 ` \| ` 连接） |
| `explanation` | 解析（`explanation_source` 标明来自父题、小题还是各空拼接） |
| `exam` / `exam_title` / `trust` | 来自哪套卷 / 卷名 / 可信度 |
| `knowledge_point` / `knowledge_point_ids` / `knowledge_point_how` | 知识点及命中依据（对不上则空串 + 原因） |
| `material` + `material_blanks` + `material_blanks_total` | **材料型题整块**：整篇原文 + 该组全部空 |
| `options` / `word_bank` | 原始选项 / 选词填空的词库 |
| `kind` | `single`（单题）或 `material`（材料组） |
| `group_uid` | 同一材料组的稳定 id |
| `chapter_raw` / `origin_db` / `school` | C 语言：原题教材章节名 / 来源库 / 学校 |
| `same_stem_exams` | 同一题干还出现在哪些卷（同题干已去重） |

## 三条硬规则

1. **零改写**：题干、材料、答案、解析全部原样落盘。唯一的"渲染"是把源里的
   `{type:'blank'}` 块显式写成 `{{__BLANK_<n>__}}`（源里它只是一段空白，不标出来材料读不通）。
   连词成句保留真题的 `词组 / 词组` 斜杠格式。
2. **材料型不拆**：一篇短文 + 它的全部空 = **一条** sample。脚本对每组空数做断言，
   不符的写进 `_index.json.validation_issues`，绝不静默丢弃。
3. **不猜知识点**：映射不上就留空，并在 `_index.json.unmapped` 里写明原因。

## 与旧库的关系

`data/generation_reference.json`（257 KB / 127 条样例）是**上一代**参考库，按用户要求**保留未删**。
`data/exam_samples/` 是它的**超集与替代**，差异见 `_index.json.relation_to_old_reference`。
下游如只认一个入口，请以 `_index.json` 为准。
