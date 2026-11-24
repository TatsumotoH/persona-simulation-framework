#!/usr/bin/env python3
"""
SWOT分析シミュレーション — 統合ランナー

マルチラウンド（MR）方式とシングルファシリテーター（SF）方式を
選択的・同時に実行する。

使い方:
  python run_simulation.py --config honda --model claude-sonnet-5 --runs 10  # バージョン指定（推奨）
  python run_simulation.py --config honda --method mr                        # MR方式のみ
  python run_simulation.py --config honda --method sf                        # SF方式のみ
  python run_simulation.py --config honda --model ollama:qwen3:32b --runs 10 # ローカルLLM

  # 2台で分担実行:
  # machine A: python run_simulation.py --config honda --model claude-sonnet-5 --start-run 1  --runs 10
  # machine B: python run_simulation.py --config honda --model claude-sonnet-5 --start-run 11 --runs 10

  # モデル指定の再現性:
  #   sonnet, haiku, opus       → エイリアス（時期により異なるバージョンに解決）
  #   claude-sonnet-5           → バージョン固定（推奨）
  #   claude-sonnet-4-5-20250514 → 完全なモデルID（最も厳密）
"""

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

METHODS = {
    "mr": ("マルチラウンド (MR)", "run_agents_multiround.py"),
    "sf": ("シングルファシリテーター (SF)", "run_agents_single_facilitator.py"),
}


def main():
    parser = argparse.ArgumentParser(
        description="SWOT分析シミュレーション — MR方式・SF方式の統合ランナー",
        epilog="上記以外の引数（--runs, --model, --pdf, --personas 等）は\n"
               "各方式のスクリプトにそのまま渡されます。\n"
               "詳細: python run_agents_multiround.py --help",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--method", default="both", choices=["mr", "sf", "both"],
        help="実行方式: mr=マルチラウンド, sf=シングルファシリテーター, both=両方 (default: both)"
    )
    parser.add_argument(
        "--start-run", type=int, default=None,
        help="開始ラン番号 (default: 1)。複数マシンで分担する場合に使用"
    )
    parser.add_argument(
        "--config", required=True,
        help="コンフィグ名（必須）。同じ設定のラン結果をまとめるディレクトリ名 "
             "(例: honda_qwen3, honda_sonnet)"
    )
    parser.add_argument(
        "--config-desc", default=None,
        help="コンフィグの説明文。初回実行時に記録され、以降の実行時に表示される "
             "(例: 'ホンダ二輪ケース／Qwen3 32B／デフォルトペルソナ30人')"
    )
    args, remaining = parser.parse_known_args()

    if args.start_run is not None:
        remaining += ["--start-run", str(args.start_run)]
    remaining += ["--config", args.config]
    if args.config_desc is not None:
        remaining += ["--config-desc", args.config_desc]

    if args.method == "both":
        targets = ["mr", "sf"]
    else:
        targets = [args.method]

    labels = [METHODS[t][0] for t in targets]
    print(f"実行方式: {' + '.join(labels)}")
    print(f"{'='*60}")

    for t in targets:
        label, script = METHODS[t]
        script_path = SCRIPT_DIR / script

        print(f"\n{'='*60}")
        print(f"  {label} 方式を開始")
        print(f"{'='*60}")

        result = subprocess.run(
            [sys.executable, str(script_path)] + remaining,
        )

        if result.returncode != 0:
            print(f"\nERROR: {label} が失敗しました (exit code: {result.returncode})",
                  file=sys.stderr)
            sys.exit(result.returncode)

        print(f"\n  {label} 方式 完了")

    print(f"\n{'='*60}")
    print(f"  全方式完了: {' + '.join(labels)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
