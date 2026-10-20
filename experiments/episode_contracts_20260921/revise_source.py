"""Apply an explicitly authorized prompt correction and synchronize current copies."""
import copy, csv, hashlib, html, io, json, shutil, time
from pathlib import Path
import run

def replace_record(path,eid,fn):
    lines=path.read_text().splitlines(keepends=True); found=0
    for i,line in enumerate(lines):
        row=json.loads(line)
        if row['episode_id']==eid:
            row=fn(row);lines[i]=json.dumps(row,ensure_ascii=False)+'\n';found+=1
    if found:
        assert found==1
        tmp=path.with_suffix(path.suffix+'.revise_tmp');tmp.write_text(''.join(lines));tmp.replace(path)
    return found

def main():
    run.io.safe_compute()
    eid='5IykypzJT80_s00027_n6_clean_v2';sid='Shot2'
    old='The pistol stays at her temple without firing throughout this five-second shot.'
    new='Once its muzzle reaches her right temple, the pistol stays there for the rest of this five-second shot. The pistol does not fire at any point.'
    folder=run.HERE/'episodes'/eid;archive=folder/'revisions'/'pre_source_v1'
    assert not archive.exists(), 'Source revision already applied or interrupted; inspect before retrying'
    assert (folder/'final.json').exists()
    assert all(run.read(p)['status']!='running' for p in (folder/'calls').glob('*/status.json'))
    src=run.read(folder/'input.json');text=next(s['prompt'] for s in src['shots'] if s['shot_id']==sid)
    assert text.count(old)==1;revised=text.replace(old,new)
    row=next(json.loads(line) for line in run.SOURCE.read_text().splitlines() if json.loads(line)['episode_id']==eid)
    shot=next(s for s in row['shots'] if s['shot_id']==sid);assert shot['generation_prompt_en']==text
    extraction_path=Path(row['provenance']['extraction']);extraction=run.read(extraction_path)
    assert next(s for s in extraction['shots'] if s['shot_id']==sid)['generation_prompt_en']==text
    archive.mkdir(parents=True)
    for name in ['input.json','draft.json','review.json','final.json','status.json']:
        shutil.copy2(folder/name,archive/name)
    shutil.copy2(extraction_path,archive/'source_extraction.json')
    shutil.copy2(run.HERE/'manifest.json',archive/'manifest.json')
    for s in extraction['shots']:
        if s['shot_id']==sid:s['generation_prompt_en']=revised
    run.dump(extraction_path,extraction);extraction_hash=run.sha(extraction_path)
    def update(r):
        for s in r['shots']:
            if s['shot_id']==sid:
                assert s['generation_prompt_en']==text;s['generation_prompt_en']=revised
        r['provenance']['extraction_sha256']=extraction_hash
        return r
    assert replace_record(run.SOURCE,eid,update)==1
    assert replace_record(run.SOURCE.parent/'candidates_in_progress.jsonl',eid,update)==1
    for p,escaping in [(Path(row['provenance']['review']),False),(run.SOURCE.parent/'review_400.html',True)]:
        content=p.read_text();a,b=(html.escape(text),html.escape(revised)) if escaping else (text,revised)
        assert a in content;p.write_text(content.replace(a,b))
    priority=run.QUEUE.parent
    canonical_line=next(line for line in run.SOURCE.read_text().splitlines(keepends=True) if json.loads(line)['episode_id']==eid)
    changed=[]
    for name in ['core_100','priority_200','stage2_additional_100','stage3_remaining_200','generation_queue_400']:
        p=priority/(name+'.jsonl');lines=p.read_text().splitlines(keepends=True)
        for i,line in enumerate(lines):
            if json.loads(line)['episode_id']==eid:lines[i]=canonical_line;changed.append(name)
        p.write_text(''.join(lines))
    record_hash=hashlib.sha256(canonical_line.encode()).hexdigest()
    p=priority/'ranking.jsonl'
    replace_record(p,eid,lambda r:{**r,'original_record_sha256':record_hash})
    p=priority/'ranking.csv'
    with p.open(newline='') as f: reader=csv.DictReader(f);fieldnames=reader.fieldnames;ranking=list(reader)
    if 'original_record_sha256' in fieldnames:
        for r in ranking:
            if r['episode_id']==eid:r['original_record_sha256']=record_hash
        with p.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fieldnames);writer.writeheader();writer.writerows(ranking)
    p=priority/'review.html';content=p.read_text();content=content.replace(html.escape(text),html.escape(revised));p.write_text(content)
    m=run.read(priority/'selection_manifest.json');m['source_sha256']=run.sha(run.SOURCE);m['record_hashes'][eid]=record_hash
    for name in m['files']:m['files'][name]['sha256']=run.sha(priority/(name+'.jsonl'))
    run.dump(priority/'selection_manifest.json',m)
    audit=run.read(priority/'audit.json');audit['source_sha256']=run.sha(run.SOURCE)
    for name,r in audit['outputs'].items():r['sha256']=run.sha(priority/(name+'.jsonl'))
    audit['checks']['canonical_source_unchanged']=False
    run.dump(priority/'audit.json',audit)
    for s in src['shots']:
        if s['shot_id']==sid:s['prompt']=revised
    src['source_units']=run.units(run.facts(src));run.dump(folder/'input.json',src)
    manifest=run.read(run.HERE/'manifest.json');manifest['source_sha256']=run.sha(run.SOURCE);manifest['queue_sha256']=run.sha(run.QUEUE)
    for j in manifest['jobs']:
        if j['episode_id']==eid:j['input_sha256']=run.sha(folder/'input.json')
    run.dump(run.HERE/'manifest.json',manifest)
    # Withdraw the superseded contract before a fresh independent draft/review.
    for name in ['draft.json','review.json','final.json']:(folder/name).unlink()
    run.dump(folder/'status.json',dict(episode_id=eid,status='source_revised_pending_rebuild'))
    run.dump(run.HERE/'source_revision.json',dict(episode_ids=[eid],completed=time.time(),source_sha256=manifest['source_sha256'],queue_sha256=manifest['queue_sha256']))
    print(json.dumps(dict(status='source_updated',episode_id=eid,shot_id=sid,updated_queue_files=changed)))
if __name__=='__main__':main()
