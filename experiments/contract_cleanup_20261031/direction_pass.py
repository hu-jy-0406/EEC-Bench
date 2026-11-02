#!/usr/bin/env python3
"""Apply the owner's left/right rule (2026-10-31) to cleaned contracts.

Rule: left/right with no stated frame whose subject is a person is in that person's own frame
(coordinate_frame "entity"). Positions in a frame composition and facing/profile orientation stay screen,
body sides stay anatomical, a stated frame stays as stated, non-person subjects are left as they are.

Every spatial, motion or cross-shot requirement whose text or evidence mentions left/right is listed, together
with every such requirement the cleanup removed or rewrote. A Sonnet agent classifies each item; for a person
direction it gives the own-frame wording. This program turns that into rewrite ops on top of the episode's final
ops (replacing an earlier remove/rewrite of the same requirement), validates with cleanup.py and re-finalizes,
keeping the review status.

Commands:
  python3 direction_pass.py prepare
  python3 direction_pass.py show EPISODE_ID
  python3 direction_pass.py apply EPISODE_ID DECISIONS_JSON
  python3 direction_pass.py status
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleanup as C  # noqa: E402

HERE = C.HERE
OUT = HERE / 'directions'
LR = re.compile(r'\b(left|right|leftward|rightward|leftwards|rightwards)\b', re.I)
CATS = ('person_direction', 'position', 'facing', 'stated_frame', 'body_side', 'non_person')


BODY = re.compile(r'\b(his|her|their|its|the|a|one)\s+(own\s+)?(left|right)\s+(hand|arm|forearm|shoulder|leg|foot|knee|eye|ear|'
                  r'cheek|hip|side|wrist|elbow|palm|fingers?|thigh|temple|brow|eyebrow|sleeve|glove|boot|shoe|cuff|pocket|lapel|ankle)s?\b', re.I)
FRAMED = re.compile(r'(screen|frame)[- ](left|right)|(left|right)[- ](of (the )?frame|frame|edge of the frame|screen)|'
                    r'(left|right) (edge|side) of the (frame|screen)|out of (the )?frame to the (left|right)', re.I)


def mentions_lr(it):
    return bool(LR.search(it['expected']) or any(LR.search(q['quote']) for q in it.get('evidence', [])))


def auto_category(row):
    """Items that need no judgment: no direction left in the requirement, body sides only, or a frame stated in the prompt words."""
    if row['state'] == 'current' and not LR.search(row['expected_now'] or ''):
        return 'no_direction_in_requirement'
    if not LR.search(BODY.sub(' ', row['expected_original'])):
        return 'body_side'
    ev = BODY.sub(' ', ' '.join(row['evidence']))
    if LR.search(ev) and not LR.search(FRAMED.sub(' ', ev)):
        return 'stated_frame'
    return None


def items_of(c):
    out = {}
    for s in c['shots']:
        for dim in ('spatial', 'motion'):
            for it in s[dim]:
                out[it['id']] = (s['shot_id'], dim, it)
    for it in c['cross_shot']:
        out[it['id']] = (None, it['dimension'], it)
    return out


def prepare():
    OUT.mkdir(exist_ok=True)
    n_items = n_eps = 0
    for j in C.manifest()['episodes']:
        eid = j['episode_id']
        folder = HERE / 'episodes' / eid
        cur = items_of(C.read(folder / 'contract_with_evidence.json'))
        orig = items_of(C.load_input(eid))
        rows = []
        for rid, (sid, dim, it) in orig.items():
            now = cur.get(rid)
            if not (mentions_lr(it) or (now and mentions_lr(now[2]))):
                continue
            state = 'removed' if now is None else ('changed' if now[2]['expected'] != it['expected'] or
                                                    now[2].get('coordinate_frame') != it.get('coordinate_frame') else 'current')
            shown = it if now is None else now[2]
            rows.append(dict(id=rid, shot_id=sid, dimension=dim, state=state, entities=it['entities'],
                             expected_now=None if now is None else now[2]['expected'],
                             frame_now=None if now is None else now[2].get('coordinate_frame'),
                             expected_original=it['expected'], frame_original=it.get('coordinate_frame'),
                             evidence=[q['quote'] for q in shown.get('evidence', [])]))
            rows[-1]['auto'] = auto_category(rows[-1])
        if rows:
            C.dump(OUT / f'{eid}.input.json', dict(episode_id=eid, items=rows))
            n_items += len(rows)
            n_eps += 1
    print(json.dumps(dict(episodes=n_eps, items=n_items)))


def show(eid):
    c = C.read(HERE / 'episodes' / eid / 'contract_with_evidence.json')
    orig = C.load_input(eid)
    names = {k: f'{e["name"]} ({e["label"]})' for k, e in orig['entity_descriptions'].items()}
    d = C.read(OUT / f'{eid}.input.json')
    print(f'EPISODE {eid}\n\n== PROMPT')
    print('global: ' + c['prompt']['global_prompt'])
    for s in c['prompt']['shots']:
        print(f'{s["shot_id"]}: {s["text"]}')
    print('\n== ITEMS (entity ids are the ORIGINAL ids; one decision per item)')
    for r in d['items']:
        if r['auto']:
            continue
        ents = ', '.join(names.get(str(k), str(k)) for k in r['entities'])
        print(f'{r["id"]} [{r["shot_id"] or "cross-shot"} {r["dimension"]}, {r["state"]}] entities: {ents}')
        print(f'   original: {r["expected_original"]} (frame {r["frame_original"]})')
        if r['state'] != 'current':
            print(f'   now: {r["expected_now"]} (frame {r["frame_now"]})')
        print('   evidence: ' + ' | '.join(f'"{q}"' for q in r['evidence']))


def apply(eid, path):
    d = C.read(OUT / f'{eid}.input.json')
    dec = C.read(path)
    want = [r['id'] for r in d['items'] if not r['auto']]
    got = [x.get('id') for x in dec.get('items', [])]
    err = []
    if dec.get('episode_id') != eid:
        err.append(f'episode_id must be {eid}')
    if sorted(got) != sorted(want):
        err.append(f'items must cover exactly {want} (got {got})')
    for x in dec.get('items', []):
        if x.get('category') not in CATS:
            err.append(f'{x.get("id")}: category must be one of {CATS}')
        if x.get('category') == 'person_direction' and not re.search(r'\bown (left|right)', x.get('expected', ''), re.I):
            err.append(f'{x.get("id")}: a person direction needs expected text with "own left"/"own right"')
    if err:
        print('FAIL\n' + '\n'.join(err))
        return 1
    folder = HERE / 'episodes' / eid
    before = folder / 'ops_before_direction_pass.json'
    ops = C.read(before if before.exists() else folder / 'final_ops.json')  # re-applying starts from the pre-pass ops
    rule ='Owner direction rule 2026-10-31: left/right with a person as subject and no stated frame is the person\'s own left/right.'
    changed = []
    for x in dec['items']:
        if x['category'] != 'person_direction':
            continue
        new = dict(op='rewrite_requirement', id=x['id'], expected=x['expected'], coordinate_frame='entity', reason=rule)
        idx = next((i for i, op in enumerate(ops['ops']) if op.get('id') == x['id'] and op['op'] in ('remove_requirement', 'rewrite_requirement')), None)
        if idx is None:
            ops['ops'].append(new)
        else:
            ops['ops'][idx] = new
            for n in ops['notes']:
                if idx in n.get('ops', []) and n['resolution'] in ('removed', 'narrowed'):
                    n['resolution'] = 'kept_sole_reading'
                    n['basis'] += ' [' + rule + ']'
        changed.append(x['id'])
    status_before = C.read(folder / 'status.json')
    log = dict(episode_id=eid, decisions=dec['items'], auto=[dict(id=r['id'], category=r['auto']) for r in d['items'] if r['auto']],
               changed=changed, at=time.time())
    if changed:
        tmp = OUT / f'{eid}.ops.json'
        C.dump(tmp, ops)
        c, o2, wo, new_id, err, warn = C.build(eid, tmp)
        if err:
            print('FAIL (ops)\n' + '\n'.join(err))
            return 1
        if not before.exists():
            C.dump(before, C.read(folder / 'final_ops.json'))
        C.finalize(eid, tmp, status_before['producer'])
        st = C.read(folder / 'status.json')
        status_before.update({k: st[k] for k in ('notes', 'identity', 'ops', 'finalized_at')})
    status_before['direction_pass'] = dict(items=len(want), person_direction=len(changed), at=time.time())
    C.dump(folder / 'status.json', status_before)
    C.dump(OUT / f'{eid}.decisions.json', log)
    print('APPLIED ' + json.dumps(dict(items=len(want), person_direction=len(changed))))
    return 0


def recheck_show(part, nparts):
    """Print the flagged items (directions/recheck_list.json) of one part, with their shot text and first verdict."""
    flags = C.read(OUT / 'recheck_list.json')
    flags = [f for k, f in enumerate(flags) if k % int(nparts) == int(part)]
    for eid, rid, why in flags:
        c = C.read(HERE / 'episodes' / eid / 'contract_with_evidence.json')
        row = next(r for r in C.read(OUT / f'{eid}.input.json')['items'] if r['id'] == rid)
        first = next(x for x in C.read(OUT / f'{eid}.agent.json')['items'] if x['id'] == rid)
        texts = {s['shot_id']: s['text'] for s in c['prompt']['shots']}
        names = {k: e['name'] for k, e in C.load_input(eid)['entity_descriptions'].items()}
        print(f'== {eid} {rid} (first verdict: {first["category"]})')
        print(f'   shot text: {texts.get(row["shot_id"], c["prompt"]["global_prompt"])}')
        print(f'   entities: {", ".join(names.get(str(k), str(k)) for k in row["entities"])}')
        print(f'   original: {row["expected_original"]} (frame {row["frame_original"]})')
        if row['state'] != 'current':
            print(f'   now: {row["expected_now"]} (frame {row["frame_now"]})')
        print('   evidence: ' + ' | '.join(f'"{q}"' for q in row['evidence']))


def recheck_apply(path):
    """Merge recheck verdicts into each episode's agent decisions and re-apply from the pre-pass ops."""
    rows = C.read(path)['items']
    by_ep = {}
    for r in rows:
        by_ep.setdefault(r['episode_id'], []).append(r)
    for eid, rs in by_ep.items():
        agent_path = OUT / f'{eid}.agent.json'
        agent = C.read(agent_path)
        if not (OUT / f'{eid}.agent.first.json').exists():
            C.dump(OUT / f'{eid}.agent.first.json', agent)
        for r in rs:
            x = next(i for i in agent['items'] if i['id'] == r['id'])
            if r['category'] == 'keep':  # first verdict stands
                x['rechecked'] = 'kept: ' + r.get('reason', '')
                continue
            if r['category'] != 'person_direction':
                raise SystemExit(f'{eid} {r["id"]}: recheck category must be keep or person_direction')
            x.clear()
            x.update(id=r['id'], category='person_direction', expected=r['expected'], rechecked='changed to person_direction')
        C.dump(agent_path, agent)
        code = apply(eid, agent_path)
        if code:
            raise SystemExit(f'{eid}: re-apply failed')


def status():
    inputs = sorted(OUT.glob('*.input.json'))
    done = [p for p in inputs if (OUT / p.name.replace('.input.json', '.decisions.json')).exists()]
    print(json.dumps(dict(episodes=len(inputs), applied=len(done))))
    print('\n'.join(p.name.replace('.input.json', '') for p in inputs if p not in done))


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'prepare':
        prepare()
    elif cmd == 'show':
        show(sys.argv[2])
    elif cmd == 'apply':
        sys.exit(apply(sys.argv[2], sys.argv[3]))
    elif cmd == 'recheck-show':
        recheck_show(sys.argv[2], sys.argv[3])
    elif cmd == 'recheck-apply':
        recheck_apply(sys.argv[2])
    else:
        status()
