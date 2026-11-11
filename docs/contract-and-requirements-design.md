# Prompt-derived files: contract and compiled requirement list (design, 2026-11-05)

Status: decided by the assistant at the owner's request ("我需要你帮我决定的是这些信息应该怎么组织最优雅/好讲故事，
并且便于在Pipeline中使用，以及discovery、detection等各个阶段各自使用其中的哪些部分/字段"); implemented 2026-11-05 on the owner's
go-ahead ("Yes, implement it, using sonnet agent also instead of gpt-6"; coded by a Sonnet subagent, no model calls: the
compilation is deterministic). Code `scripts/episode_requirements.py`, `scripts/compile_episode_requirements.py`;
packages `experiments/compiled_requirements_20261105/compiled/<episode>/`; report
`experiments/compiled_requirements_20261105/REPORT.md`. Owner requirement: the requirement list is derived once, not at
every pipeline run, so repeated experiments reuse it. This replaces the earlier proposal to merge everything into one
"requirement contract" (v3).

## 1. Decision

Each episode has three prompt-derived files. Only the first two are written by people or agents; the third
is compiled from the contract once, by a deterministic program, and never edited.

| File | Role | Made by | Organized by |
| --- | --- | --- | --- |
| `prompt.json` | the original wording (global prompt, shot prompts) | source | text |
| `contract.json` | what the prompt specifies, as a structured summary: the ground truth | contract agents + cleanup (v2, unchanged) | entities and shots |
| `requirements.json` | what is checked: every checkable statement with an ID | compiled once from the contract | one flat list |

Why two structured files and not one:

- They answer two different questions. The contract says what the video should contain (who and what
  exists, how each shot is set up and what happens); people read, edit and audit it. The requirement list
  says what is checked; programs and the prompt alignment branch read it.
- The list contains statements the contract leaves implicit: each entity's presence and absence per shot,
  its description in every shot where it appears, the camera and style values, and a cut at every boundary.
  Making them explicit once, with IDs and their generated wording, is exactly the derivation that now runs
  in every pipeline run.
- The list is a function of the contract (the file records the contract's SHA-256 and the compiler
  version), so the two cannot drift apart; a contract change means recompiling, never editing the list.

Story for the paper (Section 3.1): "We compile each prompt into a contract with two parts: an entity
registry (every specified entity with its category, name and description) and a shot plan (per shot: its
setting, the entities it must and must not show, its camera and style, and its appearance, spatial and
motion requirements; plus requirements across shots). Flattening the contract gives a requirement list in
which every checkable statement, including presence, absence, descriptions, camera, style and cuts, has an
identifier." The rest of the method then refers to "the registry", "the shot plan" and "requirement r".

## 2. requirements.json (schema episode_requirements_v1)

```json
{
  "schema_version": "episode_requirements_v1",
  "episode_id": "N39I1LM-HGY_s00208_n8_clean_v3_alt8",
  "contract_sha256": "...", "compiler": {"name": "episode_requirements.py", "sha256": "..."},
  "shot_ids": ["Shot1", "Shot2", "..."],
  "requirements": [
    {"id": "S1-pre-0", "group": "EN:0@Shot1", "kind": "presence", "dimension": "presence", "shot_id": "Shot1",
     "entities": ["0"], "text": "Robe woman: visible in this shot.", "quantifier": "exists"},
    {"id": "S1-des-0", "group": "EN:0@Shot1", "kind": "description", "shot_id": "Shot1", "entities": ["0"],
     "text": "An older fair-skinned woman ..."},
    {"id": "S1-spa-2", "group": "EN:0@Shot1", "kind": "spatial", "dimension": "spatial", "shot_id": "Shot1",
     "entities": ["0"], "text": "She is on the left of the view.", "predicate": "screen_position",
     "coordinate_frame": "screen", "quantifier": "exists"},
    {"id": "S1-cam-view", "group": "CM:Shot1", "kind": "camera_view", "shot_id": "Shot1", "text": "medium view"},
    {"id": "S2-cut", "group": "TR:Shot1->Shot2", "kind": "cut", "shot_id": "Shot2", "from_shot": "Shot1",
     "text": "..."},
    {"id": "X-1", "group": "XS:X-1", "kind": "cross_shot", "dimension": "spatial", "shot_ids": ["Shot1", "Shot3"],
     "entities": ["0"], "text": "...", "quantifier": "cross_shot"}
  ]
}
```

- Exactly today's requirement list (`vl_vv_requirement_answers.requirements` over
  `contract_template_v2`): same IDs, kinds, texts, entities and order; `group` is today's template row.
- Nothing video-specific: ledger IDs are joined at run time from the case's ledger (every ledger record
  carries its contract ID), as today.
- The discovery views that are also pure functions of the contract are compiled at the same time:
  `prompt_registry.json` (every contract entity with its per-shot expectation) and `narrative.json` (per
  shot, the names of the entities it must show), today written by `run_vl_vv_detection.py prepare` per case.

## 3. Which stage reads what

| Stage | Reads | Fields |
| --- | --- | --- |
| Detection (WeDetect) | nothing prompt-derived | fixed vocabulary, floor-covering filter |
| Shot clustering | nothing prompt-derived | own-shot detections and keyframes only (isolation) |
| Prompt binding (per shot) | registry, narrative | entity id, name, description; this shot's expectation (required / not_required); names this shot must show |
| Grounding DINO recovery | registry | entities required in the shot and still unbound; the query the binding call wrote |
| Matching v2 | registry, contract, prompt | specified entities (name, description, category); per-shot `locations`; prompt text as context |
| V-L detection | requirements, contract, prompt | every requirement (the answers schema = requirement IDs); entity names and descriptions; contract and prompt as context (owner, 2026-11-05: keep the contract input) |
| V-V detection | contract, prompt, registry labels via the ledger | per-shot presence (continuity subjects: entities in two or more shots), motion and camera statements (prompted changes are normal); specified / unspecified label of each ledger entity |
| V-L verification | requirements, contract, prompt | the requirement(s) each issue cites, by ID, with text and group; contract and prompt as context |
| V-V verification | contract, prompt | context for "does the prompt call for this change"; locations (setting gates) |
| Scoring | none | dimension and verdict of each issue |
| Analysis / paper | requirements | counts by kind and dimension (Table 3), per-requirement results |

What changes for the stages: nothing in what the models receive. The runner loads `requirements.json`
instead of deriving it, and loads the compiled registry and narrative instead of building them; every
result records the contract and requirement-list hashes, which are the same for all five models' videos of
an episode. (Two inputs are larger than what the stage needs: V-L detection gets the contract beside the
list, which the owner chose to keep; verification gets the whole contract although issues cite their
requirements. Trimming either changes model input and would need its own A/B; not part of this change.)

## 4. Implementation

1. `scripts/episode_requirements.py`: `compile(contract, prompt) -> requirements` (the current template and
   list code moved, not rewritten), `load(case)` (verifies `contract_sha256` against the case contract),
   and the registry / narrative builders moved from `run_vl_vv_detection.py`.
2. Export: `compile_contracts.py` writes `requirements.json`, `prompt_registry.json` and `narrative.json`
   for every exported contract (deliverables per episode plus a jsonl), after the cleanup export.
3. Cases: `prepare_case.py` / `run_vl_vv_detection.py prepare` copy the compiled files instead of computing
   them; detection and review read `case/requirements.json`. A historical case without it is compiled in
   memory and the result records `requirements_source: compiled_at_run`.
4. Checks (no model calls): compiled == run-time derivation for all 200 cleaned and 400 v2 contracts; the
   detection, verdict and binding payloads of the 29 frozen-frontend test cases are byte-identical before
   and after; VL/VV test set passes.

## 5. Order

Q5 (in progress) changes contracts; compile after the Q5 export, so the full run uses Q5 contracts and
their compiled lists. Paper 3.1 can then describe the registry, the shot plan and the requirement list.
