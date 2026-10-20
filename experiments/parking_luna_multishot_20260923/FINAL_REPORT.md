# Parking multi-shot — final pipeline report

All executable stages completed from the frozen frontend. Cross-shot geometry is reported as not evaluable, rather than being assigned a numerical score, because direct prompt-bound registration accepted no common coordinate transform.

| Dimension | Result |
|---|---:|
| Prompt alignment — presence | 100.0000/100 |
| Prompt alignment — appearance | 100.0000/100 |
| Prompt alignment — spatial | 94.4444/100 |
| Prompt alignment — motion | 100.0000/100 |
| Within-shot spatial consistency | 100/100 in Shot1–Shot4 |
| Within-shot static-entity position displacement | 61.7807/100 (11/23 records scored) |
| Appearance — Codex, all entities | 86.4583/100 (8/9) |
| Appearance — Codex, multi-shot entities | 81.9444/100 (6/6) |
| Appearance — DINO, all entities | 0.774840 cosine |
| Appearance — DINO, multi-shot entities | 0.697087 cosine |
| Cross-shot position / spatial consistency | not evaluable: no accepted transform |

Prompt binding: 8 bound, 0 unbound, 1 unknown. The unknown is the complete handbag; the prompt only names its strap.

No overall scalar is emitted because this run has no valid cross-shot coordinate frame. API billing cost is unavailable: legacy Astra-equivalent fields in some artifacts are not invoices for the user-supplied Luna route.
