import sys,json,copy,shutil,time
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
import run_wedetect_shot_entities as io
from gs_entity_appearance_compact import cost
from gs_shot_prompt_recovery import active_entities_root
from prepare_gs_integrated import inputs
case=R/'case';out=case/'shot_prompt_recovery';src=R.parent/'multishot_registration_ab_20260922/shared/parking4'
assert io.read(out/'results.json')['status']=='success'
# Input adapter validation reuses calibration only, does not claim fresh 3D inference.
if not (case/'calibration_new').exists():(case/'calibration_new').symlink_to(src/'calibration_new',target_is_directory=True)
inputs(case,all_shots=True)
assert active_entities_root(case)==out/'entities'
manifest=io.read(case/'raw_manifest.json');data=io.read(out/'results.json');audit=[]
for shot,summary in zip(manifest['shots'],data['shots']):
 sid=shot['shot_id'];old=io.read(case/'entities/shots'/sid/'entities.json');new=io.read(out/'entities/shots'/sid/'entities.json');payload=io.read(out/'entities/shots'/sid/'input.json');source={d['candidate_id']:(f['frame_id'],d) for f in payload['frames'] for d in f['detections']}
 before={e['entity_id']:e for e in old['entities']};old_boxes=0;added=0
 for e in new['entities']:
  for o in e['observations']:
   if o['box_xyxy'] is not None:
    assert source[o['box_candidate_id']][0]==o['frame_id'];assert source[o['box_candidate_id']][1]['box_xyxy']==o['box_xyxy']
    if ':gd' in o['box_candidate_id']:added+=1
   if e['entity_id'] in before:
    prev=next(v for v in before[e['entity_id']]['observations'] if v['frame_id']==o['frame_id'])
    if prev['box_xyxy'] is not None:
     assert prev['box_xyxy']==o['box_xyxy'] and prev['box_candidate_id']==o['box_candidate_id'];old_boxes+=1
 assert io.read(case/'inputs'/f'{sid}.json')['entities']==new['entities']
 for f in shot['frames']:assert io.sha(f['path'])==f['sha256']
 audit.append(dict(shot_id=sid,old_boxes_unchanged=old_boxes,new_observations=added,final_entities=len(new['entities']),geometry_input_uses_recovered_entities=True))
# Proof that semantic guard and new schema both reject the original invalid Shot4 assignment.
import jsonschema
from gs_shot_prompt_recovery import review_schema
sid='Shot4';p=out/'calls/Shot4_review_failed1';raw=io.read(p/'response.json');request=io.read(p/'input.json')
schema=review_schema(io.read(case/'entities/shots'/sid/'entities.json'),request['new_candidates'],request['initial_binding'],request['coverage'])
try:jsonschema.validate(raw,schema);raise AssertionError('Invalid historical result accepted')
except jsonschema.ValidationError:pass
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',18)
big=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',24)
viz=R/'visuals';viz.mkdir(exist_ok=True)
for sid in ['Shot1','Shot2','Shot4']:
 shot=next(s for s in manifest['shots'] if s['shot_id']==sid);summary=next(s for s in data['shots'] if s['shot_id']==sid);pid=next(r['entity_id'] for r in summary['final_coverage'] if r['prompt_entity_id']=='pillar');e=next(e for e in io.read(out/'entities/shots'/sid/'entities.json')['entities'] if e['entity_id']==pid)
 canvas=Image.new('RGB',(1248,3*400),'white');draw=ImageDraw.Draw(canvas)
 for i,(f,o) in enumerate(zip(shot['frames'],e['observations'])):
  im=Image.open(f['path']).convert('RGB');d=ImageDraw.Draw(im)
  if o['box_xyxy']:
   d.rectangle(o['box_xyxy'],outline='#ff3232',width=4);d.text((o['box_xyxy'][0]+4,o['box_xyxy'][1]+4),'pillar '+pid,fill='#ff3232',font=big,stroke_width=1,stroke_fill='white')
  im=im.resize((624,360));x=(i%2)*624;y=(i//2)*400;canvas.paste(im,(x,y+35));draw.text((x+8,y+6),f'{sid} / frame {f["frame_id"]} / Grounding DINO',font=font,fill='black')
 canvas.save(viz/f'{sid}_pillar_all_frames.jpg',quality=93)
# A compact, native-resolution first-frame pair for the conversation.
canvas=Image.new('RGB',(1664,520),'white');draw=ImageDraw.Draw(canvas)
for i,sid in enumerate(['Shot1','Shot2']):
 s=next(s for s in manifest['shots'] if s['shot_id']==sid);summ=next(s for s in data['shots'] if s['shot_id']==sid);pid=next(r['entity_id'] for r in summ['final_coverage'] if r['prompt_entity_id']=='pillar');e=next(e for e in io.read(out/'entities/shots'/sid/'entities.json')['entities'] if e['entity_id']==pid)
 im=Image.open(s['frames'][0]['path']).convert('RGB');ImageDraw.Draw(im).rectangle(e['observations'][0]['box_xyxy'],outline='red',width=4);canvas.paste(im,(i*832,40));draw.text((i*832+12,8),f'{sid}: pillar recovered (6/6 frames)',font=big,fill='black')
canvas.save(viz/'Shot1_Shot2_recovered_pillars.jpg',quality=95)
uses=[];calls=[]
for p in sorted((out/'calls').glob('*/status.json')):
 st=io.read(p);u=st.get('usage',st.get('known_usage',[]));uses+=u;calls.append(dict(call=p.parent.name,status=st['status'],seconds=st['seconds'],tokens=sum(a['input_tokens']+a['output_tokens'] for a in u),standard_api_equivalent_usd=cost(u)))
failed=[c for c in calls if c['status']=='failed'];tokens=sum(c['tokens'] for c in calls);usd=cost(uses)
starts=[io.read(p)['started'] for p in (out/'calls').glob('*/status.json')];finish=max(io.read(p)['started']+io.read(p)['seconds'] for p in (out/'calls').glob('*/status.json'))
summary=dict(status='success_after_one_rejected_review_and_schema_fix',audits=audit,calls=calls,total_tokens=tokens,standard_api_equivalent_usd=usd,actual_bill=False,usage={k:sum(u.get(k,0) for u in uses) for k in ['input_tokens','cached_input_tokens','output_tokens']},grounding_seconds=io.read(out/'grounding/run.json')['seconds'],first_call_to_last_call_seconds=finish-min(starts),failed_validation_tokens=sum(c['tokens'] for c in failed),failed_validation_usd=sum(c['standard_api_equivalent_usd'] for c in failed),reused_original_frontend=True,new_3d_inference=False,new_registration=False,original_inputs_unchanged=True)
io.dump(R/'audit.json',summary)
lines=['# 停车场：逐 shot prompt 绑定与 Grounding DINO 补检','',
'已完成四个 shot 的组件测试。原 WeDetect 检测和独立聚类显式复用，未重跑生成视频；新跑逐 shot 绑定、24帧 Grounding DINO 定向补检和独立候选审核。保留所有原始框，只有检测器新候选能新增实体或填补空帧。不是完整 GPU pipeline/配准/评分重跑。','',
'## 结果','', '| Shot | 实体数：前→后 | 柱子检出帧：前→后 | 新增有效观测 |','|---|---:|---:|---:|']
for s,a in zip(data['shots'],audit):
 before=next(r for r in s['initial_coverage'] if r['prompt_entity_id']=='pillar');after=next(r for r in s['final_coverage'] if r['prompt_entity_id']=='pillar');v='不要求，未补检' if after['expectation']!='required' else f"{len(before['observed_frame_ids'])}/6 → {len(after['observed_frame_ids'])}/6"
 lines.append(f"| {s['shot_id']} | {s['initial_entities']} → {s['final_entities']} | {v} | {a['new_observations']} |")
lines+=['','Shot1新增柱子和肩带；Shot2新增柱子，填补面具/肩带空帧；Shot3新增耳饰，面具仍仅第16帧有观测；Shot4新增柱子、车和肩带，车辆只检出首帧。Shot4旧肩包整体实体保持unknown，新的肩带部件单独保留，不将二者强制合并；这是仍需关注的整体/部件重叠诊断。缺口不等于物体不存在。','',
'黄色柱子在Shot1/2/4的原prompt明确出现。本次按原文引用冻结prompt_registry_v1（8项实体及4-shot schedule），不是假称旧配准实验已有结构化schedule。Shot3未要求柱子，所以不因同场景自动补建。','',
'## 实现与下游接口','',
'run_gs_integrated.py 默认 --prompt-recovery auto：有registry/align contract时，在初检聚类之后、GeoCalib/三维实体输入之前执行；--prompt-recovery off恢复旧流程。--prompt-recovery-device cuda默认，cpu可显式选择。无registry时不凭空生成schedule，保持原流程。本次CPU运行避开等待中的HoloCine GPU，GPU时间未测。','',
'prepare_gs_integrated.py、全局实体表、appearance均读取审核后的实体及候选路径；原初检目录保持不变。跨shot身份不由prompt ID强制合并；最终全局绑定复用一致的shot绑定，unknown/冲突才再次评估。失败补检阻断下游，不输出假完整结果。验证了4shot几何输入确实包含补检实体，使用旧calibration作接口验证，未推理新3D框。','',
'## 失败与修复','',
'Shot4首轮审核试图把肩带框补入绑定unknown的旧肩包整体，语义校验拒绝。原回复和成本保留为Shot4_review_failed1。将已有规则写入逐候选schema：existing目标只能是已bound且该帧缺框的实体。仅重跑Shot4审核后通过，其他三个审核及检测复用；原非法回复对新schema的拒绝检查通过。未手改模型结果或放宽规则。','',
'## 实测开销','',f'全部{len(calls)}次API调用（含1次被拒绝审核）：{tokens:,} tokens，USD {usd:.6f} 标准Astra API等价估算，非账单。失败审核：{summary["failed_validation_tokens"]:,} tokens / USD {summary["failed_validation_usd"]:.6f}。',f'Grounding DINO CPU单次加载＋24帧：{summary["grounding_seconds"]:.2f}秒。首个绑定启动到最后纠正审核完成：{summary["first_call_to_last_call_seconds"]:.2f}秒，含排查与修改等待，不是优化后生产耗时。检测本身0API tokens/USD0 API成本，CPU/GPU资源费用未计；独立环境探针额外1帧，约8.74秒（不含Python导入），不计为正式24帧补检。',
'计价沿用已核实Astra标准每百万tokens：输入USD10、缓存USD1、输出USD50；缓存是输入子集，不重复计费。逐调用原始usage在calls目录，汇总audit.json。','',
'## 图像证据','',f'![Shot1/Shot2补检柱子]({viz/"Shot1_Shot2_recovered_pillars.jpg"})','']
for sid in ['Shot1','Shot2','Shot4']:lines += [f'![{sid}六帧柱子]({viz/f"{sid}_pillar_all_frames.jpg"})','']
(R/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))
