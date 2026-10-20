import csv
import hashlib
import json
import math
from pathlib import Path
import sys
from collections import Counter
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import gs_entity_appearance_evidence as v4
root=Path(__file__).resolve().parent
oldroot=ROOT/'experiments/entity_appearance_minimal_20260920'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
results=read(root/'results.json')
rows=[]; pixels=0; calls=0; original_images={}; baseline=[]
for study in results['studies']:
    name=study['study']; run=root/name; old=oldroot/name
    m=v4.verify(run); oldsummary=read(old/'summary.json');baseline.append(oldsummary)
    assert study['all_entities']['dino_score']==oldsummary['all_entities']['dino']['score']
    for entry in m['entities']:
        eid=entry['global_entity_id']; f=run/'entities'/eid; of=old/'entities'/eid
        assert sha(f/'input.json')==sha(of/'input.json')
        assert sha(f/'dino.json')==sha(of/'dino.json')
        assert sha(f/'wire.json')==sha(of/'wire.json')
        inp=read(f/'input.json'); c=read(f/'codex.json'); previous=read(of/'codex.json')
        if c['status']=='success':
            call=run/'calls'/eid; raw=read(call/'response.json')
            exp=v4.expand(raw,inp);assert exp==c['result'] and exp['score']==c['score']
            confirmed=[e for e in exp['events'] if e['status']=='confirmed']
            ps={1:10,2:25,3:75,4:100}
            score=100-max([ps[e['severity']] for e in confirmed],default=0) if exp['assessable_dimensions'] else None
            assert score==c['score']
            assert read(call/'input.json')==read(f/'wire.json')
            assert read(call/'request.json')['images']==read(f/'images.json')
            command=read(call/'execution_override.json')['actual_command']
            assert command[command.index('--model')+1]=='gpt-6-astra'
            assert 'model_reasoning_effort="medium"' in command
            assert '--ephemeral' in command and 'project_doc_max_bytes=0' in command
            assert read(call/'execution_override.json')['protocol']==v4.PROTOCOL
            calls+=1
        else:
            assert c['status']=='not_assessable' and len(inp['appearances'])<2 and c['score'] is None
        images=read(f/'images.json'); mapping=read(f/'sheet_audit.json')
        assert [x['appearance_id'] for x in mapping]==[x['appearance_id'] for x in inp['appearances']]
        for a in mapping:
            im=images[a['sheet_index']]
            assert sha(im['path'])==im['sha256'] and sha(a['crop_path'])==a['crop_sha256']
            with Image.open(im['path']) as sheet, Image.open(a['crop_path']) as crop:
                assert sheet.crop(a['rect']).tobytes()==crop.convert('RGB').tobytes()
            pixels+=1
        for a in inp['appearances']:
            if a['original_frame'] not in original_images:original_images[a['original_frame']]=sha(a['original_frame'])
            assert original_images[a['original_frame']]==a['original_frame_sha256']
        er=c.get('result',{})
        rows.append(dict(study=name,entity=eid,name=entry['name'],shots=','.join(entry['observed_shot_ids']),
            old=previous['score'],new=c['score'],unknown_dimensions=er.get('unknown_dimensions',4),
            confirmed_events=sum(e['status']=='confirmed' for e in er.get('events',[])),
            uncertain_events=sum(e['status']=='uncertain' for e in er.get('events',[])),
            reason=er.get('reason',c.get('reason','')),limits=er.get('limitations',''),events=er.get('events',[])))
    valid=[r['new'] for r in rows if r['study']==name and r['new'] is not None]
    actual=100-math.sqrt(sum((100-s)**2 for s in valid)/len(valid)) if valid else None
    assert actual==study['all_entities']['codex_score']
    assert sum(valid)/len(valid)==study['all_entities']['codex_entity_mean']
with (root/'comparison.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=[k for k in rows[0] if k!='events']);w.writeheader()
    w.writerows({k:v for k,v in row.items() if k!='events'} for row in rows)
v4.dump(root/'comparison.json',rows)
audit=dict(passed=True,entities=len(rows),fresh_calls=calls,original_appearances_pixel_checked=pixels,
    original_images_checked=len(original_images),dino_unchanged=True,identity_and_wire_unchanged=True,
    source_hashes_passed=True,event_score_math_passed=True,all_raw_verdicts_valid=True,
    model='gpt-6-astra',reasoning='medium',fresh_frontend_or_gpu=False,
    independent_human_validation=False,tests_passed=20)
v4.dump(root/'audit.json',audit)
lines=['# Appearance evidence v4: Study2/Study3','',
'用户授权依据 Study2 扣分复核优化。一次冻结规则后对全部实体重新评分；不按分差筛选或重跑结果。使用原身份、474 appearances、原始像素拼图、叙事和 DINO；本次是全量新 Codex 评分，不是新 frontend/GPU 运行。','',
'## 规则','',
'先验证对应部位、可见性、混淆因素及实体范围，未通过的事件保留 uncertain。按整个实体的影响范围分档，轻微/局部/主体/整体变化分别扣10/25/75/100。同一变化不在属性或帧间重复累加；实体取最严重已确认事件的扣分。未知维度保留，全部未知返回null。','',
'Codex 主分 = 100 − RMS(100 − 实体分)，普通实体均分辅助；DINO 仍独立报告。以下旧/新主分公式不同，不应把其数值直接解释成模型生成质量变化。','',
'| Study | 旧 Codex 均分 | 新 Codex 缺陷敏感分 | 新实体普通均分 | DINO（未变） | 可评分实体 | 未知属性 |',
'|---|---:|---:|---:|---:|---:|---:|']
for st,old in zip(results['studies'],baseline):
    a=st['all_entities']; lines.append(f"| {st['study']} | {old['all_entities']['codex']['score']:.4f} | {a['codex_score']:.4f} | {a['codex_entity_mean']:.4f} | {a['dino_score']:.6f} | {a['scored_entities']}/{a['entities']} | {a['unknown_dimensions']} |")
lines+=['','## 逐实体变化与存疑事件','','| Study | 实体 | 旧分 | 新分 | 确认/存疑事件数 | 模型解释 |','|---|---|---:|---:|---:|---|']
for r in rows:
    if r['old'] not in (None,100) or r['new'] not in (None,100) or r['uncertain_events']:
        reason=r['reason'].replace('|','/').replace('\n',' ')
        lines.append(f"| {r['study']} | {r['entity']} {r['name']} | {r['old']} | {r['new']} | {r['confirmed_events']}/{r['uncertain_events']} | {reason} |")
lines+=['','## 用量与验证','',f"新调用 {calls}；{results['total_tokens']:,} tokens；标准 API 等价估算 ${results['standard_api_equivalent_usd']:.6f}，不是账单金额，不含本对话或计算节点成本。沿用当日已核验 Astra 费率，逐调用计算缓存/长上下文；来源 https://developers.openai.com/api/docs/models/gpt-6-astra 。",'',
'20项 focused contract tests通过。独立审计全部原图hash、474 crops拼图逐像素一致、全部实体输入/身份/叙事/DINO不变、实际模型/medium/隔离参数、原始响应与事件公式、总分。详见 audit.json、comparison.json、results.json 和原始 calls。','',
'## 限制','',
'此轮受 Study2/3 观察启发，是开发集复测，不是独立人工校准。门槛语义仍可能误判；unknown不扣分会造成乐观的条件分，必须连同未知数量/具体事件解释；多shot子集含这些实体的全部appearances。max损失不累加多个独立小错误。RMS较敏感，也可能放大误报。裁图缺乏完整场景信息。不得因为Study2未设计外观异常就强制100，也不得把新分差当作准确性证明。']
(root/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(audit))
