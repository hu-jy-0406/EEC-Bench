"""Full temporal v2 orchestration; retain original registration implementations."""
import csv
import json
import os
from pathlib import Path
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

from gs_identity_population import scene_scope
from gs_runtime_profile import profile, resolve_identity_review_input
import gs_appearance_integration as appearance
from run_gs_integrated import B, S, FRONT, REG, CPU, GEOM, read, save, sha, prepare


def scope_for(shots):
    scope = scene_scope(shots)
    # Manifest order is chronological; compare consecutive occurrences in each scene.
    scope['cross_shot_pairs'] = [dict(pair_id=f'pair_{i:03d}',scene_id=scene,shot_ids=[a,b])
        for i,(scene,a,b) in enumerate((scene,a,b) for scene,ids in scope['scenes'].items()
                                     for a,b in zip(ids,ids[1:]))]
    return scope


def scheduling(name='parallel_v2', *, prompt_alignment=False):
    if name == 'legacy':
        return dict(name=name, stage_workers=2, api_slots=8, appearance_workers=3,
                    stream_shots=False, parallel_boundary=False, parallel_appearance=False)
    if name == 'parallel_v2':
        return dict(name=name,stage_workers=6,api_slots=8,appearance_workers=3 if prompt_alignment else 5,alignment_workers=2,
                    stream_shots=True,parallel_boundary=True,parallel_appearance=True)
    if name != 'parallel_v1':
        raise ValueError('Unknown scheduling profile')
    return dict(name=name, stage_workers=4, api_slots=8, appearance_workers=5,
                stream_shots=True, parallel_boundary=True, parallel_appearance=True)


def plan(case, shots, gpu, uuid, runtime_name=None, alignment_method='roma_fps32', stop_after='full', schedule_name='parallel_v2', prompt_binding=False, prompt_alignment=False, identity_review_input=None, prompt_recovery="auto", prompt_recovery_device="cuda"):
    if stop_after not in ('identity', 'presence', 'spatial', 'full'):
        raise ValueError('Unknown stopping stage')
    prompt_binding = prompt_binding or prompt_alignment
    case=Path(case); runtime=profile(runtime_name); schedule=scheduling(schedule_name,prompt_alignment=prompt_alignment); jobs=[]; previous=None
    identity_input=resolve_identity_review_input(runtime,identity_review_input)
    def add(name,command,on_gpu=False,root=None,depends=None,api_slots=0):
        nonlocal previous
        cmd=([CPU,str(FRONT/'guard_gpu.py'),str(gpu),uuid] if on_gpu else [])+list(map(str,command))
        jobs.append(dict(stage=name,command=cmd,case_root=str(root or case),gpu=on_gpu,api_slots=api_slots,
                         depends=list(depends if depends is not None else ([previous] if previous else []))))
        previous=name
    add('detection_and_clustering',[CPU,S/'run_wedetect_shot_entities.py','--manifest',case/'raw_manifest.json',
        '--output',case/'entities','--gpu',gpu,'--model',runtime['clustering_model'],
        '--reasoning',runtime['clustering_reasoning'],'--shot-workers','2','--codex-bin',
        '/vast/users/guangyi.chen/.local/bin/codex','--timeout','1800'],True,api_slots=2)
    recover = prompt_recovery != 'off' and prompt_binding
    if recover:
        command=[CPU,S/'gs_shot_prompt_recovery.py','--case',case,'--registry',case/'prompt_registry.json',
                 '--workers','2','--device',prompt_recovery_device]
        if prompt_recovery_device=='cuda':command+=['--gpu',gpu,'--gpu-uuid',uuid]
        if prompt_alignment:command+=['--narrative',case/'prompt_alignment_reference/narrative.json']
        add('shot_prompt_recovery',command,on_gpu=prompt_recovery_device=='cuda',api_slots=2)
    free=runtime.get('coordinate_mode')=='pi3x_native'
    if free != (alignment_method=='roma_fps32_free3d'):
        raise ValueError('Use gravity_free_v1 with roma_fps32_free3d together')
    if not free:
        add('geocalib',[GEOM,S/'prepare_gs_integrated.py',case,'calibrate','--all-shots'],True)
    add('prepare_shot_inputs',[CPU,S/'prepare_gs_integrated.py',case,'inputs','--all-shots'])
    # Process cross-shot participants first; manifest chronology and pair aliases
    # remain unchanged. Each independent shot still receives its complete inputs.
    participants={s for p in scope_for(shots)['cross_shot_pairs'] for s in p['shot_ids']}
    geometry_shots=sorted(shots,key=lambda s:s['shot_id'] not in participants) if schedule['stream_shots'] else shots
    for shot in geometry_shots:
        sid=shot['shot_id']
        add('pi3x_'+sid,[GEOM,FRONT/'geometry.py','--method','pi3x','--shot',sid],True)
        add('boxer_'+sid,[GEOM,FRONT/'boxer.py','--method','pi3x','--shot',sid],True)
    geometry_done=previous; expectations=[]; within=[]
    for shot in shots:
        sid=shot['shot_id']; name='expected_motion_'+sid; expectations.append(name)
        add(name,[CPU,S/'run_gs_temporal_stage.py',case,'expectation','--shot',sid,'--runtime-profile',runtime['name']],depends=['boxer_'+sid if schedule['stream_shots'] else geometry_done],api_slots=1)
        if stop_after!='identity':
            name='within_'+sid;within.append(name)
            cmd=[CPU,S/'run_gs_temporal_stage.py',case,'within','--shot',sid,'--runtime-profile',runtime['name']]
            if stop_after=='presence':cmd+=['--presence-only']
            add(name,cmd,depends=[expectations[-1]],api_slots=1)
    identity_stages=[]
    for pair in scope_for(shots)['cross_shot_pairs']:
        pid=pair['pair_id']; dest=case/'pairs'/pid
        def cross(label,stage,depends=None):
            add(pid+'_'+label,[CPU,S/'run_gs_flow1_stage.py',dest,stage,'--runtime-profile',runtime['name']]+(['--identity-review-input',identity_input] if stage=='review_identity' else []),root=dest,depends=depends,api_slots=1)
        add(pid+'_prepare',[CPU,S/'run_gs_temporal_stage.py',case,'prepare_pair','--pair-id',pid,'--shots',*pair['shot_ids']],
            depends=['expected_motion_'+s for s in pair['shot_ids']])
        prepared=previous
        cross('initial_identity','match',depends=[prepared]);matched=previous
        if alignment_method in ('roma_fps32','roma_fps32_free3d'):
            add(pid+'_roma_matches',[GEOM,REG/'run_matching.py','--method','roma'],True,dest,
                depends=[prepared] if runtime['overlap_roma_with_identity'] else [matched]);roma=previous
            add(pid+'_lift',[GEOM,REG/'prepare_correspondences.py','--method','roma'],root=dest,depends=[matched,roma])
            add(pid+'_registration',[GEOM,S/'register_gs_3d.py','--method','roma','--sampling','fps','--sample-count','32']+(['--rotation-model','so3'] if free else []),root=dest)
        elif alignment_method=='codex_direct':
            add(pid+'_registration',[CPU,S/'register_gs_codex.py','--case',dest],root=dest,depends=[matched],api_slots=1)
        else:raise ValueError('Unknown registration method')
        cross('identity_review','review_identity')
        identity_stages.append(previous)
        if stop_after!='identity':
            cmd=[CPU,S/'run_gs_temporal_stage.py',dest,'boundary','--runtime-profile',runtime['name']]
            if stop_after=='presence':cmd+=['--presence-only']
            add(pid+'_boundary',cmd,root=dest,api_slots=3 if schedule['parallel_boundary'] else 2)
    if stop_after in ('spatial', 'full'):
        add('entity_displacement',[CPU,S/'gs_entity_displacement.py','--case',case],
            depends=expectations+[p['pair_id']+'_boundary' for p in scope_for(shots)['cross_shot_pairs']])
    add('global_entity_table',[CPU,S/'gs_episode_entities.py','--case',case,
        '--output',case/'global_entities'],depends=identity_stages or (['shot_prompt_recovery'] if recover else ['detection_and_clustering']))
    if prompt_binding:
        command=[CPU,S/'gs_prompt_binding.py','run','--case',case,
            '--registry',case/'prompt_registry.json','--out',case/'prompt_binding']
        if prompt_alignment:command+=['--narrative',case/'prompt_alignment_reference/narrative.json']
        add('prompt_binding',command,
            depends=['global_entity_table'],api_slots=1)
    if stop_after == 'full':
        if prompt_alignment:
            alignment_workers=schedule.get('alignment_workers',1)
            add('prompt_alignment',[CPU,S/'gs_prompt_alignment.py','run','--case',case,
                '--contract',case/'prompt_alignment_reference/contract.json','--binding',case/'prompt_binding/results.json',
                '--out',case/'prompt_alignment','--workers',alignment_workers,
                '--input-transport',runtime.get('prompt_alignment_transport','canonical')],
                depends=['prompt_binding']+expectations,api_slots=alignment_workers)
        appearance.append_stages(add, case, S, CPU, GEOM, schedule)
        if prompt_binding:
            add('prompt_binding_report',[CPU,S/'gs_prompt_binding.py','report',
                '--binding',case/'prompt_binding/results.json','--appearance-csv',case/'appearance/report/entities.csv',
                '--out',case/'prompt_binding/appearance_groups.json'],depends=['prompt_binding','appearance_report'])
    return jobs


def summarize(case, state):
    calls=[]
    roots=[case]+sorted((case/'pairs').glob('*')) if (case/'pairs').exists() else [case]
    files=list((case/'entities/shots').glob('*/status.json'))
    for root in roots:files+=list((root/'calls').glob('*/status.json'))
    files+=list((case/'appearance/compact/calls').glob('*/status.json'))
    files+=list((case/'prompt_binding/calls').glob('*/status.json'))
    files+=list((case/'prompt_alignment/calls').glob('*/status.json'))
    files+=list((case/'shot_prompt_recovery/calls').glob('*/status.json'))
    for path in files:
        raw=read(path);usage=raw.get('usage',raw.get('known_usage',[]))
        if isinstance(usage,dict):usage=[usage]
        totals={k:sum(int(u.get(k,0)) for u in usage if u) for k in ('input_tokens','output_tokens','cached_input_tokens')}
        calls.append(dict(call=str(path.parent.relative_to(case)),status=raw['status'],seconds=raw.get('seconds'),
                          **totals,total_tokens=totals['input_tokens']+totals['output_tokens'],
                          standard_api_equivalent_usd=appearance.cost([u for u in usage if u])))
    within={};boundary={}
    if state['status']=='success':
        for path in (case/'within').glob('*/results.json'):within[path.parent.name]=read(path)
        for path in (case/'pairs').glob('*/boundary/results.json'):
            data=read(path);data['pair_scope']=read(path.parents[1]/'pair_scope.json');boundary[path.parents[1].name]=data
    result=dict(protocol='temporal_v2',status=state['status'],elapsed_seconds=state.get('seconds'),
                alignment_method=read(case/'alignment_method.json')['method'],within_shots=within,boundaries=boundary,
                calls=calls,total_tokens=sum(r['total_tokens'] for r in calls),stages=state['stages'],
                cross_scene_registration=False,score_aggregation='relation: per shot / boundary; position: pooled entity records; no fused overall score',
                completed_through=state.get('stop_after'),scope=read(case/'identity_scope.json'))
    result['standard_api_equivalent_usd']=sum(r['standard_api_equivalent_usd'] for r in calls)
    result['cost_note']='Standard gpt-6-astra API equivalent at 2026-09-20 prices; known recorded usage only, not a billing guarantee.'
    result['appearance']=appearance.summary(case,state['stages'],calls,read)
    displacement=case/'displacement/results.json'
    displacement_requested=any(s['stage']=='entity_displacement' for s in state['stages'])
    if displacement_requested and state['status']=='success':
        data=read(displacement)
        result['position_consistency']=dict(protocol=data['protocol'],status=data['status'],
            results_path=str(displacement),entity_records_path=str(case/'displacement/entities.csv'),
            episode=data['episode'],within_shots={s:r['summary'] for s,r in data['within_shots'].items()},
            boundaries={s:r['summary'] for s,r in data['boundaries'].items()},
            model_calls=0,total_tokens=0,api_usd=0)
    else:
        result['position_consistency']=dict(status='incomplete' if displacement_requested else 'not_run')
    binding=case/'prompt_binding/results.json'
    result['prompt_binding']=read(binding) if binding.is_file() else dict(status='not_run' if not (case/'prompt_registry.json').exists() else 'incomplete')
    groups=case/'prompt_binding/appearance_groups.json'
    if groups.is_file():result['prompt_binding']['appearance_groups']=read(groups)
    alignment=case/'prompt_alignment/results.json'
    result['prompt_alignment']=read(alignment) if alignment.is_file() else dict(status='not_run' if not (case/'prompt_alignment_reference').exists() else 'incomplete_or_stopped_early')
    recovered=case/'shot_prompt_recovery/results.json'
    result['shot_prompt_recovery']=read(recovered) if recovered.exists() else dict(status='not_run_or_incomplete')
    registry=case/'global_entities/global_entities.json'
    if registry.is_file():
        result['global_entity_table']=dict(path=str(registry),**read(registry)['counts'])
    for stage in result['stages']:
        name=stage['stage'];prefix=None
        if name.startswith(('expected_motion_','within_')):prefix='calls/'+name
        elif name=='appearance_codex':prefix='appearance/compact/calls/'
        elif name=='shot_prompt_recovery':prefix='shot_prompt_recovery/calls/'
        elif name=='prompt_binding':prefix='prompt_binding/calls/'
        elif name=='prompt_alignment':prefix='prompt_alignment/calls/'
        elif name.startswith('pair_'):
            pid='_'.join(name.split('_')[:2]);label=name[len(pid)+1:]
            suffix={'initial_identity':'matching','registration':'registration_direct','identity_review':'identity_review','boundary':'boundary_'}
            if label in suffix:prefix='pairs/'+pid+'/calls/'+suffix[label]
        stage['total_tokens']=sum(r['total_tokens'] for r in calls if
            (name=='detection_and_clustering' and r['call'].startswith('entities/shots/')) or
            (prefix is not None and r['call'].startswith(prefix)))
        stage['standard_api_equivalent_usd']=sum(r['standard_api_equivalent_usd'] for r in calls if
            (name=='detection_and_clustering' and r['call'].startswith('entities/shots/')) or
            (prefix is not None and r['call'].startswith(prefix)))
    save(case/'summary.json',result)
    for name,rows,fields in [('calls',calls,['call','status','seconds','input_tokens','output_tokens','cached_input_tokens','total_tokens','standard_api_equivalent_usd']),
                             ('stages',state['stages'],['stage','status','seconds','returncode','total_tokens','standard_api_equivalent_usd'])]:
        with (case/(name+'.csv')).open('w') as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    return result


def execute(case,jobs,env,allocation,stop_after,run_process=subprocess.run,schedule_name='parallel_v2'):
    schedule=scheduling(schedule_name,prompt_alignment=any(j['stage']=='prompt_alignment' for j in jobs))
    state=dict(protocol='temporal_v2',status='running',started=time.time(),allocation=allocation,
               stop_after=stop_after,scheduling=schedule,stages=[])
    names=[j['stage'] for j in jobs]
    if len(set(names)) != len(names) or any(not set(j['depends']) <= set(names) for j in jobs):
        raise ValueError('Invalid stage dependency graph')
    if any(not 0 <= j.get('api_slots',0) <= schedule['api_slots'] for j in jobs):
        raise ValueError('Stage exceeds API concurrency budget')
    pending=list(jobs);done=set();active={};failed=[]
    def worker(job):
        started=time.time();local=env.copy();local['CASE_ROOT']=job['case_root']
        with (case/(job['stage']+'.log')).open('w') as log:
            result=run_process(job['command'],env=local,stdout=log,stderr=subprocess.STDOUT)
        return dict(seconds=time.time()-started,returncode=result.returncode,status='success' if result.returncode==0 else 'failed')
    try:
        with ThreadPoolExecutor(max_workers=schedule['stage_workers']) as pool:
            while pending or active:
                if not failed:
                    for job in list(pending):
                        if len(active)>=schedule['stage_workers']:break
                        if not set(job['depends'])<=done:continue
                        if job['gpu'] and any(r['gpu'] for r in active.values()):continue
                        if job.get('api_slots',0)+sum(r.get('api_slots',0) for r in active.values())>schedule['api_slots']:continue
                        row=dict(job,status='running',started=time.time());state['stages'].append(row)
                        active[pool.submit(worker,job)]=row;pending.remove(job)
                        print('START',job['stage'],flush=True)
                save(case/'pipeline_runtime.json',state)
                if not active:
                    if failed:break
                    raise RuntimeError('Unresolved temporal dependency graph')
                finished,_=wait(active,return_when=FIRST_COMPLETED)
                for future in finished:
                    row=active.pop(future)
                    try:row.update(future.result())
                    except Exception as exc:row.update(status='failed',error=repr(exc),seconds=time.time()-row['started'],returncode=-1)
                    if row['status']=='success':done.add(row['stage'])
                    else:failed.append(row['stage'])
                    print('END',row['stage'],row['status'],flush=True)
        if failed:raise RuntimeError('Failed stages: '+','.join(failed))
        if not (case/'global_entities/global_entities.json').is_file():
            raise ValueError('Missing episode global entity table')
        if any(j['stage']=='prompt_binding' for j in jobs) and not (case/'prompt_binding/results.json').is_file():
            raise ValueError('Missing prompt binding result')
        if any(j['stage']=='prompt_alignment' for j in jobs) and not (case/'prompt_alignment/results.json').is_file():
            raise ValueError('Missing prompt alignment result')
        if any(j['stage']=='entity_displacement' for j in jobs):
            displacement=read(case/'displacement/results.json')
            if displacement.get('status')!='success' or displacement.get('protocol')!='entity_displacement_median_rms_v1':
                raise ValueError('Missing or invalid displacement result')
        if stop_after=='full' and not (case/'appearance/report/results.json').is_file():
            raise ValueError('Missing appearance scores')
        for shot in read(case/'raw_manifest.json')['shots']:
            for frame in shot['frames']:
                if sha(frame['path'])!=frame['sha256']:raise ValueError('Original input image changed')
        if stop_after!='identity':
            for shot in read(case/'raw_manifest.json')['shots']:
                if read(case/'within'/shot['shot_id']/'results.json')['status']!='success':raise ValueError('Missing within-shot result')
            for pair in read(case/'identity_scope.json')['cross_shot_pairs']:
                if read(case/'pairs'/pair['pair_id']/'boundary/results.json')['status']!='success':raise ValueError('Missing boundary result')
        state['status']='success'
    except BaseException as exc:
        state.update(status='failed',error=repr(exc));raise
    finally:
        state.update(finished=time.time(),seconds=time.time()-state['started']);save(case/'pipeline_runtime.json',state);summarize(case,state)
    return state


def run(a):
    shots=read(a.manifest)['shots'];case=a.output.resolve();runtime=profile(a.runtime_profile)
    runtime['identity_review_input']=resolve_identity_review_input(runtime,getattr(a,'identity_review_input',None))
    for s in shots:
        sid=s['shot_id']
        if not sid or Path(sid).name!=sid or sid in ('.','..'):raise ValueError('Invalid shot ID')
    schedule_name=getattr(a,'schedule_profile','parallel_v2')
    recovery_mode=getattr(a,'prompt_recovery','auto')
    recovery_device=getattr(a,'prompt_recovery_device','cuda')
    registry_path=getattr(a,'prompt_registry',None)
    alignment_path=getattr(a,'prompt_alignment_contract',None)
    alignment=None
    registry=None
    if alignment_path:
        from gs_prompt_alignment import validate_contract
        alignment_path=Path(alignment_path).resolve()
        alignment=validate_contract(read(alignment_path),shots)
        registry=alignment['registry']
        if registry_path and read(registry_path)!=registry:raise ValueError('Conflicting prompt registries')
    elif registry_path:
        from gs_prompt_binding import validate_registry
        registry_path=Path(registry_path).resolve()
        registry=validate_registry(read(registry_path),shots,read(a.narrative))
    jobs=plan(case,shots,a.gpu,a.gpu_uuid,runtime['name'],a.alignment_method,a.stop_after,schedule_name,prompt_binding=registry is not None,prompt_alignment=alignment is not None,identity_review_input=runtime['identity_review_input'],prompt_recovery=recovery_mode,prompt_recovery_device=recovery_device)
    if a.plan_only:
        print(json.dumps(jobs,indent=2));return
    from run_isolated_shot_static_3d import owned_compute_job
    allocation=owned_compute_job()
    if not a.gpu_uuid.startswith('GPU-'):raise ValueError('Verified ROCr UUID required')
    prepare(case,a.manifest.resolve(),a.narrative.resolve(),a.model_manifest.resolve(),a.geocalib_weights.resolve(),protocol='temporal_v2',coordinate_mode=runtime.get('coordinate_mode','gravity_aligned'))
    if registry is not None:save(case/'prompt_registry.json',registry)
    if alignment is not None:
        from gs_prompt_alignment import freeze
        freeze(alignment,case/'prompt_alignment_reference')
    save(case/'identity_scope.json',scope_for(shots));save(case/'runtime_profile.json',runtime)
    save(case/'scheduling.json',scheduling(schedule_name,prompt_alignment=alignment is not None))
    save(case/'alignment_method.json',dict(method=a.alignment_method));save(case/'consistency_protocol.json',dict(protocol='temporal_v2'))
    save(case/'shot_prompt_recovery_config.json',dict(mode=recovery_mode,enabled=registry is not None and recovery_mode!='off',device=recovery_device))
    save(case/'execution_plan.json',jobs)
    protocol_path=B/'configs/gs-temporal-v2.json';policy=read(protocol_path)
    policy['active_expected_motion_protocol']=runtime.get('expected_motion_protocol','interval_v2')
    save(case/'temporal_protocol.json',policy)
    provenance=read(case/'provenance.json');provenance['source_hashes'][str(protocol_path)]=sha(protocol_path);save(case/'provenance.json',provenance)
    if registry is not None:
        for path in (alignment_path or registry_path,S/'gs_prompt_binding.py',B/'prompts/gs_prompt_binding_v1.txt'):
            provenance['source_hashes'][str(path)]=sha(path)
        save(case/'provenance.json',provenance)
    if alignment is not None:
        for path in (S/'gs_prompt_alignment.py',B/'prompts/gs_prompt_alignment_b_v1.txt',B/'prompts/gs_prompt_alignment_compile_v1.txt'):
            provenance['source_hashes'][str(path)]=sha(path)
        save(case/'provenance.json',provenance)
    env=os.environ.copy();env.update(CASE_ROOT=str(case),PYTHONPATH=str(B/'experiments/shot_scene_boxes_goal_20260916/deps'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4')
    for key,name in [('MIOPEN_USER_DB_PATH','miopen_db'),('MIOPEN_CUSTOM_CACHE_DIR','miopen_cache'),('MPLCONFIGDIR','matplotlib')]:
        path=case/'runtime_cache'/name;path.mkdir(parents=True);env[key]=str(path)
    execute(case,jobs,env,allocation,a.stop_after,schedule_name=schedule_name)
