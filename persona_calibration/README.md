# persona_calibration/

Stage 2: calibration of persona trait values, verified at the behavior level.

| File | Purpose |
|---|---|
| `run_calibration_loop.py` | The calibration pipeline (technical appendix §1C, Table 2). Sets risk aversion to a target (high = 6.0, low = 2.0 on a 7-point scale), measures, adjusts, and re-measures until convergence, then checks the effect on judgment tasks |
| `run_dissociation.py` | Pathway test: does personality shaping that moves self-report scores also move fact classification? Needs `tipi_j_items.json` (not distributed; see the top-level README) |
| `run_dissociation_pref.py` | Pathway test: the same question for a preference (risk aversion) |
| `results/calib_loop_<model>/summary.json` | Calibration results: trajectories toward the targets, final positions, and validation tests |

Usage: `python3 persona_calibration/run_calibration_loop.py --model sonnet --tag sonnet`
