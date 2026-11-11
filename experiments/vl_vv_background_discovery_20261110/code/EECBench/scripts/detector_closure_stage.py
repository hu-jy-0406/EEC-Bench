"""Registry-blind own-source append-only residual discovery rounds.

Rounds from one source are dependent searches, never additional votes. A zero
addition round is a search stop condition, not proof of visual completeness.
"""
from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

STAGE_VERSION = "single_shot_own_source_residual_closure_v0.2"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "codex_detector_closure_delta_v0.2.schema.json"
SPATIAL_CELLS = (
    "upper_left", "upper_center", "upper_right", "middle_left", "middle_center",
    "middle_right", "lower_left", "lower_center", "lower_right",
)
EDGES = ("top", "right", "bottom", "left")


def specialize_schema(*, ledger, shot_id, round_index, valid_frame_ids, allowed_input_paths):
    """Freeze known identifiers in the model schema before visual inference."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    fixed = {"stage_version": STAGE_VERSION, "shot_id": shot_id,
             "detector_id": ledger["detector_id"], "round_index": round_index}
    for key, value in fixed.items():
        schema["properties"][key]["enum"] = [value]
    frames = list(valid_frame_ids)
    existing = sorted(e["local_id"] for e in ledger["entities"])

    def restrict_array(field, values):
        field["items"] = {"type": "string"}
        if values:
            field["items"]["enum"] = values
        else:
            field["maxItems"] = 0

    restrict_array(schema["properties"]["accessed_input_paths"],
                   list(dict.fromkeys(map(str, allowed_input_paths))))
    defs = schema["$defs"]
    restrict_array(defs["closureFrameCell"]["properties"]["existing_local_ids"], existing)
    restrict_array(defs["closureNovelty"]["properties"]["nearby_existing_local_ids"], existing)
    defs["frameIds"]["items"] = {"type": "integer", "enum": frames}
    defs["closureAudit"]["properties"]["reviewed_frame_ids"]["items"] = {"type": "integer", "enum": frames}

    def visit(node):
        if isinstance(node, dict):
            for key, value in node.get("properties", {}).items():
                if key in {"frame_id", "best_frame_id", "earlier_frame_id", "later_frame_id"}:
                    value["enum"] = frames
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(schema)
    cells = defs["closureAudit"]["properties"]["frame_cell_checks"]
    cells["minItems"] = cells["maxItems"] = 9 * len(frames)
    temporal = defs["closureAudit"]["properties"]["temporal_checks"]
    temporal["minItems"] = temporal["maxItems"] = max(0, len(frames) - 1)
    return schema


class ClosureValidationError(ValueError):
    """Invalid delta or mandatory coverage accounting."""


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _fields(value: Any, names: Sequence[str], owner: str) -> None:
    if not isinstance(value, dict) or set(value) != set(names):
        raise ClosureValidationError(f"{owner}: expected exactly {list(names)}")


def _text(value: Any, owner: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ClosureValidationError(f"{owner}: expected nonempty text")


def _ids(value: Any, allowed: set[str], owner: str) -> set[str]:
    if (not isinstance(value, list) or any(not isinstance(item, str) for item in value)
            or len(value) != len(set(value)) or not set(value) <= allowed):
        raise ClosureValidationError(f"{owner}: invalid, duplicate, or foreign IDs")
    return set(value)


def build_prompt(*, ledger: Mapping[str, Any], shot_id: str, round_index: int,
                 valid_frame_ids: Sequence[int], allowed_input_paths: Sequence[str],
                 detector_policy_text: str, shot_manifest: Mapping[str, Any]) -> str:
    del shot_manifest
    mapping = [{"attachment_index": i + 1, "frame_id": frame, "path": str(path)}
               for i, (frame, path) in enumerate(zip(valid_frame_ids, allowed_input_paths))]
    own_view = {"detector_id": ledger["detector_id"], "entities": copy.deepcopy(ledger["entities"])}
    return (
        "You are the residual-discovery continuation of exactly one detector source. "
        "Inspect only this shot's original attached frames and your own frozen candidate "
        "ledger below. Do not use tools, agents, the workspace, a prompt-bound registry, "
        "other detector outputs, other shots, expected differences, or downstream decisions. "
        "This is discovery, not an endorsement or extra vote for existing candidates.\n\n"
        "Apply the complete detector-only entity-scope and precision policy:\n"
        + detector_policy_text + "\n\nExternal residual-round requirements:\n"
        "1. Reinspect every supplied frame and all nine image-plane cells in each frame, "
        "in chronological and row-major order. Never substitute one best frame. Each "
        "frame_cell_checks entry records existing IDs actually noticed there, any new IDs, "
        "and a concise pixel-based scan note. No entity is required in an empty cell.\n"
        "2. Explicitly inspect all four edges in the first frame and in the last frame. "
        "Compare every adjacent frame pair in both directions: account for newly exposed "
        "physical content AND content that disappears through cropping, occlusion, or "
        "reframing. Content visible only initially must not be missed because later frames "
        "are clearer elsewhere.\n"
        "3. Re-localize candidate boundaries from original pixels. Inspect interiors and "
        "neighboring perimeters for physically distinct omitted content. Existing boxes "
        "are low-trust hints, never exclusion masks. A large host's box does not make its "
        "entire interior or perimeter already represented.\n"
        "4. Return additions only: never copy, edit, delete, rename, split, merge, or re-emit "
        "a supplied candidate. Every new local_id must be unused in the supplied ledger. "
        "Do not add an alias, alternate label, broader scope, or finer subdivision of "
        "represented content. Every addition needs one novelty_check citing its own "
        "visible boundary in original frames and explaining physical separation from "
        "nearby existing candidates. Wording, color, category, or imagined function alone "
        "cannot establish novelty or physical existence.\n"
        "5. Retain the entity-scope and precision rules. Never infer hidden objects or "
        "promote a shadow, reflection, texture, color patch, or unresolved region. If no "
        "eligible content remains, additions and novelty_checks must both be empty. Never "
        "invent additions to continue the loop. Existing errors remain for adjudication; "
        "this append-only role cannot fix them by retargeting.\n"
        "6. Each addition uses the complete detector proposal schema and exhaustive "
        "per-frame presence, with tight full-frame boxes only where visible. Coverage "
        "accounting is private bookkeeping, never visual evidence or an extra vote.\n"
        "7. accessed_input_paths contains only exact absolute path strings from "
        "ordered_frame_mapping. Inline ledger text and attachment/frame labels are not "
        "filesystem paths and must never appear there. Existing-ID fields use only IDs "
        "in the supplied ledger at round start; this round's additions belong only in "
        "new-ID fields in every frame. Do not change uncertain presence to visible to "
        "satisfy a coverage cross-index. Physical existence and novelty are separately "
        "validated against the authoritative candidate ledger.\n\n"
        f"stage_version: {STAGE_VERSION}\nshot_id: {shot_id}\n"
        f"detector_id: {ledger['detector_id']}\nround_index: {round_index}\n"
        "ordered_frame_mapping:\n" + json.dumps(mapping, ensure_ascii=False)
        + "\ncell_order:\n" + json.dumps(SPATIAL_CELLS)
        + "\nedge_order:\n" + json.dumps(EDGES)
        + "\nown_frozen_candidate_ledger:\n" + json.dumps(own_view, ensure_ascii=False)
        + "\nReturn only the strict closure-delta JSON."
    )


def validate_delta(delta: Mapping[str, Any], *, ledger: Mapping[str, Any], shot_id: str,
                   round_index: int, valid_frame_ids: Sequence[int],
                   allowed_input_paths: Sequence[str], validate_ledger: Callable[..., Any],
                   diagnostics: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    _fields(delta, ("stage_version", "shot_id", "detector_id", "round_index",
                   "accessed_input_paths", "additions", "novelty_checks", "coverage_audit", "warnings"), "delta")
    expected = {"stage_version": STAGE_VERSION, "shot_id": shot_id,
                "detector_id": ledger["detector_id"], "round_index": round_index}
    for field, value in expected.items():
        if delta[field] != value or (field == "round_index" and isinstance(delta[field], bool)):
            raise ClosureValidationError(f"delta: wrong {field}")
    _ids(delta["accessed_input_paths"], set(allowed_input_paths), "accessed paths")
    if not isinstance(delta["warnings"], list) or any(not isinstance(item, str) for item in delta["warnings"]):
        raise ClosureValidationError("warnings must be a string list")
    additions = delta["additions"]
    if not isinstance(additions, list):
        raise ClosureValidationError("additions must be a list")
    existing_ids = {entity["local_id"] for entity in ledger["entities"]}
    added_ids: set[str] = set()
    for entity in additions:
        if not isinstance(entity, Mapping):
            raise ClosureValidationError("addition must be an entity object")
        local_id = entity.get("local_id")
        _text(local_id, "addition local_id")
        if local_id in existing_ids or local_id in added_ids:
            raise ClosureValidationError("addition reuses an existing or duplicate local_id")
        added_ids.add(local_id)
    combined = copy.deepcopy(dict(ledger))
    combined["entities"].extend(copy.deepcopy(additions))
    combined["accessed_input_paths"] = list(dict.fromkeys([*combined["accessed_input_paths"], *delta["accessed_input_paths"]]))
    combined["warnings"] = list(dict.fromkeys([*combined["warnings"], *delta["warnings"]]))
    validate_ledger(combined, shot_id=shot_id, detector_id=ledger["detector_id"],
                    source_kind="detector", valid_frame_ids=valid_frame_ids,
                    allowed_input_paths=allowed_input_paths)
    novelty = delta["novelty_checks"]
    if not isinstance(novelty, list):
        raise ClosureValidationError("novelty_checks must be a list")
    seen_novelty = []
    by_id = {entity["local_id"]: entity for entity in additions}
    for record in novelty:
        _fields(record, ("local_id", "nearby_existing_local_ids", "boundary_evidence", "separation_reason"), "novelty check")
        local_id = record["local_id"]
        if local_id not in added_ids:
            raise ClosureValidationError("novelty check must refer to an addition")
        seen_novelty.append(local_id)
        _ids(record["nearby_existing_local_ids"], existing_ids, "nearby existing IDs")
        _text(record["separation_reason"], "separation reason")
        evidence = record["boundary_evidence"]
        if not isinstance(evidence, list) or not evidence:
            raise ClosureValidationError("novelty boundary evidence must be nonempty")
        visible = {item["frame_id"] for item in by_id[local_id]["frame_presence"] if item["status"] == "visible"}
        seen_frames = []
        for item in evidence:
            _fields(item, ("frame_id", "description"), "boundary evidence")
            if item["frame_id"] not in visible:
                raise ClosureValidationError("novelty evidence must cite visible frames")
            _text(item["description"], "boundary description")
            seen_frames.append(item["frame_id"])
        if len(seen_frames) != len(set(seen_frames)):
            raise ClosureValidationError("duplicate boundary evidence frame")
    if len(seen_novelty) != len(added_ids) or set(seen_novelty) != added_ids:
        raise ClosureValidationError("every addition needs exactly one novelty check")
    audit = delta["coverage_audit"]
    _fields(audit, ("reviewed_frame_ids", "frame_cell_checks", "endpoint_checks", "temporal_checks"), "coverage audit")
    if audit["reviewed_frame_ids"] != list(valid_frame_ids):
        raise ClosureValidationError("reviewed frames must exactly match input order")
    cells = audit["frame_cell_checks"]
    if not isinstance(cells, list):
        raise ClosureValidationError("frame_cell_checks must be a list")
    actual_cells = []
    indexed: set[str] = set()
    for record in cells:
        _fields(record, ("frame_id", "cell", "existing_local_ids", "new_local_ids", "note"), "frame cell")
        actual_cells.append((record["frame_id"], record["cell"]))
        _ids(record["existing_local_ids"], existing_ids, "frame cell existing IDs")
        new_ids = _ids(record["new_local_ids"], added_ids, "frame cell new IDs")
        indexed.update(new_ids)
        for local_id in new_ids:
            if not any(item["frame_id"] == record["frame_id"] and item["status"] == "visible"
                       for item in by_id[local_id]["frame_presence"]) and diagnostics is not None:
                diagnostics.append({
                    "kind": "nonvisible_addition_in_cell_cross_index",
                    "frame_id": record["frame_id"], "cell": record["cell"],
                    "local_id": local_id,
                    "effect": "diagnostic_only_no_candidate_mutation_no_retry",
                })
        _text(record["note"], "frame cell note")
    if actual_cells != [(frame, cell) for frame in valid_frame_ids for cell in SPATIAL_CELLS]:
        raise ClosureValidationError("frame-cell audit must cover all frames times nine cells in order")
    if indexed != added_ids:
        raise ClosureValidationError("every addition must be indexed in a reviewed frame-cell")
    endpoints = audit["endpoint_checks"]
    if not isinstance(endpoints, list):
        raise ClosureValidationError("endpoint_checks must be a list")
    actual_endpoints = []
    for record in endpoints:
        _fields(record, ("endpoint", "frame_id", "reviewed_edges", "new_local_ids", "note"), "endpoint check")
        actual_endpoints.append((record["endpoint"], record["frame_id"]))
        if record["reviewed_edges"] != list(EDGES):
            raise ClosureValidationError("endpoint review must cover all four edges in order")
        _ids(record["new_local_ids"], added_ids, "endpoint new IDs")
        _text(record["note"], "endpoint note")
    if actual_endpoints != [("first_frame", valid_frame_ids[0]), ("last_frame", valid_frame_ids[-1])]:
        raise ClosureValidationError("first and last frame reviews are mandatory")
    temporal = audit["temporal_checks"]
    if not isinstance(temporal, list):
        raise ClosureValidationError("temporal_checks must be a list")
    actual_pairs = []
    for record in temporal:
        _fields(record, ("earlier_frame_id", "later_frame_id", "revealed_new_local_ids", "disappearing_new_local_ids", "note"), "temporal check")
        actual_pairs.append((record["earlier_frame_id"], record["later_frame_id"]))
        _ids(record["revealed_new_local_ids"], added_ids, "revealed new IDs")
        _ids(record["disappearing_new_local_ids"], added_ids, "disappearing new IDs")
        _text(record["note"], "temporal note")
    if actual_pairs != list(zip(valid_frame_ids, valid_frame_ids[1:])):
        raise ClosureValidationError("temporal audit must cover every adjacent pair in order")
    return combined


def run_stage(*, ledgers: Sequence[Mapping[str, Any]], shot_id: str,
              valid_frame_ids: Sequence[int], allowed_input_paths: Sequence[str],
              attachments: Sequence[Path], detector_policy_text: str,
              shot_manifest: Mapping[str, Any], run_dir: Path, max_rounds: int,
              max_workers: int, invoke_json: Callable[..., Any],
              validate_ledger: Callable[..., Any], invocation_kwargs: Mapping[str, Any],
              account_attempt: Callable[..., Mapping[str, Any]] | None = None,
              request_context_factory: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Return valid bounded-search ledgers; incomplete sources remain a hard failure."""
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or not 0 <= max_rounds <= 4:
        raise ValueError("max_rounds must be an integer between zero and four")
    if not valid_frame_ids or len(set(valid_frame_ids)) != len(valid_frame_ids):
        raise ValueError("valid_frame_ids must be nonempty and unique")
    if len(attachments) != len(valid_frame_ids) or len(allowed_input_paths) != len(valid_frame_ids):
        raise ValueError("one original allowed attachment is required per frame")
    source_ids = [ledger["detector_id"] for ledger in ledgers]
    if not source_ids or len(source_ids) != len(set(source_ids)):
        raise ValueError("source IDs must be nonempty and unique")
    if any(not isinstance(s, str) or not s.replace("_", "").isalnum() for s in source_ids):
        raise ValueError("invalid source detector ID")
    if max_workers < 1:
        raise ValueError("max_workers must be positive")
    reserved = {"prompt", "attachments", "schema_path", "output_path", "events_path",
                "stderr_path", "work_dir", "persistent", "resume_thread_id"}
    if reserved.intersection(invocation_kwargs):
        raise ValueError("invocation_kwargs cannot override isolation or artifact paths")
    stage_dir = Path(run_dir) / "detector_closure"
    stage_dir.mkdir(parents=True, exist_ok=False)

    def run_source(original):
        detector_id = original["detector_id"]
        source_dir = stage_dir / detector_id
        source_dir.mkdir()
        ledger = copy.deepcopy(dict(original))
        _write_json(source_dir / "original_ledger.json", ledger)
        audit = {"detector_id": detector_id, "status": "disabled" if max_rounds == 0 else "complete",
                 "original_ledger_sha256": _digest(original), "rounds": [], "converged": False,
                 "stop_reason": "disabled" if max_rounds == 0 else "max_rounds_with_additions",
                 "attempts": [], "invocations": 0, "token_usages": []}
        for round_index in range(1, max_rounds + 1):
            round_dir = source_dir / f"round_{round_index:02d}"
            round_dir.mkdir()
            _write_json(round_dir / "input_ledger.json", ledger)
            prompt = build_prompt(ledger=ledger, shot_id=shot_id, round_index=round_index,
                                  valid_frame_ids=valid_frame_ids, allowed_input_paths=allowed_input_paths,
                                  detector_policy_text=detector_policy_text, shot_manifest=shot_manifest)
            (round_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
            round_audit = {"round_index": round_index, "input_ledger_sha256": _digest(ledger),
                           "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                           "status": "incomplete", "added_local_ids": []}
            schema_path = round_dir / "output.schema.json"
            _write_json(schema_path, specialize_schema(
                ledger=ledger, shot_id=shot_id, round_index=round_index,
                valid_frame_ids=valid_frame_ids, allowed_input_paths=allowed_input_paths,
            ))
            round_audit["output_schema_sha256"] = hashlib.sha256(schema_path.read_bytes()).hexdigest()
            combined = None
            for attempt in (1, 2):
                routing_kwargs = ({"request_context": request_context_factory(
                    detector_id, round_index, attempt,
                )} if request_context_factory is not None else {})
                output_path = round_dir / f"attempt{attempt}.json"
                events_path = round_dir / f"attempt{attempt}.events.jsonl"
                work_dir = round_dir / f"attempt{attempt}_workdir"
                work_dir.mkdir()
                invocation = None
                error = None
                attempt_diagnostics = []
                audit["invocations"] += 1
                try:
                    invocation = invoke_json(prompt=prompt, attachments=attachments,
                                             schema_path=schema_path, output_path=output_path,
                                             events_path=events_path,
                                             stderr_path=round_dir / f"attempt{attempt}.stderr.log",
                                             work_dir=work_dir, **dict(invocation_kwargs), **routing_kwargs)
                    combined = validate_delta(invocation.payload, ledger=ledger, shot_id=shot_id,
                                              round_index=round_index, valid_frame_ids=valid_frame_ids,
                                              allowed_input_paths=allowed_input_paths,
                                              validate_ledger=validate_ledger,
                                              diagnostics=attempt_diagnostics)
                except Exception as exc:
                    error = exc
                if account_attempt is not None:
                    accounting = dict(account_attempt(invocation=invocation, error=error,
                                                      events_path=events_path, **routing_kwargs))
                else:
                    accounting = {"subprocess_started": True,
                                  "token_usage": getattr(invocation or error, "token_usage", None)}
                record = {**accounting, "detector_id": detector_id, "round_index": round_index,
                          "attempt": attempt, "status": "success" if error is None else "failed",
                          "error": str(error) if error is not None else None}
                audit["attempts"].append(record)
                if (accounting.get("subprocess_started", True)
                        or accounting.get("subprocess_start_unknown")):
                    audit["token_usages"].append(accounting.get("token_usage"))
                _write_json(round_dir / f"attempt{attempt}.audit.json", record)
                if error is None:
                    _write_json(round_dir / "delta.json", invocation.payload)
                    round_audit.update(status="complete", successful_attempt=attempt,
                                       cross_index_diagnostics=attempt_diagnostics,
                                       added_local_ids=[e["local_id"] for e in invocation.payload["additions"]],
                                       output_ledger_sha256=_digest(combined))
                    break
            audit["rounds"].append(round_audit)
            _write_json(round_dir / "round_audit.json", round_audit)
            if round_audit["status"] != "complete":
                audit.update(status="incomplete", stop_reason="failed_after_identical_retry")
                break
            ledger = combined
            _write_json(round_dir / "extended_ledger.json", ledger)
            if not round_audit["added_local_ids"]:
                audit.update(converged=True, stop_reason="zero_additions")
                break
        _write_json(source_dir / "extended_ledger.json", ledger)
        audit["extended_ledger_sha256"] = _digest(ledger)
        audit["added_entity_count"] = len(ledger["entities"]) - len(original["entities"])
        _write_json(source_dir / "source_audit.json", audit)
        return {"ledger": ledger, "audit": audit}

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(ledgers))) as executor:
        results = list(executor.map(run_source, ledgers))
    audits = [item["audit"] for item in results]
    result = {
        "stage_version": STAGE_VERSION,
        "status": "disabled" if max_rounds == 0 else (
            "complete" if all(a["status"] == "complete" for a in audits) else "incomplete"),
        "ledgers": [item["ledger"] for item in results], "source_audits": audits,
        "attempts": [attempt for audit in audits for attempt in audit["attempts"]],
        "invocations": sum(audit["invocations"] for audit in audits),
        "token_usages": [usage for audit in audits for usage in audit["token_usages"]],
        "converged": max_rounds > 0 and all(a["converged"] for a in audits),
        "budget_exhausted_sources": [a["detector_id"] for a in audits
                                     if a["stop_reason"] == "max_rounds_with_additions"],
        "stop_policy": "bounded_search_then_adjudicate_valid_source_union",
        "max_rounds": max_rounds, "source_count_before": len(ledgers), "source_count_after": len(ledgers),
        "additional_rounds_are_independent_votes": False,
        "closure_meaning": "converged=true means all sources completed a zero-addition external scan; not proof of visual completeness",
        "audit_path": str((stage_dir / "stage_audit.json").resolve()),
    }
    _write_json(stage_dir / "stage_audit.json", {k: v for k, v in result.items() if k != "ledgers"})
    return result
