#!/usr/bin/env python3
"""Unspecified-object plug-in for chain v6 V-V detection (owner, 2026-11-10: "把这个unspecify专属分支作为plug in";
default off; with the plug-in its findings and the main V-V candidates get one merged review, "保持合并复核").

Per video, after V-V detection and before V-V review:
  U1  one call per shot (GPT-6 Luna, medium; prompts/vl_vv_unspecified_plugin_u1_v1.txt): the shot's keyframes;
      keeps every ledger unspecified entity of the shot and adds the background objects the ledger misses (also things
      on or attached to registered or prompt-named objects, fixtures, edge and far-background objects);
  U2  by rule, no model call: every inventory object against the other shots that share a contract place with its
      shot (at most 3, nearest in shot order; same ledger id or a shared content word of the name), plus within-shot
      suspects (a noted change or a gap in the visible frames); at most 15 suspects;
  U3  one call per suspect (Luna, high; prompts/vl_vv_unspecified_plugin_u3_v2.txt): two frames of the object's shot
      and two of each other shot; real / not_real / unclear; a real verdict names an anchor visible in both shots;
  merge  real findings become V-V candidates (checklist item O1; subjects = ledger ids or new entities made from U1's
      new objects) appended to the main V-V detection result; issue ids and added-entity keys continue its numbering.
The V-V review then judges the merged list. A port of round 3 of experiments/vl_vv_unspecified_branch_20261110 as run
in the full first-200 C run (EECBench commit 6f530ee): same prompts (byte copies), schemas, payloads and rules.
Every model call uses the validation-repair loop."""
import argparse
import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import vl_vv_branch_common as common  # noqa: E402
import vl_vv_repair_loop as repair_loop  # noqa: E402
import run_vl_vv_issue_discovery as discovery_v4  # noqa: E402
import run_vl_vv_branch_detection as det  # noqa: E402

PROTOCOL = 'vl_vv_unspecified_plugin_v1'
MODEL = 'gpt-6-luna'
EFFORT = dict(u1='medium', u3='high')
PROMPT = dict(u1=ROOT / 'prompts/vl_vv_unspecified_plugin_u1_v1.txt', u3=ROOT / 'prompts/vl_vv_unspecified_plugin_u3_v2.txt')
# Protocol strings of the validated experiment, kept so that the model sees the same input.
P1, P3 = 'vl_vv_u1_inventory_exp_v0', 'vl_vv_u3_verify_exp_v2'
CFG = common.config(common.chain_spec('v6')['config'])
WITHIN = ['object_instability', 'presence_instability', 'background_drift', 'relation_break']
CROSS = ['setting_background', 'object_identity', 'instance_count', 'spatial_continuity']
assert set(WITHIN) <= set(CFG['v_v_subcategories']['within_shot'])
assert set(CROSS) <= set(CFG['v_v_subcategories']['cross_shot'])
# U1 has no limit on the number of objects (owner, 2026-11-11: "Remove the cap"; the 30-object cap of the 2026-11-10
# experiment was an assistant choice that the prompt never stated, and with worn items and place parts as entities it
# failed whole plug-in runs on busy shots).
MAX_SUSPECTS, MAX_OTHER = 15, 3
STOP = {'small', 'large', 'big', 'tall', 'low', 'dark', 'light', 'pale', 'white', 'black', 'gray', 'grey', 'brown', 'red',
        'green', 'blue', 'yellow', 'left', 'right', 'top', 'bottom', 'upper', 'lower', 'wall', 'the', 'and', 'with',
        'background', 'far', 'near', 'side', 'front', 'back', 'rear', 'wooden', 'metal', 'glass', 'round', 'square',
        'partly', 'hidden', 'distant', 'object', 'item', 'items', 'thing', 'unidentified', 'region', 'area'}
KEYS = ('ref', 'name', 'description', 'location', 'frames_visible', 'change_within_shot')


def obj(props, required=None):
    return dict(type='object', additionalProperties=False, required=required or list(props), properties=props)


S = dict(type='string')
U1_SCHEMA = obj(dict(protocol=dict(type='string', const=P1), view=S, objects=dict(type='array', items=obj(dict(
    ref=S, name=S, description=S, location=S, frames_visible=dict(type='array', items=dict(type='integer')),
    change_within_shot=S)))))
U3_SCHEMA = obj(dict(protocol=dict(type='string', const=P3), verdict=dict(type='string', enum=['real', 'not_real', 'unclear']),
                     reason=S, anchor=S, shots=dict(type='array', items=S), subcategory=S, description=S,
                     key_evidence=dict(type='array', items=obj(dict(shot_id=S, frame_id=dict(type='integer'), observation=S))),
                     confidence=dict(type='string', enum=['high', 'medium', 'low', ''])))


def read(p):
    return json.loads(Path(p).read_text())


def write(p, obj_):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj_, indent=1, ensure_ascii=False) + '\n')


def shot_key(s):
    return int(s[4:])


def tokens(name):
    return {w for w in re.findall(r'[a-z]+', name.lower()) if len(w) > 2 and w not in STOP}


def context(case_dir):
    case, contract, manifest, ledger = det.load_case(Path(case_dir), False)
    images = discovery_v4.image_rows(case, manifest)
    prompt = contract.get('prompt') or {}
    texts = {row['shot_id']: row.get('text', '') for row in prompt.get('shots', [])}
    ents = contract['entity_descriptions']
    places = {s['shot_id']: [ents[str(i)]['name'] for i in s.get('locations') or [] if str(i) in ents] for s in contract['shots']}
    return case, contract, manifest, ledger, images, prompt, texts, places


def u1(out, ctx, shot):
    case, contract, manifest, ledger, images, prompt, texts, places = ctx
    rows = [r for r in images if r['shot_id'] == shot]
    frames = {r['frame_id'] for r in rows}
    spec, unspec = [], []
    for kind, bucket in (('prompt_bound', spec), ('prompt_unbound', unspec)):
        for e in ledger[kind]:
            for o in e.get('occurrences') or []:
                if o['shot_id'] == shot:
                    boxed = sorted({b['frame_id'] for b in o.get('boxes') or []})
                    bucket.append(dict(id=e['global_entity_id'], name=e.get('name'), description=e.get('description'),
                                       boxed_frames=boxed) if kind == 'prompt_unbound' else
                                  dict(id=e['global_entity_id'], name=e.get('name')))
    registered = {r['id'] for r in unspec}
    payload = dict(protocol=P1, shot_id=shot, shot_text=texts.get(shot, ''), global_prompt=prompt.get('global_prompt', ''),
                   contract_entities=[dict(id=k, label=v['label'], name=v['name'], description=v.get('description', ''))
                                      for k, v in contract['entity_descriptions'].items()],
                   REGISTERED_SPECIFIED=spec, REGISTERED_UNSPECIFIED=unspec, image_order=common.image_order(rows))

    def errors(c):
        e, seen = [], []
        for i, o in enumerate(c['objects']):
            w = f'objects[{i}] {o["name"]!r}'
            if o['ref'] != 'new' and o['ref'] not in registered:
                e.append(f'{w}: ref must be "new" or an id of REGISTERED_UNSPECIFIED {sorted(registered)}')
            if o['ref'] in registered:
                seen.append(o['ref'])
            if not set(o['frames_visible']) <= frames:
                e.append(f'{w}: frames_visible must be keyframes of {shot}: {sorted(frames)}')
            if o['ref'] == 'new' and not o['frames_visible']:
                e.append(f'{w}: a new object must be visible in at least one keyframe')
            if not o['name'].strip() or not o['change_within_shot'].strip():
                e.append(f'{w}: name and change_within_shot must not be empty ("none" when nothing changes)')
        for r in sorted(registered):
            if seen.count(r) != 1:
                e.append(f'REGISTERED_UNSPECIFIED {r}: needs exactly one entry (found {seen.count(r)})')
        return e
    folder = out / 'u1' / shot / 'call'
    folder.parent.mkdir(parents=True, exist_ok=True)
    value, _, _, audit = repair_loop.call_with_repair(
        folder, payload, rows, 900, prompt_path=PROMPT['u1'], schema=U1_SCHEMA, model=MODEL, reasoning=EFFORT['u1'],
        collect_errors=lambda c: (errors(c), c), stage=f'U1 {shot}', repair_prompt=common.REPAIR_PROMPT)
    n, inv = 0, []
    for o in value['objects']:
        if o['ref'] == 'new':
            n += 1
            key = f'{shot}/o{n}'
        else:
            key = o['ref']
        inv.append(dict(o, ref=key, frames_visible=sorted(set(o['frames_visible']))))
    res = dict(shot_id=shot, view=value['view'], inventory=inv, repair_rounds=audit['repair_rounds'])
    write(out / 'u1' / shot / 'inventory.json', res)
    return res


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
            pick = sorted(dict.fromkeys(pick))[:4]
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
    cf = sorted(dict.fromkeys(s['check_frames']), key=lambda p: (shot_key(p[0]), p[1]))
    rows = [by[p] for p in cf]
    attached = set(cf)
    shots = [s['shot']] + [r['shot_id'] for r in s['others']]
    allowed = WITHIN if s['scope'] == 'within_shot' else CROSS
    suspect = dict(scope=s['scope'], shot_id=s['shot'], object={k: s['obj'][k] for k in KEYS})
    if s['scope'] == 'cross_shot':
        suspect['other_shots_same_place'] = [dict(shot_id=r['shot_id'], inventory_lists=[{k: e[k] for k in KEYS} for e in r['listed']]
                                                  or 'nothing like this object') for r in s['others']]
    payload = dict(protocol=P3, shots=[dict(shot_id=sh, text=texts.get(sh, '')) for sh in shots], SUSPECT=suspect,
                   allowed_subcategories={k: CFG['v_v_subcategories'][s['scope']][k] for k in allowed},
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
    value, _, _, audit = repair_loop.call_with_repair(
        folder, payload, rows, 900, prompt_path=PROMPT['u3'], schema=U3_SCHEMA, model=MODEL, reasoning=EFFORT['u3'],
        collect_errors=lambda c: (errors(c), c), stage=f'U3v2 suspect {index}', repair_prompt=common.REPAIR_PROMPT)
    res = dict(index=index, suspect=dict(scope=s['scope'], shot=s['shot'], object_ref=s['obj']['ref'],
                                         others=[dict(shot_id=r['shot_id'], listed=[e['ref'] for e in r['listed']]) for r in s['others']],
                                         check_frames=cf), result=value, repair_rounds=audit['repair_rounds'])
    write(out / 'u3' / f's{index}' / 'verdict.json', res)
    return u3_outcome(s, value)


def u3_outcome(s, value):
    """The shape branch_detection expects: shots of the issue and the inventory entries that are its subjects."""
    shots = [s['shot']] + [r['shot_id'] for r in s['others']]
    shots_issue = value['shots'] if value['verdict'] == 'real' else shots
    objects = [dict(shot_id=s['shot'], ref=s['obj']['ref'])] + [
        dict(shot_id=r['shot_id'], ref=e['ref']) for r in s['others'] if r['shot_id'] in shots_issue for e in r['listed']]
    return dict(suspect=dict(scope=s['scope'], shots=shots_issue, objects=objects), result=value)


def branch_detection(ctx, main, inventories, verified):
    """The plug-in's own candidates next to the main entity records (round-3 build_detection)."""
    ledger = ctx[3]
    led = {e['global_entity_id']: (e, kind) for kind in ('prompt_bound', 'prompt_unbound') for e in ledger[kind]}
    have = {r['entity_key'] for r in main['entities']}
    inv = {(sh, o['ref']): o for sh in inventories for o in inventories[sh]['inventory']}
    added, new_key, extra, issues = [], {}, [], []
    for v in verified:
        r, s = v['result'], v['suspect']
        if r['verdict'] != 'real':
            continue
        keys = []
        for o in s['objects']:
            ref = o['ref']
            if ref in led:
                if ref not in have:
                    e, part = led[ref]
                    extra.append(dict(entity_key=ref, global_entity_id=ref, source='detection_ledger', name=e.get('name'),
                                      description=e.get('description'), partition=part,
                                      prompt_entity_id=e.get('prompt_entity_id'), frame_refs=[],
                                      label='specified' if part == 'prompt_bound' else 'unspecified'))
                    have.add(ref)
                keys.append(ref)
            else:
                if ref not in new_key:
                    new_key[ref] = f'n{len(new_key) + 1}'
                    entry = inv[(o['shot_id'], ref)]
                    added.append(dict(entity_key=new_key[ref], global_entity_id=None, source='added_by_vv_detection',
                                      name=entry['name'], description=entry['description'], partition=None,
                                      prompt_entity_id=None, label='unspecified',
                                      frame_refs=[dict(shot_id=o['shot_id'], frame_id=f) for f in entry['frames_visible']]))
                keys.append(new_key[ref])
        keys = list(dict.fromkeys(keys))
        issues.append(dict(issue_id=f'V{len(issues) + 1}', branch='v_v', scope=s['scope'], subcategory=r['subcategory'],
                           description=r['description'], shot_ids=sorted(set(s['shots']), key=shot_key),
                           entity_refs=[dict(entity_key=k, role='subject') for k in keys],
                           key_evidence=[dict(shot_id=x['shot_id'], frame_id=x['frame_id'], entity_keys=keys,
                                              observation=x['observation']) for x in r['key_evidence']],
                           confidence=r['confidence'], v_l_detail=None, v_v_detail=dict(checklist_items=['O1'])))
    return dict(main, issues=issues, entities=main['entities'] + extra + added)


def merge(main, branch_det, suspects, real):
    """Main V-V candidates plus the plug-in's findings; issue ids and added-entity keys continue the main numbering."""
    vmax = max([int(i['issue_id'][1:].split('.')[0]) for i in main['issues'] if i['issue_id'][1:].split('.')[0].isdigit()] + [0])
    nmain = max([int(e['entity_key'][1:]) for e in main['entities'] if str(e['entity_key']).startswith('n')
                 and str(e['entity_key'])[1:].isdigit()] + [0])
    main_keys = {e['entity_key'] for e in main['entities']}
    assert branch_det['entities'][:len(main['entities'])] == main['entities']
    rename, extra = {}, []
    for e in branch_det['entities'][len(main['entities']):]:
        if e['source'] == 'added_by_vv_detection':
            nmain += 1
            rename[e['entity_key']] = f'n{nmain}'
            extra.append(dict(e, entity_key=f'n{nmain}'))
        elif e['entity_key'] not in main_keys:
            extra.append(e)
    issues = []
    for k, i in enumerate(branch_det['issues'], 1):
        i = json.loads(json.dumps(i))
        i['issue_id'] = f'V{vmax + k}'
        for r in i['entity_refs']:
            r['entity_key'] = rename.get(r['entity_key'], r['entity_key'])
        for ev in i['key_evidence']:
            ev['entity_keys'] = [rename.get(x, x) for x in ev['entity_keys']]
        issues.append(i)
    return dict(main, issues=main['issues'] + issues, entities=main['entities'] + extra,
                u_branch=dict(protocol=PROTOCOL, note='main V-V candidates plus the unspecified plug-in findings',
                              branch_issue_ids=[i['issue_id'] for i in issues], suspects=suspects, real=real))


def run(case, detection, out, workers=6):
    out = Path(out)
    if (out / 'result.json').is_file():
        raise ValueError(f'{out} already holds a result; use a fresh directory')
    main = read(detection)
    if main.get('status') != 'success':
        raise ValueError('The main V-V detection is not a successful result')
    ctx = context(case)
    shots = common.shot_ids(ctx[2])
    todo = [s for s in shots if not (out / 'u1' / s / 'inventory.json').is_file()]
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(lambda s: u1(out, ctx, s), todo))
    inventories = {s: read(out / 'u1' / s / 'inventory.json') for s in shots}
    suspects, raw = u2_rule(ctx, inventories)
    write(out / 'u2' / 'suspects.json', dict(before_cap=raw, count=len(suspects), suspects=[
        dict(scope=s['scope'], shot=s['shot'], object_ref=s['obj']['ref'], object_name=s['obj']['name'],
             others=[dict(shot_id=r['shot_id'], listed=[e['ref'] for e in r['listed']]) for r in s['others']],
             check_frames=s['check_frames']) for s in suspects]))
    with ThreadPoolExecutor(workers) as pool:
        verified = list(pool.map(lambda a: u3(out, ctx, a[0], a[1]), enumerate(suspects, 1)))
    real = sum(v['result']['verdict'] == 'real' for v in verified)
    branch = branch_detection(ctx, main, inventories, verified)
    write(out / 'branch_detection.json', branch)
    merged = merge(main, branch, len(verified), real)
    merged['u_branch'].update(main_detection=str(Path(detection).resolve()),
                              prompts={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in PROMPT.values()})
    write(out / 'result.json', merged)
    return dict(suspects=len(verified), before_cap=raw, real=real, added_issues=len(merged['u_branch']['branch_issue_ids']))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', type=Path, required=True)
    p.add_argument('--detection', type=Path, required=True, help='Main V-V detection result (chain v6)')
    p.add_argument('--output', type=Path, required=True, help='Plug-in folder; result.json = merged V-V detection')
    p.add_argument('--workers', type=int, default=6)
    a = p.parse_args()
    print(json.dumps(run(a.case.resolve(), a.detection.resolve(), a.output.resolve(), a.workers)))


if __name__ == '__main__':
    main()
