"""Pure, reversible verifier-input representation; no inference or output repair."""
from __future__ import annotations

import copy
import hashlib
import json
import math


FORMAT_VERSION = "verification_view_tables_v0.1"
SPLITS = "intra_cluster_divergent_footprint_challenges"
PAIRS = "identity_challenge_pairs"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _json(value):
    if type(value) is dict:
        _require(all(type(k) is str for k in value), "JSON keys must be strings")
        for item in value.values():
            _json(item)
    elif type(value) is list:
        for item in value:
            _json(item)
    else:
        _require(type(value) in (str, int, float, bool, type(None)), "Non-JSON value")
        if type(value) is float:
            _require(math.isfinite(value), "Non-finite number")


def canonical_bytes(value):
    """Preserve JSON number types and signed zero; not original text whitespace."""
    _json(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_sha256(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _same(left, right):
    return canonical_bytes(left) == canonical_bytes(right)


def _object(value):
    _require(type(value) is dict, "Expected JSON object")
    return value


def _list(value):
    _require(type(value) is list, "Expected JSON array")
    return value


def _keys(value, required, optional=()):
    _object(value)
    _require(set(required) <= value.keys() <= set(required) | set(optional),
             "Missing or unexpected representation field")


def _index(value):
    _require(type(value) is int and value >= 0, "Index/frame ID must be nonnegative int")
    return value


def _id(value):
    _require(type(value) is str and bool(value), "ID must be a nonempty string")
    return value


def _without(value, *keys):
    return {k: copy.deepcopy(v) for k, v in value.items() if k not in keys}


def _inventory(view):
    _json(view)
    _object(view)
    scopes, proposals, owners = {}, {}, {}
    for target in _list(view["targets"]):
        _object(target)
        cluster = _id(target["cluster_id"])
        _require(cluster not in scopes, "Duplicate target owner")
        scopes[cluster] = []
        for proposal in _list(target["proposals"]):
            _object(proposal)
            key = _id(proposal["anonymous_proposal_id"])
            _require(key not in proposals, "Duplicate proposal or multiple owners")
            scopes[cluster].append(key)
            proposals[key], owners[key] = proposal, cluster
            if type(proposal.get("frame_presence")) is list:
                for row in proposal["frame_presence"]:
                    _object(row)
                    _index(row["frame_id"])
    indexed = []
    for row in _list(view["cluster_index"]):
        indexed.append(_id(_object(row)["cluster_id"]))
    _require(len(indexed) == len(set(indexed)), "Duplicate cluster index ID")
    _require(set(scopes) <= set(indexed), "Target missing from original cluster index")
    return scopes, proposals, owners


def _encode_frames(rows):
    runs = []
    for index, row in enumerate(rows):
        value = _without(row, "frame_id")
        if runs and _same(runs[-1]["value"], value):
            runs[-1]["frame_ids"].append(row["frame_id"])
        else:
            runs.append({"start_index": index, "frame_ids": [row["frame_id"]], "value": value})
    return {"count": len(rows), "runs": runs}


def _decode_frames(table):
    _keys(table, ("count", "runs"))
    count, rows = _index(table["count"]), []
    for run in _list(table["runs"]):
        _keys(run, ("start_index", "frame_ids", "value"))
        _require(_index(run["start_index"]) == len(rows), "Frame run overlap/gap/order error")
        ids, value = _list(run["frame_ids"]), _object(run["value"])
        _require(bool(ids) and "frame_id" not in value, "Empty run or conflicting frame ID")
        for frame_id in ids:
            rows.append({**copy.deepcopy(value), "frame_id": _index(frame_id)})
    _require(len(rows) == count, "Frame count mismatch")
    return rows


def _split_owner(record, scopes):
    owner = _id(record["cluster_id"])
    _require(owner in scopes, "Split owner lacks complete target scope")
    return owner


def _endpoint(pair, side, owner, owners):
    key = _id(pair["proposal_id_" + side])
    _require(owners.get(key) == owner, "Split endpoint is outside its owner scope")
    return key


def _encode_bbox(value, proposal_id, frame_id, proposals):
    rows = proposals[proposal_id].get("frame_presence")
    rows = rows if type(rows) is list else []
    same_frame = [(i, row) for i, row in enumerate(rows) if _same(row["frame_id"], frame_id)]
    if len(same_frame) == 1:
        index, row = same_frame[0]
        if "bbox_xyxy_normalized" in row and _same(value, row["bbox_xyxy_normalized"]):
            return {"ref": {"proposal_id": proposal_id, "frame_presence_index": index}}
    return {"literal": copy.deepcopy(value)}


def _decode_bbox(encoded, proposal_id, frame_id, proposals):
    _object(encoded)
    if set(encoded) == {"literal"}:
        return copy.deepcopy(encoded["literal"])
    _keys(encoded, ("ref",))
    ref = encoded["ref"]
    _keys(ref, ("proposal_id", "frame_presence_index"))
    _require(ref["proposal_id"] == proposal_id, "Wrong split endpoint reference")
    rows = _list(proposals[proposal_id].get("frame_presence"))
    index = _index(ref["frame_presence_index"])
    _require(index < len(rows), "Frame reference out of range")
    row = rows[index]
    _require(_same(row["frame_id"], frame_id), "Frame reference points to another frame")
    _require(sum(_same(r["frame_id"], frame_id) for r in rows) == 1, "Ambiguous frame reference")
    _require("bbox_xyxy_normalized" in row, "Referenced bbox is missing")
    return copy.deepcopy(row["bbox_xyxy_normalized"])


def encode_verification_view(view):
    """Encode supplied view only. Unknown original fields remain verbatim."""
    scopes, proposals, owners = _inventory(view)
    encoded = {"representation_version": FORMAT_VERSION, "source_sha256": content_sha256(view),
               "record": _without(view, "targets", PAIRS, SPLITS), "scopes": [], "proposals": []}
    for target in view["targets"]:
        encoded["scopes"].append({"record": _without(target, "proposals"),
                                  "proposal_ids": scopes[target["cluster_id"]]})
        for proposal in target["proposals"]:
            row = {"record": copy.deepcopy(proposal)}
            if type(proposal.get("frame_presence")) is list:
                row["record"].pop("frame_presence")
                row["frame_table"] = _encode_frames(proposal["frame_presence"])
            encoded["proposals"].append(row)
    if PAIRS in view:
        encoded["pair_questions"] = [{"question_id": f"pair_{i:06d}", "record": copy.deepcopy(row)}
                                     for i, row in enumerate(_list(view[PAIRS]))]
    if SPLITS in view:
        encoded["split_questions"] = []
        for i, challenge in enumerate(_list(view[SPLITS])):
            owner = _split_owner(challenge, scopes)
            item = {"question_id": f"split_{i:06d}",
                    "record": _without(challenge, "divergent_proposal_pairs"), "proposal_pairs": []}
            for j, pair in enumerate(_list(challenge["divergent_proposal_pairs"])):
                endpoints = {side: _endpoint(pair, side, owner, owners) for side in ("a", "b")}
                output = {"question_id": f"split_{i:06d}_pair_{j:06d}",
                          "record": _without(pair, "frame_evidence"), "frame_evidence": []}
                for evidence in _list(pair["frame_evidence"]):
                    _index(evidence["frame_id"])
                    entry = {"record": _without(evidence, "bbox_a_xyxy_normalized", "bbox_b_xyxy_normalized")}
                    for side in ("a", "b"):
                        field = "bbox_" + side + "_xyxy_normalized"
                        if field in evidence:
                            entry["bbox_" + side] = _encode_bbox(evidence[field], endpoints[side],
                                                               evidence["frame_id"], proposals)
                    output["frame_evidence"].append(entry)
                item["proposal_pairs"].append(output)
            encoded["split_questions"].append(item)
    return encoded


def decode_verification_view(encoded):
    """Validate table ownership/references and reconstruct the original JSON value."""
    _json(encoded)
    _keys(encoded, ("representation_version", "source_sha256", "record", "scopes", "proposals"),
          ("pair_questions", "split_questions"))
    _require(encoded["representation_version"] == FORMAT_VERSION, "Unsupported representation")
    view = copy.deepcopy(_object(encoded["record"]))
    _require(not {"targets", PAIRS, SPLITS} & view.keys(), "Conflicting original top-level field")
    proposals = {}
    for row in _list(encoded["proposals"]):
        _keys(row, ("record",), ("frame_table",))
        proposal = copy.deepcopy(_object(row["record"]))
        key = _id(proposal["anonymous_proposal_id"])
        _require(key not in proposals, "Duplicate proposal table ID")
        if "frame_table" in row:
            _require("frame_presence" not in proposal, "Conflicting frame presence")
            proposal["frame_presence"] = _decode_frames(row["frame_table"])
        proposals[key] = proposal
    view["targets"], used = [], []
    for scope in _list(encoded["scopes"]):
        _keys(scope, ("record", "proposal_ids"))
        target = copy.deepcopy(_object(scope["record"]))
        _require("proposals" not in target, "Conflicting proposal field")
        keys = _list(scope["proposal_ids"])
        _require(all(type(key) is str and key in proposals for key in keys), "Missing proposal table reference")
        used.extend(keys)
        target["proposals"] = [copy.deepcopy(proposals[key]) for key in keys]
        view["targets"].append(target)
    _require(used == list(proposals), "Proposal table has orphan, duplicate, or reordered owner references")
    scopes, proposals, owners = _inventory(view)
    if "pair_questions" in encoded:
        view[PAIRS] = []
        for i, row in enumerate(_list(encoded["pair_questions"])):
            _keys(row, ("question_id", "record"))
            _require(row["question_id"] == f"pair_{i:06d}", "Pair question index mismatch")
            view[PAIRS].append(copy.deepcopy(row["record"]))
    if "split_questions" in encoded:
        view[SPLITS] = []
        for i, item in enumerate(_list(encoded["split_questions"])):
            _keys(item, ("question_id", "record", "proposal_pairs"))
            _require(item["question_id"] == f"split_{i:06d}", "Split question index mismatch")
            challenge = copy.deepcopy(_object(item["record"]))
            _require("divergent_proposal_pairs" not in challenge, "Conflicting split pair field")
            owner = _split_owner(challenge, scopes)
            challenge["divergent_proposal_pairs"] = []
            for j, output in enumerate(_list(item["proposal_pairs"])):
                _keys(output, ("question_id", "record", "frame_evidence"))
                _require(output["question_id"] == f"split_{i:06d}_pair_{j:06d}", "Split pair index mismatch")
                pair = copy.deepcopy(_object(output["record"]))
                _require("frame_evidence" not in pair, "Conflicting frame evidence field")
                endpoints = {side: _endpoint(pair, side, owner, owners) for side in ("a", "b")}
                pair["frame_evidence"] = []
                for entry in _list(output["frame_evidence"]):
                    _keys(entry, ("record",), ("bbox_a", "bbox_b"))
                    evidence = copy.deepcopy(_object(entry["record"]))
                    _index(evidence["frame_id"])
                    _require(not {"bbox_a_xyxy_normalized", "bbox_b_xyxy_normalized"} & evidence.keys(),
                             "Conflicting split bbox field")
                    for side in ("a", "b"):
                        if "bbox_" + side in entry:
                            evidence["bbox_" + side + "_xyxy_normalized"] = _decode_bbox(
                                entry["bbox_" + side], endpoints[side], evidence["frame_id"], proposals)
                    pair["frame_evidence"].append(evidence)
                challenge["divergent_proposal_pairs"].append(pair)
            view[SPLITS].append(challenge)
    _require(content_sha256(view) == encoded["source_sha256"], "Reconstructed source hash mismatch")
    return view


def audit_verification_view(original, encoded):
    """Check against trusted original and report reversible pointer maps and sizes."""
    restored = decode_verification_view(encoded)
    _require(_same(original, restored), "Roundtrip differs from supplied original")
    maps, row_count, run_count = [], 0, 0
    flat_index = 0
    for i, target in enumerate(original["targets"]):
        for j, proposal in enumerate(target["proposals"]):
            source = f"/targets/{i}/proposals/{j}"
            destination = f"/proposals/{flat_index}"
            maps.append({"original_pointer": source, "encoded_pointer": destination})
            table = encoded["proposals"][flat_index].get("frame_table")
            if table is not None:
                row_count += table["count"]
                run_count += len(table["runs"])
                for k, run in enumerate(table["runs"]):
                    for offset in range(len(run["frame_ids"])):
                        maps.append({"original_pointer": source + f"/frame_presence/{run['start_index'] + offset}",
                                     "encoded_pointer": destination + f"/frame_table/runs/{k}",
                                     "frame_ids_index": offset})
            flat_index += 1
    ref_count = 0
    for i, item in enumerate(encoded.get("split_questions", [])):
        for j, pair in enumerate(item["proposal_pairs"]):
            for k, entry in enumerate(pair["frame_evidence"]):
                for side in ("a", "b"):
                    if "bbox_" + side in entry:
                        bbox = entry["bbox_" + side]
                        ref_count += "ref" in bbox
                        maps.append({"original_pointer": f"/{SPLITS}/{i}/divergent_proposal_pairs/{j}/frame_evidence/{k}/bbox_{side}_xyxy_normalized",
                                     "encoded_pointer": f"/split_questions/{i}/proposal_pairs/{j}/frame_evidence/{k}/bbox_{side}"})
    return {"representation_version": FORMAT_VERSION, "roundtrip_valid": True,
            "original_sha256": content_sha256(original), "restored_sha256": content_sha256(restored),
            "encoded_sha256": content_sha256(encoded), "original_compact_bytes": len(canonical_bytes(original)),
            "encoded_compact_bytes": len(canonical_bytes(encoded)), "proposal_count": flat_index,
            "frame_row_count": row_count, "frame_run_count": run_count, "split_bbox_reference_count": ref_count,
            "pointer_maps": maps, "visual_truth_verified": False, "output_or_gate_modified": False}
