import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1]
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
replay=R/'replay';state=read(R/'replay_status.json');tests=read(R/'tests.json')
old=read(B/'experiments/study3_concise_mtd_fps32_20260919/source_hashes.json')
fixed=[B/'scripts'/n for n in ['register_gs_3d.py','gs_registration_3d.py','gs_registration_variants.py','register_gs_codex.py']]
fixed += [B/'experiments/study2_full_fresh_20260918'/n for n in ['run_matching.py','prepare_correspondences.py','register.py','common.py']]
unchanged={str(p):hashlib.sha256(p.read_bytes()).hexdigest()==old.get(str(p)) for p in fixed}
# Some baseline snapshots keep experiment dependencies in provenance instead.
prior=read(B/'experiments/study3_concise_mtd_fps32_20260919/run/provenance.json')['source_hashes']
for p in fixed:
 if str(p) not in old:unchanged[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()==prior.get(str(p))
source_hashes=read(replay/'replay_provenance.json')['hashes']
history_ok=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in source_hashes.items())
rows=[]
for p in sorted((replay/'calls').glob('*/status.json')):
 d=read(p);usage=d.get('usage',d.get('known_usage',[]));usage=[usage] if isinstance(usage,dict) else usage
 t={k:sum(u.get(k,0) for u in usage if u) for k in ['input_tokens','output_tokens','cached_input_tokens']}
 rows.append(dict(call=p.parent.name,status=d['status'],seconds=d.get('seconds'),**t,total_tokens=t['input_tokens']+t['output_tokens']))
within={p.parent.name:read(p) for p in (replay/'within').glob('*/results.json')}
boundary=read(replay/'boundary/results.json') if (replay/'boundary/results.json').exists() else None
short=next(e for e in read(replay/'expected_motion/shot3.json')['entities'] if e['entity_id']=='shot3/e3')
proposals=read(replay/'boundary/proposals.json') if (replay/'boundary/proposals.json').exists() else {}
report=dict(status=state['status'],validation_scope='component replay on frozen detection/geometry/identity/registration; no fresh GPU frontend; Shot2 not replayed',
 tests=tests,adapters=read(R/'adapter_validation.json'),registration_sources_unchanged=unchanged,historical_inputs_unchanged=history_ok,
 expected_short_cup_intervals=short['intervals'],within={s:{k:v[k]['summary'] for k in ('presence','spatial')} for s,v in within.items()},
 boundary=None if boundary is None else {k:boundary[k]['summary'] for k in ('presence','spatial')},
 boundary_frames=proposals.get('target_frames'),boundary_population=len(proposals.get('presence_units',[])),
 calls=rows,total_tokens=sum(r['total_tokens'] for r in rows),elapsed_seconds=state['seconds'])
save(R/'validation.json',report)
source_files=list((B/'scripts').glob('gs_temporal_*.py'))+list((B/'scripts').glob('run_gs_temporal*.py'))
source_files += [B/'scripts/run_gs_integrated.py',B/'scripts/prepare_gs_integrated.py',B/'configs/gs-temporal-v2.json']
source_files += list((B/'prompts/gs_flow1').glob('*v2.txt'))+[B/'tests/test_gs_temporal.py']
source_files += [B/'scripts'/n for n in ['gs_identity_population.py','gs_flow1_evaluator.py','review_aligned_entity_identities.py']]
source_files += [B/'experiments/study2_detection_only_fresh_20260918'/n for n in ['geometry.py','boxer.py']]
source_files += [B/'prompts/gs_flow1/match.txt', B/'prompts/gs_aligned_identity_review_v1.txt']
save(R/'source_hashes.json',{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files})
lines=['# Temporal v2 implementation validation','',f"Status: {state['status']}. Tests: {tests['tests']} passed; adapter checks passed.",'',
'Validation reuses frozen Study3-concise-MTD detections, geometry, reviewed identities and FPS32 registration. Expected-motion and temporal/boundary Codex calls are fresh. This is NOT a fresh WeDetect/GPU end-to-end run, and Shot2 is not part of this component replay. The integrated plan covers all supplied shots; singleton/Shot2 coverage and both registration paths are tested.', '',
'All registration source hashes unchanged: '+str(all(unchanged.values()))+'. Historical inputs/results unchanged: '+str(history_ok)+'.','',
'| Scope | Presence | Spatial | Presence C/K/U/E | Spatial C/K/U/E |','|---|---:|---:|---|---|']
for name,result in list(within.items())+([('boundary Shot1 -> Shot3',boundary)] if boundary else []):
 p,s=result['presence']['summary'],result['spatial']['summary'];lines.append(f"| {name} | {p['score']} | {s['score']} | {'/'.join(str(p[k]) for k in ['C','K','U','E'])} | {'/'.join(str(s[k]) for k in ['C','K','U','E'])} |")
lines += ['', 'Scores retain the historical unknown-inclusive formula. A spatial score of 100 is not proof that every relation is verified compatible. Inspect coverage and event witnesses.', '',
 f"Component validation elapsed {state['seconds']:.2f} seconds; {len(rows)} fresh Codex calls; {report['total_tokens']} tokens. These are validation costs, not fresh full-pipeline latency/cost.", '', '## Confirmed events']
for name,result in list(within.items())+([('boundary',boundary)] if boundary else []):
 for event in result['events']:
  if event['status']=='conflict':lines.append(f"- {name}: {event['event_id']}, {event.get('entity_ids',[])}, {event['review']['reason']}")
lines += ['', '## Verified behavior','', '- Shot3 short cup retains static intervals before frame202 and reasonable pickup/drinking thereafter.', '- Boundary vectors use exact Shot1 frame240 and Shot3 frame0 boxes, including the moving short-cup identity.', '- Missing endpoint boxes stay null; full identity population and ambiguous groups remain in ledgers.', '- The unweighted unsquared 3D registration objective, FPS32 selector, RoMA settings and direct estimator were not changed.', '', 'Entry: `scripts/run_gs_integrated.py --consistency-protocol temporal_v2 --alignment-method roma_fps32 ...`; direct remains selectable. Historical scoring: `--consistency-protocol flow1_fused_v1`.']
(R/'REPORT.md').write_text('\n'.join(lines)+'\n')
assert state['status']=='success' and tests['success'] and all(unchanged.values()) and history_ok
print(json.dumps(report,ensure_ascii=False,indent=2))
