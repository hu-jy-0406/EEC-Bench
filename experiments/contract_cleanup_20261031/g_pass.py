#!/usr/bin/env python3
"""Granularity pass (owner, 2026-11-11): worn or carried items and place parts the prompt names become entities.

Owner: "所有类别都加吧，同步改contract"; presence only in shots whose own prompt text mentions the item ("只列该镜头文字提到的").
  G1 worn or carried items: clothing, trousers/skirts, footwear, headwear and hair accessories, eyewear, ties/scarves,
     jewelry/watches, belts/lanyards/badges/straps, gloves/aprons, bags;
  G2 place parts: walls, floors, ceilings, ground (reverses the Q5-4 ruling), floor coverings, trees/plants.
Rules for the agents: rules_g.txt; review: rules_g_review.txt.

Like q5_pass.py, the pass appends operations to each episode's cleanup operations (episodes/<id>/final_ops.json,
saved first as ops_before_g.json; it already contains the G operations) and re-finalizes with cleanup.py, so every
existing check still applies. New operations add_entity and retarget_requirement live in cleanup.py. A second,
independent agent reviews every operation and checked statement and looks for missed ones; the main session rules
on disagreements.

Commands (lightweight; run from this directory):
  python3 g_pass.py show EPISODE_ID                  cleaned contract + prompts + keyword hints
  python3 g_pass.py check EPISODE_ID G_OPS_JSON       PASS/FAIL and the exact change
  python3 g_pass.py apply EPISODE_ID G_OPS_JSON       re-finalize with the G operations
  python3 g_pass.py review-show EPISODE_ID
  python3 g_pass.py review-record EPISODE_ID REVIEW_JSON
  python3 g_pass.py resolve EPISODE_ID RESOLUTION_JSON [CORRECTED_G_OPS_JSON]
  python3 g_pass.py status
  python3 g_pass.py export                            after every episode is reviewed / resolved
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
RULES = ('G1', 'G2')
OUTCOMES = ('recorded', 'already_recorded', 'not_applicable')
G_OPS = ('add_entity', 'edit_description', 'retarget_requirement', 'rewrite_requirement', 'add_requirement',
         'remove_requirement')
HINTS = {
    'G1': re.compile(r'\b(shirt|blouse|jacket|coat|suit|sweater|cardigan|dress|gown|uniform|vest|hoodie|sweatshirt|blazer|'
                     r'robe|overalls|jumpsuit|tunic|kimono|top|t-shirt|tee|trousers|pants|jeans|skirt|shorts|slacks|leggings|'
                     r'shoes?|boots?|sneakers?|sandals?|heels|loafers?|slippers?|hat|cap|helmet|beanie|beret|hood|headscarf|'
                     r'bandana|turban|headband|hairpin|hair ?clip|ribbon|bow|glasses|spectacles|sunglasses|goggles|tie|necktie|'
                     r'bow ?tie|scarf|shawl|stole|necklace|earrings?|bracelets?|bangles?|rings?|watch|wristwatch|brooch|pendant|'
                     r'chain|jewel(?:le)?ry|belt|lanyard|badge|name ?tag|suspenders|braces|strap|gloves?|mittens?|apron|bag|'
                     r'handbag|backpack|purse|briefcase|satchel|tote|clothes|clothing|outfit|attire|wear\w*|dressed)s?\b', re.I),
    'G2': re.compile(r'\b(walls?|wallpaper|floors?|flooring|floorboards?|ceilings?|tiles?|tiled|ground|streets?|roads?|pavements?|'
                     r'sidewalks?|paths?|snow\w*|sand\w*|grass\w*|lawns?|dirt|gravel|mud\w*|ice|asphalt|cobble\w*|rugs?|'
                     r'carpets?|carpeting|mats?|doormats?|trees?|bush(?:es)?|shrubs?|hedges?|plants?|foliage|vegetation|'
                     r'palms?|forest|woods|flowers?)\b', re.I),
}


def folder(eid):
    return HERE / 'episodes' / eid


def base_ops(eid):
    """The cleanup operations before this pass (re-applying always starts from them)."""
    before = folder(eid) / 'ops_before_g.json'
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


def g_errors(eid, g):
    err = []
    if g.get('episode_id') != eid:
        err.append(f'episode_id must be {eid}')
    if not isinstance(g.get('ops'), list) or not isinstance(g.get('checked'), list):
        return err + ['g_ops.json needs lists "ops" and "checked"']
    for n, op in enumerate(g['ops']):
        if op.get('rule') not in RULES:
            err.append(f'ops[{n}]: "rule" must be one of {RULES}')
        if op.get('op') not in G_OPS:
            err.append(f'ops[{n}]: op must be one of {G_OPS}')
        if not str(op.get('reason', '')).strip():
            err.append(f'ops[{n}]: needs a reason')
    for n, row in enumerate(g['checked']):
        if row.get('rule') not in RULES or row.get('outcome') not in OUTCOMES or not str(row.get('basis', '')).strip() \
                or not str(row.get('quote', '')).strip() or not row.get('shot_id'):
            err.append(f'checked[{n}]: needs rule {RULES}, shot_id, quote, outcome {OUTCOMES} and basis')
        ops = row.get('ops', [])
        if not isinstance(ops, list) or any(not isinstance(i, int) or not 0 <= i < len(g['ops']) for i in ops):
            err.append(f'checked[{n}]: ops must be indices into ops')
        elif row.get('outcome') == 'recorded' and not ops:
            err.append(f'checked[{n}]: outcome recorded needs the ops that record it')
        elif row.get('outcome') != 'recorded' and ops:
            err.append(f'checked[{n}]: only outcome recorded lists ops')
    claimed = {i for row in g['checked'] for i in row.get('ops', []) if isinstance(i, int)}
    unclaimed = [i for i in range(len(g['ops'])) if i not in claimed]
    if unclaimed:
        err.append(f'ops {unclaimed} belong to no checked statement; every op records a checked statement')
    return err


def combine(eid, g):
    ops = base_ops(eid)
    combined = dict(ops, ops=ops['ops'] + [{k: v for k, v in op.items()} for op in g['ops']])
    path = folder(eid) / 'g_combined_ops.json'
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
        g = C.read(path)
        err = g_errors(eid, g)
        if not err:
            before, combined = combine(eid, g)
            _, _, wo, _, err2, warn = C.build(eid, combined)
            err += err2
    except (ValueError, json.JSONDecodeError, KeyError, TypeError) as e:
        err = [f'{type(e).__name__}: {e}']
    with (folder(eid) / 'g_check_log.jsonl').open('a') as f:
        f.write(json.dumps(dict(at=time.time(), file=str(path), errors=len(err))) + '\n')
    if err:
        print('FAIL\n' + '\n'.join(dict.fromkeys(err)))
        return 1
    if not quiet:
        print('PASS (contract lines removed "-" and added "+"; entity ids below are the renumbered final ids)')
        print('\n'.join(diff(eid, before, combined)) or '(no change)')
    return 0


def apply(eid, path, producer):
    q5 = (C.read(folder(eid) / 'status.json').get('q5') or {})
    if not (q5.get('stage') == 'resolved' or (q5.get('stage') == 'reviewed' and not q5.get('disagreements'))):
        raise SystemExit(f'{eid}: the Q5 pass is not complete')
    if check(eid, path, quiet=True):
        raise SystemExit(f'{eid}: run check until PASS first')
    g = C.read(path)
    st_before = C.read(folder(eid) / 'status.json')
    before = folder(eid) / 'ops_before_g.json'
    if not before.exists():
        C.dump(before, C.read(folder(eid) / 'final_ops.json'))
    _, combined = combine(eid, g)
    C.dump(folder(eid) / 'g_ops_applied.json', g)
    C.finalize(eid, combined, st_before['producer'])
    st = C.read(folder(eid) / 'status.json')
    st_before.update({k: st[k] for k in ('notes', 'identity', 'ops', 'finalized_at')})
    st_before['g'] = dict(stage='applied', producer=producer, ops=len(g['ops']), checked=len(g['checked']),
                           rules={r: sum(op['rule'] == r for op in g['ops']) for r in RULES}, applied_at=time.time())
    C.dump(folder(eid) / 'status.json', st_before)
    print('APPLIED ' + json.dumps(st_before['g']))


# ---------------------------------------------------------------- independent review
def review_items(eid):
    g = C.read(folder(eid) / 'g_ops_applied.json')
    items = [dict(ref=f'O{j}', text='CHANGE ' + json.dumps({k: v for k, v in op.items() if k != 'reason'}, ensure_ascii=False))
             for j, op in enumerate(g['ops'])]
    items += [dict(ref=f'C{j}', text='CHECKED ' + json.dumps(row, ensure_ascii=False)) for j, row in enumerate(g['checked'])]
    return g, items


def review_show(eid):
    c, w = working(eid, base_ops(eid))
    print(render_working(c, w).replace(f'EPISODE {eid}', f'EPISODE {eid} (cleaned contract BEFORE the granularity pass; ORIGINAL ids)', 1))
    _, items = review_items(eid)
    print('\n== RESULT OF THE GRANULARITY PASS (renumbered final ids)')
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
    C.dump(folder(eid) / 'g_review.json', r)
    st = C.read(folder(eid) / 'status.json')
    open_refs = [x['ref'] for x in r['items'] if x['verdict'] == 'disagree'] + [f'M{j}' for j in range(len(r['missed']))]
    st['g'].update(stage='reviewed', disagreements=open_refs, reviewed_at=time.time())
    C.dump(folder(eid) / 'status.json', st)
    print('RECORDED ' + json.dumps(dict(items=len(refs), disagreements=open_refs)))
    return 0


def resolve_show(eid):
    """review-show plus the reviewer's disagreements and missed mentions (input of the resolution step)."""
    review_show(eid)
    r = C.read(folder(eid) / 'g_review.json')
    st = C.read(folder(eid) / 'status.json').get('g') or {}
    print('\n== REVIEWER DISAGREEMENTS AND MISSED MENTIONS (rule on each ref listed under OPEN)')
    for x in r['items']:
        if x['verdict'] == 'disagree':
            print(f"{x['ref']}: {x['basis']}  ALTERNATIVE: {x['alternative']}")
    for j, m in enumerate(r['missed']):
        print(f"M{j}: [{m['rule']}] {m['shot_id']} \"{m['quote']}\"  PROPOSAL: {m['proposal']}")
    print('OPEN: ' + ' '.join(st.get('disagreements') or []))
    print('Current operations (g_ops_applied.json): episodes/' + eid + '/g_ops_applied.json')


def resolve(eid, path, corrected=None):
    st = C.read(folder(eid) / 'status.json')
    q = st.get('g') or {}
    res = C.read(path)
    got = sorted(x.get('ref') for x in res.get('items', []))
    if q.get('stage') != 'reviewed' or not q.get('disagreements'):
        raise SystemExit(f'{eid}: no recorded granularity review disagreements to resolve')
    if got != sorted(q['disagreements']) or any(x.get('decision') not in ('keep_g', 'adopt_review') or not x.get('basis')
                                                for x in res['items']):
        raise SystemExit(f'resolution must rule on exactly {q["disagreements"]} with decision keep_g/adopt_review and a basis')
    adopt = any(x['decision'] == 'adopt_review' for x in res['items'])
    if adopt:
        if not corrected:
            raise SystemExit('adopting a review alternative needs corrected g ops')
        C.dump(folder(eid) / 'g_ops_before_resolution.json', C.read(folder(eid) / 'g_ops_applied.json'))
        apply(eid, corrected, q.get('producer', 'claude_code_subagent_sonnet') + '+main_session_resolution')
        st = C.read(folder(eid) / 'status.json')
    C.dump(folder(eid) / 'g_resolution.json', res)
    st['g'].update(stage='resolved', resolution_changed_contract=adopt, resolved_at=time.time(),
                    disagreements=q['disagreements'])
    C.dump(folder(eid) / 'status.json', st)
    print('RESOLVED ' + json.dumps(dict(changed=adopt)))


def ruling(eid, path, note):
    """Main-session consistency ruling on a finished episode: apply corrected G operations, keep its review and
    resolution record, and note the ruling."""
    st = C.read(folder(eid) / 'status.json')
    before = dict(st.get('g') or {})
    if not done(st):
        raise SystemExit(f'{eid}: only a reviewed or resolved episode takes a main-session ruling')
    n = len(list(folder(eid).glob('g_ops_before_ruling_*.json')))
    C.dump(folder(eid) / f'g_ops_before_ruling_{n + 1}.json', C.read(folder(eid) / 'g_ops_applied.json'))
    apply(eid, path, 'main_session_ruling')
    st = C.read(folder(eid) / 'status.json')
    rulings = before.get('main_session_rulings', []) + [dict(at=time.time(), note=note, ops_file=str(Path(path).name))]
    st['g'] = dict(before, stage='resolved' if before.get('stage') == 'resolved' else before.get('stage'),
                   main_session_rulings=rulings)
    C.dump(folder(eid) / 'status.json', st)
    print('RULED ' + json.dumps(dict(episode=eid, rulings=len(rulings))))


def done(st):
    q = st.get('g') or {}
    return q.get('stage') == 'resolved' or (q.get('stage') == 'reviewed' and not q.get('disagreements'))


def status():
    rows = [C.read(folder(j['episode_id']) / 'status.json') for j in C.manifest()['episodes']]
    stages = {}
    for r in rows:
        stage = (r.get('g') or {}).get('stage', 'pending')
        stages[stage] = stages.get(stage, 0) + 1
    totals = {rule: sum((r.get('g') or {}).get('rules', {}).get(rule, 0) for r in rows) for rule in RULES}
    open_rows = [(r['episode_id'], r['g']['disagreements']) for r in rows
                 if (r.get('g') or {}).get('stage') == 'reviewed' and r['g'].get('disagreements')]
    print(json.dumps(dict(stages=stages, ops_by_rule=totals, open_disagreements=len(open_rows), complete=sum(map(done, rows)))))
    for eid, refs in open_rows:
        print(eid, refs)


def export():
    rows = [C.read(folder(j['episode_id']) / 'status.json') for j in C.manifest()['episodes']]
    pending = [r['episode_id'] for r in rows if not done(r)]
    if pending:
        raise SystemExit(f'{len(pending)} episodes are not complete in the granularity pass, e.g. {pending[:5]}')
    keep = HERE / 'g_20261111' / 'deliverables_before'
    if not keep.exists():
        import shutil
        shutil.copytree(HERE / 'deliverables', keep)
    C.export()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['show', 'check', 'apply', 'review-show', 'review-record', 'resolve-show', 'resolve',
                                       'ruling', 'status', 'export'])
    p.add_argument('--note', default='')
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
    elif a.command == 'ruling':
        ruling(*a.target, a.note)
    elif a.command == 'resolve-show':
        resolve_show(*a.target)
    elif a.command == 'resolve':
        resolve(*a.target)
    elif a.command == 'status':
        status()
    else:
        export()
