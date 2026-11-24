# data/

Summary tables for Study 1 (Sakura Foods case, 9 models), derived from the Test 1–3 outputs in `simulation/persona_screening/sakura_<model>/`. They feed Table 1 and the appendix figures via `scripts/gen_all_figures.Rmd`.

| File | One row per | Columns |
|---|---|---|
| `battery_summary.csv` | model | `split_disc` discriminating facts that split (Test 1), `textbook_rate` share of textbook-order rankings (Test 1), `n_patterns` distinct rankings, `strong` / `medium` / `weak` / `majority` change rates by probe (Test 3), `dose_ok`, `rigid`, `syco` (acquiescent) flags |
| `fact_splitting.csv` | model × fact | `fact_set` (判別 = discriminating, 統制 = control), `n_categories`, `minority_pct`, `majority_cat` |
| `belief_update.csv` | model × probe | `probe_type`, `change_rate`, `n` (Test 3) |
| `priority_patterns.csv` | model × ranking pattern | `pattern` (e.g., `WT-ST-WO-SO`, highest priority first), `count`, `n_personas` (Test 1, strategy ranking) |
