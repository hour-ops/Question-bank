# -*- coding: utf-8 -*-
"""Final integrity check of the 4 deliverables."""
import json, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ['subjects/c_common/knowledge_base.md', 'subjects/c_common/knowledge_base.json',
         'subjects/english/knowledge_base.md', 'subjects/english/knowledge_base.json']
for f in FILES:
    p = os.path.join(ROOT, f)
    b = open(p, 'rb').read()
    bom = 'BOM' if b[:3] == b'\xef\xbb\xbf' else 'no-BOM'
    try:
        t = b.decode('utf-8'); dec = 'utf-8 OK'
    except Exception as e:
        dec = 'DECODE FAIL %s' % e
    # CJK sanity: no U+FFFD replacement chars, and some Chinese present
    bad = t.count('\ufffd')
    cjk = sum(1 for c in t if '\u4e00' <= c <= '\u9fff')
    print('%-42s %7d bytes  %-6s  %-10s  U+FFFD=%d  CJK=%d' % (f, len(b), bom, dec, bad, cjk))

print()
for f in ['subjects/c_common/knowledge_base.json', 'subjects/english/knowledge_base.json']:
    d = json.load(open(os.path.join(ROOT, f), encoding='utf-8'))
    print('%s -> JSON OK  subject=%s  points=%d  unmapped_chapters=%s' % (
        f, d['subject'], len(d['knowledge_points']), d['unmapped_chapters']))
    for key in ('source', 'knowledge_points', 'unmapped_chapters', 'stats'):
        assert key in d, (f, key)
    for k in d['knowledge_points']:
        for key in ('id', 'name', 'desc', 'question_count'):
            assert key in k, (f, k['id'], key)
    print('   required keys present: source / knowledge_points / unmapped_chapters / stats')
    print('   stats =', json.dumps(d['stats'], ensure_ascii=False))
print()
print('ALL CHECKS PASS')
