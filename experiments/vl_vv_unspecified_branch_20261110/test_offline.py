#!/usr/bin/env python3
"""Offline check of run_u_branch.py (no model call): a real case (#078 Wan2.2 of rerun v3) with a fake transport.
Checks: U1 runs once per shot with that shot's six keyframes and gets the shot's ledger unspecified entities; its gate
rejects a missing registered entity and an unknown ref; U2 is text-only and its gate rejects a within_shot suspect
with two shots and a check frame outside the suspect's shots; U3 attaches only the check frames and its gate rejects
evidence on an unattached frame; the built detection result passes the frozen review's loader and record checks,
with new objects as added entities n1... labelled unspecified and checklist item O1."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))
import run_u_branch as ub  # noqa: E402
import run_vl_vv_branch_review as rv  # noqa: E402

DEV = json.loads((EXP.parent / 'vl_vv_stronger_vv_recall_20261110/baseline_usage.json').read_text())
ROW = DEV['rows']['priority_078__wan22']
calls = []


def fake(folder, payload, images, timeout, *, prompt_path, schema, model, reasoning, collect_errors, stage, **kw):
    frames = [(r['shot_id'], r['frame_id']) for r in images]
    calls.append(dict(stage=stage, frames=frames, reasoning=reasoning))
    if stage.startswith('U1'):
        shot = payload['shot_id']
        assert len(frames) == 6 and {s for s, _ in frames} == {shot}, stage
        reg = [r['id'] for r in payload['REGISTERED_UNSPECIFIED']]
        good = dict(protocol=ub.P1, view='test view', objects=[
            dict(ref=r, name='reg', description='d', location='l', frames_visible=[0, 1], change_within_shot='none') for r in reg] + [
            dict(ref='new', name='cabinet', description='white cabinet', location='under TV', frames_visible=[0, 2],
                 change_within_shot='none')])
        if reg:
            bad = dict(good, objects=good['objects'][1:] + [dict(good['objects'][0], ref='ge9999')])
            errs = collect_errors(bad)[0]
            assert any('needs exactly one entry' in e for e in errs) and any('ref must be' in e for e in errs), errs
        out = good
    elif stage == 'U2':
        assert frames == [] and reasoning == 'medium'
        shots = [s['shot_id'] for s in payload['shots']]
        s0, s1 = shots[0], shots[-1]
        refs = {s['shot_id']: [o['ref'] for o in s['inventory']] for s in payload['shots']}
        good = dict(protocol=ub.P2, suspects=[
            dict(scope='within_shot', shots=[s0], kind='appears', objects=[dict(shot_id=s0, ref=refs[s0][-1])], what='w',
                 check_frames=[dict(shot_id=s0, frame_id=0), dict(shot_id=s0, frame_id=2)]),
            dict(scope='cross_shot', shots=[s0, s1], kind='changed', objects=[dict(shot_id=s0, ref=refs[s0][-1]),
                 dict(shot_id=s1, ref=refs[s1][-1])], what='c',
                 check_frames=[dict(shot_id=s0, frame_id=0), dict(shot_id=s1, frame_id=0)])])
        bad = json.loads(json.dumps(good))
        bad['suspects'][0]['shots'] = [s0, s1]
        bad['suspects'][1]['check_frames'][0]['shot_id'] = shots[1]
        errs = collect_errors(bad)[0]
        assert any('exactly one shot' in e for e in errs) and any('not a keyframe of a shot of this suspect' in e for e in errs), errs
        out = good
    else:
        assert reasoning == 'high' and 2 <= len(frames) <= 4
        scope = payload['SUSPECT']['scope']
        sub = 'presence_instability' if scope == 'within_shot' else 'object_identity'
        good = dict(protocol=ub.P3, verdict='real', reason='r', subcategory=sub, description='描述',
                    key_evidence=[dict(shot_id=s, frame_id=f, observation='o') for s, f in frames[:2]], confidence='medium')
        bad = dict(good, key_evidence=[dict(shot_id=frames[0][0], frame_id=5 if frames[0][1] != 5 else 4, observation='o'),
                                       good['key_evidence'][1]])
        errs = collect_errors(bad)[0]
        assert any('not attached' in e for e in errs), errs
        out = good
    errors, value = collect_errors(out)
    assert not errors, (stage, errors)
    return value, None, [], dict(rounds=[1], repair_rounds=0)


def main():
    ub.repair_loop.call_with_repair = fake
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = ub.context(ROW['case_dir'])
        shots = ub.common.shot_ids(ctx[2])
        inv = {s: ub.u1(tmp, ctx, s) for s in shots}
        sus = ub.u2(tmp, ctx, inv)
        ver = [ub.u3(tmp, ctx, inv, i, s) for i, s in enumerate(sus, 1)]
        path, n = ub.build_detection(tmp, ctx, Path(ROW['output_dir']) / 'vv_detection/result.json', inv, ver)
        detection = rv.load_detection(path, 'vv', ctx[2], chain='v6')
        added = [e for e in detection['entities'] if e['source'] == 'added_by_vv_detection']
        assert n == 2 and len(detection['issues']) == 2 and [a['entity_key'] for a in added] == ['n1', 'n2'], (n, added)
        assert all(a['label'] == 'unspecified' for a in added)
        assert all(i['v_v_detail']['checklist_items'] == ['O1'] for i in detection['issues'])
        print('U1 calls', sum(c['stage'].startswith('U1') for c in calls), 'shots', len(shots), '| U2 calls',
              sum(c['stage'] == 'U2' for c in calls), '| U3 calls', sum(c['stage'].startswith('U3') for c in calls))
        print('issues', [(i['issue_id'], i['scope'], i['subcategory'], [r['entity_key'] for r in i['entity_refs']]) for i in detection['issues']])
        print('OFFLINE CHECK PASSED')
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    main()
