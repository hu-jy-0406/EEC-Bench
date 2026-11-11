#!/usr/bin/env python3
"""Selected appearance scoring: original v3 model calls, local severity cap/RMS.

prepare/score delegate verbatim to the historical compact-v3 entrypoint.
report only reads existing v3 results; no VLM verifier or extra model output.
"""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import sys

import gs_entity_appearance_minimal as minimal
import gs_entity_appearance_compact as compact

PROTOCOL = 'entity_appearance_scoring_v6'
MODEL_PROTOCOL = 'entity_appearance_compact_v3'


def entity_score(scores):
    values = [v for v in scores if v is not None]
    if any(type(v) not in (int, float) or v not in (0,25,50,75,100) for v in values):
        raise ValueError('Expected original v3 attribute scores')
    if not values:
        return dict(score=None, attribute_mean=None, severe_cap=None)
    mean = sum(values) / len(values)
    cap = min(values) if min(values) <= 25 else None
    return dict(score=min(mean, cap) if cap is not None else mean,
                attribute_mean=mean, severe_cap=cap)


def aggregate(rows):
    c = [r['codex_score'] for r in rows if r['codex_score'] is not None]
    d = [r['dino_score'] for r in rows if r['dino_score'] is not None]
    return dict(entities=len(rows), scored_entities=len(c), unscored_entities=len(rows)-len(c),
        codex_score=100-math.sqrt(sum((100-v)**2 for v in c)/len(c)) if c else None,
        codex_entity_mean=sum(c)/len(c) if c else None,
        dino_score=sum(d)/len(d) if d else None, dino_scored_entities=len(d),
        unknown_dimensions=sum(r.get('unknown_dimensions',4) for r in rows))


def report(runs, out):
    from PIL import Image
    read, sha, dump = compact.read, compact.sha, compact.dump
    out = out.resolve(); out.mkdir(parents=True, exist_ok=False)
    studies=[]; all_usage=[]; all_rows=[]; sources={}; pixels=0; original_images={}
    for path in (Path(__file__).resolve(),Path(minimal.__file__).resolve(),Path(compact.__file__).resolve(),
                 compact.PROMPT,minimal.BASE):
        sources[str(path)]=sha(path)
    for run in runs:
        compact.bind_dino(run)
        m=compact.verify(run)
        if m['protocol'] != MODEL_PROTOCOL:
            raise ValueError('Requires unmodified compact-v3 model outputs, not a mixed protocol')
        sources[str(run/'manifest.json')]=sha(run/'manifest.json')
        rows=[]; usage=[]
        for e in m['entities']:
            eid=e['global_entity_id']; f=run/'entities'/eid
            payload=read(f/'input.json'); c=read(f/'codex.json'); d=read(f/'dino.json')
            for p in (f/'input.json',f/'codex.json',f/'dino.json',f/'wire.json',f/'images.json',f/'sheet_audit.json'):
                sources[str(p)]=sha(p)
            if c['status']=='failed':raise ValueError('Incomplete model population')
            if c['status']=='success':
                call=run/'calls'/eid
                raw=read(call/'response.json')
                expanded=compact.expand(raw,payload)
                if expanded!=c['result'] or expanded['score']!=c['score']:
                    raise ValueError('Raw v3 result mismatch')
                state=read(call/'status.json')
                if state['status']!='success':raise ValueError('Unsuccessful raw call')
                usage+=state['usage']
                sources[str(call/'response.json')]=sha(call/'response.json')
                if read(call/'output.schema.json')!=compact.SCHEMA:
                    raise ValueError('Changed model schema')
                expected=compact.PROMPT.read_text()+'\nINPUT:\n'+json.dumps(read(f/'wire.json'),ensure_ascii=False,separators=(',',':'))
                if (call/'prompt.txt').read_text()!=expected:raise ValueError('Changed v3 prompt')
                actual=read(call/'execution_override.json')['actual_command']
                if actual[actual.index('--model')+1]!='gpt-6-astra' or 'model_reasoning_effort="medium"' not in actual:
                    raise ValueError('Changed model/reasoning')
            else:
                if c['status']!='not_assessable' or len(payload['appearances'])>=2 or c['score'] is not None:
                    raise ValueError('Invalid unscored entity')
            scores=[c.get('result',{}).get('dimensions',{}).get(k,{}).get('score') for k in compact.base.DIMS]
            adjusted=entity_score(scores)
            if adjusted['attribute_mean']!=c['score']:raise ValueError('Original mean changed')
            images=read(f/'images.json'); mapping=read(f/'sheet_audit.json')
            if [a['appearance_id'] for a in mapping]!=[a['appearance_id'] for a in payload['appearances']]:raise ValueError('Wrong appearance coverage')
            for a in mapping:
                im=images[a['sheet_index']]
                if sha(im['path'])!=im['sha256'] or sha(a['crop_path'])!=a['crop_sha256']:raise ValueError('Changed image')
                with Image.open(im['path']) as sheet,Image.open(a['crop_path']) as crop:
                    if sheet.crop(a['rect']).tobytes()!=crop.convert('RGB').tobytes():raise ValueError('Changed crop pixels')
                pixels+=1
            for a in payload['appearances']:
                if a['original_frame'] not in original_images:original_images[a['original_frame']]=sha(a['original_frame'])
                if original_images[a['original_frame']]!=a['original_frame_sha256']:raise ValueError('Changed original')
            rows.append(dict(study=run.name,global_entity_id=eid,name=e['name'],observed_shot_ids=e['observed_shot_ids'],
                appearances=e['appearances'],attribute_scores=scores,raw_v3_mean=c['score'],severe_cap=adjusted['severe_cap'],
                codex_score=adjusted['score'],dino_score=d['score'],unknown_dimensions=sum(s is None for s in scores),
                reason=c.get('result',{}).get('reason',c.get('reason','')),limitations=c.get('result',{}).get('limitations','')))
        counter=Counter()
        for item in usage:counter.update(item)
        summary=dict(study=run.name,source=str(run),protocol=PROTOCOL,model_protocol=MODEL_PROTOCOL,
            all_entities=aggregate(rows),multi_shot_entities=aggregate([r for r in rows if len(r['observed_shot_ids'])>1]),
            single_shot_entities=aggregate([r for r in rows if len(r['observed_shot_ids'])==1]),entities=rows,
            reused_model_usage=dict(counter),reused_total_tokens=counter['input_tokens']+counter['output_tokens'],
            reused_standard_api_equivalent_usd=compact.cost(usage),new_model_calls=0,new_tokens=0,new_api_usd=0)
        dump(out/run.name/'summary.json',summary)
        studies.append(summary);all_rows+=rows;all_usage+=usage
    counts=Counter()
    for item in all_usage:counts.update(item)
    result=dict(protocol=PROTOCOL,model_protocol=MODEL_PROTOCOL,studies=studies,
        new_model_calls=0,new_tokens=0,new_api_usd=0,
        reused_model_usage=dict(counts),reused_total_tokens=counts['input_tokens']+counts['output_tokens'],
        reused_standard_api_equivalent_usd=compact.cost(all_usage),
        cost_note='Historical v3 usage reused, not a fresh cost measurement or future billing guarantee.')
    dump(out/'results.json',result)
    dump(out/'manifest.json',dict(protocol=PROTOCOL,source_hashes=sources,original_images=original_images))
    dump(out/'audit.json',dict(passed=True,entities=len(all_rows),appearances_pixel_checked=pixels,
        original_images=len(original_images),all_original_v3_prompts_and_schemas_unchanged=True,
        no_new_model_calls=True,raw_scores_and_dino_unchanged=True,model='gpt-6-astra',reasoning='medium'))
    with (out/'entities.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(all_rows[0]));writer.writeheader();writer.writerows(all_rows)
    print(json.dumps({s['study']:s['all_entities'] for s in studies}),flush=True)
    return result


def main():
    if len(sys.argv)>1 and sys.argv[1] in ('prepare','score'):
        # Same CLI, identical prompt/schema/base-role, exact same one-call budget.
        return minimal.main()
    p=argparse.ArgumentParser()
    p.add_argument('phase',choices=['report']);p.add_argument('--runs',nargs='+',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    report([r.resolve() for r in a.runs],a.out)


if __name__=='__main__':main()
