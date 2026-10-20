"""Synchronize authorized global summaries with their existing shot content."""
import hashlib,html,json,shutil,time,csv
from pathlib import Path
import run
from revise_source import replace_record
UPDATES={
 '8TM2yB381fc_s00037_n4_clean_v2':"Four five-second shots preserve the boy's cautious emergence, a white-robed adult moving the porthole door toward its frame, the boy's pause at a column, and adults crossing the stair area.",
 'jS4vMlzOaTI_s00013_n8_clean_v2':"Eight five-second shots progress from detailed amusement displays to a brown-jacketed visitor exploring arcade aisles, pausing beside the cabinets, holding a small brass-colored disc and approaching a dark-screen cabinet."
}
def apply(eid,new):
 folder=run.HERE/'episodes'/eid;src=run.read(folder/'input.json');old=src['global_prompt'];archive=folder/'revisions/pre_source_v2'
 assert not archive.exists();assert (folder/'final.json').exists()
 assert all(run.read(p)['status']!='running' for p in (folder/'calls').glob('*/status.json'))
 row=next(json.loads(line) for line in run.SOURCE.read_text().splitlines() if json.loads(line)['episode_id']==eid)
 assert row['global_prompt']==old
 extraction_path=Path(row['provenance']['extraction']);extraction=run.read(extraction_path);assert extraction['generation_summary_en']==old
 archive.mkdir(parents=True)
 for name in ['input.json','draft.json','review.json','final.json','status.json']:shutil.copy2(folder/name,archive/name)
 shutil.copy2(extraction_path,archive/'source_extraction.json');shutil.copy2(run.HERE/'manifest.json',archive/'manifest.json')
 extraction['generation_summary_en']=new;run.dump(extraction_path,extraction);extraction_hash=run.sha(extraction_path)
 def update(r):
  assert r['global_prompt']==old;r['global_prompt']=new;r['provenance']['extraction_sha256']=extraction_hash;return r
 assert replace_record(run.SOURCE,eid,update)==1
 assert replace_record(run.SOURCE.parent/'candidates_in_progress.jsonl',eid,update)==1
 for p,escaped in [(Path(row['provenance']['review']),False),(run.SOURCE.parent/'review_400.html',True)]:
  a,b=(html.escape(old),html.escape(new)) if escaped else (old,new);content=p.read_text();assert a in content;p.write_text(content.replace(a,b))
 priority=run.QUEUE.parent;line=next(s for s in run.SOURCE.read_text().splitlines(keepends=True) if json.loads(s)['episode_id']==eid)
 record_hash=hashlib.sha256(line.encode()).hexdigest()
 for name in ['core_100','priority_200','stage2_additional_100','stage3_remaining_200','generation_queue_400']:
  p=priority/(name+'.jsonl');lines=p.read_text().splitlines(keepends=True)
  p.write_text(''.join(line if json.loads(s)['episode_id']==eid else s for s in lines))
 replace_record(priority/'ranking.jsonl',eid,lambda r:{**r,'original_record_sha256':record_hash})
 p=priority/'ranking.csv'
 with p.open(newline='') as f:reader=csv.DictReader(f);fields=reader.fieldnames;ranking=list(reader)
 if 'original_record_sha256' in fields:
  for r in ranking:
   if r['episode_id']==eid:r['original_record_sha256']=record_hash
  with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(ranking)
 p=priority/'review.html';p.write_text(p.read_text().replace(html.escape(old),html.escape(new)))
 m=run.read(priority/'selection_manifest.json');m['source_sha256']=run.sha(run.SOURCE);m['record_hashes'][eid]=record_hash;m['selection_order_frozen_after_source_edits']=True
 for name in m['files']:m['files'][name]['sha256']=run.sha(priority/(name+'.jsonl'))
 run.dump(priority/'selection_manifest.json',m)
 audit=run.read(priority/'audit.json');audit['source_sha256']=run.sha(run.SOURCE);audit['checks']['canonical_source_unchanged']=False
 for name,r in audit['outputs'].items():r['sha256']=run.sha(priority/(name+'.jsonl'))
 run.dump(priority/'audit.json',audit)
 src['global_prompt']=new;src['source_units']=run.units(run.facts(src));run.dump(folder/'input.json',src)
 m=run.read(run.HERE/'manifest.json');m['source_sha256']=run.sha(run.SOURCE);m['queue_sha256']=run.sha(run.QUEUE)
 for j in m['jobs']:
  if j['episode_id']==eid:j['input_sha256']=run.sha(folder/'input.json')
 run.dump(run.HERE/'manifest.json',m)
 for name in ['draft.json','review.json','final.json']:(folder/name).unlink()
 run.dump(folder/'status.json',dict(episode_id=eid,status='source_revised_pending_rebuild'))
 revision=run.read(run.HERE/'source_revision.json');revision['episode_ids']=list(dict.fromkeys(revision['episode_ids']+[eid]));revision.update(completed=time.time(),source_sha256=m['source_sha256'],queue_sha256=m['queue_sha256']);run.dump(run.HERE/'source_revision.json',revision)
 print(json.dumps(dict(status='source_updated',episode_id=eid,field='global_prompt')),flush=True)
if __name__=='__main__':
 run.io.safe_compute()
 for eid,text in UPDATES.items():apply(eid,text)
