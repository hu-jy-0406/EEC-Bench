#!/usr/bin/env python3
"""Requirement-level audit; only publishes candidates_400.jsonl after exact completion."""
import collections,csv,html,json,os,re,statistics,subprocess,sys
from pathlib import Path
from campaign import ROOT,TARGET,FFDIR,accepted,tally,clip_overlap,read,usage_report,atomic_jsonl
from extraction.run_extraction import sha,dump
from extraction.contract import validate_extraction,validate_audit
from source_work_identity import identify,work_key

def main():
 if not os.environ.get('SLURM_JOB_ID'):raise RuntimeError('Compute allocation required')
 rows=accepted();errors=[];checks=collections.Counter();counts=tally(rows);works=collections.Counter();seen=set();cached_hash={};descriptions=[];camera=0
 official={};source_index_hashes={}
 for dataset in ['sf20k','muss']:
  index_path=ROOT/'metadata'/dataset/'candidates.json'
  official[dataset]={(v['video_id'],v['video_url']) for v in read(index_path)['candidates']}
  source_index_hashes[dataset]=sha(index_path)
 if len(rows)!=400:errors.append(f'Expected400 candidates, observed{len(rows)}')
 for key,target in TARGET.items():
  if counts[key]!=target:errors.append(f'Quota{key}:{counts[key]}!={target}')
 def verify_hash(path,expected):
  path=str(path)
  if path not in cached_hash:cached_hash[path]=sha(path)
  if cached_hash[path]!=expected:raise ValueError('Hash mismatch: '+path)
 for row in rows:
  try:
   wid=row['episode_id'];assert wid not in seen;seen.add(wid);assert row['source_work_key']==work_key(row['source']);works[row['source_work_key']]+=1
   if row['source']['dataset']=='muss':assert identify(row['source'])['method']!='video_id_fallback','MuSS work identity still unresolved'
   p=row['provenance'];verify_hash(p['canonical_source_input'],p['canonical_sha256']);verify_hash(p['extraction'],p['extraction_sha256']);verify_hash(p['audit'],p['audit_sha256'])
   canonical=read(p['canonical_source_input']);folder=Path(p['extraction']).parent;payload=read(folder/'input.json');proposal=read(p['extraction']);audit=read(p['audit'])
   assert row['source']==canonical['source']
   assert (row['source']['video_id'],row['source']['url']) in official[row['source']['dataset']]
   assert row['source_window']=={k:canonical['window'][k] for k in ['start_seconds','end_seconds']}
   assert row['source_cleanliness']==canonical['source_cleanliness']
   assert row['title']==proposal['title'] and row['global_prompt']==proposal['generation_summary_en']
   validate_extraction(proposal,payload);validate_audit(audit,payload,proposal)
   assert proposal['suitability']=='suitable' and audit['disposition']=='pass'
   assert row['shots']==proposal['shots'] and row['entities']==proposal['entities'] and row['scenes']==proposal['scenes']
   assert len(row['shots'])==row['shot_count'] and row['target_duration_seconds']==row['shot_count']*5
   assert all(s['target_duration_seconds']==5 for s in row['shots'])
   verify_hash(row['source']['path'],row['source']['sha256'])
   for shot in canonical['shots']:
    for frame in shot['frames']:verify_hash(frame['path'],frame['sha256']);checks['native_evidence_frames']+=1
   clean=row['source_cleanliness'];verify_hash(clean['screen_path'],clean['screen_sha256'])
   assert read(clean['screen_path'])['source_suitability']=='use'
   checks['official_source_membership']+=1
   assert not any(clip_overlap(row['source_window'],x) for x in clean['excluded_intervals'])
   assert all(s['source_cleanliness']=='supported' for s in audit['shot_checks'])
   clip=row['source_clip'];verify_hash(clip['path'],clip['sha256'])
   probe=json.loads(subprocess.check_output([str(FFDIR/'ffprobe'),'-v','error','-show_format','-of','json',clip['path']]))
   assert abs(float(probe['format']['duration'])-(row['source_window']['end_seconds']-row['source_window']['start_seconds']))<=.2
   assert clip['source_start_seconds']==row['source_window']['start_seconds'] and clip['source_end_seconds']==row['source_window']['end_seconds']
   for shot in row['shots']:
    text=shot['generation_prompt_en'];descriptions.append(len(text.split()))
    camera+=bool(re.search(r'\b(camera|close[- ]up|(?:wide|medium|closer)\b[^.!?]{0,24}\b(?:shot|view|composition)|waist[- ]up|two[- ]shot|eye[- ]level|high[- ]angle|low[- ]angle|over[- ]the[- ]shoulder|tracking shot|dolly|pan(?:s|ning)?|zoom(?:s|ing)?|reframe)\b',text,re.I))
   checks['verified_candidates']+=1
  except Exception as e:errors.append(f"{row.get('episode_id')}: {type(e).__name__}: {e}")
 for work,n in works.items():
  if n>3:errors.append(f'More than3 candidates from source work:{work}')
 for i,a in enumerate(rows):
  for b in rows[:i]:
   if a['source']['video_id']==b['source']['video_id'] and clip_overlap(a['source_window'],b['source_window']):errors.append('Overlapping delivered source windows:'+a['episode_id']+'/'+b['episode_id'])
 if len(descriptions)!=2000:errors.append(f'Expected2000 shot prompts, observed{len(descriptions)}')
 # Lexical camera counts are diagnostics only; phrasing such as "medium view"
 # was missed by the old regex. Semantic style is checked separately, without
 # imposing an unrequested fixed fraction of camera-guided shots.
 report={'status':'pass' if not errors else 'incomplete_or_failed','errors':errors,'counts':dict(checks),'episode_count':len(rows),'shot_count':len(descriptions),'requested_total_seconds':sum(r['target_duration_seconds'] for r in rows),'source_counts':dict(collections.Counter(r['source']['dataset'] for r in rows)),'shot_count_distribution':dict(collections.Counter(r['shot_count'] for r in rows)),'official_index_hashes':source_index_hashes,'source_type_counts':dict(collections.Counter(r['source_type'] for r in rows)),'source_work_count':len(works),'max_per_source_work':max(works.values(),default=0),'style_diagnostics':{'words_per_shot_mean':statistics.mean(descriptions) if descriptions else None,'words_per_shot_median':statistics.median(descriptions) if descriptions else None,'words_per_shot_min':min(descriptions,default=0),'words_per_shot_max':max(descriptions,default=0),'camera_language_shots_regex_diagnostic':camera,'not_a_semantic_density_or_diversity_metric':True},'cleanliness_evidence':'source overview plus dense tail original frames; independent per-window frame audit; excluded intervals cannot intersect clips','human_review_complete':False,'scope':'400 automatically screened candidates for user selection of300; not generated-video evaluation; no exhaustive human/full-frame ad-recall claim','new_call_usage_cost':{k:v for k,v in usage_report().items() if k!='rows'}}
 dump(ROOT/'deliverables/final_audit.json',report)
 if errors:print(json.dumps({'status':report['status'],'errors':errors[:15]},ensure_ascii=False));return 1
 atomic_jsonl(ROOT/'deliverables/candidates_400.jsonl',rows)
 fields=['episode_id','dataset','source_work_key','shots','target_seconds','title','source_clip','review','selected','notes']
 with (ROOT/'deliverables/review_400.csv').open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
  for row in rows:writer.writerow(dict(episode_id=row['episode_id'],dataset=row['source']['dataset'],source_work_key=row['source_work_key'],shots=row['shot_count'],target_seconds=row['target_duration_seconds'],title=row['title'],source_clip=row['source_clip']['path'],review=row['provenance']['review'],selected='',notes=''))
 cards=[]
 for row in rows:
  shots=''.join('<p><b>'+html.escape(s['shot_id'])+'</b> '+html.escape(s['generation_prompt_en'])+'</p><details><summary>Uncertainty</summary>'+html.escape('; '.join(s['uncertainties']))+'</details>' for s in row['shots'])
  cards.append('<article><h2>'+html.escape(row['episode_id']+' — '+row['title'])+'</h2><p>'+html.escape(f"{row['source']['dataset']} | {row['shot_count']} shots | target {row['target_duration_seconds']}s")+'</p><video controls preload="none" width="640" src="source_clips/'+html.escape(Path(row['source_clip']['path']).name)+'"></video><p>'+html.escape(row['global_prompt'])+'</p>'+shots+'</article>')
 (ROOT/'deliverables/review_400.html').write_text('<!doctype html><meta charset="utf-8"><title>400 source-derived prompt candidates</title><style>body{max-width:1000px;margin:30px auto;font:16px/1.6 sans-serif}article{border-top:2px solid #888;padding:25px 0}details{color:#555}video{max-width:100%}</style><h1>400 candidates — select 300</h1><p>Automatically screened; human selection pending. Each source clip excludes identified promotion/endcard intervals. Target duration differs from original source duration.</p>'+''.join(cards))
 print(json.dumps({'status':'pass','candidates':400,'shots':2000,'report':str(ROOT/'deliverables/final_audit.json')}));return 0
if __name__=='__main__':sys.exit(main())
