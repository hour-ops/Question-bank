import json, sqlite3, collections
from pathlib import Path
ROOT = Path(r"C:\Users\win11_vmusers\Documents\deepseek-harness\default-workspace\题库项目")
con = sqlite3.connect(f"file:{ROOT/'data'/'aca_llm.sqlite'}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
out = []
def P(s=""):
    out.append(str(s)); print(s)

P("## 全库 trust_level × status")
tot = 0
for r in con.execute("SELECT trust_level, status, count(*) n FROM questions GROUP BY 1,2 ORDER BY 1,2"):
    P(f"| {r['trust_level']} | {r['status']} | {r['n']} |")
    tot += r["n"]
P(f"合计 {tot}")
P()
P("## 本次 user_provided（217）")
for r in con.execute("SELECT trust_level, status, count(*) n FROM questions WHERE source_type='user_provided' GROUP BY 1,2 ORDER BY 1,2"):
    P(f"| {r['trust_level']} | {r['status']} | {r['n']} |")
P()
P("## 来源文件")
for r in con.execute("SELECT source_url, count(*) n FROM questions WHERE source_type='user_provided' GROUP BY 1 ORDER BY 1"):
    P(f"| {r['source_url']} | {r['n']} |")
P()
P("## ACA 知识点分布（168）")
for r in con.execute("SELECT knowledge_point kp, count(*) n FROM questions WHERE source_type='user_provided' AND trust_level='third_party' GROUP BY 1 ORDER BY 2 DESC"):
    P(f"| {r['kp']} | {r['n']} |")
P()
P("## ACP 主题分布（49）")
for r in con.execute("SELECT knowledge_point kp, count(*) n FROM questions WHERE source_type='user_provided' AND trust_level='acp' GROUP BY 1 ORDER BY 2 DESC"):
    P(f"| {r['kp']} | {r['n']} |")
P()
P("## 成本账本 stage=aca_acp_sort")
tot_cny, calls, errs, calls2 = 0.0, 0, 0, collections.Counter()
for line in (ROOT / "logs" / "cost_ledger.jsonl").read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    e = json.loads(line)
    if e.get("stage") != "aca_acp_sort":
        continue
    if e.get("kind") == "llm_call":
        calls += 1
        tot_cny += float(e.get("cost_cny") or 0)
        calls2[(e.get("note") or "").split()[0]] += 1
    else:
        errs += 1
P(f"LLM 调用 {calls} 次（分类 {calls2.get('batch',0)} 次 / 知识点指派 {calls2.get('kp',0)} 次），错误 {errs} 次，累计 ¥{tot_cny:.4f}")
con.close()
(ROOT / "logs" / "aca_acp_import_report.md").write_text("\n".join(out), encoding="utf-8")
