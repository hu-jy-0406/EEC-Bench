import json
import hashlib
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image
from test_accepted_compact_assembly_stage import _scope_review, _reference_review


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ensemble_shot_entity_detection as ENSEMBLE  # noqa: E402
import prompt_unbound_common as COMMON  # noqa: E402


def _usage(input_tokens, output_tokens):
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": 0,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def _cluster(
    cluster_id,
    proposal_ids,
    name,
    frame_ids,
    *,
    decision="accept",
):
    accepted = decision == "accept"
    return {
        "cluster_id": cluster_id,
        "anonymous_proposal_ids": list(proposal_ids),
        "canonical_name": name,
        "aliases": [name],
        "granularity": "whole_instance",
        "adjudicator_evidence": (
            [
                {
                    "frame_id": frame_ids[0],
                    "coarse_locator": f"stable pixels for {name}",
                    "support_quality": "strong",
                }
            ]
            if accepted
            else []
        ),
        "frame_presence": [
            {
                "frame_id": frame_id,
                "status": "visible" if accepted else "uncertain",
                "description": f"{name} at frame {frame_id}",
                # This detector-like field is deliberately present in the private
                # baseline so the accepted-only projection test can prove it is
                # removed.
                "bbox_xyxy_normalized": [0.1, 0.1, 0.3, 0.3],
            }
            for frame_id in frame_ids
        ],
        "identity_status": "resolved" if accepted else "ambiguous",
        "decision": decision,
        "decision_reason": "private adjudicator decision",
        "uncertainty_flags": ["private_provenance_flag"],
        "detector_support_count": 4,
        "detector_local_secret": "must-not-reach-planner",
        "final_entity": (
            {
                "name": name,
                "attributes": [],
                "entity_confidence": 0.9,
                "evidence_frame_ids": [frame_ids[0]],
            }
            if accepted
            else None
        ),
    }


def _baseline(frame_ids=(10, 20)):
    return {
        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
        "shot_id": "shot1",
        "clusters": [
            _cluster("c_left", ["p0001"], "left fixture", frame_ids),
            _cluster("c_right", ["p0002"], "right fixture", frame_ids),
            _cluster(
                "c_rejected",
                ["p0003"],
                "rejected_entity_sentinel",
                frame_ids,
                decision="reject",
            ),
        ],
        "warnings": [],
    }


def _candidate_id(anchor_ids):
    payload = json.dumps(
        {"anchor_cluster_ids": sorted(anchor_ids)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"aca_{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


def _empty_plan(accepted_ids, candidate_anchors=("c_left", "c_right")):
    candidate_ids = (
        [_candidate_id(candidate_anchors)] if candidate_anchors else []
    )
    return {
        "protocol_version": ENSEMBLE.accepted_assembly_stage.PLAN_PROTOCOL,
        "shot_id": "shot1",
        "reviewed_accepted_cluster_ids": list(accepted_ids),
        "reviewed_candidate_ids": candidate_ids,
        "families": [],
        "excluded_candidates": (
            [
                {
                    "candidate_id": candidate_ids[0],
                    "anchor_cluster_ids": list(candidate_anchors),
                    "reason_code": "insufficient_positive_same_role_cohesion",
                    "evidence": [],
                    "reason": "No positive two-frame cohesion is visible.",
                }
            ]
            if candidate_ids
            else []
        ),
        "warnings": [],
    }


def _anonymous_view(frame_ids=(10, 20)):
    proposals = []
    for proposal_id, name in (
        ("p0001", "left fixture"),
        ("p0002", "right fixture"),
        ("p0003", "rejected sentinel"),
    ):
        proposals.append(
            {
                "anonymous_proposal_id": proposal_id,
                "proposed_name": name,
                "canonical_head": "fixture" if proposal_id != "p0003" else "sentinel",
                "entity_type": "furnishing",
                "granularity": "whole_instance",
                "attributes": [],
                "evidence_frame_ids": [frame_ids[0]],
                "coarse_locators": [],
                "frame_presence": [],
                "uncertainty_flags": [],
            }
        )
    return {
        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
        "shot_id": "shot1",
        "proposals": proposals,
    }


def _explicit_partition_plans():
    plan = {
        "shot_id": "shot1",
        "families": [],
        "excluded_group_alternatives": [
            {
                "cluster_id": "c_rejected",
                "candidate_member_anchor_cluster_ids": ["c_left", "c_right"],
                "independent_context_anchor_cluster_ids": [],
            }
        ],
    }
    return [plan, json.loads(json.dumps(plan))]


def _explicit_agreeing_group_plans():
    plan = {
        "shot_id": "shot1",
        "families": [
            {
                "family_id": "explicit_family",
                "content_units": [
                    {"anchor_cluster_id": "c_left"},
                    {"anchor_cluster_id": "c_right"},
                ],
            }
        ],
        "excluded_group_alternatives": [],
    }
    return [plan, json.loads(json.dumps(plan))]


def _accepted_family_plan(family_id):
    stage = ENSEMBLE.accepted_assembly_stage
    anchor_ids = ["c_left", "c_right"]
    candidate_id = _candidate_id(anchor_ids)
    return {
        "protocol_version": stage.PLAN_PROTOCOL,
        "shot_id": "shot1",
        "reviewed_accepted_cluster_ids": anchor_ids,
        "reviewed_candidate_ids": [candidate_id],
        "families": [
            {
                "family_id": family_id,
                "candidate_id": candidate_id,
                "visual_scope": "one compact coordinated fixture",
                "anchor_cluster_ids": anchor_ids,
                "content_units": [
                    {
                        "unit_id": "u_left",
                        "anchor_cluster_id": "c_left",
                        "description": "left constituent",
                        "anchor_scope_review": _scope_review([10, 20]),
                        "pixel_evidence": [
                            {"frame_id": 10, "description": "left constituent"}
                        ],
                    },
                    {
                        "unit_id": "u_right",
                        "anchor_cluster_id": "c_right",
                        "description": "right constituent",
                        "anchor_scope_review": _scope_review([10, 20]),
                        "pixel_evidence": [
                            {"frame_id": 10, "description": "right constituent"}
                        ],
                    },
                ],
                "assembly_kind": "fixed_coordinated_array",
                "collection_scope_review": None,
                "common_visible_frame_ids": [10, 20],
                "cohesion_witnesses": [
                    {
                        "witness_id": "cw1",
                        "unit_a_id": "u_left",
                        "unit_b_id": "u_right",
                        "kind": "common_fixed_mounting_or_array",
                        "frame_ids": [10, 20],
                        "description": "Both frames show one coordinated array.",
                        "reference_review": _reference_review(anchor_ids, "common_fixed_mounting_or_array", frame_ids=(10, 20)),
                    }
                ],
                "pairwise_independence_reviews": [
                    {
                        "unit_a_id": "u_left",
                        "unit_b_id": "u_right",
                        "reviewed_frame_ids": [10, 20],
                        "checks": [
                            {
                                "kind": kind,
                                "outcome": "not_observed",
                                "evidence": [],
                                "description": f"No {kind} is observed.",
                            }
                            for kind in sorted(stage.INDEPENDENCE_KINDS)
                        ],
                    }
                ],
                "protected_relation_reviews": [
                    {
                        "kind": kind,
                        "outcome": "absent",
                        "evidence": [],
                        "description": f"The {kind} relation is absent.",
                    }
                    for kind in sorted(stage.PROTECTED_RELATION_KINDS)
                ],
                "context_exclusion_reviews": [],
                "scope_review_complete": True,
                "minimal_cohesive_closure_confirmed": True,
                "reason": "The exact candidate is one positively coordinated array.",
            }
        ],
        "excluded_candidates": [],
        "warnings": [],
    }


def _make_stage_inputs(root):
    prompt_dir, attempt_dir, adjudication_dir, work_dirs = _stage_paths(root)
    frame_paths = []
    reference_frames = []
    for attachment_index, frame_id in enumerate((10, 20), start=1):
        frame_path = root / f"frame_{frame_id}.jpg"
        frame_path.write_bytes(f"frame-{frame_id}".encode())
        frame_paths.append(frame_path)
        reference_frames.append(
            {
                "attachment_index": attachment_index,
                "frame_id": frame_id,
                "timestamp_sec": float(frame_id),
                "path": str(frame_path),
                "sha256": "frame-hash",
            }
        )
    return {
        "shot_id": "shot1",
        "shot_manifest": {
            "shot_id": "shot1",
            "num_frames": 21,
            "fps": 1.0,
            "reference_frames": reference_frames,
        },
        "attachments": frame_paths,
        "skill_text": "general partition policy",
        "baseline": _baseline(),
        "anonymous_view": _anonymous_view(),
        "anonymous_ids": ["p0001", "p0002", "p0003"],
        "valid_frame_ids": [10, 20],
        "codex_bin": "codex",
        "model": None,
        "timeout_sec": 5,
        "work_dirs": work_dirs,
        "prompt_dir": prompt_dir,
        "attempt_dir": attempt_dir,
        "adjudication_dir": adjudication_dir,
        "verbose": False,
    }


def _stage_paths(root):
    prompt_dir = root / "prompts"
    attempt_dir = root / "attempts"
    adjudication_dir = root / "adjudication"
    work_dirs = [root / "work_1", root / "work_2"]
    for path in [prompt_dir, attempt_dir, adjudication_dir, *work_dirs]:
        path.mkdir(parents=True, exist_ok=False)
    return prompt_dir, attempt_dir, adjudication_dir, work_dirs


class AcceptedCompactAssemblyHelperIntegrationTests(unittest.TestCase):
    def test_explicit_consensus_is_vetoed_when_accepted_judges_exclude(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = _make_stage_inputs(Path(directory))
            baseline = inputs["baseline"]

            def fake_codex(**_kwargs):
                return ENSEMBLE.CodexInvocation(
                    _empty_plan(["c_left", "c_right"]),
                    _usage(10, 1),
                    None,
                    0.01,
                )

            with mock.patch.object(
                ENSEMBLE, "run_codex_json", side_effect=fake_codex
            ):
                assembled, result = ENSEMBLE.run_accepted_compact_assembly_stage(
                    **inputs,
                    explicit_partition_plans=_explicit_agreeing_group_plans(),
                )

            self.assertEqual(result["candidate_count"], 1)
            self.assertEqual(result["status"], "no_consensus_family")
            self.assertEqual(assembled, baseline)
            self.assertEqual(
                [item["cluster_id"] for item in assembled["clusters"]],
                ["c_left", "c_right", "c_rejected"],
            )

    def test_final_merge_requires_explicit_candidate_and_two_accepted_judges(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = _make_stage_inputs(Path(directory))

            def fake_codex(**kwargs):
                planner_index = kwargs["work_dir"].name.rsplit("_", 1)[1]
                return ENSEMBLE.CodexInvocation(
                    _accepted_family_plan(f"accepted_family_{planner_index}"),
                    _usage(10, 1),
                    None,
                    0.01,
                )

            with mock.patch.object(
                ENSEMBLE, "run_codex_json", side_effect=fake_codex
            ):
                assembled, result = ENSEMBLE.run_accepted_compact_assembly_stage(
                    **inputs,
                    explicit_partition_plans=_explicit_agreeing_group_plans(),
                )

            self.assertEqual(result["candidate_count"], 1)
            self.assertEqual(result["status"], "applied")
            accepted = [
                item for item in assembled["clusters"] if item["decision"] == "accept"
            ]
            self.assertEqual(len(accepted), 1)
            self.assertEqual(
                accepted[0]["anonymous_proposal_ids"], ["p0001", "p0002"]
            )
            self.assertNotIn(
                "c_left", {item["cluster_id"] for item in assembled["clusters"]}
            )
            self.assertNotIn(
                "c_right", {item["cluster_id"] for item in assembled["clusters"]}
            )

    def test_empty_mandatory_candidate_bank_is_a_zero_call_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = _make_stage_inputs(Path(directory))
            baseline = inputs["baseline"]
            empty_explicit_plan = {
                "shot_id": "shot1",
                "families": [],
                "excluded_group_alternatives": [],
            }

            with mock.patch.object(
                ENSEMBLE,
                "run_codex_json",
                side_effect=AssertionError("empty candidate bank must skip calls"),
            ) as codex_call:
                assembled, result = ENSEMBLE.run_accepted_compact_assembly_stage(
                    **inputs,
                    explicit_partition_plans=[
                        empty_explicit_plan,
                        json.loads(json.dumps(empty_explicit_plan)),
                    ],
                )

            codex_call.assert_not_called()
            self.assertEqual(result["candidate_count"], 0)
            self.assertEqual(result["invocation_count"], 0)
            self.assertEqual(result["status"], "deterministically_skipped")
            self.assertEqual(assembled, baseline)

    def test_two_planners_are_input_identical_isolated_and_fully_accounted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt_dir, attempt_dir, adjudication_dir, work_dirs = _stage_paths(root)
            frame_paths = []
            reference_frames = []
            for attachment_index, frame_id in enumerate((10, 20), start=1):
                frame_path = root / f"frame_{frame_id}.jpg"
                frame_path.write_bytes(f"frame-{frame_id}".encode())
                frame_paths.append(frame_path)
                reference_frames.append(
                    {
                        "attachment_index": attachment_index,
                        "frame_id": frame_id,
                        "timestamp_sec": float(frame_id),
                        "path": str(frame_path),
                        "sha256": "frame-hash",
                    }
                )
            shot_manifest = {
                "shot_id": "shot1",
                "num_frames": 21,
                "fps": 1.0,
                "reference_frames": reference_frames,
                "prompt_bound_registry": "/private/registry-secret.json",
                "prompt_bound_registry_semantic": (
                    "/private/registry-semantic-secret.json"
                ),
            }
            calls = []
            call_lock = threading.Lock()

            def fake_codex(**kwargs):
                planner_index = int(kwargs["work_dir"].name.rsplit("_", 1)[1])
                with call_lock:
                    calls.append(kwargs)
                return ENSEMBLE.CodexInvocation(
                    _empty_plan(["c_left", "c_right"]),
                    _usage(10 * planner_index, planner_index),
                    f"thread-{planner_index}",
                    0.01,
                )

            with mock.patch.object(
                ENSEMBLE, "run_codex_json", side_effect=fake_codex
            ):
                assembled, result = ENSEMBLE.run_accepted_compact_assembly_stage(
                    shot_id="shot1",
                    shot_manifest=shot_manifest,
                    attachments=frame_paths,
                    skill_text="general partition policy",
                    baseline=_baseline(),
                    anonymous_view=_anonymous_view(),
                    explicit_partition_plans=_explicit_partition_plans(),
                    anonymous_ids=["p0001", "p0002", "p0003"],
                    valid_frame_ids=[10, 20],
                    codex_bin="codex",
                    model=None,
                    timeout_sec=5,
                    work_dirs=work_dirs,
                    prompt_dir=prompt_dir,
                    attempt_dir=attempt_dir,
                    adjudication_dir=adjudication_dir,
                    verbose=False,
                )

            self.assertEqual(assembled, _baseline())
            self.assertEqual(result["status"], "no_consensus_family")
            self.assertEqual(result["invocation_count"], 2)
            self.assertEqual(
                result["token_usages"], [_usage(10, 1), _usage(20, 2)]
            )
            self.assertEqual(
                [(item["planner_index"], item["attempt"]) for item in result["attempts"]],
                [(1, 1), (2, 1)],
            )

            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]["prompt"], calls[1]["prompt"])
            self.assertEqual(calls[0]["attachments"], calls[1]["attachments"])
            self.assertEqual(calls[0]["schema_path"], calls[1]["schema_path"])
            self.assertEqual(calls[0]["schema_path"], ENSEMBLE.ACCEPTED_ASSEMBLY_SCHEMA)
            self.assertEqual(
                {call["work_dir"] for call in calls}, set(work_dirs)
            )
            self.assertTrue(all(call["persistent"] is False for call in calls))

            serialized_input = result["paths"]["planner_input"].read_text(
                encoding="utf-8"
            )
            serialized_bank = result["paths"]["candidate_bank"].read_text(
                encoding="utf-8"
            )
            serialized_prompt = result["prompt_path"].read_text(encoding="utf-8")
            for forbidden in (
                "prompt_bound_registry",
                "registry-secret",
                "detector_local_secret",
                "must-not-reach-planner",
                "bbox_xyxy_normalized",
                "rejected_entity_sentinel",
                "p0001",
                "private_provenance_flag",
            ):
                self.assertNotIn(forbidden, serialized_input)
                self.assertNotIn(forbidden, serialized_bank)
                self.assertNotIn(forbidden, serialized_prompt)
            self.assertIn("c_left", serialized_input)
            self.assertIn("c_right", serialized_prompt)
            self.assertTrue(all(path.is_file() for path in result["paths"].values()))

    def test_failed_planner_returns_complete_attempt_and_usage_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt_dir, attempt_dir, adjudication_dir, work_dirs = _stage_paths(root)
            frame_paths = []
            reference_frames = []
            for attachment_index, frame_id in enumerate((10, 20), start=1):
                frame_path = root / f"frame_{frame_id}.jpg"
                frame_path.write_bytes(f"frame-{frame_id}".encode())
                frame_paths.append(frame_path)
                reference_frames.append(
                    {
                        "attachment_index": attachment_index,
                        "frame_id": frame_id,
                        "timestamp_sec": float(frame_id),
                        "path": str(frame_path),
                        "sha256": "frame-hash",
                    }
                )
            shot_manifest = {
                "shot_id": "shot1",
                "num_frames": 21,
                "fps": 1.0,
                "reference_frames": reference_frames,
            }

            def fake_codex(**kwargs):
                if kwargs["work_dir"] == work_dirs[0]:
                    kwargs["events_path"].write_text(
                        json.dumps({"usage": _usage(30, 3)}) + "\n",
                        encoding="utf-8",
                    )
                    raise ENSEMBLE.EnsembleError("planner one invalid")
                return ENSEMBLE.CodexInvocation(
                    _empty_plan(["c_left", "c_right"]),
                    _usage(40, 4),
                    "thread-2",
                    0.01,
                )

            baseline = _baseline()
            with mock.patch.object(
                ENSEMBLE, "run_codex_json", side_effect=fake_codex
            ):
                assembled, result = ENSEMBLE.run_accepted_compact_assembly_stage(
                    shot_id="shot1",
                    shot_manifest=shot_manifest,
                    attachments=frame_paths,
                    skill_text="general partition policy",
                    baseline=baseline,
                    anonymous_view=_anonymous_view(),
                    explicit_partition_plans=_explicit_partition_plans(),
                    anonymous_ids=["p0001", "p0002", "p0003"],
                    valid_frame_ids=[10, 20],
                    codex_bin="codex",
                    model=None,
                    timeout_sec=5,
                    work_dirs=work_dirs,
                    prompt_dir=prompt_dir,
                    attempt_dir=attempt_dir,
                    adjudication_dir=adjudication_dir,
                    verbose=False,
                )

            self.assertEqual(assembled, baseline)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["invocation_count"], 3)
            self.assertEqual(
                [(item["planner_index"], item["attempt"], item["status"])
                 for item in result["attempts"]],
                [(1, 1, "failed"), (1, 2, "failed"), (2, 1, "success")],
            )
            self.assertEqual(
                result["token_usages"],
                [_usage(30, 3), _usage(30, 3), _usage(40, 4)],
            )
            failure_path = result["paths"]["failure"]
            failure = json.loads(failure_path.read_text(encoding="utf-8"))
            self.assertEqual(failure["status"], "failed")
            self.assertEqual(failure["missing_planner_indices"], [1])
            self.assertEqual(len(failure["attempts"]), 3)
            self.assertTrue(result["paths"]["planner_2"].is_file())
            self.assertNotIn("firewall", result["paths"])
            self.assertNotIn("resolutions", result["paths"])


def _proposal(local_id, name, locator, bbox):
    return {
        "local_id": local_id,
        "proposed_name": name,
        "canonical_head": name,
        "entity_type": "furniture",
        "granularity": "whole_instance",
        "attributes": [],
        "evidence_frame_ids": [10],
        "coarse_locators": [{"frame_id": 10, "description": locator}],
        "frame_presence": [
            {
                "frame_id": 10,
                "status": "visible",
                "description": locator,
                "bbox_xyxy_normalized": bbox,
            }
        ],
        "self_confidence": 0.9,
        "uncertainty_flags": [],
    }


def _ledger(detector_id):
    entities = [
        _proposal(
            f"{detector_id}_left",
            "desk",
            "broad wooden workstation along far left wall",
            [0.02, 0.40, 0.42, 0.95],
        ),
        _proposal(
            f"{detector_id}_right",
            "armchair",
            "upholstered seat beside far right doorway",
            [0.62, 0.35, 0.95, 0.92],
        ),
    ]
    local_ids = [proposal["local_id"] for proposal in entities]
    return {
        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
        "shot_id": "shot1",
        "detector_id": detector_id,
        "source_kind": "detector",
        "accessed_input_paths": [],
        "entities": entities,
        "coverage_audit": {
            "reviewed_frame_ids": [10],
            "spatial_cells": [
                {
                    "cell": cell,
                    "best_frame_id": 10,
                    "represented_local_ids": local_ids if index == 0 else [],
                }
                for index, cell in enumerate(ENSEMBLE.DETECTOR_SPATIAL_CELLS)
            ],
            "content_strata": [
                {
                    "stratum": stratum,
                    "represented_local_ids": local_ids if index == 0 else [],
                }
                for index, stratum in enumerate(ENSEMBLE.DETECTOR_CONTENT_STRATA)
            ],
            "temporal_reveal_checks": [],
            "residual_added_local_ids": [],
        },
        "warnings": [],
    }


def _adjudicated_cluster(cluster_id, proposal_ids, name, locator):
    return {
        "cluster_id": cluster_id,
        "anonymous_proposal_ids": proposal_ids,
        "canonical_name": name,
        "aliases": [name],
        "granularity": "whole_instance",
        "adjudicator_evidence": [
            {
                "frame_id": 10,
                "coarse_locator": locator,
                "support_quality": "strong",
            }
        ],
        "frame_presence": [
            {
                "frame_id": 10,
                "status": "visible",
                "description": locator,
            }
        ],
        "identity_status": "resolved",
        "decision": "accept",
        "decision_reason": "independently localized physical instance",
        "uncertainty_flags": [],
        "final_entity": {
            "name": name,
            "attributes": [],
            "entity_confidence": 0.9,
            "evidence_frame_ids": [10],
        },
    }


class AcceptedCompactAssemblyPipelineFailureTests(unittest.TestCase):
    def test_failed_stage_blocks_matcher_and_final_output_but_keeps_accounting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame_path = root / "source.jpg"
            Image.new("RGB", (20, 20), "white").save(frame_path)
            sample = COMMON.shot_graph.VideoSample(
                frames={10: None},
                frame_paths={10: frame_path},
                num_frames=11,
                fps=5.0,
            )
            matcher_called = False
            call_lock = threading.Lock()

            def fake_codex(**kwargs):
                nonlocal matcher_called
                prompt = kwargs["prompt"]
                if "Your detector ID is" in prompt:
                    detector_id = next(
                        role
                        for role, _, _ in ENSEMBLE.DETECTOR_ROLES
                        if f"Your detector ID is {role}." in prompt
                    )
                    return ENSEMBLE.CodexInvocation(
                        _ledger(detector_id), _usage(10, 1), None, 0.01
                    )
                if "You are now the adjudicator" in prompt:
                    anonymous = json.loads(
                        prompt.split("anonymized_candidates:\n", 1)[1]
                    )
                    by_name = {
                        name: [
                            item["anonymous_proposal_id"]
                            for item in anonymous["proposals"]
                            if item["proposed_name"] == name
                        ]
                        for name in ("desk", "armchair")
                    }
                    return ENSEMBLE.CodexInvocation(
                        {
                            "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
                            "shot_id": "shot1",
                            "clusters": [
                                _adjudicated_cluster(
                                    "c_left",
                                    by_name["desk"],
                                    "desk",
                                    "far left workstation",
                                ),
                                _adjudicated_cluster(
                                    "c_right",
                                    by_name["armchair"],
                                    "armchair",
                                    "far right doorway seat",
                                ),
                            ],
                            "warnings": [],
                        },
                        _usage(20, 2),
                        "adjudicator-thread",
                        0.01,
                    )
                if "accepted_only_source_blind_inventory:" in prompt:
                    if kwargs["work_dir"].name.endswith("_1"):
                        return ENSEMBLE.CodexInvocation(
                            _empty_plan(["c_left"]),
                            _usage(30, 3),
                            "invalid-planner-one-thread",
                            0.01,
                        )
                    accepted_view = json.loads(
                        prompt.split(
                            "accepted_only_source_blind_inventory:\n", 1
                        )[1]
                    )
                    return ENSEMBLE.CodexInvocation(
                        _empty_plan(
                            [
                                item["cluster_id"]
                                for item in accepted_view["accepted_clusters"]
                            ]
                        ),
                        _usage(40, 4),
                        "planner-two-thread",
                        0.01,
                    )
                if "You are the prompt-bound identity matcher" in prompt:
                    with call_lock:
                        matcher_called = True
                    raise AssertionError("matcher must not run after stage failure")
                raise AssertionError(f"unexpected mocked prompt: {prompt[:120]}")

            run_dir = root / "ensemble"
            forced_candidate_bank = {
                "protocol_version": (
                    ENSEMBLE.accepted_assembly_stage.CANDIDATE_BANK_PROTOCOL
                ),
                "shot_id": "shot1",
                "candidates": [
                    {
                        "candidate_id": _candidate_id(["c_left", "c_right"]),
                        "anchor_cluster_ids": ["c_left", "c_right"],
                        "context_anchor_cluster_ids": [],
                    }
                ],
            }
            with mock.patch.object(ENSEMBLE, "_codex_version", return_value="test"):
                with mock.patch.object(
                    ENSEMBLE, "run_codex_json", side_effect=fake_codex
                ):
                    with mock.patch.object(
                        ENSEMBLE.accepted_assembly_stage,
                        "build_candidate_bank",
                        return_value=(
                            forced_candidate_bank,
                            {
                                "protocol_version": (
                                    ENSEMBLE.accepted_assembly_stage.CANDIDATE_BANK_PROTOCOL
                                ),
                                "shot_id": "shot1",
                                "candidates": [],
                            },
                        ),
                    ):
                        with self.assertRaisesRegex(
                            ENSEMBLE.EnsembleError,
                            "Missing valid accepted-only compact-assembly plan",
                        ):
                            ENSEMBLE.run_ensemble_detection(
                                sample=sample,
                                shot_id="shot1",
                                prompt_entities=[],
                                run_dir=run_dir,
                                codex_bin="codex",
                                model=None,
                                timeout_sec=5,
                                max_workers=4,
                            )

            self.assertFalse(matcher_called)
            self.assertFalse((run_dir / "matching").exists())
            self.assertFalse((run_dir / "final_semantics.json").exists())
            self.assertFalse(
                (run_dir / "adjudication" / "source_map.json").exists()
            )
            manifest = json.loads(
                (run_dir / "run_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(
                manifest["granularity_policy"]["compact_local_assembly_default"],
                "preserve_frozen_baseline_without_positive_cohesion_and_exact_consensus",
            )
            self.assertEqual(manifest["granularity_family"]["planner_count"], 2)
            self.assertEqual(
                manifest["granularity_family"]["valid_planner_count"], 2
            )
            self.assertEqual(
                manifest["granularity_family"]["planner_invocation_count"], 0
            )
            self.assertEqual(
                manifest["granularity_family"]["synthetic_empty_plan_count"], 2
            )
            self.assertTrue(
                manifest["granularity_family"][
                    "exact_family_member_partition_consensus_required"
                ]
            )
            for artifact in (
                "granularity_group_member_planner_1",
                "granularity_group_member_planner_2",
                "granularity_group_member_consensus",
                "granularity_group_member_application_plan",
            ):
                self.assertIn(artifact, manifest["artifacts"])
            self.assertEqual(manifest["accepted_compact_assembly"]["status"], "failed")
            self.assertEqual(
                manifest["accepted_compact_assembly"]["planner_invocation_count"],
                3,
            )
            self.assertEqual(
                len(manifest["accepted_compact_assembly_attempts"]), 3
            )
            self.assertIn(
                "accepted_compact_assembly_failure", manifest["artifacts"]
            )
            self.assertIn(
                "accepted_compact_assembly_planner.txt", manifest["prompt_hashes"]
            )
            self.assertEqual(
                manifest["token_usage"],
                {
                    "input_tokens": 160,
                    "cached_input_tokens": 0,
                    "output_tokens": 16,
                    "total_tokens": 176,
                },
                msg=json.dumps(
                    manifest["accepted_compact_assembly_attempts"], indent=2
                ),
            )


if __name__ == "__main__":
    unittest.main()
