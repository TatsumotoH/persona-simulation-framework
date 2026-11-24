# persona_calibration/

Stage 2: calibration of persona trait values, verified at the behavior level. All scripts here use the Honda Vietnam case materials in `simulation/data/`.

| File | Purpose |
|---|---|
| `run_calibration_loop.py` | The calibration pipeline (technical appendix §1C, Table 2). Sets risk aversion to a target (high = 6.0, low = 2.0 on a 7-point scale), measures, adjusts, and re-measures until convergence, then checks the effect on judgment tasks |
| `run_dissociation.py` | Pathway test: does personality shaping that moves self-report scores also move fact classification? Needs `tipi_j_items.json` (not distributed; see the top-level README) |
| `run_dissociation_pref.py` | Pathway test: the same question for a preference (risk aversion) |
| `results/calib_loop_<model>/summary.json` | Calibration results: `trajectories` toward the targets, `final_positions`, `validation_tests` (e.g., `WT_rank` with `high_mean`, `low_mean`, `p`), and `validation_raw` (the 12 responses per level behind each test) |

Usage: `python3 persona_calibration/run_calibration_loop.py --model sonnet --tag sonnet`
