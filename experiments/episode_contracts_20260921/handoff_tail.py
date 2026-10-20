"""Adopt the one isolated final request while releasing the drained coordinator."""
import json,os,signal,time
from pathlib import Path
import run

def proc(pid):
    try:
        fields=Path(f'/proc/{pid}/stat').read_text().split()
        return dict(state=fields[2],ticks=fields[21])
    except FileNotFoundError:return None

def main():
    run.io.safe_compute();run.DISABLED=run.io.disabled_skills_config()
    assert run.read(run.HERE/'handoff_preflight.json')['status']=='pass'
    prior=run.read(run.HERE/'scaling.json')['drain_processes'][0];parent=prior['pid']
    state=proc(parent)
    if not state or state['state']=='Z':print('Old coordinator already terminal; no handoff needed');return
    assert state['ticks']==prior['start_ticks']
    eid='u_4L7Dx1rIg_s00001_n6_clean_v2';folder=run.HERE/'episodes'/eid
    running=[p for p in (folder/'calls').glob('*/status.json') if run.read(p)['status']=='running']
    assert len(running)==1
    status_path=running[0];call=status_path.parent;status=run.read(status_path)
    children=set()
    for p in Path(f'/proc/{parent}/task').glob('*/children'):children.update(map(int,p.read_text().split()))
    assert len(children)==1,children
    child=children.pop();child_state=proc(child)
    assert str(call/'response.json') in Path(f'/proc/{child}/cmdline').read_text()
    assert os.getpgid(child)==child
    handoff=dict(episode_id=eid,parent=parent,parent_start_ticks=prior['start_ticks'],child=child,child_start_ticks=child_state['ticks'],call=str(call),started=time.time(),status='adopting',original_deadline=status['started']+1200)
    run.dump(run.HERE/'handoff.json',handoff)
    run.dump(call/'status_before_handoff.json',status)
    assert proc(parent)['ticks']==prior['start_ticks']
    os.kill(parent,signal.SIGTERM)  # Only Python coordinator; isolated API process survives.
    print(json.dumps(dict(event='tail_request_adopted',episode_id=eid,child=child)),flush=True)
    timed_out=False
    while True:
        state=proc(child)
        if not state or state['ticks']!=child_state['ticks'] or state['state']=='Z':break
        if time.time()>=handoff['original_deadline']:
            timed_out=True;os.killpg(child,signal.SIGTERM)
            deadline=time.time()+10
            while proc(child) and proc(child)['state']!='Z' and time.time()<deadline:time.sleep(.2)
            state=proc(child)
            if state and state['ticks']==child_state['ticks'] and state['state']!='Z':os.killpg(child,signal.SIGKILL)
            break
        time.sleep(1)
    try:
        if timed_out:raise TimeoutError('Original 1200-second request timeout reached after handoff')
        assert (call/'response.json').exists()
        status.update(status='success',usage=run.io.audit_events(call/'events.jsonl'))
    except Exception as ex:
        status.update(status='failed',error=str(ex))
        try:status['known_usage']=run.io.audit_events(call/'events.jsonl')
        except Exception:status['usage_unavailable']=True
    status.update(seconds=time.time()-status['started'],end_observed_by_handoff=True)
    run.dump(status_path,status)
    handoff.update(status='request_terminal',request_status=status['status']);run.dump(run.HERE/'handoff.json',handoff)
    job=next(j for j in run.read(run.HERE/'manifest.json')['jobs'] if j['episode_id']==eid)
    result=run.process(job)
    handoff.update(status='complete' if result['status']=='success' else 'failed',result=result,completed=time.time());run.dump(run.HERE/'handoff.json',handoff)
if __name__=='__main__':main()
