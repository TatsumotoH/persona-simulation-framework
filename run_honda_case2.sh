#!/bin/bash
# ホンダ版・汎用ペルソナ検査（ケース2）を1モデル分まとめて回す。
#
#   bash run_honda_case2.sh <model> <tag>
#   例: bash run_honda_case2.sh sonnet honda_sonnet
#
# 基本3検査：
#   表出テスト・信念更新テスト … persona_screening.py（同じスクリプトで同時に走る）
#   法則テスト                 … run_law_generic.py --case honda
#
# **--no-internal-tag は必須。**ケース1（サクラ食品）と手続きを揃えるためであり、
# 付け忘れると内部/外部のヒントで答えの選択肢が半分に絞られ、比較できなくなる。

set -u
cd "$(dirname "$0")" || exit 1

MODEL="${1:?モデル名を指定してください}"
TAG="${2:?タグを指定してください}"
STIM="persona_generic/data/persona_check_honda_v1.json"
LOG="persona_generic/results/honda_case2_${TAG}.log"

mkdir -p persona_generic/results

{
  echo "=== ケース2（ホンダ二輪ASEAN）: ${TAG} ==="
  echo "開始 $(date '+%F %T')"

  echo "--- 表出テスト＋信念更新テスト（204呼び出し）---"
  python3 persona_screening.py \
      --stimuli "${STIM}" \
      --model "${MODEL}" --tag "${TAG}" \
      --no-internal-tag --max-workers 5
  echo "表出＋信念更新 終了コード=$? $(date '+%F %T')"

  echo "--- 法則テスト（324呼び出し）---"
  python3 run_law_generic.py \
      --case honda --model "${MODEL}" --tag "${TAG}" \
      --reps 12 --max-workers 5
  echo "法則 終了コード=$? $(date '+%F %T')"

  echo "=== 完了 $(date '+%F %T') ==="
} 2>&1 | tee -a "${LOG}"
