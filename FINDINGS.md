# Findings

This file summarizes the preliminary results reported in the submitted proposal and technical appendix, and points to the files that support each one. It contains no results beyond those in the submitted documents.

## 1. Silent failure is common, and self-report cannot detect it

All nine models in Study 1 passed self-report validation: asked to describe their assigned traits, each answered exactly as specified. The behavioral tests nonetheless disqualified three of them. In Test 2, self-report effects were large in every model, while effects on actual strategy ranking were significant but far smaller.

- Files: `persona_generic/results/law_sakura_<model>/summary.json`

## 2. The battery separates models (Study 1, Sakura Foods case)

Six of nine models passed all three tests, covering all three commercial provider families. The three failures each showed a different pathology:

| Model | Failure |
|---|---|
| Claude Haiku | Acquiescent: changed its classification under baseless majority pressure 61% of the time |
| GPT-5.6 luna | Forbidden violation: changed position (3%) even on arguments with no evidence |
| Qwen3-32B | Rote response (17% textbook-order rate) and rigidity (6% change even on strong evidence) |

Models that passed one test could fail another, so the three tests measure separate capabilities.

- Files: `simulation/persona_screening/sakura_<model>/`, `data/battery_summary.csv`, `data/belief_update.csv`, `data/fact_splitting.csv`

## 3. Traits reach some judgments and not others

Whether a trait reached behavior depended on the kind of judgment. Factual judgment (classifying business facts) was influenced only by organizational role. Value judgment (ranking strategies) was influenced by both role and individual traits. This mirrors Simon's (1947) distinction between factual and value premises.

- Files: `persona_generic/results/law_sakura_<model>/summary.json`

## 4. Calibration transfers across vendors (Stage 2)

The calibration pipeline sets a trait to a target (for example, risk aversion 2.0 vs. 6.0 on a seven-point scale), overshoots and steps back, and checks convergence on behavior rather than on the scale. It typically converged in two iterations. After calibration, the behavioral effects were nearly identical across vendors:

| Model | WT strategy rank, high vs. low risk aversion | p |
|---|---|---|
| Claude Sonnet | 1.08 vs. 3.25 | 0.0001 |
| GPT-5.6 terra | 1.08 vs. 3.08 | 0.0001 |
| Claude Opus | — | < 0.001 |

- Files: `persona_calibration/results/calib_loop_<model>/summary.json`

## 5. The diagnosis carries over to a real case (Study 2, Honda Vietnam)

The battery was rerun on Honda's motorcycle strategy in Vietnam (528 calls per model, 9 models). The two-layer structure of Test 2 held for all 9 models × 7 attributes, with no forbidden-pathway violations, and the failure typology replicated (Claude Haiku remained acquiescent). Test 1 turned out to depend on the case: expression testing needs case materials with deliberately built-in ambiguity.

- Files: `simulation/persona_screening/honda_<model>/`, `persona_generic/results/law_honda_<model>/`

## 6. Group composition changes conclusions (Study 2, Stage 3)

Calibrated personas were placed in five-member teams, crossing group composition (headquarters-dominant, local-dominant, balanced, random) with deliberation format (four conditions), 20 replications per model: 2,560 simulations in total. Teams with different compositions reached systematically different strategic conclusions in all 8 commercial models (Kruskal-Wallis p < 0.05 for every strategy quadrant).

- Files: `run_simulation.py`, `run_agents_multiround.py`, `run_agents_single_facilitator.py` (raw outputs and analysis notebooks will be released with the full paper)

## Limitations stated in the proposal

- Sample sizes are preliminary (30 personas per model for Tests 1–2, 12 for Test 3). The full paper will increase them.
- The results are a 2026 snapshot of rapidly changing models. The standardized battery is meant to let new models be checked the same way.
