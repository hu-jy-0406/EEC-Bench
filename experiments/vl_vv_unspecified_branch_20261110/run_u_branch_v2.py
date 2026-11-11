#!/usr/bin/env python3
"""EXPERIMENT round 3 (owner, 2026-11-10: "再迭代一轮看看吧" ... "今晚11点之前把这个新分支调好"): anchors and wider U1.

Changes from round 2 (run_u_branch_v1.py, whose text follows): U1 is rerun with prompts/u1_inventory_v1.txt (also
things on registered or prompt-named objects, attached fixtures, edge and far-background objects; reasoning medium);
U2 attaches two frames of the object's shot and two frames of each other shot (at most 3 other shots); U3 v2
(prompts/u3_verify_v2.txt) must name an anchor visible in both shots, a real verdict needs one, and the description
cites it. Results in runs_v2/.

Round 2: U2 by rule instead of a model call.

Round 1 lost 6-7 targets because the U2 model did not raise objects that U1 had listed in one shot and not in another
shot of the same place. Round 2 keeps the round-1 U1 inventories unchanged (copied from runs/<task>/u1, no new U1 call)
and builds the suspects by code:
- cross_shot: for every inventory object of a shot A, the other shots that share a contract place with A (at most 4,
  the nearest in shot order). For each of them the suspect says what that shot's inventory lists that may be the same
  object (same detector id, or a name sharing a content word) or that it lists nothing like it. One suspect per object;
  a pair already covered from the other side is not repeated.
- within_shot: an object whose change_within_shot is not "none", or whose visible frames have a gap.
Frames to check: the object's middle visible frame in A and one frame of each other shot (the matched object's middle
visible frame, else frame 2); within a shot, the first and last visible frames and up to two frames where it was not
seen (or three visible frames). At most 15 suspects per video (within-shot first, then cross-shot in shot order).
- U3 v1 (Luna high, prompts/u3_verify_v1.txt): one call per suspect; real / not_real / unclear; for real, the shots
  where the inconsistency is seen and a V-V issue. Then the same detection build and frozen chain v6 V-V review as
  round 1. Results in runs_v1/."""
import argparse
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))
import run_u_branch as ub  # noqa: E402

common = ub.common
RUNS1, RUNS2 = EXP / 'runs', EXP / 'runs_v2'
P3 = 'vl_vv_u3_verify_exp_v2'
PROMPT_U3 = EXP / 'prompts/u3_verify_v2.txt'
MAX_SUSPECTS, MAX_OTHER = 15, 3
ub.PROMPT['u1'] = EXP / 'prompts/u1_inventory_v1.txt'
ub.EFFORT['u1'] = 'medium'
STOP = {'small', 'large', 'big', 'tall', 'low', 'dark', 'light', 'pale', 'white', 'black', 'gray', 'grey', 'brown', 'red',
        'green', 'blue', 'yellow', 'left', 'right', 'top', 'bottom', 'upper', 'lower', 'wall', 'the', 'and', 'with',
        'background', 'far', 'near', 'side', 'front', 'back', 'rear', 'wooden', 'metal', 'glass', 'round', 'square',
        'partly', 'hidden', 'distant', 'object', 'item', 'items', 'thing', 'unidentified', 'region', 'area'}
S = dict(type='string')
U3_SCHEMA = ub.obj(dict(protocol=dict(type='string', const=P3), verdict=dict(type='string', enum=['real', 'not_real', 'unclear']),
                        reason=S, anchor=S, shots=dict(type='array', items=S), subcategory=S, description=S,
                        key_evidence=dict(type='array', items=ub.obj(dict(shot_id=S, frame_id=dict(type='integer'), observation=S))),
                        confidence=dict(type='string', enum=['high', 'medium', 'low', ''])))


def tokens(name):
    return {w for w in re.findall(r'[a-z]+', name.lower()) if len(w) > 2 and w not in STOP}


def load_inventories(task, shots, ctx=None, workers=6):
    # Round 3: U1 is rerun with the wider prompt at reasoning medium (ub.u1 with the patched PROMPT/EFFORT).
    out = RUNS2 / task
    done = {s: out / 'u1' / s / 'inventory.json' for s in shots}
    todo = [s for s in shots if not done[s].is_file()]
    if todo:
        with ThreadPoolExecutor(workers) as pool:
            list(pool.map(lambda s: ub.u1(out, ctx, s), todo))
    return {s: json.loads(done[s].read_text()) for s in shots}


def u2_rule(ctx, inventories):
    case, contract, manifest = ctx[0], ctx[1], ctx[2]
    shots = common.shot_ids(manifest)
    frame_ids = {s: sorted(f for sh, f in common.frame_pairs(manifest) if sh == s) for s in shots}
    locs = {s['shot_id']: set(s.get('locations') or []) for s in contract['shots']}
    inv = {s: inventories[s]['inventory'] for s in shots}
    within, cross, covered = [], [], set()

    def mid(frames):
        return frames[len(frames) // 2]
    for s in shots:
        for o in inv[s]:
            fv = o['frames_visible']
            if not fv:
                continue
            gap = max(fv) - min(fv) + 1 != len(fv)
            if o['change_within_shot'].strip().lower() == 'none' and not gap:
                continue
            missing = [f for f in frame_ids[s] if f not in fv]
            pick = [fv[0], fv[-1]] + missing[:2] if missing else [fv[0], mid(fv), fv[-1]]
            pick = sorted(dict.fromkeys(pick))[:4]  # within: unchanged
            if len(pick) < 2:
                pick = sorted(dict.fromkeys([fv[0], frame_ids[s][-1] if fv[0] != frame_ids[s][-1] else frame_ids[s][0]]))
            within.append(dict(scope='within_shot', shot=s, obj=o, others=[], check_frames=[(s, f) for f in pick]))
    for a in shots:
        for o in inv[a]:
            if not o['frames_visible']:
                continue
            others = [b for b in shots if b != a and locs.get(a, set()) & locs.get(b, set())
                      and (b, o['ref'], a) not in covered]
            others = sorted(others, key=lambda b: abs(shots.index(b) - shots.index(a)))[:MAX_OTHER]
            if not others:
                continue
            fva = o['frames_visible']
            rows, frames = [], [(a, fva[0]), (a, fva[-1])] if len(fva) > 1 else [(a, fva[0])]
            for b in sorted(others, key=shots.index):
                match = [e for e in inv[b] if e['ref'] == o['ref'] or tokens(e['name']) & tokens(o['name'])]
                rows.append(dict(shot_id=b, listed=match))
                for e in match:
                    covered.add((b, e['ref'], a))
                fb = [e['frames_visible'] for e in match if e['frames_visible']]
                if fb and len(fb[0]) > 1:
                    frames += [(b, fb[0][0]), (b, fb[0][-1])]
                elif fb:
                    frames.append((b, fb[0][0]))
                else:
                    ids = frame_ids[b]
                    frames += [(b, ids[1] if len(ids) > 1 else ids[0]), (b, ids[-2] if len(ids) > 2 else ids[-1])]
            cross.append(dict(scope='cross_shot', shot=a, obj=o, others=rows, check_frames=frames))
    return (within + cross)[:MAX_SUSPECTS], len(within) + len(cross)


def u3(out, ctx, index, s):
    images, texts = ctx[4], ctx[6]
    by = {(r['shot_id'], r['frame_id']): r for r in images}
    cf = sorted(dict.fromkeys(s['check_frames']), key=lambda p: (ub.shot_key(p[0]), p[1]))
    rows = [by[p] for p in cf]
    attached = set(cf)
    keys = ('ref', 'name', 'description', 'location', 'frames_visible', 'change_within_shot')
    shots = [s['shot']] + [r['shot_id'] for r in s['others']]
    allowed = ub.WITHIN if s['scope'] == 'within_shot' else ub.CROSS
    suspect = dict(scope=s['scope'], shot_id=s['shot'], object={k: s['obj'][k] for k in keys})
    if s['scope'] == 'cross_shot':
        suspect['other_shots_same_place'] = [dict(shot_id=r['shot_id'], inventory_lists=[{k: e[k] for k in keys} for e in r['listed']]
                                                  or 'nothing like this object') for r in s['others']]
    payload = dict(protocol=P3, shots=[dict(shot_id=sh, text=texts.get(sh, '')) for sh in shots], SUSPECT=suspect,
                   allowed_subcategories={k: ub.CFG['v_v_subcategories'][s['scope']][k] for k in allowed},
                   image_order=common.image_order(rows))

    def errors(c):
        if c['verdict'] != 'real':
            return []
        e = []
        if not c['anchor'].strip():
            e.append('a real verdict needs an anchor visible in both shots (or, within a shot, next to the place)')
        if c['subcategory'] not in allowed:
            e.append(f'subcategory must be one of {allowed}')
        if not c['description'].strip():
            e.append('description must not be empty for a real verdict')
        if c['confidence'] not in ('high', 'medium', 'low'):
            e.append('confidence must be high, medium or low for a real verdict')
        sh = c['shots']
        if not set(sh) <= set(shots) or len(set(sh)) != len(sh):
            e.append(f'shots must be distinct shots of this check: {shots}')
        if s['scope'] == 'within_shot' and sh != [s['shot']]:
            e.append(f'a within_shot inconsistency has shots ["{s["shot"]}"]')
        if s['scope'] == 'cross_shot' and (s['shot'] not in sh or len(set(sh)) < 2):
            e.append(f'a cross_shot inconsistency has {s["shot"]} and at least one other shot')
        ev = [(x['shot_id'], x['frame_id']) for x in c['key_evidence']]
        if len(set(ev)) < 2:
            e.append('key_evidence needs two or more distinct attached frames')
        for p in ev:
            if p not in attached:
                e.append(f'key_evidence frame {p[0]} {p[1]} is not attached; use only {sorted(attached)}')
            elif p[0] not in sh:
                e.append(f'key_evidence frame {p[0]} {p[1]} is not in shots {sh}')
        if s['scope'] == 'cross_shot' and len({p[0] for p in ev}) < 2:
            e.append('cross_shot key_evidence needs frames of at least two shots')
        return e
    folder = out / 'u3' / f's{index}' / 'call'
    folder.parent.mkdir(parents=True, exist_ok=True)
    value, _, _, audit = ub.repair_loop.call_with_repair(
        folder, payload, rows, 900, prompt_path=PROMPT_U3, schema=U3_SCHEMA, model=ub.MODEL, reasoning='high',
        collect_errors=lambda c: (errors(c), c), stage=f'U3v2 suspect {index}', repair_prompt=common.REPAIR_PROMPT)
    res = dict(index=index, suspect=dict(scope=s['scope'], shot=s['shot'], object_ref=s['obj']['ref'],
                                         others=[dict(shot_id=r['shot_id'], listed=[e['ref'] for e in r['listed']]) for r in s['others']],
                                         check_frames=cf), result=value, repair_rounds=audit['repair_rounds'])
    (out / 'u3' / f's{index}' / 'verdict.json').write_text(json.dumps(res, indent=1, ensure_ascii=False) + '\n')
    # The shape build_detection expects: shots of the issue and the inventory entries that are its subjects.
    shots_issue = value['shots'] if value['verdict'] == 'real' else shots
    objects = [dict(shot_id=s['shot'], ref=s['obj']['ref'])] + [
        dict(shot_id=r['shot_id'], ref=e['ref']) for r in s['others'] if r['shot_id'] in shots_issue for e in r['listed']]
    return dict(suspect=dict(scope=s['scope'], shots=shots_issue, objects=objects), result=value)


def run_video(task, row, workers, count_only=False):
    out = RUNS2 / task
    if (out / 'done.json').is_file() and not count_only:
        return 'skipped'
    ctx = ub.context(row['case_dir'])
    shots = common.shot_ids(ctx[2])
    out.mkdir(parents=True, exist_ok=True)
    inventories = load_inventories(task, shots, ctx, workers)
    suspects, raw = u2_rule(ctx, inventories)
    if count_only:
        return dict(task=task, suspects=len(suspects), before_cap=raw,
                    within=sum(s['scope'] == 'within_shot' for s in suspects))
    (out / 'u2').mkdir(exist_ok=True)
    (out / 'u2' / 'suspects.json').write_text(json.dumps(dict(before_cap=raw, suspects=[
        dict(scope=s['scope'], shot=s['shot'], object_ref=s['obj']['ref'], object_name=s['obj']['name'],
             others=[dict(shot_id=r['shot_id'], listed=[e['ref'] for e in r['listed']]) for r in s['others']],
             check_frames=s['check_frames']) for s in suspects]), indent=1, ensure_ascii=False) + '\n')
    t0 = time.time()
    with ThreadPoolExecutor(workers) as pool:
        verified = list(pool.map(lambda a: u3(out, ctx, a[0], a[1]), enumerate(suspects, 1)))
    t1 = time.time()
    path, n = ub.build_detection(out, ctx, Path(row['output_dir']) / 'vv_detection/result.json', inventories, verified)
    rc = ub.review(out, ctx[0], path) if n else 0
    t2 = time.time()
    if rc:
        return f'failed at review (exit {rc})'
    summary = dict(task=task, suspects=len(suspects), before_cap=raw, real=n,
                   unclear=sum(v['result']['verdict'] == 'unclear' for v in verified),
                   seconds=dict(u3=round(t1 - t0, 1), review=round(t2 - t1, 1)), usd=round(ub.spent(out), 6))
    (out / 'done.json').write_text(json.dumps(summary, indent=1) + '\n')
    return f'success {summary}'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--only', nargs='*')
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--workers', type=int, default=6)
    p.add_argument('--cap', type=float, default=0.8)
    p.add_argument('--count', action='store_true', help='only count the rule-based suspects (no model call)')
    a = p.parse_args()
    RUNS2.mkdir(exist_ok=True)
    dev = json.loads((EXP.parent / 'vl_vv_stronger_vv_recall_20261110/baseline_usage.json').read_text())
    val = json.loads((EXP.parent / 'vl_vv_view_pair_validation_20261110/videos.json').read_text())
    rows = {t: dict(case_dir=dev['rows'][t]['case_dir'], output_dir=dev['rows'][t]['output_dir']) for t in dev['target_videos']}
    rows.update(val)
    tasks = [t for t in rows if not a.only or t in a.only]
    if a.count:
        res = [run_video(t, rows[t], a.workers, count_only=True) for t in tasks]
        for r in res:
            print(r)
        print('total suspects', sum(r['suspects'] for r in res), 'before cap', sum(r['before_cap'] for r in res))
        return
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('Run inside an owned Slurm allocation')
    reserved = {}

    def job(t):
        with ub.LOCK:
            if ub.spent(RUNS2) + sum(reserved.values()) + 0.06 > a.cap:
                return t, 'not started: budget gate'
            reserved[t] = 0.06
        try:
            try:
                r = run_video(t, rows[t], a.workers)
            except Exception as exc:  # noqa: BLE001
                r = f'failed: {type(exc).__name__}: {exc}'[:500]
            return t, r
        finally:
            with ub.LOCK:
                reserved.pop(t, None)
    with ThreadPoolExecutor(a.threads) as pool:
        for t, r in pool.map(job, tasks):
            print(t, r, flush=True)
    print('spent round 3 (GPT-6 Luna standard-price estimate, USD):', round(ub.spent(RUNS2), 6))


if __name__ == '__main__':
    main()
