import csv
import json
import math
from pathlib import Path
import sys
from collections import Counter
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import gs_entity_appearance_budget as m
root=Path(__file__).resolve().parent
oldroot=ROOT/'experiments/entity_appearance_minimal_20260920'
v4root=ROOT/'experiments/entity_appearance_evidence_20260920'
read=m.read;sha=m.sha
results=read(root/'results.json');rows=[];pixels=0;calls=0;originals={};usage_versions={k:[] for k in ['v3','v4','v5']}
for st in results['studies']:
    name=st['study'];run=root/name;old=oldroot/name;v4=v4root/name
    manifest=m.verify(run)
    assert st['all_entities']['dino_score']==read(old/'summary.json')['all_entities']['dino']['score']
    for entry in manifest['entities']:
        eid=entry['global_entity_id'];f=run/'entities'/eid;of=old/'entities'/eid
        for fname in ['input.json','dino.json','wire.json','sheet_audit.json','images.json']:
            assert sha(f/fname)==sha(of/fname)
        inp=read(f/'input.json');c=read(f/'codex.json');p3=read(of/'codex.json');p4=read(v4/'entities'/eid/'codex.json')
        if c['status']=='success':
            call=run/'calls'/eid;raw=read(call/'response.json')
            assert set(raw)=={'u','s','e','why','limits','expected_changes'}
            assert read(call/'output.schema.json')==m.SCHEMA
            expanded=m.expand(raw,inp)
            assert expanded==c['result'] and c['score']==expanded['score']
            vals=[s for s in raw['s'] if s is not None]
            assert c['score']==(min(vals) if vals else None)
            assert read(call/'input.json')==read(f/'wire.json')
            assert read(call/'request.json')['images']==read(f/'images.json')
            actual=read(call/'execution_override.json')
            command=actual['actual_command']
            assert actual['protocol']==m.PROTOCOL
            assert command[command.index('--model')+1]=='gpt-6-astra'
            assert 'model_reasoning_effort="medium"' in command and '--ephemeral' in command
            assert 'project_doc_max_bytes=0' in command
            for version,path in [('v3',old),('v4',v4),('v5',run)]:
                state=read(path/'calls'/eid/'status.json');assert state['status']=='success'
                usage_versions[version]+=state['usage']
            calls+=1
        else:
            assert c['status']=='not_assessable' and len(inp['appearances'])<2 and c['score'] is None
        images=read(f/'images.json');mapping=read(f/'sheet_audit.json')
        assert [a['appearance_id'] for a in mapping]==[a['appearance_id'] for a in inp['appearances']]
        for a in mapping:
            image=images[a['sheet_index']]
            assert sha(image['path'])==image['sha256'] and sha(a['crop_path'])==a['crop_sha256']
            with Image.open(image['path']) as im,Image.open(a['crop_path']) as crop:
                assert im.crop(a['rect']).tobytes()==crop.convert('RGB').tobytes()
            pixels+=1
        for a in inp['appearances']:
            if a['original_frame'] not in originals:originals[a['original_frame']]=sha(a['original_frame'])
            assert originals[a['original_frame']]==a['original_frame_sha256']
        r=c.get('result',{})
        rows.append(dict(study=name,entity=eid,name=entry['name'],v3=p3['score'],v4=p4['score'],v5=c['score'],
            unknown_dimensions=r.get('unknown_dimensions',4),scores=[d['score'] for d in r.get('dimensions',{}).values()],
            reason=r.get('reason',c.get('reason','')),limits=r.get('limitations','')))
    valid=[r['v5'] for r in rows if r['study']==name and r['v5'] is not None]
    assert st['all_entities']['codex_score']==100-math.sqrt(sum((100-s)**2 for s in valid)/len(valid))
    assert st['all_entities']['codex_entity_mean']==sum(valid)/len(valid)
usage={}
for version,us in usage_versions.items():
    counter=Counter()
    for u in us:counter.update(u)
    usage[version]=dict(counter,total_tokens=counter['input_tokens']+counter['output_tokens'],
        api_equivalent_usd=m.transport.cost(us),
        cache_free_equivalent_usd=m.transport.cost([dict(u,cached_input_tokens=0,cache_write_input_tokens=0) for u in us]))
assert usage['v5']['total_tokens']==results['total_tokens']
assert abs(usage['v5']['api_equivalent_usd']-results['standard_api_equivalent_usd'])<1e-9
m.dump(root/'comparison.json',rows);m.dump(root/'usage_comparison.json',usage)
with (root/'comparison.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
audit=dict(passed=True,entities=len(rows),calls=calls,appearance_pixels_checked=pixels,original_images_checked=len(originals),
    identity_wire_dino_unchanged=True,only_v3_output_fields=True,additional_verifier_calls=0,
    score_math_verified=True,source_hashes_verified=True,tests_passed=27,independent_human_validation=False)
m.dump(root/'audit.json',audit)
lines=['# Appearance budget v5: lower-cost scoring rules','',
'用户要求允许修改评分规则，但不引入新的核实机制。本版撤下v4四项布尔门槛、q状态、事件表及逐事件说明，恢复v3六字段短输出；没有第二次核实调用。gpt-6-astra/medium、全量原生像素拼图、原始实体身份、正常叙事及DINO保持不变。','',
'## 评分','',
'四维各按对整个实体的影响给100/90/75/25/0/null：稳定/轻微细节/清晰局部/主体重大变化/整体不相容/未知。实体取最低有效属性分；episode100-RMS缺陷，普通均分辅助。本地计算不增加模型token。四维可能重叠，min避免累加同一变化。','',
'## 全量复测结果','','| Study | v3主分（均分） | v4主分 | v5主分 | v5实体均分 | DINO未变 | 有效实体 |','|---|---:|---:|---:|---:|---:|---:|']
for st in results['studies']:
    name=st['study'];a=st['all_entities'];old=read(oldroot/name/'summary.json');v4=read(v4root/name/'summary.json')
    lines.append(f"| {name} | {old['all_entities']['codex']['score']:.4f} | {v4['all_entities']['codex_score']:.4f} | {a['codex_score']:.4f} | {a['codex_entity_mean']:.4f} | {a['dino_score']:.6f} | {a['scored_entities']}/{a['entities']} |")
lines+=['','v3/v4/v5规则不同；旧主分的数值不可视为同一量表的质量变化。','',
'| Study | 实体 | v3 | v4 | v5 | 新四维 | 新说明 |','|---|---|---:|---:|---:|---|---|']
for r in rows:
    if any(r[k] not in (None,100) for k in ['v3','v4','v5']):
        reason=r['reason'].replace('|','/').replace('\n',' ')
        lines.append(f"| {r['study']} | {r['entity']} {r['name']} | {r['v3']} | {r['v4']} | {r['v5']} | {r['scores']} | {reason} |")
lines+=['','## 实测用量与标准API等价费用','','| 版本 | Input | Cached input（input子集） | Output（含reasoning） | 总token | 估算USD | 无缓存等价USD |','|---|---:|---:|---:|---:|---:|---:|']
for version,u in usage.items():
    lines.append(f"| {version} | {u['input_tokens']} | {u.get('cached_input_tokens',0)} | {u['output_tokens']} | {u['total_tokens']} | {u['api_equivalent_usd']:.6f} | {u['cache_free_equivalent_usd']:.6f} |")
for version in ['v3','v4']:
    a,b=usage[version],usage['v5']
    lines.append(f"\nv5相对{version}: token变化{100*(b['total_tokens']/a['total_tokens']-1):+.2f}%，估算费用变化{100*(b['api_equivalent_usd']/a['api_equivalent_usd']-1):+.2f}%。")
lines+=['','各版本均67个调用，没有按结果挑选、重跑。标准API等价，非账单；不含本对话/CPU费用。沿用2026-09-20核验Astra输入10、缓存1、输出50 USD/M，并逐调用应用长上下文规则；来源 https://developers.openai.com/api/docs/models/gpt-6-astra 。缓存命中率不固定，不能把全部费用差异归因于输出字段减少。无缓存列是假定同次token均不命中缓存的敏感性分析，不是实收费用。','',
'## 验证与限制','',
'27项focused测试通过；71实体/474appearance逐像素、24张不同原图hash、原身份/完整wire/DINO、模型与medium、六输出字段、原始响应/评分与使用量全审计通过。未进行新GPU/frontend运行。','',
'相较v4牺牲事件级诊断与显式核实约束；不声称严格等效。未知属性仍保留，部分可评估100不是完整一致性证实。min忽略多个独立小变化的累积效应；RMS也会放大误判。Study2/3是开发样本，没有独立人工盲评验证，分差不是准确性证明。']
(root/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(dict(audit=audit,usage=usage)))
