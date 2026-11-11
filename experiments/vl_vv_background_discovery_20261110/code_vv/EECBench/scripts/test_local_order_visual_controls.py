#!/usr/bin/env python3
"""Controlled planar visual probes; ground truth is withheld from the VLM."""
import argparse
import json
import os
from pathlib import Path
import time
from PIL import Image, ImageDraw, ImageFont
import run_wedetect_shot_entities as io
import run_partial_scene_comparison as runner
from local_order_contract import EXTRACT_SCHEMA, validate_extraction, plan
from run_local_order_refinement import clean_graph, image_index


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    frames=[];images=[];entityrows={k:[] for k in ('x','y','surface')};arows={k:[] for k in ('u','v')};truth=[]
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',18)
    # Distinct screen projections; positions in common abstract planar coordinates.
    specs=[((85,65),(440,45),(-25,320),(.3,.35),(.7,.65),'clear'),
           ((550,80),(-445,45),(10,290),(.3,.35),(.7,.65),'reversed_image'),
           ((100,70),(430,70),(-35,270),(.3,.7),(.7,.3),'one_axis_swap'),
           ((525,70),(-420,65),(25,280),(.3,.7),(.7,.3),'partial'),
           ((100,65),(435,50),(-20,310),(.3,.35),(.7,.65),'hidden')]
    for fid,(origin,u,v,x,y,mode) in enumerate(specs):
        def point(p):return (round(origin[0]+u[0]*p[0]+v[0]*p[1]),round(origin[1]+u[1]*p[0]+v[1]*p[1]))
        im=Image.new('RGB',(660,470),'white');d=ImageDraw.Draw(im)
        corners=[point(p) for p in ((0,0),(1,0),(1,1),(0,1))]
        d.polygon(corners,fill='#ddd3b9',outline='black',width=3)
        for label,pt in zip(('P0','P1','P2','P3'),corners):d.text((pt[0]-8,pt[1]-24),label,font=font,fill='black')
        boxes={}
        for eid,position,color,label in [('x',x,'#db9022','A'),('y',y,'#3d72bb','B')]:
            cx,cy=point(position);box=[cx-32,cy-25,cx+32,cy+25];boxes[eid]=box
            d.ellipse(box,fill=color,outline='black',width=3);d.text((cx-7,cy-11),label,font=font,fill='black')
        if mode=='partial':
            # Occlude a portion of B's left outline while preserving a sufficient visible arc.
            cx,cy=point(y);d.rectangle([cx-40,cy-32,cx-12,cy+32],fill='#555555',outline='black',width=2)
        if mode=='hidden':
            cx,cy=point(y);d.rectangle([cx-42,cy-35,cx+42,cy+35],fill='#555555',outline='black',width=2)
        d.text((15,435),'Two flat tokens on one support; corner labels identify fixed physical ends.',fill='black',font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',13))
        dest=out/('frame_'+str(fid)+'.png');im.save(dest)
        frames.append(dict(frame_id=fid,image_size=[660,470]))
        images.append(dict(shot_id='controls',frame_id=fid,path=str(dest),sha256=io.sha(dest),role='original'))
        boxes['surface']=[min(p[0] for p in corners),min(p[1] for p in corners),max(p[0] for p in corners),max(p[1] for p in corners)]
        for eid in entityrows:
            visible=not(mode=='hidden' and eid=='y')
            entityrows[eid].append(dict(frame_id=fid,exist=True,visible=visible,box_xyxy=boxes[eid] if visible else None))
        for aid,end in [('u',(1,0)),('v',(0,1))]:
            arows[aid].append(dict(frame_id=fid,negative_endpoint_xy=list(point((0,0))),positive_endpoint_xy=list(point(end)),reason='physical labeled support corners'))
        truth.append(dict(frame_id=fid,condition=mode,u='unknown' if mode=='hidden' else ('less' if x[0]<y[0] else 'greater'),v='unknown' if mode=='hidden' else ('less' if x[1]<y[1] else 'greater')))
    entities=[dict(entity_id=e,name={'x':'Amber flat token A','y':'Blue flat token B','surface':'Planar support with labeled corners'}[e],observations=rows) for e,rows in entityrows.items()]
    graph=dict(shot_id='controls',frames=frames,entities=entities,entity_scopes=[dict(entity_id=e,scope='single') for e in entityrows],
        anchors=[dict(anchor_id=aid,entity_id='surface',part='support',axis_description='Physical P0 to '+('P1' if aid=='u' else 'P3'),resolvable=True,observations=arows[aid]) for aid in arows],
        relations=[dict(predicate='supported_by',subject_id=e,object_id='surface',observations=[dict(value='true')]) for e in ('x','y')])
    io.dump(out/'truth.json',truth);io.dump(out/'graph.json',graph);io.dump(out/'manifest.json',dict(images=images))
    return graph,images,truth


def run(args):
    io.safe_compute()
    if os.getloadavg()[0]>max(8,(os.cpu_count() or 1)*.5):raise RuntimeError('Compute node busy')
    graph,images,truth=prepare(args.out);planned=plan(graph);io.dump(args.out/'plan.json',planned)
    args.disabled_skills=io.disabled_skills_config()
    raw=runner.call('visual','local_order_evidence_v0.2.txt',dict(graph=clean_graph(graph),plan=planned,images=image_index(images)),images,EXTRACT_SCHEMA,args)
    validate_extraction(raw,planned,graph)
    scores=[]
    for q,r in zip(planned['queries'],raw['relations']):
        for expected,row in zip(truth,r['observations']):
            value=expected[q['anchor_id']];pred=row['values'];ok=pred==[value] if value!='unknown' else not pred
            scores.append(dict(frame_id=row['frame_id'],axis=q['anchor_id'],condition=expected['condition'],expected=value,predicted=pred,passed=ok,reason=row['reason']))
    io.dump(args.out/'evaluation.json',dict(passed=sum(s['passed'] for s in scores),total=len(scores),items=scores,
        limitation='Controlled planar-token visual probes; does not establish natural-image generalization. Truth withheld from model.'))
    print(json.dumps(scores,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--model',default='gpt-6-astra');p.add_argument('--reasoning',default='medium');p.add_argument('--codex-bin',default='codex');p.add_argument('--timeout',type=int,default=1800)
    a=p.parse_args();a.out=a.out.resolve();run(a)
