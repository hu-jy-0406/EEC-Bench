#!/usr/bin/env python3
"""Frozen entity graphs -> independent extraction -> visual evidence -> deterministic comparison."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
import time

import run_wedetect_shot_entities as io
import run_shot_spatial_relations as prior
from partial_scene_contract import (VERSION, GRAPH_SCHEMA, ALIGNMENT_SCHEMA, CHECK_SCHEMA,
    POLICY_SCHEMA, schema_validate, validate_graph, validate_alignment, validate_checks)
from compare_partial_scenes import build_queries, compare, fuse

ROOT = io.ROOT
PROMPTS = ROOT / "EECBench/prompts"
CODE = Path(__file__).resolve().parent


def call(stage, prompt_name, payload, images, schema, args):
    directory = args.out / stage
    directory.mkdir(parents=True, exist_ok=False)
    prompt = (PROMPTS / prompt_name).read_text() + "\nINPUT_JSON:\n" + json.dumps(payload, ensure_ascii=False)
    (directory / "prompt.txt").write_text(prompt)
    io.dump(directory / "input.json", payload)
    io.dump(directory / "output.schema.json", schema)
    start = time.time()
    state = dict(status="running", started=start, model=args.model, reasoning=args.reasoning)
    io.dump(directory / "status.json", state)
    try:
        with tempfile.TemporaryDirectory(prefix="eec-partial-scene-") as tmp:
            work = Path(tmp)
            command = [args.codex_bin, "--ask-for-approval", "never", "exec",
                "--ignore-user-config", "-c", args.disabled_skills, "--ephemeral",
                "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never", "--json",
                "--model", args.model, "-c", 'model_reasoning_effort="' + args.reasoning + '"',
                "-c", "project_doc_max_bytes=0", "-c", 'web_search="disabled"',
                "--output-schema", str(directory / "output.schema.json"),
                "--output-last-message", str(directory / "response.json"), "--cd", str(work)]
            for feature in ("shell_tool", "unified_exec", "view_image", "apps", "plugins", "hooks",
                    "multi_agent", "memories", "skill_search", "browser_use", "computer_use",
                    "code_mode", "code_mode_only", "workspace_dependencies"):
                command += ["--disable", feature]
            for i, frame in enumerate(images, 1):
                image = work / ("image_" + str(i) + Path(frame["path"]).suffix)
                shutil.copy2(frame["path"], image)
                if io.sha(image) != frame["sha256"]:
                    raise ValueError("Image changed before request")
                command += ["--image", str(image)]
            command.append("-")
            io.dump(directory / "request.json", dict(command=command, prompt_sha256=io.sha(directory / "prompt.txt"),
                schema_sha256=io.sha(directory / "output.schema.json"),
                images=[dict(shot_id=f["shot_id"], frame_id=f["frame_id"], sha256=f["sha256"]) for f in images]))
            io.run_process(command, prompt, work, directory / "events.jsonl", directory / "stderr.log", args.timeout)
        usage = io.audit_events(directory / "events.jsonl")
        result = io.read(directory / "response.json")
        schema_validate(result, schema)
        state.update(status="success", usage=usage)
        return result
    except BaseException as exc:
        usage = []
        event_file = directory / "events.jsonl"
        if event_file.exists():
            for line in event_file.read_text().splitlines():
                try:
                    e = json.loads(line)
                    if e.get("usage"):
                        usage.append(e["usage"])
                except ValueError:
                    pass
        state.update(status="failed", error=type(exc).__name__ + ": " + str(exc), known_usage=usage)
        raise
    finally:
        state.update(ended=time.time(), seconds=time.time() - start)
        io.dump(directory / "status.json", state)


def graph_input(item):
    shot, frozen, payload, source = item
    payload = dict(payload)
    pairs = sorted(payload["pair_candidates"] + payload["unobservable_pairs"], key=lambda p: p["pair_id"])
    payload["pairs"] = pairs
    del payload["pair_candidates"], payload["unobservable_pairs"]
    return payload


def all_images(items):
    return [dict(f, shot_id=item[0]["shot_id"]) for item in items for f in item[0]["frames"]]


def report(out, result, graphs, images):
    counts = result["summary"]
    lines = ["# 局部场景图自动比较首轮结果", "", "本次为真实模型取证与确定性比较试运行，不是人工准确率评测。", "",
        "## 分类数量", "", "| 类别 | 项数 |", "|---|---|"]
    for k, n in sorted(counts.items()):
        lines.append("| " + k + " | " + str(n) + " |")
    nodes = {(g["shot_id"], e["entity_id"]): e["name"] for g in graphs for e in g["entities"]}
    groups = {g["group_id"]: g for g in result["inventory_diff"]}
    sa, sb = result["source_shots"]
    def label(gid):
        g = groups[gid]
        return " / ".join(nodes[(sid, eid)] for side, sid in (("a", sa), ("b", sb)) for eid in g[side + "_ids"])
    lines += ["", "## 逐项结果", "", "| 项目 | 对象 | 结果 | 原因 |", "|---|---|---|---|"]
    for i in result["items"]:
        names = "; ".join(label(g) for g in i["group_ids"])
        lines.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in
            (i["item_id"], names, i["assessment"], i["reason_code"])) + " |")
    lines += ["", "原始 graph、alignment、checks、queries、comparison 和 scene_memory JSON 均保留。", "",
        "conflict 是在已保存连续性规则下、视觉证据通过门控的结论；unknown 不计为确认一致。",
        "关系逐项台账包含未对齐端点/锚点；可见性缺失仅为指定占位反证，不是整个房间物理不存在。"]
    (out / "README.md").write_text("\n".join(lines) + "\n")
    from materialize_partial_scene import project
    from render_partial_scene_comparison import render
    io.dump(out / "scene_view.json", project(graphs, io.read(out / "alignment.json"), result))
    render(out)


def run(args):
    job = io.safe_compute()
    if os.getloadavg()[0] > max(8, (os.cpu_count() or 1) * 0.5):
        raise RuntimeError("Compute node is too busy for additional work")
    items = prior.load_inputs(args.source)
    index = {i[0]["shot_id"]: i for i in items}
    chosen = [index[args.shot_a], index[args.shot_b]]
    if args.shot_a == args.shot_b:
        raise ValueError("Choose two different shots")
    policy = io.read(args.policy)
    schema_validate(policy, POLICY_SCHEMA)
    args.out.mkdir(parents=True, exist_ok=False)
    snapshot = args.out / "code_snapshot"
    snapshot.mkdir()
    paths = [CODE / name for name in ("partial_scene_contract.py", "compare_partial_scenes.py",
            "run_partial_scene_comparison.py", "run_shot_spatial_relations.py", "run_wedetect_shot_entities.py",
            "materialize_partial_scene.py", "render_partial_scene_comparison.py", "export_partial_scene_schemas.py")]
    paths += list(PROMPTS.glob("partial_scene_*v0.1.txt"))
    selected_prompt = PROMPTS / args.checks_prompt
    if selected_prompt not in paths:
        paths.append(selected_prompt)
    for p in paths:
        shutil.copy2(p, snapshot / p.name)
    io.dump(args.out / "code_hashes.json", {p.name: io.sha(p) for p in paths})
    io.dump(args.out / "policy.json", policy)
    io.dump(args.out / "source_run.snapshot.json", io.read(args.source / "run.json"))
    images = all_images(chosen)
    io.dump(args.out / "manifest.json", dict(images=images, sources=[i[3] for i in chosen]))
    state = dict(status="running", protocol_version=VERSION, started=time.time(), host=socket.gethostname(),
                 allocation=job, source_run=str(args.source), shots=[args.shot_a, args.shot_b], model=args.model,
                 reasoning=args.reasoning, checks_prompt=args.checks_prompt, no_ground_truth_labels_in_prompts=True)
    io.dump(args.out / "run.json", state)
    args.disabled_skills = io.disabled_skills_config()
    try:
        def extract(item):
            payload = graph_input(item)
            sid = item[0]["shot_id"]
            raw = call("graph_" + sid, "partial_scene_graph_v0.1.txt", payload, all_images([item]), GRAPH_SCHEMA, args)
            final = validate_graph(raw, payload)
            final["source"] = item[3]
            io.dump(args.out / ("graph_" + sid) / "graph.json", final)
            return final
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(extract, i) for i in chosen]
            graphs = [f.result() for f in futures]
        a, b = graphs
        image_index = [dict(attachment_index=i+1, shot_id=f["shot_id"], frame_id=f["frame_id"]) for i,f in enumerate(images)]
        clean = lambda graph: {k: v for k, v in graph.items() if k != "source"}
        alignment_payload = dict(graph_a=clean(a), graph_b=clean(b), images=image_index)
        alignment = call("alignment", "partial_scene_alignment_v0.1.txt", alignment_payload, images, ALIGNMENT_SCHEMA, args)
        validate_alignment(alignment, a, b)
        io.dump(args.out / "alignment.json", alignment)
        queries = build_queries(a, b, alignment)
        io.dump(args.out / "queries.json", queries)
        checks = call("checks", args.checks_prompt,
            dict(**alignment_payload, alignment=alignment, queries=queries), images, CHECK_SCHEMA, args)
        validate_checks(checks, queries, {g["shot_id"]: g for g in graphs})
        io.dump(args.out / "checks.json", checks)
        result = compare(a, b, alignment, checks, policy)
        io.dump(args.out / "comparison.json", result)
        io.dump(args.out / "scene_memory.json", fuse(graphs, result))
        report(args.out, result, graphs, images)
        state.update(status="success", summary=result["summary"], coverage=result["coverage"])
    except BaseException as exc:
        state.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
        raise
    finally:
        state.update(ended=time.time(), seconds=time.time() - state["started"])
        records = []
        for p in sorted(args.out.glob("*/status.json")):
            records.append(dict(stage=p.parent.name, **io.read(p)))
        state["calls"] = records
        io.dump(args.out / "run.json", state)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--policy", type=Path, required=True)
    p.add_argument("--shot-a", default="shot1")
    p.add_argument("--shot-b", default="shot3")
    p.add_argument("--model", default="gpt-6-astra")
    p.add_argument("--reasoning", default="medium")
    p.add_argument("--codex-bin", default="codex")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--checks-prompt", default="partial_scene_checks_v0.2.txt")
    args = p.parse_args()
    args.source, args.out, args.policy = args.source.resolve(), args.out.resolve(), args.policy.resolve()
    run(args)


if __name__ == "__main__":
    main()
