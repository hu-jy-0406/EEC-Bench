#!/usr/bin/env python3
"""Clean v2 episode contracts so that they hold only requirements the prompt fixes clearly.

Owner decision 2026-10-31 (README.md): wording with more than one reasonable reading yields no
requirement, and the `unresolved` field is dropped. The one exception is entity identity: whether
mentions in different shots are the same entity is decided by the most likely reading in context.

Cleanup agents (Claude Code subagents on Sonnet) write per-episode operations (ops.json). This program
applies them to the frozen v2 contract, validates the result and writes the cleaned contract. A second,
independent agent then reviews every identity decision and every change (review.json). The v2 inputs are
never modified.

Commands (lightweight; run from this directory):
  python3 cleanup.py prepare --start 0 --count 200    register episodes by generation priority
  python3 cleanup.py show EPISODE_ID                   compact input for the cleanup agent
  python3 cleanup.py check EPISODE_ID OPS_JSON         apply + validate; prints PASS/FAIL and the changes
  python3 cleanup.py finalize EPISODE_ID OPS_JSON      write the cleaned contract files
  python3 cleanup.py review-show EPISODE_ID            input for the independent review agent
  python3 cleanup.py review-record EPISODE_ID REVIEW_JSON
  python3 cleanup.py status
  python3 cleanup.py export
"""
import argparse
import collections
import copy
import hashlib
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
V2 = ROOT / 'EECBench/experiments/episode_contracts_v2_20261029/deliverables/episodes'
QUEUE = ROOT / 'EECBench/experiments/source_video_priority_20260921/generation_queue_400.ids.txt'
DIMS = ('appearance', 'spatial', 'motion')
LABEL_ORDER = ('character', 'location', 'object')
FRAMES = ('none', 'screen', 'camera', 'entity', 'world')
QUANTS = ('exists', 'start', 'end', 'throughout', 'when_visible')
NOTE_KINDS = ('already_omitted', 'non_identity_choice', 'identity', 'not_an_ambiguity', 'owner_deferred')
NOTE_RESOLUTIONS = ('drop_note', 'removed', 'narrowed', 'kept_sole_reading', 'identity_decided', 'kept_unchanged')
STRIP = ('evidence', 'source_claim_ids', 'source_labels', 'origin', 'prompt', 'cleanup')


# ---------------------------------------------------------------- io
def read(path):
    return json.loads(Path(path).read_text())


def dump(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def norm(text):
    return re.sub(r'\s+', ' ', text).strip()


def manifest():
    return read(HERE / 'manifest.json')


def load_input(eid):
    job = next((j for j in manifest()['episodes'] if j['episode_id'] == eid), None)
    if job is None:
        raise SystemExit(f'{eid} is not registered; run prepare first.')
    src = V2 / eid / 'contract_with_evidence.json'
    if sha(src) != job['source_sha256']:
        raise SystemExit(f'{eid}: the v2 input changed since prepare.')
    return read(src)


def texts_of(c):
    t = {'global': c['prompt']['global_prompt']}
    t.update({s['shot_id']: s['text'] for s in c['prompt']['shots']})
    return t


def quote_ok(texts, shot_id, quote):
    return shot_id in texts and bool(quote.strip()) and norm(quote) in norm(texts[shot_id])


def model_facing(obj):
    if isinstance(obj, dict):
        out = {k: model_facing(v) for k, v in obj.items() if k not in STRIP}
        return out['value'] if set(out) == {'value'} else out
    if isinstance(obj, list):
        return [model_facing(x) for x in obj]
    return obj


# ---------------------------------------------------------------- prepare / show
def prepare(start, count):
    queue = [x.strip() for x in QUEUE.read_text().splitlines() if x.strip()]
    path = HERE / 'manifest.json'
    m = read(path) if path.exists() else dict(queue=str(QUEUE.relative_to(ROOT)), source=str(V2.relative_to(ROOT)), episodes=[])
    known = {j['episode_id']: j for j in m['episodes']}
    for i in range(start, start + count):
        eid = queue[i]
        h = sha(V2 / eid / 'contract_with_evidence.json')
        if eid in known:
            if known[eid]['source_sha256'] != h:
                raise SystemExit(f'{eid}: registered with a different input hash')
            continue
        m['episodes'].append(dict(index=i, episode_id=eid, source_sha256=h))
    m['episodes'].sort(key=lambda j: j['index'])
    dump(path, m)
    print(json.dumps(dict(registered=len(m['episodes']), range=[start, start + count])))


def mentions(c):
    """(entity id str, shot_id) -> exact quotes from that shot that refer to the entity."""
    out = collections.defaultdict(list)
    for k, e in c['entity_descriptions'].items():
        for q in e.get('evidence', []):
            out[(k, q['shot_id'])].append(q['quote'])
    for s in c['shots']:
        for dim in DIMS:
            for it in s[dim]:
                for k in it['entities']:
                    out[(str(k), s['shot_id'])] += [q['quote'] for q in it.get('evidence', []) if q['shot_id'] == s['shot_id']]
    return {key: list(dict.fromkeys(v)) for key, v in out.items()}


def fmt_req(it, names, dim=None):
    ents = ', '.join(f'{k} {names.get(str(k), "?")}' for k in it['entities'])
    parts = [it['id'], dim or it.get('dimension', ''), f'[{ents}]']
    if 'shot_ids' in it:
        parts.append(','.join(it['shot_ids']))
    if 'predicate' in it:
        parts += [it['predicate'], f'frame={it["coordinate_frame"]}']
    parts += [f'quant={it["quantifier"]}', it['expected']]
    ev = '; '.join(f'[{q["shot_id"]}] "{q["quote"]}"' for q in it.get('evidence', []))
    return ' | '.join(parts) + (f'  <- {ev}' if ev else '')


def shots_of(c, key):
    # String comparison also serves a working copy, whose keys are strings ("7", "7.0"; q5_pass.py renders it).
    return [s['shot_id'] for s in c['shots'] if str(key) in map(str, s['presence'] + s['absent'])]


def render_text(c, notes=True):
    names = {k: e['name'] for k, e in c['entity_descriptions'].items()}
    out = [f'EPISODE {c["episode_id"]}', '', '== PROMPT', f'global: {c["prompt"]["global_prompt"]}']
    out += [f'{s["shot_id"]}: {s["text"]}' for s in c['prompt']['shots']]
    out += ['', '== ENTITIES (id | label | name | shots in presence/absent | description)']
    for k, e in c['entity_descriptions'].items():
        out.append(f'{k} | {e["label"]} | {e["name"]} | {",".join(shots_of(c, k)) or "-"} | {e["description"]}')
        out.append('    evidence: ' + '; '.join(f'[{q["shot_id"]}] "{q["quote"]}"' for q in e.get('evidence', [])))
    out += ['', '== SHOTS']
    for s in c['shots']:
        sd = s['shot_description']
        cam = {f: (None if sd[f] is None else f'{sd[f]["value"]} <- ' + '; '.join(f'"{q["quote"]}"' for q in sd[f]['evidence']))
               for f in ('camera_view', 'camera_movement', 'style')}
        out += [f'-- {s["shot_id"]} | locations: {", ".join(f"{k} {names[str(k)]}" for k in s["locations"]) or "-"}',
                f'   camera_view: {cam["camera_view"]}', f'   camera_movement: {cam["camera_movement"]}',
                f'   style: {cam["style"]}',
                '   presence: ' + ', '.join(f'{k} {names[str(k)]}' for k in s['presence']),
                '   absent: ' + (', '.join(f'{k} {names[str(k)]}' for k in s['absent']) or '-')]
        for dim in DIMS:
            out += ['   ' + fmt_req(it, names, dim) for it in s[dim]]
    out += ['', '== CROSS_SHOT'] + ([fmt_req(it, names) for it in c['cross_shot']] or ['(none)'])
    if notes:
        out += ['', '== UNRESOLVED NOTES (give each exactly one disposition, by number)']
        out += [f'N{i}: {u}' for i, u in enumerate(c.get('unresolved', []), 1)] or ['(none)']
    return '\n'.join(out)


def show(eid):
    print(render_text(load_input(eid)))


# ---------------------------------------------------------------- apply
class Contract:
    """Mutable working copy with string entity keys; ids are renumbered at the end."""

    def __init__(self, c):
        self.c = copy.deepcopy(c)
        self.texts = texts_of(c)
        self.shot_ids = [s['shot_id'] for s in c['shots']]
        self.ents = collections.OrderedDict((k, copy.deepcopy(e)) for k, e in c['entity_descriptions'].items())
        for s in self.c['shots']:
            for f in ('locations', 'presence', 'absent'):
                s[f] = [str(x) for x in s[f]]
            for dim in DIMS:
                for it in s[dim]:
                    it['entities'] = [str(x) for x in it['entities']]
        for it in self.c['cross_shot']:
            it['entities'] = [str(x) for x in it['entities']]
        self.changed_items, self.changed_entities = set(), set()
        self.owner = {(k, sid): k for k in self.ents for sid in self.shot_ids}  # (input key, shot) -> current key
        self.removed = []

    def items(self):
        for s in self.c['shots']:
            for dim in DIMS:
                for it in s[dim]:
                    yield s, dim, it
        for it in self.c['cross_shot']:
            yield None, it['dimension'], it

    def find(self, rid):
        for s, dim, it in self.items():
            if it['id'] == rid:
                return s, dim, it
        raise ValueError(f'unknown requirement id {rid}')

    def remove_item(self, rid):
        s, dim, it = self.find(rid)
        (s[dim] if s is not None else self.c['cross_shot']).remove(it)
        self.removed.append(rid)

    def key(self, x, what):
        k = str(x)
        if k not in self.ents:
            raise ValueError(f'{what}: unknown entity {x}')
        return k

    def replace_refs(self, old, new_by_shot):
        """Replace entity key old; new_by_shot(shot_id or None, item) -> list of keys ([] removes the reference)."""
        for s in self.c['shots']:
            for f in ('locations', 'presence', 'absent'):
                if old in s[f]:
                    i = s[f].index(old)
                    rep = [k for k in new_by_shot(s['shot_id'], None) if k not in s[f]]
                    s[f][i:i + 1] = rep
        for s, dim, it in list(self.items()):
            if old in it['entities']:
                i = it['entities'].index(old)
                rep = new_by_shot(s['shot_id'] if s is not None else None, it)
                it['entities'][i:i + 1] = [k for k in rep if k not in it['entities']]
                self.changed_items.add(it['id'])


def apply_ops(c, ops):
    w = Contract(c)
    err = []
    for n, op in enumerate(ops['ops']):
        tag = f'ops[{n}] {op.get("op")}'
        try:
            if not str(op.get('reason', '')).strip():
                raise ValueError('needs a reason')
            kind = op.get('op')
            if kind == 'remove_requirement':
                w.remove_item(op['id'])
            elif kind == 'rewrite_requirement':
                s, dim, it = w.find(op['id'])
                fields = [f for f in ('expected', 'predicate', 'coordinate_frame', 'quantifier', 'entities') if f in op]
                if not fields:
                    raise ValueError('changes nothing')
                if 'predicate' in op and dim == 'appearance':
                    raise ValueError('appearance requirements have no predicate')
                if 'coordinate_frame' in op and op['coordinate_frame'] not in FRAMES:
                    raise ValueError(f'coordinate_frame must be one of {FRAMES}')
                if 'quantifier' in op and op['quantifier'] not in QUANTS:
                    raise ValueError(f'quantifier must be one of {QUANTS}')
                if 'entities' in op:
                    new = [w.key(x, tag) for x in op['entities']]
                    if not new or not set(new) <= set(it['entities']):
                        raise ValueError('entities may only be reduced to a non-empty subset')
                    op = dict(op, entities=new)
                if 'expected' in op and not op['expected'].strip():
                    raise ValueError('expected must not be empty')
                for f in fields:
                    it[f] = op[f]
                w.changed_items.add(it['id'])
            elif kind == 'set_camera':
                s = next((x for x in w.c['shots'] if x['shot_id'] == op['shot_id']), None)
                if s is None or op.get('field') not in ('camera_view', 'camera_movement'):
                    raise ValueError('needs a valid shot_id and field camera_view/camera_movement')
                old = s['shot_description'][op['field']]
                if op.get('value') is None:
                    s['shot_description'][op['field']] = None
                else:
                    quotes = op.get('quotes') or []
                    if not op['value'].strip() or not quotes:
                        raise ValueError('a non-null value needs text and at least one quote')
                    bad = [q for q in quotes if not (quote_ok(w.texts, s['shot_id'], q) or quote_ok(w.texts, 'global', q))]
                    if bad:
                        raise ValueError(f'quotes not found in {s["shot_id"]} or global: {bad}')
                    s['shot_description'][op['field']] = dict(
                        value=op['value'], evidence=[dict(shot_id=s['shot_id'] if quote_ok(w.texts, s['shot_id'], q) else 'global', quote=q) for q in quotes],
                        source_claim_ids=(old or {}).get('source_claim_ids', []))
                w.changed_items.add(f'{s["shot_id"]}.{op["field"]}')
            elif kind == 'camera_to_cross_shot':
                # A camera value that only compares this shot's view with another shot belongs in cross_shot.
                s = next((x for x in w.c['shots'] if x['shot_id'] == op['shot_id']), None)
                if s is None or op.get('field') not in ('camera_view', 'camera_movement'):
                    raise ValueError('needs a valid shot_id and field camera_view/camera_movement')
                old = s['shot_description'][op['field']]
                shots = op['shot_ids']
                if old is None or s['shot_id'] not in shots or len(shots) < 2 or any(sid not in w.shot_ids for sid in shots):
                    raise ValueError('needs a non-null camera value and shot_ids with this shot and at least one other shot')
                new = [w.key(x, tag) for x in op['entities']]
                if not new or not op.get('expected', '').strip() or not op.get('predicate', '').strip():
                    raise ValueError('needs entities, expected and predicate')
                number = 1 + max([int(it['id'].split('-')[1]) for it in w.c['cross_shot']], default=0)
                w.c['cross_shot'].append(dict(id=f'X-{number}', shot_ids=shots, dimension='spatial', entities=new,
                                              expected=op['expected'], predicate=op['predicate'], coordinate_frame='camera',
                                              quantifier='cross_shot', evidence=old['evidence'],
                                              source_claim_ids=old.get('source_claim_ids', [])))
                keep = op.get('keep')  # the words that state this shot's own view stay in the field
                if keep is not None:
                    bad = [q for q in keep['quotes'] if not (quote_ok(w.texts, s['shot_id'], q) or quote_ok(w.texts, 'global', q))]
                    if not keep['value'].strip() or not keep['quotes'] or bad:
                        raise ValueError(f'keep needs a value and quotes found in {s["shot_id"]} or global: {bad}')
                    keep = dict(value=keep['value'], source_claim_ids=old.get('source_claim_ids', []),
                                evidence=[dict(shot_id=s['shot_id'] if quote_ok(w.texts, s['shot_id'], q) else 'global', quote=q) for q in keep['quotes']])
                s['shot_description'][op['field']] = keep
                w.changed_items.update((f'X-{number}', f'{s["shot_id"]}.{op["field"]}'))
            elif kind == 'edit_description':
                k = w.key(op['entity'], tag)
                if not op.get('description', '').strip():
                    raise ValueError('description must not be empty')
                # Optional quotes (Q5 pass, 2026-11-05): an added attribute carries the prompt words it rests on.
                quotes = op.get('quotes') or []
                bad = [q for q in quotes if not quote_ok(w.texts, q.get('shot_id', ''), q.get('quote', ''))]
                if bad:
                    raise ValueError(f'quotes not found in their shot (or global): {bad}')
                w.ents[k]['description'] = op['description']
                w.ents[k]['evidence'] = w.ents[k].get('evidence', []) + [
                    dict(shot_id=q['shot_id'], quote=q['quote']) for q in quotes
                    if dict(shot_id=q['shot_id'], quote=q['quote']) not in w.ents[k].get('evidence', [])]
                w.changed_entities.add(k)
            elif kind == 'add_requirement':
                # Q5 pass (2026-11-05): lighting that is a state of one shot becomes that shot's appearance requirement.
                s = next((x for x in w.c['shots'] if x['shot_id'] == op.get('shot_id')), None)
                dim = op.get('dimension')
                if s is None or dim not in DIMS:
                    raise ValueError(f'needs a valid shot_id and dimension in {DIMS}')
                new = [w.key(x, tag) for x in op.get('entities') or []]
                if not new or not op.get('expected', '').strip():
                    raise ValueError('needs entities and expected')
                if op.get('quantifier') not in QUANTS:
                    raise ValueError(f'quantifier must be one of {QUANTS}')
                if dim == 'appearance' and ('predicate' in op or 'coordinate_frame' in op):
                    raise ValueError('appearance requirements have no predicate or coordinate_frame')
                if dim != 'appearance' and (not op.get('predicate', '').strip() or op.get('coordinate_frame') not in FRAMES):
                    raise ValueError(f'a {dim} requirement needs a predicate and a coordinate_frame in {FRAMES}')
                quotes = op.get('quotes') or []
                bad = [q for q in quotes if not (quote_ok(w.texts, s['shot_id'], q) or quote_ok(w.texts, 'global', q))]
                if not quotes or bad:
                    raise ValueError(f'needs quotes found in {s["shot_id"]} or global (not found: {bad})')
                index = w.shot_ids.index(s['shot_id']) + 1
                short = dict(appearance='app', spatial='spa', motion='mot')[dim]
                used = [int(it['id'].rsplit('-', 1)[1]) for it in s[dim] if it['id'].startswith(f'S{index}-{short}-')]
                rid = f'S{index}-{short}-{max(used, default=0) + 1}'
                item = dict(id=rid, entities=new, expected=op['expected'], quantifier=op['quantifier'])
                if dim != 'appearance':
                    item.update(predicate=op['predicate'], coordinate_frame=op['coordinate_frame'])
                item['evidence'] = [dict(shot_id=s['shot_id'] if quote_ok(w.texts, s['shot_id'], q) else 'global', quote=q)
                                    for q in quotes]
                item['source_claim_ids'] = []
                s[dim].append(item)
                w.changed_items.add(rid)
            elif kind == 'merge_entities':
                into = w.key(op['into'], tag)
                merge = [w.key(x, tag) for x in op['merge']]
                if not merge or into in merge or len(set(merge)) != len(merge):
                    raise ValueError('merge must list other, distinct entities')
                if op.get('label') is not None:
                    if op['label'] not in LABEL_ORDER:
                        raise ValueError(f'label must be one of {LABEL_ORDER}')
                    w.ents[into]['label'] = op['label']
                for m in merge:
                    if op.get('label') is None and w.ents[m]['label'] != w.ents[into]['label']:
                        raise ValueError(f'cannot merge a {w.ents[m]["label"]} into a {w.ents[into]["label"]} without giving "label"')
                if not op.get('description', '').strip():
                    raise ValueError('give the merged description')
                e = w.ents[into]
                e['description'] = op['description']
                if op.get('name'):
                    e['name'] = op['name']
                e['evidence'] = list({json.dumps(q, sort_keys=True): q for m in [into] + merge for q in w.ents[m].get('evidence', [])}.values())
                e['source_labels'] = list(dict.fromkeys(sum((w.ents[m].get('source_labels', []) for m in [into] + merge), [])))
                e['cleanup'] = dict(merged_from=[w.ents[m]['name'] for m in merge])
                for m in merge:
                    w.replace_refs(m, lambda sid, it: [into])
                    for key, cur in w.owner.items():
                        if cur == m:
                            w.owner[key] = into
                    del w.ents[m]
                w.changed_entities.add(into)
            elif kind == 'split_entity':
                k = w.key(op['entity'], tag)
                parts = op.get('parts') or []
                if len(parts) < 2:
                    raise ValueError('a split needs at least two parts')
                where = set(shots_of_working(w, k))
                claimed = [sid for p in parts for sid in p.get('shots', [])]
                if len(claimed) != len(set(claimed)) or set(claimed) != where:
                    raise ValueError(f'part shots must partition the entity\'s shots exactly: {sorted(where, key=w.shot_ids.index)}')
                base = w.ents[k]
                new_keys = []
                for j, p in enumerate(parts):
                    if not p.get('name', '').strip() or not p.get('description', '').strip() or not p.get('evidence'):
                        raise ValueError(f'part {j} needs name, description and evidence')
                    bad = [q for q in p['evidence'] if not quote_ok(w.texts, q.get('shot_id', ''), q.get('quote', ''))]
                    if bad:
                        raise ValueError(f'part {j}: evidence quotes not found: {bad}')
                    nk = f'{k}.{j}'
                    w.ents[nk] = dict(label=base['label'], name=p['name'], description=p['description'],
                                      evidence=[dict(shot_id=q['shot_id'], quote=q['quote']) for q in p['evidence']],
                                      origin=base.get('origin'), source_labels=base.get('source_labels', []),
                                      cleanup=dict(split_from=base['name']))
                    new_keys.append(nk)
                    w.changed_entities.add(nk)
                part_of = {sid: new_keys[j] for j, p in enumerate(parts) for sid in p['shots']}
                reassign = {r['id']: r.get('to_parts') for r in op.get('cross_shot_reassign', [])}
                cross_refs = [it['id'] for it in w.c['cross_shot'] if k in it['entities']]
                if set(reassign) != set(cross_refs):
                    raise ValueError(f'cross_shot_reassign must list exactly the cross-shot items that reference the entity: {cross_refs}')
                drop = []
                for rid, to in reassign.items():
                    if to is None or any(t not in range(len(parts)) for t in to):
                        raise ValueError(f'{rid}: to_parts must be a list of part indices ([] removes the requirement)')
                    if not to:
                        drop.append(rid)

                def new_by_shot(sid, it, part_of=part_of, reassign=reassign, new_keys=new_keys):
                    if sid is None:
                        return [new_keys[t] for t in reassign[it['id']]]
                    return [part_of[sid]]
                w.replace_refs(k, new_by_shot)
                for rid in drop:
                    w.remove_item(rid)
                for key, cur in list(w.owner.items()):
                    if cur == k:
                        w.owner[key] = part_of.get(key[1], k)
                order = list(w.ents)
                pos = order.index(k)
                reordered = order[:pos] + new_keys + [x for x in order[pos + 1:] if x not in new_keys]
                w.ents = collections.OrderedDict((x, w.ents[x]) for x in reordered)
            elif kind == 'add_entity':
                # Granularity pass (owner, 2026-11-11): a worn or carried item or a place part the prompt names becomes its
                # own entity; it is listed only in the shots whose own prompt text mentions it (global: every shot listed).
                nk = str(op.get('id', ''))
                if not re.fullmatch(r'n[0-9]+', nk) or nk in w.ents:
                    raise ValueError('id must be a new key n1, n2, ...')
                if op.get('label') not in LABEL_ORDER:
                    raise ValueError(f'label must be one of {LABEL_ORDER}')
                if not op.get('name', '').strip() or not op.get('description', '').strip():
                    raise ValueError('needs name and description')
                ev = op.get('evidence') or []
                bad = [q for q in ev if not quote_ok(w.texts, q.get('shot_id', ''), q.get('quote', ''))]
                if not ev or bad:
                    raise ValueError(f'needs evidence quotes found in their shot or global (not found: {bad})')
                pres, absn = op.get('presence') or [], op.get('absent') or []
                if not pres or any(sid not in w.shot_ids for sid in pres + absn) or set(pres) & set(absn) \
                        or len(set(pres)) != len(pres) or len(set(absn)) != len(absn):
                    raise ValueError('presence (non-empty) and absent must list distinct, valid shot ids')
                cited = {q['shot_id'] for q in ev}
                uncited = [sid for sid in pres + absn if sid not in cited and 'global' not in cited]
                if uncited:
                    raise ValueError(f'every listed shot needs an evidence quote from that shot (or a global quote): {uncited}')
                w.ents[nk] = dict(label=op['label'], name=op['name'], description=op['description'],
                                  evidence=[dict(shot_id=q['shot_id'], quote=q['quote']) for q in ev],
                                  origin='granularity_pass_20261111', source_labels=[], cleanup=dict(added=op.get('rule')))
                for s in w.c['shots']:
                    if s['shot_id'] in pres:
                        s['presence'].append(nk)
                    if s['shot_id'] in absn:
                        s['absent'].append(nk)
                w.changed_entities.add(nk)
            elif kind == 'retarget_requirement':
                # Granularity pass: a requirement about a worn item or place part now refers to the item's own entity.
                s, dim, it = w.find(op['id'])
                new = [w.key(x, tag) for x in op.get('entities') or []]
                if not new or len(set(new)) != len(new) or new == it['entities']:
                    raise ValueError('entities must be a new, non-empty list of distinct entities')
                it['entities'] = new
                if 'expected' in op:
                    if not op['expected'].strip():
                        raise ValueError('expected must not be empty')
                    it['expected'] = op['expected']
                w.changed_items.add(it['id'])
            else:
                raise ValueError('unknown op (remove_requirement, rewrite_requirement, set_camera, camera_to_cross_shot, edit_description, '
                                 'add_requirement, merge_entities, split_entity, add_entity, retarget_requirement)')
        except (KeyError, TypeError) as e:
            err.append(f'{tag}: missing or malformed field {e}')
        except ValueError as e:
            err.append(f'{tag}: {e}')
    return w, err


def shots_of_working(w, k):
    out = []
    for s in w.c['shots']:
        refs = s['locations'] + s['presence'] + s['absent'] + [x for dim in DIMS for it in s[dim] for x in it['entities']]
        if k in refs:
            out.append(s['shot_id'])
    return out


def finish(w):
    """Renumber entities (characters, locations, objects; stable order) and validate. Returns contract, id map, errors, warnings."""
    err, warn = [], []
    keys = sorted(w.ents, key=lambda x: (LABEL_ORDER.index(w.ents[x]['label']), list(w.ents).index(x)))
    new_id = {k: i for i, k in enumerate(keys)}
    c = w.c
    names = [w.ents[k]['name'] for k in keys]
    dup = [n for n, m in collections.Counter(names).items() if m > 1]
    if dup:
        err.append(f'entity names must be unique: {dup}')
    for k in keys:
        e = w.ents[k]
        if not e['description'].strip():
            err.append(f'entity "{e["name"]}" has an empty description')
        bad = [q for q in e.get('evidence', []) if not quote_ok(w.texts, q['shot_id'], q['quote'])]
        if bad:
            (err if k in w.changed_entities else warn).append(f'entity "{e["name"]}": evidence quotes not found: {bad}')
        if not e.get('evidence'):
            err.append(f'entity "{e["name"]}" needs evidence')
    for s in c['shots']:
        style = s['shot_description']['style']
        for q in (style or {}).get('evidence', []):
            if not quote_ok(w.texts, q['shot_id'], q['quote']):
                err.append(f'{s["shot_id"]} style: quote not found: {q}')
        for f in ('locations', 'presence', 'absent'):
            if len(set(s[f])) != len(s[f]):
                err.append(f'{s["shot_id"]} {f}: duplicate entities')
        if set(s['presence']) & set(s['absent']):
            err.append(f'{s["shot_id"]}: entities both present and absent')
        for k in s['locations']:
            if w.ents[k]['label'] != 'location':
                err.append(f'{s["shot_id"]}: location {w.ents[k]["name"]} is not a location entity')
            if k not in s['presence']:
                err.append(f'{s["shot_id"]}: location {w.ents[k]["name"]} must be in presence')
        if len(s['locations']) > 2:
            err.append(f'{s["shot_id"]}: at most two locations')
        for dim in DIMS:
            for it in s[dim]:
                if not it['entities']:
                    err.append(f'{it["id"]}: no entities left')
                missing = [w.ents[k]['name'] for k in it['entities'] if k not in s['presence']]
                if missing:
                    (err if it['id'] in w.changed_items else warn).append(f'{it["id"]}: entities not in {s["shot_id"]} presence: {missing}')
    for it in c['cross_shot']:
        if not it['entities']:
            err.append(f'{it["id"]}: no entities left')
    used = {k for s in c['shots'] for k in s['presence'] + s['absent']}
    for k in keys:
        if k not in used:
            (err if k in w.changed_entities else warn).append(f'entity "{w.ents[k]["name"]}" is in no shot\'s presence or absent list')

    out = dict(schema_version=c['schema_version'], episode_id=c['episode_id'],
               entity_descriptions={str(new_id[k]): w.ents[k] for k in keys}, shots=[], cross_shot=[], prompt=c['prompt'])
    for s in c['shots']:
        s2 = dict(s)
        s2['locations'] = [new_id[k] for k in s['locations']]
        s2['presence'] = sorted(new_id[k] for k in s['presence'])
        s2['absent'] = sorted(new_id[k] for k in s['absent'])
        for dim in DIMS:
            s2[dim] = [dict(it, entities=[new_id[k] for k in it['entities']]) for it in s[dim]]
        out['shots'].append(s2)
    out['cross_shot'] = [dict(it, entities=[new_id[k] for k in it['entities']]) for it in c['cross_shot']]
    return out, new_id, err, warn


def validate_meta(c, ops, w, new_id):
    """Notes coverage and identity decisions consistent with the result."""
    err = []
    n_notes = len(c.get('unresolved', []))
    seen = collections.Counter()
    for row in ops.get('notes', []):
        try:
            seen[row['note']] += 1
            if row['kind'] not in NOTE_KINDS:
                err.append(f'note N{row["note"]}: kind must be one of {NOTE_KINDS}')
            if row['resolution'] not in NOTE_RESOLUTIONS:
                err.append(f'note N{row["note"]}: resolution must be one of {NOTE_RESOLUTIONS}')
            if not str(row.get('basis', '')).strip():
                err.append(f'note N{row["note"]}: needs a basis')
            if any(not isinstance(i, int) or not 0 <= i < len(ops['ops']) for i in row.get('ops', [])):
                err.append(f'note N{row["note"]}: ops must be indices into ops')
            if row['resolution'] in ('removed', 'narrowed') and not row.get('ops'):
                err.append(f'note N{row["note"]}: {row["resolution"]} needs the ops that do it')
        except (KeyError, TypeError) as e:
            err.append(f'notes: malformed row ({e})')
    want = set(range(1, n_notes + 1))
    if set(seen) != want or any(v > 1 for v in seen.values()):
        err.append(f'notes must cover N1..N{n_notes} exactly once each (got {sorted(seen.elements())})')
    shot_ids = [s['shot_id'] for s in c['shots']]
    for i, row in enumerate(ops.get('identity', []), 1):
        try:
            occ = row['occurrences']
            if row['decision'] not in ('same', 'separate') or not str(row.get('basis', '')).strip() or len(occ) < 2:
                err.append(f'identity I{i}: needs decision same/separate, a basis and at least two occurrences')
                continue
            finals = []
            for o in occ:
                k = str(o['entity'])
                if k not in c['entity_descriptions'] or not o['shots'] or any(sid not in shot_ids for sid in o['shots']):
                    err.append(f'identity I{i}: bad occurrence {o}')
                    break
                finals.append({w.owner[(k, sid)] for sid in o['shots']})
            else:
                if any(len(f) != 1 for f in finals):
                    err.append(f'identity I{i}: an occurrence spans shots that ended up as different entities')
                    continue
                f = [next(iter(x)) for x in finals]
                if row['decision'] == 'same' and len(set(f)) != 1:
                    err.append(f'identity I{i}: decided same, but the occurrences are still separate entities (merge them)')
                if row['decision'] == 'separate' and len(set(f)) != len(f):
                    err.append(f'identity I{i}: decided separate, but the occurrences are one entity (split it)')
        except (KeyError, TypeError) as e:
            err.append(f'identity I{i}: malformed ({e})')
    return err


def build(eid, ops_path):
    c = load_input(eid)
    ops = read(ops_path)
    if ops.get('episode_id') != eid:
        raise ValueError(f'ops.json episode_id must be {eid}')
    for key in ('notes', 'identity', 'ops'):
        if not isinstance(ops.get(key), list):
            raise ValueError(f'ops.json needs a list "{key}"')
    w, err = apply_ops(c, ops)
    if err:
        return c, ops, None, None, err, []
    out, new_id, err2, warn = finish(w)
    err = err2 + validate_meta(c, ops, w, new_id)
    return c, ops, (w, out), new_id, err, warn


def changes(c, w, out, new_id):
    """Readable list of what differs from the input."""
    names_in = {k: e['name'] for k, e in c['entity_descriptions'].items()}
    lines = [f'removed requirement {r}' for r in w.removed]
    for rid in sorted(w.changed_items):
        if '.' in rid:
            sid, f = rid.split('.')
            s = next(x for x in out['shots'] if x['shot_id'] == sid)
            v = s['shot_description'][f]
            lines.append(f'{sid} {f} -> {None if v is None else v["value"]}')
        elif rid not in w.removed:
            it = next((x for s in out['shots'] for d in DIMS for x in s[d] if x['id'] == rid), None) or \
                next(x for x in out['cross_shot'] if x['id'] == rid)
            lines.append(f'changed {rid}: {it["expected"]} (entities {it["entities"]})')
    for k in w.changed_entities:
        if k in w.ents:
            e = w.ents[k]
            lines.append(f'entity {new_id[k]} "{e["name"]}" {e.get("cleanup", "")}: {e["description"]}')
    gone = [names_in[k] for k in c['entity_descriptions'] if k not in w.ents]
    if gone:
        lines.append(f'entities removed by merge/split: {gone}')
    lines.append(f'entities {len(c["entity_descriptions"])} -> {len(out["entity_descriptions"])}; unresolved notes dropped: {len(c.get("unresolved", []))}')
    return lines


def check(eid, ops_path):
    folder = HERE / 'episodes' / eid
    try:
        c, ops, wo, new_id, err, warn = build(eid, ops_path)
    except (ValueError, json.JSONDecodeError) as e:
        err, warn, wo = [str(e)], [], None
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'check_log.jsonl').open('a') as f:
        f.write(json.dumps(dict(at=time.time(), file=str(ops_path), errors=len(err))) + '\n')
    if err:
        print('FAIL\n' + '\n'.join(dict.fromkeys(err)))
        return 1
    print('PASS')
    print('\n'.join(changes(c, *wo, new_id)))
    for x in warn:
        print('WARNING ' + x)
    return 0


def render_md(k):
    return (f'# Cleaned contract: {k["episode_id"]}\n\nModel-facing JSON: contract.json (no evidence).\n\n```\n'
            + render_text(k, notes=False) + '\n```\n')


def resolve(eid, resolution_path, ops_path=None):
    """Record the main session's ruling on review disagreements; re-finalize from corrected ops if any ruling adopts the review."""
    folder = HERE / 'episodes' / eid
    st = read(folder / 'status.json')
    res = read(resolution_path)
    if st.get('stage') != 'reviewed' or not st.get('disagreements'):
        raise SystemExit(f'{eid}: no recorded review disagreements to resolve')
    got = sorted(x['ref'] for x in res.get('items', []))
    if got != sorted(st['disagreements']) or any(x.get('decision') not in ('keep_cleanup', 'adopt_review', 'owner_rule') or not x.get('basis')
                                                 for x in res['items']):
        raise SystemExit(f'resolution must rule on exactly {st["disagreements"]} with decision keep_cleanup/adopt_review/owner_rule and a basis')
    adopt = any(x['decision'] == 'adopt_review' for x in res['items'])
    if adopt:
        if not ops_path:
            raise SystemExit('adopting a review alternative needs corrected ops')
        dump(folder / 'ops_before_resolution.json', read(folder / 'final_ops.json'))
        finalize(eid, ops_path, st['producer'] + '+main_session_resolution')
        st.update({k: v for k, v in read(folder / 'status.json').items() if k in ('notes', 'identity', 'ops', 'finalized_at')})
    dump(folder / 'resolution.json', res)
    st.update(stage='reviewed', resolved=True, resolution_changed_contract=adopt, resolved_at=time.time())
    dump(folder / 'status.json', st)
    print('RESOLVED ' + json.dumps(dict(changed=adopt)))


def finalize(eid, ops_path, producer):
    c, ops, wo, new_id, err, warn = build(eid, ops_path)
    if err:
        raise SystemExit('FAIL\n' + '\n'.join(err))
    w, out = wo
    folder = HERE / 'episodes' / eid
    dump(folder / 'final_ops.json', ops)
    dump(folder / 'contract_with_evidence.json', out)
    dump(folder / 'contract.json', model_facing(out))
    log = dict(episode_id=eid, source_sha256=sha(V2 / eid / 'contract_with_evidence.json'),
               ops_sha256=sha(folder / 'final_ops.json'), producer=producer,
               dropped_unresolved=c.get('unresolved', []), notes=ops['notes'], identity=ops['identity'], ops=ops['ops'],
               id_map={k: new_id[k] for k in new_id}, removed_requirements=w.removed,
               changes=changes(c, w, out, new_id), warnings=warn, finalized_at=time.time())
    dump(folder / 'cleanup_log.json', log)
    (folder / 'review.md').write_text(render_md(out))
    st = dict(episode_id=eid, stage='cleaned', producer=producer, notes=len(ops['notes']), identity=len(ops['identity']),
              ops=len(ops['ops']), review_items=len(ops['identity']) + len(ops['ops']), finalized_at=log['finalized_at'])
    dump(folder / 'status.json', st)
    print(json.dumps(st))


# ---------------------------------------------------------------- independent review
def review_items(eid):
    folder = HERE / 'episodes' / eid
    log = read(folder / 'cleanup_log.json')
    c = load_input(eid)
    names = {k: e['name'] for k, e in c['entity_descriptions'].items()}
    men = mentions(c)
    items = []
    for i, row in enumerate(log['identity'], 1):
        occ = []
        for o in row['occurrences']:
            k = str(o['entity'])
            quotes = [f'[{sid}] ' + ' / '.join(f'"{q}"' for q in men.get((k, sid), [])[:3]) for sid in o['shots']]
            occ.append(f'entity {k} "{names[k]}" in {",".join(o["shots"])}: ' + '; '.join(quotes))
        items.append(dict(ref=f'I{i}', text=f'IDENTITY decided "{row["decision"]}" for these occurrences:\n    ' + '\n    '.join(occ)))
    for j, op in enumerate(log['ops']):
        d = {k: v for k, v in op.items() if k != 'reason'}
        if op['op'] in ('remove_requirement', 'rewrite_requirement'):
            s, dim, it = Contract(c).find(op['id'])
            d['before'] = fmt_req(it, names, None if s is None else dim)
        if op['op'] == 'set_camera':
            s = next(x for x in c['shots'] if x['shot_id'] == op['shot_id'])
            v = s['shot_description'][op['field']]
            d['before'] = None if v is None else v['value']
        if op['op'] == 'edit_description':
            d['before'] = c['entity_descriptions'][str(op['entity'])]['description']
        items.append(dict(ref=f'O{j}', text='CHANGE ' + json.dumps(d, ensure_ascii=False)))
    return c, items


def review_show(eid):
    c, items = review_items(eid)
    print(render_text(dict(c, unresolved=[]), notes=False))
    print('\n== ITEMS TO REVIEW (one verdict each; entity ids above are the ORIGINAL ids)')
    for it in items:
        print(f'{it["ref"]}: {it["text"]}')
    if not items:
        print('(none)')


def review_record(eid, path):
    folder = HERE / 'episodes' / eid
    c, items = review_items(eid)
    r = read(path)
    refs = [x['ref'] for x in items]
    got = [x.get('ref') for x in r.get('items', [])]
    err = []
    if r.get('episode_id') != eid:
        err.append(f'episode_id must be {eid}')
    if sorted(got) != sorted(refs):
        err.append(f'items must cover exactly {refs} (got {got})')
    for x in r.get('items', []):
        if x.get('verdict') not in ('agree', 'disagree') or not str(x.get('basis', '')).strip():
            err.append(f'{x.get("ref")}: needs verdict agree/disagree and a basis')
        if x.get('verdict') == 'disagree' and not str(x.get('alternative', '')).strip():
            err.append(f'{x.get("ref")}: a disagreement needs the alternative you propose')
    if err:
        print('FAIL\n' + '\n'.join(err))
        return 1
    dump(folder / 'review.json', r)
    st = read(folder / 'status.json')
    st.update(stage='reviewed', disagreements=[x['ref'] for x in r['items'] if x['verdict'] == 'disagree'], reviewed_at=time.time())
    dump(folder / 'status.json', st)
    print('RECORDED ' + json.dumps(dict(items=len(refs), disagreements=st['disagreements'])))
    return 0


# ---------------------------------------------------------------- status / export
def status():
    rows = []
    for j in manifest()['episodes']:
        p = HERE / 'episodes' / j['episode_id'] / 'status.json'
        rows.append(read(p) if p.exists() else dict(episode_id=j['episode_id'], stage='pending'))
    cnt = collections.Counter(r['stage'] for r in rows)
    open_dis = [(r['episode_id'], r['disagreements']) for r in rows if r.get('disagreements') and not r.get('resolved')]
    no_items = sum(1 for r in rows if r.get('stage') == 'cleaned' and r.get('review_items') == 0)
    print(json.dumps(dict(stages=cnt, cleaned_without_review_items=no_items, open_disagreements=len(open_dis)), ensure_ascii=False))
    for eid, d in open_dis:
        print(eid, d)


def export():
    rows, plain, full = [], [], []
    for j in manifest()['episodes']:
        eid = j['episode_id']
        folder = HERE / 'episodes' / eid
        st = read(folder / 'status.json')
        done = st['stage'] == 'reviewed' and (not st.get('disagreements') or st.get('resolved'))
        done = done or (st['stage'] == 'cleaned' and st.get('review_items') == 0)
        if not done:
            raise SystemExit(f'{eid} is not complete ({st["stage"]}, disagreements {st.get("disagreements")})')
        c, ops, wo, new_id, err, warn = build(eid, folder / 'final_ops.json')
        assert not err and wo[1] == read(folder / 'contract_with_evidence.json'), eid
        plain.append(model_facing(wo[1]))
        full.append(wo[1])
        rows.append(dict(index=j['index'], episode_id=eid, **{k: st.get(k) for k in ('notes', 'identity', 'ops', 'disagreements', 'resolved')}))
    first, last = rows[0]['index'], rows[-1]['index']
    tag = f'{first + 1}_{last + 1}'
    dest = HERE / 'deliverables'
    dest.mkdir(exist_ok=True)
    for name, data in ((f'contracts_{tag}.jsonl', plain), (f'contracts_{tag}_with_evidence.jsonl', full)):
        (dest / name).write_text(''.join(json.dumps(r, ensure_ascii=False, separators=(',', ':')) + '\n' for r in data))
    dump(dest / f'index_{tag}.json', rows)
    print(json.dumps(dict(exported=len(rows), files=[f'contracts_{tag}.jsonl', f'contracts_{tag}_with_evidence.jsonl'])))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['prepare', 'show', 'check', 'finalize', 'review-show', 'review-record', 'resolve', 'status', 'export'])
    p.add_argument('target', nargs='*')
    p.add_argument('--start', type=int, default=0)
    p.add_argument('--count', type=int, default=200)
    p.add_argument('--producer', default='claude_code_subagent_sonnet')
    a = p.parse_args()
    if a.command == 'prepare':
        prepare(a.start, a.count)
    elif a.command == 'show':
        show(*a.target)
    elif a.command == 'check':
        sys.exit(check(*a.target))
    elif a.command == 'finalize':
        finalize(*a.target, a.producer)
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
