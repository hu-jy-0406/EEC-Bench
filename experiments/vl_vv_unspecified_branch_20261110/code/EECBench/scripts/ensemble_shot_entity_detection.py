#!/usr/bin/env python3
"""Deterministic orchestration for the single-shot entity ensemble skill."""

from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import json
import math
import random
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import extract_shot_entity_graph as shot_graph
import accepted_compact_assembly_stage as accepted_assembly_stage
import granularity_family_stage as family_stage
import detector_closure_stage as detector_closure_stage
import role_model_routing as model_routing_stage


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
REPOSITORY_ROOT = PROJECT_ROOT.parent
DEFAULT_SKILL_DIR = (
    REPOSITORY_ROOT / ".agents" / "skills" / "ensemble-shot-entity-detection"
)
DETECTOR_SCHEMA = (
    PROJECT_ROOT / "schemas" / "codex_entity_detector_ledger_v0.8.schema.json"
)
ADJUDICATION_SCHEMA = (
    PROJECT_ROOT / "schemas" / "codex_entity_adjudication_v0.5.schema.json"
)
VERIFICATION_SCHEMA = (
    PROJECT_ROOT / "schemas" / "codex_entity_verification_v0.5.schema.json"
)
MATCHING_SCHEMA = (
    PROJECT_ROOT / "schemas" / "codex_prompt_bound_matching_v0.5.schema.json"
)
GRANULARITY_FAMILY_SCHEMA = (
    PROJECT_ROOT / "schemas" / "codex_granularity_family_plan_v0.3.schema.json"
)
ACCEPTED_ASSEMBLY_SCHEMA = (
    PROJECT_ROOT
    / "schemas"
    / "codex_accepted_compact_assembly_plan_v0.5.schema.json"
)
PROTOCOL_VERSION = "single_shot_inventory_first_boxed_granularity_v0.5"
DETECTOR_POLICY_VERSION = "single_shot_detector_three_pass_coverage_v0.4"
DETECTOR_POLICY_RELATIVE_PATH = Path("references") / "detector-protocol.md"
DETECTOR_SPATIAL_CELLS: Tuple[str, ...] = (
    "upper_left",
    "upper_center",
    "upper_right",
    "middle_left",
    "middle_center",
    "middle_right",
    "lower_left",
    "lower_center",
    "lower_right",
)
DETECTOR_CONTENT_STRATA: Tuple[str, ...] = (
    "actors_and_independently_handled_objects",
    "freestanding_and_supported_objects",
    "containers_open_storage_and_bounded_collections",
    "fixed_architectural_and_mounted_objects",
    "peripheral_cropped_and_exterior_bounded_objects",
)
HOMOGENEOUS_SCAN_VARIANT = "homogeneous_complete_inventory"
HOMOGENEOUS_SCAN_INSTRUCTION = (
    "Apply the detector-only three-pass inventory procedure exactly as written. "
    "Do not adopt a specialized region, temporal direction, entity category, or "
    "attention priority."
)
DETECTOR_ROLES: Tuple[Tuple[str, str, str], ...] = (
    *tuple(
        (f"detector_{index}", HOMOGENEOUS_SCAN_VARIANT, HOMOGENEOUS_SCAN_INSTRUCTION)
        for index in range(1, 5)
    ),
)
VERIFIER_IDS: Tuple[str, str] = ("verifier_1", "verifier_2")
INITIAL_DECLARED_IDENTITY_HANDOFF_VERSION = "initial_declared_identity_handoff_v0.1"
SCOPE_RETENTION_POLICY = "single_survivor_scope_retention_v0.1"
SCOPE_RETENTION_REFERENCE = Path("references/scope-retention-protocol.md")
TOKEN_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")
IDENTITY_LOCATOR_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "center",
    "centre",
    "edge",
    "front",
    "group",
    "in",
    "item",
    "left",
    "lower",
    "middle",
    "near",
    "of",
    "on",
    "or",
    "object",
    "part",
    "possible",
    "portion",
    "rear",
    "right",
    "same",
    "set",
    "side",
    "collection",
    "the",
    "thing",
    "to",
    "upper",
    "visible",
    "with",
}
IDENTITY_TOKEN_ALIASES = {"desktop": "desk", "centre": "center"}
IDENTITY_LOCATOR_JACCARD_THRESHOLD = 0.20
BOX_REDUNDANCY_IOU_THRESHOLD = 0.70
BOX_REDUNDANCY_MIN_VISIBLE_FRAMES = 3
BOX_REDUNDANCY_COVERAGE_THRESHOLD = 0.80
INTRA_CLUSTER_DIVERGENCE_MAX_IOU = 0.10
INTRA_CLUSTER_DIVERGENCE_MAX_SMALLER_BOX_COVERAGE = 0.25
INTRA_CLUSTER_DIVERGENCE_MIN_COVISIBLE_FRAMES = 3
INTRA_CLUSTER_DIVERGENCE_COVERAGE_THRESHOLD = 0.80
NONMAJORITY_GENERIC_IDENTITY_GATE_VERSION = (
    "nonmajority_generic_identity_gate_v0.1"
)
ALL_SUPPORT_GENERIC_IDENTITY_GATE_VERSION = "all_support_generic_identity_gate_v0.1"
GENERIC_IDENTITY_PLACEHOLDER_HEADS = frozenset(
    {
        "article",
        "detail",
        "entity",
        "feature",
        "form",
        "item",
        "object",
        "patch",
        "region",
        "shape",
        "thing",
        "volume",
    }
)
GENERIC_IDENTITY_RELATIONAL_SUFFIXES = frozenset(
    {
        "above",
        "at",
        "behind",
        "below",
        "beside",
        "between",
        "by",
        "from",
        "in",
        "near",
        "on",
        "over",
        "under",
        "with",
    }
)
IDENTITY_UNCERTAINTY_SUBJECTS = frozenset(
    {"category", "class", "identity", "kind", "name", "subtype", "type"}
)
IDENTITY_UNCERTAINTY_MARKERS = frozenset(
    {"ambiguous", "indeterminate", "uncertain", "unclear", "unknown", "unresolved"}
)
IDENTITY_POSSIBILITY_MARKERS = frozenset(
    {"maybe", "perhaps", "possible", "possibly"}
)


class EnsembleError(RuntimeError):
    """Raised when a strict ensemble run cannot produce valid final semantics."""


class EnsembleIncompleteError(EnsembleError):
    """Raised after detector retry exhaustion leaves fewer than four ledgers."""


class CodexCallError(EnsembleError):
    """A launched Codex subprocess failed while retaining auditable accounting."""

    def __init__(
        self,
        message: str,
        *,
        failure_kind: str,
        runtime_seconds: float,
        token_usage: Optional[Dict[str, Optional[int]]],
        thread_id: Optional[str],
        returncode: Optional[int],
        subprocess_started: Optional[bool] = True,
    ) -> None:
        super().__init__(message)
        self.failure_kind = failure_kind
        self.runtime_seconds = runtime_seconds
        self.token_usage = token_usage
        self.thread_id = thread_id
        self.returncode = returncode
        self.subprocess_started = subprocess_started


@dataclass(frozen=True)
class CodexInvocation:
    payload: Dict[str, Any]
    token_usage: Optional[Dict[str, Optional[int]]]
    thread_id: Optional[str]
    runtime_seconds: float


@dataclass(frozen=True)
class EnsembleResult:
    semantics: Dict[str, Any]
    token_usage: Dict[str, Optional[int]]
    runtime_seconds: float
    run_dir: Path
    audit_path: Path
    detector_invocations: int
    adjudicator_invocations: int
    verifier_invocations: int
    matcher_invocations: int
    granularity_invocations: int
    grounding_frame_ids_by_entity: Dict[str, List[int]]


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _strict_json_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _revision_preview_input(path: Path, payload: Any) -> Dict[str, Any]:
    """Required pipeline inputs are checked outside the advisory failure boundary."""
    content_hash = _strict_json_sha256(payload)
    if _strict_json_sha256(json.loads(path.read_text(encoding="utf-8"))) != content_hash:
        raise EnsembleError(f"Revision preview input differs from saved pipeline input: {path}")
    return {"path": str(path.resolve()), "sha256": _sha256(path),
            "content_sha256": content_hash}


def _prepare_first_revision_obligation_preview(
    *, initial_decisions, verifier_reports, target_reasons, split_consensus,
    identity_review, obligation_review, output_dir: Path, provenance,
) -> Tuple[Optional[str], Dict[str, Any], Dict[str, Any]]:
    """Advisory only: never replace the candidate with the preview gate's result."""
    status = {
        "policy_version": obligation_review.FIRST_REVISION_PREVIEW_POLICY,
        "enabled": True, "status": "unavailable", "included_in_revision_prompt": False,
        "phase": "before_first_revision", "partial_current_scope_only": True,
        "pixel_truth_verified": False, "additional_model_calls": 0,
    }
    private = {**copy.deepcopy(provenance), **status}
    artifacts = {}
    provenance_path = output_dir / "first_revision_obligation_preview_provenance.private.json"
    stage = "copy_preview_inputs"
    try:
        inputs = copy.deepcopy({
            "initial": initial_decisions, "candidate": initial_decisions,
            "reports": verifier_reports, "target_reasons": target_reasons,
            "split_consensus": split_consensus,
        })
        before = _strict_json_sha256(inputs)
        stage = "physical_gate_preview"
        _discarded_gated_candidate, audit = identity_review.apply_physical_identity_gate(
            inputs["candidate"], initial_decisions=inputs["initial"],
            verifier_reports=inputs["reports"],
            verification_target_reasons=inputs["target_reasons"],
            intra_cluster_split_consensus=inputs["split_consensus"],
        )
        if _strict_json_sha256(inputs) != before:
            raise EnsembleError("Physical gate preview mutated its input copy")
        stage = "build_obligation_checklist"
        audit_hash = _strict_json_sha256(audit)
        checklist = obligation_review.build_physical_review_obligations(
            initial_decisions=inputs["initial"], candidate_decisions=inputs["candidate"],
            verifier_reports=inputs["reports"], gate_audit=audit,
            verifier_ids=VERIFIER_IDS,
        )
        if _strict_json_sha256(inputs) != before or _strict_json_sha256(audit) != audit_hash:
            raise EnsembleError("Obligation helper mutated its input or audit copy")
        stage = "serialize_obligation_prompt"
        supplement = obligation_review.first_revision_preview_prompt(checklist)
        private.update({
            "preview_inputs_content_sha256": before,
            "gate_audit_content_sha256": _strict_json_sha256(audit),
            "checklist_content_sha256": _strict_json_sha256(checklist),
            "supplement_sha256": hashlib.sha256(supplement.encode("utf-8")).hexdigest(),
            "supplement_utf8_bytes": len(supplement.encode("utf-8")),
            "preview_gated_candidate_used": False, "original_inputs_unchanged": True,
        })
        for name, payload in (
            ("first_revision_physical_gate_preview.private", audit),
            ("first_revision_obligation_checklist", checklist),
        ):
            stage = "persist_" + name
            path = output_dir / f"{name}.json"
            _atomic_write_json(path, payload)
            artifacts[name] = {"path": str(path.resolve()), "sha256": _sha256(path)}
        status.update({
            "status": "ready", "included_in_revision_prompt": True,
            "has_obligations": checklist["has_obligations"],
            "cluster_obligation_count": len(checklist["cluster_obligations"]),
            "pair_obligation_count": len(checklist["pair_obligations"]),
            "supplement_sha256": private["supplement_sha256"],
        })
        private.update(status)
        private["artifacts"] = copy.deepcopy(artifacts)
        stage = "persist_preview_provenance"
        _atomic_write_json(provenance_path, private)
        artifacts["first_revision_obligation_preview_provenance"] = {
            "path": str(provenance_path.resolve()), "sha256": _sha256(provenance_path),
        }
        status["provenance"] = artifacts["first_revision_obligation_preview_provenance"]
        return supplement, status, artifacts
    except Exception as error:
        # A failed preview is not an empty successful checklist. Partial files
        # are private diagnostics only, never reused or supplied to a model.
        status.update({"status": "unavailable", "included_in_revision_prompt": False,
                       "error_stage": stage, "error_type": type(error).__name__,
                       "error": str(error)})
        for key in ("has_obligations", "cluster_obligation_count", "pair_obligation_count", "supplement_sha256"):
            status.pop(key, None)
        private.update(status)
        private["unused_partial_artifacts"] = artifacts
        try:
            _atomic_write_json(provenance_path, private)
            status["provenance"] = {"path": str(provenance_path.resolve()), "sha256": _sha256(provenance_path)}
            return None, status, {"first_revision_obligation_preview_provenance": status["provenance"]}
        except Exception as persistence_error:
            status["unavailable_provenance_write_error"] = {
                "type": type(persistence_error).__name__, "error": str(persistence_error),
            }
            return None, status, {}


def _tail(value: str, limit: int = 4000) -> str:
    compact = value.strip()
    return compact[-limit:] if len(compact) > limit else compact


def _stream_text(value: Any) -> str:
    """Normalize subprocess streams, including TimeoutExpired byte buffers."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _aggregate_usage(
    usages: Sequence[Optional[Mapping[str, Optional[int]]]],
) -> Dict[str, Optional[int]]:
    result: Dict[str, Optional[int]] = {}
    for key in TOKEN_KEYS:
        values = [usage.get(key) if usage is not None else None for usage in usages]
        result[key] = (
            sum(int(value) for value in values)
            if values
            and all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in values
            )
            else None
        )
    return result


def _thread_id(jsonl: str) -> Optional[str]:
    for line in jsonl.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, Mapping) and event.get("type") == "thread.started":
            value = event.get("thread_id")
            if isinstance(value, str) and value:
                return value
    return None


def _codex_version(codex_bin: str) -> str:
    try:
        result = subprocess.run(
            [codex_bin, "--version"],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except Exception:
        return "unknown"
    return (result.stdout or result.stderr).strip() or "unknown"


def validate_codex_schema_transport(schema_path: Path) -> Dict[str, Any]:
    """Check observed Codex schema restrictions before starting any subprocess.

    Standard JSON Schema validity alone does not establish API compatibility.
    Runtime validators retain uniqueness checks omitted from the transport schema.
    """
    try:
        payload = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise EnsembleError(f"Cannot read Codex output schema {schema_path}: {error}") from error
    if not isinstance(payload, dict):
        raise EnsembleError(f"Codex output schema must be an object: {schema_path}")

    def visit(value, location):
        if isinstance(value, dict):
            forbidden = {"uniqueItems"}.intersection(value)
            if forbidden:
                raise EnsembleError(
                    f"Unsupported Codex schema keyword(s) {sorted(forbidden)} "
                    f"at {schema_path}:{location}"
                )
            if "$ref" in value and set(value) != {"$ref"}:
                raise EnsembleError(f"Codex schema $ref has siblings at {schema_path}:{location}")
            for key, child in value.items():
                # Property names are user data, not schema keywords.
                if key in {"properties", "$defs", "definitions", "patternProperties"}:
                    if isinstance(child, dict):
                        for name, subschema in child.items():
                            visit(subschema, f"{location}/{key}/{name}")
                elif key not in {"enum", "default", "examples", "const"}:
                    visit(child, f"{location}/{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{location}/{index}")

    visit(payload, "$")
    return payload


def run_codex_json(
    *,
    prompt: str,
    attachments: Sequence[Path],
    schema_path: Path,
    output_path: Path,
    events_path: Path,
    stderr_path: Path,
    codex_bin: str,
    model: Optional[str],
    timeout_sec: int,
    work_dir: Path = PROJECT_ROOT,
    persistent: bool = False,
    resume_thread_id: Optional[str] = None,
    verbose: bool = False,
    request_context: Optional[Mapping[str, Any]] = None,
) -> CodexInvocation:
    """Run one isolated structured Codex call without forwarding JSONL to stdout."""
    if shutil.which(codex_bin) is None and not Path(codex_bin).is_file():
        raise EnsembleError(f"Codex CLI was not found: {codex_bin}")
    if not schema_path.is_file():
        raise EnsembleError(f"Codex output schema is missing: {schema_path}")
    validate_codex_schema_transport(schema_path)
    for path in attachments:
        if not path.is_file():
            raise EnsembleError(f"Codex image attachment is missing: {path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    if resume_thread_id is None:
        command = [
            codex_bin,
            "--ask-for-approval",
            "never",
            "exec",
        ]
        if not persistent:
            command.append("--ephemeral")
        command.extend(
            [
                "--color",
                "never",
                "--json",
                "--sandbox",
                "read-only",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "--cd",
                str(work_dir),
            ]
        )
    else:
        command = [
            codex_bin,
            "exec",
            "resume",
            "--json",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
        ]
    if model:
        command.extend(["--model", model])
    for path in attachments:
        command.extend(["--image", str(path)])
    if resume_thread_id is not None:
        command.append(resume_thread_id)
    command.append("-")
    if request_context is not None:
        try:
            request = model_routing_stage.build_request_audit(
                request_context, model=model, command=command, prompt=prompt,
                attachments=attachments, schema_path=schema_path, output_path=output_path,
                events_path=events_path, stderr_path=stderr_path, codex_bin=codex_bin,
                work_dir=work_dir, persistent=persistent, resume_thread_id=resume_thread_id,
            )
            _atomic_write_json(model_routing_stage.request_path(events_path), request)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise EnsembleError("Model request audit could not be persisted: " + str(exc)) from exc

    started = time.perf_counter()
    process = None
    subprocess_started: Optional[bool] = False
    execution_error: Optional[BaseException] = None
    # The child owns these direct file descriptors. Already-written bytes remain
    # available if this Python process is killed before communicate() returns.
    # No parent-side JSONL buffer, terminal forwarding or atomic rename is used.
    try:
        with events_path.open("wb", buffering=0) as events_file, stderr_path.open(
            "wb", buffering=0
        ) as stderr_file:
            subprocess_started = None
            try:
                process = subprocess.Popen(
                    command, stdin=subprocess.PIPE, text=True,
                    stdout=events_file, stderr=stderr_file,
                )
            except OSError:
                # Popen reports an exec/spawn failure synchronously. The empty
                # streams opened above are not evidence of a launched CLI.
                subprocess_started = False
                raise
            subprocess_started = True
            with process:
                try:
                    process.communicate(input=prompt, timeout=timeout_sec)
                except BaseException:
                    process.kill()
                    process.wait()
                    raise
    except Exception as exc:
        execution_error = exc
    runtime = time.perf_counter() - started
    stdout, stderr = "", ""
    token_usage = None
    thread_id = resume_thread_id
    read_errors = []
    if subprocess_started is not False:
        try:
            stdout = _stream_text(events_path.read_bytes())
            token_usage = shot_graph.parse_codex_token_usage(stdout)
            thread_id = _thread_id(stdout) or resume_thread_id
        except OSError as exc:
            read_errors.append(str(exc))
        try:
            stderr = _stream_text(stderr_path.read_bytes())
        except OSError as exc:
            read_errors.append(str(exc))
    returncode = process.returncode if process is not None else None
    if execution_error is not None or read_errors:
        if isinstance(execution_error, subprocess.TimeoutExpired):
            kind = "timeout"
            message = f"Codex call timed out after {timeout_sec} seconds"
            returncode = None
        elif subprocess_started is False:
            kind, message = "launch_error", f"Codex call did not start: {execution_error}"
        elif execution_error is not None:
            kind, message = "subprocess_error", f"Codex subprocess failed: {execution_error}"
        else:
            kind, message = "artifact_read", "Cannot read persisted Codex streams"
        if read_errors:
            message += ": " + "; ".join(read_errors)
        raise CodexCallError(
            message, failure_kind=kind, runtime_seconds=runtime,
            token_usage=token_usage, thread_id=thread_id, returncode=returncode,
            subprocess_started=subprocess_started,
        ) from execution_error

    if verbose:
        label = "adjudicator resume" if resume_thread_id else "Codex call"
        print(
            f"[ensemble] {label}: exit={returncode}, runtime={runtime:.1f}s",
            file=sys.stderr,
            flush=True,
        )
    if returncode != 0:
        diagnostic = _tail(stderr + "\n" + stdout)
        raise CodexCallError(
            f"codex exec failed with exit code {returncode}: {diagnostic}",
            failure_kind="nonzero_exit",
            runtime_seconds=runtime,
            token_usage=token_usage,
            thread_id=thread_id,
            returncode=returncode,
        )
    if not output_path.is_file():
        raise CodexCallError(
            f"codex exec succeeded but did not write {output_path}",
            failure_kind="missing_output",
            runtime_seconds=runtime,
            token_usage=token_usage,
            thread_id=thread_id,
            returncode=returncode,
        )
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CodexCallError(
            f"Codex final message is not valid JSON in {output_path}: {exc}",
            failure_kind="artifact_read" if isinstance(exc, OSError) else "invalid_json",
            runtime_seconds=runtime,
            token_usage=token_usage,
            thread_id=thread_id,
            returncode=returncode,
        ) from exc
    if not isinstance(payload, dict):
        raise CodexCallError(
            f"Codex output must be a JSON object: {output_path}",
            failure_kind="invalid_payload_type",
            runtime_seconds=runtime,
            token_usage=token_usage,
            thread_id=thread_id,
            returncode=returncode,
        )
    if request_context is not None and resume_thread_id is not None:
        returned_thread = _thread_id(stdout)
        if returned_thread is not None and returned_thread != resume_thread_id:
            raise CodexCallError(
                "Revision native thread differs from its initial review thread",
                failure_kind="thread_mismatch", runtime_seconds=runtime,
                token_usage=token_usage, thread_id=returned_thread, returncode=returncode,
            )
    return CodexInvocation(
        payload=payload,
        token_usage=token_usage,
        thread_id=thread_id,
        runtime_seconds=runtime,
    )


def build_prompt_bound_registry(
    shot_id: str, prompt_entities: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    entities: List[Dict[str, Any]] = []
    for index, entity in enumerate(prompt_entities, start=1):
        grounding = entity.get("grounding", {})
        if not isinstance(grounding, Mapping):
            grounding = {}
        registry_id = entity.get("id", f"pb{index}")
        entities.append(
            {
                "registry_id": str(registry_id),
                "name": str(entity.get("name", "")).strip(),
                "description": str(
                    entity.get("description", entity.get("name", ""))
                ).strip(),
                "entity_type": str(entity.get("entity_type", "object")).strip(),
                "detector_status": grounding.get("status", "unknown"),
                "detected_boxes": grounding.get("boxes", []),
            }
        )
    return {"shot_id": shot_id, "entities": entities}


def semantic_prompt_bound_registry(registry: Mapping[str, Any]) -> Dict[str, Any]:
    """Strip detector-derived localization before the independent match stage."""
    return {
        "shot_id": registry["shot_id"],
        "entities": [
            {
                key: entity[key]
                for key in ("registry_id", "name", "description", "entity_type")
            }
            for entity in registry["entities"]
        ],
    }


def _load_skill(skill_dir: Path) -> Tuple[str, Dict[str, str]]:
    paths = {
        "skill": skill_dir / "SKILL.md",
        "protocol": skill_dir / "references" / "protocol.md",
        "output_contract": skill_dir / "references" / "output-contract.md",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise EnsembleError(f"Ensemble skill files are missing: {missing}")
    sections = []
    hashes: Dict[str, str] = {}
    for label, path in paths.items():
        sections.append(f"\n===== {label} =====\n{path.read_text(encoding='utf-8')}")
        hashes[str(path.resolve())] = _sha256(path)
    return "".join(sections), hashes


def _load_detector_policy(skill_dir: Path) -> Tuple[str, Path, str]:
    """Load the frozen detector-only policy without downstream role instructions."""
    path = (skill_dir / DETECTOR_POLICY_RELATIVE_PATH).resolve()
    if not path.is_file():
        raise EnsembleError(f"Detector policy file is missing: {path}")
    return path.read_text(encoding="utf-8"), path, _sha256(path)


def _copy_input_bundle(
    *,
    sample: shot_graph.VideoSample,
    shot_id: str,
    prompt_entities: Sequence[Mapping[str, Any]],
    run_dir: Path,
) -> Tuple[List[Path], Path, Path, Dict[str, Any]]:
    input_dir = run_dir / "input_bundle"
    input_dir.mkdir(parents=True, exist_ok=False)
    attachments: List[Path] = []
    frame_mapping: List[Dict[str, Any]] = []
    for frame_id in sample.reference_frame_ids:
        destination = input_dir / f"frame_{frame_id:06d}.jpg"
        shutil.copy2(sample.frame_paths[frame_id], destination)
        destination = destination.resolve()
        attachments.append(destination)
        frame_mapping.append(
            {
                "attachment_index": len(attachments),
                "frame_id": frame_id,
                "timestamp_sec": round(frame_id / sample.fps, 6),
                "path": str(destination),
                "sha256": _sha256(destination),
            }
        )
    registry_path = (input_dir / "prompt_bound_registry.json").resolve()
    registry = build_prompt_bound_registry(shot_id, prompt_entities)
    _atomic_write_json(registry_path, registry)
    semantic_registry_path = (
        input_dir / "prompt_bound_registry_semantic.json"
    ).resolve()
    _atomic_write_json(semantic_registry_path, semantic_prompt_bound_registry(registry))
    shot_manifest = {
        "shot_id": shot_id,
        "num_frames": sample.num_frames,
        "fps": sample.fps,
        "reference_frames": frame_mapping,
        "prompt_bound_registry": str(registry_path),
        "prompt_bound_registry_semantic": str(semantic_registry_path),
    }
    shot_manifest_path = (input_dir / "shot_manifest.json").resolve()
    _atomic_write_json(shot_manifest_path, shot_manifest)
    return attachments, registry_path, semantic_registry_path, shot_manifest


def _inventory_base_prompt(
    *,
    shot_id: str,
    shot_manifest: Mapping[str, Any],
    allowed_input_paths: Sequence[str],
    skill_text: str,
) -> str:
    return (
        "You are executing the all-entity inventory stage of a fixed EEC-Bench "
        "single-shot pipeline. Inspect all attached frames together and return one "
        "shot-level inventory. The prompt-bound registry is intentionally withheld: "
        "inventory every scoped physical entity without trying to predict which "
        "entities will later be excluded. Do not use shell tools, search the "
        "workspace, read other shots, infer cross-shot expectations, spawn agents, "
        "or add relations. Return only JSON conforming to the supplied schema.\n\n"
        f"shot_id: {shot_id}\n"
        "Chronological attachment mapping:\n"
        + json.dumps(shot_manifest["reference_frames"], indent=2)
        + "\n\nAllowed input paths:\n"
        + json.dumps(list(allowed_input_paths), indent=2)
        + "\n\nThe following Skill and references are the authoritative policy. "
        "Apply them completely:\n" + skill_text
    )


def _detector_base_prompt(
    *,
    shot_id: str,
    shot_manifest: Mapping[str, Any],
    allowed_input_paths: Sequence[str],
    detector_policy_text: str,
) -> str:
    return (
        "You are executing one homogeneous all-entity detector call in a fixed "
        "EEC-Bench single-shot pipeline. Inspect all attached frames together and "
        "return one shot-level inventory. The prompt-bound registry is intentionally "
        "withheld. Do not use shell tools, search the workspace, read other shots, "
        "infer cross-shot expectations, spawn agents, or add relations. Return only "
        "JSON conforming to the supplied detector schema.\n\n"
        f"shot_id: {shot_id}\n"
        "Chronological attachment mapping:\n"
        + json.dumps(shot_manifest["reference_frames"], indent=2)
        + "\n\nAllowed input paths:\n"
        + json.dumps(list(allowed_input_paths), indent=2)
        + "\n\nThe following detector-only protocol is the complete model-visible "
        "policy for this role. Apply it completely; no downstream adjudication, "
        "verification, partition, matching, grounding, relation, or cross-shot "
        "policy is part of this detector call:\n"
        + detector_policy_text
    )


def _detector_prompt(base: str, role: str, scan_instruction: str) -> str:
    return (
        base
        + "\n\nYour detector ID is "
        + role
        + ". Set detector_id exactly to that value, source_kind to detector, "
        + f"and protocol_version exactly to {PROTOCOL_VERSION}. {scan_instruction} "
        + "Use unique local IDs. Complete all three passes before emitting the final "
        + "ledger. Include the mandatory private coverage_audit with every supplied "
        + "frame, all nine spatial cells, all five content strata, and every adjacent "
        + "frame pair exactly once. Empty reviewed regions are allowed; never invent "
        + "content to fill the audit. represented_local_ids are best-effort private "
        + "cross-indexes: every listed ID must exist, but an accidental omission does "
        + "not alter the entity ledger. In temporal checks, added_local_ids means "
        + "entities newly revealed or materially confirmed by that adjacent-frame "
        + "comparison; it is independent of the required-but-empty-allowed, "
        + "pass-2-only residual_added_local_ids list. List only allowed paths "
        + "actually inspected in accessed_input_paths."
    )


def _decision_prompt(
    *,
    base: str,
    shot_id: str,
    anonymized_view: Mapping[str, Any],
    valid_frame_ids: Sequence[int],
) -> str:
    return (
        base + "\n\nYou are now the adjudicator, not another detector. Review only the "
        "anonymous proposal union below. The accompanying fixed detector panels expose "
        "which anonymous proposals came from each independent homogeneous detector, "
        "without exposing detector-local IDs. Use repeated panel support only as a "
        "stability signal: it is neither visual proof nor authority to accept, reject, "
        "merge, or select a graph partition by majority vote. Fixed panel labels are "
        "interchangeable and imply no specialization, ranking, or reliability prior. "
        "Panel membership may reveal mutually exclusive scope choices and repeated "
        "group-versus-member patterns, but original pixels remain authoritative. You "
        "have no "
        "authority to discover, add, or rescan for an entity absent from this union. "
        "Every output cluster must contain at least one supplied "
        "anonymous_proposal_id, and every supplied ID must appear exactly once. "
        "Treat every detector box only as a low-trust position reference. A box may "
        "be shifted, oversized, undersized, or attached to nearby content; it is not "
        "ground truth and must not define the proposal's identity or occupied visual "
        "content. Independently re-localize each proposal against the original pixels "
        "before using spatial agreement to merge, split, reject, or accept it. "
        "Re-localization may correct coordinates only around the proposal's claimed "
        "visual content; it must never retarget the proposal to a different nearby "
        "object. If the claimed content cannot be confirmed, reject or abstain. First "
        "cluster by physical content, using original-frame spatial location, occupied "
        "visual content, and temporal continuity before wording. Group duplicates only "
        "when they refer to the same physical content at the same candidate graph scope. "
        "Do not collapse a group-scope proposal into a member-scope proposal, or the "
        "reverse, merely to force one final graph partition. This pass freezes existence "
        "and physical identity; a later source-blind stage resolves graph-partition "
        "conflicts. Then perform "
        "a global duplicate-challenge pass over every proposed accepted cluster pair. "
        "The input may contain box_redundancy_challenges computed independently within "
        "each anonymous detector ledger. Resolve every such challenge before finalizing. "
        "When a target proposal's tight boxes have high IoU across its visible "
        "trajectory with one or more other proposal tracks, do not preserve it as a "
        "separate stable "
        "identity unless the original frames show its own separately locatable boundary "
        "or demonstrate that the proposal boxes are inaccurate. If its early boxes copy "
        "one entity and its later boxes copy another, reject or merge the incoherent "
        "track rather than accepting a switched identity. These metrics trigger review; "
        "they are not automatic deletion rules, and original pixels remain authoritative. "
        "Different names, subtypes, attributes, or detector-written relative-location "
        "phrases are hypotheses, not evidence of two instances. When two proposals "
        "could be alternate descriptions of the same physical content, keep two physical-"
        "instance clusters "
        "only if an original frame simultaneously resolves both physical instances "
        "with separately locatable boundaries, or the shot shows independent "
        "manipulation or trajectories. Alternating visibility and proposal repetition "
        "do not establish distinctness. When original pixels simultaneously show two "
        "separately localizable objects with clearly separated boundaries, preserve "
        "them as distinct physical-instance anchors even if supplied boxes overlap, one "
        "box spans both, or one box is misplaced. Merge same-scope proposals only "
        "when positive original-frame boundary or continuity evidence establishes "
        "that they represent the same physical content. Missing separation evidence "
        "alone establishes neither sameness nor distinctness. If the identity "
        "comparison remains unresolved, retain that uncertainty rather than "
        "resolving it by merging or accepting an additional instance. Spatial "
        "overlap or containment alone is also not evidence of sameness: a visibly held "
        "or carried prop remains distinct from its holder when its boundary, hand-object "
        "interaction, or coherent motion supports a separate physical object. Never "
        "merge such a prop into its holder merely because their regions overlap. "
        "Physical distinctness and graph-node partition are orthogonal, but this pass "
        "must not coarsen physically distinct anchors. When the proposal union contains "
        "both a compact group proposal and proposals for two or more separately "
        "locatable member instances, preserve the real member clusters as accepted "
        "intermediate anchors. Keep the mutually exclusive group proposal or proposals "
        "together in a separate rejected alternative cluster and add exactly the "
        "group_member_conflict uncertainty flag. Its decision_reason must state that "
        "the represented visual content is supported and rejection is only to avoid "
        "simultaneous group/member double counting. Never attach that flag to a group "
        "rejected for hallucination, unstable identity, or failed existence evidence. "
        "If a plausible compact assembly has multiple accepted physical anchors but no "
        "explicit competing group proposal, retain the anchors and add "
        "possible_compact_assembly_partition so the later partition stage can inspect "
        "them. A group proposal with no competing member partition may be accepted at "
        "its proposed scope. Large general hosts or supports remain separate from their "
        "spatially separable contents, and holders remain separate from held or carried "
        "props. Do not use lack of observed independence as permission to merge in this "
        "pass. "
        "Reject clothing, footwear, "
        "hair, body parts, and ordinary accessories proposed only by splitting them "
        "from the person currently wearing them; held or carried tools and props are "
        "separate. Then inspect the original frames and "
        "decide accept, reject, or abstain. A valid entity must be a distinguishable "
        "physical instance, or a subtle small object supported by visible carrying, "
        "handling, or motion evidence. An indistinct color block, texture, shadow, "
        "or background-integrated detail without a reliable boundary or functional "
        "role should be rejected or abstained. Proposal repetition is only a "
        "stability signal and never visual proof. The prompt-bound registry is not "
        "part of this stage: accept graph-worthy physical instances regardless of "
        "whether a later matcher may classify them as prompt-bound. For every cluster, "
        "return exactly one frame_presence entry for every valid frame. Use visible "
        "only when the cluster is sufficiently localized there; representative "
        "adjudicator_evidence remains a compact justification rather than a grounding "
        "schedule. For accept, require resolved identity, nonempty visual evidence, "
        "and a complete final_entity. For reject/abstain, final_entity must be null. Do not "
        "output relations, source guesses, vote counts, or new entities. Return "
        "schema-valid JSON only.\n\n"
        f"shot_id: {shot_id}\n"
        f"valid_frame_ids: {json.dumps(list(valid_frame_ids))}\n"
        "anonymized_candidates:\n"
        + json.dumps(anonymized_view, indent=2, ensure_ascii=False)
    )


def _compact_verification_proposal(proposal: Mapping[str, Any]) -> Dict[str, Any]:
    """Expose claimed scope and location without proposal-side judgments."""
    compact = {
        key: copy.deepcopy(proposal[key])
        for key in ("anonymous_proposal_id", "proposed_name", "granularity")
        if key in proposal
    }
    compact["coarse_locators"] = [
        {key: copy.deepcopy(locator[key]) for key in ("frame_id", "description") if key in locator}
        for locator in proposal.get("coarse_locators", [])
    ]
    compact["frame_presence"] = [
        {key: copy.deepcopy(presence[key])
         for key in ("frame_id", "status", "bbox_xyxy_normalized") if key in presence}
        for presence in proposal.get("frame_presence", [])
    ]
    return compact


def _verification_view(
    decisions: Mapping[str, Any],
    anonymized_view: Mapping[str, Any],
    target_cluster_ids: Sequence[str],
    identity_challenge_pairs: Sequence[Mapping[str, Any]],
    intra_cluster_split_challenges: Sequence[Mapping[str, Any]] = (),
) -> Dict[str, Any]:
    target_ids = set(target_cluster_ids)
    proposals = {
        item["anonymous_proposal_id"]: item for item in anonymized_view["proposals"]
    }
    targets = []
    for cluster in decisions["clusters"]:
        if cluster["cluster_id"] not in target_ids:
            continue
        targets.append(
            {
                "cluster_id": cluster["cluster_id"],
                "canonical_name": cluster["canonical_name"],
                "granularity": cluster["granularity"],
                "proposals": [
                    _compact_verification_proposal(proposals[proposal_id])
                    for proposal_id in cluster["anonymous_proposal_ids"]
                ],
            }
        )
    cluster_index = [
        {
            "cluster_id": cluster["cluster_id"],
            "canonical_name": cluster["canonical_name"],
            "granularity": cluster["granularity"],
        }
        for cluster in decisions["clusters"]
    ]
    return {
        "targets": targets,
        "cluster_index": cluster_index,
        "identity_challenge_pairs": copy.deepcopy(list(identity_challenge_pairs)),
        "intra_cluster_divergent_footprint_challenges": copy.deepcopy(
            list(intra_cluster_split_challenges)
        ),
    }


def _verifier_prompt(
    *,
    base: str,
    shot_id: str,
    verifier_id: str,
    verification_view: Mapping[str, Any],
    valid_frame_ids: Sequence[int],
) -> str:
    return (
        base + "\n\nYou are an independent targeted verifier, not a detector or final "
        "adjudicator. Set verifier_id exactly to "
        + verifier_id
        + f" and protocol_version exactly to {PROTOCOL_VERSION}. Review every and "
        "only target cluster below against the original frames. Do not discover or "
        "mention any entity outside the supplied cluster index. Judge whether the "
        "target is a real distinguishable physical instance, whether it is graph-"
        "worthy rather than an indistinct background detail, and whether it is the "
        "same physical instance as another listed cluster. Separately judge whether "
        "physically distinct constituents should share one graph node as a compact "
        "assembly. Explicitly review every "
        "identity_challenge_pair in the supplied view. Names and detector-written "
        "relative positions do not prove distinctness. For a possible same-physical-"
        "instance duplicate, verify at least one original frame where both instances are "
        "simultaneously visible and separately locatable by physical boundary, or cite "
        "independent manipulation or trajectories. Report a cluster in "
        "same_instance_with_cluster_ids only with positive same-content, same-scope "
        "boundary or continuity evidence. If neither sameness nor distinctness is "
        "established, leave the alias list empty and describe the unresolved "
        "comparison explicitly rather than confirming two "
        "physical instances. Do not reuse a two-boundary witness as evidence that compact "
        "assembly constituents require separate graph nodes. "
        "For a detector_box_trajectory_coverage challenge, inspect the cited frames and "
        "decide whether the target has its own stable boundary or whether its boxes copy "
        "another track, including a possible switch between tracks over time. Treat the "
        "computed overlap only as review evidence; the original frame is authoritative. "
        "Spatial overlap or containment alone never proves identity. Visible carrying, "
        "handling, or coherent motion can confirm a subtle small object as separate "
        "from its holder even when their regions overlap; commonsense alone cannot. "
        "Worn apparel and ordinary worn accessories belong to the person "
        "unless visibly removed, while a held or carried prop remains separate. Prefer "
        "one graph node for a compact local assembly unless this shot shows separate "
        "handling/use, detachment, a standalone state, relative motion, or an independent "
        "trajectory. A constituent boundary, theoretical removability, abstract function, "
        "or confirmed existence is insufficient to split it. Large general hosts do not "
        "absorb their spatially separable contents. For every review, set "
        "graph_partition_judgment, same_graph_node_with_cluster_ids, and "
        "observed_independence_evidence independently from the physical-identity field "
        "same_instance_with_cluster_ids. The same_instance_with_cluster_ids and "
        "same_graph_node_with_cluster_ids lists must be disjoint in every review: one "
        "cluster cannot simultaneously be the same physical instance and a physically "
        "distinct compact-assembly constituent. If physical identity is judged the same, "
        "record that cluster only in same_instance_with_cluster_ids and exclude it from "
        "the graph-partition target list. Use merge_into_compact_composite only for "
        "physically distinct constituents that should share one node; list all relevant "
        "target cluster IDs. Use keep_as_separate_node for a large-host relationship or "
        "when shot-observed independence supports splitting, and cite that independence "
        "when applicable. Use uncertain rather than forcing a split. These graph-"
        "partition fields are advisory evidence for the later dedicated partition "
        "stage; they do not authorize this verifier or the immediate revision pass to "
        "merge physically distinct clusters. Separately, review every supplied "
        "intra_cluster_divergent_footprint_challenge. It is a physical-instance audit "
        "inside one already formed cluster, not a graph-granularity vote. Proposal "
        "boxes are fallible position hints and their divergence never proves multiple "
        "objects. Re-localize each proposal's claimed content in the original pixels. "
        "For a challenged cluster, set intra_cluster_split_judgment to "
        "split_into_multiple_physical_instances only when the frames directly show all "
        "proposed units as real, graph-worthy, separately bounded physical instances. "
        "proposed_physical_units must then partition every anonymous proposal ID in "
        "that target cluster exactly once; assign verifier-local unit IDs, confirm each "
        "unit's existence and graph worthiness, and cite its own visual evidence. Also "
        "supply direct pairwise_physical_separation_evidence for every unordered pair "
        "of proposed units: one valid frame plus a distinct locator for each boundary. "
        "Weak evidence, box separation alone, alternating visibility, or different "
        "names cannot support a split. When inaccurate or differently sized boxes still "
        "describe one physical instance, use keep_single_physical_instance. When the "
        "pixels do not resolve the question, use uncertain. For a target with no such "
        "challenge, use not_reviewed. Unless the judgment is "
        "split_into_multiple_physical_instances, proposed_physical_units and "
        "pairwise_physical_separation_evidence must both be empty. Source labels, "
        "detector counts, and panel support are absent and must not be inferred. These "
        "fields propose a review partition only: this verifier cannot split anything, "
        "and the persistent adjudicator must still inspect the pixels. The prompt-bound registry is withheld and must not be inferred or "
        "discussed. A color patch, shadow, texture, or unresolved region is not "
        "confirmation. Supplied names and location hints identify claims to recheck, "
        "not visual facts; a specific category label alone is never proof. For each "
        "evidence item, coarse_locator must state the observed physical boundary "
        "or direct interaction cue, its separation from or continuity with nearby "
        "content, and any occlusion, contrast, or resolution limitation. State when "
        "no material limitation is visible. Across supplied frames, if neither boundary "
        "nor interaction evidence resolves the physical claim, describe that limitation "
        "and use an uncertain judgment rather than filling the gap with the proposed "
        "name. Inspect the full original frames; proposal boxes remain fallible location "
        "hints. Provide evidence only from valid frames. Return schema-valid "
        "JSON only.\n\n"
        f"shot_id: {shot_id}\n"
        f"valid_frame_ids: {json.dumps(list(valid_frame_ids))}\n"
        "verification_targets:\n"
        + json.dumps(verification_view, indent=2, ensure_ascii=False)
    )


def _retention_eligible_parents(initial_decisions, target_ids):
    return sorted(
        row["cluster_id"] for row in initial_decisions["clusters"]
        if row["cluster_id"] in set(target_ids) and row["decision"] == "accept"
        and len(row["anonymous_proposal_ids"]) >= 2
        and not set(row.get("uncertainty_flags", [])) & {
            "group_member_conflict", "possible_compact_assembly_partition",
        }
    )


def _retention_public_review(consensus, initial_decisions):
    """Expose permissions and current subset observations, never private sources."""
    initial = {c["cluster_id"]: c for c in initial_decisions["clusters"]}
    reports = {r["verifier_id"]: r for r in consensus["input_binding"]["verifier_reports"]}
    permissions = []
    for row in consensus["records"]:
        if row["status"] != "authorized_single_survivor":
            continue
        permissions.append({
            "parent_cluster_id": row["parent_cluster_id"],
            "parent_anonymous_proposal_ids": initial[row["parent_cluster_id"]]["anonymous_proposal_ids"],
            "retained_anonymous_proposal_ids": row["retained_anonymous_proposal_ids"],
            "residual_anonymous_proposal_ids": row["residual_anonymous_proposal_ids"],
            "residual_status": "unresolved",
            "verifier_requests": [
                {"verifier_id": proof["verifier_id"],
                 "request": reports[proof["verifier_id"]]["retention_requests"][proof["request_index"]]}
                for proof in row["proofs"]
            ],
        })
    return copy.deepcopy({"scope_retention_policy": SCOPE_RETENTION_POLICY,
                          "authorized_retention": permissions,
                          "automatic_acceptance": False,
                          "residual_is_a_physical_unit": False})


def _retention_native_source(invocation, raw_path, events_path):
    """Bind a successful fresh verifier to actual saved native events and raw."""
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    threads = [e.get("thread_id") for e in events if e.get("type") == "thread.started"]
    if (len(threads) != 1 or not isinstance(threads[0], str) or not threads[0]
            or threads[0] != invocation.thread_id
            or sum(e.get("type") == "turn.completed" for e in events) != 1
            or any(e.get("type") == "turn.failed" for e in events)):
        raise EnsembleError("Scope retention requires a completed fresh verifier native thread")
    saved = json.loads(raw_path.read_text(encoding="utf-8"))
    if _strict_json_sha256(saved) != _strict_json_sha256(invocation.payload):
        raise EnsembleError("Scope retention verifier payload differs from saved raw")
    return {"source_id": str(events_path.resolve()), "thread_id": threads[0],
            "report_sha256": _strict_json_sha256(invocation.payload)}


def _validate_retention_residual_lineage(decisions, transition):
    """A graph representation may not recover an unconfirmed residual as accepted."""
    residual = set().union(*(set(row["residual_anonymous_proposal_ids"])
                             for row in transition.get("audited_transitions", [])))
    owners = {p: [] for p in residual}
    for cluster in decisions["clusters"]:
        for proposal in residual.intersection(cluster["anonymous_proposal_ids"]):
            owners[proposal].append(cluster["cluster_id"])
            if cluster["decision"] == "accept" or cluster["final_entity"] is not None:
                raise EnsembleError("Graph partition promoted an unresolved retention residual")
    if any(len(ids) != 1 for ids in owners.values()):
        raise EnsembleError("Graph partition lost or duplicated a retention residual")
    return {"residual_proposal_owners": owners, "all_residuals_nonaccepted": True,
            "residual_existence_asserted": False}


def _revision_prompt(
    *,
    shot_id: str,
    initial_decisions: Mapping[str, Any],
    verifier_reports: Sequence[Mapping[str, Any]],
    identity_challenge_pairs: Sequence[Mapping[str, Any]],
    valid_frame_ids: Sequence[int],
    intra_cluster_split_consensus: Optional[Mapping[str, Any]] = None,
    scope_retention_review: Optional[Mapping[str, Any]] = None,
) -> str:
    prompt = (
        "Continue as the same adjudicator. Two isolated targeted verifiers reviewed "
        "the listed weak or unresolved clusters. Reconsider their evidence, then "
        "return the complete adjudication ledger again. You may merge existing "
        "clusters, but may split an initial cluster only under the exact-consensus "
        "contract below. You may otherwise repartition existing anonymous proposals "
        "only when the reports reveal that differently "
        "named clusters occupy the same physical content at the same candidate graph "
        "scope. You may not invent a proposal, "
        "emit an empty cluster, discover a new entity, or use another shot. Preserve "
        "every anonymous proposal exactly once. Resolve every supplied identity-"
        "challenge pair and repeat the global duplicate pass before finalizing. A "
        "possible same-physical-instance pair may remain as two physical clusters "
        "only with a same-frame two-boundary "
        "witness or independent manipulation or trajectories; names, relative-location "
        "wording, and verifier agreement are not proof. Spatial overlap metrics are "
        "review evidence rather than an automatic merge: explicitly resolve "
        "detector_box_trajectory_coverage and track-switch challenges from the original "
        "frames, rejecting an incoherent switched track unless it has its own stable "
        "visual identity. Correcting a bad box never permits retargeting a proposal to "
        "different nearby content; reject or abstain when its claimed content is not "
        "confirmed. Conversely, spatial overlap "
        "alone must not merge a visibly distinct held or carried prop with its holder. "
        "Verifier agreement is not proof: "
        "accept only with direct visual or visible interaction/temporal evidence; "
        "otherwise reject or abstain. Enforce the same scope rules during revision: "
        "do not retain worn-person components as entities. This revision pass freezes "
        "physical identity and existence only; it has no graph-partition authority. "
        "The supplied intra_cluster_split_consensus contains only cases in which two "
        "isolated verifiers independently returned the exact same proposal-set "
        "partition with confirmed, graph-worthy units and direct evidence for every "
        "pairwise physical boundary. It is permission to review a split, not visual "
        "proof and not an automatic split. Split only after independently confirming "
        "those same physical units in the original frames, and then use exactly the "
        "consensus proposal partition. A one-verifier proposal, a partition mismatch, "
        "box divergence alone, containment, or an omitted case never authorizes a "
        "split. If a permitted split is not visually confirmed, preserve the initial "
        "cluster and express uncertainty instead. "
        "Treat graph_partition_judgment, same_graph_node_with_cluster_ids, and the "
        "absence of an independence witness as advisory evidence for a later dedicated "
        "single-shot partition stage. Never merge physically distinct clusters merely "
        "because verifiers prefer a compact composite or fail to observe independent "
        "motion. Preserve accepted member anchors, rejected group alternatives carrying "
        "group_member_conflict, and possible_compact_assembly_partition flags for that "
        "later stage. Do not promote a rejected group alternative simply because its "
        "constituent visual content exists. You may change a decision for failed or "
        "confirmed physical existence, unstable identity, salience, or scope, and may "
        "merge true same-content duplicates. Keep large general hosts separate from "
        "spatially separable supported objects, and keep a holder separate from a held "
        "or carried prop. "
        "Regenerate exactly one frame_presence entry per valid frame for every final "
        "cluster; do not copy sparse representative evidence as a visibility schedule. "
        "Return schema-valid "
        "JSON only.\n\n"
        f"shot_id: {shot_id}\n"
        f"valid_frame_ids: {json.dumps(list(valid_frame_ids))}\n"
        "initial_adjudication:\n"
        + json.dumps(initial_decisions, indent=2, ensure_ascii=False)
        + "\n\nidentity_challenge_pairs:\n"
        + json.dumps(list(identity_challenge_pairs), indent=2, ensure_ascii=False)
        + "\n\nintra_cluster_split_consensus:\n"
        + json.dumps(
            intra_cluster_split_consensus or {}, indent=2, ensure_ascii=False
        )
        + "\n\nverifier_reports:\n"
        + json.dumps(list(verifier_reports), indent=2, ensure_ascii=False)
    )
    if scope_retention_review is not None:
        prompt = prompt.replace(
            "clusters, but may split an initial cluster only under the exact-consensus contract below.",
            "clusters. Ordinary physical splits require the exact-consensus contract below; "
            "the separately supplied single-survivor retention permission is its only additional scope-contraction path.",
        )
        prompt += ("\n\nOptional single-survivor scope retention is separate from ordinary physical splits. "
                   "Use only an exact authorized subset below, or preserve the complete parent. "
                   "The unresolved residual is not a confirmed physical unit; retain its original claims "
                   "exactly once in nonaccepted records with final_entity=null. The original full-parent "
                   "and pair obligations remain; regenerated exact-final-scope evidence is required. "
                   "The first-revision partial preview is not a prediction of these future subset obligations.\n"
                   + json.dumps(scope_retention_review, ensure_ascii=False, sort_keys=True))
    return prompt


def _revision_identity_fields_instruction(identity_review, revision_output_policy: str) -> str:
    """Change only the selected revision transport; canonical inputs stay canonical."""
    instruction = identity_review.ADJUDICATION_FIELDS_INSTRUCTION
    if revision_output_policy == "canonical":
        return instruction
    if revision_output_policy != "implicit_owner_wire_v0.1":
        raise EnsembleError("invalid revision output policy")
    replacements = (
        ("Use schema_version=physical_identity_review_v0.6",
         "Use schema_version=physical_identity_revision_wire_v0.1 for this revision output"),
        ("target_cluster_ids (all initial targets involved in that assertion),\n"
         "anonymous_proposal_ids (exact final cluster scope), and evidence_indices (zero\n"
         "based indices into this cluster's adjudicator_evidence).",
         "target_cluster_ids (all initial targets involved in that assertion), and\n"
         "evidence_indices (zero based indices into this cluster's adjudicator_evidence)."),
    )
    for old, new in replacements:
        if instruction.count(old) != 1:
            raise EnsembleError("Canonical revision instructions changed; wire wording needs explicit review")
        instruction = instruction.replace(old, new, 1)
    return instruction + "\n\n" + _revision_wire_output_instruction()


def _revision_wire_output_instruction() -> str:
    return (
        "CURRENT REVISION OUTPUT FORMAT: use physical_identity_revision_wire_v0.1. "
        "Return the complete ledger in the supplied revision wire schema. Canonical "
        "initial ledgers, verifier reports and earlier thread messages are input "
        "material, not the output format for this turn. On each revision_resolutions "
        "row output only axis, target_cluster_ids and evidence_indices; do not output "
        "anonymous_proposal_ids on that row. Its owner is exactly its containing final "
        "cluster; deterministic materialization copies that cluster's complete own "
        "proposal array without changing evidence. Keep anonymous_proposal_ids on "
        "clusters and observations. Observation proposal IDs for pair evidence must "
        "still equal both complete compared scopes. Initial target IDs remain initial "
        "IDs, comparison endpoints remain final cluster IDs, and all local evidence "
        "indices remain model-selected. Omitting the redundant owner field neither "
        "creates proof nor permits a partial scope, new proposal, unreviewed split, "
        "or any change to the physical evidence and exact two-verifier split rules."
    )


def _revision_repair_prompt(
    *,
    shot_id: str,
    validation_error: str,
    accounting_diagnostics: Mapping[str, Any],
    intra_cluster_split_consensus: Optional[Mapping[str, Any]] = None,
    scope_retention_review: Optional[Mapping[str, Any]] = None,
) -> str:
    prompt = (
        "Continue as the same adjudicator. Your immediately preceding revised "
        "ledger failed deterministic validation and cannot be used. This is a "
        "single accounting-repair retry, not a new discovery or visual-review "
        "stage. Return the complete adjudication ledger again in the same schema. "
        "Every original anonymous proposal ID must appear exactly once across all "
        "nonempty clusters: never repeat a proposal in both an accepted merged "
        "cluster and a rejected residual cluster. Remove such residual duplication "
        "while preserving the intended physical-instance decision and all deferred "
        "graph-partition alternatives and flags. This repair has no graph-partition "
        "authority. Do not split an initial cluster unless it appears in the supplied "
        "exact consensus list, and make every permitted split match that proposal "
        "partition exactly. Otherwise restore the initial cluster without splitting. "
        "Do not add an ID, entity, relation, source guess, or information from "
        "another shot. Recheck all schema invariants before responding. Return JSON "
        "only.\n\n"
        f"shot_id: {shot_id}\n"
        f"validation_error: {validation_error}\n"
        "intra_cluster_split_consensus:\n"
        + json.dumps(
            intra_cluster_split_consensus or {}, indent=2, ensure_ascii=False
        )
        + "\nproposal_accounting_diagnostics:\n"
        + json.dumps(accounting_diagnostics, indent=2, ensure_ascii=False)
    )
    if scope_retention_review is not None:
        prompt = prompt.replace(
            "Do not split an initial cluster unless it appears in the supplied exact consensus list, "
            "and make every permitted split match that proposal partition exactly. "
            "Otherwise restore the initial cluster without splitting.",
            "Ordinary physical splits still require the supplied exact consensus partition. "
            "Separately, only the supplied exact single-survivor retention permissions may contract "
            "a parent scope; their residual stays unresolved and nonaccepted, never a physical split unit. "
            "Otherwise preserve the complete initial parent.",
        )
        prompt += "\n\noptional_scope_retention:\n" + json.dumps(
            scope_retention_review, ensure_ascii=False, sort_keys=True)
    return prompt


def frozen_inventory_view(decisions: Mapping[str, Any]) -> Dict[str, Any]:
    """Expose immutable accepted inventory content without detector provenance."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "shot_id": decisions["shot_id"],
        "clusters": [
            {
                key: cluster[key]
                for key in (
                    "cluster_id",
                    "canonical_name",
                    "aliases",
                    "granularity",
                    "adjudicator_evidence",
                    "frame_presence",
                    "final_entity",
                )
            }
            for cluster in decisions["clusters"]
            if cluster["decision"] == "accept"
        ],
    }


def _matcher_prompt(
    *,
    shot_id: str,
    shot_manifest: Mapping[str, Any],
    semantic_registry: Mapping[str, Any],
    inventory_view: Mapping[str, Any],
    allowed_input_paths: Sequence[str],
    skill_text: str,
) -> str:
    return (
        "You are the prompt-bound identity matcher in a fixed single-shot pipeline. "
        "The supplied all-entity inventory is already frozen. You have no authority "
        "to discover, add, remove, merge, split, rename, re-ground, or otherwise "
        "revise an inventory cluster. Inspect the attached frames only to decide "
        "whether each accepted cluster is the same physical instance as a semantic "
        "registry entry. Classify every supplied cluster exactly once as bound, "
        "unbound, or ambiguous. Bound requires exactly one matching registry ID; "
        "unbound requires none; ambiguous must list one or more plausible IDs. Being "
        "near, inside, supported by, held by, carried by, or overlapping a registry "
        "entity does not make a distinct physical object bound. The registry contains "
        "no detector boxes by design. Do not search the workspace, read another shot, "
        "infer cross-shot expectations, or output anything outside the schema.\n\n"
        f"shot_id: {shot_id}\n"
        "Chronological attachment mapping:\n"
        + json.dumps(shot_manifest["reference_frames"], indent=2)
        + "\n\nAllowed input paths:\n"
        + json.dumps(list(allowed_input_paths), indent=2)
        + "\n\nFrozen semantic prompt-bound registry:\n"
        + json.dumps(semantic_registry, indent=2, ensure_ascii=False)
        + "\n\nFrozen accepted all-entity inventory:\n"
        + json.dumps(inventory_view, indent=2, ensure_ascii=False)
        + "\n\nThe following Skill and references are authoritative. Apply only "
        "the frozen-inventory matching policy relevant to this role:\n"
        + skill_text
    )


def _validate_frame_presence(
    value: Any,
    *,
    owner: str,
    valid_frame_ids: Sequence[int],
    require_visible: bool,
    require_bbox: bool = False,
) -> None:
    if not isinstance(value, list):
        raise EnsembleError(f"{owner}: frame_presence must be an array")
    expected = set(valid_frame_ids)
    seen: List[int] = []
    visible = 0
    for item in value:
        if not isinstance(item, Mapping):
            raise EnsembleError(f"{owner}: invalid frame_presence item")
        frame_id = item.get("frame_id")
        status = item.get("status")
        description = item.get("description")
        if frame_id not in expected or status not in {
            "visible",
            "absent",
            "occluded",
            "uncertain",
        }:
            raise EnsembleError(f"{owner}: invalid frame_presence value")
        if not isinstance(description, str) or not description.strip():
            raise EnsembleError(f"{owner}: frame_presence needs a description")
        if require_bbox:
            bbox = item.get("bbox_xyxy_normalized")
            if status == "visible":
                if not _is_valid_normalized_bbox(bbox):
                    raise EnsembleError(
                        f"{owner}: visible frame_presence needs a valid tight box"
                    )
            elif bbox is not None:
                raise EnsembleError(
                    f"{owner}: non-visible frame_presence box must be null"
                )
        seen.append(frame_id)
        visible += status == "visible"
    if len(seen) != len(set(seen)) or set(seen) != expected:
        raise EnsembleError(
            f"{owner}: frame_presence must cover every supplied frame exactly once"
        )
    if require_visible and visible == 0:
        raise EnsembleError(f"{owner}: accepted entity has no visible frame")


def _is_valid_normalized_bbox(value: Any) -> bool:
    if not isinstance(value, list) or len(value) != 4:
        return False
    if any(
        isinstance(coordinate, bool)
        or not isinstance(coordinate, (int, float))
        or not math.isfinite(float(coordinate))
        or not 0.0 <= float(coordinate) <= 1.0
        for coordinate in value
    ):
        return False
    x1, y1, x2, y2 = (float(coordinate) for coordinate in value)
    return x1 < x2 and y1 < y2


def _bbox_iou(left: Sequence[float], right: Sequence[float]) -> float:
    intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    left_area = (left[2] - left[0]) * (left[3] - left[1])
    right_area = (right[2] - right[0]) * (right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union > 0.0 else 0.0


def _bbox_intersection_over_smaller(
    left: Sequence[float], right: Sequence[float]
) -> float:
    """Return intersection/min(area), so containment is not mistaken for separation."""
    intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    left_area = (left[2] - left[0]) * (left[3] - left[1])
    right_area = (right[2] - right[0]) * (right[3] - right[1])
    smaller_area = min(left_area, right_area)
    return intersection / smaller_area if smaller_area > 0.0 else 0.0


def _validated_detector_audit_local_ids(
    value: Any,
    *,
    owner: str,
    valid_local_ids: set[str],
) -> set[str]:
    if not isinstance(value, list) or not all(
        isinstance(local_id, str) and local_id for local_id in value
    ):
        raise EnsembleError(f"{owner}: local IDs must be a string array")
    if len(value) != len(set(value)):
        raise EnsembleError(f"{owner}: duplicate local IDs")
    unknown = sorted(set(value) - valid_local_ids)
    if unknown:
        raise EnsembleError(f"{owner}: unknown local IDs {unknown}")
    return set(value)


def _validate_detector_coverage_audit(
    audit: Any,
    *,
    detector_id: str,
    valid_frame_ids: Sequence[int],
    valid_local_ids: set[str],
) -> Dict[str, Any]:
    owner = f"{detector_id}.coverage_audit"
    if not isinstance(audit, Mapping):
        raise EnsembleError(f"{owner}: must be an object")

    reviewed_frame_ids = audit.get("reviewed_frame_ids")
    if reviewed_frame_ids != list(valid_frame_ids):
        raise EnsembleError(
            f"{owner}: reviewed_frame_ids must exactly match chronological frames"
        )
    valid_frames = set(valid_frame_ids)

    residual_ids = _validated_detector_audit_local_ids(
        audit.get("residual_added_local_ids"),
        owner=f"{owner}.residual_added_local_ids",
        valid_local_ids=valid_local_ids,
    )

    spatial_cells = audit.get("spatial_cells")
    if not isinstance(spatial_cells, list) or len(spatial_cells) != len(
        DETECTOR_SPATIAL_CELLS
    ):
        raise EnsembleError(f"{owner}: spatial_cells must contain all nine cells")
    seen_cells: List[str] = []
    spatially_represented: set[str] = set()
    for index, record in enumerate(spatial_cells):
        record_owner = f"{owner}.spatial_cells[{index}]"
        if not isinstance(record, Mapping):
            raise EnsembleError(f"{record_owner}: must be an object")
        cell = record.get("cell")
        if cell not in DETECTOR_SPATIAL_CELLS:
            raise EnsembleError(f"{record_owner}: invalid cell {cell!r}")
        seen_cells.append(cell)
        if record.get("best_frame_id") not in valid_frames:
            raise EnsembleError(f"{record_owner}: invalid best_frame_id")
        spatially_represented.update(
            _validated_detector_audit_local_ids(
                record.get("represented_local_ids"),
                owner=f"{record_owner}.represented_local_ids",
                valid_local_ids=valid_local_ids,
            )
        )
    if len(seen_cells) != len(set(seen_cells)) or set(seen_cells) != set(
        DETECTOR_SPATIAL_CELLS
    ):
        raise EnsembleError(
            f"{owner}: every spatial cell must appear exactly once"
        )

    content_strata = audit.get("content_strata")
    if not isinstance(content_strata, list) or len(content_strata) != len(
        DETECTOR_CONTENT_STRATA
    ):
        raise EnsembleError(
            f"{owner}: content_strata must contain all five strata"
        )
    seen_strata: List[str] = []
    semantically_represented: set[str] = set()
    for index, record in enumerate(content_strata):
        record_owner = f"{owner}.content_strata[{index}]"
        if not isinstance(record, Mapping):
            raise EnsembleError(f"{record_owner}: must be an object")
        stratum = record.get("stratum")
        if stratum not in DETECTOR_CONTENT_STRATA:
            raise EnsembleError(f"{record_owner}: invalid stratum {stratum!r}")
        seen_strata.append(stratum)
        semantically_represented.update(
            _validated_detector_audit_local_ids(
                record.get("represented_local_ids"),
                owner=f"{record_owner}.represented_local_ids",
                valid_local_ids=valid_local_ids,
            )
        )
    if len(seen_strata) != len(set(seen_strata)) or set(seen_strata) != set(
        DETECTOR_CONTENT_STRATA
    ):
        raise EnsembleError(
            f"{owner}: every content stratum must appear exactly once"
        )

    temporal_checks = audit.get("temporal_reveal_checks")
    if not isinstance(temporal_checks, list):
        raise EnsembleError(f"{owner}: temporal_reveal_checks must be an array")
    expected_pairs = list(zip(valid_frame_ids, valid_frame_ids[1:]))
    actual_pairs: List[Tuple[int, int]] = []
    temporally_represented: set[str] = set()
    for index, record in enumerate(temporal_checks):
        record_owner = f"{owner}.temporal_reveal_checks[{index}]"
        if not isinstance(record, Mapping):
            raise EnsembleError(f"{record_owner}: must be an object")
        pair = (record.get("earlier_frame_id"), record.get("later_frame_id"))
        actual_pairs.append(pair)
        revealed_cells = record.get("newly_revealed_cells")
        if not isinstance(revealed_cells, list) or any(
            cell not in DETECTOR_SPATIAL_CELLS for cell in revealed_cells
        ):
            raise EnsembleError(f"{record_owner}: invalid newly_revealed_cells")
        if len(revealed_cells) != len(set(revealed_cells)):
            raise EnsembleError(f"{record_owner}: duplicate newly revealed cells")
        added_ids = _validated_detector_audit_local_ids(
            record.get("added_local_ids"),
            owner=f"{record_owner}.added_local_ids",
            valid_local_ids=valid_local_ids,
        )
        temporally_represented.update(added_ids)
    if actual_pairs != expected_pairs:
        raise EnsembleError(
            f"{owner}: temporal reveal checks must cover every adjacent frame pair "
            "exactly once in chronological order"
        )

    missing_spatial = sorted(valid_local_ids - spatially_represented)
    missing_strata = sorted(valid_local_ids - semantically_represented)
    return {
        "unindexed_spatial_local_ids": missing_spatial,
        "unindexed_content_stratum_local_ids": missing_strata,
        "pass2_residual_local_ids": sorted(residual_ids),
        "temporal_revealed_or_confirmed_local_ids": sorted(
            temporally_represented
        ),
        "has_nonfatal_cross_index_omissions": bool(
            missing_spatial or missing_strata
        ),
    }


def validate_ledger(
    ledger: Mapping[str, Any],
    *,
    shot_id: str,
    detector_id: str,
    source_kind: str,
    valid_frame_ids: Sequence[int],
    allowed_input_paths: Sequence[str],
) -> Dict[str, Any]:
    if ledger.get("protocol_version") != PROTOCOL_VERSION:
        raise EnsembleError(f"{detector_id}: wrong protocol_version")
    expected = {
        "shot_id": shot_id,
        "detector_id": detector_id,
        "source_kind": source_kind,
    }
    for key, value in expected.items():
        if ledger.get(key) != value:
            raise EnsembleError(
                f"{detector_id}: {key}={ledger.get(key)!r}, expected {value!r}"
            )
    accessed = ledger.get("accessed_input_paths")
    if not isinstance(accessed, list) or not all(
        isinstance(path, str) for path in accessed
    ):
        raise EnsembleError(f"{detector_id}: invalid accessed_input_paths")
    unexpected = sorted(set(accessed) - set(allowed_input_paths))
    if unexpected:
        raise EnsembleError(
            f"{detector_id}: accessed paths outside allowlist: {unexpected}"
        )
    entities = ledger.get("entities")
    if not isinstance(entities, list):
        raise EnsembleError(f"{detector_id}: entities must be an array")
    valid_frames = set(valid_frame_ids)
    local_ids = set()
    for index, entity in enumerate(entities):
        if not isinstance(entity, Mapping):
            raise EnsembleError(f"{detector_id}: entities[{index}] is not an object")
        local_id = entity.get("local_id")
        if not isinstance(local_id, str) or not local_id or local_id in local_ids:
            raise EnsembleError(f"{detector_id}: invalid or duplicate local_id")
        local_ids.add(local_id)
        for field in (
            "proposed_name",
            "canonical_head",
            "entity_type",
            "granularity",
        ):
            if not isinstance(entity.get(field), str) or not entity[field].strip():
                raise EnsembleError(
                    f"{detector_id}: {local_id}.{field} must be nonempty"
                )
        confidence = entity.get("self_confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not 0.0 <= float(confidence) <= 1.0
        ):
            raise EnsembleError(f"{detector_id}: invalid self_confidence")
        evidence = entity.get("evidence_frame_ids")
        if (
            not isinstance(evidence, list)
            or not evidence
            or len(evidence) != len(set(evidence))
            or not set(evidence) <= valid_frames
        ):
            raise EnsembleError(f"{detector_id}: invalid evidence frame IDs")
        attributes = entity.get("attributes")
        if not isinstance(attributes, list):
            raise EnsembleError(f"{detector_id}: {local_id}.attributes must be an array")
        for attribute_index, attribute in enumerate(attributes):
            attribute_evidence = (
                attribute.get("evidence_frame_ids")
                if isinstance(attribute, Mapping)
                else None
            )
            if (
                not isinstance(attribute_evidence, list)
                or not attribute_evidence
                or len(attribute_evidence) != len(set(attribute_evidence))
                or not set(attribute_evidence) <= valid_frames
            ):
                raise EnsembleError(
                    f"{detector_id}: {local_id}.attributes[{attribute_index}] "
                    "has invalid evidence frame IDs"
                )
        locators = entity.get("coarse_locators")
        if not isinstance(locators, list) or not locators:
            raise EnsembleError(f"{detector_id}: coarse_locators must be nonempty")
        for locator in locators:
            if (
                not isinstance(locator, Mapping)
                or locator.get("frame_id") not in valid_frames
                or not isinstance(locator.get("description"), str)
                or not locator["description"].strip()
            ):
                raise EnsembleError(f"{detector_id}: invalid coarse locator")
        _validate_frame_presence(
            entity.get("frame_presence"),
            owner=f"{detector_id}: {local_id}",
            valid_frame_ids=valid_frame_ids,
            require_visible=True,
            require_bbox=True,
        )
    return _validate_detector_coverage_audit(
        ledger.get("coverage_audit"),
        detector_id=detector_id,
        valid_frame_ids=valid_frame_ids,
        valid_local_ids=local_ids,
    )


def anonymize_proposals(
    detector_ledgers: Sequence[Mapping[str, Any]],
    *,
    shot_id: str,
    seed: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    records: List[Tuple[Dict[str, Any], Dict[str, Any], str]] = []
    for ledger in detector_ledgers:
        panel_id = ledger["detector_id"]
        for entity in ledger["entities"]:
            proposal = {
                key: entity[key]
                for key in (
                    "proposed_name",
                    "canonical_head",
                    "entity_type",
                    "granularity",
                    "attributes",
                    "evidence_frame_ids",
                    "coarse_locators",
                    "frame_presence",
                    "uncertainty_flags",
                )
            }
            source = {
                "source_kind": ledger["source_kind"],
                "source": ledger["detector_id"],
                "local_id": entity["local_id"],
            }
            records.append((proposal, source, panel_id))
    random.Random(seed).shuffle(records)
    proposals: List[Dict[str, Any]] = []
    mappings: List[Dict[str, Any]] = []
    panel_members: Dict[str, List[str]] = {
        ledger["detector_id"]: [] for ledger in detector_ledgers
    }
    for index, (proposal, source, panel_id) in enumerate(records, start=1):
        anonymous_id = f"p{index:04d}"
        proposals.append({"anonymous_proposal_id": anonymous_id, **proposal})
        mappings.append({"anonymous_proposal_id": anonymous_id, **source})
        panel_members[panel_id].append(anonymous_id)
    detector_panels = [
        {
            "panel_id": ledger["detector_id"],
            "anonymous_proposal_ids": panel_members[ledger["detector_id"]],
        }
        for ledger in detector_ledgers
    ]
    return (
        {
            "protocol_version": PROTOCOL_VERSION,
            "shot_id": shot_id,
            "shuffle_seed": seed,
            "proposals": proposals,
            "detector_panels": detector_panels,
        },
        {
            "protocol_version": PROTOCOL_VERSION,
            "shot_id": shot_id,
            "mappings": mappings,
        },
    )


def build_box_redundancy_challenges(
    anonymized_view: Mapping[str, Any], source_map: Mapping[str, Any]
) -> List[Dict[str, Any]]:
    """Flag within-detector box trajectories that another track explains.

    The result is deliberately review-only. Codex boxes are approximate, so this
    helper never removes or merges a proposal and never compares detector sources.
    """
    source_by_proposal = {
        item["anonymous_proposal_id"]: item["source"]
        for item in source_map["mappings"]
    }
    proposals = {
        item["anonymous_proposal_id"]: item
        for item in anonymized_view["proposals"]
    }
    proposal_ids_by_source: Dict[str, List[str]] = {}
    for proposal_id in proposals:
        source = source_by_proposal[proposal_id]
        proposal_ids_by_source.setdefault(source, []).append(proposal_id)

    boxes_by_proposal: Dict[str, Dict[int, List[float]]] = {}
    for proposal_id, proposal in proposals.items():
        visible_boxes = {}
        for presence in proposal.get("frame_presence", []):
            bbox = presence.get("bbox_xyxy_normalized")
            if presence.get("status") == "visible" and _is_valid_normalized_bbox(
                bbox
            ):
                visible_boxes[presence["frame_id"]] = [float(value) for value in bbox]
        boxes_by_proposal[proposal_id] = visible_boxes

    challenges: List[Dict[str, Any]] = []
    for source in sorted(proposal_ids_by_source):
        source_proposal_ids = sorted(proposal_ids_by_source[source])
        for target_id in source_proposal_ids:
            target_boxes = boxes_by_proposal[target_id]
            visible_frame_count = len(target_boxes)
            if visible_frame_count < BOX_REDUNDANCY_MIN_VISIBLE_FRAMES:
                continue
            frame_coverage = []
            for frame_id, target_box in sorted(target_boxes.items()):
                best_cover_id = None
                best_iou = 0.0
                for cover_id in source_proposal_ids:
                    if cover_id == target_id:
                        continue
                    cover_box = boxes_by_proposal[cover_id].get(frame_id)
                    if cover_box is None:
                        continue
                    overlap = _bbox_iou(target_box, cover_box)
                    if overlap > best_iou or (
                        overlap == best_iou
                        and best_cover_id is not None
                        and cover_id < best_cover_id
                    ):
                        best_cover_id = cover_id
                        best_iou = overlap
                if (
                    best_cover_id is not None
                    and best_iou >= BOX_REDUNDANCY_IOU_THRESHOLD
                ):
                    frame_coverage.append(
                        {
                            "frame_id": frame_id,
                            "covering_proposal_id": best_cover_id,
                            "iou": round(best_iou, 6),
                        }
                    )
            coverage_ratio = len(frame_coverage) / visible_frame_count
            if coverage_ratio < BOX_REDUNDANCY_COVERAGE_THRESHOLD:
                continue
            covering_ids = sorted(
                {item["covering_proposal_id"] for item in frame_coverage}
            )
            challenges.append(
                {
                    "target_proposal_id": target_id,
                    "pattern": (
                        "single_track_duplicate"
                        if len(covering_ids) == 1
                        else "track_switch_candidate"
                    ),
                    "visible_frame_count": visible_frame_count,
                    "covered_frame_count": len(frame_coverage),
                    "coverage_ratio": round(coverage_ratio, 6),
                    "spatial_match_metric": "tight_box_iou_not_containment",
                    "iou_threshold": BOX_REDUNDANCY_IOU_THRESHOLD,
                    "coverage_threshold": BOX_REDUNDANCY_COVERAGE_THRESHOLD,
                    "covering_proposal_ids": covering_ids,
                    "frame_coverage": frame_coverage,
                    "effect": "mandatory_review_no_automatic_delete",
                }
            )
    switch_covers = {
        challenge["target_proposal_id"]: set(challenge["covering_proposal_ids"])
        for challenge in challenges
        if challenge["pattern"] == "track_switch_candidate"
    }
    filtered = []
    for challenge in challenges:
        covering_ids = challenge["covering_proposal_ids"]
        if (
            challenge["pattern"] == "single_track_duplicate"
            and len(covering_ids) == 1
            and covering_ids[0] in switch_covers
            and challenge["target_proposal_id"] in switch_covers[covering_ids[0]]
        ):
            # Do not make a coherent component track look redundant merely because
            # the incoherent switch candidate copied it during one time segment.
            continue
        filtered.append(challenge)
    return sorted(filtered, key=lambda item: item["target_proposal_id"])


def validate_decisions(
    decisions: Mapping[str, Any],
    *,
    shot_id: str,
    anonymous_ids: Sequence[str],
    valid_frame_ids: Sequence[int],
) -> None:
    if decisions.get("protocol_version") != PROTOCOL_VERSION:
        raise EnsembleError("Adjudicator returned the wrong protocol_version")
    if decisions.get("shot_id") != shot_id:
        raise EnsembleError("Adjudicator returned the wrong shot_id")
    clusters = decisions.get("clusters")
    if not isinstance(clusters, list):
        raise EnsembleError("Adjudicator clusters must be an array")
    expected = set(anonymous_ids)
    seen: List[str] = []
    cluster_ids = set()
    valid_frames = set(valid_frame_ids)
    for cluster in clusters:
        if not isinstance(cluster, Mapping):
            raise EnsembleError("Adjudicator cluster must be an object")
        cluster_id = cluster.get("cluster_id")
        if (
            not isinstance(cluster_id, str)
            or not cluster_id
            or cluster_id in cluster_ids
        ):
            raise EnsembleError("Adjudicator cluster IDs must be unique")
        cluster_ids.add(cluster_id)
        members = cluster.get("anonymous_proposal_ids")
        if (
            not isinstance(members, list)
            or not members
            or len(members) != len(set(members))
        ):
            raise EnsembleError(f"{cluster_id}: invalid anonymous proposal IDs")
        seen.extend(members)
        decision = cluster.get("decision")
        final_entity = cluster.get("final_entity")
        evidence = cluster.get("adjudicator_evidence")
        if not isinstance(evidence, list):
            raise EnsembleError(f"{cluster_id}: evidence must be an array")
        for item in evidence:
            if (
                not isinstance(item, Mapping)
                or item.get("frame_id") not in valid_frames
            ):
                raise EnsembleError(f"{cluster_id}: invalid adjudicator evidence")
        _validate_frame_presence(
            cluster.get("frame_presence"),
            owner=cluster_id,
            valid_frame_ids=valid_frame_ids,
            require_visible=decision == "accept",
        )
        if decision == "accept":
            if (
                not evidence
                or cluster.get("identity_status") != "resolved"
                or not isinstance(final_entity, Mapping)
            ):
                raise EnsembleError(
                    f"{cluster_id}: accepted entity lacks required visual checks"
                )
            entity_frames = final_entity.get("evidence_frame_ids")
            if (
                not isinstance(entity_frames, list)
                or not entity_frames
                or not set(entity_frames) <= valid_frames
            ):
                raise EnsembleError(f"{cluster_id}: invalid final entity evidence")
        elif decision in {"reject", "abstain"}:
            if final_entity is not None:
                raise EnsembleError(
                    f"{cluster_id}: non-accepted cluster must have null final_entity"
                )
        else:
            raise EnsembleError(f"{cluster_id}: invalid decision {decision!r}")
    if len(seen) != len(set(seen)):
        raise EnsembleError("An anonymous proposal belongs to multiple clusters")
    if set(seen) != expected:
        missing = sorted(expected - set(seen))
        unknown = sorted(set(seen) - expected)
        raise EnsembleError(
            f"Adjudicator proposal accounting failed; missing={missing}, unknown={unknown}"
        )


def proposal_accounting_diagnostics(
    decisions: Mapping[str, Any], anonymous_ids: Sequence[str]
) -> Dict[str, Any]:
    owners: Dict[str, List[str]] = {}
    clusters = decisions.get("clusters", [])
    if isinstance(clusters, list):
        for cluster in clusters:
            if not isinstance(cluster, Mapping):
                continue
            cluster_id = str(cluster.get("cluster_id", "<invalid_cluster>"))
            proposal_ids = cluster.get("anonymous_proposal_ids", [])
            if not isinstance(proposal_ids, list):
                continue
            for proposal_id in proposal_ids:
                if isinstance(proposal_id, str):
                    owners.setdefault(proposal_id, []).append(cluster_id)
    expected = set(anonymous_ids)
    observed = set(owners)
    return {
        "duplicate_proposal_owners": {
            proposal_id: cluster_ids
            for proposal_id, cluster_ids in sorted(owners.items())
            if len(cluster_ids) > 1
        },
        "missing_proposal_ids": sorted(expected - observed),
        "unknown_proposal_ids": sorted(observed - expected),
        "expected_unique_proposal_count": len(expected),
        "observed_unique_proposal_count": len(observed),
    }


def validate_deferred_partition_lineage(
    initial_decisions: Mapping[str, Any],
    revised_decisions: Mapping[str, Any],
) -> None:
    """Keep graph-partition alternatives intact across identity revision."""
    revised_owner: Dict[str, Mapping[str, Any]] = {}
    for cluster in revised_decisions["clusters"]:
        for proposal_id in cluster["anonymous_proposal_ids"]:
            revised_owner[proposal_id] = cluster
    for initial in initial_decisions["clusters"]:
        flags = set(initial.get("uncertainty_flags", []))
        deferred_flags = flags & {
            "group_member_conflict",
            "possible_compact_assembly_partition",
        }
        if not deferred_flags:
            continue
        owners = {
            revised_owner[proposal_id]["cluster_id"]
            for proposal_id in initial["anonymous_proposal_ids"]
        }
        if len(owners) != 1:
            raise EnsembleError(
                f"Deferred partition cluster {initial['cluster_id']} was split "
                "during identity revision"
            )
        revised = revised_owner[initial["anonymous_proposal_ids"][0]]
        if "group_member_conflict" in deferred_flags:
            if revised["decision"] != "reject" or "group_member_conflict" not in set(
                revised.get("uncertainty_flags", [])
            ):
                raise EnsembleError(
                    f"Deferred group/member alternative {initial['cluster_id']} "
                    "was not preserved as a rejected partition alternative"
                )
        if (
            "possible_compact_assembly_partition" in deferred_flags
            and revised["decision"] == "accept"
            and "possible_compact_assembly_partition"
            not in set(revised.get("uncertainty_flags", []))
        ):
            raise EnsembleError(
                f"Accepted compact-assembly flag from {initial['cluster_id']} "
                "was lost during identity revision"
            )


def validate_prompt_bound_matches(
    result: Mapping[str, Any],
    *,
    shot_id: str,
    accepted_cluster_ids: Sequence[str],
    registry_ids: Sequence[str],
    valid_frame_ids: Sequence[int],
) -> None:
    if result.get("protocol_version") != PROTOCOL_VERSION:
        raise EnsembleError("Prompt-bound matcher returned the wrong protocol_version")
    if result.get("shot_id") != shot_id:
        raise EnsembleError("Prompt-bound matcher returned the wrong shot_id")
    if result.get("matcher_id") != "prompt_bound_matcher":
        raise EnsembleError("Prompt-bound matcher returned the wrong matcher_id")
    matches = result.get("matches")
    if not isinstance(matches, list):
        raise EnsembleError("Prompt-bound matcher matches must be an array")
    expected = set(accepted_cluster_ids)
    seen = [item.get("cluster_id") for item in matches if isinstance(item, Mapping)]
    if len(seen) != len(matches) or len(seen) != len(set(seen)) or set(seen) != expected:
        raise EnsembleError(
            "Prompt-bound matcher must cover every accepted inventory cluster exactly once"
        )
    known_registry_ids = set(registry_ids)
    valid_frames = set(valid_frame_ids)
    for item in matches:
        cluster_id = item["cluster_id"]
        status = item.get("status")
        matched = item.get("matched_registry_ids")
        evidence = item.get("evidence_frame_ids")
        if not isinstance(matched, list) or len(matched) != len(set(matched)):
            raise EnsembleError(f"{cluster_id}: invalid matched_registry_ids")
        if not set(matched) <= known_registry_ids:
            raise EnsembleError(f"{cluster_id}: matcher cited an unknown registry ID")
        if status == "bound" and len(matched) != 1:
            raise EnsembleError(f"{cluster_id}: bound requires exactly one registry ID")
        if status == "unbound" and matched:
            raise EnsembleError(f"{cluster_id}: unbound cannot cite a registry ID")
        if status == "ambiguous" and not matched:
            raise EnsembleError(f"{cluster_id}: ambiguous requires a plausible registry ID")
        if status not in {"bound", "unbound", "ambiguous"}:
            raise EnsembleError(f"{cluster_id}: invalid prompt-bound status")
        if (
            not isinstance(evidence, list)
            or not evidence
            or len(evidence) != len(set(evidence))
            or not set(evidence) <= valid_frames
        ):
            raise EnsembleError(f"{cluster_id}: invalid matcher evidence frames")


def _detector_support_by_cluster(
    decisions: Mapping[str, Any], source_map: Mapping[str, Any]
) -> Dict[str, int]:
    sources = {
        item["anonymous_proposal_id"]: item["source"] for item in source_map["mappings"]
    }
    return {
        cluster["cluster_id"]: len(
            {sources[proposal_id] for proposal_id in cluster["anonymous_proposal_ids"]}
        )
        for cluster in decisions["clusters"]
    }


def _identity_tokens(value: str) -> set[str]:
    tokens = set()
    for raw_token in re.findall(r"[a-z0-9]+", value.casefold()):
        token = IDENTITY_TOKEN_ALIASES.get(raw_token, raw_token)
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        if len(token) >= 3 and token not in IDENTITY_LOCATOR_STOPWORDS:
            tokens.add(token)
    return tokens


def _initial_declared_identity_pairs(decisions: Mapping[str, Any]):
    """Project validated initial declarations to neutral, complete-scope questions.

    Schema/base/physical validation precedes this handoff. Missing comparison
    fields remain compatible with legacy inputs; malformed declared endpoints
    never create a new scope or silently disappear. No verdict/evidence is copied.
    """
    clusters = {row["cluster_id"]: row for row in decisions["clusters"]}
    if len(clusters) != len(decisions["clusters"]):
        raise EnsembleError("Duplicate initial comparison owner")
    by_pair = {}
    for index, cluster in enumerate(decisions["clusters"]):
        own = cluster["cluster_id"]
        comparisons = cluster.get("identity_comparisons", [])
        if not isinstance(comparisons, list):
            raise EnsembleError("Initial identity comparisons must be an array")
        seen = set()
        for comparison_index, comparison in enumerate(comparisons):
            other = comparison.get("other_cluster_id") if isinstance(comparison, Mapping) else None
            if (not isinstance(other, str) or other not in clusters or other == own or other in seen):
                raise EnsembleError("Invalid, absent, self or duplicate initial comparison endpoint")
            seen.add(other)
            if (comparison.get("judgment") not in {"confirmed_same_scope", "confirmed_distinct", "unresolved"}
                    or comparison.get("scope_relation") not in {"comparable", "whole_part", "group_member", "unresolved"}
                    or (comparison["judgment"] != "unresolved" and comparison["scope_relation"] != "comparable")):
                raise EnsembleError("Invalid initial comparison judgment or relation")
            left, right = sorted((own, other))
            key = (left, right)
            by_pair.setdefault(key, []).append(
                f"/clusters/{index}/identity_comparisons/{comparison_index}")
    pairs, records = [], []
    for (left, right), pointers in sorted(by_pair.items()):
        scopes = [clusters[key]["anonymous_proposal_ids"] for key in (left, right)]
        if (any(not isinstance(scope, list) or not scope or any(not isinstance(x, str) or not x for x in scope)
                or len(scope) != len(set(scope)) for scope in scopes) or set(scopes[0]) & set(scopes[1])):
            raise EnsembleError("Initial comparison requires complete disjoint proposal owners")
        pairs.append({"cluster_id_a": left, "cluster_id_b": right,
                      "canonical_name_a": clusters[left]["canonical_name"],
                      "canonical_name_b": clusters[right]["canonical_name"],
                      "trigger_bases": ["physical_scope_comparison"],
                      "effect": "review_only_no_automatic_merge"})
        records.append({"cluster_id_a": left, "cluster_id_b": right,
                        "anonymous_proposal_ids_a": list(scopes[0]), "anonymous_proposal_ids_b": list(scopes[1]),
                        "source_comparison_json_pointers": pointers})
    return pairs, records


def audit_initial_declared_identity_handoff(decisions, verification_view, *, verifier_ids=VERIFIER_IDS):
    """Check the actual compact input before either paid verifier is invoked."""
    declared, records = _initial_declared_identity_pairs(decisions)
    if len(verifier_ids) != 2 or len(set(verifier_ids)) != 2:
        raise EnsembleError("Initial comparison handoff requires two independent verifier IDs")
    targets = verification_view["targets"]
    target_map = {row["cluster_id"]: row for row in targets}
    if len(target_map) != len(targets):
        raise EnsembleError("Duplicate verifier target in initial comparison handoff")
    pairs = verification_view["identity_challenge_pairs"]
    pair_keys = [frozenset((row["cluster_id_a"], row["cluster_id_b"])) for row in pairs]
    if len(pair_keys) != len(set(pair_keys)):
        raise EnsembleError("Duplicate verifier pair in initial comparison handoff")
    required_partners = {}
    for row in records:
        left, right = row["cluster_id_a"], row["cluster_id_b"]
        if frozenset((left, right)) not in pair_keys:
            raise EnsembleError("Declared initial pair was omitted from verifier questions")
        for key, scope, other in ((left, row["anonymous_proposal_ids_a"], right),
                                  (right, row["anonymous_proposal_ids_b"], left)):
            if key not in target_map or [p["anonymous_proposal_id"] for p in target_map[key]["proposals"]] != scope:
                raise EnsembleError("Declared initial pair lost a complete verifier endpoint scope")
            required_partners.setdefault(key, set()).add(other)
    return {"policy_version": INITIAL_DECLARED_IDENTITY_HANDOFF_VERSION,
            "declared_pair_count": len(declared),
            "source_comparison_count": sum(len(row["source_comparison_json_pointers"]) for row in records),
            "records": records, "required_verifier_ids": list(verifier_ids),
            "required_partners_by_cluster": {key: sorted(value) for key, value in sorted(required_partners.items())},
            "all_declared_pairs_supplied": True, "complete_endpoint_scopes_supplied": True,
            "source_assertions_used_as_proof": False, "decisions_modified": False,
            "supplied_to_any_model": False, "pixel_truth_verified": False}


def build_identity_challenge_pairs(
    decisions: Mapping[str, Any], anonymized_view: Mapping[str, Any], *,
    include_initial_comparisons: bool = False,
) -> List[Dict[str, Any]]:
    """Find review-only same-instance risks without merging any cluster."""
    proposals = {
        item["anonymous_proposal_id"]: item for item in anonymized_view["proposals"]
    }
    signatures = []
    for cluster in decisions["clusters"]:
        if cluster["decision"] == "reject":
            continue
        members = [proposals[item] for item in cluster["anonymous_proposal_ids"]]
        canonical_tokens = _identity_tokens(str(cluster.get("canonical_name", "")))
        head_tokens = set()
        locator_tokens = set()
        frame_ids = set()
        uncertain = bool(cluster.get("uncertainty_flags")) or (
            cluster.get("identity_status") == "ambiguous"
        )
        for proposal in members:
            head_tokens.update(
                _identity_tokens(str(proposal.get("canonical_head", "")))
            )
            uncertain = uncertain or bool(proposal.get("uncertainty_flags"))
            for locator in proposal.get("coarse_locators", []):
                frame_ids.add(locator["frame_id"])
                locator_tokens.update(_identity_tokens(str(locator["description"])))
        signatures.append(
            {
                "cluster_id": cluster["cluster_id"],
                "canonical_name": cluster["canonical_name"],
                "canonical_tokens": canonical_tokens,
                "head_tokens": head_tokens,
                "locator_tokens": locator_tokens,
                "frame_ids": frame_ids,
                "uncertain": uncertain,
            }
        )

    pairs: List[Dict[str, Any]] = []
    for index, left in enumerate(signatures):
        for right in signatures[index + 1 :]:
            bases = []
            if left["canonical_tokens"] and (
                left["canonical_tokens"] == right["canonical_tokens"]
            ):
                bases.append("same_canonical_name")
            elif left["canonical_tokens"] and right["canonical_tokens"] and (
                left["canonical_tokens"] < right["canonical_tokens"]
                or right["canonical_tokens"] < left["canonical_tokens"]
            ):
                bases.append("canonical_name_containment")
            if left["head_tokens"] & right["head_tokens"]:
                bases.append("proposal_head_overlap")
            shared_frames = sorted(left["frame_ids"] & right["frame_ids"])
            shared_locator_tokens = sorted(
                left["locator_tokens"] & right["locator_tokens"]
            )
            locator_union = left["locator_tokens"] | right["locator_tokens"]
            locator_similarity = (
                len(shared_locator_tokens) / len(locator_union)
                if locator_union
                else 0.0
            )
            if (
                shared_frames
                and len(shared_locator_tokens) >= 2
                and locator_similarity >= IDENTITY_LOCATOR_JACCARD_THRESHOLD
                and (left["uncertain"] or right["uncertain"])
            ):
                bases.append("coarse_locator_overlap")
            if not bases:
                continue
            pairs.append(
                {
                    "cluster_id_a": left["cluster_id"],
                    "cluster_id_b": right["cluster_id"],
                    "canonical_name_a": left["canonical_name"],
                    "canonical_name_b": right["canonical_name"],
                    "trigger_bases": sorted(set(bases)),
                    "shared_frame_ids": shared_frames,
                    "shared_locator_tokens": shared_locator_tokens,
                    "coarse_locator_jaccard": round(locator_similarity, 6),
                    "effect": "review_only_no_automatic_merge",
                }
            )

    signature_by_cluster = {item["cluster_id"]: item for item in signatures}
    cluster_by_proposal = {
        proposal_id: cluster["cluster_id"]
        for cluster in decisions["clusters"]
        for proposal_id in cluster["anonymous_proposal_ids"]
    }
    pair_by_clusters = {
        frozenset((pair["cluster_id_a"], pair["cluster_id_b"])): pair
        for pair in pairs
    }
    for challenge in anonymized_view.get("box_redundancy_challenges", []):
        target_proposal_id = challenge.get("target_proposal_id")
        target_cluster_id = cluster_by_proposal.get(target_proposal_id)
        if target_cluster_id not in signature_by_cluster:
            continue
        covering_proposal_ids = challenge.get("covering_proposal_ids", [])
        cover_ids_by_cluster: Dict[str, List[str]] = {}
        for proposal_id in covering_proposal_ids:
            cover_cluster_id = cluster_by_proposal.get(proposal_id)
            if (
                cover_cluster_id in signature_by_cluster
                and cover_cluster_id != target_cluster_id
            ):
                cover_ids_by_cluster.setdefault(cover_cluster_id, []).append(proposal_id)
        for cover_cluster_id, cover_proposal_ids in sorted(
            cover_ids_by_cluster.items()
        ):
            left_id, right_id = sorted((target_cluster_id, cover_cluster_id))
            key = frozenset((left_id, right_id))
            pair = pair_by_clusters.get(key)
            if pair is None:
                left = signature_by_cluster[left_id]
                right = signature_by_cluster[right_id]
                pair = {
                    "cluster_id_a": left_id,
                    "cluster_id_b": right_id,
                    "canonical_name_a": left["canonical_name"],
                    "canonical_name_b": right["canonical_name"],
                    "trigger_bases": [],
                    "shared_frame_ids": [],
                    "shared_locator_tokens": [],
                    "coarse_locator_jaccard": 0.0,
                    "effect": "review_only_no_automatic_merge",
                }
                pairs.append(pair)
                pair_by_clusters[key] = pair
            if "detector_box_trajectory_coverage" not in pair["trigger_bases"]:
                pair["trigger_bases"].append("detector_box_trajectory_coverage")
                pair["trigger_bases"].sort()
            cover_proposal_id_set = set(cover_proposal_ids)
            relevant_frames = [
                item
                for item in challenge.get("frame_coverage", [])
                if item.get("covering_proposal_id") in cover_proposal_id_set
            ]
            pair["shared_frame_ids"] = sorted(
                set(pair["shared_frame_ids"])
                | {item["frame_id"] for item in relevant_frames}
            )
            pair.setdefault("box_redundancy_challenges", []).append(
                {
                    **challenge,
                    "covering_proposal_ids": sorted(cover_proposal_id_set),
                    "frame_coverage": relevant_frames,
                }
            )
    if include_initial_comparisons:
        for declared in _initial_declared_identity_pairs(decisions)[0]:
            key = frozenset((declared["cluster_id_a"], declared["cluster_id_b"]))
            if key not in pair_by_clusters:
                pairs.append(declared)
                pair_by_clusters[key] = declared
            elif "physical_scope_comparison" not in pair_by_clusters[key]["trigger_bases"]:
                pair_by_clusters[key]["trigger_bases"].append("physical_scope_comparison")
                pair_by_clusters[key]["trigger_bases"].sort()
    return sorted(pairs, key=lambda item: (item["cluster_id_a"], item["cluster_id_b"]))


def build_intra_cluster_divergent_footprint_challenges(
    decisions: Mapping[str, Any], anonymized_view: Mapping[str, Any]
) -> List[Dict[str, Any]]:
    """Flag persistent within-cluster spatial divergence for review only.

    This trigger deliberately uses neither source labels nor detector counts. Boxes
    are fallible proposal-local position hints, so the result cannot split a cluster.
    """
    proposals = {
        item["anonymous_proposal_id"]: item
        for item in anonymized_view.get("proposals", [])
    }
    challenges: List[Dict[str, Any]] = []
    for cluster in decisions.get("clusters", []):
        if cluster.get("decision") == "reject":
            continue
        proposal_ids = sorted(cluster.get("anonymous_proposal_ids", []))
        if len(proposal_ids) < 2 or not set(proposal_ids) <= set(proposals):
            continue
        divergent_pairs: List[Dict[str, Any]] = []
        for left_index, left_id in enumerate(proposal_ids):
            left_presence = {
                item["frame_id"]: item["bbox_xyxy_normalized"]
                for item in proposals[left_id].get("frame_presence", [])
                if item.get("status") == "visible"
                and _is_valid_normalized_bbox(item.get("bbox_xyxy_normalized"))
            }
            for right_id in proposal_ids[left_index + 1 :]:
                right_presence = {
                    item["frame_id"]: item["bbox_xyxy_normalized"]
                    for item in proposals[right_id].get("frame_presence", [])
                    if item.get("status") == "visible"
                    and _is_valid_normalized_bbox(item.get("bbox_xyxy_normalized"))
                }
                covisible_frames = sorted(set(left_presence) & set(right_presence))
                if (
                    len(covisible_frames)
                    < INTRA_CLUSTER_DIVERGENCE_MIN_COVISIBLE_FRAMES
                ):
                    continue
                divergent_frame_evidence = []
                for frame_id in covisible_frames:
                    left_box = left_presence[frame_id]
                    right_box = right_presence[frame_id]
                    iou = _bbox_iou(left_box, right_box)
                    smaller_box_coverage = _bbox_intersection_over_smaller(
                        left_box, right_box
                    )
                    if (
                        iou <= INTRA_CLUSTER_DIVERGENCE_MAX_IOU
                        and smaller_box_coverage
                        <= INTRA_CLUSTER_DIVERGENCE_MAX_SMALLER_BOX_COVERAGE
                    ):
                        divergent_frame_evidence.append(
                            {
                                "frame_id": frame_id,
                                "bbox_a_xyxy_normalized": list(left_box),
                                "bbox_b_xyxy_normalized": list(right_box),
                                "iou": round(iou, 6),
                                "smaller_box_coverage": round(
                                    smaller_box_coverage, 6
                                ),
                            }
                        )
                divergence_ratio = len(divergent_frame_evidence) / len(
                    covisible_frames
                )
                if (
                    divergence_ratio
                    < INTRA_CLUSTER_DIVERGENCE_COVERAGE_THRESHOLD
                ):
                    continue
                divergent_pairs.append(
                    {
                        "proposal_id_a": left_id,
                        "proposal_id_b": right_id,
                        "covisible_frame_count": len(covisible_frames),
                        "divergent_frame_count": len(divergent_frame_evidence),
                        "divergence_ratio": round(divergence_ratio, 6),
                        "frame_evidence": divergent_frame_evidence,
                    }
                )
        if divergent_pairs:
            challenges.append(
                {
                    "cluster_id": cluster["cluster_id"],
                    "cluster_proposal_ids": proposal_ids,
                    "divergent_proposal_pairs": divergent_pairs,
                    "thresholds": {
                        "maximum_iou": INTRA_CLUSTER_DIVERGENCE_MAX_IOU,
                        "maximum_smaller_box_coverage": (
                            INTRA_CLUSTER_DIVERGENCE_MAX_SMALLER_BOX_COVERAGE
                        ),
                        "minimum_covisible_frames": (
                            INTRA_CLUSTER_DIVERGENCE_MIN_COVISIBLE_FRAMES
                        ),
                        "minimum_divergence_ratio": (
                            INTRA_CLUSTER_DIVERGENCE_COVERAGE_THRESHOLD
                        ),
                    },
                    "source_or_detector_count_used": False,
                    "effect": "mandatory_review_no_automatic_split",
                }
            )
    return sorted(challenges, key=lambda item: item["cluster_id"])


def select_verification_targets(
    decisions: Mapping[str, Any],
    source_map: Mapping[str, Any],
    anonymized_view: Optional[Mapping[str, Any]] = None,
    intra_cluster_split_challenges: Sequence[Mapping[str, Any]] = (),
    *, include_initial_comparisons: bool = False,
) -> Tuple[List[str], Dict[str, List[str]]]:
    support = _detector_support_by_cluster(decisions, source_map)
    deferred_partition_ids = {
        cluster["cluster_id"]
        for cluster in decisions["clusters"]
        if cluster["decision"] == "reject"
        and cluster["identity_status"] == "resolved"
        and set(cluster.get("uncertainty_flags", [])) == {"group_member_conflict"}
    }
    reasons: Dict[str, List[str]] = {}
    for cluster in decisions["clusters"]:
        if cluster["cluster_id"] in deferred_partition_ids:
            continue
        cluster_reasons: List[str] = []
        if support[cluster["cluster_id"]] <= 2:
            cluster_reasons.append("detector_support_at_most_2")
        if cluster["decision"] == "abstain":
            cluster_reasons.append("initial_adjudicator_abstained")
        if cluster["identity_status"] == "ambiguous":
            cluster_reasons.append("identity_ambiguous")
        if cluster.get("uncertainty_flags"):
            cluster_reasons.append("uncertainty_flagged")
        if cluster_reasons:
            reasons[cluster["cluster_id"]] = cluster_reasons

    named_clusters = []
    for cluster in decisions["clusters"]:
        if cluster["cluster_id"] in deferred_partition_ids:
            continue
        name = str(cluster.get("canonical_name", "")).casefold().replace("-", " ")
        tokens = {token for token in name.split() if token}
        if tokens:
            named_clusters.append((cluster["cluster_id"], tokens))
    component_conflicts = set()
    for index, (left_id, left_tokens) in enumerate(named_clusters):
        for right_id, right_tokens in named_clusters[index + 1 :]:
            if left_tokens < right_tokens or right_tokens < left_tokens:
                component_conflicts.update((left_id, right_id))
    for cluster_id in sorted(component_conflicts):
        reasons.setdefault(cluster_id, []).append(
            "possible_functional_whole_component_name_overlap"
        )
    if anonymized_view is not None:
        for pair in build_identity_challenge_pairs(decisions, anonymized_view):
            if deferred_partition_ids & {
                pair["cluster_id_a"],
                pair["cluster_id_b"],
            }:
                continue
            for cluster_id in (pair["cluster_id_a"], pair["cluster_id_b"]):
                cluster_reasons = reasons.setdefault(cluster_id, [])
                reason = "possible_same_instance_pair"
                if reason not in cluster_reasons:
                    cluster_reasons.append(reason)
    for challenge in intra_cluster_split_challenges:
        cluster_id = challenge.get("cluster_id")
        if cluster_id in deferred_partition_ids:
            continue
        if cluster_id not in support:
            raise EnsembleError(
                "Intra-cluster divergent-footprint challenge cites an unknown cluster"
            )
        cluster_reasons = reasons.setdefault(cluster_id, [])
        reason = "persistent_intra_cluster_divergent_footprints"
        if reason not in cluster_reasons:
            cluster_reasons.append(reason)
    if include_initial_comparisons:
        # Explicit comparisons survive heuristic/deferred target omission. This
        # routes rejected endpoints for review without changing their decisions.
        for pair in _initial_declared_identity_pairs(decisions)[0]:
            for cluster_id in (pair["cluster_id_a"], pair["cluster_id_b"]):
                cluster_reasons = reasons.setdefault(cluster_id, [])
                if "initial_declared_identity_comparison" not in cluster_reasons:
                    cluster_reasons.append("initial_declared_identity_comparison")
    return sorted(reasons), reasons


def add_pending_identity_review_obligations(
    *, decisions: Mapping[str, Any], pending_comparisons: Sequence[Mapping[str, Any]],
    identity_challenge_pairs: Sequence[Mapping[str, Any]], target_ids: Sequence[str],
    target_reasons: Mapping[str, Sequence[str]],
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, List[str]]]:
    """Route both complete scopes to review without disclosing a prior verdict."""
    clusters = {c["cluster_id"]: c for c in decisions["clusters"]}
    pairs = copy.deepcopy(list(identity_challenge_pairs))
    reasons = {key: list(value) for key, value in target_reasons.items()}
    targets = set(target_ids)
    pair_index = {frozenset((p["cluster_id_a"], p["cluster_id_b"])): p for p in pairs}
    for item in pending_comparisons:
        own, other = item["own_cluster_id"], item["other_cluster_id"]
        if (own == other or own not in clusters or other not in clusters
                or set(item["own_anonymous_proposal_ids"]) != set(clusters[own]["anonymous_proposal_ids"])
                or set(item["other_anonymous_proposal_ids"]) != set(clusters[other]["anonymous_proposal_ids"])):
            raise EnsembleError("Pending identity obligation changed its complete initial scopes")
        pair_key = frozenset((own, other))
        if pair_key not in pair_index:
            left, right = sorted(pair_key)
            pair = {
                "cluster_id_a": left, "cluster_id_b": right,
                "canonical_name_a": clusters[left]["canonical_name"],
                "canonical_name_b": clusters[right]["canonical_name"],
                "trigger_bases": ["physical_scope_comparison"],
                "effect": "review_only_no_automatic_merge",
            }
            pairs.append(pair)
            pair_index[pair_key] = pair
        # This reason is private orchestration metadata. Verifier inputs receive
        # only the neutral pair and the original complete proposal views.
        for cluster_id in (own, other):
            targets.add(cluster_id)
            reasons.setdefault(cluster_id, [])
            if "pending_identity_contract_review" not in reasons[cluster_id]:
                reasons[cluster_id].append("pending_identity_contract_review")
    return pairs, sorted(targets), reasons


def add_context_scope_review_obligations(
    *, decisions, review_scope_ids, target_ids, target_reasons,
):
    """Route complete context owners without inventing a pair or a judgment."""
    scopes = {c["cluster_id"] for c in decisions["clusters"]}
    if (not isinstance(review_scope_ids, list)
            or any(not isinstance(item, str) or item not in scopes for item in review_scope_ids)
            or len(review_scope_ids) != len(set(review_scope_ids))):
        raise EnsembleError("Invalid complete initial context review scopes")
    targets, reasons = set(target_ids), copy.deepcopy(target_reasons)
    for cluster_id in review_scope_ids:
        targets.add(cluster_id)
        reasons.setdefault(cluster_id, [])
        if "initial_context_scope_review" not in reasons[cluster_id]:
            reasons[cluster_id].append("initial_context_scope_review")
    return sorted(targets), reasons


def apply_single_detector_consensus_gate(
    decisions: Mapping[str, Any],
    *,
    initial_decisions: Mapping[str, Any],
    source_map: Mapping[str, Any],
    verifier_reports: Sequence[Mapping[str, Any]],
    verification_target_reasons: Mapping[str, Sequence[str]],
    verifier_ids: Sequence[str] = VERIFIER_IDS,
    intra_cluster_split_consensus: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Abstain on one-detector entities without unanimous verifier support."""
    gated = copy.deepcopy(decisions)
    support = _detector_support_by_cluster(gated, source_map)
    initial_proposals = {
        cluster["cluster_id"]: set(cluster["anonymous_proposal_ids"])
        for cluster in initial_decisions["clusters"]
    }
    report_by_verifier = {
        report["verifier_id"]: {
            review["cluster_id"]: review for review in report["reviews"]
        }
        for report in verifier_reports
    }
    exact_split_partitions = {
        item["cluster_id"]: {
            frozenset(group) for group in item["proposal_partition"]
        }
        for item in (intra_cluster_split_consensus or {}).get(
            "exact_consensus_partitions", []
        )
    }
    audit_records: List[Dict[str, Any]] = []
    for cluster in gated["clusters"]:
        cluster_id = cluster["cluster_id"]
        if cluster["decision"] != "accept" or support[cluster_id] != 1:
            continue
        proposal_ids = set(cluster["anonymous_proposal_ids"])
        target_ids = sorted(
            initial_id
            for initial_id, initial_ids in initial_proposals.items()
            if initial_id in verification_target_reasons
            and proposal_ids & initial_ids
        )
        judgments: List[Dict[str, Any]] = []
        unanimous = bool(target_ids)
        for verifier_id in verifier_ids:
            review_summaries: List[Dict[str, Any]] = []
            complete = bool(target_ids)
            for target_id in target_ids:
                review = report_by_verifier.get(verifier_id, {}).get(target_id)
                initial_ids = initial_proposals[target_id]
                overlap = proposal_ids & initial_ids
                if review is None:
                    complete = False
                    continue
                if overlap == initial_ids:
                    confirmed_graph_worthy = (
                        review["existence_judgment"] == "confirmed"
                        and review["salience_judgment"] == "graph_worthy"
                    )
                    confirmation_scope = "complete_initial_target"
                elif overlap and frozenset(overlap) in exact_split_partitions.get(
                    target_id, set()
                ):
                    matching_units = [
                        unit
                        for unit in review.get("proposed_physical_units", [])
                        if set(unit.get("anonymous_proposal_ids", [])) == overlap
                    ]
                    confirmed_graph_worthy = (
                        review.get("intra_cluster_split_judgment")
                        == "split_into_multiple_physical_instances"
                        and len(matching_units) == 1
                        and matching_units[0].get("existence_judgment") == "confirmed"
                        and matching_units[0].get("salience_judgment") == "graph_worthy"
                        and bool(matching_units[0].get("evidence"))
                    )
                    confirmation_scope = "exact_consensus_split_unit"
                else:
                    confirmed_graph_worthy = False
                    confirmation_scope = "partial_target_without_exact_unit_confirmation"
                    complete = False
                review_summaries.append(
                    {
                        "cluster_id": review["cluster_id"],
                        "proposal_ids_confirmed": sorted(overlap),
                        "confirmation_scope": confirmation_scope,
                        "existence_judgment": review["existence_judgment"],
                        "salience_judgment": review["salience_judgment"],
                        "confirmed_graph_worthy": confirmed_graph_worthy,
                    }
                )
            confirmed = complete and all(
                item["confirmed_graph_worthy"] for item in review_summaries
            )
            unanimous = unanimous and confirmed
            judgments.append(
                {
                    "verifier_id": verifier_id,
                    "complete": complete,
                    "confirmed_graph_worthy": confirmed,
                    "reviews": review_summaries,
                }
            )
        if not unanimous:
            cluster["decision"] = "abstain"
            cluster["identity_status"] = "ambiguous"
            cluster["final_entity"] = None
            cluster["decision_reason"] = (
                "Single-detector proposal support did not receive unanimous "
                "independent confirmation of both physical existence and graph "
                "worthiness; retained only in the audit ledger."
            )
            cluster["uncertainty_flags"] = sorted(
                set(cluster["uncertainty_flags"])
                | {"single_detector_consensus_gate_not_unanimous"}
            )
        audit_records.append(
            {
                "cluster_id": cluster_id,
                "detector_support": 1,
                "initial_target_cluster_ids": target_ids,
                "verifier_judgments": judgments,
                "unanimous_confirmed_graph_worthy": unanimous,
                "result": "kept_accept" if unanimous else "changed_to_abstain",
            }
        )
    return gated, {
        "policy": (
            "accepted clusters supported by exactly one detector require every "
            "isolated verifier to confirm existence and graph worthiness"
        ),
        "source_support_selects_entity_directly": False,
        "single_detector_support_triggers_stricter_confirmation": True,
        "split_singleton_requires_exact_unit_level_confirmation": True,
        "records": audit_records,
    }


def _normalized_gate_tokens(value: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


def _generic_identity_placeholder_head(value: str) -> Optional[str]:
    core = re.sub(r"\([^)]*\)", " ", value)
    tokens = _normalized_gate_tokens(core)
    for index, token in enumerate(tokens):
        if index and token in GENERIC_IDENTITY_RELATIONAL_SUFFIXES:
            tokens = tokens[:index]
            break
    if not tokens:
        return None
    head = tokens[-1]
    if head.endswith("ies"):
        singular = head[:-3] + "y"
        if singular in GENERIC_IDENTITY_PLACEHOLDER_HEADS:
            head = singular
    elif head.endswith("s") and head[:-1] in GENERIC_IDENTITY_PLACEHOLDER_HEADS:
        head = head[:-1]
    return head if head in GENERIC_IDENTITY_PLACEHOLDER_HEADS else None


def _matched_identity_uncertainty_flags(flags: Sequence[Any]) -> List[str]:
    matched: List[str] = []
    for value in flags:
        if not isinstance(value, str):
            continue
        tokens = set(_normalized_gate_tokens(value))
        explicit_uncertainty = bool(
            tokens & IDENTITY_UNCERTAINTY_SUBJECTS
            and tokens & IDENTITY_UNCERTAINTY_MARKERS
        )
        alternative_identity = bool(
            tokens & IDENTITY_POSSIBILITY_MARKERS
            and tokens & {"or", "versus"}
        )
        if explicit_uncertainty or alternative_identity:
            matched.append(value)
    return sorted(set(matched), key=lambda item: (item.casefold(), item))


def apply_nonmajority_generic_identity_gate(
    decisions: Mapping[str, Any],
    *,
    initial_decisions: Mapping[str, Any],
    source_map: Mapping[str, Any],
    verifier_reports: Sequence[Mapping[str, Any]],
    verification_target_reasons: Mapping[str, Sequence[str]],
    expected_detector_ids: Sequence[str],
    verifier_ids: Sequence[str] = VERIFIER_IDS,
    intra_cluster_split_consensus: Optional[Mapping[str, Any]] = None,
    support_scope: str = "nonmajority",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Abstain on weakly supported placeholder identities without strong review."""
    if support_scope not in {"nonmajority", "all_support"}:
        raise EnsembleError("Invalid generic identity support scope")
    all_support = support_scope == "all_support"
    detector_roster = tuple(expected_detector_ids)
    if (
        not detector_roster
        or any(not isinstance(item, str) or not item for item in detector_roster)
        or len(detector_roster) != len(set(detector_roster))
    ):
        raise EnsembleError("Nonmajority identity gate requires a unique detector roster")
    required_verifiers = tuple(verifier_ids)
    if (
        not required_verifiers
        or any(not isinstance(item, str) or not item for item in required_verifiers)
        or len(required_verifiers) != len(set(required_verifiers))
    ):
        raise EnsembleError("Nonmajority identity gate requires unique verifier IDs")

    proposal_sources: Dict[str, str] = {}
    for item in source_map.get("mappings", []):
        if item.get("source_kind") != "detector":
            continue
        proposal_id = item.get("anonymous_proposal_id")
        source = item.get("source")
        if not isinstance(proposal_id, str) or not isinstance(source, str):
            raise EnsembleError("Nonmajority identity gate received an invalid source map")
        if source not in detector_roster:
            raise EnsembleError(
                "Nonmajority identity gate source is absent from the expected roster"
            )
        proposal_sources[proposal_id] = source

    gated = copy.deepcopy(decisions)
    initial_proposals = {
        cluster["cluster_id"]: set(cluster["anonymous_proposal_ids"])
        for cluster in initial_decisions["clusters"]
    }
    report_by_verifier = {
        report["verifier_id"]: {
            review["cluster_id"]: review for review in report["reviews"]
        }
        for report in verifier_reports
        if report.get("verifier_id") in set(required_verifiers)
    }
    exact_split_partitions = {
        item["cluster_id"]: {
            frozenset(group) for group in item["proposal_partition"]
        }
        for item in (intra_cluster_split_consensus or {}).get(
            "exact_consensus_partitions", []
        )
    }

    audit_records: List[Dict[str, Any]] = []
    denominator = len(detector_roster)
    for cluster in sorted(gated["clusters"], key=lambda item: item["cluster_id"]):
        if cluster["decision"] != "accept":
            continue
        proposal_ids = set(cluster["anonymous_proposal_ids"])
        if not proposal_ids <= set(proposal_sources):
            raise EnsembleError(
                f"{cluster['cluster_id']}: nonmajority identity gate lacks a detector source"
            )
        detector_support = len(
            {proposal_sources[proposal_id] for proposal_id in proposal_ids}
        )
        nonmajority_support = 2 * detector_support <= denominator
        if not all_support and not nonmajority_support:
            continue

        canonical_head = _generic_identity_placeholder_head(
            str(cluster.get("canonical_name", ""))
        )
        final_entity = cluster.get("final_entity")
        final_name = (
            str(final_entity.get("name", ""))
            if isinstance(final_entity, Mapping)
            else ""
        )
        final_head = _generic_identity_placeholder_head(final_name)
        placeholder_only_identity = (
            canonical_head is not None and final_head is not None
        )
        matched_uncertainty_flags = _matched_identity_uncertainty_flags(
            cluster.get("uncertainty_flags", [])
        )
        identity_or_subtype_uncertain = bool(matched_uncertainty_flags)
        target_ids = sorted(
            initial_id
            for initial_id, initial_ids in initial_proposals.items()
            if initial_id in verification_target_reasons
            and proposal_ids & initial_ids
        )

        verifier_judgments: List[Dict[str, Any]] = []
        for verifier_id in required_verifiers:
            review_summaries: List[Dict[str, Any]] = []
            complete = bool(target_ids)
            for target_id in target_ids:
                review = report_by_verifier.get(verifier_id, {}).get(target_id)
                initial_ids = initial_proposals[target_id]
                overlap = proposal_ids & initial_ids
                evidence_items: Sequence[Mapping[str, Any]] = ()
                independence_items: Sequence[Mapping[str, Any]] = ()
                confirmed_graph_worthy = False
                confirmation_scope = (
                    "partial_target_without_exact_unit_confirmation"
                )
                if review is None:
                    complete = False
                elif overlap == initial_ids:
                    confirmed_graph_worthy = (
                        review.get("existence_judgment") == "confirmed"
                        and review.get("salience_judgment") == "graph_worthy"
                    )
                    confirmation_scope = "complete_initial_target"
                    evidence_items = review.get("evidence", [])
                    independence_items = review.get(
                        "observed_independence_evidence", []
                    )
                elif overlap and frozenset(overlap) in exact_split_partitions.get(
                    target_id, set()
                ):
                    matching_units = [
                        unit
                        for unit in review.get("proposed_physical_units", [])
                        if set(unit.get("anonymous_proposal_ids", [])) == overlap
                    ]
                    if (
                        review.get("intra_cluster_split_judgment")
                        == "split_into_multiple_physical_instances"
                        and len(matching_units) == 1
                    ):
                        unit = matching_units[0]
                        confirmed_graph_worthy = (
                            unit.get("existence_judgment") == "confirmed"
                            and unit.get("salience_judgment") == "graph_worthy"
                            and bool(unit.get("evidence"))
                        )
                        confirmation_scope = "exact_consensus_split_unit"
                        evidence_items = unit.get("evidence", [])
                        unit_id = unit.get("unit_id")
                        independence_items = [
                            item
                            for item in review.get(
                                "pairwise_physical_separation_evidence", []
                            )
                            if unit_id in {item.get("unit_id_a"), item.get("unit_id_b")}
                        ]
                    else:
                        complete = False
                else:
                    complete = False

                evidence_qualities = sorted(
                    {
                        str(item.get("support_quality"))
                        for item in evidence_items
                        if item.get("support_quality") in {"strong", "moderate", "weak"}
                    }
                )
                independence_qualities = sorted(
                    {
                        str(item.get("support_quality"))
                        for item in independence_items
                        if item.get("support_quality") in {"strong", "moderate", "weak"}
                    }
                )
                strong_direct_confirmation = (
                    confirmed_graph_worthy and "strong" in evidence_qualities
                )
                supported_independence_confirmation = (
                    confirmed_graph_worthy
                    and bool({"strong", "moderate"} & set(independence_qualities))
                )
                review_summaries.append(
                    {
                        "cluster_id": target_id,
                        "confirmation_scope": confirmation_scope,
                        "confirmed_graph_worthy": confirmed_graph_worthy,
                        "evidence_support_qualities": evidence_qualities,
                        "independence_support_qualities": independence_qualities,
                        "strong_direct_confirmation": strong_direct_confirmation,
                        "supported_independence_confirmation": (
                            supported_independence_confirmation
                        ),
                    }
                )

            all_targets_strong = complete and bool(review_summaries) and all(
                item["strong_direct_confirmation"] for item in review_summaries
            )
            all_targets_independent = complete and bool(review_summaries) and all(
                item["supported_independence_confirmation"]
                for item in review_summaries
            )
            verifier_judgments.append(
                {
                    "verifier_id": verifier_id,
                    "complete": complete,
                    "all_targets_strong_direct_confirmation": all_targets_strong,
                    "all_targets_supported_independence_confirmation": (
                        all_targets_independent
                    ),
                    "reviews": review_summaries,
                }
            )

        unanimous_strong_confirmation = bool(verifier_judgments) and all(
            item["all_targets_strong_direct_confirmation"]
            for item in verifier_judgments
        )
        unanimous_independence_confirmation = bool(verifier_judgments) and all(
            item["all_targets_supported_independence_confirmation"]
            for item in verifier_judgments
        )
        lacks_strong_or_independence_rescue = not (
            unanimous_strong_confirmation or unanimous_independence_confirmation
        )
        predicates = {
            ("support_in_policy_scope" if all_support else "nonmajority_support"): (
                all_support or nonmajority_support
            ),
            "placeholder_only_identity": placeholder_only_identity,
            "identity_or_subtype_uncertain": identity_or_subtype_uncertain,
            "lacks_unanimous_strong_or_independence_rescue": (
                lacks_strong_or_independence_rescue
            ),
        }
        should_abstain = all(predicates.values())
        if should_abstain:
            cluster["decision"] = "abstain"
            cluster["identity_status"] = "ambiguous"
            cluster["final_entity"] = None
            cluster["decision_reason"] = (
                ("Placeholder-only accepted identity, " if all_support else
                 "Nonmajority detector support, placeholder-only accepted identity, ")
                +
                "explicit identity or subtype uncertainty, and no unanimous strong "
                "or independently establishing verifier evidence require a "
                "precision-first abstention; retained only in the audit ledger."
            )
            cluster["uncertainty_flags"] = sorted(
                set(cluster.get("uncertainty_flags", []))
                | {("all_support_generic_identity_evidence_gate" if all_support
                    else "nonmajority_generic_identity_evidence_gate")}
            )

        audit_records.append(
            {
                "cluster_id": cluster["cluster_id"],
                "detector_support": detector_support,
                "nonmajority_support": nonmajority_support,
                "detector_denominator": denominator,
                "canonical_name": cluster.get("canonical_name"),
                "final_entity_name_before_gate": final_name,
                "canonical_placeholder_head": canonical_head,
                "final_placeholder_head": final_head,
                "matched_identity_uncertainty_flags": matched_uncertainty_flags,
                "initial_target_cluster_ids": target_ids,
                "verifier_judgments": verifier_judgments,
                "predicates": predicates,
                "failed_gate_predicates": sorted(
                    key for key, value in predicates.items() if not value
                ),
                "rescues": {
                    "unanimous_strong_confirmation": (
                        unanimous_strong_confirmation
                    ),
                    "unanimous_independence_confirmation": (
                        unanimous_independence_confirmation
                    ),
                },
                "basis": (
                    "all_gate_predicates_true"
                    if should_abstain
                    else "one_or_more_gate_predicates_false"
                ),
                "result": "changed_to_abstain" if should_abstain else "kept_accept",
            }
        )

    return gated, {
        "policy_version": (ALL_SUPPORT_GENERIC_IDENTITY_GATE_VERSION if all_support
                           else NONMAJORITY_GENERIC_IDENTITY_GATE_VERSION),
        "support_scope": support_scope,
        "detector_support_affects_gate_eligibility": not all_support,
        "policy": (
            ("an accepted cluster at any detector support becomes abstain only when " if all_support
             else "an accepted nonmajority-supported cluster becomes abstain only when ")
            +
            "both accepted names remain placeholder-only, identity or subtype "
            "uncertainty is explicit, and neither unanimous strong verifier "
            "confirmation nor unanimous supported independence evidence exists"
        ),
        "private_detector_support_audit": True,
        "supplied_to_any_model": False,
        "detector_support_selects_entity_directly": False,
        "expected_detector_count": denominator,
        "nonmajority_expression": "2 * distinct_detector_support <= detector_count",
        "placeholder_head_lexicon": sorted(GENERIC_IDENTITY_PLACEHOLDER_HEADS),
        "identity_uncertainty_requires_explicit_flag": True,
        "required_verifier_ids": list(required_verifiers),
        "strong_rescue_requires_every_verifier_and_target": True,
        "independence_rescue_requires_every_verifier_and_target": True,
        "split_child_uses_exact_unit_evidence_only": True,
        "records": audit_records,
    }


def _has_group_member_family_shape(decisions: Mapping[str, Any]) -> bool:
    return bool(family_stage.eligible_group_alternative_ids(decisions))


def _attempt_usage_from_events(path: Path) -> Optional[Dict[str, Optional[int]]]:
    if not path.is_file():
        return None
    return shot_graph.parse_codex_token_usage(_stream_text(path.read_bytes()))


def _codex_attempt_accounting(
    *,
    invocation: Optional[CodexInvocation],
    error: Optional[BaseException],
    events_path: Path,
    request_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return one loss-aware manifest record fragment for a logical call."""
    if invocation is not None:
        runtime_seconds: Optional[float] = invocation.runtime_seconds
        token_usage = invocation.token_usage
        thread_id = invocation.thread_id
        returncode: Optional[int] = 0
        failure_kind = "python_validation" if error is not None else None
        subprocess_started = True
    elif isinstance(error, CodexCallError):
        runtime_seconds = error.runtime_seconds
        token_usage = error.token_usage
        thread_id = error.thread_id
        returncode = error.returncode
        failure_kind = error.failure_kind
        subprocess_started = error.subprocess_started
    else:
        runtime_seconds = None
        events_exist = None
        try:
            events_exist = events_path.is_file()
            events_text = _stream_text(events_path.read_bytes()) if events_exist else ""
        except OSError:
            events_text = ""
        token_usage = shot_graph.parse_codex_token_usage(events_text)
        thread_id = _thread_id(events_text)
        returncode = None
        failure_kind = "orchestration_error" if error is not None else None
        # A directly streamed file may exist before Popen succeeds. Empty or
        # unreadable artifacts leave startup unknown, not positively started.
        subprocess_started = True if events_text else (False if events_exist is False else None)
    return {
        "failure_kind": failure_kind,
        "runtime_seconds": (
            round(runtime_seconds, 6) if runtime_seconds is not None else None
        ),
        "token_usage": token_usage,
        "thread_id": thread_id,
        "returncode": returncode,
        "subprocess_started": subprocess_started,
        "subprocess_start_unknown": subprocess_started is None,
        **model_routing_stage.accounting_fragment(request_context, events_path),
    }


def run_group_member_family_stage(
    *,
    shot_id: str,
    shot_manifest: Mapping[str, Any],
    attachments: Sequence[Path],
    skill_text: str,
    baseline: Mapping[str, Any],
    anonymous_view: Mapping[str, Any],
    anonymous_ids: Sequence[str],
    valid_frame_ids: Sequence[int],
    codex_bin: str,
    model: Optional[str],
    timeout_sec: int,
    work_dirs: Sequence[Path],
    prompt_dir: Path,
    attempt_dir: Path,
    adjudication_dir: Path,
    verbose: bool,
    model_routing: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Audit explicit families and materialize a provisional consensus view."""
    if len(work_dirs) != 2:
        raise EnsembleError("Group/member family stage requires two workdirs")
    planner_view = family_stage.planner_view(anonymous_view)
    planner_baseline = family_stage.planner_baseline_view(baseline)
    frozen_input_hashes = {
        "planner_view": family_stage.json_hash(planner_view),
        "planner_baseline": family_stage.json_hash(planner_baseline),
        "attachments": {
            str(path.resolve()): _sha256(path) for path in attachments
        },
    }
    planner_input_path = adjudication_dir / "granularity_group_member_input.json"
    planner_manifest = {
        key: copy.deepcopy(shot_manifest[key])
        for key in ("shot_id", "num_frames", "fps", "reference_frames")
        if key in shot_manifest
    }
    _atomic_write_json(
        planner_input_path,
        {
            "shot_manifest": planner_manifest,
            "source_blind_anonymous_candidates": planner_view,
            "source_blind_baseline": planner_baseline,
        },
    )

    prompt = family_stage.build_prompt(
        shot_id=shot_id,
        shot_manifest=shot_manifest,
        anonymous_view=planner_view,
        baseline=planner_baseline,
        skill_text=skill_text,
    )
    prompt_path = prompt_dir / "granularity_group_member_planner.txt"
    _atomic_write_text(prompt_path, prompt)

    attempts: List[Dict[str, Any]] = []
    usages: List[Optional[Dict[str, Optional[int]]]] = []
    plans_by_index: Dict[int, Optional[Dict[str, Any]]] = {}
    eligible = _has_group_member_family_shape(baseline)
    synthetic_empty_plan_count = 0
    if not eligible:
        empty_plan = {
            "protocol_version": family_stage.FAMILY_PLAN_PROTOCOL,
            "shot_id": shot_id,
            "reviewed_group_alternative_cluster_ids": [],
            "excluded_group_alternatives": [],
            "families": [],
            "warnings": [],
        }
        family_stage.validate_family_plan(
            empty_plan,
            shot_id=shot_id,
            baseline=baseline,
            anonymous_view=planner_view,
            valid_frame_ids=valid_frame_ids,
            base_protocol=PROTOCOL_VERSION,
        )
        plans_by_index = {
            1: copy.deepcopy(empty_plan),
            2: copy.deepcopy(empty_plan),
        }
        synthetic_empty_plan_count = 2
    else:
        print(
            f"[ensemble {shot_id}] group/member granularity: two isolated "
            "planners reviewing the same frozen family candidates",
            flush=True,
        )

        def invoke_planner(
            planner_index: int,
        ) -> Tuple[
            Optional[Dict[str, Any]],
            List[Dict[str, Any]],
            List[Optional[Dict[str, Optional[int]]]],
        ]:
            planner_attempts: List[Dict[str, Any]] = []
            planner_usages: List[Optional[Dict[str, Optional[int]]]] = []
            for attempt in (1, 2):
                prefix = (
                    f"granularity_group_member_planner_{planner_index}."
                    f"attempt{attempt}"
                )
                events_path = attempt_dir / f"{prefix}.events.jsonl"
                model_context = model_routing_stage.request_context(
                    model_routing, role="granularity_group_member",
                    role_id=f"granularity_group_member_planner_{planner_index}", attempt=attempt, shot_id=shot_id,
                )
                invocation: Optional[CodexInvocation] = None
                error: Optional[BaseException] = None
                candidate_plan: Optional[Dict[str, Any]] = None
                print(
                    f"[ensemble {shot_id}] group/member planner "
                    f"{planner_index}/2 attempt {attempt}",
                    flush=True,
                )
                try:
                    invocation = run_codex_json(
                        prompt=prompt,
                        attachments=attachments,
                        schema_path=GRANULARITY_FAMILY_SCHEMA,
                        output_path=attempt_dir / f"{prefix}.json",
                        events_path=events_path,
                        stderr_path=attempt_dir / f"{prefix}.stderr.log",
                        codex_bin=codex_bin,
                        model=model,
                        **model_routing_stage.request_kwargs(model_context),
                        timeout_sec=timeout_sec,
                        work_dir=work_dirs[planner_index - 1],
                        persistent=False,
                        verbose=verbose,
                    )
                    candidate_plan = invocation.payload
                    family_stage.validate_family_plan(
                        candidate_plan,
                        shot_id=shot_id,
                        baseline=baseline,
                        anonymous_view=planner_view,
                        valid_frame_ids=valid_frame_ids,
                        base_protocol=PROTOCOL_VERSION,
                    )
                except (
                    EnsembleError,
                    family_stage.FamilyPlanError,
                    OSError,
                ) as exc:
                    error = exc
                    candidate_plan = None
                accounting = _codex_attempt_accounting(
                    invocation=invocation,
                    error=error,
                    events_path=events_path,
                    **model_routing_stage.request_kwargs(model_context),
                )
                if accounting["subprocess_started"] or accounting.get("subprocess_start_unknown"):
                    planner_usages.append(accounting["token_usage"])
                planner_attempts.append(
                    {
                        "planner_index": planner_index,
                        "attempt": attempt,
                        "status": (
                            "success" if candidate_plan is not None else "failed"
                        ),
                        "error": str(error) if error is not None else None,
                        **accounting,
                    }
                )
                if candidate_plan is not None:
                    return candidate_plan, planner_attempts, planner_usages
            return None, planner_attempts, planner_usages

        results: Dict[
            int,
            Tuple[
                Optional[Dict[str, Any]],
                List[Dict[str, Any]],
                List[Optional[Dict[str, Optional[int]]]],
            ],
        ] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(invoke_planner, planner_index): planner_index
                for planner_index in (1, 2)
            }
            for future in concurrent.futures.as_completed(futures):
                planner_index = futures[future]
                results[planner_index] = future.result()
        for planner_index in (1, 2):
            plan, planner_attempts, planner_usages = results[planner_index]
            plans_by_index[planner_index] = plan
            attempts.extend(planner_attempts)
            usages.extend(planner_usages)

    spatial_vetoes = family_stage.collect_spatial_vetoes(
        [plans_by_index[index] for index in (1, 2)],
        baseline=baseline, anonymous_view=planner_view,
    )
    planner_paths: Dict[int, Path] = {}
    planner_resolutions: Dict[int, List[Dict[str, Any]]] = {}
    planner_resolution_paths: Dict[int, Path] = {}
    for planner_index in (1, 2):
        plan = plans_by_index[planner_index]
        if plan is None:
            continue
        plan_path = (
            adjudication_dir
            / f"granularity_group_member_plan_{planner_index}.json"
        )
        _atomic_write_json(plan_path, plan)
        planner_paths[planner_index] = plan_path
        resolutions = family_stage.select_resolutions(plan, spatial_vetoes=spatial_vetoes)
        resolution_path = (
            adjudication_dir
            / f"granularity_group_member_resolutions_{planner_index}.source_blind.json"
        )
        _atomic_write_json(
            resolution_path,
            {
                "protocol_version": family_stage.FAMILY_PLAN_PROTOCOL,
                "shot_id": shot_id,
                "planner_index": planner_index,
                "panel_provenance_used": False,
                "resolutions": resolutions,
            },
        )
        planner_resolutions[planner_index] = resolutions
        planner_resolution_paths[planner_index] = resolution_path

    missing_planners = [
        planner_index
        for planner_index in (1, 2)
        if plans_by_index[planner_index] is None
    ]
    if missing_planners:
        error = (
            "Missing valid source-blind group/member family plan after retry "
            f"from planner(s): {missing_planners}"
        )
        failure_path = adjudication_dir / "granularity_group_member_failure.json"
        _atomic_write_json(
            failure_path,
            {
                "protocol_version": family_stage.FAMILY_PLAN_PROTOCOL,
                "shot_id": shot_id,
                "status": "failed",
                "error": error,
                "missing_planner_indices": missing_planners,
                "attempts": attempts,
            },
        )
        paths = {"planner_input": planner_input_path, "failure": failure_path}
        paths.update(
            {
                f"planner_{index}": path
                for index, path in planner_paths.items()
            }
        )
        paths.update(
            {
                f"planner_{index}_source_blind_resolutions": path
                for index, path in planner_resolution_paths.items()
            }
        )
        return copy.deepcopy(dict(baseline)), {
            "status": "failed",
            "error": error,
            "eligible_shape": eligible,
            "plans": [
                plans_by_index[index]
                for index in (1, 2)
                if plans_by_index[index] is not None
            ],
            "family_count_by_planner": [
                (
                    len(plans_by_index[index]["families"])
                    if plans_by_index[index] is not None
                    else None
                )
                for index in (1, 2)
            ],
            "plan": None,
            "planner_resolutions": planner_resolutions,
            "consensus_resolutions": [],
            "source_blind_resolutions": [],
            "firewall_audit": None,
            "attempts": attempts,
            "token_usages": usages,
            "invocation_count": len(attempts),
            "valid_planner_count": 2 - len(missing_planners),
            "failed_planner_indices": missing_planners,
            "synthetic_empty_plan_count": synthetic_empty_plan_count,
            "prompt_path": prompt_path,
            "paths": paths,
        }

    plans = [plans_by_index[1], plans_by_index[2]]
    if not all(isinstance(plan, dict) for plan in plans):
        raise EnsembleError("Group/member planner result accounting is inconsistent")
    consensus_resolutions = family_stage.select_consensus_resolutions(
        plans[0], plans[1], spatial_vetoes=spatial_vetoes,
    )
    (
        assembled,
        firewall_audit,
        application_plan,
        application_resolutions,
    ) = family_stage.assemble_consensus(
        baseline=baseline,
        anonymous_view=planner_view,
        first_plan=plans[0],
        second_plan=plans[1],
        consensus_resolutions=consensus_resolutions,
        shot_id=shot_id,
        valid_frame_ids=valid_frame_ids,
        base_protocol=PROTOCOL_VERSION,
    )
    firewall_audit = copy.deepcopy(firewall_audit)
    firewall_audit["application_is_provisional"] = True
    firewall_audit["accepted_candidate_second_gate_required"] = True
    firewall_audit["eligible_as_final_inventory"] = False
    family_stage.validate_family_plan(
        application_plan,
        shot_id=shot_id,
        baseline=baseline,
        anonymous_view=planner_view,
        valid_frame_ids=valid_frame_ids,
        base_protocol=PROTOCOL_VERSION,
    )
    validate_decisions(
        assembled,
        shot_id=shot_id,
        anonymous_ids=anonymous_ids,
        valid_frame_ids=valid_frame_ids,
    )

    if frozen_input_hashes != {
        "planner_view": family_stage.json_hash(planner_view),
        "planner_baseline": family_stage.json_hash(planner_baseline),
        "attachments": {
            str(path.resolve()): _sha256(path) for path in attachments
        },
    }:
        raise EnsembleError("A frozen granularity-planner input changed during review")

    consensus_path = adjudication_dir / "granularity_group_member_consensus.json"
    application_plan_path = (
        adjudication_dir / "granularity_group_member_application_plan.json"
    )
    application_resolution_path = (
        adjudication_dir / "granularity_group_member_resolutions.source_blind.json"
    )
    firewall_path = adjudication_dir / "granularity_group_member_firewall.json"
    _atomic_write_json(
        consensus_path,
        {
            "protocol_version": family_stage.FAMILY_PLAN_PROTOCOL,
            "shot_id": shot_id,
            "planner_count": 2,
            "exact_family_member_partition_consensus_required": True,
            "partition_effect": (
                "provisional_pending_accepted_candidate_second_gate"
            ),
            "resolutions": consensus_resolutions,
        },
    )
    _atomic_write_json(application_plan_path, application_plan)
    _atomic_write_json(
        application_resolution_path,
        {
            "protocol_version": family_stage.FAMILY_PLAN_PROTOCOL,
            "shot_id": shot_id,
            "panel_provenance_used": False,
            "consensus_application_only": True,
            "partition_effect": (
                "provisional_pending_accepted_candidate_second_gate"
            ),
            "resolutions": application_resolutions,
        },
    )
    _atomic_write_json(firewall_path, firewall_audit)
    status = (
        "deterministically_skipped"
        if not eligible
        else (
            "applied"
            if firewall_audit["applied_family_ids"]
            else "no_consensus_family"
        )
    )
    paths = {
        "planner_input": planner_input_path,
        "planner_1": planner_paths[1],
        "planner_2": planner_paths[2],
        "planner_1_source_blind_resolutions": planner_resolution_paths[1],
        "planner_2_source_blind_resolutions": planner_resolution_paths[2],
        "consensus": consensus_path,
        "application_plan": application_plan_path,
        "source_blind_resolutions": application_resolution_path,
        "firewall": firewall_path,
    }
    return assembled, {
        "status": status,
        "application_is_provisional": True,
        "accepted_candidate_second_gate_required": True,
        "eligible_shape": eligible,
        "plans": plans,
        "family_count_by_planner": [len(plan["families"]) for plan in plans],
        "plan": application_plan,
        "planner_resolutions": planner_resolutions,
        "consensus_resolutions": consensus_resolutions,
        "source_blind_resolutions": application_resolutions,
        "firewall_audit": firewall_audit,
        "attempts": attempts,
        "token_usages": usages,
        "invocation_count": len(attempts),
        "valid_planner_count": 2,
        "failed_planner_indices": [],
        "synthetic_empty_plan_count": synthetic_empty_plan_count,
        "prompt_path": prompt_path,
        "paths": paths,
    }


def run_accepted_compact_assembly_stage(
    *,
    shot_id: str,
    shot_manifest: Mapping[str, Any],
    attachments: Sequence[Path],
    skill_text: str,
    baseline: Mapping[str, Any],
    anonymous_view: Mapping[str, Any],
    explicit_partition_plans: Sequence[Mapping[str, Any]],
    anonymous_ids: Sequence[str],
    valid_frame_ids: Sequence[int],
    codex_bin: str,
    model: Optional[str],
    timeout_sec: int,
    work_dirs: Sequence[Path],
    prompt_dir: Path,
    attempt_dir: Path,
    adjudication_dir: Path,
    verbose: bool,
    declared_partition_neighborhoods: Sequence[Mapping[str, Any]] = (),
    spatial_vetoes: Sequence[Mapping[str, Any]] = (),
    model_routing: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Apply the final exact-consensus gate to the frozen pre-group baseline."""
    if len(work_dirs) != 2:
        raise EnsembleError("Accepted-only assembly stage requires two workdirs")
    candidate_bank, candidate_bank_private_audit = (
        accepted_assembly_stage.build_candidate_bank(
            baseline=baseline,
            anonymous_view=anonymous_view,
            explicit_partition_plans=explicit_partition_plans,
            shot_id=shot_id,
            base_protocol=PROTOCOL_VERSION,
            declared_partition_neighborhoods=declared_partition_neighborhoods,
        )
    )
    spatial_vetoes = copy.deepcopy(list(spatial_vetoes))
    candidate_bank_private_audit["spatial_vetoes"] = copy.deepcopy(spatial_vetoes)
    accepted_view = accepted_assembly_stage.planner_baseline_view(
        baseline,
        candidate_bank=candidate_bank,
        shot_id=shot_id,
        base_protocol=PROTOCOL_VERSION,
    )
    accepted_ids = [
        item["cluster_id"] for item in accepted_view["accepted_clusters"]
    ]
    candidate_ids = [
        item["candidate_id"] for item in candidate_bank["candidates"]
    ]
    frozen_input_hashes = {
        "baseline": accepted_assembly_stage.json_hash(baseline),
        "accepted_view": accepted_assembly_stage.json_hash(accepted_view),
        "candidate_bank_private_audit": accepted_assembly_stage.json_hash(
            candidate_bank_private_audit
        ),
        "attachments": {
            str(path.resolve()): _sha256(path) for path in attachments
        },
    }
    input_path = adjudication_dir / "accepted_compact_assembly_input.json"
    candidate_bank_path = (
        adjudication_dir / "accepted_compact_assembly_candidate_bank.json"
    )
    candidate_bank_private_path = (
        adjudication_dir / "accepted_compact_assembly_candidate_bank.private.json"
    )
    _atomic_write_json(candidate_bank_path, candidate_bank)
    _atomic_write_json(candidate_bank_private_path, candidate_bank_private_audit)
    planner_manifest = {
        key: copy.deepcopy(shot_manifest[key])
        for key in ("shot_id", "num_frames", "fps", "reference_frames")
        if key in shot_manifest
    }
    _atomic_write_json(
        input_path,
        {
            "shot_manifest": planner_manifest,
            "accepted_only_source_blind_inventory": accepted_view,
        },
    )
    prompt = accepted_assembly_stage.build_prompt(
        shot_id=shot_id,
        shot_manifest=shot_manifest,
        accepted_view=accepted_view,
        policy_text=skill_text,
    )
    prompt_path = prompt_dir / "accepted_compact_assembly_planner.txt"
    _atomic_write_text(prompt_path, prompt)

    plans_by_index: Dict[int, Optional[Dict[str, Any]]] = {}
    attempts: List[Dict[str, Any]] = []
    usages: List[Optional[Dict[str, Optional[int]]]] = []
    if not candidate_ids:
        empty_plan = {
            "protocol_version": accepted_assembly_stage.PLAN_PROTOCOL,
            "shot_id": shot_id,
            "reviewed_accepted_cluster_ids": accepted_ids,
            "reviewed_candidate_ids": [],
            "families": [],
            "excluded_candidates": [],
            "warnings": [],
        }
        accepted_assembly_stage.validate_plan(
            empty_plan,
            shot_id=shot_id,
            baseline=baseline,
            accepted_view=accepted_view,
            valid_frame_ids=valid_frame_ids,
            base_protocol=PROTOCOL_VERSION,
        )
        plans_by_index = {
            1: copy.deepcopy(empty_plan),
            2: copy.deepcopy(empty_plan),
        }
    else:
        print(
            f"[ensemble {shot_id}] accepted-only granularity: two isolated "
            f"planners reviewing {len(candidate_ids)} mandatory candidates "
            f"over {len(accepted_ids)} frozen clusters",
            flush=True,
        )

        def invoke_planner(
            planner_index: int,
        ) -> Tuple[
            Optional[Dict[str, Any]],
            List[Dict[str, Any]],
            List[Optional[Dict[str, Optional[int]]]],
        ]:
            planner_attempts: List[Dict[str, Any]] = []
            planner_usages: List[Optional[Dict[str, Optional[int]]]] = []
            for attempt in (1, 2):
                prefix = (
                    f"accepted_compact_assembly_planner_{planner_index}."
                    f"attempt{attempt}"
                )
                events_path = attempt_dir / f"{prefix}.events.jsonl"
                model_context = model_routing_stage.request_context(
                    model_routing, role="accepted_compact_assembly",
                    role_id=f"accepted_compact_assembly_planner_{planner_index}", attempt=attempt, shot_id=shot_id,
                )
                invocation: Optional[CodexInvocation] = None
                error: Optional[BaseException] = None
                candidate: Optional[Dict[str, Any]] = None
                try:
                    invocation = run_codex_json(
                        prompt=prompt,
                        attachments=attachments,
                        schema_path=ACCEPTED_ASSEMBLY_SCHEMA,
                        output_path=attempt_dir / f"{prefix}.json",
                        events_path=events_path,
                        stderr_path=attempt_dir / f"{prefix}.stderr.log",
                        codex_bin=codex_bin,
                        model=model,
                        **model_routing_stage.request_kwargs(model_context),
                        timeout_sec=timeout_sec,
                        work_dir=work_dirs[planner_index - 1],
                        persistent=False,
                        verbose=verbose,
                    )
                    candidate = invocation.payload
                    accepted_assembly_stage.validate_plan(
                        candidate,
                        shot_id=shot_id,
                        baseline=baseline,
                        accepted_view=accepted_view,
                        valid_frame_ids=valid_frame_ids,
                        base_protocol=PROTOCOL_VERSION,
                    )
                except (
                    EnsembleError,
                    accepted_assembly_stage.AcceptedAssemblyError,
                    OSError,
                ) as exc:
                    error = exc
                    candidate = None
                accounting = _codex_attempt_accounting(
                    invocation=invocation,
                    error=error,
                    events_path=events_path,
                    **model_routing_stage.request_kwargs(model_context),
                )
                if accounting["subprocess_started"] or accounting.get("subprocess_start_unknown"):
                    planner_usages.append(accounting["token_usage"])
                planner_attempts.append(
                    {
                        "planner_index": planner_index,
                        "attempt": attempt,
                        "status": "success" if candidate is not None else "failed",
                        "error": str(error) if error is not None else None,
                        **accounting,
                    }
                )
                if candidate is not None:
                    return candidate, planner_attempts, planner_usages
            return None, planner_attempts, planner_usages

        results: Dict[
            int,
            Tuple[
                Optional[Dict[str, Any]],
                List[Dict[str, Any]],
                List[Optional[Dict[str, Optional[int]]]],
            ],
        ] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(invoke_planner, planner_index): planner_index
                for planner_index in (1, 2)
            }
            for future in concurrent.futures.as_completed(futures):
                planner_index = futures[future]
                results[planner_index] = future.result()
        for planner_index in (1, 2):
            plan, planner_attempts, planner_usages = results[planner_index]
            plans_by_index[planner_index] = plan
            attempts.extend(planner_attempts)
            usages.extend(planner_usages)

    planner_paths: Dict[int, Path] = {}
    for planner_index in (1, 2):
        plan = plans_by_index[planner_index]
        if plan is None:
            continue
        path = (
            adjudication_dir
            / f"accepted_compact_assembly_plan_{planner_index}.json"
        )
        _atomic_write_json(path, plan)
        planner_paths[planner_index] = path

    missing_planners = [
        planner_index
        for planner_index in (1, 2)
        if plans_by_index[planner_index] is None
    ]
    if missing_planners:
        error = (
            "Missing valid accepted-only compact-assembly plan after retry from "
            f"planner(s): {missing_planners}"
        )
        failure_path = adjudication_dir / "accepted_compact_assembly_failure.json"
        _atomic_write_json(
            failure_path,
            {
                "protocol_version": accepted_assembly_stage.PLAN_PROTOCOL,
                "shot_id": shot_id,
                "status": "failed",
                "error": error,
                "missing_planner_indices": missing_planners,
                "attempts": attempts,
            },
        )
        paths = {
            "planner_input": input_path,
            "candidate_bank": candidate_bank_path,
            "candidate_bank_private": candidate_bank_private_path,
            "failure": failure_path,
        }
        paths.update(
            {
                f"planner_{planner_index}": path
                for planner_index, path in planner_paths.items()
            }
        )
        return copy.deepcopy(dict(baseline)), {
            "status": "failed",
            "error": error,
            "accepted_cluster_count": len(accepted_ids),
            "candidate_count": len(candidate_ids),
            "plans": [
                plans_by_index[index]
                for index in (1, 2)
                if plans_by_index[index] is not None
            ],
            "resolutions": [],
            "firewall_audit": None,
            "attempts": attempts,
            "token_usages": usages,
            "invocation_count": len(attempts),
            "prompt_path": prompt_path,
            "paths": paths,
        }

    plans = [plans_by_index[1], plans_by_index[2]]
    if not all(isinstance(plan, dict) for plan in plans):
        raise EnsembleError("Accepted-only planner result accounting is inconsistent")

    resolutions = accepted_assembly_stage.select_consensus_resolutions(
        plans[0], plans[1], spatial_vetoes=spatial_vetoes,
    )
    assembled, firewall_audit = accepted_assembly_stage.assemble_consensus(
        baseline=baseline,
        first_plan=plans[0],
        second_plan=plans[1],
        resolutions=resolutions,
        candidate_bank=candidate_bank,
        shot_id=shot_id,
        valid_frame_ids=valid_frame_ids,
        base_protocol=PROTOCOL_VERSION,
        spatial_vetoes=spatial_vetoes,
    )
    validate_decisions(
        assembled,
        shot_id=shot_id,
        anonymous_ids=anonymous_ids,
        valid_frame_ids=valid_frame_ids,
    )
    if frozen_input_hashes != {
        "baseline": accepted_assembly_stage.json_hash(baseline),
        "accepted_view": accepted_assembly_stage.json_hash(accepted_view),
        "candidate_bank_private_audit": accepted_assembly_stage.json_hash(
            candidate_bank_private_audit
        ),
        "attachments": {
            str(path.resolve()): _sha256(path) for path in attachments
        },
    }:
        raise EnsembleError("A frozen accepted-only planner input changed during review")

    resolution_path = (
        adjudication_dir / "accepted_compact_assembly_resolutions.json"
    )
    firewall_path = adjudication_dir / "accepted_compact_assembly_firewall.json"
    _atomic_write_json(
        resolution_path,
        {
            "protocol_version": accepted_assembly_stage.PLAN_PROTOCOL,
            "shot_id": shot_id,
            "resolutions": resolutions,
        },
    )
    _atomic_write_json(firewall_path, firewall_audit)
    applied_count = sum(item["status"] == "applied" for item in resolutions)
    status = (
        "deterministically_skipped"
        if not candidate_ids
        else ("applied" if applied_count else "no_consensus_family")
    )
    return assembled, {
        "status": status,
        "accepted_cluster_count": len(accepted_ids),
        "candidate_count": len(candidate_ids),
        "plans": plans,
        "resolutions": resolutions,
        "firewall_audit": firewall_audit,
        "attempts": attempts,
        "token_usages": usages,
        "invocation_count": len(attempts),
        "prompt_path": prompt_path,
        "paths": {
            "planner_input": input_path,
            "candidate_bank": candidate_bank_path,
            "candidate_bank_private": candidate_bank_private_path,
            "planner_1": planner_paths[1],
            "planner_2": planner_paths[2],
            "resolutions": resolution_path,
            "firewall": firewall_path,
        },
    }


def _normalized_proposal_partition(
    units: Sequence[Mapping[str, Any]],
) -> Tuple[Tuple[str, ...], ...]:
    return tuple(
        sorted(
            tuple(sorted(unit.get("anonymous_proposal_ids", [])))
            for unit in units
        )
    )


def build_intra_cluster_split_consensus(
    *,
    shot_id: str,
    challenges: Sequence[Mapping[str, Any]],
    verifier_reports: Sequence[Mapping[str, Any]],
    verifier_ids: Sequence[str] = VERIFIER_IDS,
) -> Dict[str, Any]:
    """Require exact two-verifier proposal partitions before a split is reviewable."""
    reports = {
        report["verifier_id"]: {
            review["cluster_id"]: review for review in report["reviews"]
        }
        for report in verifier_reports
        if report.get("verifier_id") in set(verifier_ids)
    }
    records: List[Dict[str, Any]] = []
    exact_partitions: List[Dict[str, Any]] = []
    for challenge in sorted(challenges, key=lambda item: item["cluster_id"]):
        cluster_id = challenge["cluster_id"]
        judgments = []
        normalized_partitions: List[Optional[Tuple[Tuple[str, ...], ...]]] = []
        for verifier_id in verifier_ids:
            review = reports.get(verifier_id, {}).get(cluster_id)
            judgment = (
                review.get("intra_cluster_split_judgment")
                if review is not None
                else None
            )
            partition = (
                _normalized_proposal_partition(
                    review.get("proposed_physical_units", [])
                )
                if judgment == "split_into_multiple_physical_instances"
                else None
            )
            normalized_partitions.append(partition)
            judgments.append(
                {
                    "verifier_id": verifier_id,
                    "complete": review is not None,
                    "judgment": judgment,
                    "normalized_proposal_partition": (
                        [list(group) for group in partition]
                        if partition is not None
                        else []
                    ),
                }
            )
        exact = (
            len(normalized_partitions) == len(verifier_ids)
            and all(partition is not None for partition in normalized_partitions)
            and len(set(normalized_partitions)) == 1
        )
        if exact:
            consensus_partition = normalized_partitions[0]
            assert consensus_partition is not None
            result = "split_permitted_for_persistent_adjudicator_review"
            basis = "exact_two_verifier_proposal_partition_consensus"
            exact_partitions.append(
                {
                    "cluster_id": cluster_id,
                    "proposal_partition": [
                        list(group) for group in consensus_partition
                    ],
                }
            )
        else:
            consensus_partition = None
            result = "frozen_initial_cluster"
            if any(partition is None for partition in normalized_partitions):
                basis = "missing_or_non_split_verifier_judgment"
            else:
                basis = "proposal_partition_disagreement"
        records.append(
            {
                "cluster_id": cluster_id,
                "verifier_judgments": judgments,
                "exact_partition_consensus": exact,
                "consensus_proposal_partition": (
                    [list(group) for group in consensus_partition]
                    if consensus_partition is not None
                    else []
                ),
                "result": result,
                "basis": basis,
            }
        )
    return {
        "protocol_version": PROTOCOL_VERSION,
        "shot_id": shot_id,
        "policy": (
            "proposal boxes trigger review only; an initial cluster may be split "
            "only after exact isolated-verifier proposal-partition consensus and "
            "persistent-adjudicator pixel review"
        ),
        "source_or_detector_count_used": False,
        "automatic_split": False,
        "required_verifier_ids": list(verifier_ids),
        "exact_consensus_partitions": exact_partitions,
        "records": records,
    }


def enforce_intra_cluster_split_consensus(
    *,
    initial_decisions: Mapping[str, Any],
    revised_decisions: Mapping[str, Any],
    split_consensus: Mapping[str, Any],
    retention_consensus: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Reject any revision split not equal to an exact verifier consensus."""
    permitted = {
        item["cluster_id"]: tuple(
            sorted(tuple(sorted(group)) for group in item["proposal_partition"])
        )
        for item in split_consensus.get("exact_consensus_partitions", [])
    }
    retention_audit = None
    retained_parents = set()
    if retention_consensus is not None:
        import proposal_scope_retention
        try:
            retention_audit = proposal_scope_retention.validate_retention_transition(
                initial_decisions, revised_decisions, retention_consensus,
                independently_authorized_split_parent_ids=sorted(permitted),
            )
        except ValueError as error:
            raise EnsembleError(str(error)) from error
        retained_parents = set(retention_audit["audited_parent_ids"])
    revised_owner = {
        proposal_id: cluster["cluster_id"]
        for cluster in revised_decisions["clusters"]
        for proposal_id in cluster["anonymous_proposal_ids"]
    }
    observed_splits = []
    for initial in initial_decisions["clusters"]:
        if initial["cluster_id"] in retained_parents:
            # This transition was checked above; its unresolved complement is
            # not an ordinary, positively confirmed physical split unit.
            continue
        proposal_ids = set(initial["anonymous_proposal_ids"])
        actual_by_owner: Dict[str, List[str]] = {}
        for proposal_id in sorted(proposal_ids):
            actual_by_owner.setdefault(revised_owner[proposal_id], []).append(proposal_id)
        if len(actual_by_owner) <= 1:
            continue
        actual_partition = tuple(
            sorted(tuple(sorted(group)) for group in actual_by_owner.values())
        )
        expected_partition = permitted.get(initial["cluster_id"])
        if expected_partition is None:
            raise EnsembleError(
                f"Initial cluster {initial['cluster_id']} was split without exact "
                "two-verifier proposal-partition consensus"
            )
        if actual_partition != expected_partition:
            raise EnsembleError(
                f"Initial cluster {initial['cluster_id']} split does not match the "
                "exact verifier consensus proposal partition"
            )
        observed_splits.append(
            {
                "initial_cluster_id": initial["cluster_id"],
                "proposal_partition": [list(group) for group in actual_partition],
                "revised_cluster_ids": sorted(actual_by_owner),
            }
        )
    return {
        "automatic_split": False,
        "exact_consensus_required": True,
        "observed_split_count": len(observed_splits),
        "observed_splits": observed_splits,
        **({"scope_retention_transition": retention_audit} if retention_audit is not None else {}),
    }


def validate_verifier_report(
    report: Mapping[str, Any],
    *,
    shot_id: str,
    verifier_id: str,
    target_cluster_ids: Sequence[str],
    all_cluster_ids: Sequence[str],
    valid_frame_ids: Sequence[int],
    target_proposal_ids_by_cluster: Optional[
        Mapping[str, Sequence[str]]
    ] = None,
    intra_cluster_split_challenges: Sequence[Mapping[str, Any]] = (),
) -> None:
    if report.get("protocol_version") != PROTOCOL_VERSION:
        raise EnsembleError(f"{verifier_id}: wrong protocol_version")
    if report.get("shot_id") != shot_id:
        raise EnsembleError(f"{verifier_id}: wrong shot_id")
    if report.get("verifier_id") != verifier_id:
        raise EnsembleError(f"{verifier_id}: wrong verifier_id")
    reviews = report.get("reviews")
    if not isinstance(reviews, list):
        raise EnsembleError(f"{verifier_id}: reviews must be an array")
    reviewed = [item.get("cluster_id") for item in reviews if isinstance(item, Mapping)]
    if len(reviewed) != len(reviews) or len(reviewed) != len(set(reviewed)):
        raise EnsembleError(f"{verifier_id}: invalid or duplicate cluster reviews")
    if set(reviewed) != set(target_cluster_ids):
        raise EnsembleError(
            f"{verifier_id}: reviews do not exactly cover verification targets"
        )
    valid_frames = set(valid_frame_ids)
    all_clusters = set(all_cluster_ids)
    challenged_by_cluster = {
        item["cluster_id"]: item for item in intra_cluster_split_challenges
    }
    if len(challenged_by_cluster) != len(intra_cluster_split_challenges):
        raise EnsembleError(f"{verifier_id}: duplicate intra-cluster challenges")
    if not set(challenged_by_cluster) <= set(target_cluster_ids):
        raise EnsembleError(
            f"{verifier_id}: intra-cluster challenge is not a verification target"
        )
    target_proposal_ids_by_cluster = target_proposal_ids_by_cluster or {}
    for cluster_id, challenge in challenged_by_cluster.items():
        supplied_ids = set(challenge.get("cluster_proposal_ids", []))
        expected_ids = set(target_proposal_ids_by_cluster.get(cluster_id, supplied_ids))
        if not supplied_ids or supplied_ids != expected_ids:
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} challenge proposal scope is invalid"
            )
    for review in reviews:
        cluster_id = review["cluster_id"]
        same_instances = review.get("same_instance_with_cluster_ids")
        if not isinstance(same_instances, list) or not all(
            isinstance(value, str) for value in same_instances
        ):
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} invalid same-instance list"
            )
        if cluster_id in same_instances or not set(same_instances) <= all_clusters:
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} invalid same-instance target"
            )
        graph_partition = review.get("graph_partition_judgment")
        if graph_partition not in {
            "keep_as_separate_node",
            "merge_into_compact_composite",
            "uncertain",
        }:
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} invalid graph-partition judgment"
            )
        same_graph_nodes = review.get("same_graph_node_with_cluster_ids")
        if not isinstance(same_graph_nodes, list) or not all(
            isinstance(value, str) for value in same_graph_nodes
        ):
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} invalid same-graph-node list"
            )
        if cluster_id in same_graph_nodes or not set(same_graph_nodes) <= all_clusters:
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} invalid same-graph-node target"
            )
        if set(same_instances) & set(same_graph_nodes):
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} identity and partition targets overlap"
            )
        if graph_partition == "merge_into_compact_composite":
            if not same_graph_nodes:
                raise EnsembleError(
                    f"{verifier_id}: {cluster_id} composite merge lacks a target"
                )
        elif same_graph_nodes:
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} same-graph-node target without merge judgment"
            )
        independence_evidence = review.get("observed_independence_evidence")
        if not isinstance(independence_evidence, list):
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} independence evidence must be an array"
            )
        for item in independence_evidence:
            if (
                not isinstance(item, Mapping)
                or item.get("frame_id") not in valid_frames
            ):
                raise EnsembleError(
                    f"{verifier_id}: {cluster_id} invalid independence evidence"
                )
        if (
            graph_partition == "merge_into_compact_composite"
            and independence_evidence
        ):
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} composite merge contradicts independence evidence"
            )
        split_judgment = review.get("intra_cluster_split_judgment")
        proposed_units = review.get("proposed_physical_units")
        pairwise_separation = review.get(
            "pairwise_physical_separation_evidence"
        )
        if split_judgment not in {
            "not_reviewed",
            "keep_single_physical_instance",
            "split_into_multiple_physical_instances",
            "uncertain",
        }:
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} invalid intra-cluster split judgment"
            )
        if not isinstance(proposed_units, list) or not isinstance(
            pairwise_separation, list
        ):
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} split review arrays are required"
            )
        is_challenged = cluster_id in challenged_by_cluster
        if is_challenged and split_judgment == "not_reviewed":
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} omitted its intra-cluster challenge"
            )
        if not is_challenged and split_judgment != "not_reviewed":
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} proposed an unsupplied split review"
            )
        if split_judgment != "split_into_multiple_physical_instances":
            if proposed_units or pairwise_separation:
                raise EnsembleError(
                    f"{verifier_id}: {cluster_id} non-split review must have empty "
                    "unit and separation arrays"
                )
        else:
            if len(proposed_units) < 2:
                raise EnsembleError(
                    f"{verifier_id}: {cluster_id} split needs at least two units"
                )
            unit_ids = [unit.get("unit_id") for unit in proposed_units]
            if (
                not all(isinstance(unit_id, str) and unit_id for unit_id in unit_ids)
                or len(unit_ids) != len(set(unit_ids))
            ):
                raise EnsembleError(
                    f"{verifier_id}: {cluster_id} invalid physical unit IDs"
                )
            expected_proposals = set(
                challenged_by_cluster[cluster_id]["cluster_proposal_ids"]
            )
            observed_proposals: List[str] = []
            for unit in proposed_units:
                unit_proposals = unit.get("anonymous_proposal_ids")
                unit_evidence = unit.get("evidence")
                if (
                    not isinstance(unit_proposals, list)
                    or not unit_proposals
                    or not all(
                        isinstance(proposal_id, str) and proposal_id
                        for proposal_id in unit_proposals
                    )
                    or len(unit_proposals) != len(set(unit_proposals))
                ):
                    raise EnsembleError(
                        f"{verifier_id}: {cluster_id} invalid physical unit proposal set"
                    )
                observed_proposals.extend(unit_proposals)
                if (
                    unit.get("existence_judgment") != "confirmed"
                    or unit.get("salience_judgment") != "graph_worthy"
                    or not isinstance(unit_evidence, list)
                    or not unit_evidence
                    or any(
                        not isinstance(item, Mapping)
                        or item.get("frame_id") not in valid_frames
                        for item in unit_evidence
                    )
                ):
                    raise EnsembleError(
                        f"{verifier_id}: {cluster_id} split unit lacks exact "
                        "existence, salience, or visual confirmation"
                    )
            if (
                len(observed_proposals) != len(set(observed_proposals))
                or set(observed_proposals) != expected_proposals
            ):
                raise EnsembleError(
                    f"{verifier_id}: {cluster_id} physical units must partition "
                    "the target proposals exactly once"
                )
            expected_unit_pairs = {
                frozenset((left_id, right_id))
                for left_index, left_id in enumerate(unit_ids)
                for right_id in unit_ids[left_index + 1 :]
            }
            observed_unit_pairs = set()
            for item in pairwise_separation:
                if not isinstance(item, Mapping):
                    raise EnsembleError(
                        f"{verifier_id}: {cluster_id} invalid pairwise separation evidence"
                    )
                unit_id_a = item.get("unit_id_a")
                unit_id_b = item.get("unit_id_b")
                pair = frozenset((unit_id_a, unit_id_b))
                if (
                    unit_id_a == unit_id_b
                    or unit_id_a not in set(unit_ids)
                    or unit_id_b not in set(unit_ids)
                    or item.get("frame_id") not in valid_frames
                    or item.get("support_quality") not in {"strong", "moderate"}
                    or not isinstance(item.get("unit_a_coarse_locator"), str)
                    or not isinstance(item.get("unit_b_coarse_locator"), str)
                    or item["unit_a_coarse_locator"].strip().casefold()
                    == item["unit_b_coarse_locator"].strip().casefold()
                ):
                    raise EnsembleError(
                        f"{verifier_id}: {cluster_id} pairwise physical separation "
                        "must directly distinguish two valid units"
                    )
                observed_unit_pairs.add(pair)
            if observed_unit_pairs != expected_unit_pairs:
                raise EnsembleError(
                    f"{verifier_id}: {cluster_id} split lacks direct evidence for "
                    "every pairwise physical boundary"
                )
        evidence = review.get("evidence")
        if not isinstance(evidence, list):
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} evidence must be an array"
            )
        for item in evidence:
            if (
                not isinstance(item, Mapping)
                or item.get("frame_id") not in valid_frames
            ):
                raise EnsembleError(f"{verifier_id}: {cluster_id} invalid evidence")
        if review.get("existence_judgment") == "confirmed" and not evidence:
            raise EnsembleError(
                f"{verifier_id}: {cluster_id} confirmed without visual evidence"
            )


def build_audit_and_semantics(
    decisions: Mapping[str, Any],
    source_map: Mapping[str, Any],
    prompt_bound_matches: Mapping[str, Any],
    *,
    shot_id: str,
    verification_target_reasons: Optional[Mapping[str, Sequence[str]]] = None,
    verifier_reports: Sequence[Mapping[str, Any]] = (),
    initial_decisions: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    verification_target_reasons = verification_target_reasons or {}
    initial_decisions = initial_decisions or decisions
    target_proposals = {
        cluster["cluster_id"]: set(cluster["anonymous_proposal_ids"])
        for cluster in initial_decisions["clusters"]
        if cluster["cluster_id"] in verification_target_reasons
    }
    verifier_reviews: Dict[str, List[Dict[str, Any]]] = {}
    for report in verifier_reports:
        for review in report["reviews"]:
            verifier_reviews.setdefault(review["cluster_id"], []).append(
                {"verifier_id": report["verifier_id"], **review}
            )
    sources = {
        item["anonymous_proposal_id"]: {
            key: item[key] for key in ("source_kind", "source", "local_id")
        }
        for item in source_map["mappings"]
    }
    detector_ids = sorted(
        {
            item["source"]
            for item in source_map["mappings"]
            if item["source_kind"] == "detector"
        }
    )
    detector_count = len(detector_ids)
    if detector_count == 0:
        raise EnsembleError("Audit source map contains no detector sources")
    match_by_cluster = {
        item["cluster_id"]: item for item in prompt_bound_matches["matches"]
    }
    accepted_inventory = [
        cluster for cluster in decisions["clusters"] if cluster["decision"] == "accept"
    ]
    accepted_inventory.sort(
        key=lambda cluster: (
            min(item["frame_id"] for item in cluster["adjudicator_evidence"]),
            cluster["canonical_name"].casefold(),
            cluster["cluster_id"],
        )
    )
    accepted = [
        cluster
        for cluster in accepted_inventory
        if match_by_cluster[cluster["cluster_id"]]["status"] == "unbound"
    ]
    assigned_ids = {
        cluster["cluster_id"]: f"e{index}"
        for index, cluster in enumerate(accepted, start=1)
    }
    final_entities: List[Dict[str, Any]] = []
    grounding_frame_ids_by_entity: Dict[str, List[int]] = {}
    for cluster in accepted:
        entity_id = assigned_ids[cluster["cluster_id"]]
        final_entities.append(
            {
                "id": entity_id,
                **cluster["final_entity"],
            }
        )
        grounding_frame_ids_by_entity[entity_id] = [
            item["frame_id"]
            for item in cluster["frame_presence"]
            if item["status"] == "visible"
        ]

    audit_clusters: List[Dict[str, Any]] = []
    for cluster in decisions["clusters"]:
        final_proposals = set(cluster["anonymous_proposal_ids"])
        matching_target_ids = sorted(
            target_id
            for target_id, proposal_ids in target_proposals.items()
            if final_proposals & proposal_ids
        )
        matching_reasons = sorted(
            {
                reason
                for target_id in matching_target_ids
                for reason in verification_target_reasons[target_id]
            }
        )
        matching_reviews = [
            review
            for target_id in matching_target_ids
            for review in verifier_reviews.get(target_id, [])
        ]
        members = [
            sources[proposal_id] for proposal_id in cluster["anonymous_proposal_ids"]
        ]
        detector_sources = {
            member["source"]
            for member in members
            if member["source_kind"] == "detector"
        }
        proposal_count = len(detector_sources)
        inventory_decision = cluster["decision"]
        prompt_check = (
            match_by_cluster[cluster["cluster_id"]]
            if inventory_decision == "accept"
            else None
        )
        if inventory_decision == "accept" and prompt_check["status"] == "unbound":
            projection_decision = "accept"
            projection_reason = prompt_check["reason"]
        elif inventory_decision == "accept" and prompt_check["status"] == "bound":
            projection_decision = "reject"
            projection_reason = (
                "Excluded from the prompt-unbound projection: " + prompt_check["reason"]
            )
        elif inventory_decision == "accept":
            projection_decision = "abstain"
            projection_reason = (
                "Prompt-bound membership is ambiguous: " + prompt_check["reason"]
            )
        else:
            projection_decision = inventory_decision
            projection_reason = cluster["decision_reason"]
        final_id = assigned_ids.get(cluster["cluster_id"])
        final_entity = (
            {"id": final_id, **cluster["final_entity"]}
            if final_id is not None
            else None
        )
        audit_clusters.append(
            {
                "cluster_id": cluster["cluster_id"],
                "canonical_name": cluster["canonical_name"],
                "aliases": cluster["aliases"],
                "members": members,
                "agreement": {
                    "proposal_count": proposal_count,
                    "denominator": detector_count,
                    "label": f"{proposal_count}/{detector_count}",
                },
                "granularity": cluster["granularity"],
                "adjudicator_evidence": cluster["adjudicator_evidence"],
                "frame_presence": cluster["frame_presence"],
                "prompt_bound_check": prompt_check,
                "identity_status": cluster["identity_status"],
                "inventory_decision": inventory_decision,
                "inventory_decision_reason": cluster["decision_reason"],
                "decision": projection_decision,
                "decision_reason": projection_reason,
                "reject_or_abstain_reason": (
                    projection_reason
                    if projection_decision != "accept"
                    else None
                ),
                "uncertainty_flags": cluster["uncertainty_flags"],
                "targeted_verification": {
                    "required": bool(matching_target_ids),
                    "initial_cluster_ids": matching_target_ids,
                    "trigger_reasons": matching_reasons,
                    "reports": matching_reviews,
                },
                "frozen_inventory_entity": (
                    cluster["final_entity"] if inventory_decision == "accept" else None
                ),
                "final_entity_id": final_id,
                "final_entity": final_entity,
                "confidence_basis": {
                    "calibration": "uncalibrated",
                    "basis": (
                        "adjudicator visual support plus targeted verifier reports, "
                        "not proposal count"
                        if matching_target_ids
                        else "adjudicator visual support, not proposal count"
                    ),
                },
            }
        )
    inventory_counts = {
        decision: sum(
            cluster["decision"] == decision for cluster in decisions["clusters"]
        )
        for decision in ("accept", "reject", "abstain")
    }
    match_counts = {
        status: sum(
            item["status"] == status for item in prompt_bound_matches["matches"]
        )
        for status in ("bound", "unbound", "ambiguous")
    }
    audit = {
        "protocol_version": PROTOCOL_VERSION,
        "shot_id": shot_id,
        "detector_count_expected": len(DETECTOR_ROLES),
        "detector_count_valid": detector_count,
        "candidate_clusters": audit_clusters,
        "accounting": {
            "union_cluster_count": len(audit_clusters),
            "inventory_accepted_count": inventory_counts["accept"],
            "inventory_rejected_count": inventory_counts["reject"],
            "inventory_abstained_count": inventory_counts["abstain"],
            "prompt_bound_count": match_counts["bound"],
            "prompt_unbound_count": match_counts["unbound"],
            "prompt_bound_ambiguous_count": match_counts["ambiguous"],
            "accepted_count": match_counts["unbound"],
            "rejected_count": inventory_counts["reject"] + match_counts["bound"],
            "abstained_count": (
                inventory_counts["abstain"] + match_counts["ambiguous"]
            ),
            "all_clusters_accounted_for": (
                len(audit_clusters) == sum(inventory_counts.values())
            ),
            "all_accepted_inventory_clusters_matched": (
                inventory_counts["accept"] == sum(match_counts.values())
            ),
        },
        "grounding_frame_ids_by_entity": grounding_frame_ids_by_entity,
        "warnings": [
            *decisions.get("warnings", []),
            *prompt_bound_matches.get("warnings", []),
            "Proposal agreement is a stability signal, not calibrated probability.",
            (
                "Detector-local IDs remain hidden from model calls; only the inventory "
                "adjudicator role sees fixed homogeneous detector-panel membership. "
                "This Codex CLI sandbox does not provide a filesystem read allowlist."
            ),
            "The inventory adjudicator cannot add candidates absent from the detector union.",
            "Prompt-bound matching occurs only after the all-entity inventory freezes.",
        ],
    }
    semantics = {
        "entities": final_entities,
        "relations": [],
        "warnings": [
            "Entity confidence is adjudicator-reported and not calibrated.",
            "Prompt-bound membership was classified after inventory freeze.",
            "Relations are intentionally deferred until entity IDs are frozen.",
        ],
    }
    return audit, semantics


def run_ensemble_detection(
    *,
    sample: shot_graph.VideoSample,
    shot_id: str,
    prompt_entities: Sequence[Mapping[str, Any]],
    run_dir: Path,
    codex_bin: str,
    model: Optional[str],
    timeout_sec: int,
    max_workers: int = 4,
    shuffle_seed: int = 1729,
    skill_dir: Path = DEFAULT_SKILL_DIR,
    detector_closure_max_rounds: int = 0,
    generic_identity_support_scope: str = "nonmajority",
    identity_review_policy: str = "legacy",
    revision_output_policy: str = "canonical",
    verbose: bool = False,
    review_model: Optional[str] = None,
    scope_retention_policy: str = "disabled",
) -> EnsembleResult:
    """Run four homogeneous detectors and evidence-only adjudication for one shot."""
    try:
        model_routing = model_routing_stage.resolve_model_routing(model, review_model)
    except ValueError as exc:
        raise EnsembleError(str(exc)) from exc
    review_call_model = model if model_routing is None else model_routing["effective_review_model"]

    def model_context(role, role_id, attempt, *, round_index=None, initial_request=None):
        return model_routing_stage.request_context(
            model_routing, role=role, role_id=role_id, attempt=attempt, shot_id=shot_id,
            round_index=round_index, initial_request=initial_request,
        )
    if not 1 <= max_workers <= 4:
        raise EnsembleError("ensemble max_workers must be in [1, 4]")
    if not 0 <= detector_closure_max_rounds <= 4:
        raise EnsembleError("detector closure max rounds must be in [0, 4]")
    if generic_identity_support_scope not in {"nonmajority", "all_support"}:
        raise EnsembleError("invalid generic identity support scope")
    if identity_review_policy not in {"legacy", "physical_v0.6"}:
        raise EnsembleError("invalid physical identity review policy")
    if revision_output_policy not in {"canonical", "implicit_owner_wire_v0.1"}:
        raise EnsembleError("invalid revision output policy")
    if scope_retention_policy not in {"disabled", SCOPE_RETENTION_POLICY}:
        raise EnsembleError("invalid scope retention policy")
    physical_review = identity_review_policy == "physical_v0.6"
    retention_enabled = scope_retention_policy != "disabled"
    if retention_enabled and not physical_review:
        raise EnsembleError("scope retention requires physical_v0.6")
    wire_revision = revision_output_policy == "implicit_owner_wire_v0.1"
    if wire_revision and not physical_review:
        raise EnsembleError("implicit_owner_wire_v0.1 requires physical_v0.6")
    identity_review = None
    pending_review_audit = None
    context_projection = None
    context_review_audit = None
    obligation_review = None
    revision_wire = None
    retention_transport = None
    retention_stage = None
    retention_consensus = None
    retention_public_review = None
    retention_policy_text = None
    retention_transition = None
    if physical_review:
        import physical_identity_review as identity_review
        import pending_identity_review_audit as pending_review_audit
        import initial_context_quarantine as context_projection
        import initial_context_review_audit as context_review_audit
        import physical_review_obligations as obligation_review
    if wire_revision:
        import physical_revision_wire as revision_wire
    if retention_enabled:
        import scope_retention_transport as retention_transport
        import proposal_scope_retention as retention_stage
        if retention_transport.POLICY_VERSION != SCOPE_RETENTION_POLICY or retention_stage.POLICY_VERSION != SCOPE_RETENTION_POLICY:
            raise EnsembleError("Scope retention policy/helper version mismatch")
    adjudication_schema = (
        PROJECT_ROOT / "schemas/codex_entity_adjudication_v0.6.schema.json"
        if physical_review else ADJUDICATION_SCHEMA
    )
    verification_schema = (
        PROJECT_ROOT / "schemas/codex_entity_verification_v0.6.schema.json"
        if physical_review else VERIFICATION_SCHEMA
    )
    core_verification_schema = verification_schema
    if retention_enabled:
        verification_schema = retention_transport.SCHEMA_PATH
    revision_schema = revision_wire.SCHEMA_PATH if wire_revision else adjudication_schema
    revision_fields_instruction = (
        _revision_identity_fields_instruction(identity_review, revision_output_policy)
        if physical_review else None
    )
    # Validate all later roles before paying for the first detector panel.
    selected_schemas = (
        DETECTOR_SCHEMA, adjudication_schema, verification_schema,
        MATCHING_SCHEMA, GRANULARITY_FAMILY_SCHEMA, ACCEPTED_ASSEMBLY_SCHEMA,
    )
    if detector_closure_max_rounds:
        selected_schemas += (detector_closure_stage.SCHEMA_PATH,)
    if wire_revision:
        selected_schemas += (revision_schema,)
    if retention_enabled:
        selected_schemas += (core_verification_schema,)
    schema_payloads = {path: validate_codex_schema_transport(path) for path in selected_schemas}
    if wire_revision and (
        schema_payloads[revision_schema] != revision_wire.WIRE_SCHEMA
        or schema_payloads[adjudication_schema] != revision_wire.CANONICAL_SCHEMA
    ):
        raise EnsembleError("Loaded wire materializer schemas differ from selected schema files")
    identity_schema_validators = {}
    if physical_review:
        import jsonschema
        for label, path in (("adjudication", adjudication_schema), ("verification", verification_schema)):
            schema = schema_payloads[path]
            jsonschema.Draft202012Validator.check_schema(schema)
            identity_schema_validators[label] = jsonschema.Draft202012Validator(schema)

    def validate_inventory_structure(payload, proposal_ids):
        try:
            if physical_review:
                identity_schema_validators["adjudication"].validate(payload)
            validate_decisions(payload, shot_id=shot_id, anonymous_ids=proposal_ids,
                               valid_frame_ids=sample.reference_frame_ids)
        except Exception as error:
            raise EnsembleError(str(error)) from error

    def validate_inventory_payload(payload, proposal_ids):
        validate_inventory_structure(payload, proposal_ids)
        try:
            if physical_review:
                identity_review.validate_adjudication_identity_fields(
                    payload, valid_frame_ids=sample.reference_frame_ids,
                    expected_proposal_ids=proposal_ids,
                )
        except Exception as error:
            raise EnsembleError(str(error)) from error
    started = time.perf_counter()
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "run_manifest.json"
    manifest: Dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "status": "running",
        "start_utc": _utc_now(),
        "shot_id": shot_id,
        "model": model,
        **({"model_routing": copy.deepcopy(model_routing)} if model_routing is not None else {}),
        "codex_cli_version": _codex_version(codex_bin),
        "ensemble_max_workers": max_workers,
        "shuffle_seed": shuffle_seed,
        "detector_closure_max_rounds": detector_closure_max_rounds,
        "generic_identity_support_scope": generic_identity_support_scope,
        "identity_review_policy": identity_review_policy,
        "revision_output_policy": revision_output_policy,
        **({"scope_retention_policy": scope_retention_policy,
            "scope_retention": {"policy_version": scope_retention_policy,
                                "status": "not_reached", "enabled": True}}
           if retention_enabled else {}),
        "detector_roles": [role for role, _, _ in DETECTOR_ROLES],
        "detector_method": HOMOGENEOUS_SCAN_VARIANT,
        "box_redundancy_policy": {
            "scope": "within_detector_only",
            "spatial_match_metric": "tight_box_iou_not_containment",
            "iou_threshold": BOX_REDUNDANCY_IOU_THRESHOLD,
            "minimum_visible_frames": BOX_REDUNDANCY_MIN_VISIBLE_FRAMES,
            "coverage_meaning": "fraction_of_visible_frames_with_high_iou",
            "coverage_threshold": BOX_REDUNDANCY_COVERAGE_THRESHOLD,
            "effect": "mandatory_review_no_automatic_delete",
        },
        "intra_cluster_spatial_split_policy": {
            "scope": "within_initial_cluster_only",
            "trigger": "persistent_divergent_anonymous_proposal_footprints",
            "maximum_iou": INTRA_CLUSTER_DIVERGENCE_MAX_IOU,
            "maximum_smaller_box_coverage": (
                INTRA_CLUSTER_DIVERGENCE_MAX_SMALLER_BOX_COVERAGE
            ),
            "minimum_covisible_frames": (
                INTRA_CLUSTER_DIVERGENCE_MIN_COVISIBLE_FRAMES
            ),
            "minimum_divergence_ratio": (
                INTRA_CLUSTER_DIVERGENCE_COVERAGE_THRESHOLD
            ),
            "proposal_boxes_are_review_triggers_only": True,
            "source_or_detector_count_used": False,
            "required_decision": (
                "exact_two_verifier_proposal_partition_consensus_then_"
                "persistent_adjudicator_pixel_review"
            ),
            "automatic_split": False,
        },
        "granularity_policy": {
            "physical_distinctness_separate_from_graph_partition": True,
            "compact_local_assembly_default": (
                "preserve_frozen_baseline_without_positive_cohesion_and_exact_consensus"
            ),
            "explicit_group_member_stage_authority": (
                "candidate_scope_audit_and_provisional_application_only"
            ),
            "final_coarsening_requires_accepted_candidate_second_gate": True,
            "accepted_candidate_stage_baseline": (
                "frozen_post_inventory_pre_group_baseline"
            ),
            "split_requires_shot_observed_independence": [
                "separate_handling_or_use",
                "detachment_or_standalone_state",
                "relative_motion",
                "independent_trajectory",
            ],
            "large_general_host_exception": True,
            "merged_constituents_preserved_as_attributes": True,
            "unresolved_partition": "one_broader_uncertain_node",
        },
        "single_detector_consensus_policy": {
            "trigger": "exactly_one_distinct_detector_source",
            "required_verifier_result": (
                "all isolated verifiers confirm both existence and graph worthiness "
                "at the exact final physical-unit scope"
            ),
            "initial_target_overlap_is_unit_confirmation": False,
            "failure_result": "abstain",
            "proposal_support_is_visual_proof": False,
        },
        "detector_attempts": [],
        "adjudicator_initial_attempts": [],
        "adjudicator_revision_attempts": [],
        "granularity_family_attempts": [],
        "empty_supported_anchor_policy": family_stage.EMPTY_SUPPORTED_ANCHOR_POLICY,
        "accepted_compact_assembly_attempts": [],
        "accepted_reference_coverage_policy": (
            accepted_assembly_stage.REFERENCE_COVERAGE_POLICY
        ),
        "verifier_attempts": [],
        "matcher_attempts": [],
        "artifacts": {},
        "isolation": {
            "detector_context": "separate ephemeral Codex threads",
            "detector_method_parity": "same prompt method; detector_id differs",
            "detector_model_visible_policy": "standalone detector-only reference",
            "detector_full_downstream_skill_visible": False,
            "detector_coverage_audit_downstream_visible": False,
            "adjudicator_candidate_boundary": "detector union only; no additions",
            "inventory_adjudicator_panel_visibility": (
                "fixed detector labels and anonymous proposal membership only"
            ),
            "verifier_panel_membership_visible": False,
            "verifier_source_or_detector_count_visible": False,
            "granularity_planner_panel_membership_visible": False,
            "inventory_registry_boundary": (
                "prompt-bound registry withheld from detectors, inventory "
                "adjudicator, and verifiers"
            ),
            "matcher_authority": "classification only over frozen accepted inventory",
            "matcher_registry": "semantic fields only; detector boxes/status withheld",
            "agent_source_blinding": (
                "detector-local IDs withheld from downstream roles; own-source residual "
                "closure sees only its own IDs. The private source-map file is withheld; "
                "fixed panel membership visible only to the inventory "
                "adjudicator"
            ),
            "granularity_family_source_blinding": (
                "two isolated planners with identical same-shot frames and "
                "source-blind inventory only"
            ),
            "accepted_compact_assembly_source_blinding": (
                "same-shot frames, accepted-only source-blind inventory, and a "
                "public mandatory candidate bank without proposal IDs, derivation, "
                "boxes, panels, or counts"
            ),
            "filesystem_read_allowlist_enforced": False,
        },
    }
    _atomic_write_json(manifest_path, manifest)
    usages: List[Optional[Dict[str, Optional[int]]]] = []
    detector_invocations = 0
    adjudicator_invocations = 0
    verifier_invocations = 0
    matcher_invocations = 0
    granularity_invocations = 0
    try:
        attachments, registry_path, semantic_registry_path, shot_manifest = (
            _copy_input_bundle(
            sample=sample,
            shot_id=shot_id,
            prompt_entities=prompt_entities,
            run_dir=run_dir,
            )
        )
        semantic_registry = json.loads(
            semantic_registry_path.read_text(encoding="utf-8")
        )
        resolved_skill_dir = skill_dir.resolve()
        skill_text, skill_hashes = _load_skill(resolved_skill_dir)
        detector_policy_text, detector_policy_path, detector_policy_hash = (
            _load_detector_policy(resolved_skill_dir)
        )
        inventory_allowed_paths = [str(path) for path in attachments]
        matcher_allowed_paths = [
            *inventory_allowed_paths,
            str(semantic_registry_path),
        ]
        manifest["allowed_input_paths_by_role"] = {
            "detector": inventory_allowed_paths,
            "detector_closure": inventory_allowed_paths,
            "inventory_adjudicator": inventory_allowed_paths,
            "identity_verifier": inventory_allowed_paths,
            "granularity_family_planner": inventory_allowed_paths,
            "accepted_compact_assembly_planner": inventory_allowed_paths,
            "prompt_bound_matcher": matcher_allowed_paths,
        }
        manifest["input_hashes"] = {
            str(path): _sha256(path)
            for path in [*attachments, registry_path, semantic_registry_path]
        }
        manifest["skill_hashes"] = skill_hashes
        manifest["detector_policy"] = {
            "version": DETECTOR_POLICY_VERSION,
            "path": str(detector_policy_path),
            "sha256": detector_policy_hash,
            "model_visible_as_complete_role_policy": True,
            "full_downstream_skill_visible": False,
            "coverage_audit_downstream_visible": False,
        }
        manifest["schema_hashes"] = {
            str(DETECTOR_SCHEMA.resolve()): _sha256(DETECTOR_SCHEMA),
            str(adjudication_schema.resolve()): _sha256(adjudication_schema),
            str(verification_schema.resolve()): _sha256(verification_schema),
            str(MATCHING_SCHEMA.resolve()): _sha256(MATCHING_SCHEMA),
            str(GRANULARITY_FAMILY_SCHEMA.resolve()): _sha256(
                GRANULARITY_FAMILY_SCHEMA
            ),
            str(ACCEPTED_ASSEMBLY_SCHEMA.resolve()): _sha256(
                ACCEPTED_ASSEMBLY_SCHEMA
            ),
        }
        manifest["stage_source_hashes"] = {
            str(Path(family_stage.__file__).resolve()): _sha256(
                Path(family_stage.__file__).resolve()
            ),
            str(Path(accepted_assembly_stage.__file__).resolve()): _sha256(
                Path(accepted_assembly_stage.__file__).resolve()
            ),
        }
        if model_routing is not None:
            routing_source = Path(model_routing_stage.__file__).resolve()
            manifest["stage_source_hashes"][str(routing_source)] = _sha256(routing_source)
        if wire_revision:
            manifest["schema_hashes"][str(revision_schema.resolve())] = _sha256(revision_schema)
            wire_source = Path(revision_wire.__file__).resolve()
            manifest["stage_source_hashes"][str(wire_source)] = _sha256(wire_source)
            manifest["revision_output_contract"] = {
                "policy": revision_output_policy,
                "materialization_policy": revision_wire.POLICY_VERSION,
                "initial_schema": str(adjudication_schema.resolve()),
                "revision_model_output_schema": str(revision_schema.resolve()),
                "materialized_schema": str(adjudication_schema.resolve()),
                "raw_output_preserved": True,
                "strict_raw_json_text_entry": True,
                "canonical_base_deferred_split_and_gate_required": True,
            }
        if retention_enabled:
            reference = resolved_skill_dir / SCOPE_RETENTION_REFERENCE
            retention_policy_text = reference.read_text(encoding="utf-8")
            manifest["skill_hashes"][str(reference.resolve())] = _sha256(reference)
            manifest["schema_hashes"][str(core_verification_schema.resolve())] = _sha256(core_verification_schema)
            for module in (retention_transport, retention_stage):
                source = Path(module.__file__).resolve()
                manifest["stage_source_hashes"][str(source)] = _sha256(source)
            manifest["scope_retention"].update({
                "verifier_schema": str(verification_schema.resolve()),
                "core_verifier_schema": str(core_verification_schema.resolve()),
                "reference": {"path": str(reference.resolve()), "sha256": _sha256(reference)},
                "raw_reports_preserved": True, "projection_is_original_report": False,
                "private_provenance_model_visible": False, "automatic_acceptance": False,
            })
        verifier_policy_text = None
        if physical_review:
            manifest["distinct_revision_proof_policy"] = identity_review.DISTINCT_REVISION_PROOF_POLICY
            verifier_policy_path = resolved_skill_dir / identity_review.VERIFIER_POLICY_RELATIVE_PATH
            verifier_policy_text = verifier_policy_path.read_text(encoding="utf-8")
            manifest["skill_hashes"][str(verifier_policy_path.resolve())] = _sha256(verifier_policy_path)
            identity_source = Path(identity_review.__file__).resolve()
            manifest["stage_source_hashes"][str(identity_source)] = _sha256(identity_source)
            pending_audit_source = Path(pending_review_audit.__file__).resolve()
            manifest["stage_source_hashes"][str(pending_audit_source)] = _sha256(pending_audit_source)
            for module in (context_projection, context_review_audit, obligation_review):
                source = Path(module.__file__).resolve()
                manifest["stage_source_hashes"][str(source)] = _sha256(source)
            manifest["first_revision_obligation_preview"] = {
                "policy_version": obligation_review.FIRST_REVISION_PREVIEW_POLICY,
                "enabled": True, "status": "not_reached",
                "included_in_revision_prompt": False,
                "partial_current_scope_only": True,
            }
            manifest["initial_evidence_preparation"] = {
                "version": "initial_context_then_pending_v0.2",
                "context_policy": context_projection.POLICY_VERSION,
                "pending_policy": identity_review.INITIAL_PREPARATION_VERSION,
                "raw_output_preserved": True, "final_and_verifier_validators_unchanged": True,
            }
            manifest["verifier_policy"] = {
                "version": identity_review.SCHEMA_VERSION,
                "path": str(verifier_policy_path.resolve()),
                "sha256": _sha256(verifier_policy_path),
                "full_downstream_skill_visible": False,
                "prior_adjudicator_verdict_visible": False,
            }
        if detector_closure_max_rounds:
            manifest["schema_hashes"][str(detector_closure_stage.SCHEMA_PATH.resolve())] = _sha256(detector_closure_stage.SCHEMA_PATH)
            manifest["stage_source_hashes"][str(Path(detector_closure_stage.__file__).resolve())] = _sha256(Path(detector_closure_stage.__file__))
        _atomic_write_json(manifest_path, manifest)
        base = _inventory_base_prompt(
            shot_id=shot_id,
            shot_manifest=shot_manifest,
            allowed_input_paths=inventory_allowed_paths,
            skill_text=skill_text,
        )
        detector_base = _detector_base_prompt(
            shot_id=shot_id,
            shot_manifest=shot_manifest,
            allowed_input_paths=inventory_allowed_paths,
            detector_policy_text=detector_policy_text,
        )
        agent_work_dir = run_dir / "agent_workdirs"
        inventory_work_dir = agent_work_dir / "inventory"
        matcher_work_dir = agent_work_dir / "matcher"
        family_work_dirs = [
            agent_work_dir / f"granularity_group_member_planner_{index}"
            for index in (1, 2)
        ]
        accepted_assembly_work_dirs = [
            agent_work_dir / f"accepted_compact_assembly_planner_{index}"
            for index in (1, 2)
        ]
        inventory_work_dir.mkdir(parents=True, exist_ok=False)
        matcher_work_dir.mkdir(parents=True, exist_ok=False)
        for work_dir in family_work_dirs:
            work_dir.mkdir(parents=True, exist_ok=False)
        for work_dir in accepted_assembly_work_dirs:
            work_dir.mkdir(parents=True, exist_ok=False)
        prompt_dir = run_dir / "prompts"
        attempt_dir = run_dir / "codex_attempts"
        detector_dir = run_dir / "detector_runs"
        detector_dir.mkdir(parents=True, exist_ok=False)

        def invoke_detector(
            role_data: Tuple[str, str, str], attempt: int
        ) -> Tuple[
            str,
            Optional[Dict[str, Any]],
            Optional[CodexInvocation],
            Optional[BaseException],
        ]:
            role, _, instruction = role_data
            prefix = f"{role}.attempt{attempt}"
            prompt = _detector_prompt(detector_base, role, instruction)
            _atomic_write_text(prompt_dir / f"{prefix}.txt", prompt)
            output_path = attempt_dir / f"{prefix}.json"
            events_path = attempt_dir / f"{prefix}.events.jsonl"
            invocation: Optional[CodexInvocation] = None
            try:
                invocation = run_codex_json(
                    prompt=prompt,
                    attachments=attachments,
                    schema_path=DETECTOR_SCHEMA,
                    **model_routing_stage.request_kwargs(model_context("detector", role, attempt)),
                    output_path=output_path,
                    events_path=events_path,
                    stderr_path=attempt_dir / f"{prefix}.stderr.log",
                    codex_bin=codex_bin,
                    model=model,
                    timeout_sec=timeout_sec,
                    work_dir=inventory_work_dir,
                    verbose=verbose,
                )
                validate_ledger(
                    invocation.payload,
                    shot_id=shot_id,
                    detector_id=role,
                    source_kind="detector",
                    valid_frame_ids=sample.reference_frame_ids,
                    allowed_input_paths=inventory_allowed_paths,
                )
                return role, invocation.payload, invocation, None
            except (EnsembleError, OSError) as exc:
                return role, None, invocation, exc

        ledgers: Dict[str, Dict[str, Any]] = {}
        pending = list(DETECTOR_ROLES)
        for attempt in (1, 2):
            if not pending:
                break
            attempt_started = time.perf_counter()
            print(
                f"[ensemble {shot_id}] detectors attempt {attempt}: "
                f"starting {len(pending)} parallel calls",
                flush=True,
            )
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(max_workers, len(pending))
            ) as executor:
                futures = [
                    executor.submit(invoke_detector, role_data, attempt)
                    for role_data in pending
                ]
                detector_invocations += len(futures)
                outcomes = [future.result() for future in futures]
            valid_count = sum(payload is not None for _, payload, _, _ in outcomes)
            print(
                f"[ensemble {shot_id}] detectors attempt {attempt}: "
                f"{valid_count}/{len(outcomes)} valid "
                f"({time.perf_counter() - attempt_started:.1f}s)",
                flush=True,
            )
            next_pending = []
            for role, payload, invocation, error in outcomes:
                events_path = attempt_dir / f"{role}.attempt{attempt}.events.jsonl"
                accounting = _codex_attempt_accounting(
                    invocation=invocation,
                    error=error,
                    events_path=events_path,
                    **model_routing_stage.request_kwargs(model_context("detector", role, attempt)),
                )
                manifest["detector_attempts"].append(
                    {
                        "detector_id": role,
                        "attempt": attempt,
                        "status": "success" if payload is not None else "failed",
                        "error": str(error) if error is not None else None,
                        **accounting,
                    }
                )
                if accounting["subprocess_started"] or accounting.get("subprocess_start_unknown"):
                    usages.append(accounting["token_usage"])
                if payload is None:
                    next_pending.append(
                        next(item for item in DETECTOR_ROLES if item[0] == role)
                    )
                    continue
                ledgers[role] = payload
                canonical_path = detector_dir / f"{role}.json"
                _atomic_write_json(canonical_path, payload)
            pending = next_pending
            manifest["prompt_hashes"] = {
                path.name: _sha256(path) for path in sorted(prompt_dir.glob("*.txt"))
            }
            _atomic_write_json(manifest_path, manifest)

        if len(ledgers) != len(DETECTOR_ROLES):
            missing = [role for role, _, _ in DETECTOR_ROLES if role not in ledgers]
            manifest.update(
                {
                    "status": "incomplete",
                    "end_utc": _utc_now(),
                    "runtime_seconds": round(time.perf_counter() - started, 6),
                    "error": f"Missing valid detector ledgers after retry: {missing}",
                    "detector_invocations": detector_invocations,
                    "adjudicator_invocations": adjudicator_invocations,
                    "verifier_invocations": verifier_invocations,
                    "matcher_invocations": matcher_invocations,
                    "granularity_invocations": granularity_invocations,
                    "token_usage": _aggregate_usage(usages),
                }
            )
            _atomic_write_json(manifest_path, manifest)
            raise EnsembleIncompleteError(manifest["error"])

        ordered_ledgers = [ledgers[role] for role, _, _ in DETECTOR_ROLES]
        manifest["artifacts"]["detector_ledgers"] = {
            role: {
                "path": str((detector_dir / f"{role}.json").resolve()),
                "sha256": _sha256(detector_dir / f"{role}.json"),
            }
            for role, _, _ in DETECTOR_ROLES
        }
        coverage_diagnostics = {
            "protocol_version": PROTOCOL_VERSION,
            "shot_id": shot_id,
            "private": True,
            "downstream_visible": False,
            "effect": "diagnostic_only_no_retry_no_evidence_no_vote",
            "detectors": [
                {
                    "detector_id": ledger["detector_id"],
                    **_validate_detector_coverage_audit(
                        ledger["coverage_audit"],
                        detector_id=ledger["detector_id"],
                        valid_frame_ids=sample.reference_frame_ids,
                        valid_local_ids={
                            entity["local_id"] for entity in ledger["entities"]
                        },
                    ),
                }
                for ledger in ordered_ledgers
            ],
        }
        coverage_diagnostics_path = (
            detector_dir / "coverage_diagnostics.private.json"
        )
        _atomic_write_json(coverage_diagnostics_path, coverage_diagnostics)
        manifest["artifacts"]["detector_coverage_diagnostics"] = {
            "path": str(coverage_diagnostics_path.resolve()),
            "sha256": _sha256(coverage_diagnostics_path),
            "private": True,
            "downstream_visible": False,
        }
        manifest["detector_coverage_diagnostics"] = {
            "status": "recorded",
            "private": True,
            "downstream_visible": False,
            "detectors_with_nonfatal_cross_index_omissions": [
                item["detector_id"]
                for item in coverage_diagnostics["detectors"]
                if item["has_nonfatal_cross_index_omissions"]
            ],
        }

        if detector_closure_max_rounds:
            print(
                f"[ensemble {shot_id}] detector residual closure: "
                f"up to {detector_closure_max_rounds} own-ledger rounds",
                flush=True,
            )
            closure = detector_closure_stage.run_stage(
                ledgers=ordered_ledgers,
                shot_id=shot_id,
                valid_frame_ids=sample.reference_frame_ids,
                allowed_input_paths=inventory_allowed_paths,
                attachments=attachments,
                detector_policy_text=detector_policy_text,
                shot_manifest=shot_manifest,
                run_dir=run_dir,
                max_rounds=detector_closure_max_rounds,
                max_workers=max_workers,
                invoke_json=run_codex_json,
                validate_ledger=validate_ledger,
                account_attempt=_codex_attempt_accounting,
                **({"request_context_factory": lambda source, round_index, attempt: model_context(
                    "detector_closure", source, attempt, round_index=round_index,
                )} if model_routing is not None else {}),
                invocation_kwargs={
                    "codex_bin": codex_bin,
                    "model": model,
                    "timeout_sec": timeout_sec,
                    "verbose": verbose,
                },
            )
            detector_invocations += closure["invocations"]
            usages.extend(closure["token_usages"])
            manifest["detector_closure"] = {
                "version": detector_closure_stage.STAGE_VERSION,
                "status": closure["status"],
                "converged": closure["converged"],
                "budget_exhausted_sources": closure["budget_exhausted_sources"],
                "stop_policy": closure["stop_policy"],
                "source_count": len(DETECTOR_ROLES),
                "additional_independent_voters": 0,
                "invocations": closure["invocations"],
                "attempts": closure["attempts"],
                "source_audits": closure["source_audits"],
                "audit_path": str(run_dir / "detector_closure" / "stage_audit.json"),
                "model_visible_downstream": False,
            }
            manifest["detector_invocations"] = detector_invocations
            manifest["token_usage"] = _aggregate_usage(usages)
            if closure["status"] != "complete":
                manifest.update({
                    "status": "incomplete",
                    "end_utc": _utc_now(),
                    "runtime_seconds": round(time.perf_counter() - started, 6),
                    "error": "Detector residual discovery failed to return valid deltas for every source",
                })
                _atomic_write_json(manifest_path, manifest)
                raise EnsembleIncompleteError(manifest["error"])
            if closure["budget_exhausted_sources"]:
                print(
                    f"[ensemble {shot_id}] residual search budget reached for "
                    f"{len(closure['budget_exhausted_sources'])} sources; "
                    "valid candidates proceed to adjudication with coverage still open",
                    flush=True,
                )
            ordered_ledgers = closure["ledgers"]
            if [item["detector_id"] for item in ordered_ledgers] != [role for role, _, _ in DETECTOR_ROLES]:
                raise EnsembleError("Residual closure changed the detector roster or order")
            _atomic_write_json(manifest_path, manifest)

        adjudication_dir = run_dir / "adjudication"
        adjudication_dir.mkdir(parents=True, exist_ok=False)
        anonymous_view, source_map = anonymize_proposals(
            ordered_ledgers, shot_id=shot_id, seed=shuffle_seed
        )
        box_redundancy_challenges = build_box_redundancy_challenges(
            anonymous_view, source_map
        )
        anonymous_view["box_redundancy_challenges"] = box_redundancy_challenges
        manifest["box_redundancy_policy"]["challenge_count"] = len(
            box_redundancy_challenges
        )
        anonymous_path = adjudication_dir / "anonymized_candidates.json"
        source_map_path = adjudication_dir / "source_map.json"
        _atomic_write_json(anonymous_path, anonymous_view)
        manifest["artifacts"]["anonymized_candidates"] = {
            "path": str(anonymous_path.resolve()),
            "sha256": _sha256(anonymous_path),
        }
        _atomic_write_json(manifest_path, manifest)

        initial_prompt = _decision_prompt(
            base=base,
            shot_id=shot_id,
            anonymized_view=anonymous_view,
            valid_frame_ids=sample.reference_frame_ids,
        )
        if physical_review:
            initial_prompt += "\n\n" + identity_review.PHYSICAL_IDENTITY_RULE + "\n\n" + identity_review.ADJUDICATION_FIELDS_INSTRUCTION
        initial_prompt_path = prompt_dir / "adjudicator_initial.txt"
        _atomic_write_text(initial_prompt_path, initial_prompt)
        manifest["prompt_hashes"][initial_prompt_path.name] = _sha256(
            initial_prompt_path
        )
        initial_raw_path = attempt_dir / "adjudicator_initial.json"
        initial_events_path = attempt_dir / "adjudicator_initial.events.jsonl"
        print(
            f"[ensemble {shot_id}] adjudicator: clustering and reviewing "
            f"{len(anonymous_view['proposals'])} anonymized proposals "
            f"({len(box_redundancy_challenges)} box-redundancy challenges)",
            flush=True,
        )
        initial_call: Optional[CodexInvocation] = None
        initial_error: Optional[BaseException] = None
        initial_raw_contract_error: Optional[BaseException] = None
        initial_raw_contract_valid = False
        initial_payload: Optional[Dict[str, Any]] = None
        initial_identity_preparation: Optional[Dict[str, Any]] = None
        initial_context_payload: Optional[Dict[str, Any]] = None
        initial_context_preparation: Optional[Dict[str, Any]] = None
        initial_context_projection_audit: Optional[Dict[str, Any]] = None
        anonymous_ids = [
            proposal["anonymous_proposal_id"]
            for proposal in anonymous_view["proposals"]
        ]
        adjudicator_invocations += 1
        try:
            initial_call = run_codex_json(
                prompt=initial_prompt,
                attachments=attachments,
                schema_path=adjudication_schema,
                **model_routing_stage.request_kwargs(model_context("adjudicator_initial", "adjudicator_initial", 1)),
                output_path=initial_raw_path,
                events_path=initial_events_path,
                stderr_path=attempt_dir / "adjudicator_initial.stderr.log",
                codex_bin=codex_bin,
                model=review_call_model,
                timeout_sec=timeout_sec,
                work_dir=inventory_work_dir,
                persistent=True,
                verbose=verbose,
            )
            validate_inventory_structure(initial_call.payload, anonymous_ids)
            if physical_review:
                # Measure the actual raw contract separately from both derived
                # preparation steps. A legal wide context need not be a failed
                # raw call merely because it is kept outside the proof ledger.
                try:
                    validate_inventory_payload(initial_call.payload, anonymous_ids)
                    initial_raw_contract_valid = True
                except EnsembleError as exc:
                    initial_raw_contract_error = exc
                initial_context_payload, initial_context_preparation = (
                    context_projection.project_initial_context(
                        initial_call.payload, valid_frame_ids=sample.reference_frame_ids,
                        expected_proposal_ids=anonymous_ids,
                    )
                )
                initial_context_projection_audit = context_review_audit.audit_initial_context_projection(
                    initial_call.payload, initial_context_payload, initial_context_preparation,
                    valid_frame_ids=sample.reference_frame_ids,
                    expected_proposal_ids=anonymous_ids,
                )
                validate_inventory_structure(initial_context_payload, anonymous_ids)
                initial_payload, initial_identity_preparation = (
                    identity_review.prepare_initial_adjudication_for_review(
                        initial_context_payload, valid_frame_ids=sample.reference_frame_ids,
                        expected_proposal_ids=anonymous_ids,
                    )
                )
            else:
                initial_payload = initial_call.payload
            validate_inventory_payload(initial_payload, anonymous_ids)
            if not physical_review:
                initial_raw_contract_valid = True
        except (EnsembleError, OSError, ValueError) as exc:
            initial_error = exc
        initial_accounting = _codex_attempt_accounting(
            invocation=initial_call,
            error=initial_error or initial_raw_contract_error,
            events_path=initial_events_path,
            **model_routing_stage.request_kwargs(model_context("adjudicator_initial", "adjudicator_initial", 1)),
        )
        manifest["adjudicator_initial_attempts"].append(
            {
                "attempt": 1,
                "status": "failed" if initial_error is not None or initial_raw_contract_error is not None else "success",
                "error": (
                    str(initial_error or initial_raw_contract_error)
                    if initial_error is not None or initial_raw_contract_error is not None else None
                ),
                "recovery_status": (
                    ("initial_context_and_identity_review"
                     if initial_context_preparation and initial_context_preparation["quarantined_evidence"]
                     else "pending_identity_review")
                    if initial_error is None and initial_raw_contract_error is not None
                    else None
                ),
                "raw_contract_valid": initial_raw_contract_valid,
                "derived_contract_valid": initial_error is None and initial_payload is not None,
                **initial_accounting,
            }
        )
        if initial_accounting["subprocess_started"] or initial_accounting.get("subprocess_start_unknown"):
            usages.append(initial_accounting["token_usage"])
        _atomic_write_json(manifest_path, manifest)
        if initial_error is not None:
            raise EnsembleError(str(initial_error)) from initial_error
        if initial_call is None or initial_payload is None:
            raise EnsembleError("Initial adjudicator ended without a call result")
        initial_path = adjudication_dir / "adjudicator_initial.json"
        _atomic_write_json(initial_path, initial_payload)
        manifest["adjudicator_thread_id"] = initial_call.thread_id
        initial_request_binding = None
        if model_routing is not None:
            initial_request_path = model_routing_stage.request_path(initial_events_path)
            initial_request_binding = {"path": str(initial_request_path),
                                       "sha256": _sha256(initial_request_path),
                                       "thread_id": initial_call.thread_id}
        manifest["artifacts"]["adjudicator_initial"] = {
            "path": str(initial_path.resolve()),
            "sha256": _sha256(initial_path),
            "candidate_additions_allowed": False,
        }
        pending_input_path = initial_raw_path
        if initial_context_preparation is not None:
            pending_input_path = adjudication_dir / "initial_context_projection.json"
            for name, data in (
                ("initial_context_projection", initial_context_payload),
                ("initial_context_quarantine", initial_context_preparation),
                ("initial_context_projection_audit", initial_context_projection_audit),
            ):
                path = adjudication_dir / f"{name}.json"
                _atomic_write_json(path, data)
                manifest["artifacts"][name] = {"path": str(path.resolve()), "sha256": _sha256(path)}
            manifest["initial_context_review"] = {
                "policy_version": initial_context_preparation["policy_version"],
                "raw_output_path": str(initial_raw_path.resolve()),
                "raw_output_sha256": _sha256(initial_raw_path),
                "raw_contract_valid": initial_raw_contract_valid,
                "quarantined_observation_count": len(initial_context_preparation["quarantined_evidence"]),
                "review_scope_ids": initial_context_preparation["review_scope_ids"],
                "proof_observations_created": False, "comparison_questions_created": False,
                "supplied_to_any_model": False, "pixel_truth_verified": False,
                "verifier_coverage_validation": "before_revision_with_existing_verifier_retry_v0.1",
            }
        if initial_identity_preparation is not None:
            initial_identity_preparation.update({
                "raw_output_path": str(pending_input_path.resolve()),
                "raw_output_sha256": _sha256(pending_input_path),
                "input_stage": "context_projection" if initial_context_preparation is not None else "raw_initial",
                "derived_output_path": str(initial_path.resolve()),
                "derived_output_sha256": _sha256(initial_path),
                "supplied_to_any_model": False,
                "raw_contract_valid": not bool(initial_identity_preparation["pending_comparisons"]),
            })
            preparation_path = adjudication_dir / "initial_identity_review_preparation.json"
            _atomic_write_json(preparation_path, initial_identity_preparation)
            manifest["artifacts"]["initial_identity_review_preparation"] = {
                "path": str(preparation_path.resolve()), "sha256": _sha256(preparation_path),
            }
            manifest["initial_identity_pending_review"] = {
                "policy_version": initial_identity_preparation["policy_version"],
                "pending_assertion_count": len(initial_identity_preparation["pending_comparisons"]),
                "raw_assertions_preserved": True, "new_observations_created": False,
            }

        identity_challenge_pairs = build_identity_challenge_pairs(
            initial_payload, anonymous_view, include_initial_comparisons=physical_review,
        )
        intra_cluster_split_challenges = (
            build_intra_cluster_divergent_footprint_challenges(
                initial_payload, anonymous_view
            )
        )
        target_ids, target_reasons = select_verification_targets(
            initial_payload,
            source_map,
            anonymous_view,
            intra_cluster_split_challenges,
            include_initial_comparisons=physical_review,
        )
        if initial_identity_preparation is not None:
            identity_challenge_pairs, target_ids, target_reasons = add_pending_identity_review_obligations(
                decisions=initial_payload,
                pending_comparisons=initial_identity_preparation["pending_comparisons"],
                identity_challenge_pairs=identity_challenge_pairs,
                target_ids=target_ids, target_reasons=target_reasons,
            )
        if initial_context_preparation is not None:
            target_ids, target_reasons = add_context_scope_review_obligations(
                decisions=initial_payload,
                review_scope_ids=initial_context_preparation["review_scope_ids"],
                target_ids=target_ids, target_reasons=target_reasons,
            )
        initial_declared_handoff = None
        if physical_review:
            verification_view = _verification_view(
                initial_payload, anonymous_view, target_ids, identity_challenge_pairs,
                intra_cluster_split_challenges,
            )
            initial_declared_handoff = audit_initial_declared_identity_handoff(initial_payload, verification_view)
            initial_declared_handoff.update({
                "initial_output_path": str(initial_path.resolve()), "initial_output_sha256": _sha256(initial_path),
            })
            manifest["initial_declared_identity_review"] = initial_declared_handoff
        weak_path = adjudication_dir / "verification_targets.json"
        _atomic_write_json(
            weak_path,
            {
                "protocol_version": PROTOCOL_VERSION,
                "shot_id": shot_id,
                "cluster_ids": target_ids,
                "trigger_reasons": target_reasons,
                "identity_challenge_pairs": identity_challenge_pairs,
                "intra_cluster_divergent_footprint_challenges": (
                    intra_cluster_split_challenges
                ),
                **({"initial_declared_identity_review": initial_declared_handoff} if physical_review else {}),
            },
        )
        manifest["artifacts"]["verification_targets"] = {
            "path": str(weak_path.resolve()),
            "sha256": _sha256(weak_path),
        }
        split_challenges_path = (
            adjudication_dir
            / "intra_cluster_divergent_footprint_challenges.json"
        )
        _atomic_write_json(
            split_challenges_path,
            {
                "protocol_version": PROTOCOL_VERSION,
                "shot_id": shot_id,
                "source_or_detector_count_used": False,
                "automatic_split": False,
                "challenges": intra_cluster_split_challenges,
            },
        )
        manifest["artifacts"]["intra_cluster_divergent_footprint_challenges"] = {
            "path": str(split_challenges_path.resolve()),
            "sha256": _sha256(split_challenges_path),
        }
        intra_cluster_split_consensus = build_intra_cluster_split_consensus(
            shot_id=shot_id,
            challenges=intra_cluster_split_challenges,
            verifier_reports=[],
        )
        split_revision_audit: Dict[str, Any] = {
            "automatic_split": False,
            "exact_consensus_required": True,
            "observed_split_count": 0,
            "observed_splits": [],
        }
        verifier_reports: Dict[str, Dict[str, Any]] = {}
        retention_raw_reports: Dict[str, Dict[str, Any]] = {}
        retention_report_sources: Dict[str, Dict[str, Any]] = {}
        retention_attempt_audits: Dict[str, Dict[str, Any]] = {}
        retention_eligible_parents = (
            _retention_eligible_parents(initial_payload, target_ids) if retention_enabled else []
        )
        if retention_enabled:
            manifest["scope_retention"]["eligible_parent_ids"] = retention_eligible_parents
        if target_ids:
            if not initial_call.thread_id:
                raise EnsembleError(
                    "Adjudicator did not report a resumable thread_id for verification"
                )
            if not physical_review:
                verification_view = _verification_view(
                    initial_payload,
                    anonymous_view,
                    target_ids,
                    identity_challenge_pairs,
                    intra_cluster_split_challenges,
                )

            verifier_retry_errors: Dict[str, str] = {}
            verifier_local_failures = set()

            def invoke_verifier(
                verifier_id: str, attempt: int
            ) -> Tuple[
                str,
                Optional[Dict[str, Any]],
                Optional[CodexInvocation],
                Optional[BaseException],
            ]:
                prefix = f"{verifier_id}.attempt{attempt}"
                if retention_enabled:
                    retention_attempt_audits[prefix] = {
                        "policy_version": scope_retention_policy,
                        "status": "not_projected", "artifacts": {},
                    }
                prompt = _verifier_prompt(
                    base=base,
                    shot_id=shot_id,
                    verifier_id=verifier_id,
                    verification_view=verification_view,
                    valid_frame_ids=sample.reference_frame_ids,
                )
                if physical_review:
                    prompt = identity_review.build_verifier_prompt(
                        shot_id=shot_id, verifier_id=verifier_id,
                        verification_view=verification_view,
                        valid_frame_ids=sample.reference_frame_ids,
                        reference_frames=shot_manifest["reference_frames"],
                        allowed_input_paths=inventory_allowed_paths,
                        policy_text=verifier_policy_text,
                    )
                    if initial_context_preparation and initial_context_preparation["review_scope_ids"]:
                        required_scopes = {
                            c["cluster_id"]: c["anonymous_proposal_ids"]
                            for c in initial_payload["clusters"]
                            if c["cluster_id"] in initial_context_preparation["review_scope_ids"]
                        }
                        prompt += (
                            "\n\nFor each original target listed below, include at least one "
                            "evidence observation whose anonymous_proposal_ids exactly equal "
                            "that target's full listed scope. Describe what the supplied images "
                            "support or leave unresolved about that scope. An unresolved cue "
                            "and uncertain judgments are allowed. Pair-union observations are "
                            "separate and do not replace this observation. Do not copy a "
                            "pair-union observation and merely shrink its proposal IDs.\n"
                            + json.dumps(required_scopes, ensure_ascii=False, sort_keys=True)
                        )
                    if retention_enabled:
                        prompt += ("\n\n" + retention_policy_text
                                   + "\n\nSelected scope_retention_policy: " + scope_retention_policy
                                   + "\neligible_parent_ids: "
                                   + json.dumps(retention_eligible_parents, ensure_ascii=False))
                if attempt > 1 and verifier_id in verifier_retry_errors:
                    if verifier_id in verifier_local_failures:
                        prompt += (
                            "\n\nThe preceding attempt could not be used because local "
                            "provenance verification or report persistence failed. This "
                            "is not a finding about your visual evidence. Return a complete "
                            "report for the same original targets under the same contract. "
                            "Do not change scope or certainty to address this local failure."
                        )
                    else:
                        prompt += (
                            "\n\nYour preceding report failed deterministic validation and "
                            "cannot be used. Return the complete report again for every "
                            "original target, correcting the stated contract violation. Do "
                            "not discover new entities or change scope merely to satisfy the "
                            "format. In particular, physical-identity targets and physically "
                            "distinct compact-assembly targets must remain disjoint. "
                            "Validation error:\n"
                            + verifier_retry_errors[verifier_id]
                        )
                _atomic_write_text(prompt_dir / f"{prefix}.txt", prompt)
                events_path = attempt_dir / f"{prefix}.events.jsonl"
                invocation: Optional[CodexInvocation] = None
                local_failure_stage = None
                try:
                    invocation = run_codex_json(
                        prompt=prompt,
                        attachments=attachments,
                        schema_path=verification_schema,
                        **model_routing_stage.request_kwargs(model_context("verifier", verifier_id, attempt)),
                        output_path=attempt_dir / f"{prefix}.json",
                        events_path=events_path,
                        stderr_path=attempt_dir / f"{prefix}.stderr.log",
                        codex_bin=codex_bin,
                        model=review_call_model,
                        timeout_sec=timeout_sec,
                        work_dir=inventory_work_dir,
                        verbose=verbose,
                    )
                    if physical_review:
                        identity_schema_validators["verification"].validate(invocation.payload)
                    core_report = invocation.payload
                    if retention_enabled:
                        core_report = retention_transport.validate_and_project_verifier(
                            invocation.payload, policy=scope_retention_policy,
                            initial_decisions=initial_payload,
                            valid_frame_ids=sample.reference_frame_ids,
                            eligible_parent_ids=retention_eligible_parents,
                        )
                        split_parents = {r["cluster_id"] for r in core_report["reviews"]
                                         if r["intra_cluster_split_judgment"] == "split_into_multiple_physical_instances"}
                        if split_parents.intersection(r["parent_cluster_id"] for r in invocation.payload["retention_requests"]):
                            raise EnsembleError("Retention request overlaps an ordinary physical split in the same report")
                        retention_attempt_audits[prefix]["status"] = "validated_in_memory"
                    validate_verifier_report(
                        core_report,
                        shot_id=shot_id,
                        verifier_id=verifier_id,
                        target_cluster_ids=target_ids,
                        all_cluster_ids=[
                            cluster["cluster_id"]
                            for cluster in initial_payload["clusters"]
                        ],
                        valid_frame_ids=sample.reference_frame_ids,
                        target_proposal_ids_by_cluster={
                            cluster["cluster_id"]: cluster[
                                "anonymous_proposal_ids"
                            ]
                            for cluster in initial_payload["clusters"]
                            if cluster["cluster_id"] in set(target_ids)
                        },
                        intra_cluster_split_challenges=(
                            intra_cluster_split_challenges
                        ),
                    )
                    if physical_review:
                        try:
                            identity_review.validate_verifier_identity_fields(
                                core_report,
                                target_proposal_ids_by_cluster={
                                    c["cluster_id"]: c["anonymous_proposal_ids"]
                                    for c in initial_payload["clusters"]
                                    if c["cluster_id"] in set(target_ids)
                                },
                                identity_challenge_pairs=identity_challenge_pairs,
                                valid_frame_ids=sample.reference_frame_ids,
                                all_cluster_ids=[c["cluster_id"] for c in initial_payload["clusters"]],
                            )
                        except Exception as error:
                            raise EnsembleError(str(error)) from error
                        if initial_context_preparation is not None:
                            context_review_audit.validate_context_verifier_coverage(
                                invocation.payload, initial_decisions=initial_payload,
                                required_scope_ids=initial_context_preparation["review_scope_ids"],
                                verifier_id=verifier_id,
                                **({"scope_retention_policy": scope_retention_policy,
                                    "eligible_parent_ids": retention_eligible_parents}
                                   if retention_enabled else {}),
                            )
                    if retention_enabled:
                        local_failure_stage = "native_provenance"
                        raw_path = attempt_dir / f"{prefix}.json"
                        source = _retention_native_source(invocation, raw_path, events_path)
                        local_failure_stage = "projection_persistence"
                        audit = retention_transport.build_projection_audit(
                            invocation.payload, core_report, policy=scope_retention_policy)
                        record = retention_attempt_audits[prefix]
                        record["source"] = source
                        record["raw_file"] = {"path": str(raw_path.resolve()), "sha256": _sha256(raw_path)}
                        record["native_events"] = {"path": str(events_path.resolve()), "sha256": _sha256(events_path)}
                        for label, data in (("core_projection", core_report), ("projection_audit", audit)):
                            path = adjudication_dir / f"{prefix}.{label}.json"
                            _atomic_write_json(path, data)
                            record["artifacts"][label] = {"path": str(path.resolve()), "sha256": _sha256(path)}
                        record["status"] = "persisted"
                    return verifier_id, core_report, invocation, None
                except Exception as exc:
                    if retention_enabled and local_failure_stage is not None:
                        retention_attempt_audits[prefix].update({
                            "status": "local_validation_or_persistence_failed",
                            "failure_stage": local_failure_stage,
                            "error_type": type(exc).__name__, "error": str(exc),
                        })
                    return verifier_id, None, invocation, exc

            pending_verifiers = list(VERIFIER_IDS)
            for attempt in (1, 2):
                if not pending_verifiers:
                    break
                print(
                    f"[ensemble {shot_id}] targeted verification attempt {attempt}: "
                    f"{len(target_ids)} clusters, {len(pending_verifiers)} parallel verifiers",
                    flush=True,
                )
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(max_workers, len(pending_verifiers))
                ) as executor:
                    futures = {
                        executor.submit(invoke_verifier, verifier_id, attempt): verifier_id
                        for verifier_id in pending_verifiers
                    }
                    verifier_invocations += len(futures)
                    verifier_outcomes = []
                    for future, verifier_id in futures.items():
                        try:
                            verifier_outcomes.append(future.result())
                        except Exception as error:
                            # Preserve peer outcomes even when prompt preparation
                            # or a worker unexpectedly raises before returning.
                            verifier_outcomes.append((verifier_id, None, None, error))
                next_pending_verifiers = []
                for verifier_id, payload, invocation, error in verifier_outcomes:
                    events_path = (
                        attempt_dir
                        / f"{verifier_id}.attempt{attempt}.events.jsonl"
                    )
                    accounting = _codex_attempt_accounting(
                        invocation=invocation,
                        error=error,
                        events_path=events_path,
                        **model_routing_stage.request_kwargs(model_context("verifier", verifier_id, attempt)),
                    )
                    manifest["verifier_attempts"].append(
                        {
                            "verifier_id": verifier_id,
                            "attempt": attempt,
                            "status": "success" if payload is not None else "failed",
                            "error": str(error) if error is not None else None,
                            **accounting,
                            **({"scope_retention_transport": copy.deepcopy(retention_attempt_audits.get(
                                f"{verifier_id}.attempt{attempt}",
                                {"policy_version": scope_retention_policy, "status": "not_projected", "artifacts": {}},
                            ))} if retention_enabled else {}),
                        }
                    )
                    if accounting["subprocess_started"] or accounting.get("subprocess_start_unknown"):
                        usages.append(accounting["token_usage"])
                    if payload is None:
                        verifier_retry_errors[verifier_id] = (
                            str(error) if error is not None else "unknown validation error"
                        )
                        if retention_enabled and retention_attempt_audits.get(
                            f"{verifier_id}.attempt{attempt}", {}
                        ).get("failure_stage") is not None:
                            verifier_local_failures.add(verifier_id)
                        next_pending_verifiers.append(verifier_id)
                        continue
                    verifier_retry_errors.pop(verifier_id, None)
                    verifier_local_failures.discard(verifier_id)
                    verifier_reports[verifier_id] = payload
                    if retention_enabled:
                        retention_raw_reports[verifier_id] = copy.deepcopy(invocation.payload)
                        retention_report_sources[verifier_id] = copy.deepcopy(
                            retention_attempt_audits[f"{verifier_id}.attempt{attempt}"]["source"])
                    if not retention_enabled:
                        report_path = adjudication_dir / f"{verifier_id}.json"
                        _atomic_write_json(report_path, payload)
                if retention_enabled:
                    # Every completed peer is accounted above before any core
                    # report publication can fail and terminate the shot.
                    for verifier_id, payload, _, _ in verifier_outcomes:
                        if payload is None:
                            continue
                        report_path = adjudication_dir / f"{verifier_id}.json"
                        try:
                            _atomic_write_json(report_path, payload)
                        except Exception as error:
                            manifest["scope_retention"].update({
                                "status": "verifier_report_publication_failed",
                                "failed_report": str(report_path.resolve()),
                                "error_type": type(error).__name__, "error": str(error),
                            })
                            raise
                pending_verifiers = next_pending_verifiers
                manifest["prompt_hashes"] = {
                    path.name: _sha256(path)
                    for path in sorted(prompt_dir.glob("*.txt"))
                }
                _atomic_write_json(manifest_path, manifest)
            if len(verifier_reports) != len(VERIFIER_IDS):
                missing_verifiers = sorted(set(VERIFIER_IDS) - set(verifier_reports))
                raise EnsembleError(
                    f"Missing valid targeted verifier reports after retry: {missing_verifiers}"
                )
            manifest["artifacts"]["verifier_reports"] = {
                verifier_id: {
                    "path": str((adjudication_dir / f"{verifier_id}.json").resolve()),
                    "sha256": _sha256(adjudication_dir / f"{verifier_id}.json"),
                }
                for verifier_id in VERIFIER_IDS
            }
            intra_cluster_split_consensus = build_intra_cluster_split_consensus(
                shot_id=shot_id,
                challenges=intra_cluster_split_challenges,
                verifier_reports=[
                    verifier_reports[item] for item in VERIFIER_IDS
                ],
            )
            split_consensus_path = (
                adjudication_dir / "intra_cluster_split_consensus.json"
            )
            _atomic_write_json(
                split_consensus_path, intra_cluster_split_consensus
            )
            manifest["artifacts"]["intra_cluster_split_consensus"] = {
                "path": str(split_consensus_path.resolve()),
                "sha256": _sha256(split_consensus_path),
            }
            if retention_enabled:
                try:
                    retention_consensus = retention_stage.build_retention_consensus(
                        [retention_raw_reports[v] for v in VERIFIER_IDS],
                        initial_decisions=initial_payload,
                        valid_frame_ids=sample.reference_frame_ids,
                        report_sources=retention_report_sources, verifier_ids=VERIFIER_IDS,
                    )
                    # Even an unapplied request cannot double as an ordinary
                    # physical-split authorization for the same parent.
                    retention_stage.validate_retention_transition(
                        initial_payload, initial_payload, retention_consensus,
                        independently_authorized_split_parent_ids=[
                            r["cluster_id"] for r in intra_cluster_split_consensus["exact_consensus_partitions"]],
                    )
                except ValueError as error:
                    raise EnsembleError(str(error)) from error
                retention_public_review = _retention_public_review(retention_consensus, initial_payload)
                consensus_path = adjudication_dir / "scope_retention_consensus.private.json"
                _atomic_write_json(consensus_path, retention_consensus)
                manifest["artifacts"]["scope_retention_consensus"] = {
                    "path": str(consensus_path.resolve()), "sha256": _sha256(consensus_path),
                    "model_visible": False,
                }
                provenance = {
                    "policy_version": scope_retention_policy,
                    "initial_decisions": _revision_preview_input(initial_path, initial_payload),
                    "eligible_parent_ids": retention_eligible_parents,
                    "verifier_successful_attempts": {
                        v: copy.deepcopy(next(row for row in reversed(manifest["verifier_attempts"])
                                              if row["verifier_id"] == v and row["status"] == "success"))
                        for v in VERIFIER_IDS
                    },
                    "core_verifier_reports": copy.deepcopy(manifest["artifacts"]["verifier_reports"]),
                    "consensus": copy.deepcopy(manifest["artifacts"]["scope_retention_consensus"]),
                    "schema_hashes": copy.deepcopy(manifest["schema_hashes"]),
                    "source_hashes": copy.deepcopy(manifest["stage_source_hashes"]),
                    "reference": copy.deepcopy(manifest["scope_retention"]["reference"]),
                    "public_review_sha256": _strict_json_sha256(retention_public_review),
                    "actual_distinct_native_threads_checked": True,
                    "only_successful_verifier_attempts_authorize": True,
                    "pixel_truth_verified": False,
                }
                provenance_path = adjudication_dir / "scope_retention_provenance.private.json"
                _atomic_write_json(provenance_path, provenance)
                manifest["artifacts"]["scope_retention_provenance"] = {
                    "path": str(provenance_path.resolve()), "sha256": _sha256(provenance_path),
                    "model_visible": False,
                }
                manifest["scope_retention"].update({
                    "status": "consensus_ready", "valid_verifier_sources": len(retention_raw_reports),
                    "requested_parent_count": len(retention_consensus["records"]),
                    "authorized_parent_count": len(retention_public_review["authorized_retention"]),
                })
            revision_split_consensus = {
                "protocol_version": PROTOCOL_VERSION,
                "shot_id": shot_id,
                "exact_consensus_partitions": intra_cluster_split_consensus[
                    "exact_consensus_partitions"
                ],
                "automatic_split": False,
            }
            revision_prompt = _revision_prompt(
                shot_id=shot_id,
                initial_decisions=initial_payload,
                verifier_reports=[verifier_reports[item] for item in VERIFIER_IDS],
                identity_challenge_pairs=identity_challenge_pairs,
                valid_frame_ids=sample.reference_frame_ids,
                intra_cluster_split_consensus=revision_split_consensus,
                **({"scope_retention_review": retention_public_review} if retention_enabled else {}),
            )
            if physical_review:
                revision_prompt += "\n\n" + identity_review.PHYSICAL_IDENTITY_RULE + "\n\n" + revision_fields_instruction
                if retention_enabled:
                    revision_prompt += "\n\n" + retention_policy_text
                if initial_identity_preparation and initial_identity_preparation["pending_comparisons"]:
                    revision_prompt += (
                        "\n\nThe supplied initial ledger is authoritative for this review. "
                        "A prior identity assertion without valid exact-scope evidence is "
                        "unresolved here. Do not treat an earlier unsupported assertion as "
                        "proof or recover it by copying an evidence label. Resolve the "
                        "supplied pair questions from the original pixels and verifier "
                        "reports under the same exact-scope evidence contract."
                    )
                if initial_context_preparation and initial_context_preparation["quarantined_evidence"]:
                    revision_prompt += (
                        "\n\nThe supplied initial proof ledger supersedes earlier evidence arrays. "
                        "Broad observations spanning more than two complete scopes were retained "
                        "privately as context, outside this proof ledger. Use only the supplied "
                        "current indices. Prior broad context is not exact-own or exact-pair proof; "
                        "do not restore it by renumbering or shortening its proposal IDs. "
                        "Any new scoped observation requires explicit fresh inspection of the "
                        "original pixels. Complete reviews may remain uncertain or reject a claim."
                    )
                # Check mandatory, already persisted inputs outside the optional
                # preview boundary. Their failure keeps the existing fatal path.
                saved_targets = json.loads(weak_path.read_text(encoding="utf-8"))
                for key, expected in (
                    ("cluster_ids", target_ids), ("trigger_reasons", target_reasons),
                    ("identity_challenge_pairs", identity_challenge_pairs),
                    ("intra_cluster_divergent_footprint_challenges", intra_cluster_split_challenges),
                ):
                    if _strict_json_sha256(saved_targets[key]) != _strict_json_sha256(expected):
                        raise EnsembleError(f"Revision preview target input mismatch: {key}")
                preview_provenance = {
                    "source_hashes": {
                        str(path): _sha256(path) for path in (
                            Path(__file__).resolve(), Path(identity_review.__file__).resolve(),
                            Path(obligation_review.__file__).resolve(),
                        )
                    },
                    "raw_initial": _revision_preview_input(initial_raw_path, initial_call.payload),
                    "prepared_initial": _revision_preview_input(initial_path, initial_payload),
                    "verifier_reports": {
                        item: _revision_preview_input(adjudication_dir / f"{item}.json", verifier_reports[item])
                        for item in VERIFIER_IDS
                    },
                    "verification_targets": {
                        **_revision_preview_input(weak_path, saved_targets),
                        "target_ids_content_sha256": _strict_json_sha256(target_ids),
                        "target_reasons_content_sha256": _strict_json_sha256(target_reasons),
                        "identity_pairs_content_sha256": _strict_json_sha256(identity_challenge_pairs),
                        "split_challenges_content_sha256": _strict_json_sha256(intra_cluster_split_challenges),
                    },
                    "split_consensus": _revision_preview_input(split_consensus_path, intra_cluster_split_consensus),
                    "preparation_artifacts": {
                        key: copy.deepcopy(manifest["artifacts"][key]) for key in (
                            "initial_context_projection", "initial_context_quarantine",
                            "initial_context_projection_audit", "initial_identity_review_preparation",
                        ) if key in manifest["artifacts"]
                    },
                    "base_revision_prompt_sha256": hashlib.sha256(revision_prompt.encode("utf-8")).hexdigest(),
                }
                supplement, preview_status, preview_artifacts = _prepare_first_revision_obligation_preview(
                    initial_decisions=initial_payload,
                    verifier_reports=[verifier_reports[item] for item in VERIFIER_IDS],
                    target_reasons=target_reasons, split_consensus=intra_cluster_split_consensus,
                    identity_review=identity_review, obligation_review=obligation_review,
                    output_dir=adjudication_dir, provenance=preview_provenance,
                )
                manifest["first_revision_obligation_preview"] = preview_status
                manifest["artifacts"].update(preview_artifacts)
                if supplement is not None:
                    revision_prompt += "\n\n" + supplement
                # Mandatory manifest persistence is deliberately not swallowed.
                _atomic_write_json(manifest_path, manifest)
            revision_prompt_path = prompt_dir / "adjudicator_revision.txt"
            _atomic_write_text(revision_prompt_path, revision_prompt)
            manifest["prompt_hashes"][revision_prompt_path.name] = _sha256(
                revision_prompt_path
            )
            final_decisions: Optional[Dict[str, Any]] = None
            final_runtime = 0.0
            revision_attempt_prompt = revision_prompt
            wire_input_provenance = None
            if wire_revision:
                wire_input_provenance = {
                    "initial_adjudication": _revision_preview_input(initial_path, initial_payload),
                    "anonymized_candidates": _revision_preview_input(anonymous_path, anonymous_view),
                    "shot_manifest": _revision_preview_input(run_dir / "input_bundle/shot_manifest.json", shot_manifest),
                    "initial_cluster_ids": [row["cluster_id"] for row in initial_payload["clusters"]],
                    "expected_proposal_ids": list(anonymous_ids),
                    "valid_frame_ids": list(sample.reference_frame_ids),
                }
            for revision_attempt in (1, 2):
                print(
                    f"[ensemble {shot_id}] adjudicator revision attempt "
                    f"{revision_attempt}: {len(target_ids)} verified clusters",
                    flush=True,
                )
                final_call: Optional[CodexInvocation] = None
                revision_error: Optional[BaseException] = None
                if revision_attempt == 1:
                    output_stem = "adjudicator_revision"
                else:
                    output_stem = f"adjudicator_revision.attempt{revision_attempt}"
                revision_events_path = attempt_dir / f"{output_stem}.events.jsonl"
                revision_raw_path = attempt_dir / f"{output_stem}.json"
                revision_model_context = model_context(
                    "adjudicator_revision", "adjudicator_revision", revision_attempt,
                    initial_request=initial_request_binding,
                )
                wire_attempt = {"input_provenance": wire_input_provenance,
                                "status": "not_materialized", "artifacts": {}} if wire_revision else None
                revision_raw_sha256 = None
                adjudicator_invocations += 1
                try:
                    final_call = run_codex_json(
                        prompt=revision_attempt_prompt,
                        attachments=attachments,
                        schema_path=revision_schema,
                        **model_routing_stage.request_kwargs(revision_model_context),
                        output_path=revision_raw_path,
                        events_path=revision_events_path,
                        stderr_path=attempt_dir / f"{output_stem}.stderr.log",
                        codex_bin=codex_bin,
                        model=review_call_model,
                        timeout_sec=timeout_sec,
                        work_dir=inventory_work_dir,
                        resume_thread_id=initial_call.thread_id,
                        verbose=verbose,
                    )
                    revised_payload = final_call.payload
                    if wire_revision:
                        # Re-read exact UTF-8 bytes: json.loads in transport must
                        # not hide duplicate keys or normalize CRLF provenance.
                        raw_bytes = revision_raw_path.read_bytes()
                        revision_raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
                        raw_text = raw_bytes.decode("utf-8")
                        for key in ("initial_adjudication", "anonymized_candidates", "shot_manifest"):
                            reference = wire_input_provenance[key]
                            if _sha256(Path(reference["path"])) != reference["sha256"]:
                                raise EnsembleError("Revision wire source artifact changed: " + key)
                        revised_payload, wire_audit = revision_wire.materialize_revision_wire_json(
                            raw_text, valid_frame_ids=sample.reference_frame_ids,
                            expected_proposal_ids=anonymous_ids, expected_shot_id=shot_id,
                            initial_cluster_ids=wire_input_provenance["initial_cluster_ids"],
                        )
                        wire_attempt["status"] = "validated_in_memory"
                        wire_audit["input_provenance"] = wire_input_provenance
                        for label, data, path in (
                            ("canonical", revised_payload, adjudication_dir / f"{output_stem}.materialized.json"),
                            ("materialization_audit", wire_audit, adjudication_dir / f"{output_stem}.materialization_audit.json"),
                        ):
                            _atomic_write_json(path, data)
                            reference = {"path": str(path.resolve()), "sha256": _sha256(path)}
                            wire_attempt["artifacts"][label] = reference
                            manifest["artifacts"][f"{output_stem}_{label}"] = reference
                        wire_attempt["status"] = "persisted"
                    validate_inventory_payload(revised_payload, anonymous_ids)
                    validate_deferred_partition_lineage(
                        initial_payload, revised_payload
                    )
                    split_revision_audit = enforce_intra_cluster_split_consensus(
                        initial_decisions=initial_payload,
                        revised_decisions=revised_payload,
                        split_consensus=intra_cluster_split_consensus,
                        **({"retention_consensus": retention_consensus} if retention_enabled else {}),
                    )
                    if retention_enabled:
                        retention_transition = split_revision_audit["scope_retention_transition"]
                    final_decisions = revised_payload
                    final_runtime = final_call.runtime_seconds
                except Exception as exc:
                    if not wire_revision and not isinstance(exc, (EnsembleError, OSError)):
                        raise
                    revision_error = exc
                if wire_revision:
                    try:
                        if revision_raw_path.is_file():
                            reference = {"path": str(revision_raw_path.resolve()), "sha256": _sha256(revision_raw_path)}
                            wire_attempt["artifacts"]["raw"] = reference
                            manifest["artifacts"][f"{output_stem}_wire_raw"] = reference
                            if revision_raw_sha256 is not None and reference["sha256"] != revision_raw_sha256:
                                raise EnsembleError("Raw revision bytes changed during wire materialization")
                    except Exception as exc:
                        wire_attempt["artifact_recording_error"] = str(exc)
                        revision_error = revision_error or exc
                        final_decisions = None
                revision_accounting = _codex_attempt_accounting(
                    invocation=final_call,
                    error=revision_error,
                    events_path=revision_events_path,
                    **model_routing_stage.request_kwargs(revision_model_context),
                )
                if revision_accounting["subprocess_started"] or revision_accounting.get("subprocess_start_unknown"):
                    usages.append(revision_accounting["token_usage"])
                manifest["adjudicator_revision_attempts"].append(
                    {
                        "attempt": revision_attempt,
                        "status": "success" if final_decisions is not None else "failed",
                        "error": (
                            str(revision_error)
                            if revision_error is not None
                            else None
                        ),
                        **revision_accounting,
                        **({"revision_output_policy": revision_output_policy,
                            "wire_materialization": wire_attempt} if wire_revision else {}),
                    }
                )
                _atomic_write_json(manifest_path, manifest)
                if final_decisions is not None:
                    break
                if revision_attempt == 1:
                    accounting_diagnostics = (
                        proposal_accounting_diagnostics(
                            final_call.payload, anonymous_ids
                        )
                        if final_call is not None
                        else {}
                    )
                    revision_attempt_prompt = _revision_repair_prompt(
                        shot_id=shot_id,
                        validation_error=(
                            str(revision_error)
                            if revision_error is not None
                            else "unknown validation failure"
                        ),
                        accounting_diagnostics=accounting_diagnostics,
                        intra_cluster_split_consensus=revision_split_consensus,
                        **({"scope_retention_review": retention_public_review} if retention_enabled else {}),
                    )
                    if retention_enabled:
                        revision_attempt_prompt += "\n\n" + retention_policy_text
                    if wire_revision:
                        revision_attempt_prompt += "\n\n" + _revision_wire_output_instruction()
                    repair_prompt_path = (
                        prompt_dir / "adjudicator_revision.attempt2.txt"
                    )
                    _atomic_write_text(repair_prompt_path, revision_attempt_prompt)
                    manifest["prompt_hashes"][repair_prompt_path.name] = _sha256(
                        repair_prompt_path
                    )
            if final_decisions is None:
                raise EnsembleError(
                    "Missing valid adjudicator revision after accounting retry"
                )
        else:
            if physical_review:
                manifest["first_revision_obligation_preview"].update({
                    "status": "not_applicable", "reason": "no_targeted_verifier_revision",
                })
            if retention_enabled:
                manifest["scope_retention"]["status"] = "not_applicable_no_verifier_targets"
            print(
                f"[ensemble {shot_id}] targeted verification: no weak clusters",
                flush=True,
            )
            final_decisions = initial_payload
            final_runtime = initial_call.runtime_seconds

        split_consensus_path = (
            adjudication_dir / "intra_cluster_split_consensus.json"
        )
        split_revision_audit_path = (
            adjudication_dir / "intra_cluster_split_revision_firewall.json"
        )
        _atomic_write_json(split_consensus_path, intra_cluster_split_consensus)
        _atomic_write_json(split_revision_audit_path, split_revision_audit)
        manifest["artifacts"]["intra_cluster_split_consensus"] = {
            "path": str(split_consensus_path.resolve()),
            "sha256": _sha256(split_consensus_path),
        }
        manifest["artifacts"]["intra_cluster_split_revision_firewall"] = {
            "path": str(split_revision_audit_path.resolve()),
            "sha256": _sha256(split_revision_audit_path),
        }
        manifest["intra_cluster_spatial_split_audit"] = {
            "challenge_count": len(intra_cluster_split_challenges),
            "exact_two_verifier_consensus_count": len(
                intra_cluster_split_consensus["exact_consensus_partitions"]
            ),
            "revision_split_count": split_revision_audit[
                "observed_split_count"
            ],
            "proposal_boxes_are_review_triggers_only": True,
            "source_or_detector_count_used": False,
            "automatic_split": False,
            "exact_proposal_partition_firewall": True,
        }
        if retention_transition is not None:
            transition_path = adjudication_dir / "scope_retention_transition.json"
            _atomic_write_json(transition_path, retention_transition)
            manifest["artifacts"]["scope_retention_transition"] = {
                "path": str(transition_path.resolve()), "sha256": _sha256(transition_path),
            }
            manifest["scope_retention"].update({
                "status": "revision_validated",
                "applied_parent_count": len(retention_transition["audited_transitions"]),
                "residual_existence_asserted": False,
            })
        physical_identity_gate_audit = None
        if physical_review:
            try:
                final_decisions, physical_identity_gate_audit = identity_review.apply_physical_identity_gate(
                    final_decisions, initial_decisions=initial_payload,
                    verifier_reports=[(retention_raw_reports if retention_enabled else verifier_reports)[v]
                                      for v in VERIFIER_IDS if v in verifier_reports],
                    verification_target_reasons=target_reasons,
                    intra_cluster_split_consensus=intra_cluster_split_consensus,
                    **({"retention_consensus": retention_consensus} if retention_consensus is not None else {}),
                )
            except ValueError as error:
                raise EnsembleError(str(error)) from error
            manifest["physical_identity_gate"] = {
                "policy_version": identity_review.SCHEMA_VERSION,
                "distinct_revision_proof_policy": identity_review.DISTINCT_REVISION_PROOF_POLICY,
                "reviewed_cluster_count": len(physical_identity_gate_audit["records"]),
                "changed_to_abstain_count": sum(r["result"] == "abstain" for r in physical_identity_gate_audit["records"]),
                "source_support_used": False,
                "name_lexicon_used": False,
                "support_quality_threshold_used": False,
                "supplied_to_any_model": False,
            }
            if initial_identity_preparation is not None:
                pending_dispositions = pending_review_audit.audit_pending_identity_dispositions(
                    initial_decisions=initial_payload, final_decisions=final_decisions,
                    pending_comparisons=initial_identity_preparation["pending_comparisons"],
                    physical_gate_audit=physical_identity_gate_audit,
                    verifier_reports=[verifier_reports[v] for v in VERIFIER_IDS if v in verifier_reports],
                )
                pending_path = adjudication_dir / "pending_identity_review_dispositions.json"
                _atomic_write_json(pending_path, pending_dispositions)
                manifest["artifacts"]["pending_identity_review_dispositions"] = {
                    "path": str(pending_path.resolve()), "sha256": _sha256(pending_path),
                }
                manifest["initial_identity_pending_review"].update({
                    "all_pending_pairs_contract_resolved": pending_dispositions["all_pending_pairs_contract_resolved"],
                    "unresolved_coverage_risk": pending_dispositions["unresolved_coverage_risk"],
                    "pixel_truth_verified": False,
                })
            if initial_context_preparation is not None:
                context_dispositions = context_review_audit.audit_context_review_dispositions(
                    initial_decisions=initial_payload, final_decisions=final_decisions,
                    quarantine_audit=initial_context_preparation,
                    verifier_reports=[(retention_raw_reports if retention_enabled else verifier_reports)[v]
                                      for v in VERIFIER_IDS if v in verifier_reports],
                    **({"scope_retention_policy": scope_retention_policy,
                        "eligible_parent_ids": retention_eligible_parents} if retention_enabled else {}),
                )
                context_path = adjudication_dir / "initial_context_review_dispositions.json"
                _atomic_write_json(context_path, context_dispositions)
                manifest["artifacts"]["initial_context_review_dispositions"] = {
                    "path": str(context_path.resolve()), "sha256": _sha256(context_path),
                }
                manifest["initial_context_review"].update({
                    "all_required_scopes_reviewed": context_dispositions["all_required_scopes_reviewed"],
                    "unresolved_coverage_risk": context_dispositions["unresolved_coverage_risk"],
                })
                if not context_dispositions["all_required_scopes_reviewed"]:
                    raise EnsembleError("Initial context owners lack two complete independent scope reviews")
        final_decisions, single_detector_gate_audit = (
            apply_single_detector_consensus_gate(
                final_decisions,
                initial_decisions=initial_payload,
                source_map=source_map,
                verifier_reports=[
                    verifier_reports[item]
                    for item in VERIFIER_IDS
                    if item in verifier_reports
                ],
                verification_target_reasons=target_reasons,
                intra_cluster_split_consensus=(
                    intra_cluster_split_consensus
                ),
            ) if not physical_review else (
                final_decisions, {"records": [], "status": "superseded_by_physical_identity_gate"}
            )
        )
        validate_decisions(
            final_decisions,
            shot_id=shot_id,
            anonymous_ids=anonymous_ids,
            valid_frame_ids=sample.reference_frame_ids,
        )
        manifest["single_detector_consensus_gate"] = {
            "applied": not physical_review,
            "reviewed_cluster_count": len(single_detector_gate_audit["records"]),
            "changed_to_abstain_count": sum(
                item["result"] == "changed_to_abstain"
                for item in single_detector_gate_audit["records"]
            ),
        }
        final_decisions, nonmajority_generic_identity_gate_audit = (
            apply_nonmajority_generic_identity_gate(
                final_decisions,
                initial_decisions=initial_payload,
                source_map=source_map,
                verifier_reports=[
                    verifier_reports[item]
                    for item in VERIFIER_IDS
                    if item in verifier_reports
                ],
                verification_target_reasons=target_reasons,
                expected_detector_ids=[role for role, _, _ in DETECTOR_ROLES],
                support_scope=generic_identity_support_scope,
                intra_cluster_split_consensus=(
                    intra_cluster_split_consensus
                ),
            ) if not physical_review else (
                final_decisions, {"records": [], "policy_version": "not_applied",
                                  "status": "superseded_by_physical_identity_gate"}
            )
        )
        validate_decisions(
            final_decisions,
            shot_id=shot_id,
            anonymous_ids=anonymous_ids,
            valid_frame_ids=sample.reference_frame_ids,
        )
        manifest["nonmajority_generic_identity_gate"] = {
            "applied": not physical_review,
            "policy_version": nonmajority_generic_identity_gate_audit["policy_version"],
            "reviewed_cluster_count": len(
                nonmajority_generic_identity_gate_audit["records"]
            ),
            "changed_to_abstain_count": sum(
                item["result"] == "changed_to_abstain"
                for item in nonmajority_generic_identity_gate_audit["records"]
            ),
            "expected_detector_count": len(DETECTOR_ROLES),
            "support_rule": generic_identity_support_scope,
            "supplied_to_any_model": False,
        }

        pre_granularity_path = (
            adjudication_dir / "adjudicator_pre_granularity.json"
        )
        pre_group_frozen_baseline = copy.deepcopy(final_decisions)
        pre_group_frozen_baseline_hash = family_stage.json_hash(
            pre_group_frozen_baseline
        )
        _atomic_write_json(pre_granularity_path, pre_group_frozen_baseline)
        manifest["artifacts"]["adjudicator_pre_granularity"] = {
            "path": str(pre_granularity_path.resolve()),
            "sha256": _sha256(pre_granularity_path),
            "single_detector_gate_already_applied": not physical_review,
            "nonmajority_generic_identity_gate_already_applied": not physical_review,
            "physical_identity_gate_already_applied": physical_review,
            "frozen_baseline_for_both_partition_reviews": True,
        }
        provisional_group_member_decisions, group_member_stage_result = (
            run_group_member_family_stage(
                shot_id=shot_id,
                shot_manifest=shot_manifest,
                attachments=attachments,
                skill_text=skill_text,
                baseline=pre_group_frozen_baseline,
                anonymous_view=anonymous_view,
                anonymous_ids=anonymous_ids,
                valid_frame_ids=sample.reference_frame_ids,
                codex_bin=codex_bin,
                model=review_call_model,
                **({"model_routing": model_routing} if model_routing is not None else {}),
                timeout_sec=timeout_sec,
                work_dirs=family_work_dirs,
                prompt_dir=prompt_dir,
                attempt_dir=attempt_dir,
                adjudication_dir=adjudication_dir,
                verbose=verbose,
            )
        )
        granularity_invocations += group_member_stage_result["invocation_count"]
        manifest["granularity_invocations"] = granularity_invocations
        usages.extend(group_member_stage_result["token_usages"])
        manifest["granularity_family_attempts"] = group_member_stage_result[
            "attempts"
        ]
        group_consensus = group_member_stage_result["consensus_resolutions"]
        manifest["granularity_family"] = {
            "status": group_member_stage_result["status"],
            "status_describes_provisional_audit": True,
            "eligible_shape": group_member_stage_result["eligible_shape"],
            "planner_count": 2,
            "valid_planner_count": group_member_stage_result[
                "valid_planner_count"
            ],
            "failed_planner_indices": group_member_stage_result[
                "failed_planner_indices"
            ],
            "planner_invocation_count": group_member_stage_result[
                "invocation_count"
            ],
            "synthetic_empty_plan_count": group_member_stage_result[
                "synthetic_empty_plan_count"
            ],
            "family_count_by_planner": group_member_stage_result[
                "family_count_by_planner"
            ],
            "exact_family_member_partition_consensus_required": True,
            "role": "candidate_scope_audit_and_provisional_application",
            "coarsening_is_final": False,
            "accepted_candidate_second_gate_required": True,
            "consensus_family_count": sum(
                item["selected_kind"] is not None for item in group_consensus
            ),
            "applied_family_count": (
                len(
                    group_member_stage_result["firewall_audit"][
                        "applied_family_ids"
                    ]
                )
                if group_member_stage_result["firewall_audit"] is not None
                else 0
            ),
            "applied_family_count_is_provisional": True,
            "missing_or_structurally_different_family_count": sum(
                item["basis"]
                == "missing_exact_family_or_member_set_in_one_planner"
                for item in group_consensus
            ),
            "partition_disagreement_count": sum(
                item["basis"] == "group_members_partition_disagreement"
                for item in group_consensus
            ),
            "overlap_conflict_count": sum(
                item["basis"] == "overlapping_or_nested_family_component"
                for item in group_consensus
            ),
            "identical_planner_inputs": True,
            "isolated_ephemeral_planner_threads": True,
            "source_map_explicitly_supplied_to_model": False,
            "provenance_derived_diagnostics_supplied_to_model": False,
            "panel_positions_select_partition": False,
            "post_provenance_model_calls": 0,
            "cross_shot_input": False,
        }
        for label, path in group_member_stage_result["paths"].items():
            artifact_record = {
                "path": str(path.resolve()),
                "sha256": _sha256(path),
            }
            if label in {
                "application_plan",
                "source_blind_resolutions",
                "firewall",
            }:
                artifact_record["partition_effect"] = (
                    "provisional_pending_accepted_candidate_second_gate"
                )
                artifact_record["eligible_as_final_inventory"] = False
            manifest["artifacts"][f"granularity_group_member_{label}"] = (
                artifact_record
            )
        family_prompt_path = group_member_stage_result["prompt_path"]
        if family_prompt_path is not None:
            manifest["prompt_hashes"][family_prompt_path.name] = _sha256(
                family_prompt_path
            )
        _atomic_write_json(manifest_path, manifest)
        if group_member_stage_result["status"] == "failed":
            raise EnsembleError(group_member_stage_result["error"])

        post_group_member_path = (
            adjudication_dir / "adjudicator_post_group_member.json"
        )
        _atomic_write_json(
            post_group_member_path, provisional_group_member_decisions
        )
        manifest["artifacts"]["adjudicator_post_group_member"] = {
            "path": str(post_group_member_path.resolve()),
            "sha256": _sha256(post_group_member_path),
            "group_member_partition_frozen": False,
            "provisional_partition_view_only": True,
            "accepted_candidate_second_gate_required": True,
            "eligible_as_final_inventory": False,
        }
        if family_stage.json_hash(pre_group_frozen_baseline) != (
            pre_group_frozen_baseline_hash
        ):
            raise EnsembleError(
                "Explicit group/member review mutated the frozen partition baseline"
            )
        final_decisions, accepted_assembly_result = (
            run_accepted_compact_assembly_stage(
                shot_id=shot_id,
                shot_manifest=shot_manifest,
                attachments=attachments,
                skill_text=skill_text,
                baseline=pre_group_frozen_baseline,
                anonymous_view=anonymous_view,
                explicit_partition_plans=group_member_stage_result["plans"],
                spatial_vetoes=group_member_stage_result["firewall_audit"]["spatial_vetoes"],
                declared_partition_neighborhoods=(
                    accepted_assembly_stage.build_declared_partition_neighborhoods(
                        baseline=pre_group_frozen_baseline,
                        initial_decisions=initial_payload,
                        verifier_reports=[verifier_reports[item] for item in VERIFIER_IDS
                                          if item in verifier_reports],
                    )
                ),
                anonymous_ids=anonymous_ids,
                valid_frame_ids=sample.reference_frame_ids,
                codex_bin=codex_bin,
                model=review_call_model,
                **({"model_routing": model_routing} if model_routing is not None else {}),
                timeout_sec=timeout_sec,
                work_dirs=accepted_assembly_work_dirs,
                prompt_dir=prompt_dir,
                attempt_dir=attempt_dir,
                adjudication_dir=adjudication_dir,
                verbose=verbose,
            )
        )
        granularity_invocations += accepted_assembly_result["invocation_count"]
        manifest["granularity_invocations"] = granularity_invocations
        usages.extend(accepted_assembly_result["token_usages"])
        manifest["accepted_compact_assembly_attempts"] = (
            accepted_assembly_result["attempts"]
        )
        manifest["accepted_compact_assembly"] = {
            "reference_coverage_policy": accepted_assembly_stage.REFERENCE_COVERAGE_POLICY,
            "status": accepted_assembly_result["status"],
            "accepted_cluster_count": accepted_assembly_result[
                "accepted_cluster_count"
            ],
            "mandatory_candidate_count": accepted_assembly_result[
                "candidate_count"
            ],
            "planner_count": 2,
            "planner_invocation_count": accepted_assembly_result[
                "invocation_count"
            ],
            "synthetic_empty_plan_count": (
                2
                if accepted_assembly_result["status"]
                == "deterministically_skipped"
                else 0
            ),
            "mandatory_candidate_bank": True,
            "exact_consensus_required": True,
            "final_partition_authority": True,
            "uses_pre_group_frozen_baseline": True,
            "vetoes_provisional_explicit_coarsening": True,
            "applied_family_count": sum(
                item["status"] == "applied"
                for item in accepted_assembly_result["resolutions"]
            ),
            "rejected_and_abstained_clusters_supplied_to_model": False,
            "detector_provenance_supplied_to_model": False,
            "detector_boxes_supplied_to_model": False,
            "cross_shot_input": False,
        }
        for label, path in accepted_assembly_result["paths"].items():
            manifest["artifacts"][f"accepted_compact_assembly_{label}"] = {
                "path": str(path.resolve()),
                "sha256": _sha256(path),
            }
        accepted_assembly_prompt_path = accepted_assembly_result["prompt_path"]
        manifest["prompt_hashes"][accepted_assembly_prompt_path.name] = _sha256(
            accepted_assembly_prompt_path
        )
        _atomic_write_json(manifest_path, manifest)
        if accepted_assembly_result["status"] == "failed":
            raise EnsembleError(accepted_assembly_result["error"])

        if retention_transition is not None:
            residual_audit = _validate_retention_residual_lineage(final_decisions, retention_transition)
            residual_path = adjudication_dir / "scope_retention_graph_residual_lineage.json"
            _atomic_write_json(residual_path, residual_audit)
            manifest["artifacts"]["scope_retention_graph_residual_lineage"] = {
                "path": str(residual_path.resolve()), "sha256": _sha256(residual_path),
            }
            manifest["scope_retention"].update({"status": "final_graph_residuals_preserved",
                                                 "all_residuals_nonaccepted": True})

        lineage = accepted_assembly_stage.build_physical_anchor_lineage(
            pre_group_frozen_baseline, final_decisions,
        )
        lineage_path = adjudication_dir / "graph_physical_anchor_lineage.json"
        _atomic_write_json(lineage_path, lineage)
        manifest["artifacts"]["graph_physical_anchor_lineage"] = {
            "path": str(lineage_path.resolve()), "sha256": _sha256(lineage_path),
            "physical_inventory_path": str(pre_granularity_path.resolve()),
            "physical_inventory_file_sha256": _sha256(pre_granularity_path),
            "derived_graph_is_physical_adjudication": False,
            "grouping_establishes_same_instance_identity": False,
        }

        partition_gate_handoff_path = (
            adjudication_dir / "partition_gate_handoff.json"
        )
        _atomic_write_json(
            partition_gate_handoff_path,
            {
                "protocol_version": PROTOCOL_VERSION,
                "shot_id": shot_id,
                "pre_group_frozen_baseline_sha256": _sha256(
                    pre_granularity_path
                ),
                "provisional_group_member_view_sha256": _sha256(
                    post_group_member_path
                ),
                "explicit_group_member_role": (
                    "candidate_scope_audit_and_provisional_application"
                ),
                "accepted_candidate_second_gate_required": True,
                "accepted_candidate_second_gate_status": (
                    accepted_assembly_result["status"]
                ),
                "final_decisions_source": (
                    "pre_group_frozen_baseline_plus_accepted_candidate_consensus"
                ),
                "final_decisions_content_sha256": accepted_assembly_stage.json_hash(
                    final_decisions
                ),
            },
        )
        manifest["artifacts"]["partition_gate_handoff"] = {
            "path": str(partition_gate_handoff_path.resolve()),
            "sha256": _sha256(partition_gate_handoff_path),
            "records_provisional_to_final_authority_boundary": True,
        }
        _atomic_write_json(manifest_path, manifest)

        accepted_count = sum(
            cluster["decision"] == "accept" for cluster in final_decisions["clusters"]
        )
        print(
            f"[ensemble {shot_id}] adjudication complete: accepted "
            f"{accepted_count}/{len(final_decisions['clusters'])} clusters "
            f"(last pass {final_runtime:.1f}s)",
            flush=True,
        )
        decisions_path = adjudication_dir / "adjudicator_decisions.json"
        _atomic_write_json(decisions_path, final_decisions)
        decisions_hash = _sha256(decisions_path)
        manifest["artifacts"]["adjudicator_decisions"] = {
            "path": str(decisions_path.resolve()),
            "sha256": decisions_hash,
            "candidate_additions_allowed": False,
            "partition_source": (
                "pre_group_frozen_baseline_plus_accepted_candidate_consensus"
            ),
            "provisional_group_member_view_used_as_baseline": False,
        }

        matching_dir = run_dir / "matching"
        matching_dir.mkdir(parents=True, exist_ok=False)
        inventory_view = frozen_inventory_view(final_decisions)
        inventory_view_path = matching_dir / "frozen_inventory.json"
        _atomic_write_json(inventory_view_path, inventory_view)
        manifest["artifacts"]["frozen_inventory"] = {
            "path": str(inventory_view_path.resolve()),
            "sha256": _sha256(inventory_view_path),
            "mutable_by_matcher": False,
        }
        matcher_prompt = _matcher_prompt(
            shot_id=shot_id,
            shot_manifest=shot_manifest,
            semantic_registry=semantic_registry,
            inventory_view=inventory_view,
            allowed_input_paths=matcher_allowed_paths,
            skill_text=skill_text,
        )
        matcher_prompt_path = prompt_dir / "prompt_bound_matcher.txt"
        _atomic_write_text(matcher_prompt_path, matcher_prompt)
        manifest["prompt_hashes"][matcher_prompt_path.name] = _sha256(
            matcher_prompt_path
        )
        prompt_bound_matches: Optional[Dict[str, Any]] = None
        accepted_cluster_ids = [
            cluster["cluster_id"] for cluster in inventory_view["clusters"]
        ]
        registry_ids = [
            entity["registry_id"] for entity in semantic_registry["entities"]
        ]
        for attempt in (1, 2):
            invocation: Optional[CodexInvocation] = None
            error: Optional[BaseException] = None
            matcher_events_path = (
                attempt_dir / f"prompt_bound_matcher.attempt{attempt}.events.jsonl"
            )
            print(
                f"[ensemble {shot_id}] prompt-bound matcher attempt {attempt}: "
                f"classifying {len(accepted_cluster_ids)} frozen inventory clusters",
                flush=True,
            )
            matcher_invocations += 1
            try:
                invocation = run_codex_json(
                    prompt=matcher_prompt,
                    attachments=attachments,
                    schema_path=MATCHING_SCHEMA,
                    **model_routing_stage.request_kwargs(model_context("prompt_bound_matcher", "prompt_bound_matcher", attempt)),
                    output_path=attempt_dir / f"prompt_bound_matcher.attempt{attempt}.json",
                    events_path=matcher_events_path,
                    stderr_path=(
                        attempt_dir / f"prompt_bound_matcher.attempt{attempt}.stderr.log"
                    ),
                    codex_bin=codex_bin,
                    model=model,
                    timeout_sec=timeout_sec,
                    work_dir=matcher_work_dir,
                    verbose=verbose,
                )
                validate_prompt_bound_matches(
                    invocation.payload,
                    shot_id=shot_id,
                    accepted_cluster_ids=accepted_cluster_ids,
                    registry_ids=registry_ids,
                    valid_frame_ids=sample.reference_frame_ids,
                )
                prompt_bound_matches = invocation.payload
            except (EnsembleError, OSError) as exc:
                error = exc
            matcher_accounting = _codex_attempt_accounting(
                invocation=invocation,
                error=error,
                events_path=matcher_events_path,
                **model_routing_stage.request_kwargs(model_context("prompt_bound_matcher", "prompt_bound_matcher", attempt)),
            )
            if matcher_accounting["subprocess_started"] or matcher_accounting.get("subprocess_start_unknown"):
                usages.append(matcher_accounting["token_usage"])
            manifest["matcher_attempts"].append(
                {
                    "attempt": attempt,
                    "status": (
                        "success" if prompt_bound_matches is not None else "failed"
                    ),
                    "error": str(error) if error is not None else None,
                    **matcher_accounting,
                }
            )
            _atomic_write_json(manifest_path, manifest)
            if prompt_bound_matches is not None:
                break
        if prompt_bound_matches is None:
            raise EnsembleError("Missing valid prompt-bound matcher result after retry")
        matches_path = matching_dir / "prompt_bound_matches.json"
        _atomic_write_json(matches_path, prompt_bound_matches)
        matches_hash = _sha256(matches_path)
        match_status_counts = {
            status: sum(
                item["status"] == status
                for item in prompt_bound_matches["matches"]
            )
            for status in ("bound", "unbound", "ambiguous")
        }
        print(
            f"[ensemble {shot_id}] prompt-bound matching complete: "
            f"{match_status_counts['unbound']} unbound, "
            f"{match_status_counts['bound']} bound, "
            f"{match_status_counts['ambiguous']} ambiguous",
            flush=True,
        )
        manifest["artifacts"]["prompt_bound_matches"] = {
            "path": str(matches_path.resolve()),
            "sha256": matches_hash,
            "inventory_mutation_allowed": False,
            "registry_boxes_supplied": False,
        }
        _atomic_write_json(source_map_path, source_map)
        manifest["artifacts"]["source_map"] = {
            "path": str(source_map_path.resolve()),
            "sha256": _sha256(source_map_path),
            "written_after_adjudicator_decisions_sha256": decisions_hash,
            "written_after_prompt_bound_matches_sha256": matches_hash,
            "withheld_from_all_agents": True,
        }
        group_panel_positions = family_stage.build_panel_positions(
            group_member_stage_result["plan"],
            source_map,
            [role for role, _, _ in DETECTOR_ROLES],
        )
        panel_resolutions = family_stage.select_resolutions(
            group_member_stage_result["plan"], group_panel_positions
        )

        def decision_projection(
            items: Sequence[Mapping[str, Any]],
        ) -> List[Dict[str, Any]]:
            return [
                {
                    key: copy.deepcopy(value)
                    for key, value in item.items()
                    if key not in {"group_panel_ids", "member_panel_ids"}
                }
                for item in items
            ]

        if decision_projection(panel_resolutions) != decision_projection(
            group_member_stage_result["source_blind_resolutions"]
        ):
            raise EnsembleError(
                "Detector provenance changed a frozen granularity resolution"
            )
        group_panel_path = (
            adjudication_dir
            / "granularity_group_member_panel_positions.private.json"
        )
        group_panel_audit_path = (
            adjudication_dir
            / "granularity_group_member_resolution_panel_audit.private.json"
        )
        _atomic_write_json(group_panel_path, group_panel_positions)
        _atomic_write_json(
            group_panel_audit_path,
            {
                "protocol_version": family_stage.FAMILY_PLAN_PROTOCOL,
                "shot_id": shot_id,
                "panel_positions_select_partition": False,
                "post_provenance_model_calls": 0,
                "source_blind_decision_projection_unchanged": True,
                "resolutions_with_audit_only_panel_positions": panel_resolutions,
            },
        )
        manifest["artifacts"]["granularity_group_member_panel_positions_private"] = {
            "path": str(group_panel_path.resolve()),
            "sha256": _sha256(group_panel_path),
            "written_after_prompt_bound_matches_sha256": matches_hash,
        }
        manifest["artifacts"]["granularity_group_member_panel_audit_private"] = {
            "path": str(group_panel_audit_path.resolve()),
            "sha256": _sha256(group_panel_audit_path),
            "written_after_prompt_bound_matches_sha256": matches_hash,
        }
        single_detector_audit_path = (
            adjudication_dir / "single_detector_consensus_gate.json"
        )
        _atomic_write_json(single_detector_audit_path, single_detector_gate_audit)
        manifest["artifacts"]["single_detector_consensus_gate"] = {
            "path": str(single_detector_audit_path.resolve()),
            "sha256": _sha256(single_detector_audit_path),
            "written_after_prompt_bound_matches_sha256": matches_hash,
        }
        nonmajority_identity_audit_path = (
            adjudication_dir / "nonmajority_generic_identity_gate.private.json"
        )
        _atomic_write_json(
            nonmajority_identity_audit_path,
            nonmajority_generic_identity_gate_audit,
        )
        manifest["artifacts"]["nonmajority_generic_identity_gate_private"] = {
            "path": str(nonmajority_identity_audit_path.resolve()),
            "sha256": _sha256(nonmajority_identity_audit_path),
            "written_after_prompt_bound_matches_sha256": matches_hash,
            "private": True,
            "contains_detector_support": not physical_review,
            "supplied_to_any_model": False,
        }
        if physical_identity_gate_audit is not None:
            identity_audit_path = adjudication_dir / "physical_identity_gate.json"
            _atomic_write_json(identity_audit_path, physical_identity_gate_audit)
            manifest["artifacts"]["physical_identity_gate"] = {
                "path": str(identity_audit_path.resolve()), "sha256": _sha256(identity_audit_path),
                "written_after_prompt_bound_matches_sha256": matches_hash,
                "supplied_to_any_model": False,
            }

        audit, semantics = build_audit_and_semantics(
            final_decisions,
            source_map,
            prompt_bound_matches,
            shot_id=shot_id,
            verification_target_reasons=target_reasons,
            verifier_reports=(
                [verifier_reports[item] for item in VERIFIER_IDS]
                if verifier_reports
                else ()
            ),
            initial_decisions=initial_payload,
        )
        semantics = shot_graph.normalize_and_validate_semantics(semantics, sample)
        normalized_entities = {entity["id"]: entity for entity in semantics["entities"]}
        for cluster in audit["candidate_clusters"]:
            final_id = cluster["final_entity_id"]
            if final_id is not None:
                cluster["final_entity"] = normalized_entities[final_id]
        audit_path = adjudication_dir / "ensemble_audit.json"
        final_path = run_dir / "final_semantics.json"
        _atomic_write_json(audit_path, audit)
        _atomic_write_json(final_path, semantics)
        manifest["artifacts"]["ensemble_audit"] = {
            "path": str(audit_path.resolve()),
            "sha256": _sha256(audit_path),
        }
        manifest["artifacts"]["final_semantics"] = {
            "path": str(final_path.resolve()),
            "sha256": _sha256(final_path),
        }
        manifest.update(
            {
                "status": "success",
                "end_utc": _utc_now(),
                "runtime_seconds": round(time.perf_counter() - started, 6),
                "detector_count_valid": len(ledgers),
                "detector_invocations": detector_invocations,
                "adjudicator_invocations": adjudicator_invocations,
                "verifier_invocations": verifier_invocations,
                "matcher_invocations": matcher_invocations,
                "granularity_invocations": granularity_invocations,
                "token_usage": _aggregate_usage(usages),
            }
        )
        _atomic_write_json(manifest_path, manifest)
        return EnsembleResult(
            semantics=semantics,
            token_usage=manifest["token_usage"],
            runtime_seconds=time.perf_counter() - started,
            run_dir=run_dir,
            audit_path=audit_path,
            detector_invocations=detector_invocations,
            adjudicator_invocations=adjudicator_invocations,
            verifier_invocations=verifier_invocations,
            matcher_invocations=matcher_invocations,
            granularity_invocations=granularity_invocations,
            grounding_frame_ids_by_entity=audit[
                "grounding_frame_ids_by_entity"
            ],
        )
    except EnsembleIncompleteError:
        raise
    except Exception as exc:
        manifest.update(
            {
                "status": "failed",
                "end_utc": _utc_now(),
                "runtime_seconds": round(time.perf_counter() - started, 6),
                "error": str(exc),
                "detector_invocations": detector_invocations,
                "adjudicator_invocations": adjudicator_invocations,
                "verifier_invocations": verifier_invocations,
                "matcher_invocations": matcher_invocations,
                "granularity_invocations": granularity_invocations,
                "token_usage": _aggregate_usage(usages),
            }
        )
        _atomic_write_json(manifest_path, manifest)
        if isinstance(exc, EnsembleError):
            raise
        raise EnsembleError(str(exc)) from exc
