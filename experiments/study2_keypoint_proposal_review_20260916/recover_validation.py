"""Recover already-returned responses after local jsonschema import failure; no model calls."""
import sys,shutil,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));from run_review import *
owned_compute_job();out=HERE/'run01';records=[]
for stage in ['observe_shot1','observe_shot3']:
 d=out/stage;state=read(d/'status.json');assert state['status']=='failed' and state['error']=="ModuleNotFoundError: No module named 'jsonschema'"
 raw=read(d/'response.json');payload=read(d/'input.json');validate_single(raw,payload);usage=io.audit_events(d/'events.jsonl')
 shutil.copy2(d/'status.json',d/'status.transport_failure.json');record={'stage':stage,'error':state['error'],'response_sha256':sha(d/'response.json'),'validated_at':time.time(),'validation_python':sys.executable,'model_repeated':False};records.append(record)
 state.update(status='success',usage=usage,validation_recovery=record);state.pop('error');save(d/'status.json',state)
save(out/'validation_recovery.json',records);shutil.copy2(out/'run.json',out/'run.transport_failure.json');print('TWO EXISTING RESPONSES VALIDATED, NO NEW MODEL CALL',flush=True)
