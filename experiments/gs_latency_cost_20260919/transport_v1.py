"""Controlled compact input/output transport; canonical evidence and schemas retained."""
import copy,json,shutil,tempfile,time
from pathlib import Path
import sys
B=Path(__file__).resolve().parents[2];sys.path.insert(0,str(B/'scripts'))
import run_wedetect_shot_entities as io
from gs_flow1_compact_payload import pack,dump,GUIDE
from partial_scene_contract import schema_validate
ALIASES={'entity_id':'id','frame_id':'f','shot_id':'s','group_id':'g','initial_group_id':'old','result_group_ids':'new','initial_group_reviews':'audit','structural_anchor_group_ids':'anchors','local_origin_group_id':'origin','local_reference_group_id':'ref','reference_selection_reason':'ref_why','scene_correspondence':'scene','identity_evidence':'evidence','anchor_eligible':'anchor','anchor_reason':'anchor_why','geometry_interpretation':'geom','visual_identity_evidence':'visual','same_instance_motion_alternative':'move','noncommon_checks':'singles','counterpart_visibility':'visibility','evidence_status':'e_status','prompt_fact_references':'facts','prompt_explanation':'prompt_why','prompt_review_completed':'prompt_ok','location_correspondence_supported':'loc_ok','observable_region_supported':'obs_ok','occlusion_excluded':'occ_ok','detector_gap_excluded':'det_ok','identity_supported':'id_ok','joint_presence_reasonable':'joint_ok','conflict_kind':'kind','region_xyxy':'box','witnesses':'w','registration_caveats':'reg_caveats','camera_assessment':'camera','visual_evidence':'visual','image_box_evidence':'boxes','geometry_evidence':'geometry','reviewed_frame_ids':'reviewed','observed_frame_ids':'observed','motion_intervals':'intervals','subject_id':'sub','object_id':'obj','origin_anchor_id':'origin','reference_anchor_id':'ref','reference_direction_verified':'ref_ok','common_support_verified':'support_ok','center_order_supported':'center_ok','geometry_error_can_reverse':'can_flip','subject_region_xyxy':'sub_box','object_region_xyxy':'obj_box','reference_region_xyxy':'ref_box','support_entity_id':'support','support_verified':'support_ok','relation_id':'rel','witnesses_a':'wa','witnesses_b':'wb','reference_correspondence_verified':'ref_ok','center_semantics_verified':'center_ok','geometry_error_excluded':'geom_ok','viewpoint_only_explanation_excluded':'view_ok','prompt_motion_review':'prompt','specified_motion':'motion','affected_entities':'affected','causal_explanation_of_observed_relation_change':'cause_why'}
def wire_schema(schema):
 out=copy.deepcopy(schema)
 if 'properties' in out:
  names={k:ALIASES.get(k,k) for k in out['properties']}
  assert len(set(names.values()))==len(names),'Wire key collision'
  out['properties']={names[k]:wire_schema(v) for k,v in out['properties'].items()}
  if 'required' in out:out['required']=[names[k] for k in out['required']]
 if 'items' in out:out['items']=wire_schema(out['items'])
 for key in ['anyOf','oneOf','allOf']:
  if key in out:out[key]=[wire_schema(x) for x in out[key]]
 return out
def decode(value,schema):
 if schema.get('type')=='object':return {k:decode(value[ALIASES.get(k,k)],s) for k,s in schema['properties'].items()}
 if schema.get('type')=='array':return [decode(v,schema['items']) for v in value]
 return value
OUTPUT_GUIDE='''\nOUTPUT: Use the supplied abbreviated wire schema; field aliases preserve the canonical decision fields: ALIASES. Keep each explanatory string to one short, evidence-specific clause whenever sufficient. Do not repeat object appearance or the same rationale in multiple fields. Keep all required rows, alternatives, original-frame witnesses and Prompt causal evidence; brevity must not replace supported evidence with vague claims. Do not alter identity/uncertainty or conflict thresholds to save output.\n'''
def call(stage,prompt_path,payload,images,schema,args):
 directory=args.out/stage;directory.mkdir(parents=True,exist_ok=False)
 wire=pack(payload);ws=wire_schema(schema);prompt=Path(prompt_path).read_text()+'\n'+GUIDE+OUTPUT_GUIDE.replace('ALIASES',dump(ALIASES))+'\nINPUT_JSON:\n'+dump(wire)
 for name,x in [('input.json',payload),('wire_input.json',wire),('output.schema.json',schema),('wire.schema.json',ws)]:io.dump(directory/name,x)
 (directory/'prompt.txt').write_text(prompt);start=time.time();state=dict(status='running',started=start,model=args.model,reasoning=args.reasoning);io.dump(directory/'status.json',state)
 try:
  with tempfile.TemporaryDirectory(prefix='eec-efficient-') as tmp:
   work=Path(tmp);command=[args.codex_bin,'--ask-for-approval','never','exec','--ignore-user-config','-c',args.disabled_skills,'--ephemeral','--skip-git-repo-check','--sandbox','read-only','--color','never','--json','--model',args.model,'-c','model_reasoning_effort="'+args.reasoning+'"','-c','project_doc_max_bytes=0','-c','web_search="disabled"','--output-schema',str(directory/'wire.schema.json'),'--output-last-message',str(directory/'wire_response.json'),'--cd',str(work)]
   for feature in ('shell_tool','unified_exec','view_image','apps','plugins','hooks','multi_agent','memories','skill_search','browser_use','computer_use','code_mode','code_mode_only','workspace_dependencies'):command+=['--disable',feature]
   for i,f in enumerate(images,1):
    im=work/('image_'+str(i)+Path(f['path']).suffix);shutil.copy2(f['path'],im);assert io.sha(im)==f['sha256'];command+=['--image',str(im)]
   command.append('-');io.dump(directory/'request.json',dict(command=command,model=args.model,reasoning=args.reasoning,images=[{k:f[k] for k in ['shot_id','frame_id','sha256']} for f in images]));io.run_process(command,prompt,work,directory/'events.jsonl',directory/'stderr.log',args.timeout)
  usage=io.audit_events(directory/'events.jsonl');raw=io.read(directory/'wire_response.json');schema_validate(raw,ws);result=decode(raw,schema);schema_validate(result,schema);io.dump(directory/'response.json',result);state.update(status='success',usage=usage);return result
 except BaseException as exc:
  state.update(status='failed',error=repr(exc));raise
 finally:state.update(ended=time.time(),seconds=time.time()-start);io.dump(directory/'status.json',state)
