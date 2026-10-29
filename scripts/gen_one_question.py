"""补一道指定的题（考点+题型），用于把配比凑齐。复用 generate_mock_paper 的 RAG 与校验。

用法:
    python scripts/gen_one_question.py --module 安全合规 --type multiple_choice --count 1 --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import generate_mock_paper as g  # noqa: E402

MODMAP = {"大模型概念": 1, "提示词工程": 2, "增强大模型应用的能力": 3,
          "大模型微调": 4, "大模型 Agent": 5, "安全合规": 6}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", required=True)
    ap.add_argument("--type", default="multiple_choice")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--exam", default="AI补题·凑配比")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    mod = next(m for m in g.MODULES if m["label"] == args.module)
    qtype_cn = "多选" if args.type == "multiple_choice" else "单选"
    fine = g.load_fine_points().get(mod["no"]) or [("", mod["label"], "")]
    guides = g.GuideCache()
    s_single, s_multi = g.fetch_samples()

    from openai import OpenAI
    env = g.load_env()
    client = OpenAI(api_key=env["DEEPSEEK_API_KEY"],
                    base_url=env.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com", timeout=180)

    made = []
    for i in range(args.count):
        fp = fine[i % len(fine)]
        ctx = g.rag_context(f"{mod['label']} {fp[1]} {qtype_cn}", k=2)
        user = g.build_prompt(args.exam, i + 1, args.count, mod["label"], mod["pct"], fp,
                              qtype_cn, args.count, g.INDUSTRIES[i % len(g.INDUSTRIES)],
                              guides.get(mod["guide"]), ctx,
                              s_multi if qtype_cn == "多选" else s_single, "",
                              "AB" if qtype_cn == "多选" else "A", mod["no"])
        for attempt in range(3):
            q, usage = g.call(client, g.MODEL_DEFAULT, "none", user)
            good, why = g.validate(q, args.type)
            if good:
                made.append((q, fp))
                print(f"  ✓ {mod['label']}/{qtype_cn} {fp[0]}（{attempt + 1} 次）")
                break
            print(f"  ✗ {why}")

    if not made:
        print("没生成出来")
        return 1
    if not args.apply:
        print("dry-run：未写库")
        return 0

    db = g.DATA / f"{g.SUBJECT}.sqlite"
    con = sqlite3.connect(str(db))
    cols = [c[1] for c in con.execute("PRAGMA table_info(questions)")]
    try:
        for q, fp in made:
            stem = str(q["stem"]).strip()
            opts = [{"key": o.strip()[0], "text": re.sub(r"^[A-H]\s*[.、)．]\s*", "", o.strip())}
                    for o in q["options"]]
            ans = "".join(sorted(set(re.sub(r"[^A-H]", "", str(q["answer"]).upper()))))
            row = {
                "question_uid": f"ai-fill-{uuid.uuid4().hex[:12]}", "subject": g.SUBJECT,
                "source_type": "generate", "source_url": "AI生成-KB增强",
                "source_credit": f"{args.exam}（为凑齐考点配比补题）",
                "knowledge_point": f"考点·{mod['label']}",
                "chapter": f"{mod['label']}·AI补题",
                "question_type": args.type, "stem": stem,
                "options": json.dumps(opts, ensure_ascii=False), "answer": ans,
                "explanation": str(q["explanation"]).strip(),
                "difficulty": "中", "status": "approved", "trust_level": "ai_generated",
                "fact_source": "AI 生成", "exam_title": args.exam, "version": 1,
            }
            row = {k: v for k, v in row.items() if k in cols}
            con.execute(f"INSERT INTO questions ({','.join(row)}) VALUES ({','.join('?' * len(row))})",
                        tuple(row.values()))
        con.commit()
    finally:
        con.close()
    print(f"已入库 {len(made)} 题 → {args.exam}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
