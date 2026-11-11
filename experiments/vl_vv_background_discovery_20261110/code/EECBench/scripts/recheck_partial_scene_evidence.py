#!/usr/bin/env python3
"""Recheck evidence under a versioned witness clarification; preserve original pilot."""
import argparse
import os
from pathlib import Path
import shutil
import time
import socket
import run_wedetect_shot_entities as io
import run_partial_scene_comparison as runner
from partial_scene_contract import CHECK_SCHEMA, validate_checks
from compare_partial_scenes import build_queries, compare, fuse


def run(args):
    job=io.safe_compute()
    if os.getloadavg()[0]>max(8,(os.cpu_count() or 1)*0.5):
        raise RuntimeError("Compute node busy")
    base=io.read(args.source_run/"run.json")
    if base["status"]!="success":
        raise ValueError("Require completed source pilot")
    args.out.mkdir(parents=True,exist_ok=False)
    shots=base["shots"]
    reused=["graph_"+s for s in shots]+["alignment"]
    for name in reused+["code_snapshot"]:
        shutil.copytree(args.source_run/name,args.out/name)
    for name in ("manifest.json","alignment.json","policy.json","source_run.snapshot.json"):
        shutil.copy2(args.source_run/name,args.out/name)
    hashes=io.read(args.source_run/"code_hashes.json")
    for p in (Path(__file__),runner.PROMPTS/args.prompt):
        shutil.copy2(p,args.out/"code_snapshot"/p.name);hashes[p.name]=io.sha(p)
    io.dump(args.out/"code_hashes.json",hashes)
    graphs=[io.read(args.out/("graph_"+s)/"graph.json") for s in shots]
    a,b=graphs;alignment=io.read(args.out/"alignment.json")
    policy=io.read(args.out/"policy.json")
    queries=build_queries(a,b,alignment);io.dump(args.out/"queries.json",queries)
    manifest=io.read(args.out/"manifest.json")
    images=manifest["images"]
    for f in images:
        if io.sha(f["path"])!=f["sha256"]:raise ValueError("Changed source image")
    # Source paths can reveal dataset construction labels; retain them on disk only.
    clean=lambda g:{k:v for k,v in g.items() if k!="source"}
    payload=dict(graph_a=clean(a),graph_b=clean(b),alignment=alignment,queries=queries,
        images=[dict(attachment_index=i+1,shot_id=f["shot_id"],frame_id=f["frame_id"]) for i,f in enumerate(images)])
    state=dict(status="running",started=time.time(),host=socket.gethostname(),allocation=job,shots=shots,
        source_run=str(args.source_run),evidence_protocol="diagnostic_witness_v0.2",
        reused_stages=reused,new_call_stages=["checks"],model=args.model,reasoning=args.reasoning)
    io.dump(args.out/"run.json",state)
    args.disabled_skills=io.disabled_skills_config()
    try:
        checks=runner.call("checks",args.prompt,payload,images,CHECK_SCHEMA,args)
        validate_checks(checks,queries,{g["shot_id"]:g for g in graphs})
        io.dump(args.out/"checks.json",checks)
        result=compare(a,b,alignment,checks,policy)
        io.dump(args.out/"comparison.json",result)
        io.dump(args.out/"scene_memory.json",fuse(graphs,result))
        runner.report(args.out,result,graphs,images)
        state.update(status="success",summary=result["summary"],coverage=result["coverage"])
    except BaseException as exc:
        state.update(status="failed",error=type(exc).__name__+": "+str(exc));raise
    finally:
        state.update(ended=time.time(),seconds=time.time()-state["started"])
        state["calls"]=[dict(stage=p.parent.name,reused=p.parent.name in reused,**io.read(p))
                        for p in sorted(args.out.glob("*/status.json"))]
        io.dump(args.out/"run.json",state)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source-run",required=True,type=Path);p.add_argument("--out",required=True,type=Path)
    p.add_argument("--prompt",default="partial_scene_checks_v0.2.txt")
    p.add_argument("--model",default="gpt-6-astra");p.add_argument("--reasoning",default="medium")
    p.add_argument("--codex-bin",default="codex");p.add_argument("--timeout",type=int,default=1800)
    args=p.parse_args();args.out=args.out.resolve();args.source_run=args.source_run.resolve();run(args)
