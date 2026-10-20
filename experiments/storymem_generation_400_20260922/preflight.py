"""CPU-only queue, native parser, and full-video decode integration checks."""
import ast, argparse, hashlib, json, multiprocessing, os, py_compile, socket, subprocess, sys, tempfile, time
from pathlib import Path
import campaign
ROOT = campaign.HERE

def process_worker(number):
    while True:
        task = campaign.claim(str(number), 'test')
        if task is None: return
        if task == 'wait':
            time.sleep(.005)
            continue
        assert task != 'failed'
        with campaign.locked():
            q = campaign.read(campaign.HERE / 'queue.json')
            assert all(t['status'] == 'done' for t in q['tasks'] if t['stage'] < task['stage'])
        if task['episode_id'] == 'e0' and task['attempts'] == 1:
            campaign.finish(task, str(number), 'test', error='intentional preflight failure')
        else:
            campaign.finish(task, str(number), 'test', result={'test': True})

def main():
    started = time.monotonic()
    assert socket.gethostname().startswith('auh7-1b-gpu-')
    assert len(os.sched_getaffinity(0)) <= 4
    checks = {}
    for p in ROOT.glob('*.py'): py_compile.compile(str(p), doraise=True)
    subprocess.run(['bash', '-n', str(ROOT / 'submit.sbatch')], check=True)
    checks['syntax'] = True
    q = campaign.read(ROOT / 'queue.json')
    assert len(q['tasks']) == 400 and all(t['status'] == 'pending' for t in q['tasks'])
    assert [sum(t['stage'] == s for t in q['tasks']) for s in (1,2,3)] == [100,100,200]
    assert [sum(len(t['mapping']) for t in q['tasks'] if t['stage'] == s) for s in (1,2,3)] == [500,500,1000]
    for t in q['tasks']:
        assert campaign.sha(t['script']) == t['script_sha256']
        prompts = [p for scene in campaign.read(t['script'])['scenes'] for p in scene['video_prompts']]
        assert len(prompts) == len(t['mapping'])
        assert all(hashlib.sha256(p.encode()).hexdigest() == m['prompt_sha256'] for p,m in zip(prompts,t['mapping']))
    checks['all400_hashes_and_stage_populations'] = True
    with tempfile.TemporaryDirectory(prefix='queue_test_', dir=ROOT) as d:
        campaign.HERE = Path(d)
        tasks = [dict(episode_id=f'e{i}', stage=1+i//12, status='pending', attempts=0, failures=0, mapping=[]) for i in range(36)]
        campaign.write(campaign.HERE/'queue.json', dict(active_job={'run':'test'}, tasks=tasks))
        ctx = multiprocessing.get_context('fork')
        workers = [ctx.Process(target=process_worker,args=(n,)) for n in range(8)]
        for p in workers: p.start()
        for p in workers:
            p.join(timeout=60)
            assert not p.is_alive() and p.exitcode == 0
        done = campaign.read(campaign.HERE/'queue.json')
        assert all(t['status']=='done' for t in done['tasks'])
        assert sum(t['attempts'] for t in done['tasks']) == 37
        checks['eight_process_claims_barriers_and_retry'] = True
        for t in tasks: t['status'] = 'done' if t['stage']==1 else 'pending'
        tasks[0]['status'] = 'failed'
        campaign.write(campaign.HERE/'queue.json',dict(active_job={'run':'test'},tasks=tasks))
        assert campaign.claim('w','test') == 'failed'
        checks['failed_core_blocks_later_stages'] = True
        tasks[0].update(status='running',worker='owner',run='test',attempts=1)
        campaign.write(campaign.HERE/'queue.json',dict(active_job={'run':'test'},tasks=tasks))
        try: campaign.finish(tasks[0],'wrong_owner','test',result={})
        except AssertionError: checks['wrong_owner_rejected'] = True
        else: raise AssertionError('Ownership gate failed')
    campaign.HERE = ROOT
    module = ast.parse((ROOT/'source_snapshot/StoryMem/pipeline.py').read_text())
    parser = next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='_parse_args')
    ns = {'argparse':argparse}
    exec(compile(ast.Module(body=[parser],type_ignores=[]),'<native_parser>','exec'),ns)
    previous = sys.argv
    for first in (True,False):
        cmd = campaign.command(q['tasks'][0],ROOT/'unused',ROOT/'unused.log',first,0,'GPU-0000000000000000')
        offset = cmd.index(str(ROOT/'source_snapshot/StoryMem/pipeline.py'))
        sys.argv = cmd[offset:]
        a = ns['_parse_args']()
        assert a.t2v_first_shot == first and not a.m2v_first_shot
        assert (a.sample_steps,a.frame_num,a.sample_guide_scale,a.max_memory_size,a.fix,a.lora_rank)==(40,81,3.5,10,3,128)
        assert a.offload_model and a.convert_model_dtype and a.mi2v
        assert a.sample_shift is None and a.sample_solver=='unipc'
        assert a.story_script_path == q['tasks'][0]['script']
    sys.argv = previous
    checks['native_parser_both_invocations'] = True
    assets = ['models/CLIP/ViT-B-32-openai.pt','models/HPSv3/HPSv3.safetensors',
              'models/StoryMem/Wan2.2-MI2V-A14B/backbone_low_noise.safetensors',
              'models/StoryMem/Wan2.2-MI2V-A14B/backbone_high_noise.safetensors',
              'models/Wan2.2-T2V-A14B/models_t5_umt5-xxl-enc-bf16.pth',
              'models/Wan2.2-I2V-A14B/models_t5_umt5-xxl-enc-bf16.pth']
    assert all((campaign.FEAS/p).is_file() and (campaign.FEAS/p).stat().st_size>0 for p in assets)
    checks['local_model_assets'] = True
    import validate_episode
    fixture = campaign.FEAS/'outputs/storymem_official'
    for i in range(1,5): validate_episode.decode(fixture/f'01_{i:02d}.mp4',81)
    validate_episode.decode(fixture/'storymem_official.mp4',324)
    try: validate_episode.decode(fixture/'01_01.mp4',80)
    except AssertionError: checks['decode_and_wrong_frame_count_rejection'] = True
    else: raise AssertionError('Frame count gate failed')
    # Exercise the entire validator with real previously generated video,
    # original tensor/selector logs, and unchanged keyframe pixels.
    with tempfile.TemporaryDirectory(prefix='episode_fixture_', dir=ROOT) as d:
        attempt = Path(d)
        native = attempt/'native'
        native.mkdir()
        for p in fixture.glob('[0-9][0-9]_[0-9][0-9].mp4'):
            (native/p.name).symlink_to(p.resolve())
        for p in fixture.glob('*keyframe*.jpg'):
            (native/p.name).symlink_to(p.resolve())
        (native/'native.mp4').symlink_to((fixture/'storymem_official.mp4').resolve())
        script = campaign.FEAS/'prompts/storymem_case.json'
        texts = [p for scene in campaign.read(script)['scenes'] for p in scene['video_prompts']]
        task = dict(episode_id='preflight_known4',script=str(script),script_sha256=campaign.sha(script),seed=20260921,
                    mapping=[dict(shot_id=f'Shot{i}',storymem_output_name=f'01_{i:02d}.mp4',
                                  prompt_sha256=hashlib.sha256(p.encode()).hexdigest()) for i,p in enumerate(texts,1)])
        campaign.write(attempt/'input.json',task)
        lines = (campaign.FEAS/'logs/storymem_official.log').read_text().splitlines()
        first = [line for line in lines if 'VIDEO_STATS ' in line and '/01_01.mp4 ' in line]
        later = [line for line in lines if 'MEMORY ' in line or ('VIDEO_STATS ' in line and '/01_01.mp4 ' not in line)]
        (attempt/'t2v.model.log').write_text(('\n'.join(first)).replace(str(fixture),str(native)))
        (attempt/'memory.model.log').write_text(('\n'.join(later)).replace(str(fixture),str(native)))
        result = validate_episode.validate(attempt)
        assert result['status']=='pass' and result['memory_counts']==[0,1,2,2]
        assert result['concatenated']['frames']==324
        checks['complete_validator_on_original_four_shot_evidence'] = True
    checks['frozen_source_hashes'] = all(campaign.sha(ROOT/name)==h for name,h in campaign.read(ROOT/'manifest.json')['code_hashes'].items())
    assert all(checks.values())
    result = dict(status='pass',checks=checks,seconds=time.monotonic()-started,node=socket.gethostname(),
                  cpus=sorted(os.sched_getaffinity(0)),gpu_work=False,new_generation=False,
                  api_calls=0,api_tokens=0,api_usd=0)
    campaign.write(ROOT/'preflight.json',result)
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
