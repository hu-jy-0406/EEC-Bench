#!/usr/bin/env python3
"""Summarize compact scores for fresh runs (no previous VLM evaluation needed)."""
import argparse
import json
from collections import Counter
from pathlib import Path
import gs_entity_appearance_compact as compact


def summarize(out):
    m=compact.verify(out);rows=[];usage=[];calls=[]
    for e in m['entities']:
        folder=out/'entities'/e['global_entity_id']
        c=compact.read(folder/'codex.json');d=compact.read(folder/'dino.json')
        if c['status']=='failed':raise ValueError('Incomplete successful population: '+e['global_entity_id'])
        if c['status']=='success':
            compact.base.validate_codex(c['result'],compact.read(folder/'input.json'))
            status=compact.read(out/'calls'/e['global_entity_id']/'status.json')
            if status['status']!='success':raise ValueError('Unsuccessful raw call')
            calls.append(status);usage+=status['usage']
        rows.append(dict(global_entity_id=e['global_entity_id'],name=e['name'],observed_shot_ids=e['observed_shot_ids'],appearances=e['appearances'],
                         codex_score=c['score'],dino_score=d['score'],reason=c.get('result',{}).get('reason',c.get('reason','')),
                         limitations=c.get('result',{}).get('limitations','')))
    def group(rs):
        g=dict(entities=len(rs),appearances=sum(r['appearances'] for r in rs))
        for metric in ('codex','dino'):
            vals=[r[metric+'_score'] for r in rs if r[metric+'_score'] is not None]
            g[metric]=dict(score=sum(vals)/len(vals) if vals else None,scored_entities=len(vals),unscored_entities=len(rs)-len(vals))
        return g
    u=Counter()
    for item in usage:u.update(item)
    result=dict(protocol=m['protocol'],all_entities=group(rows),multi_shot_entities=group([r for r in rows if len(r['observed_shot_ids'])>1]),
                single_shot_entities=group([r for r in rows if len(r['observed_shot_ids'])==1]),entities=rows,usage=dict(u),
                total_tokens=u['input_tokens']+u['output_tokens'],calls=len(calls),
                cost=dict(standard_api_equivalent_usd=compact.cost(usage),verified_date='2026-09-20',
                          source='https://developers.openai.com/api/docs/models/gpt-6-astra',not_invoice=True))
    compact.dump(out/'summary.json',result)
    lines=['# '+out.name+' appearance: '+m['protocol'],'','Codex 与 DINO 分别计算；有效实体等权。原始全局身份及 DINO 不变，所有 appearance crop 均参与。','',
           '| 实体 | 名称 | shots | Codex /100 | DINO | 解释 |','|---|---|---|---:|---:|---|']
    for r in rows:
        c='null' if r['codex_score'] is None else f'{r["codex_score"]:.4f}';d='null' if r['dino_score'] is None else f'{r["dino_score"]:.6f}'
        lines.append(f'| {r["global_entity_id"]} | {r["name"]} | {", ".join(r["observed_shot_ids"])} | {c} | {d} | {r["reason"].replace(chr(10)," ").replace("|","/")} |')
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='entities'},ensure_ascii=False))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runs',nargs='+',type=Path);a=p.parse_args()
    for out in a.runs:summarize(out.resolve())
