#!/usr/bin/env python3
"""Compare frozen 2D references with input-conditioned cuboid projections, not 3D GT."""
import base64,hashlib,json,math,statistics,sys
from pathlib import Path
import numpy as np
from run_geocalib_boxer import BASE,CASE,DEFAULT_OUT,frozen,load,save,unit
from sparse_scene_3d import camera_matrix,K

def box_metrics(a,b,W=852,H=480):
    a=np.asarray(a,float).copy();a[[0,2]]=np.clip(a[[0,2]],0,W);a[[1,3]]=np.clip(a[[1,3]],0,H)
    area=lambda r: max(0,float(r[2]-r[0]))*max(0,float(r[3]-r[1]))
    inter=area([max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3])]); union=area(a)+area(b)-inter
    return {'iou':inter/union if union else 0.,'coverage':inter/area(b),'area_ratio':area(a)/area(b),'center_error_px':float(np.linalg.norm((a[:2]+a[2:]-np.array(b[:2])-b[2:])/2))}
def stats(rows):
    if not rows:return {'n':0}
    return {'n':len(rows),'median_iou':statistics.median(r['iou'] for r in rows),'mean_iou':statistics.mean(r['iou'] for r in rows),'iou_ge_05':sum(r['iou']>=.5 for r in rows),'iou_ge_075':sum(r['iou']>=.75 for r in rows),'median_coverage':statistics.median(r['coverage'] for r in rows),'median_area_ratio':statistics.median(r['area_ratio'] for r in rows)}

def vertical_residual(K_,up,line):
    p,q=np.asarray(line,float);m=(p+q)/2;v=K_@up;d=v[:2]-m*v[2];e=q-p
    return math.degrees(math.acos(float(np.clip(abs(np.dot(unit(d),unit(e))),0,1))))

def review(out):
    # Root Codex visual review: approximate visible vertical edges, original pixels, frame0.
    # These are new sparse visual annotations, not human ground truth or fit targets.
    lines={'shot1':[[[398,2],[398,80]],[[497,2],[498,82]],[[532,2],[535,207]],[[61,2],[66,187]]],
           'shot3':[[[261,9],[260,89]],[[365,10],[365,90]],[[183,2],[189,220]],[[698,1],[691,239]]]}
    reviews=[]
    for sid in ['shot1','shot3']:
        c=load(out/'calibration'/f'{sid}.json');scene=load(CASE/'sparse_scene_3d_20260913/run01'/('scene_'+sid)/'scene.json')['proposal'];old=scene['cameras'][0];R,_=camera_matrix(old);old_up=R@np.array([0,0,1.]);new=c['fixed_camera_consensus'];new_up=np.array(new['physical_up_camera']);Kn=np.array(new['K'])
        record={'shot_id':sid,'reference_frame_id':0,'reviewed_vertical_lines_xy':lines[sid],'annotation_source':'Root Codex inspected original frame0; approximate sparse endpoints, not independent ground truth','new_focal_px':Kn[0,0],'old_focal_px':old['fx'],'gravity_angle_change_deg':math.degrees(math.acos(float(np.clip(np.dot(old_up,new_up),-1,1)))),'within_shot_max_up_deviation_deg':max(math.degrees(math.acos(float(np.clip(np.dot(unit(x['geocalib_gravity_raw']),new_up),-1,1)))) for x in c['records']),'vertical_line_angle_error_deg':{'geocalib':[vertical_residual(Kn,new_up,l) for l in lines[sid]],'codex_camera':[vertical_residual(K(old),old_up,l) for l in lines[sid]]},'action':'Retain unmodified GeoCalib parameters as experimental candidate; do not tune to object-box overlap.'}
        corners=scene['reference']['corners_by_frame'][0];points=[np.r_[corners[k]['xy'],1.] for k in ['xminus_yminus','xplus_yminus','xplus_yplus','xminus_yplus']];a,b,c0,d=points
        vx=np.cross(np.cross(a,b),np.cross(d,c0));vy=np.cross(np.cross(a,d),np.cross(b,c0));checks={}
        for label,Ki,up in [('geocalib',Kn,new_up),('codex_camera',K(old),old_up)]:
            dx=unit(np.linalg.solve(Ki,vx));dy=unit(np.linalg.solve(Ki,vy));normal=unit(np.cross(dx,dy));checks[label]={'table_axis_nonorthogonality_deg':abs(90-math.degrees(math.acos(float(np.clip(np.dot(dx,dy),-1,1))))),'table_normal_vs_up_deg':math.degrees(math.acos(float(np.clip(abs(np.dot(normal,up)),0,1))))}
        record['table_perspective_diagnostic']=checks;record['table_evidence_source']='Previously model-annotated table corners; not new independent GT. Small residual only tests internal consistency.';reviews.append(record)
    save(out/'geometry_review.json',reviews)

def evaluate(out):
    fs=frozen();data=[];images={};coverage=[];summary={};entities=[]
    for sid,s in fs.items():
        old=load(CASE/'sparse_scene_3d_20260913/run01'/('scene_'+sid)/'geometry_audit.json')
        original={(x['entity_id'],x['frame_id']):x for x in old['projected_boxes'] if x['camera_variant']=='raw'}
        for variant in ['geocalib','codex_camera']:
            variant_rows=[]
            for f in s['frames']:
                path=out/'predictions'/variant/sid/f"frame_{f['frame_id']:06d}.json"
                if not path.exists():raise ValueError('Incomplete predictions: '+str(path))
                d=load(path);expected=[e['entity_id'] for e in s['entities'] if next(o for o in e['observations'] if o['frame_id']==f['frame_id'])['visible']]
                ids=[e['entity_id'] for e in d['entities']]
                if ids!=expected:raise ValueError('Dropped or reordered entity')
                imagekey=sid+'/'+str(f['frame_id'])
                if imagekey not in images:images[imagekey]='data:image/jpeg;base64,'+base64.b64encode(Path(f['path']).read_bytes()).decode()
                for e in d['entities']:
                    if not np.isfinite(e['corners_camera']).all():raise ValueError('Nonfinite prediction')
                    raw=original[(e['entity_id'],f['frame_id'])]
                    if raw['visible_detection_box']!=e['grounding_box_xyxy']:raise ValueError('Grounding changed')
                    # Count invalid/behind-camera boxes as IoU=0, never silently drop failures.
                    met=box_metrics(e['projected_envelope_xyxy'],e['grounding_box_xyxy']) if e['all_corners_in_front'] else {'iou':0.,'coverage':0.,'area_ratio':None,'center_error_px':None}
                    row={'shot_id':sid,'frame_id':f['frame_id'],'entity_id':e['entity_id'],'name':e['name'],'variant':variant,'metrics':met,'baseline_metrics':box_metrics(raw['projected_envelope'],raw['visible_detection_box']),'reference':e['grounding_box_xyxy'],'projected':e['projected_envelope_xyxy'],'corners':e['projected_corners_xy'],'baseline_projected':raw['projected_envelope'],'valid':e['all_corners_in_front']};data.append(row);variant_rows.append(row)
            if not all(x['valid'] for x in variant_rows):raise ValueError('Behind-camera outputs require explicit aggregate handling')
            summary[sid+'/'+variant]={'new':stats([x['metrics'] for x in variant_rows]),'baseline_same_rows':stats([x['baseline_metrics'] for x in variant_rows]),'invalid_boxes':sum(not x['valid'] for x in variant_rows)}
            for e in s['entities']:
                rows=[x for x in variant_rows if x['entity_id']==e['entity_id']]
                entities.append({'shot_id':sid,'variant':variant,'entity_id':e['entity_id'],'name':e['name'],'new':stats([x['metrics'] for x in rows]),'baseline':stats([x['baseline_metrics'] for x in rows])})
            coverage.append({'shot_id':sid,'variant':variant,'entity_count':len(s['entities']),'predicted_entity_count':len(set(x['entity_id'] for x in variant_rows)),'visible_entity_frames':len(variant_rows)})
    save(out/'comparison.json',{'summary':summary,'coverage':coverage,'per_entity':entities,'items':data,'limitations':['2D grounding boxes are INPUT prompts to Boxer, so overlap is input-conditioned consistency, not independent accuracy.','No depth input; monocular metric scale is a model prior, not ground truth.','Images are nearly fixed-view; repeated frames are not independent trials.','No cross-shot world registration or anomaly adjudication performed.']})
    html='''<!doctype html><meta charset="utf-8"><title>GeoCalib + Boxer 对照</title><style>body{font-family:system-ui;margin:24px;max-width:1500px}select{margin:8px;padding:8px}svg{width:100%;background:#eee}.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}#detail{white-space:pre-wrap}</style><h1>GeoCalib + Boxer：原图重投影对照</h1><p>绿色：冻结 grounding 框；橙色：原 Codex OBB 投影；紫色：Boxer OBB 投影。二维框是 Boxer 的输入，IoU 是输入条件下的投影拟合，不是独立三维准确率。</p><select id="shot"><option>shot1</option><option>shot3</option></select><select id="frame"></select><select id="entity"></select><select id="variant"><option value="geocalib">GeoCalib + Boxer</option><option value="codex_camera">原 Codex 相机 + Boxer</option></select><div class="cols"><div><h3>原 Codex 三维框投影</h3><svg id="old" viewBox="0 0 852 480"></svg></div><div><h3>Boxer 三维框投影</h3><svg id="new" viewBox="0 0 852 480"></svg></div></div><p id="detail"></p><script>const DATA=__DATA__, IMAGES=__IMAGES__;const $=id=>document.getElementById(id);for(const f of [0,24,48,72,96,120])$('frame').add(new Option(f,f));function rect(b,c){return `<rect x="${b[0]}" y="${b[1]}" width="${b[2]-b[0]}" height="${b[3]-b[1]}" fill="none" stroke="${c}" stroke-width="2"/>`;}function refresh(){const rows=DATA.filter(x=>x.shot_id==$('shot').value&&x.frame_id==+$('frame').value&&x.variant==$('variant').value);const prev=$('entity').value;$('entity').innerHTML='';for(const r of rows)$('entity').add(new Option(r.entity_id+' '+r.name,r.entity_id));if(rows.some(r=>r.entity_id==prev))$('entity').value=prev;draw();}function draw(){const r=DATA.find(x=>x.shot_id==$('shot').value&&x.frame_id==+$('frame').value&&x.variant==$('variant').value&&x.entity_id==$('entity').value);if(!r)return;const bg=`<image href="${IMAGES[r.shot_id+'/'+r.frame_id]}" width="852" height="480"/>`; $('old').innerHTML=bg+rect(r.baseline_projected,'#ff8800')+rect(r.reference,'#00ef70');const edges=[[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];const wire=edges.map(([a,b])=>`<line x1="${r.corners[a][0]}" y1="${r.corners[a][1]}" x2="${r.corners[b][0]}" y2="${r.corners[b][1]}" stroke="#d700ff" stroke-width="1.5"/>`).join('');$('new').innerHTML=bg+wire+rect(r.projected,'#d700ff')+rect(r.reference,'#00ef70');$('detail').textContent=`${r.name}\n原 Codex IoU=${r.baseline_metrics.iou.toFixed(3)}；Boxer IoU=${r.metrics.iou.toFixed(3)}\nBoxer 投影面积/grounding 面积=${r.metrics.area_ratio.toFixed(2)}；覆盖率=${r.metrics.coverage.toFixed(3)}`;}for(const id of ['shot','frame','variant'])$(id).onchange=refresh;$('entity').onchange=draw;refresh();</script>'''
    (out/'projection_viewer.html').write_text(html.replace('__DATA__',json.dumps(data,ensure_ascii=False)).replace('__IMAGES__',json.dumps(images)))
    print(json.dumps(summary,indent=2))
if __name__=='__main__':
    out=Path(sys.argv[1]) if len(sys.argv)>1 else DEFAULT_OUT
    review(out);evaluate(out)
