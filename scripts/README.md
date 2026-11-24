# scripts/

Regenerate the figures and tables of the submitted proposal and technical appendix. Output goes to `output/` at the repository root.

| Script | Produces |
|---|---|
| `create_figure1_three_stage_framework.py` | Figure 1 (three-stage framework) |
| `create_figure3_diagnostic_battery.py` | Figure 3 (diagnostic test battery) |
| `gen_all_figures.Rmd` | Figure 2 (test system), Table 1, Table 2, Appendix Figure A1 (Study 1 descriptives), Appendix Figure A2 (diagnostic scorecard) |

```bash
python3 scripts/create_figure1_three_stage_framework.py
python3 scripts/create_figure3_diagnostic_battery.py
cd scripts && Rscript -e 'rmarkdown::render("gen_all_figures.Rmd")'
```

`gen_all_figures.Rmd` reads `data/*.csv` and `persona_generic/results/law_sakura_*/summary.json`. It needs R 4.x with tidyverse, gt, webshot2, scales, and jsonlite.
