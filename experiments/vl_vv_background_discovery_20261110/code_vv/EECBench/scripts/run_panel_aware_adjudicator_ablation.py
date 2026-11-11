#!/usr/bin/env python3
"""Replay frozen detector ledgers with detector-panel-aware adjudication only."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
REPOSITORY_ROOT = PROJECT_ROOT.parent
sys.path.insert(0, str(SCRIPT_DIR))

import ensemble_shot_entity_detection as ensemble  # noqa: E402


DEFAULT_SOURCE_RUN = (
    PROJECT_ROOT
    / "experiments"
    / "study_inconsistent_2"
    / "prompt_unbound_prefilter"
    / "detector_adjudicator_only"
    / "run_20260906T172749Z"
)
DEFAULT_OUTPUT_PARENT = (
    PROJECT_ROOT
    / "experiments"
    / "study_inconsistent_2"
    / "prompt_unbound_prefilter"
    / "panel_aware_adjudicator_ablation"
)
SHOT_DIR_NAMES = (
    "inconsistent_study_shot1",
    "inconsitent_study_shot3",
)

PANEL_AWARE_OVERRIDE = """\
CONTROLLED PANEL-AWARE ABLATION OVERRIDE

This controlled ablation exposes proposal-source visibility and defines a
panel-aware granularity stability prior. It overrides the source-blind,
anonymize-source, and globally-shuffled-union clauses in the embedded Skill and
references. All other scope, visual-verification, low-trust-box,
physical-identity, graph-granularity, accounting, and single-shot rules remain
authoritative.

The input is organized as four fixed detector panels named detector_1 through
detector_4. These labels identify proposal provenance only. All four detectors
used the same ordered frames, prompt, complete-inventory method, and output
contract; no detector has a specialized role or preferred reliability rank.
Count support by distinct detector_id, never by the number of proposals a
detector emitted. Multiple member proposals from one detector jointly express
one split-partition position, not multiple votes. A detector that did not
propose this visual content supplies no negative vote. If one detector emitted
both the group and its members, treat that panel as internally conflicted
rather than counting it for both alternatives.

Use cross-panel agreement only as a stability prior when resolving incompatible
group-versus-member graph partitions over the same visual content. Compare the
partition independently proposed by each detector. If most panels represent
the content as one group while a minority panel splits it into members, prefer
the group unless the original frames provide strong shot-observed evidence that
the members are independently trackable or have distinct actions, states,
motion, trajectories, or interaction roles. Mere visible separation or distinct
physical boundaries is not sufficient to override the more stable group
partition. Never retain both a group and its members for the same content.

Panel agreement is not an entity-existence voting gate. A proposal found by
only one detector may still be accepted when the original frames clearly show
a graph-worthy, independently localizable physical entity. Conversely, repeated
proposals may be rejected when the pixels contradict them. The original frames
are always authoritative, and detector boxes remain approximate location
references. Judge only this shot; do not infer or use anything about another
shot or any expected cross-shot result.
"""


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _read_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ensemble.EnsembleError(f"Expected a JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact(path: Path) -> Dict[str, str]:
    return {"path": str(path.resolve()), "sha256": _sha256(path)}


def _build_panel_view(
    source_shot_dir: Path,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    ledgers = [
        _read_json(source_shot_dir / "detector_runs" / f"detector_{index}.json")
        for index in range(1, 5)
    ]
    anonymous_view = _read_json(
        source_shot_dir / "adjudication" / "anonymized_candidates.json"
    )
    source_map = _read_json(
        source_shot_dir / "adjudication" / "source_map.private.json"
    )

    proposals_by_id = {
        item["anonymous_proposal_id"]: item
        for item in anonymous_view["proposals"]
    }
    proposal_id_by_source = {
        (item["source"], item["local_id"]): item["anonymous_proposal_id"]
        for item in source_map["mappings"]
    }
    if len(proposals_by_id) != len(anonymous_view["proposals"]):
        raise ensemble.EnsembleError("Duplicate anonymous proposal IDs in source run")
    if len(proposal_id_by_source) != len(source_map["mappings"]):
        raise ensemble.EnsembleError("Duplicate detector/local IDs in source map")

    used_ids = set()
    panels = []
    for expected_index, ledger in enumerate(ledgers, start=1):
        detector_id = f"detector_{expected_index}"
        if ledger.get("detector_id") != detector_id:
            raise ensemble.EnsembleError(
                f"Frozen ledger order mismatch: expected {detector_id}"
            )
        panel_proposals = []
        for entity in ledger["entities"]:
            key = (detector_id, entity["local_id"])
            if key not in proposal_id_by_source:
                raise ensemble.EnsembleError(f"Missing source-map entry for {key}")
            proposal_id = proposal_id_by_source[key]
            if proposal_id not in proposals_by_id:
                raise ensemble.EnsembleError(
                    f"Missing anonymous proposal {proposal_id} for {key}"
                )
            panel_proposals.append(proposals_by_id[proposal_id])
            used_ids.add(proposal_id)
        panels.append(
            {
                "detector_id": detector_id,
                "proposals": panel_proposals,
            }
        )

    expected_ids = set(proposals_by_id)
    if used_ids != expected_ids:
        missing = sorted(expected_ids - used_ids)
        extra = sorted(used_ids - expected_ids)
        raise ensemble.EnsembleError(
            f"Panel regrouping changed proposal accounting: missing={missing}, extra={extra}"
        )

    panel_view = {
        "protocol_version": anonymous_view["protocol_version"],
        "shot_id": anonymous_view["shot_id"],
        "organization": "four homogeneous detector ledgers grouped by fixed detector_id",
        "detector_panels": panels,
        "box_redundancy_challenges": anonymous_view.get(
            "box_redundancy_challenges", []
        ),
    }
    return panel_view, ledgers, anonymous_view


def _build_prompt(
    *,
    shot_id: str,
    shot_manifest: Mapping[str, Any],
    panel_view: Mapping[str, Any],
    skill_text: str,
) -> str:
    attachment_paths = [
        str(Path(item["path"]).resolve())
        for item in shot_manifest["reference_frames"]
    ]
    base = ensemble._inventory_base_prompt(
        shot_id=shot_id,
        shot_manifest=shot_manifest,
        allowed_input_paths=attachment_paths,
        skill_text=skill_text,
    )
    prompt = ensemble._decision_prompt(
        base=base,
        shot_id=shot_id,
        anonymized_view=panel_view,
        valid_frame_ids=[
            int(item["frame_id"]) for item in shot_manifest["reference_frames"]
        ],
    )
    prompt = prompt.replace(
        "Review only the deterministically shuffled anonymous proposal union below.",
        "Review only the four detector-panel-organized proposal ledgers below.",
        1,
    )
    label = "anonymized_candidates:\n"
    if label not in prompt:
        raise ensemble.EnsembleError("Could not locate adjudicator input label")
    prefix, serialized_view = prompt.rsplit(label, 1)
    return (
        prefix
        + "\n"
        + PANEL_AWARE_OVERRIDE
        + "\npanel_aware_candidates:\n"
        + serialized_view
    )


def _attempt_usage(events_path: Path) -> Dict[str, Any] | None:
    if not events_path.is_file():
        return None
    return ensemble.shot_graph.parse_codex_token_usage(
        events_path.read_text(encoding="utf-8")
    )


def _run_one_shot(
    *,
    source_shot_dir: Path,
    output_shot_dir: Path,
    skill_text: str,
    skill_hashes: Mapping[str, str],
    codex_bin: str,
    model: str | None,
    timeout_sec: int,
) -> Dict[str, Any]:
    started = time.perf_counter()
    start_utc = _utc_now()
    shot_manifest_path = source_shot_dir / "input_bundle" / "shot_manifest.json"
    shot_manifest = _read_json(shot_manifest_path)
    shot_id = str(shot_manifest["shot_id"])
    panel_view, ledgers, anonymous_view = _build_panel_view(source_shot_dir)
    frame_ids = [
        int(item["frame_id"]) for item in shot_manifest["reference_frames"]
    ]
    attachments = [
        Path(item["path"]).resolve()
        for item in shot_manifest["reference_frames"]
    ]
    allowed_paths = [str(path) for path in attachments]

    for index, ledger in enumerate(ledgers, start=1):
        ensemble.validate_ledger(
            ledger,
            shot_id=shot_id,
            detector_id=f"detector_{index}",
            source_kind="detector",
            valid_frame_ids=frame_ids,
            allowed_input_paths=allowed_paths,
        )

    adjudication_dir = output_shot_dir / "adjudication"
    attempts_dir = output_shot_dir / "codex_attempts"
    prompts_dir = output_shot_dir / "prompts"
    adjudication_dir.mkdir(parents=True, exist_ok=False)
    attempts_dir.mkdir(parents=True, exist_ok=False)
    prompts_dir.mkdir(parents=True, exist_ok=False)

    panel_view_path = adjudication_dir / "panel_aware_candidates.json"
    ensemble._atomic_write_json(panel_view_path, panel_view)
    prompt = _build_prompt(
        shot_id=shot_id,
        shot_manifest=shot_manifest,
        panel_view=panel_view,
        skill_text=skill_text,
    )
    prompt_path = prompts_dir / "adjudicator_initial.txt"
    ensemble._atomic_write_text(prompt_path, prompt)

    frozen_inputs = {
        "shot_manifest": _artifact(shot_manifest_path),
        "frames": [_artifact(path) for path in attachments],
        "detector_ledgers": [
            _artifact(source_shot_dir / "detector_runs" / f"detector_{index}.json")
            for index in range(1, 5)
        ],
        "source_anonymized_candidates": _artifact(
            source_shot_dir / "adjudication" / "anonymized_candidates.json"
        ),
        "source_adjudication": _artifact(
            source_shot_dir / "adjudication" / "adjudicator_initial.json"
        ),
        "proposal_ids_preserved": True,
        "proposal_count": len(anonymous_view["proposals"]),
    }
    ensemble._atomic_write_json(output_shot_dir / "frozen_inputs.json", frozen_inputs)

    print(
        f"[panel-ablation] {shot_id}: starting adjudicator "
        f"({len(anonymous_view['proposals'])} frozen proposals)",
        flush=True,
    )
    attempts: List[Dict[str, Any]] = []
    decisions: Dict[str, Any] | None = None
    successful_invocation: ensemble.CodexInvocation | None = None
    for attempt in range(1, 3):
        output_path = attempts_dir / f"adjudicator_initial.attempt{attempt}.json"
        events_path = attempts_dir / f"adjudicator_initial.attempt{attempt}.events.jsonl"
        stderr_path = attempts_dir / f"adjudicator_initial.attempt{attempt}.stderr.log"
        attempt_started = time.perf_counter()
        invocation: ensemble.CodexInvocation | None = None
        error = None
        try:
            invocation = ensemble.run_codex_json(
                prompt=prompt,
                attachments=attachments,
                schema_path=ensemble.ADJUDICATION_SCHEMA,
                output_path=output_path,
                events_path=events_path,
                stderr_path=stderr_path,
                codex_bin=codex_bin,
                model=model,
                timeout_sec=timeout_sec,
                work_dir=ensemble.PROJECT_ROOT,
                persistent=False,
                verbose=False,
            )
            ensemble.validate_decisions(
                invocation.payload,
                shot_id=shot_id,
                anonymous_ids=sorted(
                    item["anonymous_proposal_id"]
                    for item in anonymous_view["proposals"]
                ),
                valid_frame_ids=frame_ids,
            )
            decisions = invocation.payload
            successful_invocation = invocation
        except Exception as exc:  # bounded identical-input retry is intentional
            error = str(exc)
        usage = (
            invocation.token_usage
            if invocation is not None
            else _attempt_usage(events_path)
        )
        attempts.append(
            {
                "attempt": attempt,
                "status": "success" if decisions is not None else "failed",
                "error": error,
                "runtime_seconds": round(time.perf_counter() - attempt_started, 6),
                "token_usage": usage,
                "thread_id": invocation.thread_id if invocation is not None else None,
            }
        )
        if decisions is not None:
            break
        if attempt == 1:
            print(
                f"[panel-ablation] {shot_id}: first attempt failed; retrying once",
                flush=True,
            )

    if decisions is None or successful_invocation is None:
        raise ensemble.EnsembleError(
            f"{shot_id}: panel-aware adjudicator failed after two attempts: "
            f"{attempts[-1]['error']}"
        )

    decision_path = adjudication_dir / "adjudicator_initial.json"
    ensemble._atomic_write_json(decision_path, decisions)
    decision_counts = {
        decision: sum(
            cluster["decision"] == decision for cluster in decisions["clusters"]
        )
        for decision in ("accept", "reject", "abstain")
    }
    manifest = {
        "protocol_version": ensemble.PROTOCOL_VERSION,
        "mode": "panel_aware_initial_adjudicator_ablation",
        "status": "success",
        "start_utc": start_utc,
        "end_utc": _utc_now(),
        "shot_id": shot_id,
        "source_shot_run": str(source_shot_dir.resolve()),
        "ablation_variable": (
            "preserve fixed detector_1..detector_4 provenance and ledger grouping "
            "plus an explicit panel-aware granularity stability prior"
        ),
        "detector_conditions": "four frozen homogeneous detector ledgers",
        "panel_order": [f"detector_{index}" for index in range(1, 5)],
        "within_panel_order": "original immutable detector ledger order",
        "entity_existence_majority_gate": False,
        "panel_agreement_use": "granularity stability prior only",
        "cross_shot_input": False,
        "excluded_stages": [
            "detectors",
            "targeted_verifiers",
            "adjudicator_revision",
            "prompt_bound_matcher",
            "grounding",
            "relations",
            "cross_shot_reconciliation",
        ],
        "proposal_count": len(anonymous_view["proposals"]),
        "box_challenge_count": len(
            panel_view.get("box_redundancy_challenges", [])
        ),
        "adjudicator_cluster_count": len(decisions["clusters"]),
        "adjudicator_decision_counts": decision_counts,
        "attempts": attempts,
        "token_usage": ensemble._aggregate_usage(
            [attempt_record["token_usage"] for attempt_record in attempts]
        ),
        "runtime_seconds": round(time.perf_counter() - started, 6),
        "skill_hashes": dict(skill_hashes),
        "artifacts": {
            "panel_aware_candidates": _artifact(panel_view_path),
            "prompt": _artifact(prompt_path),
            "adjudicator_initial": _artifact(decision_path),
        },
    }
    ensemble._atomic_write_json(output_shot_dir / "run_manifest.json", manifest)
    print(
        f"[panel-ablation] {shot_id}: complete in "
        f"{manifest['runtime_seconds']:.1f}s; decisions={decision_counts}; "
        f"tokens={manifest['token_usage'].get('total_tokens')}",
        flush=True,
    )
    return manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, default=DEFAULT_SOURCE_RUN)
    parser.add_argument("--output-parent", type=Path, default=DEFAULT_OUTPUT_PARENT)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-sec", type=int, default=1800)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    source_run = args.source_run.resolve()
    missing = [
        name for name in SHOT_DIR_NAMES if not (source_run / name).is_dir()
    ]
    if missing:
        raise ensemble.EnsembleError(
            f"Source run is missing required frozen shots: {missing}"
        )

    run_dir = (args.output_parent.resolve() / f"run_{_utc_stamp()}")
    run_dir.mkdir(parents=True, exist_ok=False)
    skill_text, skill_hashes = ensemble._load_skill(ensemble.DEFAULT_SKILL_DIR)
    started = time.perf_counter()
    start_utc = _utc_now()
    print(f"[panel-ablation] output: {run_dir}", flush=True)

    manifests: List[Dict[str, Any]] = []
    errors: List[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(
                _run_one_shot,
                source_shot_dir=source_run / shot_name,
                output_shot_dir=run_dir / shot_name,
                skill_text=skill_text,
                skill_hashes=skill_hashes,
                codex_bin=args.codex_bin,
                model=args.model,
                timeout_sec=args.timeout_sec,
            ): shot_name
            for shot_name in SHOT_DIR_NAMES
        }
        for future in concurrent.futures.as_completed(futures):
            shot_name = futures[future]
            try:
                manifests.append(future.result())
            except Exception as exc:
                errors.append(f"{shot_name}: {exc}")
                print(f"[panel-ablation] {shot_name}: FAILED: {exc}", flush=True)

    manifests.sort(key=lambda item: item["shot_id"])
    all_usages = [
        attempt["token_usage"]
        for manifest in manifests
        for attempt in manifest["attempts"]
    ]
    top_manifest = {
        "protocol_version": ensemble.PROTOCOL_VERSION,
        "mode": "panel_aware_initial_adjudicator_ablation",
        "status": "success" if not errors and len(manifests) == 2 else "failed",
        "start_utc": start_utc,
        "end_utc": _utc_now(),
        "source_run": str(source_run),
        "run_dir": str(run_dir),
        "ablation_variable": (
            "detector provenance and per-detector ledger grouping plus an explicit "
            "panel-aware granularity stability prior"
        ),
        "fixed_detector_ids_exposed": [
            f"detector_{index}" for index in range(1, 5)
        ],
        "cross_shot_input": False,
        "parallel_shot_calls": True,
        "shots": manifests,
        "errors": errors,
        "token_usage": ensemble._aggregate_usage(all_usages),
        "runtime_seconds": round(time.perf_counter() - started, 6),
        "skill_hashes": dict(skill_hashes),
    }
    ensemble._atomic_write_json(run_dir / "run_manifest.json", top_manifest)
    print(
        f"[panel-ablation] finished status={top_manifest['status']} "
        f"runtime={top_manifest['runtime_seconds']:.1f}s "
        f"tokens={top_manifest['token_usage'].get('total_tokens')}",
        flush=True,
    )
    print(f"[panel-ablation] run_dir={run_dir}", flush=True)
    return 0 if top_manifest["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
