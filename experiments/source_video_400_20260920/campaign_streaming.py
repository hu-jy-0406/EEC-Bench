"""Continuous bounded API scheduling with reserved quotas and one clip collector."""
import collections, concurrent.futures as futures, fcntl, json, os, subprocess, sys, time
from pathlib import Path
import campaign as c
ROOT=c.ROOT

def choose_reserved(pool, rows, reservations, seen):
    # Accepted rows and not-yet-delivered jobs consume the same capacity.
    known={r['episode_id'] for r in rows}
    pending=[w for w in reservations if w['window_id'] not in known]
    counts=c.tally(rows);works=collections.Counter(r['source_work_key'] for r in rows)
    blocks=[{'video_id':r['source']['video_id'],**r['source_window']} for r in rows]
    for w in pending:
        counts[w['dataset'],w['shot_count']]+=1;works[w['source_work_key']]+=1;blocks.append(w)
    eligible=[w for w in pool if w['window_id'] not in seen
        and counts[w['dataset'],w['shot_count']]<c.TARGET[w['dataset'],w['shot_count']]
        and works[w['source_work_key']]<3 and not c.scheduling_overlap(w,blocks)]
    return min(eligible,key=lambda w:(counts[w['dataset'],w['shot_count']]/c.TARGET[w['dataset'],w['shot_count']],c.sha_text(w['window_id']))) if eligible else None

def command(argv, log, allowed=(0,)):
    c.run_cmd([sys.executable,*map(str,argv)],log,allowed)

def load_pool(existing=None, keys=None):
    pool=[w for w in (existing or []) if (w['dataset'],w['video_id']) not in (keys or set())]
    for w in c.read(ROOT/'clean_window_index.json'):
        if keys is not None and (w['dataset'],w['video_id']) not in keys:continue
        identity=c.identify(c.read(w['input_path'])['source'])
        if w['dataset']=='muss' and identity['method']=='video_id_fallback':continue
        pool.append({**w,'source_work_key':identity['key']})
    return pool

def run_streaming(args):
    lock=(ROOT/'campaign.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    manifests=sorted((ROOT/'batches').glob('batch_*/manifest.json'))
    seen=set();number=0
    for m in manifests:
        number=max(number,int(m.parent.name.split('_')[-1]))
        for w in c.read(m)['windows']:
            seen.add(w['window_id'])
            if not (m.parent/'windows'/w['window_id']/'status.json').exists():
                lock.close()
                raise RuntimeError('Unfinished historical job requires inspection, never automatic paid replay: '+str(m))
    c.collect();usage=c.usage_report()
    command([ROOT/'preprocess/build_windows.py','--include-eight-alternatives'],ROOT/'preflight/build-windows-latest.log')
    pool=load_pool()
    ready=sorted((ROOT/'prepared_sources').glob('*/*/ready.json'))
    screen_queue=collections.deque(p for p in ready if not (ROOT/'source_screen'/p.parent.parent.name/p.parent.name/'status.json').exists())
    active={};encoding={};reservations={};new_keys=set();recent_failures=collections.deque(maxlen=12)
    submitted=0;stopping=None;last_heartbeat=0;max_pending_clips=16
    def api_job(w,out):
        command([ROOT/'extraction/run_extraction.py','run','--out',out,'--workers','1'],ROOT/'preflight'/f'{out.name}-run.log',tuple(range(101)))
        return c.read(out/'windows'/w['window_id']/'status.json')
    def finish_window(out):
        command([ROOT/'extraction/run_extraction.py','summarize','--out',out,'--pricing',ROOT/'pricing.json'],ROOT/'preflight'/f'{out.name}-summary.log')
        return c.collect(True,[out/'manifest.json'])
    def screen_job(path):
        command([ROOT/'screening/screen_sources.py','--ready-path',path,'--workers','1','--limit','1'],ROOT/'preflight'/f'stream-screen-{path.parent.parent.name}-{path.parent.name}.log',(0,1))
        return path
    with futures.ThreadPoolExecutor(max_workers=args.api_workers) as api, futures.ThreadPoolExecutor(max_workers=1) as clips:
        while True:
            # Consume completion on one thread; only the clip worker writes delivery files.
            for f in list(encoding):
                if not f.done():continue
                wid=encoding.pop(f);f.result();reservations.pop(wid)
            for f in list(active):
                if not f.done():continue
                kind,item,out=active.pop(f);result=f.result()
                if kind=='screen':
                    key=(item.parent.parent.name,item.parent.name)
                    new_keys.add(key);paths=list((ROOT/'source_screen'/key[0]/key[1]/'calls').glob('*/status.json'))
                else:
                    wid=item['window_id'];folder=out/'windows'/wid
                    paths=list((folder/'calls').glob('*/status.json'))
                    # Only the single collector renders or changes accepted/rejected ledgers.
                    encoding[clips.submit(finish_window,out)]=wid
                    runtime=c.read(out/'runtime.json');runtime['global_api_worker_limit']=args.api_workers;c.dump(out/'runtime.json',runtime)
                failures=sum(c.read(p).get('status')=='failed' for p in paths)
                recent_failures.append(failures)
                if sum(recent_failures)>=3:stopping='service_failures_need_inspection'
                usage=c.usage_report(paths=paths,prior=usage)
                c.dump(ROOT/'streaming_usage_checkpoint.json',{'updated':time.time(),'completed_work_kind':kind,'total_tokens':usage['total_tokens'],'standard_api_equivalent_usd':usage['standard_api_equivalent_usd'],'not_a_bill':True,'scope':'completed jobs; in-flight calls excluded'})
            if (ROOT/'pause_after_batch').exists():stopping='paused_at_batch_boundary'
            if submitted>=args.max_rounds*args.batch_size:stopping='bounded_round_limit_reached'
            rows=c.accepted()
            if len(rows)==400:stopping='quota_reached_pending_final_audit'
            if new_keys and not stopping:
                argv=[ROOT/'preprocess/build_windows.py','--include-eight-alternatives']
                for dataset,vid in sorted(new_keys):argv+=['--source-key',dataset+'/'+vid]
                command(argv,ROOT/'preflight/build-windows-latest.log');pool=load_pool(pool,new_keys);new_keys.clear()
            while not stopping and len(active)<args.api_workers and len(encoding)<max_pending_clips:
                w=choose_reserved(pool,rows,reservations.values(),seen)
                if w:
                    number+=1;out=ROOT/'batches'/f'batch_{number:04d}'
                    command([ROOT/'extraction/run_extraction.py','prepare','--out',out,'--inputs',w['input_path']],ROOT/'preflight'/f'{out.name}-prepare.log')
                    seen.add(w['window_id']);reservations[w['window_id']]=w
                    active[api.submit(api_job,w,out)]=('extract',w,out);submitted+=1
                elif screen_queue:
                    path=screen_queue.popleft();active[api.submit(screen_job,path)]=('screen',path,None);submitted+=1
                else:break
            now=time.time()
            if now-last_heartbeat>=30:
                state={'status':'running','mode':'streaming_v1','pid':os.getpid(),'host':__import__('socket').gethostname(),'slurm_job_id':os.environ.get('SLURM_JOB_ID'),'api_workers':args.api_workers,'active_api_jobs':len(active),'pending_clips':len(encoding),'reserved_windows':list(reservations),'accepted':len(rows),'submitted':submitted,'stopping':stopping,'updated':now}
                c.dump(ROOT/'runtime.json',state);print(json.dumps(state),flush=True);last_heartbeat=now
            if not active and not encoding:
                if stopping:
                    lock.close();return stopping
                if screen_queue or new_keys:continue
                lock.close();return 'source_pool_exhausted_expand_needed'
            time.sleep(.5)
