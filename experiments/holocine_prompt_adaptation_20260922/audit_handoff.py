#!/usr/bin/env python3
"""Check exclusive queue handoff, with no duplicate original API request."""
from run import HERE,read,dump,io
io.safe_compute()
ids=read(HERE/'parallel_takeover.json')['episodes']
assert len(ids)==len(set(ids))
for eid in ids:
    calls=HERE/'episodes'/eid/'calls'
    reservation=calls/'draft_1'
    assert read(reservation/'status.json')['not_an_api_call'] is True
    assert not any((reservation/x).exists() for x in ['request.json','events.jsonl','response.json','prompt.txt'])
    assert all(p.name=='draft_1' or p.name.startswith('parallel_') for p in calls.iterdir() if p.is_dir())
result=dict(status='pass',exclusively_transferred_episodes=len(ids),duplicate_original_api_requests=0,reservations_excluded_from_usage=True)
dump(HERE/'handoff_audit.json',result)
print(result)
