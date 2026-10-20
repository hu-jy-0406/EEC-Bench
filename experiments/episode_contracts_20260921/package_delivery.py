"""Freeze compiler sources and package audited text-only deliverables."""
import hashlib,json,shutil,zipfile
from pathlib import Path
import run
run.io.safe_compute();here=run.HERE;dest=here/'deliverables'
complete=run.read(here/'completion.json');assert complete['status']=='complete'
assert run.read(here/'independent_validation.json')['status']=='pass'
u=run.read(here/'usage_cost.json');assert all(r['status']!='running' for r in u['rows'])
run.dump(here/'usage_summary.json',{k:v for k,v in u.items() if k!='rows'})
source_names=['run.py','rules.txt','review.txt','base.txt','draft.schema.json','review.schema.json','audit_delivery.py','make_report.py','rebuild_episode.py','revise_source.py','revise_source_globals.py','package_delivery.py','METHOD.md','pricing.json']
snapshot=here/'final_source_snapshot';snapshot.mkdir(exist_ok=True);source_hashes={}
for name in source_names:
 shutil.copy2(here/name,snapshot/name);source_hashes[name]=run.sha(snapshot/name)
spec=run.ROOT/'EECBench/docs/episode-schedule-claims-v1.md';shutil.copy2(spec,snapshot/spec.name);source_hashes[spec.name]=run.sha(snapshot/spec.name)
run.dump(snapshot/'sha256.json',source_hashes)
files=[p for p in sorted(dest.rglob('*')) if p.is_file() and p.name!='sha256.json']
run.dump(dest/'sha256.json',{str(p.relative_to(dest)):run.sha(p) for p in files})
archive=here/'contracts_400_bundle.zip';tmp=archive.with_suffix('.tmp')
with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in files+[dest/'sha256.json']:z.write(p,str(p.relative_to(here)))
 for name in ['REPORT.md','METHOD.md','independent_validation.json','usage_summary.json','pricing.json','source_revision.json','completion.json']:z.write(here/name,name)
 z.write(spec,'episode-schedule-claims-v1.md')
with zipfile.ZipFile(tmp) as z:
 assert z.testzip() is None
 entries=len(z.namelist())
tmp.replace(archive);digest=run.sha(archive)
(archive.with_suffix('.zip.sha256')).write_text(digest+'  '+archive.name+'\n')
result=dict(status='pass',bundle=str(archive),bytes=archive.stat().st_size,entries=entries,sha256=digest,all_deliverable_hashes_recorded=True)
run.dump(here/'package_validation.json',result);print(json.dumps(result))
