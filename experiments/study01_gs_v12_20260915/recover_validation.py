import sys,json,shutil,time
from pathlib import Path
from types import SimpleNamespace
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT/'runtime/EECBench/scripts'))
import run_wedetect_shot_entities as io
import run_isolated_shot_static_3d as static
static.owned_compute_job()
mode=sys.argv[1]
if mode=='static':
    directory=OUT/'study1/static/shot1';stage=directory/'review'
    for p in [stage/'status.json',directory/'run.json']:shutil.copy2(p,p.with_suffix('.failed.json'))
    raw=io.read(stage/'response.json');payload=io.read(stage/'input.json');static.validate_review(raw,payload)
    usage=io.audit_events(stage/'events.jsonl');status=io.read(stage/'status.json');status.update(status='success',usage=usage,recovery='Original response schema and events validated in base Python; no new inference',validated_at=time.time());io.dump(stage/'status.json',status)
    snapshot=io.read(directory/'source_shot.json');review=dict(reviewer='fresh isolated configured Codex CLI',scope='single shot only',shots=[raw]);io.dump(directory/'agent_review.json',review)
    graph=static.fusion.build(snapshot,review)
    paths=[directory/'source_shot.json',directory/'agent_review.json',Path(static.__file__),Path(static.fusion.__file__),static.transport.PROMPTS/static.PROMPT]+[Path(f['path']) for f in snapshot['shots'][0]['calibration']['images']]
    graph['provenance']=[dict(path=str(p.resolve()),sha256=io.sha(p)) for p in paths]
    io.dump(directory/'static_scene_graph.json',graph);(directory/'viewer.html').write_text(static.fusion.viewer(graph));io.dump(directory/'diagnostics.json',static.fusion.diagnostics(snapshot))
    state=io.read(directory/'run.json');state.update(status='success',counts={k:sum(e['status']==k for e in raw['entities']) for k in ('static','moving','unknown')},usage=usage,recovery='Post-call dependency repair; raw response unchanged');io.dump(directory/'run.json',state)
else:
    er=OUT/'study0/entities';manifest=io.read(er/'manifest.json');state=io.read(er/'run.json');shutil.copy2(er/'run.json',er/'run.failed.json');records=[]
    for shot in manifest['shots']:
        d=er/'shots'/shot['shot_id'];shutil.copy2(d/'status.json',d/'status.failed.json')
        payload=io.read(d/'input.json');io.validate_result(io.read(d/'response.json'),payload);io.audit_events(d/'events.jsonl')
        r=io.finish_review(shot,payload,d);r['recovery']='Original response validated in base Python; no new inference';io.dump(d/'status.json',r);records.append(r)
    state.update(status='success',shots=records,recovery='Schema dependency repaired post-call; all original responses unchanged');io.dump(er/'run.json',state)
print('RECOVERED',mode)
