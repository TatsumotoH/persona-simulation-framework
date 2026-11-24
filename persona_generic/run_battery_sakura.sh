#!/bin/bash
# サクラ食品ケースで基本3検査を1モデルぶん通す。
#
#   ./run_battery_sakura.sh "<model-spec>" <tag> [max_workers]
#
# 例:
#   ./run_battery_sakura.sh "codex:gpt-5.6-terra" sakura_gpt56terra 3
#   ./run_battery_sakura.sh "ollama:qwen3:32b" sakura_qwen32b 1
#
# 表出テスト（検査1＋検査3、204呼び出し）→ 法則テスト（検査2、324呼び出し）の順。
# 表出テストが全滅したら法則テストは意味がないので、そこで止める。
set -u
cd "$(dirname "$0")/.." || exit 1

MODEL="$1"; TAG="$2"; MW="${3:-3}"
LOG="persona_generic/results/battery_${TAG}.log"
mkdir -p persona_generic/results

echo "=== ${TAG} : ${MODEL} ===" | tee "$LOG"
date | tee -a "$LOG"

echo "--- 検査1・3 表出＋信念更新（204呼び出し） ---" | tee -a "$LOG"
python3 -u persona_screening.py --model "$MODEL" --tag "$TAG" \
  --stimuli persona_generic/data/persona_check_sakura_v1.json \
  --no-internal-tag --max-workers "$MW" 2>&1 | tee -a "$LOG"

# 表出テストの結果が書き出されていなければ、法則テストへ進まない
if [ ! -s "simulation/persona_screening/${TAG}/screening_summary.json" ]; then
  echo "!! 表出テストの出力がない。法則テストは行わない" | tee -a "$LOG"
  date | tee -a "$LOG"
  exit 1
fi

echo "--- 検査2 法則（324呼び出し） ---" | tee -a "$LOG"
python3 -u run_law_generic.py --model "$MODEL" --tag "$TAG" \
  --max-workers "$MW" 2>&1 | tee -a "$LOG"

echo "=== ${TAG} 完了 ===" | tee -a "$LOG"
date | tee -a "$LOG"
