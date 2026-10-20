#!/usr/bin/env python3
"""Resumable, stage-barrier Wan2.2 generation on existing Slurm allocations."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parent
FEAS = ROOT.parent / 'generation_feasibility_20260921'
SOURCE = ROOT.parent / 'wan_prompt_adaptation_20260921/deliverables/generation_queue_400.jsonl'

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.{os.getpid()}.{threading.get_ident()}.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    os.replace(tmp, path)

@contextlib.contextmanager
def queue_lock():
    with (ROOT / 'queue.lock').open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield

def prepare():
    with queue_lock():
        if (ROOT / 'queue.json').exists():
            raise SystemExit('Queue already exists; use status/resume, never overwrite.')
        raw = SOURCE.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == '479568f1410beb5706ab3a6373f618bc91ef24e71c1d40a2745a9a0754896174'
        episodes = [json.loads(s) for s in raw.splitlines()]
        tasks = []
        for rank, ep in enumerate(episodes, 1):
            assert ep['generation_priority'] == rank
            for shot in ep['shots']:
                prompt = shot['wan_prompt_en']
                assert hashlib.sha256(prompt.encode()).hexdigest() == shot['wan_sha256']
                assert Path(shot['prompt_file']).read_text() == prompt
                assert shot['wan_tokens_including_special'] <= 512
                key = ep['episode_id'] + '/' + shot['shot_id']
                tasks.append(dict(key=key, episode_id=ep['episode_id'], shot_id=shot['shot_id'],
                    rank=rank, stage=1 if rank <= 100 else 2 if rank <= 200 else 3,
                    seed=int.from_bytes(hashlib.sha256(('wan400-v1:' + key).encode()).digest()[:4], 'big'),
                    prompt=prompt, prompt_sha256=shot['wan_sha256'], status='pending', attempts=0))
        assert len(episodes) == 400 and len(tasks) == 2000
        assert [sum(t['stage'] == s for t in tasks) for s in (1,2,3)] == [500,500,1000]
        (ROOT / 'input_queue_400.jsonl').write_bytes(raw)
        write_json(ROOT / 'queue.json', dict(created=time.time(), stage=1, tasks=tasks))
        write_json(ROOT / 'manifest.json', dict(source=str(SOURCE), source_sha256=hashlib.sha256(raw).hexdigest(),
            model='Wan2.2-T2V-A14B', checkpoint=str(FEAS/'models/Wan2.2-T2V-A14B'),
            size=[832,480], frames=81, fps=16, steps=40, solver='unipc', shift=12,
            guide_scale=[3.0,4.0], precision='official BF16 conversion; no quantization',
            negative_prompt='unchanged official WAN_CONFIGS[t2v-A14B].sample_neg_prompt',
            prompt_policy='exact wan_prompt_en; no global concatenation or extra rewriting',
            phase_policy='all 500 core shots verified before stage2; next500 before final1000',
            seed_policy='first32bits SHA256(wan400-v1:<episode_id>/<shot_id>)',
            created=time.time()))
    status()

def claim(worker):
    with queue_lock():
        q = json.loads((ROOT / 'queue.json').read_text())
        for stage in (1,2,3):
            group = [x for x in q['tasks'] if x['stage'] == stage]
            if all(x['status'] == 'done' for x in group):
                continue
            q['stage'] = stage
            pending = [x for x in group if x['status'] == 'pending']
            if not pending:
                return 'wait'
            task = pending[0]
            task.update(status='running', worker=worker, started=time.time(), attempts=task['attempts']+1)
            write_json(ROOT / 'queue.json', q)
            return dict(task)
        return None

def finish(key, worker, result=None, error=None):
    with queue_lock():
        q = json.loads((ROOT / 'queue.json').read_text())
        t = next(t for t in q['tasks'] if t['key'] == key)
        assert t['status'] == 'running' and t['worker'] == worker
        if error:
            t.update(status='pending' if t['attempts'] < 3 else 'failed', error=error, ended=time.time())
        else:
            t.update(status='done', result=result, ended=time.time())
        write_json(ROOT / 'queue.json', q)

def status():
    q = json.loads((ROOT / 'queue.json').read_text())
    from collections import Counter
    out = {'timestamp':time.time(), 'stages': {str(s):dict(Counter(t['status'] for t in q['tasks'] if t['stage']==s)) for s in (1,2,3)}}
    out['complete_episodes'] = sum(all(t['status']=='done' for t in q['tasks'] if t['episode_id']==e)
        for e in {t['episode_id'] for t in q['tasks']})
    out['workers'] = [json.loads(p.read_text()) for p in sorted((ROOT/'workers').glob('*.json'))]
    print(json.dumps(out, indent=2))

def concat_episode(episode_id):
    import imageio_ffmpeg
    dest = ROOT / 'videos' / episode_id
    with (dest/'concat.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (dest/'episode.json').exists():
            return
        q=json.loads((ROOT/'queue.json').read_text())
        group=[t for t in q['tasks'] if t['episode_id']==episode_id]
        if not all(t['status']=='done' for t in group):
            return
        entries=[dest/(t['shot_id']+'.mp4') for t in group]
        listing=dest/'concat.txt'
        listing.write_text(''.join("file '"+p.name+"'\n" for p in entries))
        temp=dest/'episode.partial.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-y','-loglevel','error',
            '-f','concat','-safe','0','-i',str(listing),'-c','copy',str(temp)],check=True)
        reader=imageio_ffmpeg.read_frames(str(temp))
        meta=next(reader)
        count=sum(1 for _ in reader)
        assert count==81*len(group), (count,len(group))
        assert tuple(meta['size'])==(832,480)
        final=dest/'episode.mp4';os.replace(temp,final)
        write_json(dest/'episode.json',dict(episode_id=episode_id,shots=len(group),frames=count,
            video=str(final),sha256=hashlib.sha256(final.read_bytes()).hexdigest(),completed=time.time()))

def worker(args):
    sys.path[:0]=[str(FEAS/'wan_deps'),str(FEAS/'deps'),str(FEAS/'repos/Wan2.2')]
    # Per-worker local writable MIOpen cache; shared defaults are read-only on some nodes.
    cache=Path('/tmp')/'eecbench_wan400_miopen'/args.worker
    cache.mkdir(parents=True,exist_ok=True)
    os.environ['MIOPEN_USER_DB_PATH']=str(cache)
    os.environ['MIOPEN_CUSTOM_CACHE_DIR']=str(cache)
    # The idle guard must run before this process imports torch/opens a GPU.
    import torch
    from wan import WanT2V
    from wan.configs import WAN_CONFIGS
    from wan.utils.utils import save_video
    import imageio.v2 as imageio
    name=args.worker
    cfg=WAN_CONFIGS['t2v-A14B']
    state=dict(worker=name,node=socket.gethostname(),pid=os.getpid(),job=os.environ.get('SLURM_JOB_ID'),
        uuid=os.environ.get('ROCR_VISIBLE_DEVICES'),memory_mode=args.memory_mode,state='loading',started=time.time())
    stop=threading.Event()
    def heartbeat():
        while not stop.is_set():
            write_json(ROOT/'workers'/f'{name}.json',dict(state,heartbeat=time.time()))
            stop.wait(30)
    threading.Thread(target=heartbeat,daemon=True).start()
    t0=time.perf_counter()
    try:
        if args.memory_mode=='stream':
            from streaming import StreamingWan
            model=StreamingWan(cfg,str(FEAS/'models/Wan2.2-T2V-A14B'))
        else:
            model=WanT2V(cfg,str(FEAS/'models/Wan2.2-T2V-A14B'),device_id=0,
                t5_cpu=False,init_on_cpu=True,convert_model_dtype=True)
        torch.cuda.synchronize()
        state.update(state='ready',load_seconds=time.perf_counter()-t0,torch=torch.__version__)
        print('MODEL_READY',json.dumps(state),flush=True)
        # Keep official sampling loop untouched; record completed denoising steps.
        import wan.text2video as t2v
        original_tqdm=t2v.tqdm
        def progress(iterable,*a,**kw):
            total=len(iterable);state.update(step=0,total_steps=total,denoise_started=time.time())
            for i,item in enumerate(original_tqdm(iterable,*a,**kw)):
                yield item
                state.update(step=i+1,last_step_at=time.time())
        t2v.tqdm=progress
        while True:
            if (ROOT/'STOP').exists():
                state.update(state='stopped_between_shots');break
            task=claim(name)
            if task is None:
                state.update(state='complete');break
            if task=='wait':
                state.update(state='waiting_for_phase_barrier');time.sleep(20);continue
            state.update(state='generating',task=task['key'],shot_started=time.time(),step=0)
            dest=ROOT/'videos'/task['episode_id'];dest.mkdir(parents=True,exist_ok=True)
            video=None
            try:
                (dest/(task['shot_id']+'.prompt.txt')).write_text(task['prompt'])
                torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();started=time.perf_counter()
                video=model.generate(task['prompt'],size=(832,480),frame_num=81,shift=cfg.sample_shift,
                    sample_solver='unipc',sampling_steps=40,guide_scale=cfg.sample_guide_scale,
                    seed=task['seed'],offload_model=True)
                torch.cuda.synchronize();generation=time.perf_counter()-started
                assert list(video.shape)==[3,81,480,832],list(video.shape)
                assert torch.isfinite(video).all().item(),'Nonfinite output'
                stats=dict(min=video.min().item(),max=video.max().item(),std=video.float().std().item())
                state.update(state='saving');started=time.perf_counter()
                path=dest/(task['shot_id']+'.mp4');temp=dest/(task['shot_id']+'.partial.mp4')
                save_video(tensor=video[None],save_file=str(temp),fps=16,nrow=1,normalize=True,value_range=(-1,1))
                reader=imageio.get_reader(str(temp));n=0;selected=[]
                for frame in reader:
                    assert frame.shape[:2]==(480,832)
                    if n in (0,40,80):selected.append(frame.copy())
                    n+=1
                reader.close();assert n==81,n
                os.replace(temp,path)
                from PIL import Image
                sheet=Image.new('RGB',(832*3,480))
                for i,frame in enumerate(selected):sheet.paste(Image.fromarray(frame),(i*832,0))
                sheet.resize((1248,240)).save(dest/(task['shot_id']+'.contact.jpg'))
                record=dict(key=task['key'],seed=task['seed'],prompt_sha256=task['prompt_sha256'],
                    worker=name,node=state['node'],uuid=state['uuid'],memory_mode=args.memory_mode,
                    generation_seconds=generation,save_validation_seconds=time.perf_counter()-started,
                    peak_allocated_bytes=torch.cuda.max_memory_allocated(),frames=n,tensor_stats=stats,
                    output=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),finished=time.time())
                write_json(dest/(task['shot_id']+'.json'),record)
                finish(task['key'],name,result=record)
                print('SHOT_DONE',json.dumps(record),flush=True)
                try:concat_episode(task['episode_id'])
                except Exception:
                    print('CONCAT_ERROR',task['episode_id'],traceback.format_exc(),flush=True)
            except Exception:
                error=traceback.format_exc();print('SHOT_ERROR',task['key'],error,flush=True)
                finish(task['key'],name,error=error)
                # A broken GPU context must not poison every remaining task.
                state.update(state='failed',error=error);raise
            finally:
                del video
    except BaseException:
        state.update(state='failed',error=traceback.format_exc())
        raise
    finally:
        stop.set()
        write_json(ROOT/'workers'/f'{name}.json',dict(state,heartbeat=time.time()))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','status','worker'])
    p.add_argument('--worker');p.add_argument('--memory-mode',choices=['standard','stream'],default='standard')
    args=p.parse_args()
    if args.action=='prepare':prepare()
    elif args.action=='status':status()
    else:worker(args)
