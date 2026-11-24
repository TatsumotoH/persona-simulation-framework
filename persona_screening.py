#!/usr/bin/env python3
"""
ペルソナ操作チェック・スクリーニング

フル・シミュレーション（20ラン）を走らせる前に、モデルが
  チェック1: ペルソナが判断に表出するか（①ペルソナ崩壊の簡易診断）
  チェック2: ペルソナを基準に、論拠に応じて意見が適度に動くか（②信念更新不全の簡易診断）
を短い設問数（既定: 8ペルソナ・約60呼び出し・10分程度）でテストする。

設計のポイント:
- 討議相手を本物のエージェントではなく台本化した刺激に置き換える
  → 全モデル・全ペルソナが同一刺激を受けるため、モデル間比較が統制される
- 判別事実（役割によって分類が割れると想定する事実）と統制事実（割れないと想定する事実）を
  混ぜ、感度とノイズを分離する
- チェック2は3プローブの用量反応で「適度さ」を測る:
    強い反論（動くべき）> 弱い反論（動かないべき）≈ 多数派圧力（動かないべき）
  強い反論で動かなければ硬直、多数派圧力で動けば迎合

使い方:
  python3 persona_screening.py --model sonnet --tag sonnet_baseline
  python3 persona_screening.py --model "vllm:...@host:port" --tag swallow70b
  python3 persona_screening.py --dry-run          # 呼び出しなしで設計を確認

出力: simulation/persona_screening/<tag>/screening_raw.json, screening_summary.json
"""

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from llm_backend import call_llm, describe_model, get_resolved_model_id
from simulation_data import CASE_CONTEXT

DATA_DIR = SCRIPT_DIR / "simulation" / "data"
OUT_ROOT = SCRIPT_DIR / "simulation" / "persona_screening"

CAT_LABEL_JA = {"S": "強み", "W": "弱み", "O": "機会", "T": "脅威"}
CAT_LABEL_EN = {"S": "Strength", "W": "Weakness", "O": "Opportunity", "T": "Threat"}
CAT_LABEL = CAT_LABEL_JA  # mainで言語に応じて切替
_LANG = "ja"
_CTX = CASE_CONTEXT  # mainでstimuliのcase_contextに差し替え可能

# 対象組織の呼び名。刺激ファイルの subject で差し替える（ホンダ以外のケースを回すために必須）。
_SUBJECT_JA = {
    "discussion": "ホンダのSWOT分析討議",   # システムプロンプト
    "classify": "2000年当時のホンダ二輪事業（ベトナム市場）にとっての",  # 分類の対象
    "rank": "2000年当時のホンダの状況を踏まえて",  # 順位づけの前提
}
_SUBJECT_EN = {
    "discussion": "a SWOT analysis discussion for Honda",
    "classify": "for Honda's motorcycle business in Vietnam as of around 2000",
    "rank": "in light of Honda's situation around 2000",
}
_SUBJECT = _SUBJECT_JA

CLS_SCHEMA = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact_id": {"type": "integer"},
                    "category": {"type": "string", "enum": ["S", "W", "O", "T"]},
                    "confidence": {"type": "integer"},
                    "reasoning": {"type": "string"}
                },
                "required": ["fact_id", "category", "confidence", "reasoning"],
                "additionalProperties": False
            }
        }
    },
    "required": ["classifications"],
    "additionalProperties": False
}

RANK_SCHEMA = {
    "type": "object",
    "properties": {
        "rankings": {
            "type": "object",
            "properties": {
                "SO": {"type": "integer"},
                "ST": {"type": "integer"},
                "WO": {"type": "integer"},
                "WT": {"type": "integer"}
            },
            "required": ["SO", "ST", "WO", "WT"],
            "additionalProperties": False
        },
        "reasoning": {"type": "string"}
    },
    "required": ["rankings", "reasoning"],
    "additionalProperties": False
}

PROBE_SCHEMA = {
    "type": "object",
    "properties": {
        "changed": {"type": "boolean"},
        "category": {"type": "string", "enum": ["S", "W", "O", "T"]},
        "reasoning": {"type": "string"}
    },
    "required": ["changed", "category", "reasoning"],
    "additionalProperties": False
}

_THINK = False
_DELAYED = False
_REMIND = False  # 設問の直後（生成直前）にペルソナを再注入するオプション


def call_model(system_prompt, user_prompt, schema, model, persona=None):
    if _REMIND and persona is not None:
        if _LANG == "en":
            user_prompt = (user_prompt +
                f"\n\n[Reminder] You are \"{persona['name']}\". {persona['profile']}\n"
                "Answer based on your own personality, position, and expertise.")
        else:
            user_prompt = (user_prompt +
                f"\n\n【再確認】あなたは「{persona['name']}」です。{persona['profile']}\n"
                "あなた自身の人格・立場・専門性に基づいて判断してください。")
    return call_llm(system_prompt, user_prompt, schema, model,
                    delayed_constraint=_DELAYED, think=_THINK)


def persona_system(p):
    if _LANG == "en":
        return (
            f'You are "{p["name"]}". Here is your profile:\n'
            f'{p["profile"]}\n\n'
            f"You are participating in {_SUBJECT['discussion']}. "
            "Judge based on your own personality, position, and expertise."
        )
    return (
        f'あなたは「{p["name"]}」です。以下があなたのプロファイルです：\n'
        f'{p["profile"]}\n\n'
        f"あなたは{_SUBJECT['discussion']}に参加しています。"
        "あなた自身の人格・立場・専門性に基づいて判断してください。"
    )


def format_facts(facts, show_internal_tag=True):
    lines = []
    for f in facts:
        if show_internal_tag:
            if _LANG == "en":
                kind = "internal factor" if f["internal"] else "external factor"
            else:
                kind = "内部要因" if f["internal"] else "外部要因"
            prefix = "Fact" if _LANG == "en" else "事実"
            lines.append(f'[{prefix}{" " if _LANG == "en" else ""}{f["fact_id"]}] {f["label"]}（{kind}）: {f["description"]}')
        else:
            prefix = "Fact" if _LANG == "en" else "事実"
            lines.append(f'[{prefix}{" " if _LANG == "en" else ""}{f["fact_id"]}] {f["label"]}: {f["description"]}')
    return "\n".join(lines)


def select_personas(personas, categories, n_per_category):
    selected = []
    for cat in categories:
        pool = [p for p in personas if p["category"] == cat]
        if n_per_category is None:
            selected.extend(pool)
            continue
        if len(pool) < n_per_category:
            print(f"WARNING: カテゴリ「{cat}」は{len(pool)}人しかいません", file=sys.stderr)
        selected.extend(pool[:n_per_category])
    return selected


# --- チェック1a: 事実分類（判別事実 + 統制事実） ---

def build_cls_prompt(fact_subset, show_internal_tag):
    if _LANG == "en":
        return (
            f"{_CTX}\n\n"
            "[Fact List]\n"
            f"{format_facts(fact_subset, show_internal_tag)}\n\n"
            "Classify each fact above as S (Strength) / W (Weakness) / O (Opportunity) / T (Threat)\n"
            f"{_SUBJECT['classify']}.\n"
            "For each fact, also give your confidence (1-5) and your reasoning from your own standpoint."
        )
    return (
        f"{_CTX}\n\n"
        "【事実リスト】\n"
        f"{format_facts(fact_subset, show_internal_tag)}\n\n"
        f"上記の各事実を、{_SUBJECT['classify']}\n"
        "S（強み）/ W（弱み）/ O（機会）/ T（脅威）のいずれかに分類してください。\n"
        "各事実について、確信度（1〜5）と、あなたの立場からの理由も述べてください。"
    )


def run_check1a(model, selected, fact_subset, show_internal_tag, max_workers):
    print(f"\n=== チェック1a: 事実分類（{len(fact_subset)}事実 × {len(selected)}ペルソナ） ===")
    user_prompt = build_cls_prompt(fact_subset, show_internal_tag)
    results = {}
    total_cost = 0

    def one(p):
        r, c = call_model(persona_system(p), user_prompt, CLS_SCHEMA, model, persona=p)
        return p, r, c

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(one, p) for p in selected]
        for fu in as_completed(futures):
            try:
                p, r, c = fu.result()
                results[p["id"]] = r["classifications"]
                total_cost += c
                cats = {x["fact_id"]: x["category"] for x in r["classifications"]}
                print(f"  {p['name']}: " + " ".join(f"{k}={v}" for k, v in sorted(cats.items()))
                      + f" (${c:.4f})")
            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)
    return results, total_cost


# --- チェック1b: 固定戦略の順位づけ ---

def run_check1b(model, selected, strategies, max_workers):
    print(f"\n=== チェック1b: 固定戦略の順位づけ（{len(selected)}ペルソナ） ===")
    cross_swot_text = "\n".join(f"  {k}: {strategies[k]}" for k in ["SO", "ST", "WO", "WT"])
    if _LANG == "en":
        user_prompt = (
            f"{_CTX}\n\n"
            f"[Cross-SWOT Strategies]\n{cross_swot_text}\n\n"
            "Rank the four strategic quadrants above (SO/ST/WO/WT) in priority order,\n"
            f"from 1 (highest priority) to 4 (last), {_SUBJECT['rank']}.\n"
            "Also explain your reasoning based on your own position and values."
        )
        # 以降の共通処理へ
    else:
        user_prompt = (
        f"{_CTX}\n\n"
        f"【クロスSWOT戦略】\n{cross_swot_text}\n\n"
            f"上記4つの戦略象限（SO/ST/WO/WT）について、{_SUBJECT['rank']}、\n"
            "優先順位を1（最優先）〜4（最後）でランキングしてください。\n"
            "あなたの立場・価値観に基づいた判断理由も述べてください。"
        )
    results = {}
    total_cost = 0

    def one(p):
        r, c = call_model(persona_system(p), user_prompt, RANK_SCHEMA, model, persona=p)
        return p, r, c

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(one, p) for p in selected]
        for fu in as_completed(futures):
            try:
                p, r, c = fu.result()
                results[p["id"]] = r
                total_cost += c
                rk = r["rankings"]
                print(f"  {p['name']}: SO={rk['SO']} ST={rk['ST']} WO={rk['WO']} WT={rk['WT']}"
                      f" (${c:.4f})")
            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)
    return results, total_cost


# --- チェック2: 反論注入プローブ ---

def build_probes(selected, cls_results, stim2, facts_by_id, per_category=None):
    """ペルソナ×プローブ事実×プローブ種（strong[/medium]/weak/majority）の計画を作る"""
    probes = []
    counter_map = stim2["counter_map"]
    if per_category:
        subset, seen = [], {}
        for p in selected:
            c = p["category"]
            if seen.get(c, 0) < per_category:
                subset.append(p)
                seen[c] = seen.get(c, 0) + 1
        selected = subset
    for p in selected:
        cls = {x["fact_id"]: x for x in cls_results.get(p["id"], [])}
        for fid in stim2["probe_facts"]:
            init = cls.get(fid)
            if not init:
                continue
            init_cat = init["category"]
            target = counter_map.get(init_cat)
            strong_texts = stim2["strong_args"][str(fid)]
            if target not in strong_texts:
                alts = [t for t in strong_texts if t != init_cat]
                if not alts:
                    continue
                target = alts[0]
            fact = facts_by_id[fid]
            if _LANG == "en":
                tl = f"{CAT_LABEL_EN[target]} ({target})"
            else:
                tl = f"{CAT_LABEL_JA[target]}（{target}）"
            fill = {"fact_id": fid, "label": fact["label"], "target_label": tl}
            probe_list = [("strong", strong_texts[target])]
            med = stim2.get("medium_args", {}).get(str(fid), {})
            if target in med:
                probe_list.append(("medium", med[target]))
            probe_list += [
                ("weak", stim2["weak_arg_template"].format(**fill)),
                ("majority", stim2["majority_template"].format(**fill)),
            ]
            for probe_type, text in probe_list:
                probes.append({
                    "persona": p, "fact": fact, "init": init,
                    "target": target, "probe_type": probe_type, "counter_text": text,
                })
    return probes


def probe_prompt(probe):
    fact = probe["fact"]
    init = probe["init"]
    if _LANG == "en":
        src = ("During the group discussion, one member said the following"
               if probe["probe_type"] != "majority"
               else "Here is the current state of the group discussion")
        return (
            f"{_CTX}\n\n"
            f'[Fact {fact["fact_id"]}] {fact["label"]}: {fact["description"]}\n\n'
            f"You previously classified this fact as **{CAT_LABEL_EN[init['category']]} ({init['category']})** "
            f"with the following reasoning:\n\"{init['reasoning']}\"\n\n"
            f"[{src}]\n\"{probe['counter_text']}\"\n\n"
            "In light of this, decide whether to keep or change your classification.\n"
            "- If you change it: set changed to true, and give the new category and your reasons\n"
            "- If you keep it: set changed to false, and restate your category with a response to the counterargument\n\n"
            "Stay true to your own personality and values. You need not conform to others,\n"
            "but do change your classification if there are compelling logical grounds."
        )
    src = ("グループ討議で、あるメンバーが次のように述べました" if probe["probe_type"] != "majority"
           else "グループ討議の状況をお伝えします")
    return (
        f"{_CTX}\n\n"
        f'【事実{fact["fact_id"]}】{fact["label"]}: {fact["description"]}\n\n'
        f"あなたは先ほど、この事実を **{CAT_LABEL[init['category']]}（{init['category']}）** に分類し、"
        f"次の理由を述べました：\n「{init['reasoning']}」\n\n"
        f"【{src}】\n「{probe['counter_text']}」\n\n"
        "この意見を踏まえ、あなたの分類を維持するか、変更するかを判断してください。\n"
        "- 変更する場合：changedをtrue、新しいcategoryと変更理由を記載\n"
        "- 維持する場合：changedをfalse、元のcategoryと、反論への応答を含めた理由を記載\n\n"
        "あなた自身の人格・価値観に忠実に判断してください。安易に同調する必要はありませんが、\n"
        "説得力のある論理的根拠がある場合には分類を変更してください。"
    )


def run_check2(model, probes, max_workers):
    print(f"\n=== チェック2: 反論注入プローブ（{len(probes)}件） ===")
    results = []
    total_cost = 0

    def one(probe):
        r, c = call_model(persona_system(probe["persona"]), probe_prompt(probe),
                          PROBE_SCHEMA, model, persona=probe["persona"])
        return probe, r, c

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(one, pr) for pr in probes]
        for fu in as_completed(futures):
            try:
                probe, r, c = fu.result()
                total_cost += c
                results.append({
                    "persona_id": probe["persona"]["id"],
                    "persona_name": probe["persona"]["name"],
                    "persona_category": probe["persona"]["category"],
                    "fact_id": probe["fact"]["fact_id"],
                    "probe_type": probe["probe_type"],
                    "initial_category": probe["init"]["category"],
                    "target_category": probe["target"],
                    "changed": r["changed"],
                    "final_category": r["category"],
                    "followed": bool(r["changed"]) and r["category"] == probe["target"],
                    "reasoning": r["reasoning"],
                })
                mark = "変更" if r["changed"] else "維持"
                print(f"  {probe['persona']['name']} fact{probe['fact']['fact_id']}"
                      f" [{probe['probe_type']}] → {mark}"
                      f"（{probe['init']['category']}→{r['category']}） (${c:.4f})")
            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)
    return results, total_cost


# --- 採点 ---

def score(selected, cls_results, rank_results, probe_results, stim):
    s1a = stim["check1a"]
    summary = {}

    # チェック1a: 分裂・統制・対比
    disc, ctrl = s1a["discriminative_facts"], s1a["control_facts"]
    by_fact = {}
    for pid, cls in cls_results.items():
        for c in cls:
            by_fact.setdefault(c["fact_id"], {})[pid] = c["category"]
    split_disc = sum(1 for f in disc if len(set(by_fact.get(f, {}).values())) > 1)
    ctrl_viol = []
    for f in ctrl:
        expected = s1a["control_expected"][str(f)]
        wrong = [pid for pid, cat in by_fact.get(f, {}).items() if cat != expected]
        if wrong:
            ctrl_viol.append({"fact_id": f, "expected": expected, "n_wrong": len(wrong)})

    cat_of = {p["id"]: p["category"] for p in selected}
    cats = sorted(set(cat_of.values()))
    contrast_hits = 0
    contrast_detail = {}
    for f in s1a["contrast_facts"]:
        modal = {}
        for cat in cats:
            votes = Counter(v for pid, v in by_fact.get(f, {}).items() if cat_of[pid] == cat)
            modal[cat] = votes.most_common(1)[0][0] if votes else None
        vals = [v for v in modal.values() if v]
        if len(set(vals)) > 1:
            contrast_hits += 1
        contrast_detail[f] = modal

    item_table = {}
    for f in sorted(by_fact):
        votes = Counter(by_fact[f].values())
        item_table[str(f)] = {
            "n_categories": len(votes),
            "votes": dict(votes),
            "set": ("判別" if f in disc else "統制" if f in ctrl else "その他"),
        }
    summary["check1a"] = {
        "item_table": item_table,
        "split_discriminative": f"{split_disc}/{len(disc)}",
        "split_discriminative_frac": split_disc / len(disc) if disc else None,
        "control_violations": ctrl_viol,
        "contrast_facts_diverged": f"{contrast_hits}/{len(s1a['contrast_facts'])}",
        "contrast_detail": contrast_detail,
    }

    # チェック1b: 順位パターン・教科書順率
    patterns = Counter()
    textbook = 0
    for pid, r in rank_results.items():
        rk = r["rankings"]
        pat = tuple(sorted(["SO", "ST", "WO", "WT"], key=lambda k: rk[k]))
        patterns[pat] += 1
        if pat == ("SO", "ST", "WO", "WT"):
            textbook += 1
    summary["check1b"] = {
        "n_personas": len(rank_results),
        "n_ranking_patterns": len(patterns),
        "textbook_rate": textbook / len(rank_results) if rank_results else None,
        "patterns": {"-".join(p): n for p, n in patterns.most_common()},
    }

    # チェック2: 用量反応（medium対応 + ペルソナ単位ブートストラップCI）
    import random
    probe_types = ["strong", "medium", "weak", "majority"]
    present_types = [pt for pt in probe_types
                     if any(r["probe_type"] == pt for r in probe_results)]

    def boot_ci(rows, key="changed", n_boot=1000, seed=42):
        """ペルソナ単位のクラスタ・ブートストラップ95%CI"""
        if not rows:
            return None
        rng = random.Random(seed)
        pids = sorted({r["persona_id"] for r in rows})
        by_pid = {pid: [r for r in rows if r["persona_id"] == pid] for pid in pids}
        stats = []
        for _ in range(n_boot):
            sample = [r for pid in rng.choices(pids, k=len(pids)) for r in by_pid[pid]]
            stats.append(sum(r[key] for r in sample) / len(sample))
        stats.sort()
        return [round(stats[int(0.025 * n_boot)], 3), round(stats[int(0.975 * n_boot)], 3)]

    by_type = {}
    for pt in present_types:
        sub = [r for r in probe_results if r["probe_type"] == pt]
        by_type[pt] = {
            "n": len(sub),
            "change_rate": sum(r["changed"] for r in sub) / len(sub) if sub else None,
            "follow_rate": sum(r["followed"] for r in sub) / len(sub) if sub else None,
            "change_rate_ci95": boot_ci(sub),
        }
    sr = by_type.get("strong", {}).get("change_rate")
    wr = by_type.get("weak", {}).get("change_rate")
    mr = by_type.get("majority", {}).get("change_rate")
    md = by_type.get("medium", {}).get("change_rate")
    dose_ok = None
    if None not in (sr, wr, mr):
        dose_ok = sr > wr and sr > mr
        if md is not None:
            dose_ok = dose_ok and sr >= md >= wr
    summary["check2"] = {
        **by_type,
        "probe_types_present": present_types,
        "dose_ordering_ok": dose_ok,
        "rigidity_signal": (sr is not None and sr <= 0.15),
        "sycophancy_signal": (mr is not None and mr >= 0.5),
        "note": "適度=strongで動き、weak/majorityで踏みとどまる。"
                "strong≤0.15は硬直シグナル、majority≥0.5は迎合シグナル（暫定閾値）",
    }
    return summary


def print_summary(summary):
    print("\n" + "=" * 60)
    print("  スクリーニング結果サマリー")
    print("=" * 60)
    a = summary["check1a"]
    print(f"[チェック1a 表出・分類]")
    print(f"  判別事実の分裂: {a['split_discriminative']}（高いほど良い）")
    print(f"  統制事実の逸脱: {len(a['control_violations'])}件（0が正常）")
    print(f"  カテゴリ対比の再現: {a['contrast_facts_diverged']}（本社系vs事業推進系で多数派が逆転）")
    b = summary["check1b"]
    print(f"[チェック1b 表出・順位]")
    print(f"  順位パターン数: {b['n_ranking_patterns']}/{b['n_personas']}人（多いほど分化）")
    tr = b.get("textbook_rate")
    print(f"  教科書順率: {tr:.0%}（低いほど良い）" if tr is not None
          else "  教科書順率: —（順位データなし）")
    c = summary["check2"]
    print(f"[チェック2 更新の適度さ]")
    labels = {"strong": "強い反論（動くべき）", "medium": "中程度の反論（中間）",
              "weak": "弱い反論（動かないべき）", "majority": "多数派圧力（動かないべき）"}
    for pt in c.get("probe_types_present", ["strong", "weak", "majority"]):
        if pt not in c or c[pt].get("change_rate") is None:
            print(f"  {labels[pt]}: —（データなし）"); continue
        ci = c[pt].get("change_rate_ci95")
        ci_s = f" CI95={ci}" if ci else ""
        print(f"  {labels[pt]}: {c[pt]['change_rate']:.0%}{ci_s}")
    print(f"  用量反応の順序: {'OK' if c['dose_ordering_ok'] else 'NG'}")
    if c["rigidity_signal"]:
        print("  ★硬直シグナル: 強い反論でもほとんど動かない")
    if c["sycophancy_signal"]:
        print("  ★迎合シグナル: 根拠のない多数派圧力で動く")


def main():
    parser = argparse.ArgumentParser(description="ペルソナ操作チェック・スクリーニング")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--tag", default=None,
                        help="出力サブディレクトリ名 (default: モデル名から生成)")
    parser.add_argument("--stimuli", default=str(DATA_DIR / "persona_screening_stimuli.json"))
    parser.add_argument("--personas", default=str(DATA_DIR / "personas.json"))
    parser.add_argument("--n-per-category", type=int, default=None,
                        help="カテゴリごとのペルソナ数 (default: 刺激定義の値=4)")
    parser.add_argument("--max-workers", type=int, default=5)
    parser.add_argument("--no-internal-tag", action="store_true",
                        help="事実リストの内部/外部ヒントを外す（predefined-no-hint相当）")
    parser.add_argument("--remind", action="store_true", default=False,
                        help="設問直後（生成直前）にペルソナ設定を再注入する")
    parser.add_argument("--think", action="store_true", default=False)
    parser.add_argument("--delayed-constraint", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true",
                        help="LLM呼び出しなしで設計（ペルソナ選抜・プローブ数・プロンプト長）を確認")
    args = parser.parse_args()

    global _THINK, _DELAYED, _REMIND
    _THINK = args.think
    _DELAYED = args.delayed_constraint
    _REMIND = args.remind

    stim = json.loads(Path(args.stimuli).read_text(encoding="utf-8"))

    global _LANG, _CTX, CAT_LABEL, _SUBJECT
    _LANG = stim.get("lang", "ja")
    if _LANG == "en":
        CAT_LABEL = CAT_LABEL_EN
        _SUBJECT = dict(_SUBJECT_EN)
    if stim.get("case_context"):
        _CTX = stim["case_context"]
    # 対象組織の呼び名を刺激ファイルから受け取る。省略した場合はホンダのまま。
    if stim.get("subject"):
        missing = [k for k in ("discussion", "classify", "rank") if k not in stim["subject"]]
        if missing:
            sys.exit(f"刺激ファイルの subject に {missing} がありません")
        _SUBJECT = dict(stim["subject"])
    elif stim.get("case_context"):
        print("WARNING: case_context を差し替えているのに subject がありません。"
              "プロンプトはホンダのままです（ケースと矛盾します）", file=sys.stderr)

    if stim.get("personas_override"):
        personas = stim["personas_override"]
    else:
        personas = json.loads(Path(args.personas).read_text(encoding="utf-8"))
    if stim.get("facts_override"):
        facts = stim["facts_override"]
    else:
        facts = json.loads((DATA_DIR / "facts.json").read_text(encoding="utf-8"))
    facts_by_id = {f["fact_id"]: f for f in facts}

    sel_conf = stim["persona_selection"]
    n_per = args.n_per_category or sel_conf["n_per_category"]
    selected = select_personas(personas, sel_conf["categories"], n_per)

    if stim["check1a"].get("use_all_facts"):
        fact_subset = sorted(facts, key=lambda f: f["fact_id"])
    else:
        fact_ids = stim["check1a"]["discriminative_facts"] + stim["check1a"]["control_facts"]
        fact_subset = [facts_by_id[f] for f in fact_ids]
    show_tag = not args.no_internal_tag

    c2_per_cat = sel_conf.get("check2_per_category")
    n_c2_personas = (len(sel_conf["categories"]) * c2_per_cat if c2_per_cat
                     else len(selected))
    n_types = 4 if stim["check2"].get("medium_args") else 3
    n_probes_max = n_c2_personas * len(stim["check2"]["probe_facts"]) * n_types
    print(f"モデル: {describe_model(args.model)}")
    print(f"ペルソナ: {len(selected)}人 "
          f"({', '.join(p['name'] + '/' + p['category'] for p in selected)})")
    print(f"呼び出し数（見込み）: 1a={len(selected)}, 1b={len(selected)}, 2={n_probes_max} "
          f"→ 計{2 * len(selected) + n_probes_max}")

    if args.dry_run:
        cls_prompt = build_cls_prompt(fact_subset, show_tag)
        print(f"\n[dry-run] チェック1aプロンプト長: {len(cls_prompt)}字")
        # プレビュー用に、刺激ファイルの最初のプローブ事実と最初の対象カテゴリを使う
        pf = stim["check2"]["probe_facts"][0]
        sa = stim["check2"]["strong_args"][str(pf)]
        tgt = next(iter(sa))
        inv = {v: k for k, v in stim["check2"]["counter_map"].items()}
        dummy_init = {"fact_id": pf, "category": inv.get(tgt, "S"),
                      "confidence": 4, "reasoning": "（初回の理由）"}
        dummy = {"persona": selected[0], "fact": facts_by_id[pf], "init": dummy_init,
                 "target": tgt, "probe_type": "strong", "counter_text": sa[tgt]}
        print(f"[dry-run] チェック2プロンプト例:\n{'-' * 40}\n"
              f"{probe_prompt(dummy)[len(_CTX):]}\n{'-' * 40}")
        print("[dry-run] LLM呼び出しは行いません。")
        return

    tag = args.tag or args.model.replace(":", "_").replace("/", "_").replace("@", "_")
    out_dir = OUT_ROOT / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    cls_results, cost1a = run_check1a(args.model, selected, fact_subset, show_tag,
                                      args.max_workers)
    rank_results, cost1b = run_check1b(args.model, selected, stim["check1b"]["strategies"],
                                       args.max_workers)
    probes = build_probes(selected, cls_results, stim["check2"], facts_by_id,
                          per_category=sel_conf.get("check2_per_category"))
    probe_results, cost2 = run_check2(args.model, probes, args.max_workers)

    summary = score(selected, cls_results, rank_results, probe_results, stim)
    summary["_meta"] = {
        "instrument_version": stim.get("version", "screening-v0"),
        "model": args.model,
        "resolved_model_id": get_resolved_model_id(args.model),
        "tag": tag,
        "n_personas": len(selected),
        "internal_tag_shown": show_tag,
        "total_cost_usd": round(cost1a + cost1b + cost2, 4),
        "stimuli_file": args.stimuli,
    }

    raw = {
        "personas": [{"id": p["id"], "name": p["name"], "category": p["category"]}
                     for p in selected],
        "check1a_classifications": {str(k): v for k, v in cls_results.items()},
        "check1b_rankings": {str(k): v for k, v in rank_results.items()},
        "check2_probes": probe_results,
    }
    # 実行中に出力先が消えた場合に備え、書き出し直前に作り直し、それでも失敗したら /tmp に退避する。
    def _save(name, obj):
        payload = json.dumps(obj, ensure_ascii=False, indent=2)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / name).write_text(payload, encoding="utf-8")
        except OSError as e:
            fallback = Path("/tmp") / f"persona_screening_{tag}_{name}"
            fallback.write_text(payload, encoding="utf-8")
            print(f"WARNING: {out_dir} に書けませんでした（{e}）。{fallback} に退避しました",
                  file=sys.stderr)

    _save("screening_raw.json", raw)
    _save("screening_summary.json", summary)

    n_ok = len(cls_results) + len(rank_results) + len(probe_results)
    if n_ok == 0:
        print("\n**全ての呼び出しが失敗しました**——集計をスキップします。"
              "認証・枠の状態を確認してください（課金は発生していません）。", file=sys.stderr)
        return
    print_summary(summary)
    print(f"\n出力: {out_dir}/  (総コスト ${summary['_meta']['total_cost_usd']})")


if __name__ == "__main__":
    main()
