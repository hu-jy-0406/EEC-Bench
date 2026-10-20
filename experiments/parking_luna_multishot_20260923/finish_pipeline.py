#!/usr/bin/env python3
"""Finish non-registration scoring for the parking multi-shot experiment.

This adapter deliberately consumes only the frozen scene-global *initial*
identity result.  No final aligned-identity review can be made because the
registration stage accepted no coordinate transform.  It exports that fact in
the registry policy rather than pretending that an aligned review occurred.

The script has small phases so CPU/API work can be restarted independently:
``registry``, ``reference``, ``within``, and ``displacement``.  Appearance,
binding, and prompt alignment use their existing project entrypoints after
these files have been materialized.
"""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from gs_entity_displacement import aggregate, within

HERE = Path(__file__).resolve().parent
CASE = HERE / "shared" / "parking4"


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def registry():
    """Materialize a canonical registry without inventing final-review links."""
    out = CASE / "global_entities"
    if out.exists():
        raise FileExistsError(f"Fresh output required: {out}")
    manifest = read(CASE / "raw_manifest.json")
    initial = read(CASE / "global_initial" / "results.json")
    inventories = {
        shot["shot_id"]: read(CASE / "shot_prompt_recovery" / "entities" / "shots" /
                              shot["shot_id"] / "entities.json")
        for shot in manifest["shots"]
    }
    nodes = {}
    for shot in manifest["shots"]:
        sid = shot["shot_id"]
        expected = [f["frame_id"] for f in shot["frames"]]
        for entity in inventories[sid]["entities"]:
            if [o["frame_id"] for o in entity["observations"]] != expected:
                raise ValueError(f"Observation frame mismatch: {sid}/{entity['entity_id']}")
            key = f"{sid}/{entity['entity_id']}"
            if key in nodes:
                raise ValueError(f"Duplicate local node: {key}")
            nodes[key] = dict(shot_id=sid, local_entity_id=entity["entity_id"],
                              name=entity["name"],
                              observed_frame_ids=[o["frame_id"] for o in entity["observations"]
                                                  if o["exist"] is True and o["box_xyxy"] is not None],
                              observations=copy.deepcopy(entity["observations"]))
    assigned = set()
    entities, local_to_global = [], {}
    for i, group in enumerate(initial["groups"], 1):
        members = group["entity_ids"]
        if not members or any(m not in nodes or m in assigned for m in members):
            raise ValueError(f"Invalid exact-once initial group: {group['group_id']}")
        assigned.update(members)
        appearances = [copy.deepcopy(nodes[m]) for m in members]
        gid = f"ge{i:04d}"
        local_to_global.update({m: gid for m in members})
        entities.append(dict(global_entity_id=gid, name=appearances[0]["name"], scene_id="parking",
                             observed_shot_ids=[a["shot_id"] for a in appearances], appearances=appearances,
                             initial_group_id=group["group_id"],
                             initial_identity_evidence=group["identity_evidence"]))
    # Be conservative: any unassigned local entity remains a singleton.
    for member in sorted(set(nodes) - assigned):
        gid = f"ge{len(entities)+1:04d}"
        local_to_global[member] = gid
        entities.append(dict(global_entity_id=gid, name=nodes[member]["name"], scene_id="parking",
                             observed_shot_ids=[nodes[member]["shot_id"]],
                             appearances=[copy.deepcopy(nodes[member])], initial_group_id=None,
                             initial_identity_evidence="No scene-global initial group; singleton retained."))
    for e in entities:
        for a in e["appearances"]:
            folder = CASE / "shot_prompt_recovery" / "entities" / "shots" / a["shot_id"]
            a["source_entities_file"] = str(folder / "entities.json")
            a["source_candidates_file"] = str(folder / "input.json")
    sources = {str(CASE / "raw_manifest.json"): sha(CASE / "raw_manifest.json"),
               str(CASE / "global_initial" / "results.json"): sha(CASE / "global_initial" / "results.json"),
               str(Path(__file__).resolve()): sha(Path(__file__).resolve())}
    for sid in inventories:
        p = CASE / "shot_prompt_recovery" / "entities" / "shots" / sid / "entities.json"
        sources[str(p)] = sha(p)
    result = dict(
        schema_version="episode_entities_v1",
        policy="scene_global_initial_confirmed_groups_only_no_aligned_review",
        occurrence_semantics="Positive shot-local detector observations only; omitted shots are unknown, not absent.",
        identity_scope="Scene-global initial associations. No post-registration aligned identity review was possible because every shot remained in a distinct coordinate group.",
        shot_order=[s["shot_id"] for s in manifest["shots"]], entities=entities,
        local_to_global=local_to_global, confirmed_identity_links=[], unresolved_identity_links=initial["unresolved"],
        unmatched_records=[], counts=dict(local_entities=len(nodes), global_records=len(entities),
                                           initial_groups=len(initial["groups"]), confirmed_links=0,
                                           unresolved_links=len(initial["unresolved"])),
        appearance_score_computed=False, source_case=str(CASE), source_hashes=sources)
    out.mkdir()
    save(out / "global_entities.json", result)
    save(out / "PROTOCOL_STATUS.json", dict(status="limited_no_aligned_review",
        reason="All four shots were assigned separate coordinate groups by the frozen registration result.",
        downstream_uses="Prompt binding/alignment and appearance use the frozen initial scene-global groups; cross-shot geometry scores are not computed."))
    print(json.dumps(result["counts"], ensure_ascii=False))


def reference():
    """Create the text-only compiler input for the normal-story prompt contract."""
    out = CASE / "prompt_alignment_compile_input.json"
    if out.exists():
        raise FileExistsError(f"Fresh output required: {out}")
    narrative = read(CASE / "narrative.json")
    registry_data = read(CASE / "prompt_registry.json")
    source = dict(reference_text="\n\n".join(
        f"{row['shot_id']}: {row['text']}" for row in narrative["facts"]),
        shot_ids=[row["shot_id"] for row in narrative["facts"]], narrative=narrative, registry=registry_data)
    save(out, source)
    print(out)


def within_scores():
    """Run deterministic within-shot displacement only; no boundary coordinates exist."""
    out = CASE / "displacement_within_only"
    if out.exists():
        raise FileExistsError(f"Fresh output required: {out}")
    manifest = read(CASE / "raw_manifest.json")
    shots = {}
    for shot in manifest["shots"]:
        sid = shot["shot_id"]
        graph = read(CASE / "selected" / f"{sid}_scene.json")
        shots[sid] = within(graph)
    records = [r for data in shots.values() for r in data["records"]]
    result = dict(protocol="entity_displacement_median_rms_v1", status="success",
                  scope="within_shots_only", source_case=str(CASE), within_shots=shots,
                  boundaries=dict(status="not_evaluable_no_accepted_cross_shot_transform",
                                  coordinate_groups=read(CASE / "direct_prompt_bound_luna" / "results.json")["roots"]),
                  episode=dict(within=aggregate(records), cross=None, all=aggregate(records)), records=records,
                  model_calls=0, total_tokens=0, api_usd=0,
                  limitation="Cross-shot distances are undefined: registration left every shot in a distinct coordinate group.")
    out.mkdir()
    save(out / "results.json", result)
    print(json.dumps(result["episode"], ensure_ascii=False))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["registry", "reference", "displacement"])
    a = p.parse_args()
    {"registry": registry, "reference": reference, "displacement": within_scores}[a.phase]()


if __name__ == "__main__":
    main()
