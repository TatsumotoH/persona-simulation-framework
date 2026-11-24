# persona_generic/

The standardized diagnostic battery (Stage 1), used in both Study 1 (Sakura Foods) and Study 2 (Honda Vietnam).

## data/ — stimuli

| File | Contents | Used by |
|---|---|---|
| `case_pack_v1.json` | Study 1 case (fictional Sakura Foods): case text, 12 facts, 4 strategic options, 30 personas (6 role categories × 5) | `run_law_generic.py` |
| `case_pack_honda_v1.json` | Study 2 case (Honda Vietnam): case summary and 20 facts; source citation in `_meta.source`. Personas are in `simulation/data/personas.json` | `run_law_generic.py` |
| `persona_check_sakura_v1.json` | Tests 1 & 3 stimuli for Study 1: fact assignments, the four strategies, counterarguments | `persona_screening.py`, `run_law_generic.py` |
| `persona_check_honda_v1.json` | Tests 1 & 3 stimuli for Study 2: fact assignments, the four strategies, counterarguments | `persona_screening.py`, `run_law_generic.py` |
| `attributes_v1.json` | Test 2: the seven persona attributes, their high/low wording, and self-report items | `run_law_generic.py` |

In the stimulus files, `check1a` and `check1b` are Test 1 (fact classification and strategy ranking) and `check2` is Test 3. Fields named `note`, `rationale`, `anchor`, or `_meta` are documentation and are never sent to the models.

## results/ — Test 2 outputs

`law_sakura_<model>/` (Study 1) and `law_honda_<model>/` (Study 2), each with `summary.json` (high-vs-low effects per attribute and measure) and `raw.json` (every call).

## run_battery_sakura.sh

Runs Tests 1–3 for one model on the Study 1 case: `bash persona_generic/run_battery_sakura.sh "<model-spec>" sakura_<tag> [max_workers]`.
