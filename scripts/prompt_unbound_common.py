#!/usr/bin/env python3
"""Shared, auditable utilities for prompt-bound/unbound graph separation."""

from __future__ import annotations

import copy
import json
import math
import re
import shlex
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from PIL import Image


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import extract_episode_entity_graphs as episode_graphs  # noqa: E402
import extract_shot_entity_graph as shot_graph  # noqa: E402


TOKEN_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "total_tokens",
)
SCHEDULE_CATEGORIES = (
    ("characters", "character"),
    ("places", "location"),
    ("objects", "object"),
)


class PromptUnboundError(RuntimeError):
    """Raised when a prompt-bound/unbound run cannot remain auditable."""


@dataclass(frozen=True)
class PromptBoundTarget:
    name: str
    description: str
    entity_type: str
    schedule_category: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: Optional[datetime] = None) -> str:
    return (value or utc_now()).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromptUnboundError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PromptUnboundError(f"Expected a JSON object in {path}")
    return value


def _schedule_sort_key(key: str) -> Tuple[Any, ...]:
    parts = re.split(r"([0-9]+)", key)
    return tuple(int(part) if part.isdigit() else part.lower() for part in parts)


def normalize_name(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    words = text.split()
    while words and words[0] in {"a", "an", "the"}:
        words.pop(0)
    return " ".join(words)


def name_similarity(left: str, right: str) -> float:
    """Combine normalized character and token similarity without an LLM."""
    a, b = normalize_name(left), normalize_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sequence = SequenceMatcher(None, a, b).ratio()
    a_tokens, b_tokens = set(a.split()), set(b.split())
    overlap = len(a_tokens & b_tokens)
    token_f1 = (
        2.0 * overlap / (len(a_tokens) + len(b_tokens))
        if a_tokens and b_tokens
        else 0.0
    )
    containment = 0.9 if a in b or b in a else 0.0
    return max(sequence, token_f1, containment)


def load_schedule_bundle(path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    payload = read_json(path)
    schedule = payload.get("entity_schedule", payload)
    descriptions = payload.get("entity_descriptions", {})
    if not isinstance(schedule, dict) or not schedule:
        raise PromptUnboundError(f"entity_schedule is missing or empty in {path}")
    if not isinstance(descriptions, dict):
        raise PromptUnboundError(f"entity_descriptions must be an object in {path}")
    for shot_key, entry in schedule.items():
        if not isinstance(shot_key, str) or not isinstance(entry, dict):
            raise PromptUnboundError(f"Invalid schedule entry {shot_key!r} in {path}")
        for category, _ in SCHEDULE_CATEGORIES:
            names = entry.get(category, [])
            if not isinstance(names, list) or not all(
                isinstance(name, str) and name.strip() for name in names
            ):
                raise PromptUnboundError(
                    f"entity_schedule[{shot_key!r}].{category} must be strings"
                )
    return schedule, descriptions


def ordered_schedule_keys(schedule: Mapping[str, Any]) -> List[str]:
    return sorted(schedule, key=_schedule_sort_key)


def map_shots_to_schedule(
    shots: Sequence[Path],
    schedule: Mapping[str, Any],
    explicit_keys: Optional[Sequence[str]] = None,
) -> List[Tuple[Path, str]]:
    keys = list(explicit_keys) if explicit_keys is not None else ordered_schedule_keys(schedule)
    if len(keys) != len(shots):
        raise PromptUnboundError(
            f"Found {len(shots)} shot(s) but {len(keys)} selected schedule key(s). "
            "Pass --shot-keys in shot-file order when automatic ordering is unsuitable."
        )
    unknown = [key for key in keys if key not in schedule]
    if unknown:
        raise PromptUnboundError(f"Unknown schedule key(s): {unknown}")
    if len(set(keys)) != len(keys):
        raise PromptUnboundError("--shot-keys contains duplicates")
    return list(zip(shots, keys))


def _description_lookup(descriptions: Mapping[str, Any]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for label, info in descriptions.items():
        if isinstance(info, Mapping):
            name = info.get("name", label)
            description = info.get("description", name)
        else:
            name = label
            description = info
        if isinstance(name, str) and name.strip():
            desc = description if isinstance(description, str) else name
            result[normalize_name(name)] = desc.strip() or name.strip()
    return result


def targets_for_shot(
    schedule_entry: Mapping[str, Any], descriptions: Mapping[str, Any]
) -> List[PromptBoundTarget]:
    lookup = _description_lookup(descriptions)
    targets: List[PromptBoundTarget] = []
    seen = set()
    for category, entity_type in SCHEDULE_CATEGORIES:
        for raw_name in schedule_entry.get(category, []) or []:
            normalized = normalize_name(raw_name)
            if normalized in seen:
                continue
            seen.add(normalized)
            targets.append(
                PromptBoundTarget(
                    name=raw_name.strip(),
                    description=lookup.get(normalized, raw_name.strip()),
                    entity_type=entity_type,
                    schedule_category=category,
                )
            )
    return targets


def load_sample_from_graph(graph: Mapping[str, Any], frame_dir: Path) -> shot_graph.VideoSample:
    metadata = graph.get("shot_metadata")
    if not isinstance(metadata, Mapping):
        raise PromptUnboundError("Graph is missing shot_metadata")
    try:
        reference_ids = [int(value) for value in metadata["reference_frame_ids"]]
        num_frames = int(metadata["num_frames"])
        fps = float(metadata["fps"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PromptUnboundError("Graph has invalid shot timing metadata") from exc
    frames: Dict[int, Any] = {}
    frame_paths: Dict[int, Path] = {}
    try:
        import numpy as np
    except ImportError as exc:
        raise PromptUnboundError("NumPy is required to load reference frames") from exc
    for frame_id in reference_ids:
        path = (frame_dir / f"frame_{frame_id:06d}.jpg").resolve()
        if not path.is_file():
            raise PromptUnboundError(f"Reference frame is missing: {path}")
        with Image.open(path) as image:
            frames[frame_id] = np.asarray(image.convert("RGB")).copy()
        frame_paths[frame_id] = path
    return shot_graph.VideoSample(
        frames=frames, frame_paths=frame_paths, num_frames=num_frames, fps=fps
    )


def ground_prompt_bound_targets(
    targets: Sequence[PromptBoundTarget],
    sample: shot_graph.VideoSample,
    *,
    device: str,
    box_threshold: float,
    text_threshold: float,
) -> Tuple[List[Dict[str, Any]], int, List[str]]:
    """Run the EntityBench detector + CLIP/quality selector on scheduled entities."""
    (
        get_grounding_dino,
        get_clip_model,
        ground_one_entity,
        crop_entity,
        compute_clip_text_sim,
        compute_selection_score,
    ) = shot_graph._load_grounding_functions()
    try:
        get_grounding_dino(device=device, strict=True)
        get_clip_model(device=device)
    except Exception as exc:
        raise PromptUnboundError(
            f"EntityBench-style GroundingDINO/CLIP stack failed to load: {exc}"
        ) from exc

    output: List[Dict[str, Any]] = []
    warnings: List[str] = []
    n_calls = 0
    for index, target in enumerate(targets, start=1):
        boxes: List[Dict[str, Any]] = []
        canonical: Optional[Dict[str, Any]] = None
        for frame_id in sample.reference_frame_ids:
            frame = sample.frames[frame_id]
            frame_height, frame_width = frame.shape[:2]
            n_calls += 1
            try:
                raw = list(
                    ground_one_entity(
                        frame,
                        entity_name=target.name,
                        description=target.description,
                        entity_type=target.entity_type,
                        device=device,
                        box_threshold=box_threshold,
                        text_threshold=text_threshold,
                        return_all=True,
                        strict=True,
                    )
                )
            except Exception as exc:
                raise PromptUnboundError(
                    f"GroundingDINO failed for {target.name!r} on frame {frame_id}: {exc}"
                ) from exc
            cleaned, rejected, truncated = shot_graph.sanitize_grounding_candidates(
                raw,
                frame_width=frame_width,
                frame_height=frame_height,
                max_candidates=max(1, len(raw)),
            )
            if rejected:
                warnings.append(
                    f"Discarded {rejected} invalid candidate(s) for {target.name!r} "
                    f"on frame {frame_id}."
                )
            if truncated:
                raise PromptUnboundError("Scheduled-entity candidates were unexpectedly truncated")

            best: Optional[Dict[str, Any]] = None
            for detection in cleaned:
                crop = crop_entity(frame, detection["bbox"])
                try:
                    clip_score = compute_clip_text_sim(crop, target.description, device)
                    components = compute_selection_score(
                        clip_score, crop, frame.shape
                    )
                except Exception as exc:
                    raise PromptUnboundError(
                        f"CLIP candidate scoring failed for {target.name!r}: {exc}"
                    ) from exc
                candidate = {
                    "frame_id": frame_id,
                    "bbox_xyxy_normalized": [
                        round(max(0.0, min(1.0, detection["bbox"][0] / frame_width)), 6),
                        round(max(0.0, min(1.0, detection["bbox"][1] / frame_height)), 6),
                        round(max(0.0, min(1.0, detection["bbox"][2] / frame_width)), 6),
                        round(max(0.0, min(1.0, detection["bbox"][3] / frame_height)), 6),
                    ],
                    "score": round(float(detection["confidence"]), 6),
                    "clip_score": round(float(clip_score), 6),
                    "selection_score": round(float(components["selection"]), 8),
                }
                if best is None or candidate["selection_score"] > best["selection_score"]:
                    best = candidate
            if best is not None:
                boxes.append(best)
                if canonical is None or best["selection_score"] > canonical["selection_score"]:
                    canonical = best

        status = (
            "grounded"
            if boxes and len(boxes) == len(sample.reference_frame_ids)
            else "partially_grounded"
            if boxes
            else "not_found"
        )
        output.append(
            {
                "id": f"pb{index}",
                **asdict(target),
                "grounding": {
                    "query": target.description,
                    "status": status,
                    "boxes": boxes,
                    "canonical_detection": canonical,
                },
            }
        )
    return output, n_calls, warnings


def bbox_iou(left: Sequence[float], right: Sequence[float]) -> float:
    return shot_graph.bbox_iou(left, right)


def _boxes_by_frame(entity: Mapping[str, Any]) -> Dict[int, List[Sequence[float]]]:
    grounding = entity.get("grounding", {})
    boxes = grounding.get("boxes", []) if isinstance(grounding, Mapping) else []
    result: Dict[int, List[Sequence[float]]] = {}
    if not isinstance(boxes, list):
        return result
    for box in boxes:
        if not isinstance(box, Mapping):
            continue
        frame_id = box.get("frame_id")
        coords = box.get("bbox_xyxy_normalized")
        if (
            isinstance(frame_id, int)
            and isinstance(coords, list)
            and len(coords) == 4
        ):
            result.setdefault(frame_id, []).append(coords)
    return result


def compare_entity_pair(
    graph_entity: Mapping[str, Any],
    prompt_entity: Mapping[str, Any],
    *,
    name_match_threshold: float,
    box_iou_threshold: float,
    combined_threshold: float,
) -> Dict[str, Any]:
    name_score = name_similarity(str(graph_entity.get("name", "")), str(prompt_entity.get("name", "")))
    graph_boxes = _boxes_by_frame(graph_entity)
    prompt_boxes = _boxes_by_frame(prompt_entity)
    common_frames = sorted(set(graph_boxes) & set(prompt_boxes))
    frame_ious = []
    for frame_id in common_frames:
        frame_ious.append(
            max(
                bbox_iou(left, right)
                for left in graph_boxes[frame_id]
                for right in prompt_boxes[frame_id]
            )
        )
    mean_iou = sum(frame_ious) / len(frame_ious) if frame_ious else None
    max_iou = max(frame_ious) if frame_ious else None
    geometry_score = mean_iou or 0.0
    combined = 0.55 * name_score + 0.45 * geometry_score

    normalized_identity = (
        normalize_name(str(graph_entity.get("name", "")))
        == normalize_name(str(prompt_entity.get("name", "")))
    )
    semantic_identity = normalized_identity or name_score >= name_match_threshold
    grounding_overlap = mean_iou is not None and mean_iou >= box_iou_threshold
    grounding_identity = grounding_overlap and combined >= combined_threshold
    is_match = semantic_identity and grounding_identity
    reason = (
        "normalized_name_plus_grounding"
        if is_match and normalized_identity
        else "name_plus_grounding"
        if is_match
        else "grounding_overlap_without_semantic_identity"
        if grounding_overlap and not semantic_identity
        else "semantic_identity_without_grounding"
        if semantic_identity and not grounding_identity
        else "below_threshold"
    )
    return {
        "graph_entity_id": graph_entity.get("id"),
        "graph_entity_name": graph_entity.get("name"),
        "prompt_entity_id": prompt_entity.get("id"),
        "prompt_entity_name": prompt_entity.get("name"),
        "name_similarity": round(name_score, 6),
        "common_detection_frames": common_frames,
        "frame_ious": [round(value, 6) for value in frame_ious],
        "mean_iou": round(mean_iou, 6) if mean_iou is not None else None,
        "max_iou": round(max_iou, 6) if max_iou is not None else None,
        "combined_score": round(combined, 6),
        "is_match": is_match,
        "match_reason": reason,
    }


def classify_graph_entities(
    graph_entities: Sequence[Mapping[str, Any]],
    prompt_entities: Sequence[Mapping[str, Any]],
    *,
    name_match_threshold: float = 0.88,
    box_iou_threshold: float = 0.50,
    combined_threshold: float = 0.60,
    protected_unbound_entity_ids: Sequence[str] = (),
) -> Dict[str, Any]:
    comparisons = [
        compare_entity_pair(
            graph_entity,
            prompt_entity,
            name_match_threshold=name_match_threshold,
            box_iou_threshold=box_iou_threshold,
            combined_threshold=combined_threshold,
        )
        for graph_entity in graph_entities
        for prompt_entity in prompt_entities
    ]
    protected = set(protected_unbound_entity_ids)
    protected_conflicts = []
    for comparison in comparisons:
        if (
            comparison["is_match"]
            and comparison["graph_entity_id"] in protected
        ):
            comparison["candidate_match_reason"] = comparison["match_reason"]
            comparison["is_match"] = False
            comparison["match_reason"] = "protected_unbound_evidence"
            protected_conflicts.append(comparison)

    eligible = [comparison for comparison in comparisons if comparison["is_match"]]
    eligible.sort(
        key=lambda item: (
            item["match_reason"] == "normalized_name_plus_grounding",
            item["combined_score"],
            item["mean_iou"] if item["mean_iou"] is not None else -1.0,
            str(item["graph_entity_id"]),
            str(item["prompt_entity_id"]),
        ),
        reverse=True,
    )
    used_graph, used_prompt = set(), set()
    matches = []
    for candidate in eligible:
        graph_id = candidate["graph_entity_id"]
        prompt_id = candidate["prompt_entity_id"]
        if graph_id in used_graph or prompt_id in used_prompt:
            continue
        used_graph.add(graph_id)
        used_prompt.add(prompt_id)
        matches.append(candidate)

    graph_ids = {entity.get("id") for entity in graph_entities}
    prompt_ids = {entity.get("id") for entity in prompt_entities}
    return {
        "thresholds": {
            "name_match_threshold": name_match_threshold,
            "box_iou_threshold": box_iou_threshold,
            "combined_threshold": combined_threshold,
            "combined_weights": {"name": 0.55, "grounding_iou": 0.45},
            "requires_semantic_and_grounding_identity": True,
        },
        "protected_unbound_entity_ids": sorted(protected),
        "protected_unbound_conflicts": protected_conflicts,
        "matches": matches,
        "prompt_bound_graph_entity_ids": sorted(used_graph),
        "prompt_unbound_graph_entity_ids": sorted(graph_ids - used_graph),
        "unmatched_prompt_bound_entity_ids": sorted(prompt_ids - used_prompt),
        "all_pair_comparisons": comparisons,
    }


def strong_ensemble_unbound_entity_ids(
    ensemble_audit: Mapping[str, Any],
) -> List[str]:
    """Return accepted ensemble entities that a noisy grounding pass cannot veto.

    In inventory-first v0.3, boxed v0.4, and granularity-aware boxed v0.5, the post-inventory matcher is
    authoritative and all projected unbound entities are protected from the
    legacy heuristic postcheck. For older protocols, protection still requires
    either repeatability from at least three detectors or two independent
    targeted confirmations.
    """
    protected: List[str] = []
    clusters = ensemble_audit.get("candidate_clusters", [])
    if not isinstance(clusters, list):
        return protected
    for cluster in clusters:
        if not isinstance(cluster, Mapping):
            continue
        prompt_check = cluster.get("prompt_bound_check", {})
        if (
            cluster.get("decision") != "accept"
            or cluster.get("identity_status") != "resolved"
            or not isinstance(prompt_check, Mapping)
            or prompt_check.get("status") != "unbound"
        ):
            continue
        if ensemble_audit.get("protocol_version") in {
            "single_shot_inventory_first_v0.3",
            "single_shot_inventory_first_boxed_v0.4",
            "single_shot_inventory_first_boxed_granularity_v0.5",
        }:
            final_id = cluster.get("final_entity_id")
            if isinstance(final_id, str) and final_id:
                protected.append(final_id)
            continue
        agreement = cluster.get("agreement", {})
        detector_support = (
            agreement.get("proposal_count", 0)
            if isinstance(agreement, Mapping)
            else 0
        )
        verification = cluster.get("targeted_verification", {})
        reports = (
            verification.get("reports", [])
            if isinstance(verification, Mapping)
            else []
        )
        confirming_verifiers = {
            report.get("verifier_id")
            for report in reports
            if isinstance(report, Mapping)
            and report.get("existence_judgment") == "confirmed"
            and report.get("salience_judgment") == "graph_worthy"
            and isinstance(report.get("verifier_id"), str)
        }
        entity_id = cluster.get("final_entity_id")
        if (
            isinstance(entity_id, str)
            and entity_id
            and (detector_support >= 3 or len(confirming_verifiers) >= 2)
        ):
            protected.append(entity_id)
    return sorted(set(protected))


def filter_graph_to_unbound(
    graph: Mapping[str, Any], prompt_bound_ids: Sequence[str], *, warning: str
) -> Dict[str, Any]:
    result = copy.deepcopy(dict(graph))
    removed = set(prompt_bound_ids)
    result["entities"] = [
        entity for entity in result.get("entities", []) if entity.get("id") not in removed
    ]
    retained = {entity.get("id") for entity in result["entities"]}
    result["relations"] = [
        relation
        for relation in result.get("relations", [])
        if relation.get("subject_id") in retained and relation.get("object_id") in retained
    ]
    warnings = list(result.get("warnings", []))
    warnings.append(warning)
    result["warnings"] = warnings
    return result


def build_prompt_bound_graph(
    prompt_entities: Sequence[Mapping[str, Any]],
    base_graph: Mapping[str, Any],
    sample: shot_graph.VideoSample,
    *,
    n_grounding_calls: int,
) -> Dict[str, Any]:
    """Convert scheduled-entity grounding records into a renderable graph.

    Scheduled entities with no visual detection remain in the raw
    ``prompt_bound_detections`` ledger but are omitted from this visual graph,
    because the graph schema requires positive visual evidence for every node.
    """
    result = copy.deepcopy(dict(base_graph))
    entities: List[Dict[str, Any]] = []
    omitted: List[str] = []
    for prompt_entity in prompt_entities:
        grounding = prompt_entity.get("grounding", {})
        raw_boxes = grounding.get("boxes", []) if isinstance(grounding, Mapping) else []
        boxes = [
            {
                "frame_id": int(box["frame_id"]),
                "bbox_xyxy_normalized": list(box["bbox_xyxy_normalized"]),
                "score": float(box["score"]),
            }
            for box in raw_boxes
            if isinstance(box, Mapping)
        ]
        if not boxes:
            omitted.append(str(prompt_entity.get("name", "unknown")))
            continue
        evidence_frame_ids = sorted({box["frame_id"] for box in boxes})
        query = grounding.get("query") if isinstance(grounding, Mapping) else None
        status = grounding.get("status") if isinstance(grounding, Mapping) else None
        if status not in {"grounded", "partially_grounded"}:
            status = (
                "grounded"
                if len(evidence_frame_ids) == len(sample.reference_frame_ids)
                else "partially_grounded"
            )
        entity = {
            "id": f"e{len(entities) + 1}",
            "name": str(prompt_entity.get("name", "prompt-bound entity")),
            "attributes": [],
            "entity_confidence": max(box["score"] for box in boxes),
            "evidence_frame_ids": evidence_frame_ids,
            "grounding": {
                "query": str(query or prompt_entity.get("description") or prompt_entity.get("name")),
                "status": status,
                "boxes": boxes,
            },
            "reference_grounding": [
                {
                    "frame_id": box["frame_id"],
                    "reference_frame_path": str(sample.frame_paths[box["frame_id"]].resolve()),
                    "bbox_xyxy_normalized": list(box["bbox_xyxy_normalized"]),
                    "score": box["score"],
                }
                for box in boxes
            ],
        }
        entities.append(entity)

    result["entities"] = entities
    result["relations"] = []
    result["warnings"] = list(result.get("warnings", [])) + [
        "Prompt-bound graph nodes are constructed from the frozen entity schedule "
        "and positive EntityBench-style grounding detections; relation extraction "
        "was not run for this schedule-derived graph."
    ]
    if omitted:
        result["warnings"].append(
            "Scheduled prompt-bound entities without a positive grounding detection "
            f"remain in the detection ledger but are omitted from this visual graph: {omitted}."
        )
    metadata = result.get("extraction_metadata")
    if isinstance(metadata, dict):
        metadata["vlm_provider"] = "precomputed_json"
        metadata["codex_model"] = "not_used_for_schedule_grounding"
        metadata["codex_token_usage"] = None
        metadata["vlm_prompt_version"] = "prompt_bound_schedule_grounding_v0.1"
        metadata["n_grounding_calls"] = n_grounding_calls
    shot_graph.validate_final_graph(result)
    return result


def merge_prompt_bound_and_unbound_graphs(
    prompt_bound_graph: Mapping[str, Any],
    prompt_unbound_graph: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build a total graph for prefilter mode without inventing cross-set edges."""
    for key in ("video_id", "shot_id", "shot_metadata"):
        if prompt_bound_graph.get(key) != prompt_unbound_graph.get(key):
            raise PromptUnboundError(
                f"Cannot merge prompt-bound and prompt-unbound graphs: {key} differs"
            )
    result = copy.deepcopy(dict(prompt_unbound_graph))
    merged_entities: List[Dict[str, Any]] = []
    merged_relations: List[Dict[str, Any]] = []

    for source_graph in (prompt_bound_graph, prompt_unbound_graph):
        id_map: Dict[str, str] = {}
        for source_entity in source_graph.get("entities", []):
            entity = copy.deepcopy(source_entity)
            new_id = f"e{len(merged_entities) + 1}"
            id_map[str(entity["id"])] = new_id
            entity["id"] = new_id
            merged_entities.append(entity)
        for source_relation in source_graph.get("relations", []):
            subject = id_map.get(str(source_relation.get("subject_id")))
            obj = id_map.get(str(source_relation.get("object_id")))
            if subject is None or obj is None:
                continue
            relation = copy.deepcopy(source_relation)
            relation["id"] = f"r{len(merged_relations) + 1}"
            relation["subject_id"] = subject
            relation["object_id"] = obj
            merged_relations.append(relation)

    result["entities"] = merged_entities
    result["relations"] = merged_relations
    result["warnings"] = list(prompt_bound_graph.get("warnings", [])) + list(
        prompt_unbound_graph.get("warnings", [])
    ) + [
        "Total graph in prefilter mode is the union of schedule-grounded prompt-bound "
        "nodes and Codex-discovered prompt-unbound nodes. Because Codex was instructed "
        "to exclude prompt-bound nodes, cross-set relations were not extracted."
    ]
    metadata = result.get("extraction_metadata")
    bound_metadata = prompt_bound_graph.get("extraction_metadata", {})
    if isinstance(metadata, dict) and isinstance(bound_metadata, Mapping):
        metadata["n_grounding_calls"] = int(metadata.get("n_grounding_calls", 0)) + int(
            bound_metadata.get("n_grounding_calls", 0)
        )
    shot_graph.validate_final_graph(result)
    return result


def render_grounding_artifacts(
    graph_path: Path,
    frame_dir: Path,
    output_dir: Path,
) -> Dict[str, Any]:
    """Write every grounded keyframe, a contact sheet, and an audit manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    contact_sheet = output_dir / "contact_sheet.png"
    try:
        n_frames, n_detections = episode_graphs.render_reference_sheet(
            graph_path,
            frame_dir,
            contact_sheet,
            annotated_dir=output_dir,
        )
    except (OSError, episode_graphs.RenderError) as exc:
        raise PromptUnboundError(
            f"Cannot render grounding results for {graph_path}: {exc}"
        ) from exc
    manifest = {
        "graph": str(graph_path.resolve()),
        "reference_frames": str(frame_dir.resolve()),
        "contact_sheet": str(contact_sheet.resolve()),
        "annotated_frames_dir": str(output_dir.resolve()),
        "reference_frame_count": n_frames,
        "grounding_detection_count": n_detections,
    }
    atomic_write_json(output_dir / "grounding_manifest.json", manifest)
    return manifest


def aggregate_token_usage(
    usages: Sequence[Optional[Mapping[str, Optional[int]]]],
) -> Dict[str, Optional[int]]:
    totals: Dict[str, Optional[int]] = {}
    for key in TOKEN_KEYS:
        values = [usage.get(key) if usage is not None else None for usage in usages]
        totals[key] = (
            sum(int(value) for value in values)
            if values and all(isinstance(value, int) and not isinstance(value, bool) for value in values)
            else None
        )
    return totals


def graph_token_usage(graph: Mapping[str, Any]) -> Optional[Dict[str, Optional[int]]]:
    return episode_graphs.graph_token_usage(graph)


def parse_shot_keys(value: Optional[str]) -> Optional[List[str]]:
    if value is None:
        return None
    keys = [part.strip() for part in value.split(",") if part.strip()]
    if not keys:
        raise PromptUnboundError("--shot-keys cannot be empty")
    return keys


def validate_thresholds(*values: Tuple[str, float]) -> None:
    for name, value in values:
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise PromptUnboundError(f"{name} must be in [0, 1]")


def build_prompt_unbound_codex_prompt(
    sample: shot_graph.VideoSample,
    prompt_entities: Sequence[Mapping[str, Any]],
    template_path: Path,
) -> str:
    if not template_path.is_file():
        raise PromptUnboundError(f"Prompt template is missing: {template_path}")
    mapping = "\n".join(
        f"- attached image {index + 1}: frame_id={frame_id}, "
        f"timestamp_sec={frame_id / sample.fps:.6f}"
        for index, frame_id in enumerate(sample.reference_frame_ids)
    )
    exclusions = []
    for entity in prompt_entities:
        grounding = entity.get("grounding", {})
        exclusions.append(
            {
                "name": entity.get("name"),
                "description": entity.get("description"),
                "entity_type": entity.get("entity_type"),
                "detector_status": grounding.get("status") if isinstance(grounding, Mapping) else None,
                "detected_boxes": grounding.get("boxes", []) if isinstance(grounding, Mapping) else [],
            }
        )
    return (
        template_path.read_text(encoding="utf-8").rstrip()
        + "\n\nShot metadata:\n"
        + f"- num_frames: {sample.num_frames}\n"
        + f"- fps: {sample.fps:.9g}\n"
        + f"- valid frame interval: [0, {sample.num_frames})\n\n"
        + "Attachment-to-frame mapping (chronological):\n"
        + mapping
        + "\n\nPrompt-bound exclusion registry and detector observations:\n"
        + json.dumps(exclusions, indent=2, ensure_ascii=False)
        + "\n"
    )


def run_codex_with_prompt(
    sample: shot_graph.VideoSample,
    prompt: str,
    *,
    codex_bin: str,
    model: Optional[str],
    timeout_sec: int,
    work_dir: Path,
    verbose: bool,
) -> shot_graph.CodexRunResult:
    """Reuse v1's locked Codex invocation while supplying the v2 prompt text."""
    original_builder = shot_graph.build_codex_prompt
    shot_graph.build_codex_prompt = lambda _sample: prompt
    try:
        return shot_graph.run_codex(
            sample,
            codex_bin=codex_bin,
            model=model,
            timeout_sec=timeout_sec,
            work_dir=work_dir,
            verbose=verbose,
        )
    finally:
        shot_graph.build_codex_prompt = original_builder


class RunRecorder:
    """Incrementally persist a readable log and machine-readable run manifest."""

    def __init__(self, run_dir: Path, pipeline: str, command: Sequence[str]) -> None:
        self.run_dir = run_dir.resolve()
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.log_path = self.run_dir / "run.log"
        self.manifest_path = self.run_dir / "run_manifest.json"
        self._log = self.log_path.open("x", encoding="utf-8", buffering=1)
        self.started = time.perf_counter()
        self.manifest: Dict[str, Any] = {
            "pipeline": pipeline,
            "status": "running",
            "start_utc": iso_utc(),
            "command": shlex.join(command),
            "stages": [],
            "shots": [],
        }
        self.write(f"pipeline: {pipeline}")
        self.write("status: running")
        self.write(f"start_utc: {self.manifest['start_utc']}")
        self.write(f"command: {self.manifest['command']}")
        self.flush_manifest()

    def write(self, line: str = "") -> None:
        self._log.write(line.rstrip("\n") + "\n")
        self._log.flush()

    def flush_manifest(self) -> None:
        atomic_write_json(self.manifest_path, self.manifest)

    def add_stage(self, name: str, seconds: float, **details: Any) -> None:
        record = {"name": name, "runtime_seconds": round(seconds, 6), **details}
        self.manifest["stages"].append(record)
        self.write(f"stage: {name}")
        self.write(f"runtime_seconds: {seconds:.6f}")
        self.flush_manifest()

    def add_shot(self, record: Mapping[str, Any]) -> None:
        self.manifest["shots"].append(dict(record))
        self.write(f"shot: {record.get('shot')}")
        self.write(f"shot_runtime_seconds: {float(record.get('runtime_seconds', 0.0)):.6f}")
        self.write(f"codex_token_usage: {json.dumps(record.get('codex_token_usage'))}")
        self.flush_manifest()

    def finish(
        self,
        status: str,
        *,
        token_usage: Optional[Mapping[str, Optional[int]]] = None,
        error: Optional[str] = None,
    ) -> None:
        self.manifest["status"] = status
        self.manifest["end_utc"] = iso_utc()
        self.manifest["total_runtime_seconds"] = round(time.perf_counter() - self.started, 6)
        self.manifest["total_codex_token_usage"] = dict(token_usage) if token_usage else None
        if error:
            self.manifest["error"] = error
        self.write(f"status: {status}")
        self.write(f"end_utc: {self.manifest['end_utc']}")
        self.write(f"total_runtime_seconds: {self.manifest['total_runtime_seconds']:.6f}")
        self.write(f"total_codex_token_usage: {json.dumps(self.manifest['total_codex_token_usage'])}")
        if error:
            self.write(f"error: {error}")
        self.flush_manifest()
        self._log.close()
