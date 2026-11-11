#!/usr/bin/env python3
"""Replay the Codex-only ensemble stage from a prior immutable input bundle.

This utility intentionally skips prompt-bound grounding and GroundingDINO.  It
copies the exact reference images and semantic prompt-bound registry recorded by
an earlier ensemble run into a new run, then executes entity discovery from
scratch.  It is useful for prompt, Skill, and orchestration ablations while
holding visual inputs fixed.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from ensemble_shot_entity_detection import run_ensemble_detection
from role_model_routing import resolve_model_routing
from prompt_unbound_common import shot_graph


def _shot_dirs(source_root: Path, requested: Sequence[str]) -> list[Path]:
    by_name = {
        path.name: path
        for path in source_root.iterdir()
        if path.is_dir() and (path / "input_bundle" / "shot_manifest.json").is_file()
    }
    if requested:
        missing = sorted(set(requested) - set(by_name))
        if missing:
            raise ValueError(f"Requested shots are absent from source run: {missing}")
        return [by_name[name] for name in requested]
    if not by_name:
        raise ValueError(f"No ensemble shot input bundles found under {source_root}")
    return [by_name[name] for name in sorted(by_name)]


def _load_replay_input(shot_dir: Path) -> tuple[shot_graph.VideoSample, list[Dict[str, Any]]]:
    input_dir = shot_dir / "input_bundle"
    manifest = json.loads((input_dir / "shot_manifest.json").read_text(encoding="utf-8"))
    frame_paths: Dict[int, Path] = {}
    for item in manifest["reference_frames"]:
        frame_id = int(item["frame_id"])
        path = Path(item["path"])
        if not path.is_file():
            fallback = input_dir / f"frame_{frame_id:06d}.jpg"
            if not fallback.is_file():
                raise FileNotFoundError(path)
            path = fallback
        frame_paths[frame_id] = path.resolve()
    sample = shot_graph.VideoSample(
        frames={frame_id: None for frame_id in frame_paths},
        frame_paths=frame_paths,
        num_frames=int(manifest["num_frames"]),
        fps=float(manifest["fps"]),
    )
    registry_path = Path(manifest["prompt_bound_registry_semantic"])
    if not registry_path.is_file():
        registry_path = input_dir / "prompt_bound_registry_semantic.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    prompt_entities = [
        {
            "id": entity["registry_id"],
            "name": entity["name"],
            "description": entity["description"],
            "entity_type": entity["entity_type"],
        }
        for entity in registry["entities"]
    ]
    return sample, prompt_entities


def _default_output_root(source_root: Path) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
    return source_root.parent / "entity_only_replay" / stamp


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_run", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--shots", nargs="*", default=[])
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--codex-model")
    parser.add_argument("--codex-review-model", help="Review roles only; omitted inherits --codex-model")
    parser.add_argument("--codex-timeout-sec", type=int, default=1800)
    parser.add_argument("--ensemble-max-workers", type=int, default=4)
    parser.add_argument("--ensemble-shuffle-seed", type=int, default=1729)
    parser.add_argument(
        "--ensemble-detector-closure-max-rounds", type=int, choices=range(5), default=3
    )
    parser.add_argument(
        "--ensemble-generic-identity-support-scope",
        choices=("nonmajority", "all_support"), default="all_support",
    )
    parser.add_argument(
        "--ensemble-identity-review-policy",
        choices=("legacy", "physical_v0.6"), default="legacy",
    )
    parser.add_argument(
        "--ensemble-revision-output-policy",
        choices=("canonical", "implicit_owner_wire_v0.1"), default="canonical",
    )
    parser.add_argument(
        "--ensemble-scope-retention-policy",
        choices=("disabled", "single_survivor_scope_retention_v0.1"), default="disabled",
    )
    parser.add_argument(
        "--ensemble-skill-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / ".agents"
        / "skills"
        / "ensemble-shot-entity-detection",
    )
    parser.add_argument("--parallel-shots", type=int, choices=(1, 2), default=1)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    model_routing = resolve_model_routing(args.codex_model, args.codex_review_model)
    if (args.ensemble_revision_output_policy != "canonical"
            and args.ensemble_identity_review_policy != "physical_v0.6"):
        parser.error("implicit_owner_wire_v0.1 requires physical_v0.6")
    if (args.ensemble_scope_retention_policy != "disabled"
            and args.ensemble_identity_review_policy != "physical_v0.6"):
        parser.error("scope retention requires physical_v0.6")

    source_root = args.source_run.resolve()
    shot_dirs = _shot_dirs(source_root, args.shots)
    output_root = (args.output_root or _default_output_root(source_root)).resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    _write_json(
        output_root / "replay_manifest.json",
        {
            "status": "running",
            "source_run": str(source_root),
            "shots": [path.name for path in shot_dirs],
            "parallel_shots": args.parallel_shots,
            "revision_output_policy": args.ensemble_revision_output_policy,
            **({"scope_retention_policy": args.ensemble_scope_retention_policy}
               if args.ensemble_scope_retention_policy != "disabled" else {}),
            **({"review_model": args.codex_review_model} if args.codex_review_model is not None else {}),
            **({"model_routing": model_routing} if model_routing is not None else {}),
            "grounding_executed": False,
            "cross_shot_model_input": False,
        },
    )

    def replay(shot_dir: Path):
        sample, prompt_entities = _load_replay_input(shot_dir)
        print(f"[replay] {shot_dir.name}: starting fixed-input ensemble", flush=True)
        result = run_ensemble_detection(
            sample=sample,
            shot_id=shot_dir.name,
            prompt_entities=prompt_entities,
            run_dir=output_root / shot_dir.name,
            codex_bin=args.codex_bin,
            model=args.codex_model,
            **({"review_model": args.codex_review_model} if args.codex_review_model is not None else {}),
            timeout_sec=args.codex_timeout_sec,
            max_workers=args.ensemble_max_workers,
            shuffle_seed=args.ensemble_shuffle_seed,
            skill_dir=args.ensemble_skill_dir,
            detector_closure_max_rounds=args.ensemble_detector_closure_max_rounds,
            generic_identity_support_scope=args.ensemble_generic_identity_support_scope,
            identity_review_policy=args.ensemble_identity_review_policy,
            revision_output_policy=args.ensemble_revision_output_policy,
            **({"scope_retention_policy": args.ensemble_scope_retention_policy}
               if args.ensemble_scope_retention_policy != "disabled" else {}),
            verbose=args.verbose,
        )
        print(
            f"[replay] {shot_dir.name}: done, "
            f"{len(result.semantics['entities'])} unbound entities",
            flush=True,
        )
        return result

    results = []
    failures = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(args.parallel_shots, len(shot_dirs))
    ) as executor:
        futures = {executor.submit(replay, path): path for path in shot_dirs}
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                shot_dir = futures[future]
                failures.append({
                    "shot_id": shot_dir.name, "error": str(exc),
                    "error_type": type(exc).__name__,
                    "run_manifest": str(output_root / shot_dir.name / "run_manifest.json"),
                })
                print(f"[replay] {shot_dir.name}: failed: {exc}", flush=True)

    summaries = []
    for result in sorted(results, key=lambda item: item.run_dir.name):
        summaries.append(
            {
                "shot_id": result.run_dir.name,
                "unbound_entity_count": len(result.semantics["entities"]),
                "entity_names": [item["name"] for item in result.semantics["entities"]],
                "runtime_seconds": result.runtime_seconds,
                "token_usage": result.token_usage,
                "run_manifest": str((result.run_dir / "run_manifest.json").resolve()),
            }
        )
    _write_json(
        output_root / "replay_manifest.json",
        {
            "status": "incomplete" if failures else "success",
            "end_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source_run": str(source_root),
            "shots": [path.name for path in shot_dirs],
            "parallel_shots": args.parallel_shots,
            "revision_output_policy": args.ensemble_revision_output_policy,
            **({"scope_retention_policy": args.ensemble_scope_retention_policy}
               if args.ensemble_scope_retention_policy != "disabled" else {}),
            **({"review_model": args.codex_review_model} if args.codex_review_model is not None else {}),
            **({"model_routing": model_routing} if model_routing is not None else {}),
            "grounding_executed": False,
            "cross_shot_model_input": False,
            "results": summaries,
            "failures": sorted(failures, key=lambda item: item["shot_id"]),
        },
    )
    print(f"[replay] {'incomplete' if failures else 'complete'}: {output_root}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
