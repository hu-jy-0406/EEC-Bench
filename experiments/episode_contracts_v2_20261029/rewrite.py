#!/usr/bin/env python3
"""Rewrite the Full400 v1 episode contracts into the v2 layout.

Layout and rules: EECBench/docs/episode-contract-v2-format.md (owner decisions 2026-10-27/29).
Per episode, one configured Astra/medium call returns conversion DECISIONS (entity table, v1
entity dispositions, per-shot locations/camera/presence, exceptions to the default claim
mapping, new requirements). The program assembles the v2 contract from those decisions and the
unchanged v1 claims, and rejects it on any mechanical error (all errors go back to the model).
A fresh-context Astra/medium audit then checks the assembled contract and may return complete
revised decisions, which are assembled and validated the same way.

Commands (run on a compute node of an existing allocation; API/CPU only):
  python rewrite.py prepare
  python rewrite.py run --pilot | --episodes ID ... | --all  [--workers N] [--no-audit]
  python rewrite.py usage
  python rewrite.py export
"""
import argparse, collections, concurrent.futures, copy, json, os, re, socket, sys, tempfile, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'EECBench/scripts'))
import run_wedetect_shot_entities as io  # noqa: E402

read, dump, sha = io.read, io.dump, io.sha
V1 = ROOT / 'EECBench/experiments/episode_contracts_20260921/deliverables'
MODEL, REASONING = 'gpt-6-astra', 'medium'
MAX_REWRITE_ATTEMPTS, MAX_AUDIT_ATTEMPTS = 4, 3
LOCK = threading.Lock()
DISABLED = None

# ---------------------------------------------------------------- schemas
S = {'type': 'string'}


def obj(**props):
    return {'type': 'object', 'properties': props, 'required': list(props), 'additionalProperties': False}


def arr(item):
    return {'type': 'array', 'items': item}


def enum(*values):
    return {'type': 'string', 'enum': list(values)}


def nullable(schema):
    return {'anyOf': [schema, {'type': 'null'}]}


QUOTE = obj(fact_id=S, quote=S)
FRAMES = enum('none', 'screen', 'camera', 'entity', 'world')
QUANT = enum('exists', 'start', 'end', 'throughout', 'when_visible')
CAMERA = nullable(obj(value=S, quotes=arr(S)))
DECISIONS = obj(
    entities=arr(obj(label=enum('character', 'location', 'object'), name=S, description=S, evidence=arr(QUOTE),
                     v1_labels=arr(S), origin=enum('v1', 'split_from_description', 'newly_named'))),
    v1_entities=arr(obj(v1_label=S, action=enum('kept', 'merged_into_location', 'folded_into_owner',
                                                'merged_into_collection'), target=S, reason=S)),
    shots=arr(obj(shot_id=S, locations=arr(S), camera_view=CAMERA, camera_movement=CAMERA,
                  presence=arr(S), absent=arr(S))),
    appearance_keep=arr(obj(claim_id=S, reason=S)),
    camera_from_claims=arr(obj(claim_id=S, field=enum('camera_view', 'camera_movement'))),
    claim_entity_updates=arr(obj(claim_id=S, entities=arr(S))),
    claim_to_description=arr(obj(claim_id=S, entity=S)),
    dropped_claims=arr(obj(claim_id=S, reason=S)),
    new_requirements=arr(obj(shot_id=S, dimension=enum('appearance', 'spatial', 'motion'), entities=arr(S),
                             predicate=S, expected=S, coordinate_frame=FRAMES, quantifier=QUANT,
                             evidence=arr(QUOTE))),
    unresolved=arr(S))
AUDIT = obj(verdict=enum('pass', 'revised'), issues=arr(S), revised_decisions=nullable(DECISIONS))

LABEL_ORDER = ('character', 'location', 'object')
SURFACE = re.compile(r'\b(walls?|floors?|ceilings?)$', re.I)
WORN = re.compile(r'\b(badge|lanyard|glasses|sunglasses|watch|wristwatch|necklace|earrings?|ring|scarf|tie|hat|cap|'
                  r'helmet|bag|backpack|purse|handbag|coat|jacket|gloves?|belt|phone|smartphone|cup|mug|glass|'
                  r'knife|gun|pistol|rifle|cane|umbrella|book|notebook|camera|bottle)\b', re.I)


# ---------------------------------------------------------------- inputs
def norm(text):
    return re.sub(r'\s+', ' ', text).strip()


def texts_of(payload):
    t = {'global': payload['prompt']['global']}
    t.update({s['shot_id']: s['text'] for s in payload['prompt']['shots']})
    return t


def build_payload(eid):
    c = read(V1 / 'episodes' / eid / 'contract.json')
    shot_key = {s['shot_id']: s['schedule_key'] for s in c['prompt']['shots']}
    unscored = collections.defaultdict(list)
    for unit in c['coverage']:
        fact = unit['unit_id'].split('.')[0]
        unscored[fact] += [dict(quote=x['quote'], reason=x['reason']) for x in unit['unscored']]
    v1 = dict(
        entities=[dict(label=k, name=e['name'], description=e['description'],
                       evidence=[dict(fact_id=q['fact_id'], quote=q['quote']) for q in e['evidence']])
                  for k, e in c['entity_descriptions'].items()],
        schedule=[dict(shot_id=sid, **c['entity_schedule'][key]) for sid, key in shot_key.items()],
        claims=[{k: q[k] for k in ('claim_id', 'dimension', 'entity_ids', 'shot_ids', 'predicate', 'expected',
                                   'coordinate_frame', 'quantifier')} for q in c['claims']],
        unscored_text=[dict(fact_id=k, items=v) for k, v in unscored.items()],
        unresolved=c['unresolved'])
    prompt = {'global': c['prompt']['global_prompt'],
              'shots': [dict(shot_id=s['shot_id'], text=s['text']) for s in c['prompt']['shots']]}
    return dict(episode_id=eid, prompt=prompt, v1=v1), dict()


# ---------------------------------------------------------------- assembly
def assemble(dec, payload, meta, v1_contract):
    """Build the v2 contract (with evidence) from decisions; raise ValueError listing every error."""
    err, warn = [], []
    texts = texts_of(payload)
    shot_ids = [s['shot_id'] for s in payload['prompt']['shots']]
    v1_ent = v1_contract['entity_descriptions']
    claims = {q['claim_id']: q for q in v1_contract['claims']}

    def quote_ok(fact, quote):
        return fact in texts and quote.strip() and norm(quote) in norm(texts[fact])

    # entities
    ents = dec['entities']
    names = [e['name'] for e in ents]
    if len(set(names)) != len(names) or any(not n.strip() for n in names):
        err.append('Entity names must be unique and non-empty: ' + str([n for n, k in collections.Counter(names).items() if k > 1]))
    ranks = [LABEL_ORDER.index(e['label']) for e in ents]
    if ranks != sorted(ranks):
        err.append('Entities must be ordered: all characters, then all locations, then all objects.')
    by_name = {e['name']: e for e in ents}
    for e in ents:
        if e['label'] == 'object' and SURFACE.search(e['name'].strip()):
            err.append(f'Entity "{e["name"]}" is a wall/floor/ceiling; merge it into its location.')
        if not e['evidence']:
            err.append(f'Entity "{e["name"]}" needs at least one evidence quote.')
        for q in e['evidence']:
            if not quote_ok(q['fact_id'], q['quote']):
                err.append(f'Entity "{e["name"]}": quote not found in {q["fact_id"]}: "{q["quote"]}"')
        if (e['origin'] == 'v1') != bool(e['v1_labels']):
            err.append(f'Entity "{e["name"]}": origin v1 requires v1_labels, and only v1 entities have them.')

    # v1 dispositions
    disp = {}
    for row in dec['v1_entities']:
        if row['v1_label'] in disp:
            err.append(f'v1 entity {row["v1_label"]} has more than one disposition.')
        disp[row['v1_label']] = row
    missing = set(v1_ent) - set(disp)
    extra = set(disp) - set(v1_ent)
    if missing:
        err.append('v1 entities without a disposition: ' + ', '.join(sorted(missing)))
    if extra:
        err.append('Dispositions for unknown v1 labels: ' + ', '.join(sorted(extra)))
    target = {}
    for lab, row in disp.items():
        if lab not in v1_ent:
            continue
        t = by_name.get(row['target'])
        if t is None:
            err.append(f'{lab}: target "{row["target"]}" is not an entity.')
            continue
        target[lab] = t['name']
        if row['action'] == 'kept':
            if t['name'] != v1_ent[lab]['name']:
                err.append(f'{lab} is kept, so its v2 name must stay "{v1_ent[lab]["name"]}" (got "{t["name"]}").')
            if lab not in t['v1_labels']:
                err.append(f'{lab} is kept as "{t["name"]}", which must list it in v1_labels.')
        if row['action'] == 'merged_into_location' and t['label'] != 'location':
            err.append(f'{lab} is merged into a location, but "{t["name"]}" is not a location.')
        if t['name'] == v1_ent[lab]['name'] and row['action'] != 'kept':
            err.append(f'{lab} keeps its name "{t["name"]}" but is not marked kept.')
    for e in ents:
        for lab in e['v1_labels']:
            if lab not in v1_ent:
                err.append(f'Entity "{e["name"]}" lists unknown v1 label {lab}.')
            elif target.get(lab) != e['name']:
                err.append(f'Entity "{e["name"]}" lists {lab}, whose disposition targets "{target.get(lab)}".')

    ids = {e['name']: i for i, e in enumerate(ents)}

    # shots
    shots_in = dec['shots']
    if [s['shot_id'] for s in shots_in] != shot_ids:
        err.append(f'shots must list exactly {shot_ids} in order.')
    shot_dec = {s['shot_id']: s for s in shots_in}
    for s in shots_in:
        for field in ('presence', 'absent', 'locations'):
            unknown = [n for n in s[field] if n not in by_name]
            if unknown:
                err.append(f'{s["shot_id"]} {field}: unknown names {unknown}')
            if len(set(s[field])) != len(s[field]):
                err.append(f'{s["shot_id"]} {field}: duplicate names')
        if set(s['presence']) & set(s['absent']):
            err.append(f'{s["shot_id"]}: entities both present and absent: {sorted(set(s["presence"]) & set(s["absent"]))}')
        for n in s['locations']:
            if n in by_name and by_name[n]['label'] != 'location':
                err.append(f'{s["shot_id"]}: location "{n}" is not a location entity.')
            if n not in s['presence']:
                err.append(f'{s["shot_id"]}: location "{n}" must also be in presence.')
        if len(s['locations']) > 2:
            err.append(f'{s["shot_id"]}: at most two locations (two only when the camera moves between them).')
        for field in ('camera_view', 'camera_movement'):
            v = s[field]
            if v is not None:
                if not v['value'].strip() or not v['quotes']:
                    err.append(f'{s["shot_id"]} {field}: needs a value and at least one quote, or null.')
                for q in v['quotes']:
                    if not (quote_ok(s['shot_id'], q) or quote_ok('global', q)):
                        err.append(f'{s["shot_id"]} {field}: quote not found in the shot or global text: "{q}"')
    appearing = {n for s in shots_in for n in s['presence'] + s['absent']}
    for e in ents:
        if e['name'] not in appearing:
            (warn if e['origin'] == 'v1' else err).append(f'Entity "{e["name"]}" is in no shot\'s presence or absent list.')

    # claim decisions
    lists = {}
    for key in ('appearance_keep', 'camera_from_claims', 'claim_to_description', 'dropped_claims', 'claim_entity_updates'):
        lists[key] = {}
        for row in dec[key]:
            if row['claim_id'] not in claims:
                err.append(f'{key}: unknown v1 claim {row["claim_id"]}')
            elif row['claim_id'] in lists[key]:
                err.append(f'{key}: {row["claim_id"]} listed twice')
            lists[key][row['claim_id']] = row
    exclusive = ['appearance_keep', 'camera_from_claims', 'claim_to_description', 'dropped_claims']
    for cid in set().union(*[lists[k] for k in exclusive]):
        hits = [k for k in exclusive if cid in lists[k]]
        if len(hits) > 1:
            err.append(f'{cid} is in more than one of {hits}.')
    for cid in lists['claim_entity_updates']:
        if cid in lists['dropped_claims'] or cid in lists['claim_to_description'] or cid in lists['camera_from_claims']:
            err.append(f'{cid}: an entity update cannot be combined with drop / to-description / camera.')
        unknown = [n for n in lists['claim_entity_updates'][cid]['entities'] if n not in by_name]
        if unknown or not lists['claim_entity_updates'][cid]['entities']:
            err.append(f'claim_entity_updates {cid}: unknown or empty entities {unknown}')
    for cid, row in lists['appearance_keep'].items():
        if claims[cid]['dimension'] != 'appearance':
            err.append(f'appearance_keep {cid} is a {claims[cid]["dimension"]} claim.')
    for cid, row in lists['claim_to_description'].items():
        if row['entity'] not in by_name:
            err.append(f'claim_to_description {cid}: unknown entity "{row["entity"]}"')

    evidence = {e['name']: [dict(shot_id=q['fact_id'], quote=q['quote']) for q in e['evidence']] for e in ents}
    accounting = {}
    per_shot = {sid: {'appearance': [], 'spatial': [], 'motion': []} for sid in shot_ids}
    cross = []
    camera_sources = collections.defaultdict(list)

    def ev(q):
        return [dict(shot_id=x['fact_id'], quote=x['quote']) for x in q['evidence']]

    def mapped(q):
        out = []
        for lab in q['entity_ids']:
            n = target.get(lab)
            if n is not None and n not in out:
                out.append(n)
        return out

    for cid, q in claims.items():
        dim, sids = q['dimension'], q['shot_ids']
        touches_merged = any(disp.get(lab, {}).get('action', 'kept') != 'kept' for lab in q['entity_ids'])
        if cid in lists['dropped_claims']:
            accounting[cid] = dict(to='dropped', reason=lists['dropped_claims'][cid]['reason'])
            continue
        if cid in lists['camera_from_claims']:
            field = lists['camera_from_claims'][cid]['field']
            sid = sids[-1]
            if sid in shot_dec and shot_dec[sid][field] is None:
                err.append(f'{cid} moves into {sid} {field}, which is null.')
            camera_sources[(sid, field)].append(cid)
            accounting[cid] = dict(to='shot_description.' + field, shot_id=sid)
            continue
        if cid in lists['claim_to_description']:
            n = lists['claim_to_description'][cid]['entity']
            evidence.setdefault(n, []).extend(ev(q))
            accounting[cid] = dict(to='entity_description', entity=n)
            continue
        names_q = lists['claim_entity_updates'][cid]['entities'] if cid in lists['claim_entity_updates'] else mapped(q)
        if dim == 'presence':
            if len(sids) != 1 or len(names_q) != 1:
                err.append(f'{cid}: presence claim must have one shot and one entity.')
                continue
            field = 'presence' if q['predicate'] == 'present' else 'absent'
            if sids[0] in shot_dec and names_q[0] not in shot_dec[sids[0]][field]:
                err.append(f'{cid} ({q["predicate"]}): "{names_q[0]}" must be in {sids[0]} {field}.')
            accounting[cid] = dict(to=field, shot_id=sids[0], entity=names_q[0])
            continue
        if dim == 'appearance' and len(sids) == 1 and cid not in lists['appearance_keep']:
            if not names_q:
                err.append(f'{cid}: no target entity to fold into.')
                continue
            evidence.setdefault(names_q[0], []).extend(ev(q))
            accounting[cid] = dict(to='entity_description', entity=names_q[0])
            continue
        if touches_merged and dim != 'appearance' and cid not in lists['claim_entity_updates']:
            err.append(f'{cid} ({dim}) references a merged or folded v1 entity; give claim_entity_updates, '
                       f'claim_to_description or dropped_claims for it.')
            continue
        item = dict(entities=[ids[n] for n in names_q if n in ids], expected=q['expected'])
        if dim != 'appearance':
            item.update(predicate=q['predicate'], coordinate_frame=q['coordinate_frame'])
        item.update(quantifier=q['quantifier'], evidence=ev(q), source_claim_ids=[cid])
        if len(sids) == 1:
            sid = sids[0]
            if sid in shot_dec:
                absent_entities = [n for n in names_q if n not in shot_dec[sid]['presence']]
                if absent_entities:
                    warn.append(f'{cid}: entities not in {sid} presence: {absent_entities}')
            tag = {'appearance': 'app', 'spatial': 'spa', 'motion': 'mot'}[dim]
            item = dict(id=f'S{shot_ids.index(sid) + 1}-{tag}-{len(per_shot[sid][dim]) + 1}', **item)
            per_shot[sid][dim].append(item)
            accounting[cid] = dict(to=dim, shot_id=sid, id=item['id'])
        else:
            item = dict(id=f'X-{len(cross) + 1}', shot_ids=sids, dimension=dim, **item)
            cross.append(item)
            accounting[cid] = dict(to='cross_shot', id=item['id'])

    for k, r in enumerate(dec['new_requirements'], 1):
        sid = r['shot_id']
        if sid not in per_shot:
            err.append(f'new requirement {k}: unknown shot {sid}')
            continue
        unknown = [n for n in r['entities'] if n not in by_name]
        if unknown or not r['entities']:
            err.append(f'new requirement {k}: unknown or empty entities {unknown}')
            continue
        not_present = [n for n in r['entities'] if n not in shot_dec[sid]['presence']]
        if not_present:
            err.append(f'new requirement {k}: entities not in {sid} presence: {not_present}')
        if not r['evidence']:
            err.append(f'new requirement {k}: needs evidence.')
        for q in r['evidence']:
            if not quote_ok(q['fact_id'], q['quote']):
                err.append(f'new requirement {k}: quote not found in {q["fact_id"]}: "{q["quote"]}"')
        dim = r['dimension']
        tag = {'appearance': 'app', 'spatial': 'spa', 'motion': 'mot'}[dim]
        item = dict(id=f'S{shot_ids.index(sid) + 1}-{tag}-{len(per_shot[sid][dim]) + 1}',
                    entities=[ids[n] for n in r['entities']], expected=r['expected'])
        if dim != 'appearance':
            item.update(predicate=r['predicate'], coordinate_frame=r['coordinate_frame'])
        item.update(quantifier=r['quantifier'], evidence=[dict(shot_id=q['fact_id'], quote=q['quote']) for q in r['evidence']],
                    source_claim_ids=[])
        per_shot[sid][dim].append(item)

    assert not set(accounting) - set(claims)
    if err:
        raise ValueError('\n'.join(dict.fromkeys(err)))

    # granularity hints for the auditor
    motion_text = collections.defaultdict(str)
    for sid in shot_ids:
        for it in per_shot[sid]['spatial'] + per_shot[sid]['motion']:
            for i in it['entities']:
                motion_text[i] += ' ' + it['expected']
    for i, e in enumerate(ents):
        if e['label'] == 'object' and WORN.search(e['name']) and not motion_text[i]:
            warn.append(f'Object "{e["name"]}" has no spatial/motion requirement: check whether it is only worn/carried.')
        if e['label'] == 'character':
            actions = motion_text[i]
            for other in ents:  # entity names ("Dark-jacket visitor") are not item mentions
                actions = re.sub(re.escape(other['name']), ' ', actions, flags=re.I)
            for word in set(m.lower() for m in WORN.findall(e['description'])):
                if re.search(r'\b' + re.escape(word) + r'\b', actions, re.I):
                    warn.append(f'"{word}" in the description of "{e["name"]}" appears in its actions: check whether it should be a separate entity.')

    entities_out = {}
    for i, e in enumerate(ents):
        entities_out[str(i)] = dict(label=e['label'], name=e['name'], description=e['description'],
                                    evidence=dedup(evidence[e['name']]), origin=e['origin'], source_labels=e['v1_labels'])
    shots_out = []
    # A camera requirement on how this shot's view relates to another shot belongs in cross_shot
    # (owner, 2026-11-01); the decisions keep the camera value it came from.
    moved = {(r['shot_id'], r['field']): r for r in dec.get('camera_to_cross_shot', [])}
    # shot_styles: the visual or render style the prompt states for a shot (owner, 2026-11-01); null otherwise.
    styles = {r['shot_id']: r for r in dec.get('shot_styles', [])}
    for r in styles.values():
        for q in r['quotes']:
            if not quote_ok(q['fact_id'], q['quote']):
                raise ValueError(f'{r["shot_id"]} style: quote not found in {q["fact_id"]}: "{q["quote"]}"')
    for sid in shot_ids:
        s = shot_dec[sid]
        desc = {}
        for field in ('camera_view', 'camera_movement'):
            v = s[field]
            if (sid, field) in moved:
                r = moved[(sid, field)]
                sources = camera_sources.get((sid, field), [])
                cross.append(dict(id=f'X-{len(cross) + 1}', shot_ids=r['shot_ids'], dimension='spatial',
                                  entities=[ids[n] for n in r['entities']], expected=r['expected'], predicate=r['predicate'],
                                  coordinate_frame='camera', quantifier='cross_shot',
                                  evidence=[dict(shot_id=sid, quote=q) for q in v['quotes']], source_claim_ids=sources))
                accounting.update({cid: dict(to='cross_shot', id=cross[-1]['id']) for cid in sources})
                v = r.get('keep')  # the words that state this shot's own view stay in the field
            desc[field] = None if v is None else dict(value=v['value'], evidence=[dict(shot_id=sid, quote=q) for q in v['quotes']],
                                                     source_claim_ids=camera_sources.get((sid, field), []))
        style = styles.get(sid)
        desc['style'] = None if style is None else dict(value=style['value'], source_claim_ids=[],
                                                        evidence=[dict(shot_id=q['fact_id'], quote=q['quote']) for q in style['quotes']])
        shots_out.append(dict(shot_id=sid, locations=[ids[x] for x in s['locations']], shot_description=desc,
                              presence=sorted(ids[x] for x in s['presence']), absent=sorted(ids[x] for x in s['absent']),
                              **per_shot[sid]))
    contract = dict(schema_version='episode_contract_v2', episode_id=payload['episode_id'],
                    entity_descriptions=entities_out, shots=shots_out, cross_shot=cross, unresolved=dec['unresolved'],
                    prompt=dict(global_prompt=payload['prompt']['global'], shots=payload['prompt']['shots']))
    summary = collections.Counter(a['to'] for a in accounting.values())
    return contract, dict(v1_claims=len(claims), summary=dict(summary), claims=accounting,
                          new_requirements=len(dec['new_requirements'])), warn


def dedup(items):
    seen, out = set(), []
    for it in items:
        key = json.dumps(it, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


STRIP = ('evidence', 'source_claim_ids', 'source_labels', 'origin', 'prompt')


def model_facing(obj_):
    if isinstance(obj_, dict):
        out = {k: model_facing(v) for k, v in obj_.items() if k not in STRIP}
        return out['value'] if set(out) == {'value'} else out
    if isinstance(obj_, list):
        return [model_facing(x) for x in obj_]
    return obj_


def render(k, accounting):
    ents = k['entity_descriptions']
    nm = lambda i: f"{i} {ents[str(i)]['name']}"
    lines = [f"# Contract v2: {k['episode_id']}", '', 'Model-facing version (no evidence). v1 claims: '
             + ', '.join(f'{v} → {key}' for key, v in accounting['summary'].items())
             + f"; new requirements: {accounting['new_requirements']}.", '',
             '## entity_descriptions', '', '| id | label | name | description |', '|---|---|---|---|']
    lines += [f"| {i} | {e['label']} | {e['name']} | {e['description']} |" for i, e in ents.items()]
    for s in k['shots']:
        sd = s['shot_description']
        lines += ['', f"## {s['shot_id']}", '', '- **locations**: ' + ', '.join(nm(i) for i in s['locations']),
                  f"- **camera_view**: {sd['camera_view']}", f"- **camera_movement**: {sd['camera_movement']}",
                  f"- **style**: {sd['style']}",
                  '- **presence**: ' + ', '.join(nm(i) for i in s['presence']),
                  '- **absent**: ' + (', '.join(nm(i) for i in s['absent']) or '(none)')]
        for dim in ('appearance', 'spatial', 'motion'):
            lines += ['', f'**{dim}** ({len(s[dim])})', '']
            if not s[dim]:
                lines.append('(none)')
                continue
            lines += ['| id | entities | expected | quantifier |', '|---|---|---|---|']
            lines += [f"| {it['id']} | {', '.join(nm(i) for i in it['entities'])} | {it['expected']} | {it['quantifier']} |" for it in s[dim]]
    lines += ['', f"## cross_shot ({len(k['cross_shot'])})", '']
    lines += [f"- {it['id']} [{', '.join(it['shot_ids'])}] {it['dimension']}: {it['expected']}" for it in k['cross_shot']] or ['(none)']
    lines += ['', '## unresolved', ''] + ([f'- {u}' for u in k['unresolved']] or ['(none)'])
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------- model calls
def call(folder, stage, payload):
    folder.mkdir(parents=True, exist_ok=False)
    prompt = ((HERE / 'audit_v2.txt').read_text() if stage == 'audit' else '') + (HERE / 'rules_v2.txt').read_text()
    prompt += '\nINPUT_JSON:\n' + json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    (folder / 'prompt.txt').write_text(prompt)
    state = dict(status='running', started=time.time(), model=MODEL, reasoning=REASONING, stage=stage)
    dump(folder / 'status.json', state)
    try:
        with tempfile.TemporaryDirectory(prefix='eec-contract-v2-') as tmp:
            cmd = ['codex', '--ask-for-approval', 'never', 'exec', '--ignore-user-config', '-c', DISABLED, '--ephemeral',
                   '--skip-git-repo-check', '--sandbox', 'read-only', '--color', 'never', '--json', '--model', MODEL,
                   '-c', f'model_reasoning_effort="{REASONING}"', '-c', 'project_doc_max_bytes=0', '-c', 'web_search="disabled"',
                   '-c', 'model_instructions_file=' + json.dumps(str(HERE / 'base.txt')),
                   '--output-schema', str(HERE / f'{stage}.schema.json'), '--output-last-message', str(folder / 'response.json'),
                   '--cd', tmp]
            for f in ('shell_tool', 'unified_exec', 'view_image', 'apps', 'plugins', 'hooks', 'multi_agent', 'memories',
                      'skill_search', 'browser_use', 'computer_use', 'code_mode', 'code_mode_only', 'workspace_dependencies'):
                cmd += ['--disable', f]
            cmd += ['-']
            dump(folder / 'request.json', dict(command=cmd, prompt_sha256=sha(folder / 'prompt.txt')))
            io.run_process(cmd, prompt, Path(tmp), folder / 'events.jsonl', folder / 'stderr.log', 1800)
        state.update(status='success', usage=io.audit_events(folder / 'events.jsonl'))
        return read(folder / 'response.json')
    except BaseException as e:
        state.update(status='failed', error=str(e))
        try:
            state['known_usage'] = io.audit_events(folder / 'events.jsonl')
        except Exception:
            state['usage_unavailable'] = True
        raise
    finally:
        state['seconds'] = time.time() - state['started']
        dump(folder / 'status.json', state)


def attempt_loop(folder, stage, base_payload, max_attempts, build, meta, v1c):
    """Call, assemble and validate; on errors resend with the previous output and all errors."""
    feedback, previous = None, None
    for n in range(1, max_attempts + 1):
        dest = folder / 'calls' / f'{stage}_{n}'
        payload = copy.deepcopy(base_payload)
        if feedback:
            payload['previous_output'] = previous
            payload['validation_errors'] = feedback
        if (dest / 'response.json').exists():
            raw = read(dest / 'response.json')
        elif dest.exists():
            feedback, previous = ['Previous call did not return a complete JSON response.'], None
            continue
        else:
            raw = call(dest, stage, payload)
        try:
            dec = build(raw)
            if dec is None:  # audit pass
                dump(dest / 'validation.json', dict(status='pass'))
                return raw, None
            contract, accounting, warn = assemble(dec, base_payload, meta, v1c)
            dump(dest / 'validation.json', dict(status='pass', warnings=warn))
            return raw, (dec, contract, accounting, warn)
        except Exception as e:
            feedback = str(e).split('\n')
            previous = raw
            dump(dest / 'validation.json', dict(status='failed', errors=feedback))
    raise ValueError(f'{stage} failed after {max_attempts} attempts: ' + '; '.join(feedback[:20]))


def process(job, audit=True):
    eid = job['episode_id']
    folder = HERE / 'episodes' / eid
    started = time.time()
    try:
        assert sha(folder / 'input.json') == job['input_sha256']
        if (folder / 'final_decisions.json').exists():
            return dict(episode_id=eid, status='cached')
        payload, meta = read(folder / 'input.json'), read(folder / 'meta.json')
        v1c = read(V1 / 'episodes' / eid / 'contract.json')
        if (folder / 'rewrite.json').exists():
            dec = read(folder / 'rewrite.json')
            contract, accounting, warn = assemble(dec, payload, meta, v1c)
        else:
            raw, (dec, contract, accounting, warn) = attempt_loop(folder, 'rewrite', payload, MAX_REWRITE_ATTEMPTS,
                                                                    lambda r: r, meta, v1c)
            dump(folder / 'rewrite.json', raw)
        verdict, issues = 'not_audited', []
        if audit:
            audit_payload = dict(payload, decisions=dec, assembled=model_facing(contract), warnings=warn)
            raw, built = attempt_loop(folder, 'audit', audit_payload, MAX_AUDIT_ATTEMPTS, audit_build, meta, v1c)
            dump(folder / 'audit.json', raw)
            verdict, issues = raw['verdict'], raw['issues']
            if built is not None:
                dec, contract, accounting, warn = built
        dump(folder / 'final_decisions.json', dec)
        dump(folder / 'contract_with_evidence.json', contract)
        dump(folder / 'contract.json', model_facing(contract))
        dump(folder / 'claim_accounting.json', accounting)
        (folder / 'review.md').write_text(render(model_facing(contract), accounting))
        state = dict(episode_id=eid, status='success', audit_verdict=verdict, audit_issues=len(issues),
                     entities=len(contract['entity_descriptions']), warnings=len(warn), seconds=time.time() - started,
                     summary=accounting['summary'], new_requirements=accounting['new_requirements'])
    except Exception as e:
        state = dict(episode_id=eid, status='failed', error=str(e)[:2000], seconds=time.time() - started)
    dump(folder / 'status.json', state)
    with LOCK:
        print(json.dumps(state, ensure_ascii=False), flush=True)
    return state


def audit_build(raw):
    if raw['verdict'] == 'pass':
        if raw['issues'] or raw['revised_decisions'] is not None:
            raise ValueError('A pass verdict must have no issues and revised_decisions null.')
        return None
    if raw['revised_decisions'] is None or not raw['issues']:
        raise ValueError('A revised verdict needs issues and the complete revised_decisions.')
    return raw['revised_decisions']


# ---------------------------------------------------------------- commands
def prepare():
    io.safe_compute()
    if (HERE / 'manifest.json').exists():
        raise FileExistsError('Already prepared')
    index = read(V1 / 'index.json')
    jobs = []
    for row in index:
        eid = row['episode_id']
        payload, meta = build_payload(eid)
        dump(HERE / 'episodes' / eid / 'input.json', payload)
        dump(HERE / 'episodes' / eid / 'meta.json', meta)
        jobs.append(dict(index=row['priority_index'], episode_id=eid, shots=row['shots'],
                         input_sha256=sha(HERE / 'episodes' / eid / 'input.json'),
                         v1_contract_sha256=sha(V1 / 'episodes' / eid / 'contract.json')))
    for name, schema in (('rewrite', DECISIONS), ('audit', AUDIT)):
        dump(HERE / f'{name}.schema.json', schema)
    dump(HERE / 'manifest.json', dict(schema_version='episode_contract_v2', created=time.time(), model=MODEL,
                                      reasoning=REASONING, v1_deliverables=str(V1),
                                      spec='EECBench/docs/episode-contract-v2-format.md', jobs=jobs,
                                      prompt_sha256={n: sha(HERE / n) for n in ('rules_v2.txt', 'audit_v2.txt', 'base.txt')}))
    print(json.dumps(dict(prepared=len(jobs))), flush=True)


def usage():
    prices = read(HERE / 'pricing.json')
    tot, amount, unknown, rows = collections.Counter(), 0.0, 0, []
    for p in sorted((HERE / 'episodes').glob('*/calls/*/status.json')):
        s = read(p)
        us = s.get('usage', s.get('known_usage', []))
        us = [us] if isinstance(us, dict) else us
        cost, valid = 0.0, bool(us)
        for u in us:
            inp, cache, out = (u.get(k, 0) for k in ('input_tokens', 'cached_input_tokens', 'output_tokens'))
            if not 0 <= cache <= inp <= prices['max_input_tokens'] or u.get('cache_write_input_tokens', 0):
                valid = False
            cost += ((inp - cache) * prices['input_usd_per_million'] + cache * prices['cached_input_usd_per_million']
                     + out * prices['output_usd_per_million']) / 1e6
            for k in ('input_tokens', 'cached_input_tokens', 'output_tokens'):
                tot[k] += u.get(k, 0)
        amount += cost if valid else 0
        unknown += 0 if valid else 1
        rows.append(dict(path=str(p.relative_to(HERE)), status=s['status'], stage=s.get('stage'), seconds=s.get('seconds'),
                         usage=us, standard_api_equivalent_usd=cost if valid else None))
    result = dict(calls=len(rows), usage=dict(tot), total_tokens=tot['input_tokens'] + tot['output_tokens'],
                  standard_api_equivalent_usd=amount if not unknown else None, known_subtotal_usd=amount,
                  unavailable_or_inflight_costs=unknown, pricing=prices, actual_billed_api_usd=None, rows=rows)
    dump(HERE / 'usage_cost.json', result)
    return result


def run(args):
    global DISABLED
    alloc = io.safe_compute()
    m = read(HERE / 'manifest.json')
    DISABLED = io.disabled_skills_config()
    jobs = m['jobs']
    if args.pilot:
        wanted = ['74Od5-Fmf60_s00006_n4_clean_v2'] + [next(j['episode_id'] for j in jobs if j['shots'] == n) for n in (6, 8)]
        jobs = [j for j in jobs if j['episode_id'] in wanted]
    elif args.episodes:
        jobs = [j for j in jobs if j['episode_id'] in set(args.episodes)]
    elif not args.all:
        raise SystemExit('choose --pilot, --episodes or --all')
    started = time.time()
    dump(HERE / 'runs' / f'run_{int(started)}.json', dict(started=started, host=socket.gethostname(), allocation=alloc,
                                                          workers=args.workers, planned=[j['episode_id'] for j in jobs],
                                                          audit=not args.no_audit))
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        states = list(pool.map(lambda j: process(j, audit=not args.no_audit), jobs))
    u = usage()
    summary = dict(seconds=time.time() - started, planned=len(jobs), succeeded=sum(s['status'] in ('success', 'cached') for s in states),
                   failed=[s for s in states if s['status'] == 'failed'], total_tokens=u['total_tokens'],
                   cumulative_standard_api_equivalent_usd=u['standard_api_equivalent_usd'])
    dump(HERE / 'runs' / f'run_{int(started)}_summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def load_episode(eid):
    folder = HERE / 'episodes' / eid
    m = read(HERE / 'manifest.json')
    job = next(j for j in m['jobs'] if j['episode_id'] == eid)
    assert sha(folder / 'input.json') == job['input_sha256'], f'{eid}: input changed'
    return folder, read(folder / 'input.json'), read(folder / 'meta.json'), read(V1 / 'episodes' / eid / 'contract.json')


def show(eid):
    """Print the episode input compactly for an agent: prompts, v1 entities, schedule, claims, notes."""
    folder, payload, meta, v1c = load_episode(eid)
    v1 = payload['v1']
    out = [f'EPISODE {eid}', '', '== PROMPT (fact_id: text)', f'global: {payload["prompt"]["global"]}']
    out += [f'{s["shot_id"]}: {s["text"]}' for s in payload['prompt']['shots']]
    out += ['', '== V1 ENTITIES (label | name | description | evidence)']
    out += [f'{e["label"]} | {e["name"]} | {e["description"]} | ' + '; '.join(f'[{q["fact_id"]}] "{q["quote"]}"' for q in e['evidence'])
            for e in v1['entities']]
    out += ['', '== V1 SCHEDULE (shot | characters | places | objects)']
    out += [f'{s["shot_id"]} | {", ".join(s["characters"])} | {", ".join(s["places"])} | {", ".join(s["objects"])}' for s in v1['schedule']]
    out += ['', '== V1 CLAIMS (claim_id | dimension | entity_ids | shot_ids | predicate | quantifier | frame | expected)']
    out += [f'{q["claim_id"]} | {q["dimension"]} | {",".join(q["entity_ids"])} | {",".join(q["shot_ids"])} | {q["predicate"]} | '
            f'{q["quantifier"]} | {q["coordinate_frame"]} | {q["expected"]}' for q in v1['claims']]
    out += ['', '== V1 UNSCORED TEXT (camera, timing, style text v1 did not score)']
    out += [f'{u["fact_id"]}: "{x["quote"]}" ({x["reason"]})' for u in v1['unscored_text'] for x in u['items']]
    out += ['', '== V1 UNRESOLVED'] + [f'- {u}' for u in v1['unresolved']]
    print('\n'.join(out))


def check(eid, path):
    """Validate agent-written decisions: schema + assembly gates. Prints PASS/FAIL; no outputs written."""
    import jsonschema
    folder, payload, meta, v1c = load_episode(eid)

    def log(result, n_errors):
        line = json.dumps(dict(at=time.time(), file=str(path), result=result, errors=n_errors))
        with (folder / 'claude' / 'check_log.jsonl').open('a') as f:
            f.write(line + '\n')

    (folder / 'claude').mkdir(exist_ok=True)
    try:
        dec = read(path)
        jsonschema.validate(dec, DECISIONS)
        contract, accounting, warn = assemble(dec, payload, meta, v1c)
    except jsonschema.ValidationError as e:
        print('FAIL\nschema: ' + e.message + ' at ' + '/'.join(map(str, e.absolute_path)))
        log('fail_schema', 1)
        return 1
    except (ValueError, json.JSONDecodeError) as e:
        print('FAIL\n' + str(e))
        log('fail', len(str(e).splitlines()))
        return 1
    log('pass', 0)
    print('PASS ' + json.dumps(dict(summary=accounting['summary'], new_requirements=accounting['new_requirements'],
                                     entities=len(contract['entity_descriptions'])), ensure_ascii=False))
    for w in warn:
        print('WARNING ' + w)
    return 0


def finalize(eid, path, producer, audit_verdict, audit_issues):
    """Write the final v2 files from decisions that pass check()."""
    folder, payload, meta, v1c = load_episode(eid)
    dec = read(path)
    import jsonschema
    jsonschema.validate(dec, DECISIONS)
    contract, accounting, warn = assemble(dec, payload, meta, v1c)
    dump(folder / 'final_decisions.json', dec)
    dump(folder / 'contract_with_evidence.json', contract)
    dump(folder / 'contract.json', model_facing(contract))
    dump(folder / 'claim_accounting.json', accounting)
    (folder / 'review.md').write_text(render(model_facing(contract), accounting))
    state = dict(episode_id=eid, status='success', producer=producer, decisions_file=str(Path(path).resolve().relative_to(HERE)),
                 audit_verdict=audit_verdict, audit_issues=audit_issues, entities=len(contract['entity_descriptions']),
                 warnings=len(warn), summary=accounting['summary'], new_requirements=accounting['new_requirements'],
                 finalized_at=time.time())
    dump(folder / 'status.json', state)
    print(json.dumps(state, ensure_ascii=False))


def export():
    m = read(HERE / 'manifest.json')
    dest = HERE / 'deliverables'
    index, plain, full = [], [], []
    for j in m['jobs']:
        eid = j['episode_id']
        folder = HERE / 'episodes' / eid
        st = read(folder / 'status.json')
        if st['status'] != 'success':
            raise RuntimeError(f'{eid} is not complete: {st["status"]}')
        payload, meta = read(folder / 'input.json'), read(folder / 'meta.json')
        contract, accounting, warn = assemble(read(folder / 'final_decisions.json'), payload, meta,
                                              read(V1 / 'episodes' / eid / 'contract.json'))
        assert contract == read(folder / 'contract_with_evidence.json')
        out = dest / 'episodes' / eid
        dump(out / 'contract_with_evidence.json', contract)
        dump(out / 'contract.json', model_facing(contract))
        dump(out / 'claim_accounting.json', accounting)
        (out / 'review.md').write_text(render(model_facing(contract), accounting))
        index.append(dict(episode_id=eid, priority_index=j['index'], shots=j['shots'],
                          entities=len(contract['entity_descriptions']), audit_verdict=st.get('audit_verdict'),
                          accounting=accounting['summary'], new_requirements=accounting['new_requirements'],
                          warnings=len(warn)))
        plain.append(model_facing(contract))
        full.append(contract)
    for name, rows in (('contracts_400.jsonl', plain), ('contracts_400_with_evidence.jsonl', full),
                       ('priority_200.jsonl', plain[:200])):
        (dest / name).write_text(''.join(json.dumps(r, ensure_ascii=False, separators=(',', ':')) + '\n' for r in rows))
    dump(dest / 'index.json', index)
    print(json.dumps(dict(exported=len(index))), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['prepare', 'run', 'usage', 'export', 'show', 'check', 'finalize'])
    p.add_argument('target', nargs='*', help='check/finalize: EPISODE_ID DECISIONS_JSON')
    p.add_argument('--producer', default='claude_code_subagent')
    p.add_argument('--audit-verdict', default='not_audited', choices=['not_audited', 'pass', 'revised'])
    p.add_argument('--audit-issues', type=int, default=0)
    p.add_argument('--pilot', action='store_true')
    p.add_argument('--episodes', nargs='*')
    p.add_argument('--all', action='store_true')
    p.add_argument('--workers', type=int, default=3)
    p.add_argument('--no-audit', action='store_true')
    a = p.parse_args()
    if a.command == 'prepare':
        prepare()
    elif a.command == 'run':
        run(a)
    elif a.command == 'usage':
        print(json.dumps({k: v for k, v in usage().items() if k != 'rows'}))
    elif a.command == 'show':
        show(*a.target)
    elif a.command == 'check':
        sys.exit(check(*a.target))
    elif a.command == 'finalize':
        finalize(*a.target, a.producer, a.audit_verdict, a.audit_issues)
    else:
        export()
