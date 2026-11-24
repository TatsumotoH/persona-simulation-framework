"""
SWOT分析シミュレーション — 共通データ定義 & Step 0 データ生成

Step 0: PDFからCASE_CONTEXT・FACTS・PERSONASを自動生成
Step 1: デフォルトデータの定義（ホンダ二輪ケース）

run_agents_multiround.py / run_agents_single_facilitator.py から参照される。
"""

import json
from pathlib import Path

from llm_backend import call_llm

# --- Step 0: PDFからデータ自動生成 ---

CASE_CONTEXT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "context": {"type": "string"},
    },
    "required": ["title", "context"],
    "additionalProperties": False,
}

FACTS_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact_id": {"type": "integer"},
                    "label": {"type": "string"},
                    "description": {"type": "string"},
                    "internal": {"type": "boolean"},
                },
                "required": ["fact_id", "label", "description", "internal"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}

PERSONAS_SCHEMA = {
    "type": "object",
    "properties": {
        "personas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "profile": {"type": "string"},
                },
                "required": ["id", "name", "category", "profile"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["personas"],
    "additionalProperties": False,
}


def _call_model(system_prompt, user_prompt, schema, model="sonnet"):
    return call_llm(system_prompt, user_prompt, schema, model)


def extract_pdf_text(pdf_paths):
    """PDFファイルからテキストを抽出"""
    import pdfplumber

    all_text = []
    for path in pdf_paths:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"PDFファイルが見つかりません: {path}")
        print(f"  PDF読み込み: {p.name}")
        with pdfplumber.open(p) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_text.append(text)
    return "\n\n".join(all_text)


def generate_case_context(pdf_text, model="sonnet"):
    """PDFテキストからケース概要を生成"""
    system = (
        "あなたは経営学のケーススタディ分析の専門家です。\n"
        "与えられたケース文書を読み、SWOT分析のための簡潔なケース概要を作成してください。"
    )
    user = (
        f"以下のケース文書のテキストを読み、SWOT分析シミュレーションに使用する"
        f"ケース概要を作成してください。\n\n"
        f"要件：\n"
        f"- titleにはケースのタイトル（著者・年を含む）を記載\n"
        f"- contextには、SWOT分析に必要な情報を網羅した概要（400〜800字程度）を記載\n"
        f"- 企業の内部環境（強み・弱み）と外部環境（機会・脅威）の両面をカバーすること\n"
        f"- 具体的な数字・固有名詞を含めること\n\n"
        f"【ケース文書】\n{pdf_text}"
    )
    result, cost = _call_model(system, user, CASE_CONTEXT_SCHEMA, model)
    print(f"  ケース概要生成 ... done (${cost:.4f})")
    return result


def generate_facts(pdf_text, case_context, model="sonnet"):
    """PDFテキストからSWOT分析対象の事実一覧を生成"""
    system = (
        "あなたは経営学のケーススタディ分析の専門家です。\n"
        "ケース文書からSWOT分析の対象となる事実を抽出してください。"
    )
    user = (
        f"以下のケース文書から、SWOT分析の対象となる重要な事実を15〜25個抽出してください。\n\n"
        f"要件：\n"
        f"- 各事実にfact_id（1から連番）、label（短いラベル）、description（詳細な記述）を付与\n"
        f"- internalフラグ：企業の内部要因ならtrue、外部環境要因ならfalse\n"
        f"- 内部要因（技術力、戦略、組織能力、弱みなど）と外部要因（市場変化、競合、規制、マクロ環境など）を\n"
        f"  バランスよく含めること\n"
        f"- 各事実は具体的な数字や固有名詞を含む客観的な記述にすること\n"
        f"- S/W/O/Tのどれに該当するかは分析者によって異なりうるため、ここでは分類しないこと\n\n"
        f"【ケース概要】\n{case_context}\n\n"
        f"【ケース文書全文】\n{pdf_text}"
    )
    result, cost = _call_model(system, user, FACTS_SCHEMA, model)
    print(f"  事実抽出 ... {len(result['facts'])}項目 (${cost:.4f})")
    return result["facts"]


def generate_personas(pdf_text, case_context, facts, model="sonnet"):
    """ケースに適したペルソナ一覧を生成"""
    facts_summary = "\n".join(
        f"  {f['fact_id']}. {f['label']}（{'内部' if f['internal'] else '外部'}）"
        for f in facts
    )
    system = (
        "あなたは経営学のケーススタディ分析と組織論の専門家です。\n"
        "ケースのSWOT分析を多角的に行うためのペルソナ（分析者の人格）を設計してください。"
    )
    user = (
        f"以下のケースについて、SWOT分析を多角的に行うためのペルソナを25〜35人設計してください。\n\n"
        f"要件：\n"
        f"- 各ペルソナにid（1から連番）、name（役職名＋識別子）、category（所属カテゴリ）、\n"
        f"  profile（50〜100字の自然言語プロファイル）を付与\n"
        f"- categoryは以下の6つに分類：\n"
        f"  本社系 / 事業推進系 / 財務系 / 現地系 / 技術系 / 外部・革新系\n"
        f"- 各カテゴリに最低3人、多くても7人程度を配置\n"
        f"- profileには、職歴・専門性・価値観・信条を含め、\n"
        f"  同じ事実を見ても異なるSWOT分類をするであろう多様な視点を反映させること\n"
        f"- ケースの企業・業界・市場に適した具体的な役職名にすること\n\n"
        f"【ケース概要】\n{case_context}\n\n"
        f"【抽出された事実一覧】\n{facts_summary}\n\n"
        f"【ケース文書全文】\n{pdf_text}"
    )
    result, cost = _call_model(system, user, PERSONAS_SCHEMA, model)
    print(f"  ペルソナ生成 ... {len(result['personas'])}人 (${cost:.4f})")
    return result["personas"]


def run_step0(pdf_paths, data_dir, model="sonnet"):
    """Step 0: PDFからCASE_CONTEXTとFACTSを自動生成して保存"""
    print(f"\n=== Step 0: PDFからケース概要・事実を自動生成 ===")
    print(f"  対象PDF: {', '.join(str(p) for p in pdf_paths)}")

    pdf_text = extract_pdf_text(pdf_paths)
    print(f"  抽出テキスト: {len(pdf_text)}文字")

    ctx = generate_case_context(pdf_text, model)
    case_context = f"【ケース概要】{ctx['title']}\n\n{ctx['context']}"

    facts = generate_facts(pdf_text, case_context, model)

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    ctx_path = data_dir / "case_context.txt"
    ctx_path.write_text(case_context, encoding="utf-8")
    print(f"  -> {ctx_path}")

    fulltext_path = data_dir / "case_fulltext.txt"
    fulltext_path.write_text(pdf_text, encoding="utf-8")
    print(f"  -> {fulltext_path} ({len(pdf_text)}文字)")

    f_path = data_dir / "facts.json"
    f_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {f_path}")

    return case_context, facts


def run_generate_personas(pdf_paths, output_path, model="sonnet"):
    """PDFからペルソナを自動生成してファイルに保存"""
    print(f"\n=== ペルソナ自動生成 ===")
    print(f"  対象PDF: {', '.join(str(p) for p in pdf_paths)}")

    pdf_text = extract_pdf_text(pdf_paths)
    print(f"  抽出テキスト: {len(pdf_text)}文字")

    ctx = generate_case_context(pdf_text, model)
    case_context = f"【ケース概要】{ctx['title']}\n\n{ctx['context']}"

    facts = generate_facts(pdf_text, case_context, model)
    personas = generate_personas(pdf_text, case_context, facts, model)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(personas, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {output_path} ({len(personas)}人)")

    return personas


# --- デフォルトデータ定義（ホンダ二輪ケース） ---

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

PERSONAS = [
    {"id": 1, "name": "品質重視役員A", "category": "本社系",
     "profile": "本社取締役。品質管理30年。ホンダの「技術のホンダ」ブランドを最重視。品質問題のリコール経験あり。低価格化でブランドが毀損されることを最も恐れる。"},
    {"id": 2, "name": "品質重視役員B", "category": "本社系",
     "profile": "本社常務。ブランド戦略担当。欧米市場でのプレミアムポジショニングの成功体験を持つ。新興国での「安売り」がグローバルブランドに波及することを懸念。"},
    {"id": 3, "name": "品質重視役員C", "category": "本社系",
     "profile": "本社専務。生産品質統括。「一度下げた品質基準は元に戻せない」が信条。工場の品質管理体制を長年築いてきた。"},
    {"id": 4, "name": "ブランド戦略部長A", "category": "本社系",
     "profile": "ブランド戦略部長。カブの世界的ブランド価値を管理。サブブランド戦略の専門家。低価格帯への参入にはブランド・アーキテクチャの再設計が必要と主張。"},
    {"id": 5, "name": "ブランド戦略部長B", "category": "本社系",
     "profile": "広報・IR担当部長。投資家やメディアへのブランドメッセージの一貫性を重視。低価格モデルの報道がグローバルでのブランド認知にどう影響するかを気にする。"},
    {"id": 6, "name": "シェア拡大派事業部長A", "category": "事業推進系",
     "profile": "二輪事業本部長。ASEAN市場での販売台数拡大が最重要KPI。タイでのWave 100成功を主導した実績。「シェアを取らなければ何も始まらない」が持論。"},
    {"id": 7, "name": "シェア拡大派事業部長B", "category": "事業推進系",
     "profile": "海外事業統括。新興国市場のポートフォリオを管理。インドネシア、インドでの市場拡大経験。スピード最優先の意思決定スタイル。"},
    {"id": 8, "name": "シェア拡大派事業部長C", "category": "事業推進系",
     "profile": "ASEAN地域本部長。タイを拠点にASEAN全域を統括。各国の市場特性を熟知。プラットフォーム戦略の推進者。"},
    {"id": 9, "name": "営業本部長A", "category": "事業推進系",
     "profile": "グローバル営業本部長。ディーラー網の拡大と販売台数の最大化が使命。「製品はあっても売る場所がなければ意味がない」が持論。"},
    {"id": 10, "name": "営業本部長B", "category": "事業推進系",
     "profile": "ASEAN営業統括。各国のディーラーとの直接的な関係を持つ。中国車に顧客を奪われているディーラーの悲痛な声を日々聞いている。"},
    {"id": 11, "name": "マーケティング部長A", "category": "事業推進系",
     "profile": "二輪マーケティング部長。消費者調査とセグメンテーションの専門家。ベトナム市場の消費者層の分析から、低価格帯に巨大な潜在需要があると確信。"},
    {"id": 12, "name": "マーケティング部長B", "category": "事業推進系",
     "profile": "デジタルマーケティング責任者。新興国市場での口コミ効果と、中国車の品質問題報道が消費者心理に与える影響を分析。ブランドスイッチの好機と捉えている。"},
    {"id": 13, "name": "CFO_A", "category": "財務系",
     "profile": "最高財務責任者。すべての投資をROIとNPVで評価。リーマンショック後のホンダの連結売上高激減を経験し、財務規律を重視。「最悪シナリオで回収できる範囲に投資を抑えよ」が原則。"},
    {"id": 14, "name": "CFO_B", "category": "財務系",
     "profile": "財務企画部長。グローバルポートフォリオの中での資源配分最適化を担当。ベトナムへの投資とインド・インドネシアへの投資の機会費用を常に比較。"},
    {"id": 15, "name": "経営企画部長A", "category": "財務系",
     "profile": "経営企画部長。中期経営計画の策定を統括。ASEAN事業の成長シナリオを複数描き、投資の段階的実行を設計。リスクシナリオの策定に長けている。"},
    {"id": 16, "name": "経営企画部長B", "category": "財務系",
     "profile": "事業戦略部長。M&Aとアライアンスの専門家。ベトナムでの合弁パートナーや調達先の選定を担当。制度リスクと為替リスクに敏感。"},
    {"id": 17, "name": "ベトナム現地GM", "category": "現地系",
     "profile": "ホンダベトナムのGM（駐在員）。ハノイで中国車が溢れる光景を毎日目にする。ディーラーからの悲鳴を受け続けている。本社の「売れる人に売る」方針に強い不満。カブがベトナム人の生活にどれほど根付いているかを肌で理解。"},
    {"id": 18, "name": "ベトナム現地GM_B", "category": "現地系",
     "profile": "ホンダベトナムの副GM。ベトナム人スタッフとの日常的なやり取りから、一般消費者の所得水準や生活実態を深く理解。550ドルの中国車でさえ庶民にとっては大きな買い物だと知っている。"},
    {"id": 19, "name": "現地営業マネージャーA", "category": "現地系",
     "profile": "ベトナム北部の営業マネージャー。ハノイとその周辺のディーラーを統括。都市部の渋滞事情と消費者ニーズに精通。時速80km以上の性能は不要だと確信している。"},
    {"id": 20, "name": "現地営業マネージャーB", "category": "現地系",
     "profile": "ベトナム南部の営業マネージャー。ホーチミンと農村部のディーラーを統括。農村部での中国車の浸透度を目の当たりにしている。農村部のニーズは都市部と異なり、耐久性と積載能力が最重要。"},
    {"id": 21, "name": "現地調達マネージャー", "category": "現地系",
     "profile": "ベトナム現地の調達責任者。現地部品メーカーの技術水準、中国からの部品輸入の実態を熟知。コスト構造の改善可能性と限界を具体的に理解している。"},
    {"id": 22, "name": "R&DエンジニアA", "category": "技術系",
     "profile": "HRS-T（タイR&Dセンター）のシニアエンジニア。4ストロークエンジン開発の中心人物。「4スト宣言」の実現を技術面で支えた。性能・信頼性への妥協を許さない。"},
    {"id": 23, "name": "R&DエンジニアB", "category": "技術系",
     "profile": "本社の二輪設計部のエンジニア。プラットフォーム設計の専門家。部品共通化と各国仕様の最適化のバランスを設計する立場。技術的合理性を重視。"},
    {"id": 24, "name": "生産技術部長A", "category": "技術系",
     "profile": "タイ工場の生産技術部長。現地調達率96.8%を実現した生産システムの設計者。コスト削減と品質維持の両立に関する実務的知見が豊富。"},
    {"id": 25, "name": "生産技術部長B", "category": "技術系",
     "profile": "ベトナム工場の生産技術マネージャー。ベトナムの労働力の技能水準、部品品質のばらつきなど、現地生産の課題を日々経験している。"},
    {"id": 26, "name": "品質保証マネージャー", "category": "技術系",
     "profile": "品質保証部門の責任者。3年3万km保証の設計者。完成車の全数検査と市場品質データの分析を統括。中国部品の採用に対して最も慎重な立場。"},
    {"id": 27, "name": "外部コンサルタントA", "category": "外部・革新系",
     "profile": "大手戦略コンサルのパートナー。クリステンセンの「イノベーションのジレンマ」の観点からホンダを分析。過去の成功体験が変革の最大の障壁になると指摘する立場。"},
    {"id": 28, "name": "外部コンサルタントB", "category": "外部・革新系",
     "profile": "新興国市場戦略の専門コンサルタント。プラハラードの「BOP（Bottom of Pyramid）」理論に精通。P&G、ユニリーバの新興国成功事例との比較分析を得意とする。"},
    {"id": 29, "name": "新興国市場アナリスト", "category": "外部・革新系",
     "profile": "証券会社のASEAN市場担当アナリスト。ベトナム経済の成長トレンド、規制環境の変化、消費者動向を定量的に分析。投資家目線でホンダのベトナム戦略を評価する。"},
    {"id": 30, "name": "社外取締役", "category": "外部・革新系",
     "profile": "他業界（消費財メーカー）出身の社外取締役。異業種での新興国展開経験を持つ。ホンダの組織文化を外部の目で見て、「品質へのこだわり」が変革を阻害している可能性を指摘できる立場。"},
]

