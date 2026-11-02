"""Convert one v1 episode contract (episode_schedule_claims_v1) into the draft v2 layout.

Mechanical parts (entity ids, presence lists, spatial and motion requirements, accounting of every
original claim) are done here; judgment inputs (rewritten descriptions, kept appearance claims,
shot descriptions) come from the decisions file. Writes, into OUT_DIR:
  contract.json                  model-facing version, no evidence
  contract_with_evidence.json    same content plus evidence, source claim IDs and the prompt
  claim_accounting.json          where every v1 claim went
  review.md                      readable rendering

Usage: python convert_example.py SRC_CONTRACT DECISIONS OUT_DIR
"""
import json
import pathlib
import sys

LABEL_ORDER = ["Character", "Location", "Object"]
DIM_TAG = {"appearance": "app", "spatial": "spa", "motion": "mot"}


def quotes(claim):
    return [{"shot_id": e["fact_id"], "quote": e["quote"]} for e in claim["evidence"]]


def dedup(items):
    seen, out = set(), []
    for it in items:
        key = json.dumps(it, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def main(src, decisions_path, out_dir):
    c = json.loads(pathlib.Path(src).read_text())
    d = json.loads(pathlib.Path(decisions_path).read_text())
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    old = c["entity_descriptions"]
    order = sorted(old, key=lambda k: (LABEL_ORDER.index(k.split()[0]), int(k.split()[1])))
    # Owner rule: walls are part of the location, so merged entities get no ID of their own.
    merged = {n: t for n, t in d.get("merge_into_location", {}).items() if n != "rule"}
    key_of = {old[k]["name"]: k for k in order}
    kept = [k for k in order if old[k]["name"] not in merged]
    new_id = {k: i for i, k in enumerate(kept)}
    for name, target in merged.items():
        assert key_of[target].startswith("Location"), f"{name}: merge target must be a location"
        new_id[key_of[name]] = new_id[key_of[target]]
    name_to_id = {old[k]["name"]: new_id[k] for k in order}
    assert set(d["descriptions"]) == {old[k]["name"] for k in kept}, "every kept entity needs a rewritten description"

    entities = {}
    for k in kept:
        e = old[k]
        entities[new_id[k]] = {
            "label": k.split()[0].lower(),
            "name": e["name"],
            "description": d["descriptions"][e["name"]],
            "evidence": [{"shot_id": q["fact_id"], "quote": q["quote"]} for q in e["evidence"]],
            "source_label": k,
        }
    for name, target in merged.items():
        e = entities[name_to_id[target]]
        e["evidence"] += [{"shot_id": q["fact_id"], "quote": q["quote"]} for q in old[key_of[name]]["evidence"]]
        e["merged_source_labels"] = e.get("merged_source_labels", []) + [key_of[name]]
    merged_keys = {key_of[n] for n in merged}

    shot_key = {s["shot_id"]: s["schedule_key"] for s in c["prompt"]["shots"]}
    claims_by_shot = {s: [q for q in c["claims"] if q["shot_ids"] == [s]] for s in shot_key}
    assert sum(len(v) for v in claims_by_shot.values()) == len(c["claims"]), "multi-shot claims are not handled"

    accounting = {}
    shots = []
    for n, (sid, key) in enumerate(shot_key.items(), start=1):
        sch = c["entity_schedule"][key]
        scheduled = sch["characters"] + sch["places"] + sch["objects"]
        presence = sorted({name_to_id[x] for x in scheduled})
        # Owner location rule: main setting only; two only when the camera moves between locations.
        locations = [name_to_id[x] for x in d["locations"][sid]["value"]]
        assert all(entities[i]["label"] == "location" and i in presence for i in locations), f"{sid}: bad location"
        counters = {"app": 0, "spa": 0, "mot": 0}
        lists = {"appearance": [], "spatial": [], "motion": []}
        camera_from_claims = []

        for q in claims_by_shot[sid]:
            cid, dim = q["claim_id"], q["dimension"]
            ids = list(dict.fromkeys(new_id[x] for x in q["entity_ids"]))
            via = [x for x in q["entity_ids"] if x in merged_keys]
            note = {"merged_into_location_from": via} if via else {}
            if dim == "presence":
                assert q["predicate"] == "present" and q["quantifier"] == "exists" and len(ids) == 1
                assert ids[0] in presence, f"{cid}: presence claim outside the schedule"
                accounting[cid] = {"to": "presence", "shot_id": sid, "entity": ids[0], **note}
                continue
            assert all(dep.startswith("p") for dep in q["depends_on"]), f"{cid}: non-presence dependency"
            if dim == "appearance" and cid not in d["appearance_keep"]:
                assert len(ids) >= 1
                entities[ids[0]]["evidence"] += quotes(q)
                accounting[cid] = {"to": "entity_description", "entity": ids[0], **note}
                continue
            if dim == "spatial" and cid in d["spatial_to_shot_description"]:
                camera_from_claims.append(cid)
                accounting[cid] = {"to": "shot_description.camera_view", "shot_id": sid}
                continue
            tag = DIM_TAG[dim]
            counters[tag] += 1
            rid = f"S{n}-{tag}-{counters[tag]}"
            item = {"id": rid, "entities": ids, "expected": q["expected"]}
            if dim != "appearance":
                item.update({"predicate": q["predicate"], "coordinate_frame": q["coordinate_frame"]})
            item.update({"quantifier": q["quantifier"], "evidence": quotes(q), "source_claim_ids": [cid]})
            lists[dim].append(item)
            accounting[cid] = {"to": dim, "shot_id": sid, "id": rid, **note}

        sd = d["shot_descriptions"][sid]
        desc = {}
        for field in ("camera_view", "camera_movement", "transition_from_previous"):
            v = sd[field]
            if v is None:
                desc[field] = None
            elif "evidence" in v:
                desc[field] = {"value": v["value"], "evidence": [{"shot_id": sid, "quote": x} for x in v["evidence"]]}
            else:
                desc[field] = {"value": v["value"], "evidence_source": v["evidence_source"]}
        if camera_from_claims:
            desc["source_claim_ids"] = camera_from_claims
        shots.append({
            "shot_id": sid,
            "locations": locations,
            "shot_description": desc,
            "presence": presence,
            **lists,
        })

    assert set(accounting) == {q["claim_id"] for q in c["claims"]}, "a claim was not accounted for"
    for e in entities.values():
        e["evidence"] = dedup(e["evidence"])

    unresolved = c.get("unresolved", [])
    with_ev = {
        "schema_version": "episode_contract_v2_draft",
        "episode_id": c["episode_id"],
        "entity_descriptions": {str(i): e for i, e in entities.items()},
        "shots": shots,
        "unresolved": unresolved,
        "prompt": {"global_prompt": c["prompt"]["global_prompt"],
                   "shots": [{"shot_id": s["shot_id"], "text": s["text"]} for s in c["prompt"]["shots"]]},
    }

    def strip(obj):
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if k in ("evidence", "evidence_source", "source_claim_ids", "source_label",
                         "merged_source_labels", "prompt"):
                    continue
                out[k] = strip(v)
            if set(out) == {"value"}:
                return out["value"]
            return out
        if isinstance(obj, list):
            return [strip(x) for x in obj]
        return obj

    no_ev = strip(with_ev)
    (out / "contract_with_evidence.json").write_text(json.dumps(with_ev, ensure_ascii=False, indent=2) + "\n")
    (out / "contract.json").write_text(json.dumps(no_ev, ensure_ascii=False, indent=2) + "\n")
    summary = {}
    for a in accounting.values():
        summary[a["to"]] = summary.get(a["to"], 0) + 1
    (out / "claim_accounting.json").write_text(json.dumps(
        {"v1_claims": len(c["claims"]), "summary": summary, "claims": accounting}, ensure_ascii=False, indent=2) + "\n")
    (out / "review.md").write_text(render(no_ev, summary, len(c["claims"])))
    print(json.dumps(summary), "of", len(c["claims"]))


def render(k, summary, n_claims):
    ents = k["entity_descriptions"]
    nm = lambda i: f"{i} {ents[str(i)]['name']}"
    lines = [f"# Contract v2 draft: {k['episode_id']}", "",
             f"Model-facing version (no evidence). Converted from the v1 contract; {n_claims} v1 claims: "
             + ", ".join(f"{v} → {key}" for key, v in summary.items()) + ".", "",
             "## entity_descriptions", "", "| id | label | name | description |", "|---|---|---|---|"]
    for i, e in ents.items():
        lines.append(f"| {i} | {e['label']} | {e['name']} | {e['description']} |")
    for s in k["shots"]:
        sd = s["shot_description"]
        lines += ["", f"## {s['shot_id']}", "",
                  f"- **locations**: " + ", ".join(nm(i) for i in s["locations"]),
                  f"- **camera_view**: {sd['camera_view']}",
                  f"- **camera_movement**: {sd['camera_movement']}",
                  f"- **transition_from_previous**: {sd['transition_from_previous']}",
                  f"- **presence**: " + ", ".join(nm(i) for i in s["presence"])]
        for dim in ("appearance", "spatial", "motion"):
            items = s[dim]
            lines += ["", f"**{dim}** ({len(items)})", ""]
            if not items:
                lines.append("(none)")
                continue
            lines += ["| id | entities | expected | quantifier |", "|---|---|---|---|"]
            for it in items:
                lines.append(f"| {it['id']} | {', '.join(nm(i) for i in it['entities'])} | {it['expected']} | {it['quantifier']} |")
    lines += ["", "## unresolved", ""] + [f"- {u}" for u in k["unresolved"]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main(*sys.argv[1:4])
