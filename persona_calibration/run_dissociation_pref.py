#!/usr/bin/env python3
"""
乖離実験（選好版: 選好→事実認定）

run_dissociation.py（性格→事実認定）の姉妹版。
シェイピング属性を「性格（神経症傾向・開放性）」から「選好（リスク回避）」に差し替えた。

問い: 設定した選好（リスク回避）は、事実認定（SWOT分類）に反映されるか。
  - 反映される  = リスク回避的な個体ほど防御的分類（W+T）が増える
  - 反映されない = リスク回避を極端に振っても事実の分類は変わらない

設計: 中立の基底ペルソナ × リスク回避{極高(+3), 極低(-3)} × reps反復
  測定1: 新作リスク回避尺度（6項目・7件法。自己申告が動くかの確認）
  測定2: 20事実のS/W/O/T分類 → 防御的分類数（W+T）
  検定: 高vs低のMann-Whitney（正規近似）

使い方: python3 persona_calibration/run_dissociation_pref.py --model sonnet --tag sonnet
出力: persona_calibration/results/dissociation_pref_<tag>/raw.json, summary.json
"""

import argparse
import json
import math
import random
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))
from llm_backend import call_llm, describe_model
from simulation_data import CASE_CONTEXT

DATA_DIR = SCRIPT_DIR / "simulation" / "data"
OUT_ROOT = Path(__file__).parent / "results"

# 新作リスク回避尺度（dir=-1は逆転＝リスク追求）
RISK_SCALE = [
    {"no": 1, "dir": +1, "text": "不確実な結果になるくらいなら、確実で堅実な選択をしたい"},
    {"no": 2, "dir": +1, "text": "大きな損失を避けることは、大きな利益を得ることより重要だ"},
    {"no": 3, "dir": -1, "text": "好機と見れば、多少のリスクは進んで引き受ける"},
    {"no": 4, "dir": +1, "text": "決断の前には、最悪の事態を十分に想定しておきたい"},
    {"no": 5, "dir": -1, "text": "現状維持よりも、大胆な挑戦のほうが性に合っている"},
    {"no": 6, "dir": -1, "text": "リスクを取らないこと自体が最大のリスクだと感じる"},
]

SHAPING = {
    "high": "あなたは極めて慎重で、極めてリスクを避け、不確実なことには極めて用心深く、損失の可能性を何よりも重視します。",
    "low":  "あなたは極めて大胆で、極めてリスクを取ることを恐れず、不確実な機会に極めて積極的で、損失よりも機会を何よりも重視します。",
}

BASE_PERSONA = (
    "あなたはホンダの経営戦略討議に参加する中堅マネージャーです。\n{shaping}\n"
    "この選好は、あなたの考え方・感じ方・判断のすべてに反映されます。"
)

SCALE_SCHEMA = {
    "type": "object",
    "properties": {"ratings": {"type": "array", "items": {
        "type": "object",
        "properties": {"item_no": {"type": "integer"}, "rating": {"type": "integer"}},
        "required": ["item_no", "rating"], "additionalProperties": False}}},
    "required": ["ratings"], "additionalProperties": False
}

CLS_SCHEMA = {
    "type": "object",
    "properties": {"classifications": {"type": "array", "items": {
        "type": "object",
        "properties": {"fact_id": {"type": "integer"},
                       "category": {"type": "string", "enum": ["S", "W", "O", "T"]}},
        "required": ["fact_id", "category"], "additionalProperties": False}}},
    "required": ["classifications"], "additionalProperties": False
}


def scale_score(ratings):
    vals = []
    for it in RISK_SCALE:
        r = ratings.get(it["no"])
        if r is not None:
            vals.append(r if it["dir"] > 0 else 8 - r)
    return sum(vals) / len(vals) if vals else None


def mann_whitney(x, y):
    n1, n2 = len(x), len(y)
    allv = sorted(x + y)
    def rank(v):
        lo = sum(1 for a in allv if a < v); hi = sum(1 for a in allv if a <= v)
        return (lo + hi + 1) / 2
    U = sum(rank(v) for v in x) - n1 * (n1 + 1) / 2
    mu = n1 * n2 / 2
    sd = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    z = (U - mu) / sd if sd else 0
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return U, z, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--reps", type=int, default=12)
    ap.add_argument("--max-workers", type=int, default=5)
    args = ap.parse_args()

    facts = json.loads((DATA_DIR / "facts.json").read_text(encoding="utf-8"))
    facts_text = "\n".join(
        f'[事実{f["fact_id"]}] {f["label"]}（{"内部要因" if f["internal"] else "外部要因"}）: {f["description"]}'
        for f in facts)

    out_dir = OUT_ROOT / f"dissociation_pref_{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs = []
    for level in ["high", "low"]:
        for rep in range(args.reps):
            jobs.append((level, rep, "scale"))
            jobs.append((level, rep, "cls"))
    print(f"モデル: {describe_model(args.model)} / 2セル×{args.reps}反復×2測定 = {len(jobs)}呼び出し")

    def one(job):
        level, rep, measure = job
        system = BASE_PERSONA.format(shaping=SHAPING[level])
        if measure == "scale":
            rng = random.Random(hash((level, rep)) % (2**31))
            order = RISK_SCALE[:]
            rng.shuffle(order)
            items = "\n".join(f"[項目{it['no']}] {it['text']}" for it in order)
            user = ("以下のそれぞれの記述が、あなた自身にどのくらいあてはまるかを、"
                    "1（全く違うと思う）〜7（強くそう思う）の7段階で評定してください。\n\n"
                    f"{items}\n\n全6項目について、item_noとrating（1〜7）を回答してください。")
            result, cost = call_llm(system, user, SCALE_SCHEMA, args.model)
            ratings = {r["item_no"]: r["rating"] for r in result["ratings"]}
            return job, {"ratings": ratings}, cost
        else:
            user = (f"{CASE_CONTEXT}\n\n【事実リスト】\n{facts_text}\n\n"
                    "上記の各事実を、2000年当時のホンダ二輪事業（ベトナム市場）にとっての\n"
                    "S（強み）/ W（弱み）/ O（機会）/ T（脅威）のいずれかに分類してください。")
            result, cost = call_llm(system, user, CLS_SCHEMA, args.model)
            cats = {c["fact_id"]: c["category"] for c in result["classifications"]}
            return job, {"cats": cats}, cost

    raw = []
    total_cost = 0
    with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futures = [ex.submit(one, j) for j in jobs]
        for fu in as_completed(futures):
            try:
                (level, rep, measure), payload, cost = fu.result()
                total_cost += cost
                raw.append({"level": level, "rep": rep, "measure": measure, **payload})
                print(f"  リスク回避-{level} rep{rep} [{measure}] done")
            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)

    (out_dir / "raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    res = {}
    for level in ["high", "low"]:
        scale_vals = [scale_score(r["ratings"]) for r in raw
                      if r["measure"] == "scale" and r["level"] == level
                      and scale_score(r["ratings"]) is not None]
        def_counts = [sum(1 for c in r["cats"].values() if c in ("W", "T")) for r in raw
                      if r["measure"] == "cls" and r["level"] == level]
        res[level] = {"scale": scale_vals, "defensive": def_counts}
    U1, z1, p1 = mann_whitney(res["high"]["scale"], res["low"]["scale"])
    U2, z2, p2 = mann_whitney(res["high"]["defensive"], res["low"]["defensive"])
    d_scale = statistics.mean(res["high"]["scale"]) - statistics.mean(res["low"]["scale"])
    d_def = statistics.mean(res["high"]["defensive"]) - statistics.mean(res["low"]["defensive"])
    summary = {
        "_meta": {"model": args.model, "reps": args.reps, "attribute": "リスク回避（選好）",
                  "total_cost_usd": round(total_cost, 4)},
        "cells": {"リスク回避": {
            "scale_high_mean": round(statistics.mean(res["high"]["scale"]), 2),
            "scale_low_mean": round(statistics.mean(res["low"]["scale"]), 2),
            "scale_shift": round(d_scale, 2), "scale_p": round(p1, 5),
            "defensive_high_mean": round(statistics.mean(res["high"]["defensive"]), 2),
            "defensive_low_mean": round(statistics.mean(res["low"]["defensive"]), 2),
            "defensive_shift": round(d_def, 2), "defensive_p": round(p2, 5),
        }}}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 乖離検定（選好→事実認定・⑤セル）===")
    print(f"リスク回避: 自己申告 {statistics.mean(res['low']['scale']):.1f}→"
          f"{statistics.mean(res['high']['scale']):.1f} (Δ={d_scale:+.1f}, p={p1:.4f}) | "
          f"防御的分類 {statistics.mean(res['low']['defensive']):.1f}→"
          f"{statistics.mean(res['high']['defensive']):.1f} (Δ={d_def:+.1f}, p={p2:.4f})")
    print(f"出力: {out_dir}/ (総コスト ${total_cost:.2f})")


if __name__ == "__main__":
    main()
