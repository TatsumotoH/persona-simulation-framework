# Persona Simulation Framework

Research artifact for the proposal

> Tatsumoto, H. (2026). *Calibrate Before You Simulate: Detecting Silent Failure in AI Persona-Based Organizational Simulations.* Research proposal submitted to the *Organization Science* special issue "AI-Enabled Frontiers in Organizational Science."

The repository contains the scripts, stimuli, and model outputs behind the preliminary results reported in the proposal and its technical appendix.

## What the framework does

Researchers increasingly assign personas to AI models (large language models) to simulate organizational decision-making. A model can report its assigned traits perfectly ("How risk-averse are you?" → "Very") while those traits barely reach its actual judgments. The proposal calls this **silent failure**. The framework detects it with behavioral tests rather than self-report, in three stages:

| Stage | Purpose | Main code |
|---|---|---|
| 1. Diagnostic | Three behavioral tests decide whether a model can host personas | `persona_screening.py`, `run_law_generic.py` |
| 2. Calibration | Tune trait values to target levels, verified at the behavior level | `persona_calibration/` |
| 3. Simulation | Run multi-agent group decision-making with verified personas | `run_simulation.py`, `run_agents_*.py` |

The three diagnostic tests:

- **Test 1 — Persona Expression Test** (manipulation validity): do personas with different organizational roles classify the same ambiguous business facts differently, while agreeing on unambiguous ones? Does strategy ranking avoid simply reproducing the textbook order?
- **Test 2 — Persona Nomological Test** (nomological validity): when a trait is set high vs. low, does the difference reach behavior (strategy ranking, fact classification) in the theoretically predicted direction, and not only self-report scales?
- **Test 3 — Persona Belief-Update Test** (deliberation fitness): does the persona yield to strong evidence while resisting weak arguments and baseless majority pressure?

Scoring rules are in [docs/BATTERY_MANUAL.md](docs/BATTERY_MANUAL.md).

## Where each reported result comes from

| Result in the proposal | Files |
|---|---|
| Table 1, Figure 3, Appendix Figures A1–A2 (Study 1, Sakura Foods case, 9 models) | Tests 1 & 3: `simulation/persona_screening/sakura_<model>/` · Test 2: `persona_generic/results/law_sakura_<model>/` · Summary tables: `data/*.csv` |
| Table 1 rows marked † (GPT-OSS 120B, Swallow-70B; preliminary version of the battery) | `simulation/persona_screening/gptoss120b/`, `simulation/persona_screening/swallow70b_full/` |
| Table 2, Appendix §1C (calibration pipeline) | `persona_calibration/run_calibration_loop.py` → `persona_calibration/results/calib_loop_<model>/` |
| Appendix §2A (Study 2, Honda Vietnam case: diagnostic replication) | `simulation/persona_screening/honda_<model>/`, `persona_generic/results/law_honda_<model>/` |
| §3 and Appendix §2A (Study 2: 2,560-run group simulation) | `run_simulation.py` → `run_agents_multiround.py` / `run_agents_single_facilitator.py` (raw simulation outputs are not included; see below) |
| Figures 1 and 3 (diagrams) | `scripts/create_figure1_three_stage_framework.py`, `scripts/create_figure3_diagnostic_battery.py` |
| Figure 2, Tables 1–2, Appendix Figures A1–A2 | `scripts/gen_all_figures.Rmd` (reads `data/` and `persona_generic/results/`) |

A plain-language summary of these results is in [FINDINGS.md](FINDINGS.md).

## Repository layout

```
├── persona_screening.py          # Tests 1 & 3 (204 calls per model)
├── run_law_generic.py            # Test 2 (self-report vs. behavioral layers)
├── llm_backend.py                # Common interface to the model CLIs (see "Running")
├── config_manager.py             # Experiment configuration records
├── simulation_data.py            # Case materials and persona definitions (Study 2)
├── run_simulation.py             # Group simulation runner (Stage 3)
├── run_agents.py, run_agents_multiround.py, run_agents_single_facilitator.py
├── run_honda_case2.sh, run_honda_case2_family.sh   # Study 2 batch commands
├── persona_generic/
│   ├── data/                     # Stimuli: case packs, persona attributes, test items
│   ├── results/                  # Test 2 outputs (law_sakura_*, law_honda_*)
│   └── run_battery_sakura.sh     # Study 1 batch command (Tests 1–3 for one model)
├── simulation/
│   ├── data/                     # Study 2 case summary, 20 facts, 30 personas
│   └── persona_screening/        # Tests 1 & 3 outputs (sakura_*, honda_*)
├── persona_calibration/          # Stage 2: calibration loop and pathway tests; calibration results
├── data/                         # Summary CSVs used for Table 1 and appendix figures
├── scripts/                      # Figure and table generation
└── docs/BATTERY_MANUAL.md        # How to run and score the diagnostic battery
```

## Models

Model specifications as recorded in the output files (`_meta.model` in each `screening_summary.json`):

| Model | Provider | Specification used | Study 1 result |
|---|---|---|---|
| Claude Sonnet | Anthropic | `sonnet` | Pass |
| Claude Opus | Anthropic | `opus` | Pass |
| Claude Haiku | Anthropic | `haiku` | Fail (acquiescent) |
| GPT-5.6 terra | OpenAI | `codex:gpt-5.6-terra` | Pass |
| GPT-5.6 sol | OpenAI | `codex:gpt-5.6-sol` | Pass |
| GPT-5.6 luna | OpenAI | `codex:gpt-5.6-luna` | Fail (forbidden violation) |
| Gemini 3.1 Pro | Google | `agy:Gemini 3.1 Pro (High)` | Pass |
| Gemini 3.5 Flash | Google | `agy:Gemini 3.5 Flash (Medium)` | Pass |
| Qwen3-32B | Alibaba (open-weight) | `ollama:qwen3:32b` | Fail (rote response + rigidity) |

GPT-OSS 120B and Swallow-70B (open-weight) were run on AIST's ABCI supercomputer with a preliminary version of the battery.

## Running

**Language.** All stimuli, personas, and prompts are in Japanese, and the experiments were run in Japanese. Code comments are also in Japanese; function and variable names are in English. This README, FINDINGS.md, and docs/BATTERY_MANUAL.md are the English entry points.

**Model access.** `llm_backend.py` calls models through command-line tools rather than vendor SDKs:

| Specification | Tool |
|---|---|
| `sonnet`, `opus`, `haiku` | Claude Code CLI (`claude`) |
| `codex:<model>` | OpenAI Codex CLI |
| `agy:<model display name>` | Google Antigravity CLI |
| `ollama:<model>[@host:port]` | Ollama HTTP API |
| `vllm:<model>[@host:port]` | vLLM (OpenAI-compatible API) |

**Python.** Python 3.10+; `pip install -r requirements.txt`. `scripts/gen_all_figures.Rmd` needs R 4.x with tidyverse, gt, webshot2, scales, and jsonlite.

**Examples.**

```bash
# Study 1: Tests 1–3 for one model (Sakura Foods case)
bash persona_generic/run_battery_sakura.sh "sonnet" sakura_sonnet 3

# Study 2: Tests 1–3 for one model (Honda Vietnam case)
bash run_honda_case2.sh sonnet honda_sonnet

# Check the design without calling any model
python3 persona_screening.py --stimuli persona_generic/data/persona_check_sakura_v1.json --no-internal-tag --dry-run

# Regenerate the figures and tables (written to output/)
python3 scripts/create_figure1_three_stage_framework.py
python3 scripts/create_figure3_diagnostic_battery.py
cd scripts && Rscript -e 'rmarkdown::render("gen_all_figures.Rmd")'
```

## Case materials

**Study 1: Sakura Foods** is a fictional case written for this study, included in full in `persona_generic/data/case_pack_v1.json`.

**Study 2: Honda Vietnam** is based on a published, open-access article:

> Amano, T., & Shintaku, J. (2010). Honda's two-wheeled vehicle business strategy in ASEAN: Strategy innovation and the introduction of low-cost models and product. *Akamon Management Review*, 9(11), 783–806. https://doi.org/10.14955/amr.091101 (in Japanese: 天野倫文・新宅純二郎「ホンダ二輪事業のASEAN戦略：低価格モデルの投入と製品戦略の革新」『赤門マネジメント・レビュー』)

The case summary (`simulation/data/case_context.txt`, `persona_generic/data/case_pack_honda_v1.json`) and the 20 facts (`simulation/data/facts.json`) were prepared by the author from this article. The article itself is © 2010 Global Business Research Center and is not redistributed here.

## What is not included

- **Group simulation raw outputs and detailed analysis notebooks** (Study 2; several GB). They will be released with the full paper; the raw outputs can be shared on request.
- **Full text of the Honda Vietnam case article.** It is freely available from J-STAGE (see "Case materials" above). This repository contains only the short case summary and 20 facts used as stimuli.
- **Human benchmark data** (pilot data from 33 working professionals), to protect participants' privacy.
- **TIPI-J items** (Oshio, Abe & Cutrone 2012) used by `persona_calibration/run_dissociation.py`. Prepare `persona_calibration/tipi_j_items.json` from the original publication; the expected format is described at the top of the script.

## License

MIT License. See [LICENSE](LICENSE).

## Funding

JSPS KAKENHI Grant Number 26K00362.

## Author

Hirofumi Tatsumoto, University of Tsukuba
