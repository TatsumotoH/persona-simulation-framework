#!/usr/bin/env python3
"""
SWOT分析の多人格エージェント・シミュレーション — 再現用スクリプト
Claude Code CLI (claude -p) を使用。

使い方:
  python run_agents.py                    # 全ステップ実行
  python run_agents.py --steps 3          # Step 3のみ
  python run_agents.py --steps 4,5,6      # Step 4〜6のみ
  python run_agents.py --model haiku      # モデル変更（sonnet/haiku/opus）

前提:
  - Claude Code がインストール済み（claude コマンドが使えること）
  - claude コマンドでログイン済み
"""

import json
import subprocess
import argparse
import random
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).parent / "simulation"
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

CASE_CONTEXT = """\
【ケース概要】天野倫文・新宅純二郎（2010）「ホンダ二輪事業のASEAN戦略」

2000年前後、ベトナム二輪市場に中国製イミテーションバイクが大量流入した。
中国車は約550ドルとホンダの約半額で、市場は1999年の50万台から2000年に175万台へ3.5倍に膨張。
ホンダはスーパードリーム（923ドル）やFuture（125cc高価格スポーツ）を中心とする
「売れる人に売る」高ロイヤルティ戦略をとっていたが、シェアを急速に失った。

ホンダは世界トップクラスの二輪技術を持ち、タイではWave 125/100/Zで段階的に
ローコストモデルを展開しシェア70%を達成した実績がある。ASEAN域内で
プラットフォーム戦略（800〜1000部品共通化）とサプライチェーン（タイ現地調達率96.8%）を
構築していた。またカブはベトナム戦争中に根付き「バイク＝ホンダ」と同義語になっていた。

対応として、2002年1月にベトナム向けWave α（時速80km制限、800ドル）を投入。
しかし中国車流入から約2年を要した意思決定の遅さ、ベトナム現地R&D（HRS-V）の
2003年設立まで現地開発力が不足していた課題もあった。

外部環境では、2002年9月にベトナム政府が輸入総量規制を敷き中国車を規制。
2003年に1人1台登録制を導入（「1台なら品質の良いものを」という消費者心理を生む）。
中国車の品質問題報道、中間層の拡大、道路インフラ整備、
スクータ市場の将来成長なども重要な外部要因である。"""

# --- JSON Schemas ---

CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "persona_id": {"type": "integer"},
        "persona_name": {"type": "string"},
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact_id": {"type": "integer"},
                    "category": {"type": "string", "enum": ["S", "W", "O", "T"]},
                    "confidence": {"type": "number"},
                    "reasoning": {"type": "string"}
                },
                "required": ["fact_id", "category", "confidence", "reasoning"],
                "additionalProperties": False
            }
        }
    },
    "required": ["persona_id", "persona_name", "classifications"],
    "additionalProperties": False
}

CROSS_SWOT_SCHEMA = {
    "type": "object",
    "properties": {
        "group_name": {"type": "string"},
        "members": {"type": "array", "items": {"type": "string"}},
        "consensus_swot": {
            "type": "object",
            "properties": {
                "S": {"type": "array", "items": {"type": "string"}},
                "W": {"type": "array", "items": {"type": "string"}},
                "O": {"type": "array", "items": {"type": "string"}},
                "T": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["S", "W", "O", "T"],
            "additionalProperties": False
        },
        "cross_swot": {
            "type": "object",
            "properties": {
                "SO": {"type": "string"},
                "ST": {"type": "string"},
                "WO": {"type": "string"},
                "WT": {"type": "string"}
            },
            "required": ["SO", "ST", "WO", "WT"],
            "additionalProperties": False
        },
        "discussion_highlights": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["group_name", "members", "consensus_swot", "cross_swot", "discussion_highlights"],
    "additionalProperties": False
}

PRIORITY_SCHEMA = {
    "type": "object",
    "properties": {
        "group_name": {"type": "string"},
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
    "required": ["group_name", "rankings", "reasoning"],
    "additionalProperties": False
}

INTEGRATION_SCHEMA = {
    "type": "object",
    "properties": {
        "group_name": {"type": "string"},
        "unified_strategy": {"type": "string"},
        "action_priorities": {"type": "array", "items": {"type": "string"}},
        "timeline": {"type": "string"}
    },
    "required": ["group_name", "unified_strategy", "action_priorities", "timeline"],
    "additionalProperties": False
}

ROUND_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "persona_id": {"type": "integer"},
        "persona_name": {"type": "string"},
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact_id": {"type": "integer"},
                    "category": {"type": "string", "enum": ["S", "W", "O", "T"]},
                    "confidence": {"type": "number"},
                    "changed": {"type": "boolean"},
                    "reasoning": {"type": "string"}
                },
                "required": ["fact_id", "category", "confidence", "changed", "reasoning"],
                "additionalProperties": False
            }
        }
    },
    "required": ["persona_id", "persona_name", "classifications"],
    "additionalProperties": False
}

PRIORITY_INDIVIDUAL_SCHEMA = {
    "type": "object",
    "properties": {
        "persona_id": {"type": "integer"},
        "persona_name": {"type": "string"},
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
    "required": ["persona_id", "persona_name", "rankings", "reasoning"],
    "additionalProperties": False
}


def load_data():
    personas = json.loads((DATA_DIR / "personas.json").read_text(encoding="utf-8"))
    facts = json.loads((DATA_DIR / "facts.json").read_text(encoding="utf-8"))
    return personas, facts


def call_claude(system_prompt, user_prompt, schema, model="sonnet"):
    """Claude Code CLI を呼び出して構造化JSONを取得する。"""
    schema_json = json.dumps(schema, ensure_ascii=False)
    result = subprocess.run(
        [
            "claude", "-p",
            "--model", model,
            "--json-schema", schema_json,
            "--output-format", "json",
            "--no-session-persistence",
            "--system-prompt", system_prompt,
            user_prompt,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error (exit {result.returncode}): {result.stderr[:500]}")

    output = json.loads(result.stdout)
    if output.get("is_error"):
        raise RuntimeError(f"Claude error: {output.get('result', 'unknown')[:500]}")

    return output["structured_output"], output.get("total_cost_usd", 0)


def format_facts_list(facts):
    lines = []
    for f in facts:
        kind = "内部要因" if f["internal"] else "外部要因"
        lines.append(f'[事実{f["fact_id"]}] {f["label"]}（{kind}）: {f["description"]}')
    return "\n".join(lines)


# --- Step 2: Group Selection ---

def step2_select_groups(personas):
    by_cat = {}
    for p in personas:
        by_cat.setdefault(p["category"], []).append(p)

    groups = {}

    groups["バランス型"] = [
        by_cat["本社系"][0],
        by_cat["事業推進系"][0],
        by_cat["財務系"][0],
        by_cat["現地系"][0],
        by_cat["技術系"][0],
        by_cat["外部・革新系"][0],
    ]

    groups["本社偏向型"] = [
        by_cat["本社系"][0],
        by_cat["本社系"][2],
        by_cat["本社系"][3],
        by_cat["財務系"][0],
        by_cat["財務系"][2],
        by_cat["技術系"][0],
        by_cat["技術系"][4],
    ]

    groups["現地偏向型"] = [
        by_cat["事業推進系"][0],
        by_cat["事業推進系"][4],
        by_cat["事業推進系"][5],
        by_cat["現地系"][0],
        by_cat["現地系"][1],
        by_cat["現地系"][3],
        by_cat["外部・革新系"][1],
    ]

    rng = random.Random(42)
    groups["ランダム型"] = rng.sample(personas, 6)

    return groups


# --- Step 3: Individual SWOT Classification ---

def step3_classify_one(model, persona, facts_text):
    system_prompt = (
        f"あなたは「{persona['name']}」です。以下があなたのプロファイルです：\n"
        f"{persona['profile']}\n\n"
        "あなたはこの人格になりきって、ケースの事実をSWOT分析の観点から分類してください。"
    )
    user_prompt = (
        f"{CASE_CONTEXT}\n\n"
        "【分類対象の事実一覧】\n"
        f"{facts_text}\n\n"
        "上記の各事実を、あなたの立場・価値観・専門性に基づいて、"
        "S（Strength）、W（Weakness）、O（Opportunity）、T（Threat）のいずれかに分類してください。\n"
        "各事実について、分類カテゴリ、確信度（0.0〜1.0）、判断理由を述べてください。\n\n"
        "注意：\n"
        "- 内部要因はS（強み）またはW（弱み）に分類するのが一般的ですが、"
        "あなたの解釈次第ではO（機会）やT（脅威）と捉えることも許容されます。\n"
        "- 外部要因はO（機会）またはT（脅威）に分類するのが一般的ですが、同様に柔軟な解釈が可能です。\n"
        "- あなた自身の人格・立場・価値観に忠実に判断してください。"
    )
    result, cost = call_claude(system_prompt, user_prompt, CLASSIFICATION_SCHEMA, model)
    result["persona_id"] = persona["id"]
    result["persona_name"] = persona["name"]
    return result, cost


def run_step3(model, personas, facts, max_workers):
    print(f"\n=== Step 3: 個別SWOT分類（{len(personas)}エージェント並列） ===")
    facts_text = format_facts_list(facts)
    results = []
    total_cost = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(step3_classify_one, model, p, facts_text): p
            for p in personas
        }
        for i, future in enumerate(as_completed(futures), 1):
            persona = futures[future]
            try:
                result, cost = future.result()
                results.append(result)
                total_cost += cost
                n_cls = len(result.get("classifications", []))
                print(f"  [{i}/{len(personas)}] {persona['name']} ... {n_cls} facts (${cost:.4f})")
            except Exception as e:
                print(f"  [{i}/{len(personas)}] {persona['name']} ... ERROR: {e}",
                      file=sys.stderr)

    results.sort(key=lambda r: r["persona_id"])
    out_path = OUTPUT_DIR / "step3_classifications.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {out_path}  (total: ${total_cost:.4f})")
    return results


# --- Step 4: Multi-Round Group Discussion → Cross-SWOT ---

def format_group_step3(members, s3_by_id):
    """グループメンバーのStep 3分類結果をテキストに整形"""
    blocks = []
    for m in members:
        cls = s3_by_id.get(m["id"])
        if not cls:
            continue
        lines = []
        for c in cls.get("classifications", []):
            lines.append(
                f'  事実{c["fact_id"]}→{c["category"]}'
                f'（確信度{c["confidence"]}）: {c["reasoning"]}'
            )
        blocks.append(f'【{m["name"]}】\n' + "\n".join(lines))
    return "\n\n".join(blocks)


def format_round_results(responses):
    """ラウンドのレスポンスをテキストに整形"""
    blocks = []
    for r in responses:
        lines = []
        for c in r.get("classifications", []):
            tag = "[変更]" if c.get("changed") else ""
            lines.append(
                f'  事実{c["fact_id"]}→{c["category"]}'
                f'（確信度{c["confidence"]}）{tag}: {c["reasoning"]}'
            )
        blocks.append(f'【{r["persona_name"]}】\n' + "\n".join(lines))
    return "\n\n".join(blocks)


def run_step4_round(model, group_name, members, context_text, round_num, max_workers):
    """1ラウンド分のグループ討議（各メンバー並列）"""
    results = []
    total_cost = 0

    if round_num == 2:
        instruction = (
            "他のメンバーの分類結果と理由を注意深く読み、以下を行ってください：\n"
            "1. 他メンバーの意見で説得力があると感じたものを特定する\n"
            "2. 各事実について、自分の当初の分類を維持するか変更するか判断する\n"
            "3. 変更する場合：changedをtrue、新しいcategoryと変更理由を記載\n"
            "4. 維持する場合：changedをfalse、反論への防御を含めた理由を記載\n\n"
            "あなた自身の人格・価値観に忠実に判断してください。安易に多数派に合わせる必要はありません。\n"
            "説得力のある論理的根拠がある場合のみ、分類を変更してください。"
        )
        round_label = "ラウンド1（各メンバーの個別分類結果）"
    else:
        instruction = (
            "上記のラウンド2の結果を読み、最終的な分類を決定してください。\n"
            "他のメンバーが考えを変えた理由も参考にしてください。\n"
            "- 変更する場合：changedをtrue\n"
            "- ラウンド2から変更なし：changedをfalse\n\n"
            "これが最終ラウンドです。あなたの最終判断を述べてください。"
        )
        round_label = "ラウンド2: 各メンバーの修正後の分類"

    def classify_member(member):
        system_prompt = (
            f'あなたは「{member["name"]}」です。以下があなたのプロファイルです：\n'
            f'{member["profile"]}\n\n'
            f"あなたはグループ「{group_name}」のSWOT分析討議に参加しています。"
        )
        user_prompt = (
            f"{CASE_CONTEXT}\n\n"
            f"【{round_label}】\n{context_text}\n\n"
            f"{instruction}"
        )
        result, cost = call_claude(system_prompt, user_prompt, ROUND_RESPONSE_SCHEMA, model)
        result["persona_id"] = member["id"]
        result["persona_name"] = member["name"]
        return result, cost

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(classify_member, m): m for m in members}
        for future in as_completed(futures):
            member = futures[future]
            try:
                result, cost = future.result()
                results.append(result)
                total_cost += cost
                n_changed = sum(1 for c in result.get("classifications", []) if c.get("changed"))
                print(f"    R{round_num} {member['name']} ... {n_changed} changed (${cost:.4f})")
            except Exception as e:
                print(f"    R{round_num} {member['name']} ... ERROR: {e}", file=sys.stderr)

    results.sort(key=lambda r: r["persona_id"])
    return results, total_cost


def run_step4(model, groups, step3_results, facts, max_workers):
    print(f"\n=== Step 4: マルチラウンド・グループ討議（{len(groups)}グループ × 3ラウンド） ===")
    s3_by_id = {r["persona_id"]: r for r in step3_results}
    personas_dict = {p["id"]: p for p in load_data()[0]}

    all_round2 = []
    all_round3 = []
    all_synthesis = []
    total_cost = 0

    for group_name, members_ref in groups.items():
        members = [
            {**m, "profile": personas_dict[m["id"]]["profile"]}
            for m in members_ref
        ]
        member_names = [m["name"] for m in members]
        print(f"\n  [{group_name}]")

        # Round 2: メンバーが他者のStep 3結果を読んで応答
        step3_text = format_group_step3(members_ref, s3_by_id)
        r2_results, r2_cost = run_step4_round(
            model, group_name, members, step3_text, 2, max_workers
        )
        all_round2.append({
            "group_name": group_name,
            "round": 2,
            "responses": r2_results
        })
        total_cost += r2_cost

        # Round 3: Round 2結果を読んで最終判断
        r2_text = format_round_results(r2_results)
        r3_results, r3_cost = run_step4_round(
            model, group_name, members, r2_text, 3, max_workers
        )
        all_round3.append({
            "group_name": group_name,
            "round": 3,
            "responses": r3_results
        })
        total_cost += r3_cost

        # Synthesis: ファシリテーターが合意形成
        r3_text = format_round_results(r3_results)
        synth_prompt = (
            f"{CASE_CONTEXT}\n\n"
            f"以下は「{group_name}」グループの3ラウンドにわたるSWOT討議の記録です。\n\n"
            f"【ラウンド1（初期分類）】\n{step3_text}\n\n"
            f"【ラウンド2（応答・修正）】\n{r2_text}\n\n"
            f"【ラウンド3（最終判断）】\n{r3_text}\n\n"
            "上記の3ラウンドの討議過程を踏まえて、以下を行ってください：\n"
            "1. ラウンド間で分類が変わった事実を特定し、なぜ変わったかを分析\n"
            "2. 最終ラウンドの結果に基づいてコンセンサスSWOTを確定\n"
            "3. クロスSWOT戦略（SO/ST/WO/WT）を具体的な戦略提言として生成\n"
            "4. 討論のハイライト（意見が変わった瞬間、最も白熱した論点）を記録"
        )
        synth_system = (
            "あなたは経営戦略のグループ討論のファシリテーターです。\n"
            "3ラウンドの討議記録を分析し、コンセンサスSWOTとクロスSWOT戦略を導出してください。"
        )
        synth_result, synth_cost = call_claude(
            synth_system, synth_prompt, CROSS_SWOT_SCHEMA, model
        )
        synth_result["group_name"] = group_name
        synth_result["members"] = member_names
        all_synthesis.append(synth_result)
        total_cost += synth_cost
        print(f"    Synthesis ... done (${synth_cost:.4f})")

    # Save round data
    round_data = []
    for r2, r3 in zip(all_round2, all_round3):
        round_data.append({
            "group_name": r2["group_name"],
            "rounds": [r2, r3]
        })
    (OUTPUT_DIR / "step4_rounds.json").write_text(
        json.dumps(round_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_DIR / "step4_cross_swot.json").write_text(
        json.dumps(all_synthesis, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n  -> step4_rounds.json, step4_cross_swot.json  (total: ${total_cost:.4f})")
    return all_synthesis, round_data


# --- Step 5: Priority Ranking (Multi-Round) ---

def run_step5(model, groups, step4_results, max_workers):
    print(f"\n=== Step 5: 優先順位づけ（個別ランキング + 統合） ===")
    s4_by_name = {r["group_name"]: r for r in step4_results}
    personas_dict = {p["id"]: p for p in load_data()[0]}
    all_individual = []
    results = []
    total_cost = 0

    for group_name, members_ref in groups.items():
        s4 = s4_by_name.get(group_name)
        if not s4:
            continue
        members = [
            {**m, "profile": personas_dict[m["id"]]["profile"]}
            for m in members_ref
        ]
        member_names = [m["name"] for m in members]

        cross_swot_text = "\n".join(
            f"  {cell}: {s4['cross_swot'][cell]}"
            for cell in ["SO", "ST", "WO", "WT"]
        )

        # Individual ranking
        def rank_member(member):
            system_prompt = (
                f'あなたは「{member["name"]}」です。{member["profile"]}\n'
                f'グループ「{group_name}」のメンバーとして、戦略の優先順位を判断してください。'
            )
            user_prompt = (
                f"{CASE_CONTEXT}\n\n"
                f"【グループ「{group_name}」のクロスSWOT戦略】\n{cross_swot_text}\n\n"
                "上記4つの戦略象限（SO/ST/WO/WT）について、2000年当時のホンダの状況を踏まえて、\n"
                "優先順位を1（最優先）〜4（最後）でランキングしてください。\n"
                "あなたの立場・価値観に基づいた判断理由も述べてください。"
            )
            result, cost = call_claude(
                system_prompt, user_prompt, PRIORITY_INDIVIDUAL_SCHEMA, model
            )
            result["persona_id"] = member["id"]
            result["persona_name"] = member["name"]
            return result, cost

        indiv_results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(rank_member, m): m for m in members}
            for future in as_completed(futures):
                member = futures[future]
                try:
                    result, cost = future.result()
                    indiv_results.append(result)
                    total_cost += cost
                    r = result["rankings"]
                    print(f"    {member['name']}: SO={r['SO']} ST={r['ST']} WO={r['WO']} WT={r['WT']} (${cost:.4f})")
                except Exception as e:
                    print(f"    {member['name']} ... ERROR: {e}", file=sys.stderr)

        indiv_results.sort(key=lambda r: r["persona_id"])
        all_individual.append({
            "group_name": group_name,
            "individual": indiv_results
        })

        # Synthesis
        indiv_text = "\n".join(
            f"【{r['persona_name']}】"
            f"SO={r['rankings']['SO']}位, ST={r['rankings']['ST']}位, "
            f"WO={r['rankings']['WO']}位, WT={r['rankings']['WT']}位 / "
            f"理由: {r['reasoning']}"
            for r in indiv_results
        )
        synth_prompt = (
            f"{CASE_CONTEXT}\n\n"
            f"【グループ「{group_name}」のクロスSWOT戦略】\n{cross_swot_text}\n\n"
            f"【各メンバーの個別ランキング】\n{indiv_text}\n\n"
            "上記の各メンバーの個別ランキングと理由を踏まえ、グループとしての最終優先順位を決定してください。\n"
            "多数決ではなく、各メンバーの論理を検討した上での合意として示してください。"
        )
        synth_system = (
            "あなたは経営戦略の優先順位づけを行う討論のファシリテーターです。\n"
            "各メンバーの個別ランキングを踏まえ、グループの最終優先順位を決定してください。"
        )
        synth_result, synth_cost = call_claude(
            synth_system, synth_prompt, PRIORITY_SCHEMA, model
        )
        synth_result["group_name"] = group_name
        results.append(synth_result)
        total_cost += synth_cost
        print(f"    Synthesis: SO={synth_result['rankings']['SO']} "
              f"ST={synth_result['rankings']['ST']} "
              f"WO={synth_result['rankings']['WO']} "
              f"WT={synth_result['rankings']['WT']} (${synth_cost:.4f})")

    (OUTPUT_DIR / "step5_individual_rankings.json").write_text(
        json.dumps(all_individual, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_DIR / "step5_priorities.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n  -> step5_individual_rankings.json, step5_priorities.json  (total: ${total_cost:.4f})")
    return results


# --- Step 6: Strategy Integration ---

def run_step6(model, groups, step4_results, step5_results):
    print(f"\n=== Step 6: 統合戦略の導出 ===")
    s4_by_name = {r["group_name"]: r for r in step4_results}
    s5_by_name = {r["group_name"]: r for r in step5_results}
    results = []
    total_cost = 0

    for group_name, members in groups.items():
        s4 = s4_by_name.get(group_name)
        s5 = s5_by_name.get(group_name)
        if not s4 or not s5:
            continue
        member_names = [m["name"] for m in members]

        cross_swot_text = "\n".join(
            f"  {cell}: {s4['cross_swot'][cell]}"
            for cell in ["SO", "ST", "WO", "WT"]
        )
        rankings = s5["rankings"]
        priority_text = ", ".join(
            f"{cell}={rankings[cell]}位"
            for cell in sorted(rankings, key=lambda c: rankings[c])
        )

        system_prompt = (
            "あなたは経営戦略の統合提言を行うシニアストラテジストです。\n"
            "グループのクロスSWOT戦略と優先順位を踏まえて、統合戦略を導出してください。"
        )
        user_prompt = (
            f"{CASE_CONTEXT}\n\n"
            f"【グループ名】{group_name}\n"
            f"【メンバー】{', '.join(member_names)}\n\n"
            "【クロスSWOT戦略】\n"
            f"{cross_swot_text}\n\n"
            f"【優先順位】{priority_text}\n"
            f"【優先順位の理由】{s5['reasoning']}\n\n"
            "上記を踏まえて、以下を導出してください：\n"
            "1. 統合戦略（4象限の戦略をどう組み合わせるか、全体としてどのような方向を目指すか）\n"
            "2. アクションの優先順位リスト（具体的に何を、どの順番で実行するか）\n"
            "3. タイムライン（短期・中期・長期の時間軸での実行計画）\n\n"
            "2000年当時のホンダ二輪事業の立場から、実行可能で論理的に一貫した戦略を提案してください。"
        )
        result, cost = call_claude(system_prompt, user_prompt, INTEGRATION_SCHEMA, model)
        result["group_name"] = group_name
        results.append(result)
        total_cost += cost
        print(f"  {group_name} ... done (${cost:.4f})")

    out_path = OUTPUT_DIR / "step6_integration.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {out_path}  (total: ${total_cost:.4f})")
    return results


def main():
    parser = argparse.ArgumentParser(
        description="SWOT分析の多人格エージェント・シミュレーション（Claude Code CLI版）"
    )
    parser.add_argument(
        "--model", default="sonnet",
        help="使用するモデル (default: sonnet / haiku / opus)"
    )
    parser.add_argument(
        "--steps", default="2,3,4,5,6",
        help="実行するステップ (例: 3 or 4,5,6)"
    )
    parser.add_argument(
        "--max-workers", type=int, default=5,
        help="Step 3の並列数 (default: 5)"
    )
    args = parser.parse_args()

    steps = {int(s.strip()) for s in args.steps.split(",")}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    personas, facts = load_data()

    print(f"Model: {args.model}")
    print(f"Steps: {sorted(steps)}")
    print(f"Personas: {len(personas)}, Facts: {len(facts)}")

    groups = None
    if steps & {2, 4, 5, 6}:
        groups = step2_select_groups(personas)
        if 2 in steps:
            print("\n=== Step 2: グループ選抜 ===")
            for name, members in groups.items():
                print(f"  {name}: {', '.join(m['name'] for m in members)}")

    step3_results = None
    if 3 in steps:
        step3_results = run_step3(args.model, personas, facts, args.max_workers)
    elif steps & {4, 5, 6}:
        s3_path = OUTPUT_DIR / "step3_classifications.json"
        if s3_path.exists():
            step3_results = json.loads(s3_path.read_text(encoding="utf-8"))
            print(f"\nStep 3の結果を読み込み: {s3_path} ({len(step3_results)} personas)")
        else:
            print("ERROR: Step 3の結果が見つかりません。先に --steps 3 を実行してください。",
                  file=sys.stderr)
            sys.exit(1)

    step4_results = None
    if 4 in steps:
        step4_results, round_data = run_step4(
            args.model, groups, step3_results, facts, args.max_workers
        )
    elif steps & {5, 6}:
        s4_path = OUTPUT_DIR / "step4_cross_swot.json"
        if s4_path.exists():
            step4_results = json.loads(s4_path.read_text(encoding="utf-8"))
            print(f"\nStep 4の結果を読み込み: {s4_path}")
        else:
            print("ERROR: Step 4の結果が見つかりません。先に --steps 4 を実行してください。",
                  file=sys.stderr)
            sys.exit(1)

    step5_results = None
    if 5 in steps:
        step5_results = run_step5(args.model, groups, step4_results, args.max_workers)
    elif 6 in steps:
        s5_path = OUTPUT_DIR / "step5_priorities.json"
        if s5_path.exists():
            step5_results = json.loads(s5_path.read_text(encoding="utf-8"))
            print(f"\nStep 5の結果を読み込み: {s5_path}")
        else:
            print("ERROR: Step 5の結果が見つかりません。先に --steps 5 を実行してください。",
                  file=sys.stderr)
            sys.exit(1)

    if 6 in steps:
        run_step6(args.model, groups, step4_results, step5_results)

    print("\n=== 完了 ===")
    print(f"出力先: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
