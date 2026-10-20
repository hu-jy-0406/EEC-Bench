#!/usr/bin/env python3
"""Bounded batches toward the exact 400 source-prompt candidate quota."""
import argparse,collections,csv,fcntl,hashlib,html,json,os,re,socket,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'extraction'))
from run_extraction import dump,sha
from contract import validate_extraction,validate_audit
from source_work_identity import identify,work_key
TARGET={('sf20k',4):120,('sf20k',6):60,('sf20k',8):20,('muss',4):120,('muss',6):60,('muss',8):20}
FFDIR=ROOT/'tools/ffmpeg-n9.0-latest-linux64-lgpl-9.0/bin'

def read(p):return json.loads(Path(p).read_text())
def lines(p):return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []
def atomic_jsonl(p,rows):
 tmp=p.with_suffix('.tmp');tmp.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows));tmp.replace(p)
def clip_overlap(a,b):return min(a['end_seconds'],b['end_seconds'])>max(a['start_seconds'],b['start_seconds'])
def run_cmd(command,log,allowed=(0,)):
 with log.open('w') as f:p=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT)
 if p.returncode not in allowed:raise RuntimeError(f'Command exit {p.returncode}: {log}')
 return p.returncode

def accepted():
 rows=lines(ROOT/'deliverables/candidates_in_progress.jsonl')
 for row in rows:
  row['source_work_identity']=identify(row['source'])
  row['source_work_key']=row['source_work_identity']['key']
 return rows
def tally(rows):return collections.Counter((r['source']['dataset'],r['shot_count']) for r in rows)
def scheduling_overlap(window,blocks):
 return any(window['video_id']==b['video_id'] and clip_overlap(window,b) for b in blocks)

def choose_batch(limit=12):
 rows=accepted();counts=tally(rows);works=collections.Counter(r['source_work_key'] for r in rows)
 seen=set()
 for path in (ROOT/'batches').glob('*/manifest.json'):
  seen.update(w['window_id'] for w in read(path)['windows'])
 pool=[]
 for x in read(ROOT/'clean_window_index.json'):
  if x['window_id'] in seen:continue
  identity=identify(read(x['input_path'])['source'])
  if x['dataset']=='muss' and identity['method']=='video_id_fallback':continue
  pool.append({**x,'source_work_key':identity['key']})
 chosen=[]
 blocked_windows=[{'video_id':r['source']['video_id'],**r['source_window']} for r in rows]
 while len(chosen)<limit:
  candidates=[w for w in pool if counts[w['dataset'],w['shot_count']]<TARGET[w['dataset'],w['shot_count']] and works[w['source_work_key']]<3 and not scheduling_overlap(w,blocked_windows)]
  if not candidates:break
  # Source/shot quota fill controls the schedule, never evaluator or generator scores.
  w=min(candidates,key=lambda w:(counts[w['dataset'],w['shot_count']]/TARGET[w['dataset'],w['shot_count']],sha_text(w['window_id'])))
  chosen.append(w);pool.remove(w);counts[w['dataset'],w['shot_count']]+=1;works[w['source_work_key']]+=1;blocked_windows.append(w)
 return chosen

def sha_text(x):return hashlib.sha256(('20260920:'+x).encode()).hexdigest()
def render_clip(row):
 dst=ROOT/'deliverables/source_clips'/f"{row['episode_id']}.mp4";dst.parent.mkdir(exist_ok=True)
 record=dst.with_suffix('.json')
 if record.exists():
  prior=read(record)
  if dst.exists() and sha(dst)==prior['sha256']:return prior
  raise ValueError('Previously rendered source clip changed')
 win=row['source_window'];duration=win['end_seconds']-win['start_seconds'];temporary=dst.with_name(dst.stem+'.partial.mp4')
 fast_seek=row['source']['download_provenance'].get('codec') in {'h264','av1','vp9'}
 seek_args=['-ss',str(win['start_seconds']),'-accurate_seek','-i',row['source']['path']] if fast_seek else ['-i',row['source']['path'],'-ss',str(win['start_seconds'])]
 cmd=[str(FFDIR/'ffmpeg'),'-y','-nostdin','-hide_banner','-loglevel','error','-threads','1']+seek_args+['-t',str(duration),'-map','0:v:0','-an','-vf',"scale=w='min(720,iw)':h=-2",'-c:v','libopenh264','-b:v','3M','-pix_fmt','yuv420p','-threads','1','-filter_threads','1','-fps_mode','vfr','-movflags','+faststart',str(temporary)]
 run_cmd(cmd,dst.with_suffix('.encode.log'))
 probe=json.loads(subprocess.check_output([str(FFDIR/'ffprobe'),'-v','error','-show_format','-show_streams','-of','json',str(temporary)]))
 actual=float(probe['format']['duration'])
 if abs(actual-duration)>.2:raise ValueError('Clipped duration mismatch')
 temporary.replace(dst);result={'path':str(dst),'sha256':sha(dst),'source_start_seconds':win['start_seconds'],'source_end_seconds':win['end_seconds'],'requested_source_duration_seconds':duration,'actual_clip_duration_seconds':actual,'source_original_unchanged':True,'audio_included':False,'command':cmd,'seek_mode':'accurate_input_seek_v1' if fast_seek else 'legacy_output_seek'}
 dump(record,result);return result

def collect(render=True, manifests=None):
 rows=accepted();existing={r['episode_id'] for r in rows};counts=tally(rows);works=collections.Counter(r['source_work_key'] for r in rows)
 rejections=read(ROOT/'deliverables/rejected_or_review.json') if manifests is not None and (ROOT/'deliverables/rejected_or_review.json').exists() else []
 for manifest in (sorted((ROOT/'batches').glob('*/manifest.json')) if manifests is None else manifests):
  for job in read(manifest)['windows']:
   wid=job['window_id'];folder=manifest.parent/'windows'/wid;status=folder/'status.json'
   if wid in existing or not status.exists():continue
   state=read(status)
   if state.get('status')!='success' or state.get('disposition')!='pass':
    rejections.append({'window_id':wid,'batch':manifest.parent.name,**state});continue
   p=read(folder/'extraction.json');a=read(folder/'audit.json');inp=read(folder/'input.json');source=read(folder/'canonical_source_input.json')
   validate_extraction(p,inp);validate_audit(a,inp,p)
   key=source['source']['dataset'],len(p['shots']);work=work_key(source['source']);w=source['window']
   if counts[key]>=TARGET[key] or works[work]>=3:continue
   if any(r['source_work_key']==work and r['source']['video_id']==source['source']['video_id'] and clip_overlap(r['source_window'],w) for r in rows):raise ValueError('Accepted source overlap')
   forbidden=source['source_cleanliness']['excluded_intervals']
   if any(clip_overlap(w,x) for x in forbidden):raise ValueError('Accepted window crosses excluded content')
   row={'episode_id':wid,'source':source['source'],'source_work_key':work,'source_type':read(Path(source['source_cleanliness']['screen_path']))['source_type'],'source_window':{'start_seconds':w['start_seconds'],'end_seconds':w['end_seconds']},'shot_count':len(p['shots']),'target_duration_seconds':5*len(p['shots']),'title':p['title'],'global_prompt':p['generation_summary_en'],'shots':p['shots'],'entities':p['entities'],'scenes':p['scenes'],'limitations':p['limitations'],'quality_status':'automatic_checks_passed_human_selection_pending','human_review_complete':False,'source_cleanliness':source['source_cleanliness'],'provenance':{'canonical_source_input':str(folder/'canonical_source_input.json'),'canonical_sha256':sha(folder/'canonical_source_input.json'),'extraction':str(folder/'extraction.json'),'extraction_sha256':sha(folder/'extraction.json'),'audit':str(folder/'audit.json'),'audit_sha256':sha(folder/'audit.json'),'review':str(folder/'review.md'),'batch':manifest.parent.name},'contact_sheets':source['contact_sheets']}
   row['source_work_identity']=identify(source['source'])
   if render:row['source_clip']=render_clip(row)
   rows.append(row);existing.add(wid);counts[key]+=1;works[work]+=1
   atomic_jsonl(ROOT/'deliverables/candidates_in_progress.jsonl',rows)
 dump(ROOT/'deliverables/rejected_or_review.json',list({r['window_id']:r for r in rejections}.values()))
 atomic_jsonl(ROOT/'deliverables/candidates_in_progress.jsonl',rows)
 report={'target':400,'accepted_candidates':len(rows),'counts':[{'dataset':d,'shots':n,'accepted':counts[d,n],'target':quota} for (d,n),quota in TARGET.items()],'source_works':len(works),'max_per_work':max(works.values(),default=0),'human_review_complete':False,'status':'building' if len(rows)<400 else 'quota_reached_pending_final_audit'}
 dump(ROOT/'progress.json',report)
 return report

def usage_report(paths=None, prior=None):
 prices=read(ROOT/'pricing.json');calls=[];total=collections.Counter();cost=0.;unknown=False
 previous={r['path']:r for r in (prior or {}).get('rows',[])}
 if paths is None:paths=list((ROOT/'source_screen').glob('*/*/calls/*/status.json'))+list((ROOT/'batches').glob('*/windows/*/calls/*/status.json'))
 for path in paths:
  item=read(path);usage=collections.Counter()
  for u in item.get('usage',item.get('known_usage',[])):
   if u:usage.update({k:v for k,v in u.items() if type(v) in (int,float)})
  inp,cache,write,out=(usage.get(k,0) for k in ['input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens'])
  valid=0<=cache+write<=inp and inp<=prices['max_input_tokens'] and write==0 and bool(usage)
  amount=((inp-cache)*prices['input_usd_per_million']+cache*prices['cached_input_usd_per_million']+out*prices['output_usd_per_million'])/1e6 if valid else None
  if amount is None:unknown=True
  else:cost+=amount
  total.update(usage);calls.append({'path':str(path),'status':item['status'],'usage':dict(usage),'standard_api_equivalent_usd':amount,'not_a_bill':True})
 previous.update({r['path']:r for r in calls});calls=list(previous.values());total=collections.Counter();cost=0.;unknown=False
 for r in calls:
  total.update(r['usage'])
  if r['standard_api_equivalent_usd'] is None:unknown=True
  else:cost+=r['standard_api_equivalent_usd']
 report={'calls':len(calls),'usage':dict(total),'total_tokens':total['input_tokens']+total['output_tokens'],'standard_api_equivalent_usd':None if unknown else cost,'known_subtotal_usd':cost,'unknown_or_inflight_usage':unknown,'pricing':prices,'includes_pilot_historical_calls':False,'rows':calls}
 dump(ROOT/'usage_cost.json',report);return report

def download_is_live():
 path=ROOT/'acquisition_state/coordinator.lock'
 if not path.exists():return False
 with path.open('a') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(f,fcntl.LOCK_UN);return False
  except BlockingIOError:return True

def run_campaign(args):
 lock=(ROOT/'campaign.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for turn in range(args.max_rounds):
  if (ROOT/'pause_after_batch').exists():return 'paused_at_batch_boundary'
  dump(ROOT/'runtime.json',{'status':'running','pid':os.getpid(),'host':socket.gethostname(),'slurm_job_id':os.environ.get('SLURM_JOB_ID'),'turn':turn,'api_workers':args.api_workers,'updated':time.time()})
  report=collect();usage_report()
  if report['accepted_candidates']==400:return 'quota_reached_pending_final_audit'
  run_cmd([sys.executable,str(ROOT/'preprocess/build_windows.py'),'--include-eight-alternatives'],ROOT/'preflight/build-windows-latest.log')
  chosen=choose_batch(args.batch_size)
  if chosen:
   number=1+max([int(p.name.split('_')[-1]) for p in (ROOT/'batches').iterdir() if p.is_dir() and p.name.startswith('batch_')]+[0]);out=ROOT/'batches'/f'batch_{number:04d}'
   inputs=ROOT/'preflight'/f'{out.name}-inputs.json';dump(inputs,[x['input_path'] for x in chosen])
   run_cmd([sys.executable,str(ROOT/'extraction/run_extraction.py'),'prepare','--out',str(out),'--input-list',str(inputs)],ROOT/'preflight'/f'{out.name}-prepare.log')
   run_cmd([sys.executable,str(ROOT/'extraction/run_extraction.py'),'run','--out',str(out),'--workers',str(args.api_workers)],ROOT/'preflight'/f'{out.name}-run.log',allowed=tuple(range(0,101)))
   run_cmd([sys.executable,str(ROOT/'extraction/run_extraction.py'),'summarize','--out',str(out),'--pricing',str(ROOT/'pricing.json')],ROOT/'preflight'/f'{out.name}-summary.log')
   report=collect();cost=usage_report();print(json.dumps({'batch':out.name,**report,'tokens_so_far':cost['total_tokens'],'api_equivalent_usd_so_far':cost['standard_api_equivalent_usd']}),flush=True)
   # Stop on transport failure rather than charging through a systemic service problem.
   bad=[p for p in (out/'windows').glob('*/calls/*/status.json') if read(p).get('status')=='failed']
   if len(bad)>=3:return 'service_failures_need_inspection'
   continue
  ready=list((ROOT/'prepared_sources').glob('*/*/ready.json'))
  pending_screen=[p for p in ready if not (ROOT/'source_screen'/p.parent.parent.name/p.parent.name/'status.json').exists()]
  if pending_screen:
   run_cmd([sys.executable,str(ROOT/'screening/screen_sources.py'),'--limit','12','--workers',str(args.api_workers)],ROOT/'preflight'/f'campaign-screen-{turn:04d}.log',allowed=(0,1));continue
  manifest=read(ROOT/'acquisition_manifest.json')
  pending_prepare=[r for r in manifest['videos'] if not (ROOT/'prepared_sources'/r['source']/r['video_id']/'status.json').exists()]
  if pending_prepare:
   run_cmd([sys.executable,str(ROOT/'preprocess/prepare_sources.py'),'--limit','12','--ffmpeg',str(FFDIR/'ffmpeg'),'--ffprobe',str(FFDIR/'ffprobe')],ROOT/'preflight'/f'campaign-prepare-{turn:04d}.log',allowed=(0,1));continue
  if download_is_live():
   dump(ROOT/'runtime.json',{'status':'waiting_live_downloader_lock','pid':os.getpid(),'updated':time.time()});time.sleep(30);continue
  return 'source_pool_exhausted_expand_needed'
 return 'bounded_round_limit_reached'

def main():
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['run','collect','usage']);p.add_argument('--batch-size',type=int,default=12);p.add_argument('--max-rounds',type=int,default=180);p.add_argument('--api-workers',type=int,choices=range(1,9),default=3);p.add_argument('--streaming',action='store_true');a=p.parse_args()
 if not os.environ.get('SLURM_JOB_ID'):raise RuntimeError('Use an existing compute allocation')
 if a.phase=='usage':print(json.dumps(usage_report()));return
 if a.phase=='collect':print(json.dumps(collect()));usage_report();return
 try:
  if a.streaming:
   from campaign_streaming import run_streaming
   status=run_streaming(a)
  else:status=run_campaign(a)
  dump(ROOT/'runtime.json',{'status':status,'pid':os.getpid(),'ended':time.time()});print(status,flush=True)
 except Exception as e:
  dump(ROOT/'runtime.json',{'status':'failed','pid':os.getpid(),'error':str(e),'ended':time.time()});raise
if __name__=='__main__':main()
