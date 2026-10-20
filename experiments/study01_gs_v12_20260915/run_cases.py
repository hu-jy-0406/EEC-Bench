#!/usr/bin/env python3
"""Case adapter; all inference/fusion/scoring algorithms imported from frozen releases."""
import argparse, copy, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'EECBench'
OUT=Path(__file__).resolve().parent
SCORE=OUT/'runtime/EECBench'
GEO=BASE/'releases/static-geometry-20260914-v1/payload/EECBench'
PYTHON=Path('/vast/users/guangyi.chen/anaconda3/bin/python')
DETPY=BASE/'experiments/study_inconsistent_2/detector_upgrade_20260910/venv/bin/python'
PORT=ROOT/'to_human/eec-bench-repro-20260912'
sys.path[:0]=[str(SCORE/'scripts'),str(GEO/'scripts')]
import run_wedetect_shot_entities as io
from run_isolated_shot_static_3d import owned_compute_job

def read(p):return json.loads(Path(p).read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def log(*x):print(time.strftime('%H:%M:%S'),*x,flush=True)
def command(cmd,path):
    log('START',path.name)
    with path.open('w') as f:subprocess.run([str(x) for x in cmd],env=dict(os.environ,PATH='/vast/users/guangyi.chen/.local/bin:'+os.environ['PATH']),stdout=f,stderr=subprocess.STDOUT,check=True)
    log('DONE',path.name)
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def prepare(case):
    dest=OUT/case; dest.mkdir(exist_ok=True)
    er=dest/'entities'
    if (er/'run.json').exists() and read(er/'run.json')['status']=='success':return er
    er.mkdir(exist_ok=True)
    shots=[]
    if case=='study1':
        src=BASE/'experiments/study_inconsistent_2/wedetect_shot_entities_20260911/parallel_run01'
        assert read(src/'run.json')['status']=='success'
        origins=[s for s in read(src/'manifest.json')['shots'] if s['shot_id'].endswith(('shot1','shot3'))]
        for s in origins:
            sid='shot'+s['shot_id'][-1]; frames=[]
            for f in s['frames']:
                assert sha(f['path'])==f['sha256']
                target=dest/'inputs'/sid/Path(f['path']).name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f['path'],target)
                frames.append(dict(f,path=str(target)))
            shots.append(dict(shot_id=sid,frames=frames))
            source=src/'shots'/s['shot_id']/'entities.json';entities=read(source);entities['shot_id']=sid
            save(er/'shots'/sid/'entities.json',entities)
        save(er/'reuse.json',dict(source=str(src),source_manifest_sha256=sha(src/'manifest.json'),mapping={s['shot_id']:'shot'+s['shot_id'][-1] for s in origins},mode='frozen within-shot entities reused; shot IDs normalized; original boxes and entity IDs unchanged'))
        save(er/'manifest.json',dict(shots=shots));save(er/'run.json',dict(status='success',new_model_calls=0))
    else:
        for sid in ['shot1','shot3']:
            video=BASE/'experiments/study/shots'/('study_'+sid+'.mp4')
            import cv2
            cap=cv2.VideoCapture(str(video));fps=cap.get(cv2.CAP_PROP_FPS);cap.release()
            assert fps>0
            frames=[]
            for p in sorted((BASE/'experiments/study/reference_frames'/('study_'+sid)).glob('frame_*.jpg')):
                fid=int(p.stem.split('_')[-1]);target=dest/'inputs'/sid/p.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
                frames.append(dict(frame_id=fid,timestamp_sec=fid/fps,path=str(target),sha256=sha(target)))
            assert len(frames)==6
            shots.append(dict(shot_id=sid,frames=frames))
        save(er/'manifest.json',dict(shots=shots))
        # Reuse the validated portable CPU detector adapter and current frozen reviewer.
        portable=load_module('portable_adapter',PORT/'run_pipeline.py');portable.ensure_compute=owned_compute_job
        args=SimpleNamespace(detector_python=str(DETPY),weights=PORT/'weights/wedetect_base_uni.pth',seed=0,device='cpu',gpu=None,detector_timeout=7200,
            model='gpt-6-astra',reasoning='medium',codex_bin='/vast/users/guangyi.chen/.local/bin/codex',timeout=1800,shot_workers=2,prepare_only=False)
        if not (er/'detections/run.json').exists():
            log('DETECT',case);directory=portable.detect(shots,args,er)
        else:directory=er/'detections'
        detections=io.load_detections(directory,shots)
        state=dict(status='running',started=time.time());save(er/'run.json',state)
        log('CLUSTER',case)
        io.review_shots(shots,detections,args,er,state)
        state['status']='success';save(er/'run.json',state)
    log('ENTITIES',case,[(s['shot_id'],len(read(er/'shots'/s['shot_id']/'entities.json')['entities'])) for s in shots])
    return er

def read_json_command(cmd):return json.loads(subprocess.check_output(cmd,text=True))

def geometry(case,er):
    dest=OUT/case/'geometry';dest.mkdir(exist_ok=True)
    if (dest/'audit.json').exists() and read(dest/'audit.json')['status']=='pass':return dest
    g=load_module('run_geocalib_boxer',GEO/'scripts/run_geocalib_boxer.py');g.BASE=BASE
    def frozen():
        scenes={}
        for s in read(er/'manifest.json')['shots']:
            s=copy.deepcopy(s);s['entities']=read(er/'shots'/s['shot_id']/'entities.json')['entities']
            for f in s['frames']:assert sha(f['path'])==f['sha256']
            scenes[s['shot_id']]=s
        return scenes
    g.frozen=frozen
    (dest/'weights').mkdir(exist_ok=True)
    weight=dest/'weights/geocalib-pinhole.tar'
    if not weight.exists():weight.symlink_to(BASE/'experiments/study_inconsistent_3/geocalib_boxer_20260913/weights/geocalib-pinhole.tar')
    if not all((dest/'calibration'/f'{sid}.json').exists() for sid in ['shot1','shot3']):g.calibrate(dest,'cpu')
    g.run_boxer(dest,'cpu',['geocalib'],0)
    import numpy as np
    graphs=[];count=0
    for sid,s in frozen().items():
        states={e['entity_id']:[] for e in s['entities']};frames=[]
        for f in s['frames']:
            p=read(dest/'predictions/geocalib'/sid/f"frame_{f['frame_id']:06d}.json");K=np.array(p['K_original']);R=np.array(p['R_world_from_camera'])
            frames.append(dict(frame_id=f['frame_id'],image_sha256=f['sha256'],K=K.tolist(),R_world_from_camera=R.tolist(),translation_world_from_camera=[0,0,0]))
            lookup={e['entity_id']:e for e in p['entities']}
            assert set(lookup)=={e['entity_id'] for e in s['entities'] if next(o for o in e['observations'] if o['frame_id']==f['frame_id'])['visible']}
            for e in s['entities']:
                pred=lookup.get(e['entity_id']);states[e['entity_id']].append(dict(frame_id=f['frame_id'],geometry=pred,status='model_estimate' if pred else 'not_visible_geometry_unresolved'))
                if pred:
                    rot=np.array(pred['R_world_from_object']);size=np.array(pred['size_xyz']);world=np.array(pred['corners_world']);center=np.array(pred['center_world']);camera=world@R
                    assert np.all(size>0) and np.allclose(rot@rot.T,np.eye(3),atol=2e-5) and np.linalg.det(rot)>.999
                    assert np.allclose(camera,pred['corners_camera'],atol=1e-5)
                    assert np.allclose(np.ptp((world-center)@rot,axis=0),size,atol=1e-4)
                    uv=camera@K.T;uv=uv[:,:2]/uv[:,2:]
                    assert np.all(camera[:,2]>0) and np.allclose(uv,pred['projected_corners_xy'],atol=1e-5)
                    count+=1
        entities=[dict(entity_id=sid+'/'+e['entity_id'],local_id=e['entity_id'],name=e['name'],candidate_ids=e['candidate_ids'],observations=e['observations'],states=states[e['entity_id']]) for e in s['entities']]
        graphs.append(dict(shot_id=sid,world_frame_id=sid+'/geocalib_camera_origin_z_up',world_registration='shot_local_only',scale='monocular_model_metric_prior_not_measured',calibration=read(dest/'calibration'/f'{sid}.json'),frames=frames,entities=entities))
    save(dest/'boxer_scene_graph.json',dict(schema_version='boxer_sparse_scene_v0.1',shots=graphs,cross_shot_alignment=None))
    save(dest/'audit.json',dict(status='pass',predictions_replayed=count,source_script=str(GEO/'scripts/run_geocalib_boxer.py'),source_sha256=sha(GEO/'scripts/run_geocalib_boxer.py'),device='cpu',adapter='only frozen input provider and weights base path replaced; original geometry functions unchanged'))
    log('GEOMETRY',case,count)
    return dest

def evaluate(case,geo):
    dest=OUT/case;labels=dest/'static'
    for sid in ['shot1','shot3']:
        target=labels/sid
        if not (target/'run.json').exists():
            command([PYTHON,SCORE/'scripts/run_isolated_shot_static_3d.py','--source',geo/'boxer_scene_graph.json','--shot',sid,'--out',target],dest/(sid+'_static.log'))
        assert read(target/'run.json')['status']=='success'
    # Frozen builder's only overrides are input directories; evaluate main method only.
    fusion=load_module('case_fusion',GEO/'scripts/build_three_method_static_scenes.py');fusion.BOXER=geo;fusion.LABELS=labels
    for sid in ['shot1','shot3']:
        graph,frames=fusion.build('boxer_geocalib',sid);save(dest/'fusion'/sid/'Gs_global.json',graph);save(dest/'fusion'/sid/'Gs_frames.json',frames)
    score=dest/'gs_v11'
    if not (score/'run.json').exists():
        command([PYTHON,SCORE/'scripts/run_gs_consistency.py','--graph-a',dest/'fusion/shot1/Gs_global.json','--graph-b',dest/'fusion/shot3/Gs_global.json','--source-a',labels/'shot1/source_shot.json','--source-b',labels/'shot3/source_shot.json','--out',score],dest/'gs_v11.log')
    assert read(score/'run.json')['status']=='success'
    final=dest/'gs_v12'
    if not (final/'run.json').exists():command([PYTHON,SCORE/'scripts/run_gs_spatial_consistency.py','--source-run',score,'--out',final],dest/'gs_v12.log')
    assert read(final/'run.json')['status']=='success'
    for script,folder in [('audit_gs_consistency.py',score),('audit_gs_spatial_consistency.py',final),('render_gs_spatial_evidence.py',final),('replay_gs_spatial_consistency.py',final)]:
        command([PYTHON,SCORE/'scripts'/script,folder],dest/(script+'.log'))
    log('SCORED',case,read(final/'score.json')['score'])

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--case',choices=['study0','study1'],required=True);ap.add_argument('--stage',choices=['all','entities','geometry','score'],default='all');a=ap.parse_args()
    job=owned_compute_job();assert os.getloadavg()[0]<8
    state=dict(case=a.case,stage=a.stage,status='running',job=job,started=time.time());save(OUT/(a.case+'_driver.json'),state)
    try:
        er=prepare(a.case) if a.stage in ['all','entities'] else OUT/a.case/'entities'
        geo=geometry(a.case,er) if a.stage in ['all','geometry'] else OUT/a.case/'geometry'
        if a.stage in ['all','score']:evaluate(a.case,geo)
        state['status']='success'
    except BaseException as e:state.update(status='failed',error=repr(e));raise
    finally:state['ended']=time.time();save(OUT/(a.case+'_driver.json'),state)
