#!/usr/bin/env python3
"""
乖離実験: 性格シェイピングは「尺度得点」を動かすが「判断」を動かすか

問い（乖離）: 性格シェイピング（Serapio-García式の形容詞×強度修飾語）で自己申告尺度
（TIPI-J）の得点が動いても、経営判断（20事実のSWOT分類）まで分化するとは限らない。
自己申告と判断行動のそれぞれへの効果を同じ個体で測る。

設計: 中立の基底ペルソナ × {神経症傾向, 開放性} × {極高, 極低} の4セル × 12反復
  測定1: TIPI-J（10項目・項目順は反復ごとにランダム化）
  測定2: 20事実のS/W/O/T分類 → 防御的分類数（W+T）
  検定: セル間（高vs低）のMann-Whitney（正規近似）

使い方:
  python3 persona_calibration/run_dissociation.py --model "vllm:...@localhost:8000" --tag swallow70b
出力: persona_calibration/results/dissociation_<tag>/raw.json, summary.json
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

# TIPI-J items (Oshio, Abe & Cutrone 2012) are not redistributed here. Create
# persona_calibration/tipi_j_items.json from the original publication as a list of
# {"no": 1-10, "text": item, "trait": "外向性|協調性|誠実性|神経症傾向|開放性", "dir": +1|-1}.
TIPI_J_PATH = Path(__file__).parent / "tipi_j_items.json"
TIPI_J = []


def load_tipi_j():
    if not TIPI_J_PATH.exists():
        sys.exit(f"{TIPI_J_PATH} not found: TIPI-J items must be prepared from "
                 "Oshio, Abe & Cutrone (2012).")
    TIPI_J.extend(json.loads(TIPI_J_PATH.read_text(encoding="utf-8")))

# Serapio-García式シェイピング（形容詞リスト×強度修飾語「極めて」）
SHAPING = {
    ("神経症傾向", "high"): "あなたは極めて心配性で、極めて不安になりやすく、極めて動揺しやすく、極めて緊張しやすく、悲観的にものごとを考えがちです。",
    ("神経症傾向", "low"):  "あなたは極めて冷静で、極めて感情が安定しており、極めてリラックスしていて、めったに動揺せず、楽観的にものごとを考えます。",
    ("開放性", "high"): "あなたは極めて好奇心が強く、極めて想像力豊かで、極めて新しい経験を好み、極めて創造的で、型にとらわれない考え方をします。",
    ("開放性", "low"):  "あなたは極めて伝統を重んじ、極めて慣れたやり方を好み、極めて実際的で、想像よりも現実を重視し、変化を好みません。",
}

BASE_PERSONA = (
    "あなたはホンダの経営戦略討議に参加する中堅マネージャーです。\n{shaping}\n"
    "この性格は、あなたの考え方・感じ方・判断のすべてに反映されます。"
)

TIPI_SCHEMA = {
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


def tipi_score(ratings, trait):
    pair = [it for it in TIPI_J if it["trait"] == trait]
    vals = []
    for it in pair:
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
    load_tipi_j()

    facts = json.loads((DATA_DIR / "facts.json").read_text(encoding="utf-8"))
    facts_text = "\n".join(
        f'[事実{f["fact_id"]}] {f["label"]}（{"内部要因" if f["internal"] else "外部要因"}）: {f["description"]}'
        for f in facts)

    out_dir = OUT_ROOT / f"dissociation_{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    cells = list(SHAPING.keys())
    jobs = []
    for cell in cells:
        for rep in range(args.reps):
            jobs.append((cell, rep, "tipi"))
            jobs.append((cell, rep, "cls"))
    print(f"モデル: {describe_model(args.model)} / 4セル×{args.reps}反復×2測定 = {len(jobs)}呼び出し")

    def one(job):
        (trait, level), rep, measure = job
        system = BASE_PERSONA.format(shaping=SHAPING[(trait, level)])
        if measure == "tipi":
            rng = random.Random(hash((trait, level, rep)) % (2**31))
            order = TIPI_J[:]
            rng.shuffle(order)
            items = "\n".join(f"[項目{it['no']}] {it['text']}" for it in order)
            user = ("以下のそれぞれの記述が、あなた自身にどのくらいあてはまるかを、"
                    "1（全く違うと思う）〜7（強くそう思う）の7段階で評定してください。\n\n"
                    f"{items}\n\n全10項目について、item_noとrating（1〜7）を回答してください。")
            result, cost = call_llm(system, user, TIPI_SCHEMA, args.model)
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
                (cell, rep, measure), payload, cost = fu.result()
                total_cost += cost
                raw.append({"trait": cell[0], "level": cell[1], "rep": rep,
                            "measure": measure, **payload})
                print(f"  {cell[0]}-{cell[1]} rep{rep} [{measure}] done")
            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)

    (out_dir / "raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    # 集計
    summary = {"_meta": {"model": args.model, "reps": args.reps, "total_cost_usd": round(total_cost, 4)},
               "cells": {}}
    print("\n=== 乖離検定 ===")
    for trait in ["神経症傾向", "開放性"]:
        res = {}
        for level in ["high", "low"]:
            tipi_vals = [tipi_score(r["ratings"], trait) for r in raw
                         if r["measure"] == "tipi" and r["trait"] == trait and r["level"] == level
                         and tipi_score(r["ratings"], trait) is not None]
            def_counts = [sum(1 for c in r["cats"].values() if c in ("W", "T")) for r in raw
                          if r["measure"] == "cls" and r["trait"] == trait and r["level"] == level]
            res[level] = {"tipi": tipi_vals, "defensive": def_counts}
        U1, z1, p1 = mann_whitney(res["high"]["tipi"], res["low"]["tipi"])
        U2, z2, p2 = mann_whitney(res["high"]["defensive"], res["low"]["defensive"])
        d_tipi = (statistics.mean(res["high"]["tipi"]) - statistics.mean(res["low"]["tipi"]))
        d_def = (statistics.mean(res["high"]["defensive"]) - statistics.mean(res["low"]["defensive"]))
        summary["cells"][trait] = {
            "tipi_high_mean": round(statistics.mean(res["high"]["tipi"]), 2),
            "tipi_low_mean": round(statistics.mean(res["low"]["tipi"]), 2),
            "tipi_shift": round(d_tipi, 2), "tipi_p": round(p1, 5),
            "defensive_high_mean": round(statistics.mean(res["high"]["defensive"]), 2),
            "defensive_low_mean": round(statistics.mean(res["low"]["defensive"]), 2),
            "defensive_shift": round(d_def, 2), "defensive_p": round(p2, 5),
        }
        print(f"{trait}: TIPI {statistics.mean(res['low']['tipi']):.1f}→"
              f"{statistics.mean(res['high']['tipi']):.1f} (Δ={d_tipi:+.1f}, p={p1:.4f}) | "
              f"防御的分類 {statistics.mean(res['low']['defensive']):.1f}→"
              f"{statistics.mean(res['high']['defensive']):.1f} (Δ={d_def:+.1f}, p={p2:.4f})")

    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n出力: {out_dir}/ (総コスト ${total_cost:.2f})")


if __name__ == "__main__":
    main()
