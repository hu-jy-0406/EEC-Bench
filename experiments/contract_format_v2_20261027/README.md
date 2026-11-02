# Contract v2 layout: example conversion (2026-10-27)

Owner-requested layout, applied to one episode. Spec, conversion rules and open
points: `EECBench/docs/episode-contract-v2-format.md`.

| File | Content |
| --- | --- |
| `74Od5-Fmf60_s00006_n4_clean_v2/contract.json` | model-facing version, no evidence (23 KB) |
| `74Od5-Fmf60_s00006_n4_clean_v2/contract_with_evidence.json` | same content plus evidence, v1 claim IDs and the prompt (50 KB) |
| `74Od5-Fmf60_s00006_n4_clean_v2/review.md` | readable rendering of the model-facing version |
| `74Od5-Fmf60_s00006_n4_clean_v2/claim_accounting.json` | destination of every v1 claim |
| `decisions_74Od5-Fmf60_s00006.json` | hand-made judgment inputs (rewritten descriptions, kept appearance claim, framing claim moved to the shot description, shot descriptions) |
| `convert_example.py` | mechanical conversion and accounting checks |

Source: `experiments/episode_contracts_20260921/deliverables/episodes/74Od5-Fmf60_s00006_n4_clean_v2/contract.json` (v1, 102 KB, unchanged).

Rebuild (CPU, seconds):

```bash
python convert_example.py ../episode_contracts_20260921/deliverables/episodes/74Od5-Fmf60_s00006_n4_clean_v2/contract.json decisions_74Od5-Fmf60_s00006.json 74Od5-Fmf60_s00006_n4_clean_v2
```

Result (after the 2026-10-29 granularity rulings: office walls merged into the Office location, 22 entities): 161 v1 claims → presence 40, folded into entity descriptions 60,
spatial 39, motion 20, per-shot appearance 1, camera view 1. No model calls,
no cost. The descriptions and shot descriptions are the assistant's reading
of the prompt, not an independent audit.
