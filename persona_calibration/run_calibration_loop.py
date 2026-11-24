#!/usr/bin/env python3
"""
較正ループ試作: リスク回避 高/低 の個体を目標値に収束させ、判断への波及を検証する

工程（calibrate → validate）:
  1. calibrate: 強度の梯子（極めて/かなり/やや × 回避的/追求的、7段階）を調整ダイヤルに、
     新作リスク回避尺度（6項目・7件法）の得点を目標値（高=6.0±0.4, 低=2.0±0.4）に
     測定→調整→再測定で収束させる（各測定は6反復平均、最大4イテレーション）
  2. validate: 収束した2個体に判断課題を実施（各12反復）
     - 20事実分類 → 防御的分類数（W+T）
     - 固定戦略4本の優先順位づけ → WT順位・SO順位（リスク回避が高ければWT重視/SO軽視か）

使い方: python3 persona_calibration/run_calibration_loop.py --model sonnet --tag sonnet
出力: persona_calibration/results/calib_loop_<tag>/raw.json, summary.json
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

# 新作リスク回避尺度（6項目・オリジナル文面。dir=-1は逆転＝リスク追求）
RISK_ITEMS = [
    {"no": 1, "dir": +1, "text": "成功の見込みが五分五分の企画なら、見送る方に傾く"},
    {"no": 2, "dir": -1, "text": "前例のない施策こそ、先行者として試す価値があると思う"},
    {"no": 3, "dir": +1, "text": "大きなリターンの話を聞くと、まず裏にある落とし穴を探す"},
    {"no": 4, "dir": -1, "text": "多少の損失覚悟でも、当たれば大きい選択肢に賭けたい"},
    {"no": 5, "dir": +1, "text": "予算配分では、確実に回収できる案件を優先すべきだ"},
    {"no": 6, "dir": -1, "text": "リスクを取らないこと自体が最大のリスクだと感じる"},
]

# 強度の梯子: -3(極めて追求) 〜 +3(極めて回避)。0は中立（シェイピングなし）
LADDER = {
    +3: "あなたは極めて慎重で、極めてリスクを避け、不確実なことには極めて用心深く、損失の可能性を何よりも重視します。",
    +2: "あなたはかなり慎重で、かなりリスクを避け、不確実なことには用心深く、損失の可能性を重視します。",
    +1: "あなたはやや慎重で、どちらかといえばリスクを避け、不確実なことにはやや用心深い方です。",
     0: "",
    -1: "あなたはやや大胆で、どちらかといえばリスクを取ることを恐れず、不確実な機会にもやや積極的な方です。",
    -2: "あなたはかなり大胆で、リスクを取ることを恐れず、不確実な機会に積極的で、損失より機会を重視します。",
    -3: "あなたは極めて大胆で、極めてリスクを取ることを恐れず、不確実な機会に極めて積極的で、損失よりも機会を何よりも重視します。",
}

BASE = ("あなたはホンダの経営戦略討議に参加する中堅マネージャーです。\n{shaping}\n"
        "この性格は、あなたの考え方・感じ方・判断のすべてに反映されます。")

RATING_SCHEMA = {
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
RANK_SCHEMA = {
    "type": "object",
    "properties": {"rankings": {"type": "object", "properties": {
        "SO": {"type": "integer"}, "ST": {"type": "integer"},
        "WO": {"type": "integer"}, "WT": {"type": "integer"}},
        "required": ["SO", "ST", "WO", "WT"], "additionalProperties": False}},
    "required": ["rankings"], "additionalProperties": False
}


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


class Runner:
    def __init__(self, model, workers):
        self.model = model
        self.workers = workers
        self.cost = 0.0

    def batch(self, fn, args_list):
        out = []
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            futures = [ex.submit(fn, a) for a in args_list]
            for fu in as_completed(futures):
                try:
                    r, c = fu.result()
                    self.cost += c
                    out.append(r)
                except Exception as e:
                    print(f"  ERROR: {e}", file=sys.stderr)
        return out

    def measure_risk(self, pos, n_reps, seed_base):
        """梯子位置posの個体のリスク回避得点（n_reps平均）"""
        system = BASE.format(shaping=LADDER[pos])
        def one(rep):
            rng = random.Random(seed_base + rep)
            order = RISK_ITEMS[:]
            rng.shuffle(order)
            items = "\n".join(f"[項目{it['no']}] {it['text']}" for it in order)
            user = ("以下のそれぞれの記述が、あなた自身にどのくらいあてはまるかを、"
                    "1（全く違うと思う）〜7（強くそう思う）の7段階で評定してください。\n\n"
                    f"{items}\n\n全6項目について、item_noとrating（1〜7）を回答してください。")
            result, cost = call_llm(system, user, RATING_SCHEMA, self.model)
            ratings = {r["item_no"]: r["rating"] for r in result["ratings"]}
            vals = [(ratings[it["no"]] if it["dir"] > 0 else 8 - ratings[it["no"]])
                    for it in RISK_ITEMS if it["no"] in ratings]
            return sum(vals) / len(vals), cost
        scores = self.batch(one, list(range(n_reps)))
        return statistics.mean(scores), scores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--tag", default="sonnet")
    ap.add_argument("--measure-reps", type=int, default=6)
    ap.add_argument("--valid-reps", type=int, default=12)
    ap.add_argument("--max-workers", type=int, default=5)
    args = ap.parse_args()

    out_dir = OUT_ROOT / f"calib_loop_{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    R = Runner(args.model, args.max_workers)

    stim = json.loads((DATA_DIR / "persona_screening_stimuli.json").read_text(encoding="utf-8"))
    strategies = stim["check1b"]["strategies"]
    facts = json.loads((DATA_DIR / "facts.json").read_text(encoding="utf-8"))
    facts_text = "\n".join(
        f'[事実{f["fact_id"]}] {f["label"]}（{"内部要因" if f["internal"] else "外部要因"}）: {f["description"]}'
        for f in facts)

    # --- 1. calibrate: 目標値への収束ループ ---
    targets = {"high": (6.0, +2), "low": (2.0, -2)}   # (目標, 開始位置)
    tol = 0.4
    trajectories = {}
    final_pos = {}
    print(f"モデル: {describe_model(args.model)}")
    for name, (target, pos) in targets.items():
        traj = []
        for it in range(4):
            mean_score, scores = R.measure_risk(pos, args.measure_reps, seed_base=1000 * it)
            traj.append({"iteration": it, "position": pos, "ladder_text": LADDER[pos][:30],
                         "mean": round(mean_score, 2), "scores": [round(s, 2) for s in scores]})
            print(f"[{name}] iter{it}: 位置{pos:+d} → 得点{mean_score:.2f}（目標{target}±{tol}）")
            if abs(mean_score - target) <= tol:
                print(f"[{name}] 収束")
                break
            step = +1 if mean_score < target else -1
            new_pos = max(-3, min(3, pos + step))
            if new_pos == pos:
                print(f"[{name}] 梯子の端に到達（これ以上調整不可）")
                break
            pos = new_pos
        trajectories[name] = traj
        final_pos[name] = pos

    # --- 2. validate: 判断課題（分類 + 順位づけ） ---
    cross_text = "\n".join(f"  {k}: {strategies[k]}" for k in ["SO", "ST", "WO", "WT"])
    valid = {n: {"defensive": [], "WT_rank": [], "SO_rank": []} for n in targets}
    for name in targets:
        system = BASE.format(shaping=LADDER[final_pos[name]])

        def cls_one(rep):
            user = (f"{CASE_CONTEXT}\n\n【事実リスト】\n{facts_text}\n\n"
                    "上記の各事実を、2000年当時のホンダ二輪事業（ベトナム市場）にとっての\n"
                    "S（強み）/ W（弱み）/ O（機会）/ T（脅威）のいずれかに分類してください。")
            result, cost = call_llm(system, user, CLS_SCHEMA, self_model)
            cats = [c["category"] for c in result["classifications"]]
            return sum(1 for c in cats if c in ("W", "T")), cost

        def rank_one(rep):
            user = (f"{CASE_CONTEXT}\n\n【クロスSWOT戦略】\n{cross_text}\n\n"
                    "上記4つの戦略象限（SO/ST/WO/WT）について、2000年当時のホンダの状況を踏まえて、\n"
                    "優先順位を1（最優先）〜4（最後）でランキングしてください。")
            result, cost = call_llm(system, user, RANK_SCHEMA, self_model)
            return (result["rankings"]["WT"], result["rankings"]["SO"]), cost

        self_model = args.model
        defensive = R.batch(cls_one, list(range(args.valid_reps)))
        ranks = R.batch(rank_one, list(range(args.valid_reps)))
        valid[name]["defensive"] = defensive
        valid[name]["WT_rank"] = [r[0] for r in ranks]
        valid[name]["SO_rank"] = [r[1] for r in ranks]
        print(f"[{name}] validate: 防御的分類 平均{statistics.mean(defensive):.2f} / "
              f"WT順位 平均{statistics.mean(valid[name]['WT_rank']):.2f} / "
              f"SO順位 平均{statistics.mean(valid[name]['SO_rank']):.2f}")

    # --- 検定 ---
    tests = {}
    for key, better in [("defensive", "高いほどリスク回避的"), ("WT_rank", "小さいほどWT重視"),
                        ("SO_rank", "大きいほどSO軽視")]:
        U, z, p = mann_whitney(valid["high"][key], valid["low"][key])
        tests[key] = {"high_mean": round(statistics.mean(valid["high"][key]), 2),
                      "low_mean": round(statistics.mean(valid["low"][key]), 2),
                      "p": round(p, 5), "note": better}
        print(f"検定[{key}]: 高={tests[key]['high_mean']} vs 低={tests[key]['low_mean']} (p={p:.4f})")

    summary = {"_meta": {"model": args.model, "total_cost_usd": round(R.cost, 4),
                         "instrument": "新作リスク回避6項目・7件法", "targets": {k: v[0] for k, v in targets.items()},
                         "tolerance": tol},
               "trajectories": trajectories, "final_positions": final_pos,
               "validation_tests": tests,
               "validation_raw": valid}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n出力: {out_dir}/ (総コスト ${R.cost:.2f})")


if __name__ == "__main__":
    main()
