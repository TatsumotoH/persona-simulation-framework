#!/bin/bash
# ケース2（ホンダ）を製品ファミリー単位で順に回す。
#
#   bash run_honda_case2_family.sh claude|gpt|gemini|qwen
#
# ファミリーごとに1本の流れにし、同時に走るのは各ファミリー1モデル（5並列）とする。
# これはケース1のときと同じ負荷である。

set -u
cd "$(dirname "$0")" || exit 1

case "${1:?claude / gpt / gemini / qwen のいずれかを指定してください}" in
  claude) JOBS=("sonnet honda_sonnet" "opus honda_opus" "haiku honda_haiku") ;;
  gpt)    JOBS=("codex:gpt-5.6-terra honda_gpt56terra"
                "codex:gpt-5.6-sol honda_gpt56sol"
                "codex:gpt-5.6-luna honda_gpt56luna") ;;
  gemini) JOBS=("agy:Gemini 3.1 Pro (High) honda_gemini31pro"
                "agy:Gemini 3.5 Flash (Medium) honda_gemini35flash") ;;
  qwen)   JOBS=("ollama:qwen3:32b honda_qwen32b") ;;
  *) echo "不明なファミリー: $1" >&2; exit 1 ;;
esac

for job in "${JOBS[@]}"; do
  TAG="${job##* }"          # 末尾の語がタグ
  MODEL="${job% *}"         # それ以外がモデル指定（空白を含みうる）
  echo "################ ${TAG} 開始 $(date '+%F %T') ################"
  bash run_honda_case2.sh "${MODEL}" "${TAG}"
  echo "################ ${TAG} 終了 $(date '+%F %T') ################"
done

echo "===== ファミリー $1 のケース2 完了 $(date '+%F %T') ====="
