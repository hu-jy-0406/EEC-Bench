# Independent server batches

The complete 1–400 ranking is unchanged. Assign the existing server 0–100 and each new
server one additional batch. Ranges use zero-based, end-exclusive offsets: 100–150
contains 50 episodes, ranks 101–150. The seven batches have no overlaps and cover all
400 episodes. A batch priority expresses the preferred expansion order; separately
assigned servers may run their batches concurrently. No central scheduler is included.

| Priority | Offset range | Existing ranks | Episodes | Shots | Archive |
|---|---|---|---:|---:|---|
| P1 | 0–100 | 1–100 | 100 | 500 | [ZIP](batches/storymem_inputs_0000_0100.zip) |
| P2 | 100–150 | 101–150 | 50 | 252 | [ZIP](batches/storymem_inputs_0100_0150.zip) |
| P3 | 150–200 | 151–200 | 50 | 248 | [ZIP](batches/storymem_inputs_0150_0200.zip) |
| P4 | 200–250 | 201–250 | 50 | 252 | [ZIP](batches/storymem_inputs_0200_0250.zip) |
| P5 | 250–300 | 251–300 | 50 | 248 | [ZIP](batches/storymem_inputs_0250_0300.zip) |
| P6 | 300–350 | 301–350 | 50 | 252 | [ZIP](batches/storymem_inputs_0300_0350.zip) |
| P7 | 350–400 | 351–400 | 50 | 248 | [ZIP](batches/storymem_inputs_0350_0400.zip) |

## Download only the assigned batch (example: 100–150)

```bash
hf auth login
hf download BlueSourceJY/eec-bench-storymem-400 batches/storymem_inputs_0100_0150.zip batches/storymem_inputs_0100_0150.zip.sha256 --repo-type dataset --local-dir storymem_dataset
cd storymem_dataset/batches
sha256sum -c storymem_inputs_0100_0150.zip.sha256
unzip storymem_inputs_0100_0150.zip
python storymem_inputs_0100_0150/verify_bundle.py
python storymem_inputs_0100_0150/list_story_scripts.py > assigned_story_scripts.txt
```

Replace `0100_0150` with the assigned batch ID. Each ZIP is self-contained: its index.json
and generation_queue.jsonl contain ONLY that batch, with portable paths resolved
relative to its extracted directory. Feed each listed native story_script.json to the
existing StoryMem runner through its official --story_script_path argument. Use a
separate output directory per episode. list_story_scripts.py only enumerates inputs.

## Full bundle and compatibility

Download only storymem_inputs_400.zip and its .sha256 sidecar if you need all 400.
The full archive extracts to storymem_inputs/. Select one batch using
`python storymem_inputs/list_story_scripts.py --batch 0100_0150` or use the corresponding
batches/batch_0100_0150.jsonl. Existing core_100.jsonl, priority_200.jsonl,
stage2_additional_100.jsonl, stage3_remaining_200.jsonl, index.json and episode files
remain byte-identical. The old coarse stages remain compatibility views. New
priority_150/250/300/350.jsonl are CUMULATIVE evaluation subsets, not additional jobs.
Do not dispatch a cumulative subset as a new batch. All models share the same episode
IDs/order. These archives contain StoryMem inputs; HoloCine requires its own native
input adapter and runtime. The manifest/ID lists define common assignments for both.

## Preserved input semantics

Every episode includes unchanged story_script.json, contract.json,
alignment_contract.json, entity_schedule.json and shot_mapping.json. Use the native
video_prompts as delivered, with all cut flags true. Earlier context is already
included where needed; do not append schedules, claims or other shots to the text.
Map native scene/shot output names using shot_mapping.json; scene occurrence numbers
are not persistent scene identities. Schedule omission is not a prohibition.
Original ambiguity records and the previous validation report are retained in the
full archive. Per-batch ZIPs retain the original contracts and claims verbatim.

This is a dispatch/export change only: no reranking, new prompt rewriting, model
inference or fresh semantic annotation. Full source order, first100 and all episode
payload hashes are verified. The previously audited tokenizer inputs are unchanged;
this update does not repeat tokenization. Lower batch number means earlier priority,
not a calibrated difficulty or quality score. Existing strict cluster campaign
barriers were not changed by exporting these independent assignments.

For reproducible downloads, add --revision <commit> to hf download and use the same
commit on all rented servers. Keep the account's existing private-repository access.
Official StoryMem: https://github.com/Kevin-thu/StoryMem
Previously tested code commit: 052c68d2627a22a95f79dbb4d3376cc30c96f1a3.

Local model-specific queues and their path roots are recorded in queue_roots.json.
