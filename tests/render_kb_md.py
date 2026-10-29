# -*- coding: utf-8 -*-
"""Render knowledge_base.md for both subjects from the JSON."""
import json, os, sys, io, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ROOT = r'C:\Users\win11_vmusers\Documents\deepseek-harness\default-workspace\题库项目'

ERA = {
 'new_2024plus': '2024+ 新格式（湖北·全主观题）',
 'old_2020_2023': '2020–2023 老格式（湖北·含客观题）',
 'hebei_2016_2025': '河北格式（2016–2025）',
}

# ============================== C ==============================
d = json.load(open(os.path.join(ROOT,'subjects','c_common','knowledge_base.json'), encoding='utf-8'))
L = []
L.append('# C 语言知识点体系（规范版）')
L.append('')
L.append('> 由 `tests/build_c_kb.py` 从 `data/c_wuhan.sqlite` + `data/c_hbpu.sqlite` 只读生成；'
         '构建时间 %s。' % d['built_at'])
L.append('> 本文档与 `knowledge_base.json` 内容一致，JSON 为机器可读版本。')
L.append('')
L.append('## 一、总览')
L.append('')
s = d['stats']
L.append('| 项 | 值 |')
L.append('|---|---|')
L.append('| 题库 | %s |' % ' + '.join(d['source']['dbs']))
L.append('| 题目总数 | %d |' % s['total_questions'])
L.append('| 规范知识点数 | **%d** |' % s['total_points'])
L.append('| 原始章节名（非空，去重） | **%d** |' % s['distinct_raw_chapter_names'])
L.append('| 已映射章节名 | %d |' % s['raw_names_assigned'])
L.append('| 未映射章节名 | **%d** |' % s['raw_names_unmapped'])
L.append('| 知识点覆盖题数 | **%d**（只统计有章节名的题） |' % s['covered_questions'])
L.append('| knowledge_point 为空串的题 | %d（c_wuhan %d / c_hbpu %d）——**不在任何知识点内** |' % (
    d['unassigned']['total_rows'], d['unassigned']['rows']['c_wuhan.sqlite'], d['unassigned']['rows']['c_hbpu.sqlite']))
L.append('')
L.append('> ⚠️ 命名覆盖率：有章节名的题 %d / 全部 %d 题 = **%.1f%%**；'
         '剩下 %d 题的 `knowledge_point` 在源库里就是空串。' % (
    s['covered_questions'], s['total_questions'], 100.0 * s['named_chapter_share_of_all_questions'],
    d['unassigned']['total_rows']))
L.append('')
L.append('原始题型分布：`%s`' % '`, `'.join('%s=%d' % (k,v) for k,v in d['source']['question_type_distribution'].items()))
L.append('')
L.append('trust_level 分布：`%s`；exam_title 共 %d 种。' % (
    '`, `'.join('%s=%d' % (k,v) for k,v in d['source']['trust_level_distribution'].items()),
    d['source']['exam_title_count']))
L.append('')
L.append('## 二、归一化规则')
L.append('')
L.append(d['merge_rule'])
L.append('')
L.append('关键点：')
L.append('')
L.append('1. **章号不可信**。不同教材的「第7章」分别指函数、指针或数组，所以匹配前先剥掉 `第N章` 前缀，只按标题语义归并。')
L.append('2. **同义标题合并**。例如 `第5章 循环结构程序设计`、`第6章 循环结构程序设计`、`第4章 循环结构程序设计`、`项目五 设计循环结构程序` 全部归入 `C-05 循环结构`。')
L.append('3. **复合章节单独记录**。跨主题的章节（如 `第3章 流程控制`、`第11章 指针和数组`）归属唯一主知识点，同时在 `multi_topic_chapters` 里记下次要点，不会丢信息。')
L.append('4. **空串不算章节名**。`knowledge_point` 为空串的题单独记在 `unassigned`，不计入映射率分子分母。')
L.append('')
L.append('## 三、规范知识点清单')
L.append('')
L.append('| ID | 知识点 | 覆盖题数 | c_wuhan | c_hbpu | 原始章节名数 | 复合章节题数 |')
L.append('|---|---|---|---|---|---|---|')
for k in d['knowledge_points']:
    L.append('| `%s` | %s | %d | %d | %d | %d | %s |' % (
        k['id'], k['name'], k['question_count'],
        k['question_count_by_db']['c_wuhan.sqlite'], k['question_count_by_db']['c_hbpu.sqlite'],
        k['alias_count'], k.get('multi_topic_question_count', 0) or '—'))
L.append('')
for k in d['knowledge_points']:
    L.append('### %s %s' % (k['id'], k['name']))
    L.append('')
    L.append('- **说明**：%s' % k['desc'])
    L.append('- **%s**' % k['canonical_hint'])
    L.append('- **覆盖题数**：%d（c_wuhan %d / c_hbpu %d）' % (
        k['question_count'], k['question_count_by_db']['c_wuhan.sqlite'], k['question_count_by_db']['c_hbpu.sqlite']))
    if k.get('related_points'):
        L.append('- **关联知识点**：%s' % '、'.join('`%s`' % r for r in k['related_points']))
    L.append('- **子考点**：%s' % '；'.join(k['sub_points']))
    L.append('- **alias_chapters（%d 个原始章节名）**：' % k['alias_count'])
    L.append('')
    for a in k['alias_chapters']:
        L.append('  - `%s`' % a)
    L.append('')
    if k.get('multi_topic_chapters'):
        L.append('- **复合章节（主归属本点，兼含其他知识点）**：')
        for n, sec in k['multi_topic_chapters'].items():
            L.append('  - `%s` → 兼含 %s' % (n, '、'.join('`%s`' % x for x in sec)))
        L.append('')
L.append('## 四、未映射章节名')
L.append('')
L.append('`unmapped_chapters` = `%s`（共 **%d** 个）' % (json.dumps(d['unmapped_chapters'], ensure_ascii=False), len(d['unmapped_chapters'])))
L.append('')
L.append('## 五、未归属（空 knowledge_point）')
L.append('')
L.append('- 原因：%s' % d['unassigned']['reason'])
L.append('- 题量：c_wuhan %d / c_hbpu %d，合计 **%d** 题' % (
    d['unassigned']['rows']['c_wuhan.sqlite'], d['unassigned']['rows']['c_hbpu.sqlite'], d['unassigned']['total_rows']))
L.append('- 说明：%s' % d['unassigned']['note'])
L.append('')
L.append('## 六、复核方法')
L.append('')
L.append('```powershell')
L.append('& "$env:DSH_PY" tests\\verify_kb_mapping.py    # 见 tests/verify_kb_mapping.py，输出「未映射: 0」')
L.append('```')
L.append('')
open(os.path.join(ROOT,'subjects','c_common','knowledge_base.md'),'w',encoding='utf-8').write('\n'.join(L))

# ============================== English ==============================
d = json.load(open(os.path.join(ROOT,'subjects','english','knowledge_base.json'), encoding='utf-8'))
s = d['stats']
E = []
E.append('# 英语知识点体系（湖北专升本 + 河北对照）')
E.append('')
E.append('> 由 `tests/build_english_kb.py` 从 `data/english.sqlite` 只读生成，并引用 `inbox/english/` 素材；构建时间 %s。' % d['built_at'])
E.append('> 本文档与 `knowledge_base.json` 内容一致，JSON 为机器可读版本。')
E.append('')
E.append('## 一、为什么必须反推')
E.append('')
E.append('官方真题的 `knowledge_point` 字段几乎全空：')
E.append('')
E.append('| 项 | 值 |')
E.append('|---|---|')
E.append('| 题目总数 | %d |' % d['source']['questions'])
E.append('| 官方真题（trust_level=official_exam） | %d |' % d['source']['official_exam_questions'])
E.append('| knowledge_point 有值的行 | %d（只有 `%s`） |' % (
    d['source']['knowledge_point_field']['filled_rows'], '`, `'.join(d['source']['knowledge_point_field']['filled_values'])))
E.append('| knowledge_point 为空的行 | %d |' % d['source']['knowledge_point_field']['empty_rows'])
E.append('')
E.append('结论：%s' % d['source']['knowledge_point_field']['conclusion'])
E.append('')
E.append('官方真题卷别（%d 种）：' % len(d['source']['official_exam_titles']))
E.append('')
E.append('| 卷别 | 题数 | 地区/格式 |')
E.append('|---|---|---|')
for t, n in d['source']['official_exam_titles'].items():
    if t.startswith('河北'): region = '河北格式'
    elif any(x in t for x in ('2024','2025','2026')) and t.startswith('湖北') and '真题' not in t: region = '湖北·2024+ 新格式'
    elif t.startswith('湖北专升本') and '真题' in t: region = '湖北·单题补充'
    else: region = '湖北·2020–2023 老格式'
    E.append('| %s | %d | %s |' % (t, n, region))
E.append('')
E.append('## 二、两个维度')
E.append('')
for dim in d['dimensions']:
    E.append('- **%s**：%s' % (dim['name'], dim['desc']))
E.append('')
E.append('## 三、维度一 · 题型（%d 条）' % s['format_points'])
E.append('')
E.append('| ID | 题型 | 格式 | question_type | 题数 |')
E.append('|---|---|---|---|---|')
for k in d['knowledge_points']:
    if k['dimension'] != 'format': continue
    E.append('| `%s` | %s | %s | `%s` | %s |' % (
        k['id'], k['name'], ERA.get(k['format_era'], k['format_era']), k['question_type'],
        k['question_count'] if k['question_count'] is not None else '—'))
E.append('')
for k in d['knowledge_points']:
    if k['dimension'] != 'format': continue
    E.append('### %s %s' % (k['id'], k['name']))
    E.append('')
    E.append('- **格式**：%s' % ERA.get(k['format_era'], k['format_era']))
    E.append('- **说明**：%s' % k['desc'])
    E.append('- **题数**：%s（统计方式：%s）' % (
        k['question_count'] if k['question_count'] is not None else '—', k['count_basis']))
    if k.get('count_note'): E.append('- **口径**：%s' % k['count_note'])
    E.append('- **子考点**：%s' % '；'.join(k['sub_points']))
    E.append('- **真题依据**：%s' % k['evidence'])
    E.append('')
E.append('> 说明：`E-T04` 与 `E-T16` 共用 `reading_qa` 这个 question_type —— '
         '湖北 2024+ 是「用英语回答问题」（%d 题），河北是四选一（42 题，答案是选项字母）。'
         '两者之和 = `reading_qa` 总数 %d 题。'
         % (d['knowledge_points'][3]['question_count'], d['source']['question_type_distribution']['all']['reading_qa']))
E.append('')
E.append('### 数据质量注意（构建时实测，必须知道）')
E.append('')
for n in d['source'].get('data_quality_notes', []):
    E.append('- %s' % n)
E.append('')
E.append('## 四、维度二 · 语言知识（%d 条）' % s['knowledge_points'])
E.append('')
E.append('### 4.1 语法（%d 条）' % s['grammar_points'])
E.append('')
E.append('| ID | 语法点 | 标注题数 | 构成 |')
E.append('|---|---|---|---|')
for k in d['knowledge_points']:
    if k.get('category') != 'grammar': continue
    E.append('| `%s` | %s | %s | %s |' % (k['id'], k['name'],
        k['question_count'] if k['question_count'] else '—', '；'.join(k.get('tag_breakdown') or ['—'])))
E.append('')
for k in d['knowledge_points']:
    if k.get('category') != 'grammar': continue
    E.append('### %s %s' % (k['id'], k['name']))
    E.append('')
    E.append('- **说明**：%s' % k['desc'])
    E.append('- **标注题数**：%s（%s）' % (k['question_count'], k['count_basis']))
    E.append('- **真题原文依据**：')
    for ev in k['evidence']:
        E.append('  - %s' % ev)
    E.append('')
E.append('### 4.2 阅读（%d 条）' % s['reading_points'])
E.append('')
E.append('| ID | 技能 | 官方 reading_qa 中标注题数 | 占比 |')
E.append('|---|---|---|---|')
tot_rq = sum(v for k, v in [('', 0)] ) or sum(
    k['question_count'] for k in d['knowledge_points'] if k.get('category') == 'reading' and k['question_count'])
for k in d['knowledge_points']:
    if k.get('category') != 'reading': continue
    pct = ('%.1f%%' % (100.0 * k['question_count'] / tot_rq)) if k['question_count'] else '—'
    E.append('| `%s` | %s | %s | %s |' % (k['id'], k['name'], k['question_count'], pct))
E.append('')
for k in d['knowledge_points']:
    if k.get('category') != 'reading': continue
    E.append('### %s %s' % (k['id'], k['name']))
    E.append('')
    E.append('- **说明**：%s' % k['desc'])
    E.append('- **真题原文依据**：')
    for ev in k['evidence']:
        E.append('  - %s' % ev)
    E.append('')
E.append('### 4.3 翻译 / 写作 / 语音 / 交际 / 完形')
E.append('')
for k in d['knowledge_points']:
    if k.get('category') not in ('translation','writing','voice','dialogue','cloze'): continue
    E.append('#### %s %s' % (k['id'], k['name']))
    E.append('')
    E.append('- **说明**：%s' % k['desc'])
    if k['question_count']: E.append('- **题数**：%s' % k['question_count'])
    E.append('- **真题原文依据**：')
    for ev in k['evidence']:
        E.append('  - %s' % ev)
    E.append('')
E.append('## 五、question_type → 知识点 映射')
E.append('')
E.append('| question_type | 展示名 | 题数（全部） | 题数（官方真题） | 对应知识点 |')
E.append('|---|---|---|---|---|')
NAMES = {'grammar_fill':'语法填空','sentence_build':'连词成句','translation_fill':'翻译填空','reading_fill':'阅读填空',
 'reading_qa':'阅读理解','writing':'写作','sentence_completion':'完成句子','cloze':'完形填空','word_fill':'选词填空',
 'single_choice':'单选题','multiple_choice':'多选题','true_false':'判断题','phonetics':'语音题','dialogue':'情景对话',
 'translation_choice':'英译汉选择','translation':'翻译（英译汉）','outline_fill':'提纲填空','program_fill':'程序填空',
 'code_correction':'程序改错','programming':'编程题'}
for t, pts in d['question_type_to_points'].items():
    E.append('| `%s` | %s | %d | %d | %s |' % (
        t, NAMES.get(t, t),
        d['source']['question_type_distribution']['all'].get(t, 0),
        d['source']['question_type_distribution']['official_exam'].get(t, 0),
        '、'.join('`%s`' % p for p in pts)))
E.append('')
E.append('## 六、未映射')
E.append('')
E.append('`unmapped_chapters` = `%s`（共 **%d** 项）' % (json.dumps(d['unmapped_chapters'], ensure_ascii=False), len(d['unmapped_chapters'])))
E.append('')
E.append('全部 %d 个 `question_type` 均已映射到知识点：`%s`' % (
    s['question_types_total'], '`, `'.join(d['source']['question_type_coverage_check']['all_types'])))
E.append('')
E.append('## 七、统计口径与证据来源')
E.append('')
E.append('| 口径 | 说明 |')
E.append('|---|---|')
E.append('| `exact_sql` | 直接来自 SQL 计数，精确 |')
E.append('| `explicit_per_item_tag` | 逐题人工/规则标注后计数；单项选择题 103/103 全覆盖，语法填空 40/40 空全覆盖，阅读简答 240/240 全覆盖 |')
E.append('| `not_counted_individually` | 未单独计数（如完形填空的语境逻辑与词汇辨析，同一题可同时属两类） |')
E.append('')
E.append('| 证据来源 | 用途 |')
E.append('|---|---|')
m = d['source']['materials']
E.append('| `%s`（%s） | %s |' % (m['exam_guide']['path'], m['exam_guide']['origin'], m['exam_guide']['used_for']))
E.append('| `%s`（%s） | %s |' % (m['essay_review']['path'], m['essay_review']['origin'], m['essay_review']['used_for']))
E.append('| `%s` | %s |' % (m['raw_exam_json']['path'], m['raw_exam_json']['used_for']))
E.append('')
E.append('⚠️ %s' % d['source']['caveat'])
E.append('')
open(os.path.join(ROOT,'subjects','english','knowledge_base.md'),'w',encoding='utf-8').write('\n'.join(E))
print('md written: subjects/c_common/knowledge_base.md, subjects/english/knowledge_base.md')
