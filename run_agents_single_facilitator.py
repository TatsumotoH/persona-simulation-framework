#!/usr/bin/env python3
"""
SWOT分析の多人格エージェント・シミュレーション — シングルファシリテーター版
Claude Code CLI (claude -p) を使用。

マルチラウンド版とは異なり、Step 4・5 では1つのファシリテーターエージェントが
グループ全体の討論をシミュレートするよりシンプルなアプローチを採用。

処理ステップ:
  Step 0: PDFからデータ自動生成（--pdf指定時のみ）
  Step 1: データ準備（ペルソナ・事実・ケース概要をJSONに保存）
  Step 2: グループ編成（4グループを選抜）
  Step 3: 個別SWOT分類（30人が各事実をS/W/O/Tに分類）
  Step 4: シングルファシリテーター・グループ討議 → クロスSWOT生成
  Step 5: 優先順位づけ（ファシリテーターが一括ランキング）
  Step 6: 統合戦略の導出

使い方:
  python run_agents_single_facilitator.py              # run1〜20を全ステップ実行
  python run_agents_single_facilitator.py --runs 5     # run1〜5のみ
  python run_agents_single_facilitator.py --steps 4,5,6  # Step 4〜6のみ
  python run_agents_single_facilitator.py --pdf case.pdf # PDFからデータ生成→全ステップ実行

前提:
  - Claude Code がインストール済み（claude コマンドが使えること）
  - claude コマンドでログイン済み
"""

import json
import argparse
import random
import sys
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from simulation_data import CASE_CONTEXT, PERSONAS, run_step0, run_generate_personas
from llm_backend import call_llm, describe_model, get_resolved_model_id
from config_manager import build_config_record, save_and_verify_config

BASE_DIR = Path(__file__).parent / "simulation"
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

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

FREE_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "persona_id": {"type": "integer"},
        "persona_name": {"type": "string"},
        "swot": {
            "type": "object",
            "properties": {
                "S": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item": {"type": "string"},
                            "reasoning": {"type": "string"}
                        },
                        "required": ["item", "reasoning"],
                        "additionalProperties": False
                    }
                },
                "W": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item": {"type": "string"},
                            "reasoning": {"type": "string"}
                        },
                        "required": ["item", "reasoning"],
                        "additionalProperties": False
                    }
                },
                "O": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item": {"type": "string"},
                            "reasoning": {"type": "string"}
                        },
                        "required": ["item", "reasoning"],
                        "additionalProperties": False
                    }
                },
                "T": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item": {"type": "string"},
                            "reasoning": {"type": "string"}
                        },
                        "required": ["item", "reasoning"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["S", "W", "O", "T"],
            "additionalProperties": False
        }
    },
    "required": ["persona_id", "persona_name", "swot"],
    "additionalProperties": False
}

CONSENSUS_SWOT_ONLY_SCHEMA = {
    "type": "object",
    "properties": {
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
        "discussion_highlights": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["consensus_swot", "discussion_highlights"],
    "additionalProperties": False
}

STRATEGY_PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "persona_id": {"type": "integer"},
        "persona_name": {"type": "string"},
        "strategies": {
            "type": "object",
            "properties": {
                "SO": {"type": "object", "properties": {
                    "strategy": {"type": "string"},
                    "reasoning": {"type": "string"}
                }, "required": ["strategy", "reasoning"], "additionalProperties": False},
                "ST": {"type": "object", "properties": {
                    "strategy": {"type": "string"},
                    "reasoning": {"type": "string"}
                }, "required": ["strategy", "reasoning"], "additionalProperties": False},
                "WO": {"type": "object", "properties": {
                    "strategy": {"type": "string"},
                    "reasoning": {"type": "string"}
                }, "required": ["strategy", "reasoning"], "additionalProperties": False},
                "WT": {"type": "object", "properties": {
                    "strategy": {"type": "string"},
                    "reasoning": {"type": "string"}
                }, "required": ["strategy", "reasoning"], "additionalProperties": False}
            },
            "required": ["SO", "ST", "WO", "WT"],
            "additionalProperties": False
        }
    },
    "required": ["persona_id", "persona_name", "strategies"],
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


def run_step1(personas_path):
    """Step 1: データ確認 — データファイルの存在を確認し、なければデフォルトを書き出す"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    ctx_path = DATA_DIR / "case_context.txt"
    p_path = Path(personas_path)
    f_path = DATA_DIR / "facts.json"

    if ctx_path.exists():
        case_context = ctx_path.read_text(encoding="utf-8")
        print(f"\n=== Step 1: データ確認（Step 0で生成済み） ===")
    else:
        case_context = CASE_CONTEXT
        ctx_path.write_text(case_context, encoding="utf-8")
        print(f"\n=== Step 1: データ準備（デフォルトデータを使用） ===")

    if p_path.exists():
        personas = json.loads(p_path.read_text(encoding="utf-8"))
    else:
        personas = PERSONAS
        p_path.parent.mkdir(parents=True, exist_ok=True)
        p_path.write_text(json.dumps(personas, ensure_ascii=False, indent=2), encoding="utf-8")

    if f_path.exists():
        facts = json.loads(f_path.read_text(encoding="utf-8"))
    else:
        print(f"ERROR: {f_path} が見つかりません。先に --pdf でStep 0を実行してください。",
              file=sys.stderr)
        sys.exit(1)

    print(f"  ケース概要: {ctx_path} ({len(case_context)}文字)")
    print(f"  ペルソナ: {p_path} ({len(personas)}人)")
    cats = Counter(p["category"] for p in personas)
    for cat, n in cats.items():
        names = [p["name"] for p in personas if p["category"] == cat]
        print(f"    {cat} ({n}人): {', '.join(names)}")
    internal = sum(1 for f in facts if f["internal"])
    external = len(facts) - internal
    print(f"  事実: {len(facts)}項目（内部要因{internal}, 外部要因{external}）")

    return case_context, personas, facts


def load_data(personas_path):
    ctx_path = DATA_DIR / "case_context.txt"
    if ctx_path.exists():
        case_context = ctx_path.read_text(encoding="utf-8")
    else:
        case_context = CASE_CONTEXT
    p_path = Path(personas_path)
    personas = json.loads(p_path.read_text(encoding="utf-8"))
    facts = json.loads((DATA_DIR / "facts.json").read_text(encoding="utf-8"))
    return case_context, personas, facts


_THINK = False
_FREE_EXTRACT = False
_SHOW_INTERNAL_TAG = True
_EXTRACT_CONTEXT = None

def call_model(system_prompt, user_prompt, schema, model="sonnet"):
    return call_llm(system_prompt, user_prompt, schema, model, think=_THINK)


def format_facts_list(facts, show_internal_tag=True):
    lines = []
    for f in facts:
        if show_internal_tag:
            kind = "内部要因" if f["internal"] else "外部要因"
            lines.append(f'[事実{f["fact_id"]}] {f["label"]}（{kind}）: {f["description"]}')
        else:
            lines.append(f'[事実{f["fact_id"]}] {f["label"]}: {f["description"]}')
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
    result, cost = call_model(system_prompt, user_prompt, CLASSIFICATION_SCHEMA, model)
    result["persona_id"] = persona["id"]
    result["persona_name"] = persona["name"]
    return result, cost


def step3_free_extract_one(model, persona):
    system_prompt = (
        f"あなたは「{persona['name']}」です。以下があなたのプロファイルです：\n"
        f"{persona['profile']}\n\n"
        "あなたはこの人格になりきって、ケースを読み、重要な事実を自分で抽出し、"
        "SWOT分析の観点から分類してください。"
    )
    extract_ctx = _EXTRACT_CONTEXT or CASE_CONTEXT
    user_prompt = (
        f"{extract_ctx}\n\n"
        "上記のケースを読み、あなたの立場・価値観・専門性に基づいて、"
        "ホンダ二輪事業のベトナム戦略に関する重要な事実を抽出し、"
        "SWOT分析の4象限に分類してください。\n\n"
        "指示：\n"
        "- ケースから重要と考える事実を自由に抽出してください（数の指定はありません）\n"
        "- 各事実を S（Strength：強み）、W（Weakness：弱み）、"
        "O（Opportunity：機会）、T（Threat：脅威）のいずれかに分類してください\n"
        "- 内部要因（自社の特性）か外部要因（市場・環境）かの判断も、あなた自身の解釈に委ねます\n"
        "- 各事実について、なぜその象限に分類したかの理由を述べてください\n"
        "- あなた自身の人格・立場・価値観に忠実に判断してください"
    )
    result, cost = call_model(system_prompt, user_prompt, FREE_EXTRACT_SCHEMA, model)
    result["persona_id"] = persona["id"]
    result["persona_name"] = persona["name"]
    return result, cost


def run_step3(model, personas, facts, max_workers):
    if _FREE_EXTRACT:
        print(f"\n=== Step 3: 自由抽出SWOT分類（{len(personas)}エージェント並列） ===")
    else:
        print(f"\n=== Step 3: 個別SWOT分類（{len(personas)}エージェント並列） ===")
    results = []
    total_cost = 0

    if _FREE_EXTRACT:
        submit_fn = lambda p: step3_free_extract_one(model, p)
    else:
        facts_text = format_facts_list(facts, show_internal_tag=_SHOW_INTERNAL_TAG)
        submit_fn = lambda p: step3_classify_one(model, p, facts_text)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(submit_fn, p): p
            for p in personas
        }
        for i, future in enumerate(as_completed(futures), 1):
            persona = futures[future]
            try:
                result, cost = future.result()
                results.append(result)
                total_cost += cost
                if _FREE_EXTRACT:
                    swot = result.get("swot", {})
                    n_items = sum(len(swot.get(k, [])) for k in ["S", "W", "O", "T"])
                    print(f"  [{i}/{len(personas)}] {persona['name']} ... {n_items} items (${cost:.4f})")
                else:
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


# --- Step 4: Single-Facilitator Group Discussion → Cross-SWOT ---

def format_strategy_proposals(proposals):
    """戦略提案をテキストに整形"""
    blocks = []
    for p in proposals:
        lines = []
        for cell in ["SO", "ST", "WO", "WT"]:
            s = p["strategies"][cell]
            lines.append(f"  {cell}: {s['strategy']}\n    理由: {s['reasoning']}")
        blocks.append(f'【{p["persona_name"]}】\n' + "\n".join(lines))
    return "\n\n".join(blocks)


def run_strategy_round(model, group_name, members, context_text, round_num, max_workers):
    """戦略提案ラウンド（R4/R5）— SF版"""
    results = []
    total_cost = 0

    if round_num == 4:
        instruction = (
            "上記のコンセンサスSWOTに基づき、クロスSWOT戦略を提案してください。\n"
            "各象限（SO/ST/WO/WT）について、具体的な戦略と根拠を述べてください。\n\n"
            "- SO（強み×機会）: 強みを活かして機会を最大化する攻めの戦略\n"
            "- ST（強み×脅威）: 強みを活かして脅威に対抗する防衛戦略\n"
            "- WO（弱み×機会）: 弱みを克服して機会を活かす改善戦略\n"
            "- WT（弱み×脅威）: 弱みと脅威の影響を最小化するリスク回避戦略\n\n"
            "あなた自身の人格・立場・専門性に基づいて、独自の視点で提案してください。"
        )
        round_label = "コンセンサスSWOT"
    else:
        instruction = (
            "他のメンバーの戦略提案を注意深く読み、以下を行ってください：\n"
            "1. 他メンバーの提案で優れていると感じたものを取り入れる\n"
            "2. 各象限について、自分の戦略提案を維持するか修正するか判断する\n"
            "3. 最終的な戦略提案と根拠を記載する\n\n"
            "これが最終ラウンドです。あなたの最終的な戦略提案を述べてください。"
        )
        round_label = "ラウンド4（各メンバーの戦略提案）"

    def propose_strategy(member):
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
        result, cost = call_model(system_prompt, user_prompt, STRATEGY_PROPOSAL_SCHEMA, model)
        result["persona_id"] = member["id"]
        result["persona_name"] = member["name"]
        return result, cost

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(propose_strategy, m): m for m in members}
        for future in as_completed(futures):
            member = futures[future]
            try:
                result, cost = future.result()
                results.append(result)
                total_cost += cost
                print(f"    R{round_num} {member['name']} ... done (${cost:.4f})")
            except Exception as e:
                print(f"    R{round_num} {member['name']} ... ERROR: {e}", file=sys.stderr)

    results.sort(key=lambda r: r["persona_id"])
    return results, total_cost


def run_step4(model, groups, step3_results, facts, cross_swot_discussion=False,
              max_workers=5):
    label = "クロスSWOT討議あり" if cross_swot_discussion else "標準"
    print(f"\n=== Step 4: グループ討論 → クロスSWOT生成（{len(groups)}グループ, {label}） ===")
    s3_by_id = {r["persona_id"]: r for r in step3_results}
    results = []
    round_data = []
    total_cost = 0

    for group_name, members in groups.items():
        member_names = [m["name"] for m in members]
        members_classifications = []
        for m in members:
            cls = s3_by_id.get(m["id"])
            if cls:
                summary_lines = []
                if "swot" in cls:
                    for cat in ["S", "W", "O", "T"]:
                        cat_label = {"S": "強み", "W": "弱み", "O": "機会", "T": "脅威"}[cat]
                        for item in cls["swot"].get(cat, []):
                            summary_lines.append(
                                f'  {cat}（{cat_label}）: {item["item"]} — {item["reasoning"]}'
                            )
                else:
                    for c in cls.get("classifications", []):
                        fact_label = next(
                            (f["label"] for f in facts if f["fact_id"] == c["fact_id"]),
                            f'事実{c["fact_id"]}'
                        )
                        summary_lines.append(
                            f'  事実{c["fact_id"]}「{fact_label}」→ {c["category"]}'
                            f'（確信度{c["confidence"]}）: {c["reasoning"]}'
                        )
                members_classifications.append(
                    f"【{m['name']}】({m['category']})\n" + "\n".join(summary_lines)
                )

        classifications_text = "\n\n".join(members_classifications)

        if not cross_swot_discussion:
            # --- 標準モード: ファシリテーターが一括処理 ---
            system_prompt = (
                "あなたは経営戦略のグループ討論のファシリテーターです。\n"
                "以下のメンバーの個別SWOT分類結果を踏まえて、グループとしての討論をシミュレートし、\n"
                "コンセンサスSWOTとクロスSWOT戦略を導出してください。"
            )
            user_prompt = (
                f"{CASE_CONTEXT}\n\n"
                f"【グループ名】{group_name}\n"
                f"【メンバー】{', '.join(member_names)}\n\n"
                "【各メンバーの個別SWOT分類結果】\n"
                f"{classifications_text}\n\n"
                "上記の各メンバーの分類結果を元に、以下を行ってください：\n"
                "1. 分類が分かれている事実を特定し、各立場の論理を検討する\n"
                "2. 討論を通じてコンセンサスを形成する（多数決ではなく論理的合意）\n"
                "3. コンセンサスSWOT（S/W/O/Tそれぞれに該当する事実のリスト）を確定する\n"
                "4. クロスSWOT戦略（SO/ST/WO/WT）を生成する\n"
                "5. 討論のハイライト（意見が分かれたポイントとその解決過程）を記録する\n\n"
                "クロスSWOT戦略は具体的な戦略提言として記述してください。"
            )
            result, cost = call_model(system_prompt, user_prompt, CROSS_SWOT_SCHEMA, model)
            result["group_name"] = group_name
            result["members"] = member_names
            results.append(result)
            total_cost += cost
            print(f"  {group_name} ... done (${cost:.4f})")
        else:
            # --- クロスSWOT討議モード ---
            print(f"  [{group_name}]")

            # (a) ファシリテーターが討論シミュレート + コンセンサスSWOT確定
            system_prompt = (
                "あなたは経営戦略のグループ討論のファシリテーターです。\n"
                "以下のメンバーの個別SWOT分類結果を踏まえて、グループとしての討論をシミュレートし、\n"
                "コンセンサスSWOTを確定してください。クロスSWOT戦略はまだ導出しないでください。"
            )
            user_prompt = (
                f"{CASE_CONTEXT}\n\n"
                f"【グループ名】{group_name}\n"
                f"【メンバー】{', '.join(member_names)}\n\n"
                "【各メンバーの個別SWOT分類結果】\n"
                f"{classifications_text}\n\n"
                "上記の各メンバーの分類結果を元に、以下を行ってください：\n"
                "1. 分類が分かれている事実を特定し、各立場の論理を検討する\n"
                "2. 討論を通じてコンセンサスを形成する（多数決ではなく論理的合意）\n"
                "3. コンセンサスSWOT（S/W/O/Tそれぞれに該当する事実のリスト）を確定する\n"
                "4. 討論のハイライト（意見が分かれたポイントとその解決過程）を記録する"
            )
            consensus_result, consensus_cost = call_model(
                system_prompt, user_prompt, CONSENSUS_SWOT_ONLY_SCHEMA, model
            )
            total_cost += consensus_cost
            print(f"    Consensus SWOT ... done (${consensus_cost:.4f})")

            consensus_swot = consensus_result["consensus_swot"]
            consensus_text = "\n".join(
                f"  {cat}: " + ", ".join(items)
                for cat, items in consensus_swot.items()
            )

            # (b) R4: 各メンバーがクロスSWOT戦略を提案
            print(f"    --- クロスSWOT戦略の討議 ---")
            r4_results, r4_cost = run_strategy_round(
                model, group_name, members, consensus_text, 4, max_workers
            )
            total_cost += r4_cost

            # (c) R5: 他メンバーの提案を読んで修正
            r4_text = format_strategy_proposals(r4_results)
            r5_context = f"{consensus_text}\n\n【ラウンド4（各メンバーの戦略提案）】\n{r4_text}"
            r5_results, r5_cost = run_strategy_round(
                model, group_name, members, r5_context, 5, max_workers
            )
            total_cost += r5_cost

            round_data.append({
                "group_name": group_name,
                "rounds": [
                    {"group_name": group_name, "round": 4, "responses": r4_results},
                    {"group_name": group_name, "round": 5, "responses": r5_results},
                ]
            })

            # (d) ファシリテーターが統合
            r5_text = format_strategy_proposals(r5_results)
            final_system = (
                "あなたは経営戦略のグループ討論のファシリテーターです。\n"
                "メンバーのクロスSWOT戦略提案を統合し、最終戦略を導出してください。"
            )
            final_prompt = (
                f"{CASE_CONTEXT}\n\n"
                f"【コンセンサスSWOT】\n{consensus_text}\n\n"
                f"以下はグループメンバーによるクロスSWOT戦略提案の2ラウンドの記録です。\n\n"
                f"【ラウンド4（初期提案）】\n{r4_text}\n\n"
                f"【ラウンド5（修正後の最終提案）】\n{r5_text}\n\n"
                "上記のメンバーの戦略提案を統合して、以下を行ってください：\n"
                "1. 各メンバーの提案の共通点と相違点を分析\n"
                "2. 最終的なクロスSWOT戦略（SO/ST/WO/WT）を導出\n"
                "3. 討論のハイライト（特に優れた提案、意見が分かれた点）を記録"
            )
            synth_result, synth_cost = call_model(
                final_system, final_prompt, CROSS_SWOT_SCHEMA, model
            )
            synth_result["group_name"] = group_name
            synth_result["members"] = member_names
            synth_result["consensus_swot"] = consensus_swot
            results.append(synth_result)
            total_cost += synth_cost
            print(f"    Final Synthesis ... done (${synth_cost:.4f})")

    out_path = OUTPUT_DIR / "step4_cross_swot.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    if round_data:
        rounds_path = OUTPUT_DIR / "step4_rounds.json"
        rounds_path.write_text(
            json.dumps(round_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  -> {rounds_path}")
    print(f"  -> {out_path}  (total: ${total_cost:.4f})")
    return results


# --- Step 5: Single-Facilitator Priority Ranking ---

def run_step5(model, groups, step4_results):
    print(f"\n=== Step 5: 優先順位づけ ===")
    s4_by_name = {r["group_name"]: r for r in step4_results}
    results = []
    total_cost = 0

    for group_name, members in groups.items():
        s4 = s4_by_name.get(group_name)
        if not s4:
            continue
        member_names = [m["name"] for m in members]
        cross_swot_text = "\n".join(
            f"  {cell}: {s4['cross_swot'][cell]}"
            for cell in ["SO", "ST", "WO", "WT"]
        )
        system_prompt = (
            "あなたは経営戦略の優先順位づけを行う討論のファシリテーターです。\n"
            "グループのクロスSWOT戦略について、4つの象限の優先順位を決定してください。"
        )
        user_prompt = (
            f"{CASE_CONTEXT}\n\n"
            f"【グループ名】{group_name}\n"
            f"【メンバー】{', '.join(member_names)}\n\n"
            "【クロスSWOT戦略】\n"
            f"{cross_swot_text}\n\n"
            "上記4つの戦略象限（SO/ST/WO/WT）について、2000年当時のホンダの状況を踏まえて、\n"
            "優先順位を1（最優先）〜4（最後）でランキングしてください。\n"
            "グループメンバーの立場を考慮しつつ、論理的な合意として優先順位とその理由を示してください。"
        )
        result, cost = call_model(system_prompt, user_prompt, PRIORITY_SCHEMA, model)
        result["group_name"] = group_name
        results.append(result)
        total_cost += cost
        print(f"  {group_name} ... done (${cost:.4f})")

    out_path = OUTPUT_DIR / "step5_priorities.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {out_path}  (total: ${total_cost:.4f})")
    return results


def run_step5_individual(model, groups, step4_results, max_workers, personas):
    """Step 5をメンバー個別順位＋ファシリテーター統合で行う（--step5-mode individual。MR方式のStep 5と同一設計）"""
    print(f"\n=== Step 5: 優先順位づけ（個別ランキング + 統合） ===")
    s4_by_name = {r["group_name"]: r for r in step4_results}
    personas_dict = {p["id"]: p for p in personas}
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
            result, cost = call_model(
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
        synth_result, synth_cost = call_model(
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
        result, cost = call_model(system_prompt, user_prompt, INTEGRATION_SCHEMA, model)
        result["group_name"] = group_name
        results.append(result)
        total_cost += cost
        print(f"  {group_name} ... done (${cost:.4f})")

    out_path = OUTPUT_DIR / "step6_integration.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {out_path}  (total: ${total_cost:.4f})")
    return results


STEP_FILES_SF = {
    3: ["step3_classifications.json"],
    4: ["step4_cross_swot.json"],
    5: ["step5_priorities.json"],
    6: ["step6_integration.json"],
}


def print_run_status(run_num, total_runs, output_dir, steps):
    run_steps = {s for s in steps if s in STEP_FILES_SF}
    print(f"\n{'='*60}")
    print(f"  SF Run {run_num}/{total_runs}（シングルファシリテーター方式）")
    print(f"{'='*60}")
    print(f"  入力: {DATA_DIR}/personas.json, {DATA_DIR}/facts.json")
    print(f"  出力: {output_dir}/")
    if run_steps:
        print(f"  ステップ状態:")
        for s in sorted(run_steps):
            files = STEP_FILES_SF[s]
            all_exist = all((output_dir / f).exists() for f in files)
            status = "完了 → スキップ" if all_exist else "未完了 → 実行予定"
            print(f"    Step {s}: {status}")
    all_done = all(
        (output_dir / f).exists()
        for s in run_steps for f in STEP_FILES_SF[s]
    ) if run_steps else True
    if all_done:
        print(f"  → 全ステップ完了済み。このランはスキップします。")
    print(f"{'='*60}")
    return all_done


def run_single(args, steps, output_dir, personas, facts):
    global OUTPUT_DIR
    OUTPUT_DIR = output_dir
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    groups = None
    if steps & {2, 4, 5, 6}:
        groups = step2_select_groups(personas)
        if 2 in steps:
            print("\n=== Step 2: グループ選抜 ===")
            for name, members in groups.items():
                print(f"  {name}: {', '.join(m['name'] for m in members)}")

    step3_results = None
    if 3 in steps:
        s3_path = OUTPUT_DIR / "step3_classifications.json"
        if s3_path.exists():
            step3_results = json.loads(s3_path.read_text(encoding="utf-8"))
            print(f"\nStep 3: スキップ（既存の結果を使用: {s3_path}, {len(step3_results)} personas）")
        else:
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
        s4_path = OUTPUT_DIR / "step4_cross_swot.json"
        if s4_path.exists():
            step4_results = json.loads(s4_path.read_text(encoding="utf-8"))
            print(f"\nStep 4: スキップ（既存の結果を使用: {s4_path}）")
        else:
            step4_results = run_step4(
                args.model, groups, step3_results, facts,
                cross_swot_discussion=getattr(args, 'cross_swot_discussion', False),
                max_workers=args.max_workers
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
        s5_path = OUTPUT_DIR / "step5_priorities.json"
        s5i_path = OUTPUT_DIR / "step5_individual_rankings.json"
        step5_mode = getattr(args, 'step5_mode', 'facilitator')
        step5_done = s5_path.exists() and (
            step5_mode != "individual" or s5i_path.exists()
        )
        if step5_done:
            step5_results = json.loads(s5_path.read_text(encoding="utf-8"))
            print(f"\nStep 5: スキップ（既存の結果を使用: {s5_path}）")
        elif step5_mode == "individual":
            step5_results = run_step5_individual(
                args.model, groups, step4_results, args.max_workers, personas
            )
        else:
            step5_results = run_step5(args.model, groups, step4_results)
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
        s6_path = OUTPUT_DIR / "step6_integration.json"
        if s6_path.exists():
            print(f"\nStep 6: スキップ（既存の結果を使用: {s6_path}）")
        else:
            run_step6(args.model, groups, step4_results, step5_results)


def main():
    parser = argparse.ArgumentParser(
        description="SWOT分析の多人格エージェント・シミュレーション（シングルファシリテーター版）"
    )
    parser.add_argument(
        "--model", default="sonnet",
        help="使用するモデル (例: sonnet, claude:opus, ollama:qwen3:32b, ollama:qwen3:32b@host:port)"
    )
    parser.add_argument(
        "--steps", default="1,2,3,4,5,6",
        help="実行するステップ (例: 0,1,2,3,4,5,6 or 3 or 4,5,6)"
    )
    parser.add_argument(
        "--max-workers", type=int, default=5,
        help="Step 3の並列数 (default: 5)"
    )
    parser.add_argument(
        "--runs", type=int, default=20,
        help="実行するラン数 (default: 20)"
    )
    parser.add_argument(
        "--start-run", type=int, default=1,
        help="開始ラン番号 (default: 1)。複数マシンで分担する場合に使用"
    )
    parser.add_argument(
        "--config", required=True,
        help="コンフィグ名（必須）。同じ設定のラン結果をまとめるディレクトリ名 "
             "(例: honda_qwen3, honda_sonnet)"
    )
    parser.add_argument(
        "--config-desc", default=None,
        help="コンフィグの説明文。初回実行時に記録され、以降の実行時に表示される"
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="出力ディレクトリ（単一ラン用。--runsと併用不可）"
    )
    parser.add_argument(
        "--pdf", nargs="+", default=None,
        help="Step 0用: ケース文書のPDFパス（複数指定可。CASE_CONTEXTとFACTSを生成）"
    )
    parser.add_argument(
        "--personas", default=str(DATA_DIR / "personas.json"),
        help="ペルソナ定義ファイル (default: simulation/data/personas.json)"
    )
    parser.add_argument(
        "--generate-personas", nargs="+", metavar="PDF", default=None,
        help="PDFからペルソナを自動生成して --personas のパスに保存"
    )
    parser.add_argument(
        "--cross-swot-discussion", action="store_true", default=False,
        help="クロスSWOT戦略の導出をグループ討議で行う（R4: 戦略提案, R5: 相互修正）"
    )
    parser.add_argument(
        "--fact-mode", default="predefined", choices=["predefined", "predefined-no-hint", "extract", "deep-extract"],
        help="事実の取得方法（2軸: 本文=要約/全文 × 事実リスト=与える/自由抽出）: "
             "predefined=要約+20事実タグあり（デフォルト）, "
             "predefined-no-hint=要約+20事実タグなし, "
             "extract=要約のみ・各自が事実を自由抽出, "
             "deep-extract=ケース全文から自由抽出（全文は同梱しない）"
    )
    parser.add_argument(
        "--think", action="store_true", default=False,
        help="思考モード（<think>タグ）を有効にする。Ollamaではformatを使わずプロンプトで"
             "JSON指示し、done_reason=lengthでnum_predictを倍増してリトライ（最大3回）"
    )
    parser.add_argument(
        "--step5-mode", default="auto", choices=["auto", "individual", "facilitator"],
        help="Step 5（優先順位づけ）の方式: auto=方式のデフォルトに従う（SF=facilitator）, "
             "individual=各メンバーが個別順位を付けてファシリテーターが統合（step5_individual_rankings.jsonを生成）, "
             "facilitator=ファシリテーターが単独で決定。"
             "MR/SFが束ねているS4a（事実討議）とS5（順位参加）を独立に操作するためのフラグ"
    )
    args = parser.parse_args()

    if args.step5_mode == "auto":
        args.step5_mode = "facilitator"
    if args.step5_mode == "individual":
        STEP_FILES_SF[5] = ["step5_priorities.json", "step5_individual_rankings.json"]

    global _THINK, _FREE_EXTRACT, _SHOW_INTERNAL_TAG, _EXTRACT_CONTEXT
    _THINK = args.think
    _FREE_EXTRACT = args.fact_mode in ("extract", "deep-extract")
    _SHOW_INTERNAL_TAG = args.fact_mode == "predefined"

    if args.fact_mode == "deep-extract":
        fulltext_path = DATA_DIR / "case_fulltext.txt"
        if not fulltext_path.exists():
            print(f"ERROR: {fulltext_path} が見つかりません。"
                  f"先に --pdf でStep 0を実行するか、PDFから生成してください。",
                  file=sys.stderr)
            sys.exit(1)
        _EXTRACT_CONTEXT = fulltext_path.read_text(encoding="utf-8")

    steps = {int(s.strip()) for s in args.steps.split(",")}

    if args.pdf and 0 not in steps:
        steps.add(0)

    fact_mode_labels = {
        "predefined": "predefined（事前定義の事実リストを使用）",
        "predefined-no-hint": "predefined-no-hint（事前定義の事実リスト、内部/外部ヒントなし）",
        "extract": "extract（ペルソナがケース概要から事実を抽出・分類）",
        "deep-extract": f"deep-extract（ペルソナがケース全文から事実を抽出・分類、{len(_EXTRACT_CONTEXT or '')}文字）",
    }
    print(f"方式: シングルファシリテーター (SF)")
    print(f"モデル: {describe_model(args.model)}")
    print(f"事実モード: {fact_mode_labels[args.fact_mode]}")
    if args.step5_mode != "facilitator":
        print(f"Step 5方式: 個別ランキング + 統合（--step5-mode {args.step5_mode}）")
    if _THINK:
        print(f"思考モード: 有効（think:true）")
    print(f"ステップ: {sorted(steps)}")
    print(f"ペルソナ: {args.personas}")

    global CASE_CONTEXT

    if args.generate_personas:
        run_generate_personas(args.generate_personas, args.personas, args.model)

    if 0 in steps:
        if not args.pdf:
            print("ERROR: Step 0には --pdf でPDFファイルを指定してください。",
                  file=sys.stderr)
            sys.exit(1)
        case_context, facts = run_step0(args.pdf, DATA_DIR, args.model)
        CASE_CONTEXT = case_context

    if 1 in steps:
        case_context, personas, facts = run_step1(args.personas)
        CASE_CONTEXT = case_context
    else:
        case_context, personas, facts = load_data(args.personas)
        CASE_CONTEXT = case_context
        print(f"  入力データ: {args.personas} ({len(personas)}人), {DATA_DIR}/facts.json ({len(facts)}項目)")

    config_name = args.config
    config_dir = BASE_DIR / config_name
    print(f"コンフィグ: {config_name}")

    config_record = build_config_record(args.model, args.personas, DATA_DIR, args.config_desc)
    config_record["step5_mode"] = args.step5_mode
    save_and_verify_config(config_dir, config_record)

    def _update_resolved_model_id():
        resolved = get_resolved_model_id(args.model)
        if resolved:
            config_path = config_dir / "config.json"
            if config_path.exists():
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                if not cfg.get("resolved_model_id"):
                    cfg["resolved_model_id"] = resolved
                    config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"  resolved_model_id 記録: {resolved}")

    if args.output_dir:
        output_dir = Path(args.output_dir)
        print_run_status(1, 1, output_dir, steps)
        run_single(args, steps, output_dir, personas, facts)
        _update_resolved_model_id()
        print(f"\n=== 完了 ===")
        print(f"出力先: {output_dir}/")
    else:
        start = args.start_run
        end = start + args.runs - 1
        print(f"ラン: run{start}〜run{end}（{args.runs}回）")
        completed = 0
        skipped = 0
        for i in range(start, end + 1):
            output_dir = config_dir / f"sf_run{i}"
            all_done = print_run_status(i, end, output_dir, steps)
            if all_done:
                skipped += 1
                continue
            run_single(args, steps, output_dir, personas, facts)
            if completed == 0:
                _update_resolved_model_id()
            completed += 1
            print(f"\n  Run {i}/{end} 完了")
        print(f"\n{'='*60}")
        print(f"  全ラン完了: 実行={completed}, スキップ={skipped}, 合計={args.runs}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
