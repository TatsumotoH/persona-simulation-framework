# simulation/

## data/ — Honda case materials

Used by Study 2, the calibration loop (Stage 2), and the group simulation (Stage 3).

| File | Contents |
|---|---|
| `case_context.txt` | Short summary of the Honda Vietnam case (prepared from Amano & Shintaku 2010; see the top-level README) |
| `facts.json` | The 20 business facts given to personas |
| `personas.json` | The 30 personas in six role categories used in Study 2 and in the group simulation |
| `persona_screening_stimuli.json` | Preliminary version of the battery stimuli (8 personas); used for GPT-OSS 120B and by the calibration loop |

## persona_screening/ — Test 1 & 3 outputs

One folder per model and case: `sakura_<model>/` (Study 1), `honda_<model>/` (Study 2), and `gptoss120b/`, `swallow70b_full/` (preliminary versions of the battery; Table 1 rows marked †). GPT-OSS 120B used `data/persona_screening_stimuli.json`; Swallow-70B used an earlier version of the Honda stimuli that is not included. Each folder holds:

- `screening_summary.json` — the scores for Tests 1 and 3
- `screening_raw.json` — every model response, including the reasoning text

The fields of both files, with an example record, are explained in the glossary of `docs/BATTERY_MANUAL.md`.

Group simulation outputs (Stage 3) are not included in this repository; see the top-level README.
