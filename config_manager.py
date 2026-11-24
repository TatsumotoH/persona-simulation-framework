"""
Configuration Management -- コンフィグごとにラン結果を分離

ディレクトリ構造:
  simulation/
    data/                           入力データ（共有）
    <config_name>/                  コンフィグ単位
      config.json                   設定の記録
      mr_run1/ / sf_run1/           ラン結果
"""

import hashlib
import json
import re
import sys
from pathlib import Path


def sanitize_config_name(model_spec):
    """モデル指定からデフォルトのコンフィグ名を生成"""
    name = model_spec
    name = re.sub(r"@[^/]+", "", name)
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name


def _file_hash(path):
    """ファイルの内容からSHA256ハッシュ（先頭12文字）を返す"""
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def _extract_case_title(data_dir):
    """case_context.txt の先頭行からケースタイトルを抽出"""
    ctx_path = Path(data_dir) / "case_context.txt"
    if not ctx_path.exists():
        return None
    first_line = ctx_path.read_text(encoding="utf-8").strip().split("\n")[0]
    for prefix in ["【ケース概要】", "【ケース】"]:
        if first_line.startswith(prefix):
            first_line = first_line[len(prefix):]
    return first_line.strip()


def auto_description(model_spec, personas_path, data_dir):
    """設定情報から説明文を自動生成"""
    from llm_backend import describe_model
    parts = [describe_model(model_spec)]

    title = _extract_case_title(data_dir)
    if title:
        parts.insert(0, title)

    p = Path(personas_path)
    if p.exists():
        personas = json.loads(p.read_text(encoding="utf-8"))
        parts.append(f"ペルソナ{len(personas)}人")

    f = Path(data_dir) / "facts.json"
    if f.exists():
        facts = json.loads(f.read_text(encoding="utf-8"))
        parts.append(f"事実{len(facts)}項目")

    return " / ".join(parts)


def build_config_record(model_spec, personas_path, data_dir, description=None, resolved_model_id=None):
    """現在の設定からconfig.jsonに保存するレコードを作成"""
    personas_path = Path(personas_path)
    data_dir = Path(data_dir)

    record = {
        "model": model_spec,
        "resolved_model_id": resolved_model_id,
        "personas_file": str(personas_path),
        "personas_hash": _file_hash(personas_path),
        "facts_hash": _file_hash(data_dir / "facts.json"),
        "case_context_hash": _file_hash(data_dir / "case_context.txt"),
    }

    record["description"] = description or auto_description(model_spec, personas_path, data_dir)

    if personas_path.exists():
        personas = json.loads(personas_path.read_text(encoding="utf-8"))
        record["personas_count"] = len(personas)

    facts_path = data_dir / "facts.json"
    if facts_path.exists():
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        record["facts_count"] = len(facts)

    return record


def save_and_verify_config(config_dir, record):
    """config.jsonを保存、または既存と比較して不一致なら警告"""
    config_dir = Path(config_dir)
    config_path = config_dir / "config.json"

    if not config_path.exists():
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  コンフィグ保存: {config_path}")
        return True

    existing = json.loads(config_path.read_text(encoding="utf-8"))

    if existing.get("description"):
        print(f"  説明: {existing['description']}")

    mismatches = []
    for key in ["model", "personas_hash", "facts_hash", "case_context_hash"]:
        old_val = existing.get(key)
        new_val = record.get(key)
        if old_val and new_val and old_val != new_val:
            mismatches.append(f"  {key}: {old_val} -> {new_val}")

    if mismatches:
        print(f"\nWARNING: コンフィグ不一致（{config_path}）", file=sys.stderr)
        for m in mismatches:
            print(m, file=sys.stderr)
        print("既存のラン結果と設定が異なります。", file=sys.stderr)
        print("別の --config 名を指定するか、既存結果を削除してください。", file=sys.stderr)
        sys.exit(1)

    updated = False
    if record.get("resolved_model_id") and not existing.get("resolved_model_id"):
        existing["resolved_model_id"] = record["resolved_model_id"]
        updated = True
    if record.get("description") and record["description"] != existing.get("description"):
        existing["description"] = record["description"]
        updated = True
    if updated:
        config_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return True
