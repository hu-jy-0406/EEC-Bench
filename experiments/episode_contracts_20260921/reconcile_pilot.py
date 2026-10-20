"""Re-adopt the earliest structurally valid draft after fixing ambiguity-only rejection."""
import copy, json, shutil, time
import run
run.io.safe_compute();run.DISABLED=run.io.disabled_skills_config()
eid='74Od5-Fmf60_s00006_n4_clean_v2';folder=run.HERE/'episodes'/eid
src=run.read(folder/'input.json');initial=run.read(folder/'calls/draft_1/response.json')
error=run.read(folder/'calls/draft_1/validation.json')['error']
assert error.startswith('Unresolved semantics:')
run.validate(initial,src)
archive=folder/'ambiguity_validation_recovery';archive.mkdir(exist_ok=True)
for n in ['draft.json','review.json','final.json','status.json']:
 if not (archive/n).exists():shutil.copy2(folder/n,archive/n)
payload=copy.deepcopy(src);payload['proposal']=initial
for attempt in range(2,5):
 dest=folder/'calls'/f'review_{attempt}'
 try:
  raw=run.read(dest/'response.json') if (dest/'response.json').exists() else run.call(dest,payload,'review',feedback='The original first draft was rejected by a LOCAL validator solely for honestly recorded source ambiguities. That incorrect mechanical gate is removed. Audit this earliest valid draft normally; do not force ambiguous source text into a more specific physical interpretation to eliminate ambiguity notes. Preserve the source semantics.')
  final=run.validate(run.apply_review(initial,raw),src)
  run.dump(dest/'validation.json',dict(status='pass'));break
 except Exception as ex:
  run.dump(dest/'validation.json',dict(status='failed',error=str(ex)))
else:raise RuntimeError('Corrected pilot review did not validate')
run.dump(folder/'draft.json',initial);run.dump(folder/'review.json',raw);run.dump(folder/'final.json',final)
run.dump(folder/'reconciliation.json',dict(reason='Earliest draft passes corrected mechanical validation; source ambiguity must not trigger source strengthening',original_rejected_draft='calls/draft_1/response.json',selected_review=str(dest.relative_to(folder)),historical_stage_files=str(archive),new_review=True,completed=time.time()))
run.dump(folder/'status.json',dict(episode_id=eid,status='success',claims=len(final['claims']),entities=len(final['entities']),reconciled=True))
print(json.dumps(dict(status='success',episode_id=eid,claims=len(final['claims']),unresolved=final['unresolved'])))
