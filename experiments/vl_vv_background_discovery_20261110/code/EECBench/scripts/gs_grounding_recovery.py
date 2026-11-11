#!/usr/bin/env python3
"""One fixed Grounding DINO sweep over frame gaps; no invented or repaired boxes."""
import argparse,os,time,sys
from pathlib import Path
import run_wedetect_shot_entities as io

def run(request,output,device='cpu',box_threshold=.30,text_threshold=.25):
    io.safe_compute()
    if device=='cpu' and (os.environ.get('ROCR_VISIBLE_DEVICES')!='-1' or os.environ.get('CUDA_VISIBLE_DEVICES')!=''):raise RuntimeError('CPU inference must hide GPUs')
    if device=='cuda' and not os.environ.get('ROCR_VISIBLE_DEVICES','').startswith('GPU-'):raise RuntimeError('GPU inference requires guarded UUID')
    output=Path(output);output.mkdir(parents=True,exist_ok=False);req=io.read(request);start=time.time()
    state=dict(status='running',device=device,started=start,frames=[],box_threshold=box_threshold,text_threshold=text_threshold,model='GroundingDINO_SwinT_OGC',request_sha256=io.sha(request));io.dump(output/'run.json',state)
    try:
        import torch
        torch.set_num_threads(4);sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from eval.evaluate_benchmark import get_grounding_dino
        from groundingdino.util.inference import load_image,predict
        model,_=get_grounding_dino(device=device,strict=True);state['model_load_seconds']=time.time()-start
        cache=Path.home()/'.cache/entitybench/groundingdino'
        state['model_sources']={str(p):io.sha(p) for p in [Path(os.environ.get('GDINO_CONFIG',cache/'GroundingDINO_SwinT_OGC.py')),Path(os.environ.get('GDINO_WEIGHTS',cache/'groundingdino_swint_ogc.pth'))]}
        for task in req['frames']:
            t=time.time();assert io.sha(task['path'])==task['sha256']
            image,tensor=load_image(task['path']);h,w=image.shape[:2]
            rows=[]; candidate_index=0
            # Run the fixed detector once for each requested instance phrase.
            # The target ID is therefore detector provenance, not a later VLM
            # assignment; a candidate cannot drift to another schedule entity.
            for target in task['targets']:
                query=target['query']
                boxes,scores,phrases=predict(model=model,image=tensor,caption=query,box_threshold=box_threshold,text_threshold=text_threshold,device=device)
                for box,score,label in zip(boxes.tolist(),scores.tolist(),phrases):
                    candidate_index+=1
                    cx,cy,bw,bh=box;raw=[(cx-bw/2)*w,(cy-bh/2)*h,(cx+bw/2)*w,(cy+bh/2)*h]
                    try:io.validate_box(raw,w,h);valid=True
                    except ValueError:valid=False
                    rows.append(dict(candidate_id=f"f{task['frame_id']}:gd{candidate_index}",name=label,box_xyxy=raw,score=score,valid_box=valid,normalized_cxcywh=box,detector='grounding_dino',query=query,prompt_entity_id=target['prompt_entity_id']))
            item=dict(**task,image_size=[w,h],detections=rows,seconds=time.time()-t);io.dump(output/task['shot_id']/f"frame_{task['frame_id']:06d}.json",item)
            state['frames'].append(dict(shot_id=task['shot_id'],frame_id=task['frame_id'],count=len(rows),seconds=item['seconds']));io.dump(output/'run.json',state);print(task['shot_id'],task['frame_id'],len(rows),flush=True)
        state['status']='success'
    except BaseException as e:state.update(status='failed',error=repr(e));raise
    finally:state.update(seconds=time.time()-start);io.dump(output/'run.json',state)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--request',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--device',choices=['cpu','cuda'],default='cpu');p.add_argument('--box-threshold',type=float,default=.30);p.add_argument('--text-threshold',type=float,default=.25);a=p.parse_args();run(a.request,a.output,a.device,a.box_threshold,a.text_threshold)
