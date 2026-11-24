"""
LLM Backend Abstraction -- Claude CLI / Ollama HTTP API / vLLM (OpenAI互換API)

model_spec format:
  claude-sonnet-5                   -> Claude CLI (versioned, recommended)
  claude-sonnet-4-5-20250514        -> Claude CLI (exact model ID)
  sonnet / haiku / opus             -> Claude CLI (alias, resolved at runtime)
  claude:sonnet                     -> Claude CLI
  ollama:qwen3:32b                  -> Ollama localhost:11434
  ollama:qwen3:32b@host             -> Ollama on host:11434
  ollama:qwen3:32b@host:port        -> Ollama on host:port
  vllm:Qwen/Qwen3-32B              -> vLLM localhost:8000
  vllm:Qwen/Qwen3-32B@host:port    -> vLLM on host:port
  codex:gpt-5.6-terra              -> Codex CLI
  agy:Gemini 3.1 Pro (High)        -> Antigravity CLI (モデル名は表示名に完全一致)
"""

import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error

CLAUDE_SHORTNAMES = {"sonnet", "haiku", "opus", "fable"}

_resolved_model_ids = {}

def _find_claude_cli():
    found = shutil.which("claude")
    if found:
        return found
    for candidate in [
        os.path.expanduser("~/.nvm/versions/node/v20.20.2/bin/claude"),
        "/usr/local/bin/claude",
    ]:
        if os.path.isfile(candidate):
            return candidate
    return "claude"


def parse_model_spec(model_spec):
    """Parse model specification into (backend, model_name, host).

    Returns:
        ("claude", model_name, None)
        ("ollama", model_name, "host:port")
        ("vllm",   model_name, "host:port")
    """
    if model_spec in CLAUDE_SHORTNAMES:
        return "claude", model_spec, None

    if model_spec.startswith("claude:"):
        return "claude", model_spec[7:], None

    if model_spec.startswith("ollama:"):
        rest = model_spec[7:]
        if "@" in rest:
            model_part, host_part = rest.rsplit("@", 1)
            if ":" not in host_part:
                host_part += ":11434"
            return "ollama", model_part, host_part
        return "ollama", rest, "localhost:11434"

    if model_spec.startswith("codex:"):
        return "codex", model_spec[6:], None

    if model_spec.startswith("agy:"):
        return "agy", model_spec[4:], None

    if model_spec.startswith("vllm:"):
        rest = model_spec[5:]
        if "@" in rest:
            model_part, host_part = rest.rsplit("@", 1)
            if ":" not in host_part:
                host_part += ":8000"
            return "vllm", model_part, host_part
        return "vllm", rest, "localhost:8000"

    return "claude", model_spec, None


def _extract_json(text):
    """テキストからJSONオブジェクトを抽出する。"""
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


_TRANSIENT_MARKERS = (
    "api_error", "overloaded", "rate_limit", "429", "500", "502", "503", "529",
    "Connection error", "timeout",
)


def _is_transient_api_error(detail):
    """一時的で再試行すれば消える種類のエラーか。認証切れや権限拒否は含めない。"""
    if "Not logged in" in detail or "disabled Claude subscription" in detail:
        return False
    return any(m in detail for m in _TRANSIENT_MARKERS)


def _make_schema_instruction(schema):
    """遅延制約用のスキーマ指示テキストを生成する。"""
    schema_text = json.dumps(schema, ensure_ascii=False, indent=2)
    return (
        "\n\n【出力形式の指示（厳守）】\n"
        "以下のJSONスキーマに厳密に従い、有効なJSONオブジェクトのみを出力してください。\n"
        "説明文、質問、マークダウン、コードフェンス(```)は一切不要です。\n"
        "質問や確認を返さないでください。与えられた情報だけを使ってください。\n"
        "出力はJSONオブジェクトのみです。\n"
        f"スキーマ:\n{schema_text}"
    )


def _call_claude_delayed_constraint(system_prompt, user_prompt, schema, model, timeout):
    """遅延制約パターン: --json-schema を使わず、プロンプトでJSON形式を指示して自前パース。"""
    augmented_system = system_prompt + _make_schema_instruction(schema)
    env = os.environ.copy()
    env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = "64000"
    result = subprocess.run(
        [
            _find_claude_cli(), "-p",
            "--model", model,
            "--output-format", "json",
            "--no-session-persistence",
            "--system-prompt", augmented_system,
        ],
        input=user_prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if result.returncode != 0:
        detail = result.stderr[:500] or result.stdout[:500]
        raise RuntimeError(f"claude CLI error (delayed constraint, exit {result.returncode}): {detail}")

    output = json.loads(result.stdout)
    if output.get("is_error"):
        raise RuntimeError(f"Claude error (delayed constraint): {output.get('result', 'unknown')[:500]}")

    cost = output.get("total_cost_usd", 0)
    raw = output.get("result", "")
    parsed = _extract_json(raw)
    if parsed is not None:
        return parsed, cost

    raise RuntimeError(
        f"Claude (delayed constraint): JSONの抽出に失敗しました。\n"
        f"Result: {str(raw)[:500]}"
    )


def _call_claude(system_prompt, user_prompt, schema, model, timeout, _attempt=0):
    # 一時的なAPIエラー（output_tokens=0 / terminal_reason=api_error）は指数バックオフで再試行する。
    _MAX_RETRY = 4
    # Haiku: --json-schema causes excessive CLI internal retries (especially Step 6).
    # Route to delayed constraint for reliable, faster execution.
    if "haiku" in model.lower():
        print(f"  [haiku] --json-schema をスキップ → 遅延制約パターンで実行", file=sys.stderr)
        return _call_claude_delayed_constraint(system_prompt, user_prompt, schema, model, timeout)

    schema_json = json.dumps(schema, ensure_ascii=False)
    env = os.environ.copy()
    env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = "64000"
    result = subprocess.run(
        [
            _find_claude_cli(), "-p",
            "--model", model,
            "--json-schema", schema_json,
            "--output-format", "json",
            "--no-session-persistence",
            "--system-prompt", system_prompt,
        ],
        input=user_prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if result.returncode != 0:
        detail = result.stderr[:500] or result.stdout[:500]
        if "error_max_structured_output_retries" in detail:
            print(
                f"  [fallback] --json-schema 失敗 → 遅延制約パターンで再試行",
                file=sys.stderr,
            )
            return _call_claude_delayed_constraint(
                system_prompt, user_prompt, schema, model, timeout
            )
        if _is_transient_api_error(detail) and _attempt < _MAX_RETRY:
            wait = 5 * (2 ** _attempt) + random.uniform(0, 5)
            print(f"  [retry {_attempt + 1}/{_MAX_RETRY}] 一時的なAPIエラー → {wait:.0f}秒待って再試行",
                  file=sys.stderr)
            time.sleep(wait)
            return _call_claude(system_prompt, user_prompt, schema, model, timeout,
                                _attempt=_attempt + 1)
        raise RuntimeError(f"claude CLI error (exit {result.returncode}): {detail}")

    output = json.loads(result.stdout)
    if output.get("is_error"):
        raise RuntimeError(f"Claude error: {output.get('result', 'unknown')[:500]}")

    global _resolved_model_ids
    model_usage = output.get("modelUsage", {})
    for resolved_id in model_usage:
        _resolved_model_ids[model] = resolved_id
        break

    cost = output.get("total_cost_usd", 0)
    if "structured_output" in output and output["structured_output"] is not None:
        return output["structured_output"], cost

    raw = output.get("result", "")
    try:
        return json.loads(raw), cost
    except (json.JSONDecodeError, TypeError):
        raise RuntimeError(
            f"Claude: structured_output missing and result not valid JSON.\n"
            f"Result: {str(raw)[:500]}"
        )


def _call_codex(system_prompt, user_prompt, schema, model, timeout):
    """Codex CLI (非対話モード) 経由の呼び出し。

    - --output-schema でスキーマ強制（claude CLIの --json-schema 相当）
    - システムプロンプトはCLIに専用フラグがないため、プロンプト先頭に結合する
    - プロンプトは argv 上限を避けるため stdin ('-') で渡す（stdinを開いたままにすると
      ハングするため、必ず input= で渡して閉じる）
    - OPENAI_API_KEY は環境から除去し、CLI のログイン認証で実行する
    """
    import tempfile

    codex_bin = shutil.which("codex") or os.path.expanduser(
        "~/.nvm/versions/node/v20.20.2/bin/codex")
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"

    with tempfile.TemporaryDirectory(prefix="codex_llm_") as tmpdir:
        schema_path = os.path.join(tmpdir, "schema.json")
        out_path = os.path.join(tmpdir, "last_message.txt")
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, ensure_ascii=False)

        result = subprocess.run(
            [
                codex_bin, "exec",
                "--skip-git-repo-check", "--ephemeral",
                "-s", "read-only",
                "-m", model,
                "--output-schema", schema_path,
                "-o", out_path,
                "--json",
                "-",
            ],
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=tmpdir,
        )
        if result.returncode != 0:
            detail = result.stderr[:500] or result.stdout[:500]
            raise RuntimeError(f"codex CLI error (exit {result.returncode}): {detail}")

        tokens = {}
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "turn.completed":
                tokens = event.get("usage", {})

        try:
            with open(out_path, encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            raw = ""

    parsed = _extract_json(raw)
    if parsed is None:
        raise RuntimeError(
            f"Codex: 出力のJSONパースに失敗しました (model={model}).\n"
            f"Result: {str(raw)[:500]}"
        )
    # CLI は呼び出しごとの費用を返さないため cost_usd は 0 とし、トークン数を集計用に記録する
    global _codex_token_totals
    _codex_token_totals["input"] += tokens.get("input_tokens", 0)
    _codex_token_totals["cached"] += tokens.get("cached_input_tokens", 0)
    _codex_token_totals["output"] += tokens.get("output_tokens", 0)
    _codex_token_totals["calls"] += 1
    return parsed, 0.0


def _call_agy(system_prompt, user_prompt, schema, model, timeout):
    """Antigravity CLI (agy) 経由の呼び出し。

    - スキーマ強制フラグがないため遅延制約（プロンプト指示＋JSON抽出）で実装
    - システムプロンプトはプロンプト先頭に結合（codexと同じ）
    - モデル名は `agy models` の表示名に完全一致で渡す（例: 'Gemini 3.1 Pro (High)'）
    """
    agy_bin = shutil.which("agy") or os.path.expanduser("~/.local/bin/agy")
    full_prompt = (f"{system_prompt}\n\n---\n\n{user_prompt}"
                   + _make_schema_instruction(schema))
    result = subprocess.run(
        [
            agy_bin,
            "-p", full_prompt,
            "--model", model,
            "--print-timeout", f"{max(60, min(timeout, 3600))}s",
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        detail = result.stderr[:500] or result.stdout[:500]
        raise RuntimeError(f"agy CLI error (exit {result.returncode}): {detail}")

    raw = result.stdout.strip()
    parsed = _extract_json(raw)
    if parsed is None:
        # 空応答・パース失敗は一時的なことが多い（レート制限等）。指数バックオフで再試行する
        import time
        for attempt in range(3):
            time.sleep(5 * (attempt + 1))
            retry = subprocess.run(
                [agy_bin, "-p", full_prompt, "--model", model,
                 "--print-timeout", f"{max(60, min(timeout, 3600))}s"],
                capture_output=True, text=True, timeout=timeout,
                stdin=subprocess.DEVNULL,
            )
            parsed = _extract_json(retry.stdout.strip())
            if parsed is not None:
                return parsed, 0.0
        raise RuntimeError(
            f"agy: 出力のJSONパースに失敗しました (model={model}、3回再試行後).\n"
            f"Result: {raw[:500]}"
        )
    return parsed, 0.0


_codex_token_totals = {"input": 0, "cached": 0, "output": 0, "calls": 0}


def get_codex_token_totals():
    """Codexバックエンドの累計トークン数。"""
    return dict(_codex_token_totals)


def _strip_think_tags(text):
    """Remove <think>...</think> blocks from model output."""
    if not text:
        return text
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL)


def _call_ollama(system_prompt, user_prompt, schema, model, host, timeout,
                  delayed_constraint=False, think=False):
    url = f"http://{host}/api/chat"

    # think:true の場合、format パラメータは使えない
    # (grammar-based constrained decoding が <think> トークンを抑制するため)
    use_prompt_json = delayed_constraint or think

    if use_prompt_json:
        sys_content = system_prompt + _make_schema_instruction(schema)
        fmt = None
    else:
        sys_content = system_prompt
        fmt = schema

    num_predict_initial = 16384 if think else -1

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "think": think,
        "options": {
            "temperature": 0.7,
            "num_predict": num_predict_initial,
            "num_ctx": 65536,
        },
    }
    if fmt is not None:
        payload["format"] = fmt

    max_retries = 3 if think else 1
    last_content = ""
    last_done_reason = ""
    for attempt in range(max_retries):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama connection error ({host}): {e}")
        except TimeoutError:
            raise RuntimeError(f"Ollama timeout ({host}, model={model})")

        last_done_reason = result.get("done_reason", "")
        content = result.get("message", {}).get("content", "")

        if think:
            content = _strip_think_tags(content)

        last_content = content

        if use_prompt_json:
            parsed = _extract_json(content)
            if parsed is not None:
                return parsed, 0.0
            if think and attempt < max_retries - 1:
                if last_done_reason == "length":
                    prev = payload["options"]["num_predict"]
                    payload["options"]["num_predict"] = prev * 2
                    print(
                        f"  [retry] truncated (done_reason=length) "
                        f"→ num_predict {prev} → {prev * 2} "
                        f"(attempt {attempt + 1}/{max_retries})",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"  [retry] JSON parse failed (done_reason={last_done_reason}, "
                        f"content={len(content)} chars) "
                        f"(attempt {attempt + 1}/{max_retries})",
                        file=sys.stderr,
                    )
                continue
            raise RuntimeError(
                f"Ollama ({'think' if think else 'delayed constraint'}): "
                f"JSONの抽出に失敗しました (done_reason={last_done_reason}, "
                f"attempts={attempt + 1}/{max_retries})。\n"
                f"Raw: {content[:500]}"
            )

        try:
            structured = json.loads(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Ollama JSON parse error (model={model}): {e}\n"
                f"Raw: {content[:500]}"
            )

        return structured, 0.0

    raise RuntimeError(
        f"Ollama (think:true): all {max_retries} retries exhausted. "
        f"done_reason={last_done_reason}\n"
        f"Raw: {last_content[:500]}"
    )


def _call_vllm(system_prompt, user_prompt, schema, model, host, timeout,
               delayed_constraint=False, max_retries=3):
    url = f"http://{host}/v1/chat/completions"

    if delayed_constraint:
        sys_content = system_prompt + _make_schema_instruction(schema)
    else:
        sys_content = system_prompt

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
    }

    payload["chat_template_kwargs"] = {"enable_thinking": False}
    if schema and not delayed_constraint:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "strict": True,
                "schema": schema,
            },
        }

    last_error = None
    for attempt in range(1, max_retries + 1):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"vLLM HTTP {e.code} ({host}): {body}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"vLLM connection error ({host}): {e}")
        except TimeoutError:
            raise RuntimeError(f"vLLM timeout ({host}, model={model})")

        try:
            content = result["choices"][0]["message"]["content"]
            finish_reason = result["choices"][0].get("finish_reason", "")
        except (KeyError, IndexError):
            raise RuntimeError(f"vLLM unexpected response: {json.dumps(result)[:500]}")

        if finish_reason == "length":
            last_error = (
                f"vLLM output truncated (finish_reason=length, model={model}). "
                f"Output too long for context window."
            )
            print(f"  WARNING: {last_error} (retry {attempt}/{max_retries})")
            continue

        if content.startswith("<think>"):
            content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL)

        if delayed_constraint:
            parsed = _extract_json(content)
            if parsed is not None:
                return parsed, 0.0
            last_error = f"vLLM (delayed constraint): JSONの抽出に失敗しました。"
            print(f"  WARNING: {last_error} (retry {attempt}/{max_retries})")
            continue

        try:
            structured = json.loads(content)
        except json.JSONDecodeError as e:
            last_error = f"vLLM JSON parse error (model={model}): {e}"
            print(f"  WARNING: {last_error} (retry {attempt}/{max_retries})")
            continue

        return structured, 0.0

    raise RuntimeError(f"{last_error} — all {max_retries} retries exhausted")


def call_llm(system_prompt, user_prompt, schema, model_spec="sonnet", timeout=3600,
             delayed_constraint=False, think=False):
    """Unified LLM call. Returns (structured_output, cost_usd).

    delayed_constraint: Trueの場合、constrained decodingを使わず、
        プロンプトでJSON形式を指示して自前パースする（遅延制約パターン）。
    think: Trueの場合、Ollama限定で思考モード（<think>タグ）を有効にする。
        format を使わずプロンプトでJSON指示、done_reason=length でリトライ。
        Ollama以外のバックエンドでは無視される。
    """
    backend, model, host = parse_model_spec(model_spec)

    if backend == "claude":
        if delayed_constraint:
            return _call_claude_delayed_constraint(
                system_prompt, user_prompt, schema, model, timeout
            )
        return _call_claude(system_prompt, user_prompt, schema, model, timeout)
    elif backend == "ollama":
        return _call_ollama(system_prompt, user_prompt, schema, model, host, timeout,
                            delayed_constraint=delayed_constraint, think=think)
    elif backend == "vllm":
        return _call_vllm(system_prompt, user_prompt, schema, model, host, timeout,
                          delayed_constraint=delayed_constraint)
    elif backend == "codex":
        return _call_codex(system_prompt, user_prompt, schema, model, timeout)
    elif backend == "agy":
        return _call_agy(system_prompt, user_prompt, schema, model, timeout)
    else:
        raise ValueError(f"Unknown backend: {backend}")


def get_resolved_model_id(model_spec):
    """Return the actual model ID resolved by the API (e.g. 'claude-sonnet-5').

    Available after at least one call_llm() with the same model_spec.
    Returns None for non-Claude backends or if no call has been made yet.
    """
    backend, model, _ = parse_model_spec(model_spec)
    if backend == "claude":
        return _resolved_model_ids.get(model)
    return model


def describe_model(model_spec):
    """Human-readable description of model spec."""
    backend, model, host = parse_model_spec(model_spec)
    if backend == "claude":
        return f"Claude ({model})"
    elif backend == "codex":
        return f"Codex ({model})"
    elif backend == "agy":
        return f"Antigravity ({model})"
    elif backend == "vllm":
        return f"vLLM {model} @ {host}"
    else:
        return f"Ollama {model} @ {host}"
