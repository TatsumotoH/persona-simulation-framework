#!/usr/bin/env python3
"""
汎用ペルソナ法則テスト（Test 2: Persona Nomological Test）

属性を高低（ジェンダーは3条件）に振り、次の3つを測る。
  ① 自己申告尺度      … 操作が効いたかの確認（尺度の可動域）
  ② 事実分類          … **曖昧事実／確定事実を分けて**防御的分類数を集計
  ③ 4戦略の順位づけ    … 価値判断側への波及

規範（二層化）:
  - 曖昧事実（正解基準なし）への影響 … **記述的忠実性**の基準。動いてよい
  - 確定事実（一義的）への影響       … **規範的正確性**の基準。動くべきでない
  - 優先順位への影響                 … 全属性で動いてよい

persona_calibration/ の乖離テスト（run_dissociation.py / run_dissociation_pref.py）との違いは、
事実を曖昧/確定に分けて集計する点と、7属性を1本で回す点。

使い方:
  python3 run_law_generic.py --model sonnet --tag sakura_sonnet                    # ケース1
  python3 run_law_generic.py --model sonnet --tag honda_sonnet  --case honda        # ケース2
  python3 run_law_generic.py --model sonnet --tag sonnet --attrs overconfidence,gender
出力: persona_generic/results/law_<tag>/{raw.json, summary.json}

**--case はケースパックを切り替える。**会社名・ケース記述・事実・4戦略のすべてが
ケースパック側から来るので、スクリプトに固有名詞を書かない。
"""

import argparse, json, math, random, statistics, sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from llm_backend import call_llm, describe_model

GDIR = ROOT / "persona_generic"
QUADS = ["SO", "ST", "WO", "WT"]

# ケースごとの部品。増やすときはここに1行足す。
CASES = {
    "sakura": {"pack": "case_pack_v1.json",       "stim": "persona_check_sakura_v1.json"},
    "honda":  {"pack": "case_pack_honda_v1.json", "stim": "persona_check_honda_v1.json"},
}

# 会社名はケースパックの base_persona / subject から受け取る。既定はサクラ（後方互換）。
_BASE_DEFAULT = "あなたはサクラ食品株式会社の経営戦略の討議に参加する中堅マネージャーです。"
_CLASSIFY_DEFAULT = "サクラ食品にとっての"
PERSONA_TMPL = ("{base}\n{shaping}\n"
                "この特徴は、あなたの考え方・感じ方・判断のすべてに反映されます。")

SCALE_SCHEMA = {"type": "object", "properties": {"ratings": {"type": "array", "items": {
    "type": "object", "properties": {"item_no": {"type": "integer"}, "rating": {"type": "integer"}},
    "required": ["item_no", "rating"], "additionalProperties": False}}},
    "required": ["ratings"], "additionalProperties": False}

JUDGE_SCHEMA = {"type": "object", "properties": {
    "classifications": {"type": "array", "items": {"type": "object", "properties": {
        "fact_id": {"type": "integer"},
        "category": {"type": "string", "enum": ["S", "W", "O", "T"]}},
        "required": ["fact_id", "category"], "additionalProperties": False}},
    "ranking": {"type": "array", "items": {"type": "string", "enum": QUADS},
                "minItems": 4, "maxItems": 4}},
    "required": ["classifications", "ranking"], "additionalProperties": False}


def mann_whitney(x, y):
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        return None
    allv = sorted(x + y)
    def rank(v):
        lo = sum(1 for a in allv if a < v); hi = sum(1 for a in allv if a <= v)
        return (lo + hi + 1) / 2
    U = sum(rank(v) for v in x) - n1 * (n1 + 1) / 2
    mu = n1 * n2 / 2
    sd = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    if sd == 0:
        return 1.0
    z = (U - mu) / sd
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


def scale_score(items, ratings):
    vals = [r if it["dir"] > 0 else 8 - r
            for it in items if (r := ratings.get(it["no"])) is not None]
    return statistics.mean(vals) if vals else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--tag", default="sonnet")
    ap.add_argument("--reps", type=int, default=12)
    ap.add_argument("--attrs", default=None, help="カンマ区切り。省略で全属性")
    ap.add_argument("--case", default="sakura", choices=sorted(CASES),
                    help="ケースパック。sakura=ケース1（サクラ食品）、honda=ケース2（ホンダ二輪ASEAN）")
    ap.add_argument("--max-workers", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    attrs = json.loads((GDIR / "data" / "attributes_v1.json").read_text(encoding="utf-8"))
    cfg = CASES[args.case]
    pack = json.loads((GDIR / "data" / cfg["pack"]).read_text(encoding="utf-8"))
    stim = json.loads((GDIR / "data" / cfg["stim"]).read_text(encoding="utf-8"))
    base_persona = pack.get("base_persona", _BASE_DEFAULT)
    classify_subject = (pack.get("subject") or {}).get("classify", _CLASSIFY_DEFAULT)
    # 黙って別会社の名前で回さない。ケースパックに指定がなければ必ず知らせる。
    if not pack.get("base_persona") or not (pack.get("subject") or {}).get("classify"):
        print(f"[警告] ケースパック {cfg['pack']} に base_persona / subject.classify がありません。"
              f"既定（サクラ食品）を使います——別のケースなら誤りです", file=sys.stderr)

    AMB = [f["fact_id"] for f in pack["facts"] if f["ambiguity"] == "ambiguous"]
    DET = [f["fact_id"] for f in pack["facts"] if f["ambiguity"] == "determinate"]
    facts_text = "\n".join(f'[事実{f["fact_id"]}] {f["label"]}: {f["description"]}'
                           for f in pack["facts"])
    strat_text = "\n\n".join(f'[{q}] {stim["check1b"]["strategies"][q]}' for q in QUADS)

    names = [k for k in attrs if not k.startswith("_")]
    if args.attrs:
        names = [a.strip() for a in args.attrs.split(",")]
    names = [n for n in names if attrs[n].get("shaping") and n != "role"]

    judge_user = (
        f"{pack['case_context']}\n\n【事実リスト】\n{facts_text}\n\n"
        f"上記の各事実を、{classify_subject}S（強み）/ W（弱み）/ O（機会）/ T（脅威）の\n"
        "いずれかに分類してください。\n\n"
        f"【4つの基本戦略】\n{strat_text}\n\n"
        "続いて、この4つの戦略を、あなたが優先すべきと考える順に ranking に並べてください。"
    )

    jobs = []
    for a in names:
        for lv in attrs[a]["shaping"]:
            for rep in range(args.reps):
                if attrs[a].get("scale"):
                    jobs.append((a, lv, rep, "scale"))
                jobs.append((a, lv, rep, "judge"))

    print(f"ケース: {args.case}（{cfg['pack']}）")
    print(f"モデル: {describe_model(args.model)}")
    print(f"属性 {len(names)}件: {', '.join(names)}")
    print(f"曖昧事実 {AMB} / 確定事実 {DET}")
    print(f"呼び出し数: {len(jobs)}")
    if args.dry_run:
        print(f"\n[dry-run] 判断プロンプト長: {len(judge_user)}字")
        print(f"[dry-run] シェイピング例（{names[0]}/{list(attrs[names[0]]['shaping'])[0]}）:")
        print("  " + PERSONA_TMPL.format(
            base=base_persona,
            shaping=attrs[names[0]]["shaping"][list(attrs[names[0]]["shaping"])[0]]).replace("\n", "\n  "))
        print(f"\n[dry-run] 分類の対象: 「{classify_subject}S/W/O/T」")
        return

    out_dir = GDIR / "results" / f"law_{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    def one(job):
        a, lv, rep, kind = job
        system = PERSONA_TMPL.format(base=base_persona, shaping=attrs[a]["shaping"][lv])
        if kind == "scale":
            items = attrs[a]["scale"]
            rng = random.Random(hash((a, lv, rep)) % (2**31))
            order = items[:]; rng.shuffle(order)
            txt = "\n".join(f"[項目{it['no']}] {it['text']}" for it in order)
            user = ("以下のそれぞれの記述が、あなた自身にどのくらいあてはまるかを、"
                    "1（全く違うと思う）〜7（強くそう思う）の7段階で評定してください。\n\n"
                    f"{txt}\n\n全項目について、item_noとrating（1〜7）を回答してください。")
            r, c = call_llm(system, user, SCALE_SCHEMA, args.model)
            return job, {"ratings": {x["item_no"]: x["rating"] for x in r["ratings"]}}, c
        r, c = call_llm(system, judge_user, JUDGE_SCHEMA, args.model)
        return job, {"cats": {x["fact_id"]: x["category"] for x in r["classifications"]},
                     "ranking": r["ranking"]}, c

    raw, total = [], 0.0
    with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futs = [ex.submit(one, j) for j in jobs]
        done = 0
        for fu in as_completed(futs):
            try:
                (a, lv, rep, kind), payload, c = fu.result()
                total += c; done += 1
                raw.append({"attr": a, "level": lv, "rep": rep, "kind": kind, **payload})
                if done % 20 == 0:
                    print(f"  {done}/{len(jobs)} 完了")
            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)
    (out_dir / "raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 集計 ----
    summary = {"_meta": {"model": args.model, "case": args.case,
                         "case_pack": cfg["pack"], "reps": args.reps,
                         "ambiguous_facts": AMB, "determinate_facts": DET,
                         "total_cost_usd": round(total, 4)}, "attributes": {}}
    for a in names:
        levels = list(attrs[a]["shaping"])
        cell = defaultdict(lambda: defaultdict(list))
        for r in raw:
            if r["attr"] != a:
                continue
            if r["kind"] == "scale":
                s = scale_score(attrs[a]["scale"], r["ratings"])
                if s is not None:
                    cell[r["level"]]["scale"].append(s)
            else:
                cats = {int(k): v for k, v in r["cats"].items()}
                cell[r["level"]]["def_amb"].append(sum(1 for f in AMB if cats.get(f) in ("W", "T")))
                cell[r["level"]]["def_det"].append(sum(1 for f in DET if cats.get(f) in ("W", "T")))
                for q in QUADS:
                    cell[r["level"]][f"rank_{q}"].append(r["ranking"].index(q) + 1)
        res = {"levels": levels, "measures": {}}
        hi, lo = levels[0], levels[-1]
        for m in ["scale", "def_amb", "def_det"] + [f"rank_{q}" for q in QUADS]:
            x, y = cell[hi].get(m, []), cell[lo].get(m, [])
            if not x or not y:
                continue
            res["measures"][m] = {
                f"{hi}_mean": round(statistics.mean(x), 2),
                f"{lo}_mean": round(statistics.mean(y), 2),
                "p": round(mann_whitney(x, y), 5)}
        summary["attributes"][a] = res
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== 法則テスト（{args.tag}）===")
    print(f"{'属性':20s} {'尺度':>16s} {'曖昧事実':>16s} {'確定事実':>16s} {'WT順位':>16s}")
    for a, v in summary["attributes"].items():
        M = v["measures"]; lv = v["levels"]; hi, lo = lv[0], lv[-1]
        def f(m):
            d = M.get(m)
            if not d: return "—"
            s = "*" if d["p"] < 0.05 else " "
            return f'{d[f"{lo}_mean"]:.1f}→{d[f"{hi}_mean"]:.1f} p={d["p"]:.3f}{s}'
        print(f"{attrs[a]['label'][:18]:20s} {f('scale'):>16s} {f('def_amb'):>16s} "
              f"{f('def_det'):>16s} {f('rank_WT'):>16s}")
    print(f"\n出力: {out_dir}/ (総コスト ${total:.2f})")


if __name__ == "__main__":
    main()
