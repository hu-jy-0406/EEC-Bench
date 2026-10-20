"""Compare all final identity/scoring units by entity membership, not group IDs."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;R=ROOT/'sign_transport_fix';BASE=ROOT.parent/'temporal_v2_study234_revised_20260920'
read=lambda p:json.loads(p.read_text())

def group_map(pair):
    return {g['group_id']:tuple(sorted(g['a_ids']+g['b_ids'])) for g in read(pair/'matching.json')['groups']}

def units(result,kind,groups=None):
    rows={}
    for u in result[kind]['units']:
        key=tuple(sorted(u['entity_ids'])) if 'entity_ids' in u else tuple(sorted(groups[g] for g in u['endpoint_groups']))
        rows[key]=u['status']
    return rows

def diff(a,b):
    return [dict(entity_members=k,old=a.get(k),new=b.get(k)) for k in sorted(a.keys()|b.keys()) if a.get(k)!=b.get(k)]

def audit(name):
    dst=R/name;src=BASE/name;rows={};known=True
    assert read(dst/'downstream_status.json')['status']=='success'
    for sid in ('shot1','shot2','shot3'):
        a=read(src/'within'/sid/'results.json');b=read(dst/'within'/sid/'results.json')
        rows[sid]=dict(scores={k:b[k]['summary'] for k in ('presence','spatial')},
                       unit_differences={k:diff(units(a,k),units(b,k)) for k in ('presence','spatial')})
        known &= all({k for k,v in units(a,t).items() if v=='conflict'}=={k for k,v in units(b,t).items() if v=='conflict'} for t in ('presence','spatial'))
    ap=src/'pairs/pair_000';bp=dst/'pairs/pair_000';am=group_map(ap);bm=group_map(bp)
    a=read(ap/'boundary/results.json');b=read(bp/'boundary/results.json')
    boundary=dict(scores={k:b[k]['summary'] for k in ('presence','spatial')},
                  unit_differences={k:diff(units(a,k,am),units(b,k,bm)) for k in ('presence','spatial')})
    for kind in ('presence','spatial'):
        aa={k for k,v in units(a,kind,am).items() if v=='conflict'}
        bb={k for k,v in units(b,kind,bm).items() if v=='conflict'}
        boundary[kind+'_confirmed_anomalies_preserved']=aa==bb
        known &= aa==bb
    ai={tuple(sorted(g['a_ids']+g['b_ids'])):g['identity'] for g in read(ap/'matching.json')['groups']}
    bi={tuple(sorted(g['a_ids']+g['b_ids'])):g['identity'] for g in read(bp/'matching.json')['groups']}
    # Initial anchor choices and final support choices are explicit, audited outcomes.
    anchors={}
    for label,p in [('old',ap),('new',bp)]:
        m=read(p/'matching_initial.json');gm={g['group_id']:g for g in m['groups']}
        anchors[label]=[dict(entity_members=sorted(gm[g]['a_ids']+gm[g]['b_ids']),reason=gm[g]['anchor_reason']) for g in m['structural_anchor_group_ids']]
    result=dict(study=name,within=rows,boundary=boundary,identity_differences=diff(ai,bi),
                confirmed_identity_matches_preserved={k for k,v in ai.items() if v=='matched'}=={k for k,v in bi.items() if v=='matched'},anchors=anchors,
                confirmed_anomaly_sets_preserved=bool(known),
                scope='Fresh CPU/API downstream replay from frozen detector/Pi3X/Boxer/raw RoMa outputs; not a fresh GPU frontend run')
    (dst/'quality_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result

if __name__=='__main__':
    rows=[audit(n) for n in ('study2','study3','study4')]
    (ROOT/'quality_summary.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([dict(study=r['study'],confirmed_anomalies_preserved=r['confirmed_anomaly_sets_preserved'],identity_differences=len(r['identity_differences']),
                           boundary_differences={k:len(v) for k,v in r['boundary']['unit_differences'].items()}) for r in rows],indent=2))
