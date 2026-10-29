# -*- coding: utf-8 -*-
"""映射率自证脚本：证明所有原始章节名/题型都能在知识库的 alias 里找到。

用法：
  python tests/verify_kb_mapping.py

输出（关键行）：
  未映射: 0
"""
import sqlite3, json, os, sys, io, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def ro(p): return sqlite3.connect('file:%s?mode=ro' % p.replace('\\','/'), uri=True)

fail = 0
print('=' * 78)
print('C 语言：原始章节名 → alias_chapters 映射率')
print('=' * 78)
kb = json.load(open(os.path.join(ROOT, 'subjects', 'c_common', 'knowledge_base.json'), encoding='utf-8'))
alias2kp = {}
for k in kb['knowledge_points']:
    for a in k['alias_chapters']:
        assert a not in alias2kp, '重复 alias: %s' % a
        alias2kp[a] = k['id']

raw = collections.Counter(); empty = 0
for db in ['c_wuhan.sqlite', 'c_hbpu.sqlite']:
    con = ro(os.path.join(ROOT, 'data', db)); cur = con.cursor()
    cur.execute("SELECT knowledge_point, COUNT(*) FROM questions GROUP BY knowledge_point")
    for kp, n in cur.fetchall():
        if kp is None or not str(kp).strip(): empty += n
        else: raw[kp] += n
    con.close()

missing = sorted([n for n in raw if n not in alias2kp], key=lambda x: -raw[x])
covered_q = sum(raw[n] for n in raw if n in alias2kp)
print('SQL: SELECT DISTINCT knowledge_point FROM questions  (c_wuhan.sqlite UNION c_hbpu.sqlite)')
print('  - 原始章节名（去重，非空） : %d' % len(raw))
print('  - 能在 alias_chapters 找到 : %d' % (len(raw) - len(missing)))
print('  - 空串（非章节名，单列）   : %d 题' % empty)
print('  - 已映射题数 / 命名题数    : %d / %d' % (covered_q, sum(raw.values())))
if missing:
    fail = 1
    print('  ✗ 未映射的章节名：')
    for m in missing: print('      %5d  %s' % (raw[m], m))
print()
print('未映射: %d' % len(missing))
print()

print('=' * 78)
print('英语：question_type → 知识点 映射率')
print('=' * 78)
ke = json.load(open(os.path.join(ROOT, 'subjects', 'english', 'knowledge_base.json'), encoding='utf-8'))
con = ro(os.path.join(ROOT, 'data', 'english.sqlite')); cur = con.cursor()
cur.execute("SELECT question_type, COUNT(*) FROM questions GROUP BY question_type")
types = collections.Counter(dict(cur.fetchall()))
kpf = cur.execute("SELECT COUNT(*) FROM questions WHERE TRIM(COALESCE(knowledge_point,''))<>''").fetchone()[0]
kpe = cur.execute("SELECT COUNT(*) FROM questions WHERE TRIM(COALESCE(knowledge_point,''))=''").fetchone()[0]
con.close()
mapped = set(ke['question_type_to_points'])
for k in ke['knowledge_points']:
    if k.get('question_type'): mapped.add(k['question_type'])
missing_e = sorted(t for t in types if t not in mapped)
print('SQL: SELECT DISTINCT question_type FROM questions  (english.sqlite)')
print('  - 原始题型（去重）  : %d  合计 %d 题' % (len(types), sum(types.values())))
print('  - 能在知识点表找到  : %d' % (len(types) - len(missing_e)))
print('  - knowledge_point 字段有值 / 为空 : %d / %d' % (kpf, kpe))
if missing_e:
    fail = 1
    print('  ✗ 未映射的题型：%s' % missing_e)
print()
print('未映射: %d' % len(missing_e))
print()
print('=' * 78)
print('总判定: %s' % ('PASS —— 未映射: 0' if not fail else 'FAIL —— 存在未映射项'))
print('=' * 78)
sys.exit(fail)
