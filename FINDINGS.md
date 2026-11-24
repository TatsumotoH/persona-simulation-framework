# Findings

This file summarizes the preliminary results reported in the submitted proposal and technical appendix, and shows where each one can be checked in the repository. It contains no results beyond those in the submitted documents. Field names used below are defined in the glossary of [docs/BATTERY_MANUAL.md](docs/BATTERY_MANUAL.md).

## 1. Silent failure is common, and self-report cannot detect it

All nine models in Study 1 passed self-report validation: asked to describe their assigned traits, each answered exactly as specified. The behavioral tests nonetheless disqualified three of them. In Test 2, self-report effects were large in every model, while effects on actual strategy ranking were significant but far smaller.

- Files: `persona_generic/results/law_sakura_<model>/summary.json` (self-report = `scale`; strategy ranking = `rank_*`)

## 2. The battery separates models (Study 1, Sakura Foods case)

Six of nine models passed all three tests, covering all three commercial provider families. The three failures each showed a different pathology:

| Model | Failure |
|---|---|
| Claude Haiku | Acquiescent: changed its classification under baseless majority pressure 61% of the time |
| GPT-5.6 luna | Forbidden violation: changed position (3%) even on arguments with no evidence |
| Qwen3-32B | Rote response (17% textbook-order rate) and rigidity (6% change even on strong evidence) |

Models that passed one test could fail another, so the three tests measure separate capabilities.

## 3. Traits reach value judgments, not unambiguous facts

When a trait was set high vs. low (Test 2), it shifted the models' strategy rankings (value judgments) but never shifted their classification of unambiguous facts — in all 9 models and 7 attributes, in both cases (no forbidden-pathway violations). Some traits did shift the classification of ambiguous facts, which the norm in Test 2 permits (see "Test 2" in the manual). The proposal relates this pattern to Simon's (1947) distinction between factual and value premises.

- Files: `persona_generic/results/law_<case>_<model>/summary.json` (unambiguous facts = `def_det`; ambiguous facts = `def_amb`; strategy ranking = `rank_*`)

## 4. Calibration transfers across vendors (Stage 2)

The calibration pipeline sets a trait to a target (risk aversion 2.0 vs. 6.0 on a seven-point scale), overshoots and steps back, and checks convergence on behavior rather than on the scale. It typically converged in two iterations. After calibration, the behavioral effects were nearly identical across vendors (WT strategy rank, where 1 = top priority):

| Model | High vs. low risk aversion | p |
|---|---|---|
| Claude Sonnet | 1.08 vs. 3.25 | < 0.001 |
| GPT-5.6 terra | 1.08 vs. 3.08 | < 0.001 |
| Claude Opus | 1.33 vs. 3.92 | < 0.001 |

The calibration runs used the Honda Vietnam case materials.

## 5. The diagnosis carries over to a real case (Study 2, Honda Vietnam)

The battery was rerun on Honda's motorcycle strategy in Vietnam (528 calls per model, 9 models). The two-layer structure of Test 2 held for all 9 models × 7 attributes, with no forbidden-pathway violations, and the failure typology replicated (Claude Haiku remained acquiescent). Test 1 turned out to depend on the case: expression testing needs case materials with deliberately built-in ambiguity.

- Files: `simulation/persona_screening/honda_<model>/`, `persona_generic/results/law_honda_<model>/`

## 6. Group composition changes conclusions (Study 2, Stage 3)

Calibrated personas were placed in five-member teams, crossing group composition (headquarters-dominant, local-dominant, balanced, random) with deliberation format (four conditions), 20 replications per model: 2,560 simulations in total. Teams with different compositions reached systematically different strategic conclusions in all 8 commercial models (Kruskal-Wallis p < 0.05 for every strategy quadrant).

- Code: `run_simulation.py`, `run_agents_multiround.py`, `run_agents_single_facilitator.py`. Raw outputs and analysis notebooks will be released with the full paper.

## Checking the numbers yourself

Each number in the proposal's Table 1 and Table 2 can be traced to a field in the repository. Summary values are in `data/battery_summary.csv` (one row per model); the per-call records behind them are in `screening_raw.json`.

| Number in the proposal | Summary value | Underlying records |
|---|---|---|
| Haiku changed under majority pressure 61% (Test 3) | `data/battery_summary.csv`, row Claude Haiku, `majority` = 0.611 | `simulation/persona_screening/sakura_haiku/screening_raw.json` → `check2_probes` with `probe_type` = `majority`: 22 of 36 have `changed` = true |
| Haiku changed on weak arguments 22% (Table 1) | same row, `weak` = 0.222 | same file, `probe_type` = `weak`: 8 of 36 changed |
| luna changed on weak arguments 3% (Test 3) | row GPT-5.6 luna, `weak` = 0.028 | `sakura_gpt56luna/screening_raw.json`, `probe_type` = `weak`: 1 of 36 changed |
| Qwen3 textbook-order rate 17% (Test 1) | row Qwen3-32B, `textbook_rate` = 0.167 | `sakura_qwen32b/screening_summary.json` → `check1b.patterns`: 5 of 30 personas gave `SO-ST-WO-WT` |
| Qwen3 changed on strong evidence 6% (Test 3) | row Qwen3-32B, `strong` = 0.056 | `sakura_qwen32b/screening_raw.json`, `probe_type` = `strong`: 2 of 36 changed |
| Discriminating facts that split, e.g. 7/7 (Test 1) | `split_disc` column | `data/fact_splitting.csv` (one row per model × fact) |
| Calibration, Sonnet WT rank 1.08 vs. 3.25 (Table 2) | `persona_calibration/results/calib_loop_sonnet/summary.json` → `validation_tests.WT_rank`: `high_mean` 1.08, `low_mean` 3.25, `p` 5e-05 | same file → `validation_raw` (12 responses per level) |

Haiku also fails the weak-argument criterion (22% > 0%); the proposal reports its failure as acquiescence.

## Limitations stated in the proposal

- Sample sizes are preliminary (30 personas per model for Tests 1–2, 12 for Test 3). The full paper will increase them.
- The results are a 2026 snapshot of rapidly changing models. The standardized battery is meant to let new models be checked the same way.
