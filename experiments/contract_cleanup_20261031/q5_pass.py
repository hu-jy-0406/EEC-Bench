#!/usr/bin/env python3
"""Apply the owner's four Q5 rulings (2026-11-01; go-ahead 2026-11-05) to the cleaned contracts.

Rulings (EECBench/docs/open-questions.md Q5; rules_q5.txt):
  Q5-1 focus, softness or blur is camera information of that shot (camera_view);
  Q5-2 "hold the shot / view / two-shot" is a static camera (camera_movement);
  Q5-3 lighting stated in one shot goes to the location description or to that shot, by context;
  Q5-4 a street, snow or similar ground is part of the location, not an entity.

Like direction_pass.py, the pass appends operations to each episode's cleanup operations
(episodes/<id>/final_ops.json, saved first as ops_before_q5.json) and re-finalizes with cleanup.py,
so every existing check still applies and export rebuilds every contract from the frozen v2 input.
Agents see the current cleaned contract with the ORIGINAL entity and requirement ids that the
operations use. A second, independent agent reviews every Q5 operation, every checked statement and
looks for missed ones; the main session rules on disagreements.

Commands (lightweight; run from this directory):
  python3 q5_pass.py show EPISODE_ID                  cleaned contract + prompts + keyword hints
  python3 q5_pass.py check EPISODE_ID Q5_OPS_JSON      PASS/FAIL and the exact change
  python3 q5_pass.py apply EPISODE_ID Q5_OPS_JSON      re-finalize with the Q5 operations
  python3 q5_pass.py review-show EPISODE_ID
  python3 q5_pass.py review-record EPISODE_ID REVIEW_JSON
  python3 q5_pass.py resolve EPISODE_ID RESOLUTION_JSON [CORRECTED_Q5_OPS_JSON]
  python3 q5_pass.py status
  python3 q5_pass.py export                            after every episode is reviewed / resolved
"""
import argparse
import difflib
import json
import re
import sys
import time
from pathlib import Path

import cleanup as C

HERE = Path(__file__).resolve().parent
RULES = ('Q5-1', 'Q5-2', 'Q5-3', 'Q5-4')
OUTCOMES = ('recorded', 'already_recorded', 'not_applicable')
Q5_OPS = ('set_camera', 'remove_requirement', 'rewrite_requirement', 'edit_description', 'add_requirement',
          'merge_entities')
HINTS = {
    'Q5-1': re.compile(r'\b(blur\w*|focus\w*|soft\w*|bokeh|depth of field|haz[ey]\w*|out of focus)\b', re.I),
    'Q5-2': re.compile(r'\b(hold|holds|holding|held)\b', re.I),
    'Q5-3': re.compile(r'\b(\w*lit|light\w*|lamp\w*|glow\w*|shadow\w*|dim\w*|bright\w*|neon|backlit|silhouett\w*|'
                       r'candle\w*|flicker\w*|sunlit|sunlight|sunbeam\w*|sunset|sunrise|sunshine|moonlight|moonlit)\b', re.I),
    'Q5-4': re.compile(r'\b(street\w*|road\w*|snow\w*|sand\w*|grass\w*|pavement|sidewalk|asphalt|gravel|dirt|'
                       r'ground|lawn|cobble\w*|mud\w*|ice)\b', re.I),
}


def folder(eid):
    return HERE / 'episodes' / eid


def base_ops(eid):
    """The cleanup operations before this pass (re-applying always starts from them)."""
    before = folder(eid) / 'ops_before_q5.json'
    return C.read(before if before.exists() else folder(eid) / 'final_ops.json')


def working(eid, ops):
    c = C.load_input(eid)
    w, err = C.apply_ops(c, ops)
    if err:
        raise SystemExit(f'{eid}: the operations do not apply: {err}')
    return c, w


def render_working(c, w):
    view = dict(w.c, entity_descriptions=w.ents, prompt=c['prompt'], unresolved=[])
    return C.render_text(view, notes=False)


def hints(c):
    rows = []
    for sid, text in [('global', c['prompt']['global_prompt'])] + [(s['shot_id'], s['text']) for s in c['prompt']['shots']]:
        for rule, rx in HINTS.items():
            words = sorted({m.group(0).lower() for m in rx.finditer(text or '')})
            if words:
                rows.append(f'{rule} {sid}: {", ".join(words)}')
    return rows


def show(eid):
    c, w = working(eid, base_ops(eid))
    print(render_working(c, w).replace(f'EPISODE {eid}', f'EPISODE {eid} (cleaned contract; ORIGINAL ids, used by the ops)', 1))
    print('\n== KEYWORD HINTS (neither complete nor all relevant; read every prompt)')
    print('\n'.join(hints(c)) or '(none)')


def q5_errors(eid, q5):
    err = []
    if q5.get('episode_id') != eid:
        err.append(f'episode_id must be {eid}')
    if not isinstance(q5.get('ops'), list) or not isinstance(q5.get('checked'), list):
        return err + ['q5_ops.json needs lists "ops" and "checked"']
    for n, op in enumerate(q5['ops']):
        if op.get('rule') not in RULES:
            err.append(f'ops[{n}]: "rule" must be one of {RULES}')
        if op.get('op') not in Q5_OPS:
            err.append(f'ops[{n}]: op must be one of {Q5_OPS}')
        if not str(op.get('reason', '')).strip():
            err.append(f'ops[{n}]: needs a reason')
    for n, row in enumerate(q5['checked']):
        if row.get('rule') not in RULES or row.get('outcome') not in OUTCOMES or not str(row.get('basis', '')).strip() \
                or not str(row.get('quote', '')).strip() or not row.get('shot_id'):
            err.append(f'checked[{n}]: needs rule {RULES}, shot_id, quote, outcome {OUTCOMES} and basis')
        ops = row.get('ops', [])
        if not isinstance(ops, list) or any(not isinstance(i, int) or not 0 <= i < len(q5['ops']) for i in ops):
            err.append(f'checked[{n}]: ops must be indices into ops')
        elif row.get('outcome') == 'recorded' and not ops:
            err.append(f'checked[{n}]: outcome recorded needs the ops that record it')
        elif row.get('outcome') != 'recorded' and ops:
            err.append(f'checked[{n}]: only outcome recorded lists ops')
    claimed = {i for row in q5['checked'] for i in row.get('ops', []) if isinstance(i, int)}
    unclaimed = [i for i in range(len(q5['ops'])) if i not in claimed]
    if unclaimed:
        err.append(f'ops {unclaimed} belong to no checked statement; every op records a checked statement')
    return err


def combine(eid, q5):
    ops = base_ops(eid)
    combined = dict(ops, ops=ops['ops'] + [{k: v for k, v in op.items()} for op in q5['ops']])
    path = folder(eid) / 'q5_combined_ops.json'
    C.dump(path, combined)
    return ops, path


def diff(eid, ops_before, path_after):
    outs = []
    for ops in (ops_before, C.read(path_after)):
        c, w = working(eid, ops)
        out, _, err, _ = C.finish(w)
        outs.append(C.render_text(out, notes=False).splitlines())
    return [line for line in difflib.unified_diff(outs[0], outs[1], lineterm='', n=0)
            if line.startswith(('+', '-')) and not line.startswith(('+++', '---'))]


def check(eid, path, quiet=False):
    try:
        q5 = C.read(path)
        err = q5_errors(eid, q5)
        if not err:
            before, combined = combine(eid, q5)
            _, _, wo, _, err2, warn = C.build(eid, combined)
            err += err2
    except (ValueError, json.JSONDecodeError, KeyError, TypeError) as e:
        err = [f'{type(e).__name__}: {e}']
    with (folder(eid) / 'q5_check_log.jsonl').open('a') as f:
        f.write(json.dumps(dict(at=time.time(), file=str(path), errors=len(err))) + '\n')
    if err:
        print('FAIL\n' + '\n'.join(dict.fromkeys(err)))
        return 1
    if not quiet:
        print('PASS (contract lines removed "-" and added "+"; entity ids below are the renumbered final ids)')
        print('\n'.join(diff(eid, before, combined)) or '(no change)')
    return 0


def apply(eid, path, producer):
    if check(eid, path, quiet=True):
        raise SystemExit(f'{eid}: run check until PASS first')
    q5 = C.read(path)
    st_before = C.read(folder(eid) / 'status.json')
    before = folder(eid) / 'ops_before_q5.json'
    if not before.exists():
        C.dump(before, C.read(folder(eid) / 'final_ops.json'))
    _, combined = combine(eid, q5)
    C.dump(folder(eid) / 'q5_ops_applied.json', q5)
    C.finalize(eid, combined, st_before['producer'])
    st = C.read(folder(eid) / 'status.json')
    st_before.update({k: st[k] for k in ('notes', 'identity', 'ops', 'finalized_at')})
    st_before['q5'] = dict(stage='applied', producer=producer, ops=len(q5['ops']), checked=len(q5['checked']),
                           rules={r: sum(op['rule'] == r for op in q5['ops']) for r in RULES}, applied_at=time.time())
    C.dump(folder(eid) / 'status.json', st_before)
    print('APPLIED ' + json.dumps(st_before['q5']))


# ---------------------------------------------------------------- independent review
def review_items(eid):
    q5 = C.read(folder(eid) / 'q5_ops_applied.json')
    items = [dict(ref=f'O{j}', text='CHANGE ' + json.dumps({k: v for k, v in op.items() if k != 'reason'}, ensure_ascii=False))
             for j, op in enumerate(q5['ops'])]
    items += [dict(ref=f'C{j}', text='CHECKED ' + json.dumps(row, ensure_ascii=False)) for j, row in enumerate(q5['checked'])]
    return q5, items


def review_show(eid):
    c, w = working(eid, base_ops(eid))
    print(render_working(c, w).replace(f'EPISODE {eid}', f'EPISODE {eid} (cleaned contract BEFORE the Q5 pass; ORIGINAL ids)', 1))
    _, items = review_items(eid)
    print('\n== RESULT OF THE Q5 PASS (renumbered final ids)')
    print('\n'.join(diff(eid, base_ops(eid), folder(eid) / 'final_ops.json')) or '(no change)')
    print('\n== ITEMS TO REVIEW (one verdict each)')
    print('\n'.join(f'{it["ref"]}: {it["text"]}' for it in items) or '(none)')
    print('\n== KEYWORD HINTS (neither complete nor all relevant)')
    print('\n'.join(hints(c)) or '(none)')


def review_record(eid, path):
    _, items = review_items(eid)
    r = C.read(path)
    refs = [x['ref'] for x in items]
    err = []
    if r.get('episode_id') != eid:
        err.append(f'episode_id must be {eid}')
    if sorted(x.get('ref') for x in r.get('items', [])) != sorted(refs):
        err.append(f'items must cover exactly {refs}')
    for x in r.get('items', []):
        if x.get('verdict') not in ('agree', 'disagree') or not str(x.get('basis', '')).strip():
            err.append(f'{x.get("ref")}: needs verdict agree/disagree and a basis')
        if x.get('verdict') == 'disagree' and not str(x.get('alternative', '')).strip():
            err.append(f'{x.get("ref")}: a disagreement needs the alternative you propose')
    if not isinstance(r.get('missed'), list):
        err.append('needs a list "missed" (empty when nothing was missed)')
    for j, m in enumerate(r.get('missed') or []):
        if m.get('rule') not in RULES or not m.get('shot_id') or not str(m.get('quote', '')).strip() \
                or not str(m.get('proposal', '')).strip():
            err.append(f'missed[{j}]: needs rule, shot_id, quote and proposal')
    if err:
        print('FAIL\n' + '\n'.join(err))
        return 1
    C.dump(folder(eid) / 'q5_review.json', r)
    st = C.read(folder(eid) / 'status.json')
    open_refs = [x['ref'] for x in r['items'] if x['verdict'] == 'disagree'] + [f'M{j}' for j in range(len(r['missed']))]
    st['q5'].update(stage='reviewed', disagreements=open_refs, reviewed_at=time.time())
    C.dump(folder(eid) / 'status.json', st)
    print('RECORDED ' + json.dumps(dict(items=len(refs), disagreements=open_refs)))
    return 0


def resolve(eid, path, corrected=None):
    st = C.read(folder(eid) / 'status.json')
    q = st.get('q5') or {}
    res = C.read(path)
    got = sorted(x.get('ref') for x in res.get('items', []))
    if q.get('stage') != 'reviewed' or not q.get('disagreements'):
        raise SystemExit(f'{eid}: no recorded Q5 review disagreements to resolve')
    if got != sorted(q['disagreements']) or any(x.get('decision') not in ('keep_q5', 'adopt_review') or not x.get('basis')
                                                for x in res['items']):
        raise SystemExit(f'resolution must rule on exactly {q["disagreements"]} with decision keep_q5/adopt_review and a basis')
    adopt = any(x['decision'] == 'adopt_review' for x in res['items'])
    if adopt:
        if not corrected:
            raise SystemExit('adopting a review alternative needs corrected q5 ops')
        C.dump(folder(eid) / 'q5_ops_before_resolution.json', C.read(folder(eid) / 'q5_ops_applied.json'))
        apply(eid, corrected, q.get('producer', 'claude_code_subagent_sonnet') + '+main_session_resolution')
        st = C.read(folder(eid) / 'status.json')
    C.dump(folder(eid) / 'q5_resolution.json', res)
    st['q5'].update(stage='resolved', resolution_changed_contract=adopt, resolved_at=time.time(),
                    disagreements=q['disagreements'])
    C.dump(folder(eid) / 'status.json', st)
    print('RESOLVED ' + json.dumps(dict(changed=adopt)))


def done(st):
    q = st.get('q5') or {}
    return q.get('stage') == 'resolved' or (q.get('stage') == 'reviewed' and not q.get('disagreements'))


def status():
    rows = [C.read(folder(j['episode_id']) / 'status.json') for j in C.manifest()['episodes']]
    stages = {}
    for r in rows:
        stage = (r.get('q5') or {}).get('stage', 'pending')
        stages[stage] = stages.get(stage, 0) + 1
    totals = {rule: sum((r.get('q5') or {}).get('rules', {}).get(rule, 0) for r in rows) for rule in RULES}
    open_rows = [(r['episode_id'], r['q5']['disagreements']) for r in rows
                 if (r.get('q5') or {}).get('stage') == 'reviewed' and r['q5'].get('disagreements')]
    print(json.dumps(dict(stages=stages, ops_by_rule=totals, open_disagreements=len(open_rows), complete=sum(map(done, rows)))))
    for eid, refs in open_rows:
        print(eid, refs)


def export():
    rows = [C.read(folder(j['episode_id']) / 'status.json') for j in C.manifest()['episodes']]
    pending = [r['episode_id'] for r in rows if not done(r)]
    if pending:
        raise SystemExit(f'{len(pending)} episodes are not complete in the Q5 pass, e.g. {pending[:5]}')
    C.export()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['show', 'check', 'apply', 'review-show', 'review-record', 'resolve', 'status', 'export'])
    p.add_argument('target', nargs='*')
    p.add_argument('--producer', default='claude_code_subagent_sonnet')
    a = p.parse_args()
    if a.command == 'show':
        show(*a.target)
    elif a.command == 'check':
        sys.exit(check(*a.target))
    elif a.command == 'apply':
        apply(*a.target, a.producer)
    elif a.command == 'review-show':
        review_show(*a.target)
    elif a.command == 'review-record':
        sys.exit(review_record(*a.target))
    elif a.command == 'resolve':
        resolve(*a.target)
    elif a.command == 'status':
        status()
    else:
        export()
