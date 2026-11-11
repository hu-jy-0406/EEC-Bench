#!/usr/bin/env python3
"""Generic independent local-order refinement of a completed partial-scene run."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import socket
import time
import run_wedetect_shot_entities as io
import run_partial_scene_comparison as runner
from local_order_contract import (VERSION, EXTRACT_SCHEMA, VERIFY_SCHEMA, plan,
    validate_extraction, aligned_queries, validate_review, compare_local)


def clean_graph(g):
    # No prior relation values, source paths or cross-shot conclusions.
    return {k:g[k] for k in ("shot_id","entities","frames","anchors","entity_scopes")}


def detail_images(graph,planned,originals,out):
    """Deterministic native-pixel crop and 2x enlargement, preserving transforms."""
    from PIL import Image
    out.mkdir()
    nodes={e["entity_id"]:e for e in graph["entities"]}
    framefiles={f["frame_id"]:f for f in originals}
    pairs=sorted({(q["subject_id"],q["object_id"]) for q in planned["queries"]})
    crops=[]
    for x,y in pairs:
        rows=[]
        for a,b in zip(nodes[x]["observations"],nodes[y]["observations"]):
            if a["visible"] and b["visible"] and a["box_xyxy"] and b["box_xyxy"]:
                rows.append((a,b))
        # First/last visible frames inspect temporal ends without selecting by desired order.
        selected=[rows[0],rows[-1]] if len(rows)>1 else rows
        seen=set()
        for a,b in selected:
            fid=a["frame_id"]
            if fid in seen:continue
            seen.add(fid)
            f=framefiles[fid]
            with Image.open(f["path"]) as im:
                w,h=im.size;aa,bb=a["box_xyxy"],b["box_xyxy"]
                box=[max(0,int(min(aa[0],bb[0]))-24),max(0,int(min(aa[1],bb[1]))-24),
                     min(w,int(max(aa[2],bb[2]))+25),min(h,int(max(aa[3],bb[3]))+25)]
                crop=im.crop(box);crop=crop.resize((crop.width*2,crop.height*2),Image.Resampling.NEAREST)
                dest=out/(x+"_"+y+"_"+str(fid)+".png");crop.save(dest)
            crops.append(dict(shot_id=graph["shot_id"],frame_id=fid,path=str(dest),sha256=io.sha(dest),
                role="detail",entities=[x,y],original_sha256=f["sha256"],original_region_xyxy=box,scale=2))
    return crops


def image_index(images):
    return [dict(attachment_index=i+1,**{k:v for k,v in f.items() if k not in ("path","sha256","original_sha256","timestamp_sec")}) for i,f in enumerate(images)]


def write_report(out,graphs,result,manifest,base_result):
    names=[{e["entity_id"]:e["name"] for e in g["entities"]} for g in graphs]
    lines=["# 局部顺序提取与复核 v0.2", "", "原始图和历史完整足迹关系保留；本版显式判断承载面上的位置中心顺序。", "",
           "| 对象 | 固定参考轴 | Shot A 提取/复核 | Shot B 提取/复核（已归一） | 结果 |", "|---|---|---|---|---|"]
    anchors={a["anchor_id"]:a for a in graphs[0]["anchors"]}
    for r in result["items"]:
        q=r["query"];ev=r["evidence"]
        label=" / ".join(names[0][q["a"][k]] for k in ("subject_id","object_id"))
        vals=[str(ev[s]["extracted_values"])+" / "+str(ev[s]["reviewed_values"]) for s in ("a","b")]
        lines.append("| "+" | ".join([label,anchors[q["reference"]]["axis_description"],*vals,r["reason_code"]])+" |")
    lines += ["", "本次判断依赖视觉模型给出的局部定位与不确定性范围，不是人工准确率结论。",
        "compare_local 在两边逐帧证据中保留变化及提取/复核分歧；没有预置对象名或期望冲突标签。",
        "查看 comparison.json 的逐帧可见部位、位置范围、推断依据及符号归一。",
        "历史存在性检查未重跑，保存在 source_snapshot/comparison.json；combined_comparison.json 并列保存历史与新增语义。"]
    (out/"README.md").write_text("\n".join(lines)+"\n")
    io.dump(out/"combined_comparison.json",dict(protocol_version=VERSION,baseline=base_result,local_order=result))
    from render_local_order_evidence import render
    render(out)


def run(args):
    job=io.safe_compute()
    if os.getloadavg()[0]>max(8,(os.cpu_count() or 1)*0.5):raise RuntimeError("Compute node busy")
    base=io.read(args.source_run/"run.json")
    if base["status"]!="success":raise ValueError("Completed source run required")
    args.out.mkdir(parents=True,exist_ok=False)
    snapshot=args.out/"source_snapshot";snapshot.mkdir()
    graphs=[io.read(args.source_run/("graph_"+s)/"graph.json") for s in base["shots"]]
    for g in graphs:io.dump(snapshot/("graph_"+g["shot_id"]+".json"),g)
    for n in ("alignment.json","policy.json","comparison.json","manifest.json","run.json","scene_memory.json","scene_view.json"):
        shutil.copy2(args.source_run/n,snapshot/n)
    io.dump(args.out/"source_hashes.json",{p.name:io.sha(p) for p in snapshot.iterdir()})
    code=args.out/"code_snapshot";code.mkdir()
    paths=[Path(__file__),Path(__file__).with_name("local_order_contract.py"),Path(runner.__file__),
           Path(io.__file__),Path(__file__).with_name("render_local_order_evidence.py"),Path(__file__).with_name("compare_partial_scenes.py"),Path(__file__).with_name("partial_scene_contract.py"),
           runner.PROMPTS/"local_order_evidence_v0.2.txt",runner.PROMPTS/"local_order_verify_v0.2.txt"]
    for p in paths:shutil.copy2(p,code/p.name)
    io.dump(args.out/"code_hashes.json",{p.name:io.sha(p) for p in paths})
    io.dump(args.out/"extraction.schema.json",EXTRACT_SCHEMA);io.dump(args.out/"review.schema.json",VERIFY_SCHEMA)
    plans=[plan(g) for g in graphs]
    originals=io.read(snapshot/"manifest.json")["images"]
    for f in originals:
        if io.sha(f["path"])!=f["sha256"]:raise ValueError("Source image changed")
    shotimages=[]
    for g,p in zip(graphs,plans):
        imgs=[dict(f,role="original") for f in originals if f["shot_id"]==g["shot_id"]]
        details=detail_images(g,p,imgs,args.out/("details_"+g["shot_id"]))
        shotimages.append(imgs+details)
        io.dump(args.out/("plan_"+g["shot_id"]+".json"),p)
    manifest=dict(images=[f for rows in shotimages for f in rows],source_run=str(args.source_run))
    io.dump(args.out/"manifest.json",manifest)
    alignment=io.read(snapshot/"alignment.json");policy=io.read(snapshot/"policy.json")
    queries,unmapped=aligned_queries(plans,graphs,alignment)
    io.dump(args.out/"queries.json",dict(queries=queries,unmapped=unmapped))
    state=dict(status="running",protocol_version=VERSION,started=time.time(),host=socket.gethostname(),allocation=job,
        source_run=str(args.source_run),shots=base["shots"],model=args.model,reasoning=args.reasoning,
        candidate_counts=[len(p["queries"]) for p in plans],cross_queries=len(queries),automatic_name_independent_selection=True)
    io.dump(args.out/"run.json",state)
    args.disabled_skills=io.disabled_skills_config()
    try:
        def extract(g,p,images):
            raw=runner.call("local_"+g["shot_id"],"local_order_evidence_v0.2.txt",
                dict(graph=clean_graph(g),plan=p,images=image_index(images)),images,EXTRACT_SCHEMA,args)
            return validate_extraction(raw,p,g)
        with ThreadPoolExecutor(max_workers=2) as pool:
            fs=[pool.submit(extract,g,p,imgs) for g,p,imgs in zip(graphs,plans,shotimages)]
            extracts=[f.result() for f in fs]
        relevant=[set(q[s]["query_id"] for q in queries) for s in ("a","b")]
        proposals=[dict(shot_id=e["shot_id"],relations=[r for r in e["relations"] if r["query_id"] in ids]) for e,ids in zip(extracts,relevant)]
        pairs={g["shot_id"]:{frozenset((q[s]["subject_id"],q[s]["object_id"])) for q in queries} for s,g in zip(("a","b"),graphs)}
        reviewimages=[f for rows in shotimages for f in rows if f["role"]=="original" or frozenset(f["entities"]) in pairs[f["shot_id"]]]
        review=runner.call("review","local_order_verify_v0.2.txt",dict(graphs=[clean_graph(g) for g in graphs],
            queries=queries,proposals=proposals,images=image_index(reviewimages)),reviewimages,VERIFY_SCHEMA,args)
        validate_review(review,queries,graphs)
        result=compare_local(graphs,plans,extracts,alignment,review,policy)
        io.dump(args.out/"comparison.json",result)
        memory=io.read(snapshot/"scene_memory.json")
        io.dump(args.out/"scene_memory.json",dict(protocol_version=VERSION,baseline=memory,local_graphs=extracts,
            local_plans=plans,local_comparison=result,source_hashes=io.read(args.out/"source_hashes.json")))
        write_report(args.out,graphs,result,manifest,io.read(snapshot/"comparison.json"))
        state.update(status="success",summary=result["summary"])
    except BaseException as exc:
        state.update(status="failed",error=type(exc).__name__+": "+str(exc));raise
    finally:
        state.update(ended=time.time(),seconds=time.time()-state["started"])
        state["calls"]=[dict(stage=p.parent.name,**io.read(p)) for p in sorted(args.out.glob("*/status.json"))]
        io.dump(args.out/"run.json",state)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source-run",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    p.add_argument("--model",default="gpt-6-astra");p.add_argument("--reasoning",default="medium")
    p.add_argument("--codex-bin",default="codex");p.add_argument("--timeout",type=int,default=1800)
    args=p.parse_args();args.source_run=args.source_run.resolve();args.out=args.out.resolve();run(args)
