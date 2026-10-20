#!/usr/bin/env python3
"""Serialize validated source-construction updates at completed batch boundaries."""
import argparse,fcntl,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if not os.environ.get('SLURM_JOB_ID'):raise RuntimeError('Existing compute allocation required')
p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group();group.add_argument('--resume-validated-seek',action='store_true');group.add_argument('--resume-validated-eight',action='store_true');args=p.parse_args()
update=args.resume_validated_seek or args.resume_validated_eight
print(json.dumps({'status':'waiting_previous_coordinator','validated_update':bool(update)}),flush=True)
transition=(ROOT/'continuation.lock').open('a');fcntl.flock(transition,fcntl.LOCK_EX)
with (ROOT/'campaign.lock').open('a') as handle:
 fcntl.flock(handle,fcntl.LOCK_EX)
 state=json.loads((ROOT/'runtime.json').read_text())
 for _ in range(50):
  if state['status'] not in ('running','waiting_live_downloader_lock'):break
  time.sleep(.1);state=json.loads((ROOT/'runtime.json').read_text())
 expected='paused_at_batch_boundary' if update else 'bounded_round_limit_reached'
 if state['status']!=expected:
  print(json.dumps({'status':'not_started','reason':'previous campaign needs inspection','expected':expected,'previous_campaign':state}),flush=True);sys.exit(2)
 if update:
  marker=ROOT/'pause_after_batch';request=json.loads(marker.read_text())
  expected_reason='validated_source_eight_alternatives_reload' if args.resume_validated_eight else 'validated_source_clip_accurate_seek_reload'
  assert request['reason']==expected_reason
  assert hashlib.sha256((ROOT/'campaign.py').read_bytes()).hexdigest()==request['campaign_sha256']
  for relative,digest in request.get('additional_code_sha256',{}).items():assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest
  seen=set()
  for relative in ['preflight/fast-seek/audit.json','preflight/fast-seek-extra/audit.json']:
   audit=json.loads((ROOT/relative).read_text());assert audit['status']=='pass' and audit['completed_cases']==audit['expected_cases']
   for record in audit['records']:
    assert record['identical_frame_sequence'];seen.add(record['source_codec'])
  assert seen=={'h264','av1','vp9'}
  assert json.loads((ROOT/'preflight/fast-seek-render-smoke/audit.json').read_text())['status']=='pass'
  if args.resume_validated_eight:
   audit=json.loads((ROOT/'preflight/eight-alternatives-validation.json').read_text())
   assert audit['status']=='pass' and audit['final_candidate_overlap_count']==0
   assert audit['source_work_quota_preserved'] and audit['ad_exclusion_preserved'] and audit['original_frame_times_preserved']
  marker.unlink()
 fcntl.flock(handle,fcntl.LOCK_UN)
print(json.dumps({'status':'continuing','started':time.time(),'previous':state['status'],'validated_seek_reload':args.resume_validated_seek,'validated_eight_reload':args.resume_validated_eight}),flush=True)
sys.exit(subprocess.call([sys.executable,'-u',str(ROOT/'campaign.py'),'run','--batch-size','12','--max-rounds','180']))
