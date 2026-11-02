"""Camera fields fed by a multi-shot v1 claim: a between-shot camera requirement by provenance, not by wording."""
import json
from pathlib import Path
R = Path(__file__).resolve().parents[2]
V2 = R / 'episode_contracts_v2_20261029/deliverables/episodes'
V1 = R / 'episode_contracts_20260921/deliverables/episodes'
C = R / 'contract_cleanup_20261031/episodes'
OUT = Path(__file__).resolve().parents[1] / 'camera_multishot_claims.jsonl'
rows = []
for folder in sorted(V2.iterdir()):
    eid = folder.name
    cleaned = C / eid / 'contract_with_evidence.json'
    c = json.loads((cleaned if cleaned.exists() else folder / 'contract_with_evidence.json').read_text())
    claims = {q['claim_id']: q for q in json.loads((V1 / eid / 'contract.json').read_text())['claims']}
    for s in c['shots']:
        for field in ('camera_view', 'camera_movement'):
            v = s['shot_description'][field]
            if not v:
                continue
            for cid in v.get('source_claim_ids', []):
                q = claims.get(cid)
                if q and len(q['shot_ids']) >= 2:
                    rows.append(dict(episode_id=eid, source='cleaned' if cleaned.exists() else 'v2', shot_id=s['shot_id'], field=field,
                                     value=v['value'], v1_claim=cid, v1_shots=q['shot_ids'], v1_expected=q['expected'],
                                     entities=q['entity_ids']))
OUT.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
print(len(rows))
for r in rows:
    print(r['source'], r['episode_id'], r['shot_id'], r['field'], r['v1_shots'], '|', r['value'][:90], '| v1:', r['v1_expected'][:110])
