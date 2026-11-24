# simulation/

## data/ — Study 2 case materials

| File | Contents |
|---|---|
| `case_context.txt` | Short summary of the Honda Vietnam case (prepared from Amano & Shintaku 2010; see the top-level README) |
| `facts.json` | The 20 business facts given to personas |
| `personas.json` | The 30 personas in six role categories used in Study 2 and in the group simulation |
| `persona_screening_stimuli.json` | Preliminary version of the battery stimuli (8 personas); used for GPT-OSS 120B and by the calibration loop |

## persona_screening/ — Test 1 & 3 outputs

One folder per model and case: `sakura_<model>/` (Study 1), `honda_<model>/` (Study 2), and `gptoss120b/`, `swallow70b_full/` (preliminary versions of the battery; Table 1 rows marked †). GPT-OSS 120B used `data/persona_screening_stimuli.json`; Swallow-70B used an earlier version of the Honda stimuli that is not included. Each folder holds:

- `screening_summary.json` — scores: `check1a` and `check1b` (Test 1), `check2` (Test 3), and `_meta` (model, stimulus file, cost)
- `screening_raw.json` — every model response, including the reasoning text

Group simulation outputs (Stage 3) are not included in this repository; see the top-level README.
