#!/usr/bin/env python3
"""Read-only reconstruction/provenance audit for a completed comparison run."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "scripts"))
import run_wedetect_shot_entities as io
from partial_scene_contract import GRAPH_SCHEMA, validate_graph
from compare_partial_scenes import compare, fuse

def audit(root):
    state=io.read(root/"run.json")
    assert state["status"]=="success",state
    manifest=io.read(root/"manifest.json")
    for f in manifest["images"]:
        assert io.sha(f["path"])==f["sha256"]
    for src in manifest["sources"]:
        assert io.sha(src["entity_file"])==src["entity_sha256"]
    code=io.read(root/"code_hashes.json")
    for name,sha in code.items():
        assert io.sha(root/"code_snapshot"/name)==sha
    for path in root.glob("graph_*/graph.json"):
        g=io.read(path)
        raw=io.read(path.parent/"response.json")
        payload=io.read(path.parent/"input.json")
        regenerated=validate_graph(raw,payload)
        regenerated["source"]=g["source"]
        assert regenerated==g
        assert payload["shot_id"]==g["shot_id"]
    s1,s3=state["shots"]
    a,b=[io.read(root/("graph_"+s)/"graph.json") for s in (s1,s3)]
    args=[a,b,io.read(root/"alignment.json"),io.read(root/"checks.json"),io.read(root/"policy.json")]
    result=compare(*args)
    assert result==io.read(root/"comparison.json")
    mem=fuse([a,b],result)
    assert mem==io.read(root/"scene_memory.json")==fuse([b,a,a],result)
    threads=[];usage=[];new_usage=[];stages=[]
    reused=set(state.get('reused_stages',[]))
    for directory in sorted(p for p in root.iterdir() if (p/"request.json").is_file()):
        req=io.read(directory/"request.json")
        assert io.sha(directory/"prompt.txt")==req["prompt_sha256"]
        assert io.sha(directory/"output.schema.json")==req["schema_sha256"]
        stage=io.read(directory/"status.json")
        assert stage["status"]=="success"
        stage_usage=io.audit_events(directory/"events.jsonl")
        usage+=stage_usage
        if directory.name not in reused:
            new_usage+=stage_usage
        else:
            original=Path(state["source_run"])/directory.name
            assert io.sha(directory/"response.json")==io.sha(original/"response.json")
            assert io.sha(directory/"events.jsonl")==io.sha(original/"events.jsonl")
        events=[json.loads(l) for l in (directory/"events.jsonl").read_text().splitlines() if l]
        tid=[e["thread_id"] for e in events if e["type"]=="thread.started"]
        assert len(tid)==1
        threads+=tid
        stages.append(dict(stage=directory.name,reused=directory.name in reused,seconds=stage["seconds"],thread_id=tid[0],
                           image_count=len(req["images"]),response_sha256=io.sha(directory/"response.json")))
        if directory.name.startswith("graph_"):
            assert {f["shot_id"] for f in req["images"]}=={directory.name[6:]}
    assert len(threads)==len(set(threads))==4
    totals={k:sum((u or {}).get(k,0) for u in usage) for k in ("input_tokens","output_tokens","cached_input_tokens")}
    totals["total_tokens"]=totals["input_tokens"]+totals["output_tokens"]
    incremental={k:sum((u or {}).get(k,0) for u in new_usage) for k in ("input_tokens","output_tokens","cached_input_tokens")}
    incremental["total_tokens"]=incremental["input_tokens"]+incremental["output_tokens"]
    schema_root=Path(__file__).resolve().parents[1]/"schemas"
    import jsonschema
    for filename,schema_name in (("comparison.json","comparison"),("scene_memory.json","memory"),
                                ("graph_"+s1+"/graph.json","graph"),("graph_"+s3+"/graph.json","graph")):
        jsonschema.validate(io.read(root/filename),io.read(schema_root/("partial_scene_"+schema_name+".v0.1.schema.json")))
    data=dict(status="pass",incremental_usage=incremental,new_model_calls=len(stages)-len(reused),checks=["source hashes","snapshot hashes","raw graph reconstruction",
        "single-shot isolation","unique tool-free calls","comparison replay","fusion replay/idempotence/order",
        "complete semantic validators"],stages=stages,usage=totals,coverage=result["coverage"],
        summary=result["summary"],limitations="No human GT accuracy or calibrated geometry validation.")
    io.dump(root/"audit.json",data)
    print(json.dumps(data,ensure_ascii=False,indent=2))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);audit(p.parse_args().run.resolve())
