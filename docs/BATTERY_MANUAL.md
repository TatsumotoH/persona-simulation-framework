# Diagnostic Battery Manual

How to run and score the three diagnostic tests (Stage 1). The criteria below are those stated in Section 1A of the technical appendix.

## Overview

| Test | Question | Script | Calls per model |
|---|---|---|---|
| 1. Persona Expression | Does the persona shape judgment itself? | `persona_screening.py` | 60 (30 + 30) |
| 3. Persona Belief-Update | Does the persona revise its view in proportion to argument quality? | `persona_screening.py` (same run) | 144 |
| 2. Persona Nomological | Do trait differences reach behavior in the predicted direction? | `run_law_generic.py` | 324 |

Tests 1 and 3 run in a single `persona_screening.py` call (204 calls) for implementation convenience; they are separate tests. A model must pass all three to be used in group simulation. Failing Test 3 alone rules out experiments that involve deliberation.

The script replaces real discussion partners with scripted stimuli, so every model and persona receives identical input and models can be compared directly.

## Stimuli

| Case | File | Notes |
|---|---|---|
| Study 1: Sakura Foods (fictional) | `persona_generic/data/persona_check_sakura_v1.json`, `case_pack_v1.json` | A fictional case avoids training-data contamination |
| Study 2: Honda Vietnam (real) | `persona_generic/data/persona_check_honda_v1.json`, `case_pack_honda_v1.json` | Cross-case replication. Based on Amano & Shintaku (2010), *Akamon Management Review* 9(11), https://doi.org/10.14955/amr.091101 |
| Trait definitions (Test 2) | `persona_generic/data/attributes_v1.json` | Seven attributes, each set high and low |

Facts come in two kinds: **discriminating** facts (ambiguous, designed so that different occupational roles should classify them differently) and **control** facts (unambiguous, expected to show consensus). The Sakura Foods case has 12 facts (7 discriminating, 5 control); the Honda case has 20 facts (7 discriminating, 7 control, 6 other). The assignment of each fact is in the `check1a` section of each stimulus file. Personas come from six occupational role categories, 5 per category (30 in total).

Always pass `--no-internal-tag`. It removes the internal/external hints from the facts; without it, the hints halve the answer options and the results are not comparable.

## Running

```bash
# Study 1, one model: Tests 1 & 3, then Test 2 (stops if Tests 1 & 3 produce no output)
bash persona_generic/run_battery_sakura.sh "<model-spec>" sakura_<tag> [max_workers]

# Study 2, one model
bash run_honda_case2.sh "<model-spec>" honda_<tag>

# Study 2, a whole provider family in sequence
bash run_honda_case2_family.sh claude|gpt|gemini|qwen

# Individual steps
python3 persona_screening.py --model "<model-spec>" --tag <tag> \
    --stimuli persona_generic/data/persona_check_sakura_v1.json --no-internal-tag
python3 run_law_generic.py --model "<model-spec>" --tag <tag> --case sakura --reps 12

# Inspect the design without calling a model
python3 persona_screening.py --stimuli persona_generic/data/persona_check_sakura_v1.json --no-internal-tag --dry-run
```

Model specifications (`sonnet`, `codex:gpt-5.6-terra`, `agy:Gemini 3.1 Pro (High)`, `ollama:qwen3:32b`, …) are explained in the README.

## Outputs

| Test | Output |
|---|---|
| 1 & 3 | `simulation/persona_screening/<tag>/screening_raw.json` (every call) and `screening_summary.json` (scores) |
| 2 | `persona_generic/results/law_<tag>/raw.json` and `summary.json` |

## Scoring

### Test 1: Persona Expression

- **1a. Factual judgment (30 calls).** Each persona classifies the 20 facts into S/W/O/T.
- **1b. Value judgment (30 calls).** Each persona ranks four strategies (SO, ST, WO, WT). The *textbook-order rate* is the share of personas returning the presentation order SO > ST > WO > WT.

Pass requires all three:

1. At least 70% of discriminating facts split, with the minority answer at 10% or more.
2. Every control fact reaches a majority of 90% or more.
3. Textbook-order rate is 10% or less.

1a provides the positive evidence that the persona is expressed. 1b is an exclusion condition: passing it does not show that the persona works, but failing it (reproducing the order in which options were presented) shows that it cannot.

### Test 2: Persona Nomological

Seven attributes (for example, risk aversion and openness to change) are each set high and low. The test checks two layers:

- **Self-report:** questionnaire items asking the persona to rate its own traits
- **Behavior:** strategy ranking and fact classification

Pass: for every attribute, the high–low difference on the behavioral measures is significant (p < .05) and in the direction predicted by theory. All models passed. The diagnostic value lies in the gap between self-report and behavioral effect sizes, which is what reveals silent failure.

### Test 3: Persona Belief-Update

Twelve personas receive counterarguments against their own classifications of 3 facts, at four quality levels (12 × 3 × 4 = 144 calls):

| Probe | Content | Should the persona change? |
|---|---|---|
| Strong | Case-specific evidence | Yes |
| Medium | General reasoning | — |
| Weak | No evidence | No |
| Majority | "All other members classified it differently" | No |

Pass requires all three:

1. Change rate under strong rebuttal is above 15% (otherwise **rigid**).
2. Change rate under weak rebuttal is 0% (the persona discriminates argument quality).
3. Change rate under majority pressure is below 50% (otherwise **acquiescent**).

## Note on the summary fields

`screening_summary.json` reports Test 1a under `check1a`, Test 1b under `check1b`, and Test 3 under `check2` (internal names from an earlier version of the battery). Field labels such as `判別` (discriminating), `統制` (control), and `その他` (neutral) are in Japanese.
