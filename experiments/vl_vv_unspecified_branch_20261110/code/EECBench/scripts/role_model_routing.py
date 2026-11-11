"""Private opt-in model routing and auditable CLI request descriptions.

These records describe requested execution, never server-side model attestation
or evidence about an entity. A request record is not proof that a process ran.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path


POLICY_VERSION = "ensemble_role_model_routing_v0.1"
REQUEST_VERSION = "ensemble_role_model_request_v0.1"
ROLE_GROUPS = {
    "detector": "primary", "detector_closure": "primary",
    "adjudicator_initial": "review", "adjudicator_revision": "review",
    "verifier": "review", "granularity_group_member": "review",
    "accepted_compact_assembly": "review", "prompt_bound_matcher": "primary",
}


def json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_model_routing(primary_model, review_model=None):
    if review_model is None:
        return None  # Preserve configured-default and all legacy request behavior.
    for label, value in (("primary_model", primary_model), ("review_model", review_model)):
        if value is None and label == "primary_model":
            continue
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError(label + " must be a nonempty model name")
    return {"policy_version": POLICY_VERSION, "primary_model": primary_model,
            "declared_review_model": review_model, "effective_review_model": review_model,
            "role_models": {role: primary_model if group == "primary" else review_model
                            for role, group in ROLE_GROUPS.items()}}


def request_context(routing, *, role, role_id, attempt, shot_id,
                    round_index=None, initial_request=None):
    if routing is None:
        return None
    expected = resolve_model_routing(routing["primary_model"], routing["declared_review_model"])
    if routing != expected or role not in ROLE_GROUPS:
        raise ValueError("Invalid model routing configuration or role")
    allowed_ids = {
        "detector": [f"detector_{i}" for i in range(1, 5)],
        "detector_closure": [f"detector_{i}" for i in range(1, 5)],
        "verifier": [f"verifier_{i}" for i in (1, 2)],
        "granularity_group_member": [f"granularity_group_member_planner_{i}" for i in (1, 2)],
        "accepted_compact_assembly": [f"accepted_compact_assembly_planner_{i}" for i in (1, 2)],
    }
    if (role_id not in allowed_ids.get(role, [role]) or type(attempt) is not int
            or attempt not in (1, 2) or not isinstance(shot_id, str) or not shot_id):
        raise ValueError("Invalid model request slot")
    if role == "adjudicator_initial" and attempt != 1:
        raise ValueError("Initial adjudication has no retry slot")
    if role == "detector_closure":
        if type(round_index) is not int or not 1 <= round_index <= 4:
            raise ValueError("Invalid closure round")
    elif round_index is not None:
        raise ValueError("Only closure requests have a round")
    if (role == "adjudicator_revision") != (initial_request is not None):
        raise ValueError("Only revision requests require an initial binding")
    return {"routing_config_sha256": json_hash(routing), "role": role, "role_id": role_id,
            "attempt": attempt, "round_index": round_index, "shot_id": shot_id,
            "requested_model": routing["role_models"][role], "model_group": ROLE_GROUPS[role],
            "initial_request": copy.deepcopy(initial_request)}


def request_kwargs(context):
    return {} if context is None else {"request_context": context}


def request_path(events_path):
    path = Path(events_path)
    suffix = ".events.jsonl"
    if not path.name.endswith(suffix):
        raise ValueError("Model request requires a standard events stem")
    return path.with_name(path.name[:-len(suffix)] + ".request.json")


def build_request_audit(context, *, model, command, prompt, attachments, schema_path,
                        output_path, events_path, stderr_path, codex_bin, work_dir,
                        persistent, resume_thread_id):
    """Bind the exact assembled argv to the preselected role and initial call."""
    c = copy.deepcopy(context)
    if model != c["requested_model"] or ROLE_GROUPS.get(c["role"]) != c["model_group"]:
        raise ValueError("Actual requested model differs from role model routing")
    positions = [i for i, arg in enumerate(command) if arg == "--model"]
    if ((model is None and positions) or
            (model is not None and (len(positions) != 1 or command[positions[0] + 1] != model))):
        raise ValueError("Actual CLI argv does not select the routed model")
    role = c["role"]
    if role == "adjudicator_initial":
        if not persistent or resume_thread_id is not None:
            raise ValueError("Initial review must open one persistent thread")
    elif role == "adjudicator_revision":
        initial = c["initial_request"]
        if (not isinstance(initial, dict) or set(initial) != {"path", "sha256", "thread_id"}
                or not initial["thread_id"] or resume_thread_id != initial["thread_id"]
                or file_hash(initial["path"]) != initial["sha256"]):
            raise ValueError("Revision initial request/thread binding changed")
        origin = json.loads(Path(initial["path"]).read_text())
        if (origin.get("policy_version") != REQUEST_VERSION
                or origin.get("role") != "adjudicator_initial"
                or origin.get("shot_id") != c["shot_id"]
                or origin.get("requested_model") != model
                or origin.get("routing_config_sha256") != c["routing_config_sha256"]
                or origin.get("persistent") is not True or origin.get("resume_thread_id") is not None):
            raise ValueError("Revision differs from the initial review model/configuration")
    elif persistent or resume_thread_id is not None:
        raise ValueError("Only initial/revision use persistent review context")
    if request_path(events_path).name != Path(output_path).stem + ".request.json":
        raise ValueError("Output and events stems differ")
    return {"policy_version": REQUEST_VERSION, **c, "argv": list(command),
            "codex_bin": codex_bin, "persistent": persistent, "resume_thread_id": resume_thread_id,
            "output_path": str(output_path), "events_path": str(events_path),
            "stderr_path": str(stderr_path), "requested_work_dir": str(work_dir),
            "process_cwd": str(Path.cwd()),
            "schema": {"path": str(schema_path), "sha256": file_hash(schema_path)},
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "attachments": [{"path": str(p), "sha256": file_hash(p)} for p in attachments]}


def accounting_fragment(context, events_path):
    if context is None:
        return {}
    path = request_path(events_path)
    record = {"status": "not_materialized", "path": str(path), "sha256": None}
    try:
        if path.exists():
            record.update(status="persisted", sha256=file_hash(path))
    except OSError as error:
        record.update(status="unreadable", error=str(error))
    return {"requested_model": context["requested_model"], "model_group": context["model_group"],
            "model_role": context["role"], "model_request": record}
