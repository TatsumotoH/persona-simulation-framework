# Persona Simulation Framework

Research artifact for the proposal

> Tatsumoto, H. (2026). *Calibrate Before You Simulate: Detecting Silent Failure in AI Persona-Based Organizational Simulations.* Research proposal submitted to the *Organization Science* special issue "AI-Enabled Frontiers in Organizational Science."

The repository contains the scripts, stimuli, and model outputs behind the preliminary results reported in the proposal and its technical appendix.

## What the framework does

Researchers increasingly assign personas to AI models (large language models) to simulate organizational decision-making. A model can report its assigned traits perfectly ("How risk-averse are you?" → "Very") while those traits barely reach its actual judgments. The proposal calls this **silent failure**. The framework detects it with behavioral tests rather than self-report, in three stages: **Diagnostic → Calibration → Simulation**.

The three diagnostic tests (Stage 1):

- **Test 1 — Persona Expression Test** (manipulation validity): do personas with different organizational roles classify the same ambiguous business facts differently, while agreeing on unambiguous ones? Does strategy ranking avoid simply reproducing the textbook order?
- **Test 2 — Persona Nomological Test** (nomological validity): when a trait is set high vs. low, does the difference reach behavior (strategy ranking, fact classification) in the theoretically predicted direction, and not only self-report scales?
- **Test 3 — Persona Belief-Update Test** (deliberation fitness): does the persona yield to strong evidence while resisting weak arguments and baseless majority pressure?

The tasks are built on SWOT analysis: personas classify business facts as Strengths, Weaknesses, Opportunities, or Threats, and rank four strategies (SO, ST, WO, WT; e.g., WT = a defensive strategy that minimizes weaknesses and avoids threats).

The two studies use two cases: **Study 1** a fictional company (Sakura Foods; file prefix `sakura_`) and **Study 2** a real case (Honda Vietnam; file prefix `honda_`).

## Start here

| Step | Code | Stimuli | Results | Reported in |
|---|---|---|---|---|
| **Test 1** Expression | `persona_screening.py` | `persona_generic/data/persona_check_sakura_v1.json` (Study 1), `persona_check_honda_v1.json` (Study 2) | `simulation/persona_screening/sakura_<model>/`, `honda_<model>/` | Table 1, Figure 3, Appendix A1–A2, §2A |
| **Test 2** Nomological | `run_law_generic.py` | `persona_generic/data/attributes_v1.json` with `case_pack_v1.json` (Study 1) or `case_pack_honda_v1.json` (Study 2) | `persona_generic/results/law_sakura_<model>/`, `law_honda_<model>/` | Table 1, Appendix A1–A2, §2A |
| **Test 3** Belief-Update | `persona_screening.py` (same run as Test 1) | same as Test 1 | same as Test 1 | Table 1, Figure 3, Appendix A1–A2, §2A |
| Preliminary battery (GPT-OSS 120B, Swallow-70B) | `persona_screening.py` | `simulation/data/persona_screening_stimuli.json` (GPT-OSS); an earlier Honda version, not included (Swallow) | `simulation/persona_screening/gptoss120b/`, `swallow70b_full/` | Table 1, rows marked † |
| **Stage 2** Calibration | `persona_calibration/run_calibration_loop.py` | Honda case materials in `simulation/data/` | `persona_calibration/results/calib_loop_<model>/` | Table 2, Appendix §1C |
| **Stage 3** Simulation | `run_simulation.py` → `run_agents_multiround.py` or `run_agents_single_facilitator.py` | Honda case materials in `simulation/data/` | not included (see below) | §3, Appendix §2A |
| Figures and tables | `scripts/` | `data/*.csv`, `persona_generic/results/law_sakura_*` | written to `output/` | Figures 1–3, Tables 1–2, Appendix A1–A2 |

Calibration was run with the Honda Vietnam case materials; the technical appendix presents it in §1C alongside Study 1.

**Where to read next**

- [FINDINGS.md](FINDINGS.md): the reported results, and a table showing where to check each number in Table 1 and Table 2.
- [docs/BATTERY_MANUAL.md](docs/BATTERY_MANUAL.md): how to run and score the tests, and a glossary of the field names in the result files.
- Each folder has a short README describing its files.

**Names to know.** File and folder names date from the research process and are kept so that they match the file list in the technical appendix (Section G). The main ones: `law` = Test 2; inside the stimulus and result files, `check1a` and `check1b` = Test 1 and `check2` = Test 3. The full list is in the glossary.

## Repository layout

```
├── persona_screening.py          # Stage 1: Tests 1 & 3 (204 calls per model)
├── run_law_generic.py            # Stage 1: Test 2 (324 calls per model)
├── run_simulation.py             # Stage 3: runner; calls one of the two scripts below
├── run_agents_multiround.py      # Stage 3: multi-round group deliberation
├── run_agents_single_facilitator.py  # Stage 3: single-facilitator deliberation
├── run_agents.py                 # Stage 3: initial single-file version (superseded by the two above)
├── simulation_data.py            # Honda case summary and persona definitions
├── llm_backend.py                # Common interface to the model CLIs (see "Running")
├── config_manager.py             # Records the configuration of each simulation run
├── run_honda_case2.sh            # Study 2: Tests 1–3 for one model
├── run_honda_case2_family.sh     # Study 2: Tests 1–3 for a provider family
├── persona_generic/              # Standardized battery used in Studies 1 and 2
│   ├── data/                     #   stimuli: case packs, persona attributes, test items
│   ├── results/                  #   Test 2 outputs (law_sakura_*, law_honda_*)
│   └── run_battery_sakura.sh     #   Study 1: Tests 1–3 for one model
├── simulation/
│   ├── data/                     # Honda case materials: summary, 20 facts, 30 personas
│   └── persona_screening/        # Test 1 & 3 outputs (sakura_*, honda_*)
├── persona_calibration/          # Stage 2: calibration loop, pathway tests, results
├── data/                         # Summary CSVs behind Table 1 and the appendix figures
├── scripts/                      # Figure and table generation
├── docs/BATTERY_MANUAL.md        # How to run and score the tests; glossary
└── FINDINGS.md                   # Reported results and where to check them
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

**Language.** All stimuli, personas, and prompts are in Japanese, and the experiments were run in Japanese. Code comments and the models' reasoning texts are also in Japanese; function, variable, and field names are in English. The READMEs, FINDINGS.md, and docs/BATTERY_MANUAL.md are the English entry points.

**Model access.** `llm_backend.py` calls models through command-line tools rather than vendor SDKs:

| Specification | Tool |
|---|---|
| `sonnet`, `opus`, `haiku` | Claude Code CLI (`claude`) |
| `codex:<model>` | OpenAI Codex CLI |
| `agy:<model display name>` | Google Antigravity CLI |
| `ollama:<model>[@host:port]` | Ollama HTTP API |
| `vllm:<model>[@host:port]` | vLLM (OpenAI-compatible API) |

**Requirements.** Python 3.10+ (`pip install -r requirements.txt`). `scripts/gen_all_figures.Rmd` needs R 4.x with tidyverse, gt, webshot2, scales, and jsonlite.

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

- **Group simulation raw outputs and detailed analysis notebooks** (Study 2). They will be released with the full paper; the raw outputs can be shared on request.
- **Full text of the Honda Vietnam case article.** It is freely available from J-STAGE (see "Case materials" above). This repository contains only the short case summary and 20 facts used as stimuli.
- **Human benchmark data** (pilot data from 33 working professionals), to protect participants' privacy.
- **TIPI-J items** (Oshio, Abe & Cutrone 2012) used by `persona_calibration/run_dissociation.py`. Prepare `persona_calibration/tipi_j_items.json` from the original publication; the expected format is described at the top of the script.
- **The earlier Honda stimulus file** used for the preliminary Swallow-70B run.

## Correspondence with the technical appendix (Section G)

Section G of the technical appendix lists the repository contents. Each item and where it stands in this public version:

| Section G item | In this repository |
|---|---|
| `persona_screening.py`, `llm_backend.py`, `config_manager.py`, `simulation_data.py`, `run_simulation.py`, `run_agents*.py` | Included, as listed |
| `persona_calibration/` (`run_calibration_loop.py`, `run_dissociation.py`, `run_dissociation_pref.py`) | Included, with the calibration results |
| `requirements.txt`, `README.md` | Included |
| `FINDINGS.md` | Included; summarizes the results reported in the proposal |
| `persona_simulation/`, `analysis/` (analysis notebooks) | To be released with the full paper, together with the raw simulation outputs |
| `bias_tasks_v1.json`, `run_behavioral_tasks.py` | Not included; these belong to additional tests that are not part of the results reported in the proposal |

Added since the appendix was written: `run_law_generic.py` (Test 2), the batch scripts, the stimuli in `persona_generic/`, the model outputs, `data/`, `scripts/`, and `docs/`.

## License

MIT License. See [LICENSE](LICENSE).

## Funding

JSPS KAKENHI Grant Number 26K00362.

## Author

Hirofumi Tatsumoto, University of Tsukuba
