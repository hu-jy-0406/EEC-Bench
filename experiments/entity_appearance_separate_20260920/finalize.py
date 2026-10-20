"""Postrun audit, cost accounting and human-readable cross-study report."""
import csv,json,sys,time
from pathlib import Path
from collections import Counter
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from gs_entity_appearance import read,dump,sha,verify_sources,validate_codex,crop_box
EXP=Path(__file__).resolve().parent

def main():
    results={}; allstatuses=[]; audit={}
    for study in ('study2','study3'):
        out=EXP/study;m=verify_sources(out);s=read(out/'summary.json'); reg=read(m['source_registry'])
        original={e['global_entity_id']:e for e in reg['entities']}
        matrix=np.load(out/'dino_embeddings.npz'); lookup={k:v for k,v in zip(matrix['keys'],matrix['embeddings'])}
        ids=set();positive=0;unknown=0;cost=0;statuses=[];counters=Counter();flat=[]
        for row in s['entities']:
            eid=row['global_entity_id'];folder=out/'entities'/eid;p=read(folder/'input.json'); ids.add(eid)
            expected={(a['shot_id'],o['frame_id']):o for a in original[eid]['appearances'] for o in a['observations'] if o['exist'] is True and o['box_xyxy'] is not None}
            assert set(expected)=={(a['shot_id'],a['frame_id']) for a in p['appearances']}
            assert len(expected)==len(p['appearances']);positive+=len(expected);unknown+=len(p['unknown_observations'])
            for a in p['appearances']:
                o=expected[a['shot_id'],a['frame_id']]
                assert a['canonical_box_xyxy']==o['box_xyxy'] and a['box_candidate_id']==o['box_candidate_id']
                assert [c['candidate_id'] for c in a['candidates']]==o['candidate_ids']
                assert sha(a['crop_path'])==a['crop_sha256'] and sha(a['original_frame'])==a['original_frame_sha256']
            c=read(folder/'codex.json');d=read(folder/'dino.json')
            assert c['status'] in ('success','not_assessable')
            if c['status']=='success':
                validate_codex(c['result'],p)
                call=out/'calls'/eid
                assert read(call/'input.json')==p
                request=read(call/'request.json');images=read(folder/'images.json')
                assert len(request['images'])==2*len(p['appearances'])
                assert [a['sha256'] for a in request['images']]==[a['sha256'] for a in images]
                status=read(call/'status.json');assert status['status']=='success';assert status['model']=='gpt-6-astra' and status['reasoning']=='medium'
                statuses.append(status)
                for u in status['usage']:
                    counters.update(u)
                    inp=u['input_tokens'];cache=u.get('cached_input_tokens',0);write=u.get('cache_write_input_tokens',0);output=u['output_tokens']
                    assert 0<=cache+write<=inp
                    im,om=(2,1.5) if inp>272000 else (1,1)
                    cost+=((inp-cache-write)*10*im+cache*1*im+write*12.5*im+output*50*om)/1e6
            else:assert len(expected)<2 and c['score'] is None
            features=np.stack([lookup[eid+'/'+a['appearance_id']] for a in p['appearances']]).astype(np.float64)
            features/=np.linalg.norm(features,axis=1)[:,None]
            shotcounts=Counter(a['shot_id'] for a in p['appearances'])
            w=np.array([1/(len(shotcounts)*shotcounts[a['shot_id']]) for a in p['appearances']])
            center=np.einsum('i,ij->j',w,features);norm=np.linalg.norm(center)
            independent=float(np.linalg.norm(center)) if len(expected)>=2 and norm>1e-12 else None
            assert (independent is None)==(d['score'] is None)
            if independent is not None:assert abs(independent-d['score'])<1e-10
            assert np.allclose(features@features.T,d['pairwise_cosines'],atol=1e-10)
            assert d['appearance_ids']==[a['appearance_id'] for a in p['appearances']]
            for i,a in enumerate(p['appearances']):
                flat.append(dict(global_entity_id=eid,name=row['name'],**a,codex_entity_score=c['score'],
                                 dino_entity_score=d['score'],dino_centroid_similarity=d['similarities_to_centroid'][i] if d['similarities_to_centroid'] is not None and d['score'] is not None else None,
                                 dino_weight=d['weights'][i]))
        assert ids==set(original)
        dump(out/'appearance_table.json',dict(source_case=m['source_case'],source_registry=m['source_registry'],
             entities=s['entities'],appearances=flat,unknown_observations_total=unknown))
        with (out/'appearances.csv').open('w') as f:
            columns=['global_entity_id','name','appearance_id','shot_id','frame_id','timestamp_sec','canonical_box_xyxy','box_candidate_id','derived_crop_xyxy','crop_path','original_frame','dino_centroid_similarity','dino_weight','dino_entity_score','codex_entity_score']
            w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
            for r in flat:w.writerow({k:json.dumps(r[k],ensure_ascii=False) if isinstance(r[k],(list,dict)) else r[k] for k in columns})
        for grouping,rs in [('all_entities',s['entities']),('multi_shot_entities',[r for r in s['entities'] if len(r['observed_shot_ids'])>1]),('single_shot_entities',[r for r in s['entities'] if len(r['observed_shot_ids'])==1])]:
            for metric in ('codex','dino'):
                vals=[r[metric+'_score'] for r in rs if r[metric+'_score'] is not None]
                assert abs(sum(vals)/len(vals)-s[grouping][metric]['score'])<1e-10
        s['usage']=dict(counters);s['usage']['total_input_plus_output_tokens']=counters['input_tokens']+counters['output_tokens']
        s['cost']=dict(status='standard_api_equivalent_estimate_not_invoice',currency='USD',estimate=cost,
            source='https://developers.openai.com/api/docs/models/gpt-6-astra',verified_date='2026-09-20',
            per_million_tokens=dict(uncached_input=10,cached_input=1,cache_write_input=12.5,output=50),
            long_context='input>272000: input/cache/write x2, output x1.5',excludes='This interactive conversation, GPU and any subscription-specific billing')
        s['timing']=dict(calls=len(statuses),summed_call_seconds=sum(x['seconds'] for x in statuses),
                         first_call_started=min(x['started'] for x in statuses),last_call_ended=max(x['ended'] for x in statuses),
                         call_span_seconds=max(x['ended'] for x in statuses)-min(x['started'] for x in statuses),dino=read(out/'dino_runtime.json'))
        dump(out/'summary.json',s); results[study]=s;allstatuses.extend(statuses)
        audit[study]=dict(passed=True,entities=len(ids),positive_appearances=positive,unknown_observations=unknown,codex_calls=len(statuses),
                         complete_frozen_population=True,original_boxes_and_hashes_unchanged=True,all_attachments_accounted=True,
                         dimension_and_entity_means_valid=True,dino_independently_recomputed=True)
        with (out/'entities.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=['global_entity_id','name','observed_shot_ids','appearances','codex_score','dino_score','codex_reason','limitations']);w.writeheader()
            for r in s['entities']:w.writerow({k:r[k] for k in w.fieldnames})
    for p,h in read(EXP/'implementation_hashes.json').items():assert sha(p)==h,p
    audit['implementation_unchanged']=True;dump(EXP/'audit.json',audit)
    total=dict(calls=len(allstatuses),tokens=sum(s['usage']['total_input_plus_output_tokens'] for s in results.values()),
               api_equivalent_usd=sum(s['cost']['estimate'] for s in results.values()),
               codex_wall_seconds=max(x['ended'] for x in allstatuses)-min(x['started'] for x in allstatuses))
    dump(EXP/'results.json',dict(studies=results,total=total,audit=audit))
    lines=['# Study2 / Study3 appearance：独立 Codex 与 DINO 实测','',
           '复用 `within_negative_review_20260920/full` 的冻结全局身份表，appearance 全部新算。未重新检测、聚类、注册或计算原有 presence/spatial；没有融合分。每个可评实体一次 Astra/medium 调用，传入全部出现的 crop 与原图。DINOv2-base 独立推理。','',
           '| 范围 | Study | Codex可评 / DINO可评 / 总实体 | Codex /100 | DINO centroid cosine |','|---|---|---:|---:|---:|']
    for key,label in [('all_entities','全部实体'),('multi_shot_entities','跨 shot 实体子集'),('single_shot_entities','单 shot 实体子集')]:
        for name,s in results.items():
            g=s[key];lines.append(f'| {label} | {name} | {g["codex"]["scored_entities"]} / {g["dino"]["scored_entities"]} / {g["entities"]} | {g["codex"]["score"]:.4f} | {g["dino"]["score"]:.6f} |')
    lines += ['', '两项均采用有效实体等权均值；DINO 每实体内部各 shot 总权重相等。跨 shot 子集仍包含这些实体的全部关键帧，不是单独的跨 shot pair-only 指标。每个 study 两个实体只有一帧，均 null。未知身份不合并，场景间不建立身份链，因此 Shot2 的人物/书等仍独立记录。','',
              '## 主要非满分 Codex 结果','', '| Study | Entity | Name | Codex | DINO | 解释 |','|---|---|---|---:|---:|---|']
    for name,s in results.items():
        for r in sorted(s['entities'],key=lambda x:x['codex_score'] if x['codex_score'] is not None else 101):
            if r['codex_score'] is not None and r['codex_score']<100:
                lines.append(f'| {name} | {r["global_entity_id"]} | {r["name"]} | {r["codex_score"]:.2f} | {r["dino_score"]:.4f} | {r["codex_reason"].replace(chr(10)," ").replace("|","/")} |')
    lines += ['', '## 使用量与耗时','', '| Study | 调用 | Input | Cached subset | Output | Token总量 | API等价USD | 调用墙钟分钟 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for name,s in results.items():
        u=s['usage'];t=s['timing'];lines.append(f'| {name} | {t["calls"]} | {u["input_tokens"]:,} | {u["cached_input_tokens"]:,} | {u["output_tokens"]:,} | {u["total_input_plus_output_tokens"]:,} | ${s["cost"]["estimate"]:.6f} | {t["call_span_seconds"]/60:.2f} |')
    lines += ['',f'合计 {total["calls"]} 次调用，{total["tokens"]:,} tokens，标准 API 等价估算 ${total["api_equivalent_usd"]:.6f}；三路有界并发墙钟 {total["codex_wall_seconds"]/60:.2f} 分钟。无自动重试。两 study 调用范围可能交叠，时间不能相加。DINO 474 个 appearance 已完成，时间/config 见各 study 的 dino_runtime.json。',
              '价格核验：2026-09-20 [OpenAI GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra)，普通输入$10/M、缓存输入$1/M、缓存写入$12.5/M、输出$50/M；逐调用适用长上下文规则。缓存输入为输入子集，没有重复计算；reasoning token 是 output 子集，不再另加。标准 API 等价费用，不是账单，不包含本对话和 GPU。','',
              '## 验证与限制','',
              '5项 CPU 测试通过；audit.json 校验全部冻结实体/appearance 的保全、原图/原框/hash不变、附件映射、Codex证据ID/维度均值和独立重算DINO/汇总分。GPU使用现有job196093/node197，启动前guard核验idle/VRAM/KFD并绑定GPU UUID；DINO完成后退出，无新allocation。',
              '模型结果是首轮诊断，没有人工真值标定；本次样例不能证明适用于所有物体/视角。DINO默认processor的center crop可能截去细长实体边部；小物体、遮挡和背景进入crop也会影响分数。Codex只对可比较属性评分，未显示表面不代表验证一致。',
              '历史Shot2画框集合保留旧粒度；当前更严格“独立物体分开、真实集合合并”规则未对这些冻结来源重新执行。该限制不隐藏，也不在appearance阶段改身份。',
              '逐实体：study2/REPORT.md、study3/REPORT.md 与 entities.csv；统一appearance表：appearance_table.json、appearances.csv；全部appearance原框/crop映射：entities/ge*/input.json；原始模型证据：calls/ge*/；特征和诊断：dino_embeddings.npz、entities/ge*/dino.json。协议见 EECBench/docs/entity-appearance-separate-v1.md。']
    (EXP/'REPORT.md').write_text('\n'.join(lines)+'\n' + '\n人工抽查待复核项：Study2/ge0009植物的扣分理由主要涉及盆体，但花盆另有ge0016实体，存在同一花盆变化重复归因的风险。尚无精确实体范围标注，故标为potential_scope_leakage，而非已确认误报。本轮保留全部原始分数，没有见到结果后改prompt/重跑。详见manual_review_flags.json及visual_spot_checks.md。\n')
    print(json.dumps(dict(total=total,audit=audit),ensure_ascii=False))
if __name__=='__main__':main()
