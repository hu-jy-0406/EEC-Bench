#!/usr/bin/env python3
"""Budget appearance rubric: v3 wire fields, no event verifier, local min/RMS."""
import argparse
from collections import Counter
import concurrent.futures
import json
import math
from pathlib import Path
import shutil
import time

import gs_entity_appearance_minimal as minimal
import gs_entity_appearance_compact as transport
import run_wedetect_shot_entities as io
from gs_consistency_contract import obj, arr, I, S

PROTOCOL = 'entity_appearance_budget_v5'
PROMPT = transport.ROOT / 'prompts/appearance/entity_budget_v5.txt'
SCORES = [0, 25, 75, 90, 100, None]
SCHEMA = obj(u=arr(dict(type='integer', enum=[0, 1, 2])),
    s=arr(dict(type=['integer', 'null'], enum=SCORES)), e=arr(arr(I)),
    why=dict(type='string', maxLength=160), limits=dict(type='string', maxLength=120),
    expected_changes=arr(S))
read, dump, sha = transport.read, transport.dump, transport.sha


def configure():
    transport.PROTOCOL = minimal.PROTOCOL = PROTOCOL
    transport.PROMPT, transport.SCHEMA = PROMPT, SCHEMA
    io.run_process = minimal.evaluation_process


def expand(raw, payload):
    """Keep v3's structural validation; introduce no semantic verifier gates."""
    import jsonschema
    jsonschema.validate(raw, SCHEMA)
    appearances = payload['appearances']; n = len(appearances)
    if len(raw['u']) != n or len(raw['s']) != 4 or len(raw['e']) != 4:
        raise ValueError('Wrong panel/dimension coverage')
    if not raw['why'].strip():
        raise ValueError('Missing concise explanation')
    for score, ids in zip(raw['s'], raw['e']):
        if len(ids) != len(set(ids)) or any(i < 0 or i >= n for i in ids):
            raise ValueError('Invalid/duplicate evidence index')
        if score is not None and sum(raw['u'][i] > 0 for i in ids) < 2:
            raise ValueError('Need two usable/partial witnesses')
    facts = {f['fact_id'] for f in payload['normal_story_prompt']['facts']}
    if not set(raw['expected_changes']) <= facts:
        raise ValueError('Unknown narrative fact')
    vals = [s for s in raw['s'] if s is not None]
    return dict(global_entity_id=payload['global_entity_id'], score=min(vals) if vals else None,
        appearance_checks=[dict(appearance_id=a['appearance_id'],
            usability=['unusable','partial','usable'][raw['u'][i]]) for i,a in enumerate(appearances)],
        dimensions={dim:dict(score=score,
            evidence_appearance_ids=[appearances[i]['appearance_id'] for i in ids])
            for dim,score,ids in zip(transport.base.DIMS,raw['s'],raw['e'])},
        assessable_dimensions=len(vals), unknown_dimensions=4-len(vals),
        expected_changes=raw['expected_changes'], reason=raw['why'], limitations=raw['limits'])


def prepare(source, out):
    configure()
    source, out = source.resolve(), out.resolve()
    source_m = read(source / 'manifest.json')
    if source_m['protocol'].startswith('entity_appearance_compact'):
        m = transport.verify(source)
        out.mkdir(parents=True, exist_ok=False)
        sources = {str(source / 'manifest.json'): sha(source / 'manifest.json')}
        for entry in m['entities']:
            old, new = source / 'entities' / entry['global_entity_id'], out / 'entities' / entry['global_entity_id']
            new.mkdir(parents=True)
            for name in ('input.json', 'dino.json', 'wire.json', 'images.json', 'sheet_audit.json'):
                shutil.copy2(old / name, new / name)
                sources[str(old / name)] = sha(old / name)
        # Original contact sheets are immutable referenced evidence; no reencoding.
        manifest = dict(m, protocol=PROTOCOL, source=str(source), source_hashes=sources)
    else:
        transport.prepare(source, out)
        manifest = read(out / 'manifest.json')
    for path in (Path(__file__).resolve(), PROMPT, minimal.BASE,
                 Path(minimal.__file__).resolve(), Path(transport.__file__).resolve(),
                 Path(transport.base.__file__).resolve(), Path(io.__file__).resolve()):
        manifest['source_hashes'][str(path)] = sha(path)
    manifest.update(protocol=PROTOCOL,
        output='v3 fields u/s/e/why/limits/expected_changes only; no event/gate/reviewer outputs; local minimum score',
        aggregation='Codex: 100-RMS(100-entity_score), equal entities; arithmetic mean auxiliary. DINO: unchanged equal-entity mean.',
        score_anchors=SCORES, base_instructions=str(minimal.BASE))
    dump(out / 'manifest.json', manifest)
    print(json.dumps(dict(prepared=str(out), entities=len(manifest['entities']))), flush=True)


def verify(out):
    m = transport.verify(out)
    if m['protocol'] != PROTOCOL:
        raise ValueError('Wrong scoring protocol')
    for e in m['entities']:
        folder = out / 'entities' / e['global_entity_id']
        for im in read(folder / 'images.json'):
            if sha(im['path']) != im['sha256']:
                raise ValueError('Changed contact sheet')
    return m


def score(runs, workers, only, timeout):
    configure()
    disabled, jobs = io.disabled_skills_config(), []
    for out in runs:
        for e in verify(out)['entities']:
            if not only or out.name + '/' + e['global_entity_id'] in only:
                jobs.append((out, e))
    def one(job):
        out, e = job
        eid = e['global_entity_id']; folder = out / 'entities' / eid
        payload = read(folder / 'input.json')
        if (folder / 'codex.json').exists():
            saved = read(folder / 'codex.json')
            if saved['status'] == 'success' and expand(read(out / 'calls' / eid / 'response.json'), payload) != saved['result']:
                raise ValueError('Saved result does not match raw verdict')
            return saved
        if len(payload['appearances']) < 2:
            result = dict(status='not_assessable', score=None, reason='Fewer than two appearances')
        else:
            try:
                raw = transport.call(out / 'calls' / eid, read(folder / 'wire.json'), read(folder / 'images.json'), disabled, timeout)
                expanded = expand(raw, payload)
                result = dict(status='success', score=expanded['score'], result=expanded)
            except Exception as exc:
                result = dict(status='failed', score=None, error=str(exc))
        dump(folder / 'codex.json', result)
        print(json.dumps(dict(study=out.name, entity=eid, status=result['status'], score=result['score'], error=result.get('error'))), flush=True)
        return result
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, jobs))
    failed = sum(r['status'] == 'failed' for r in results)
    print(json.dumps(dict(seconds=time.time()-started, failed=failed)), flush=True)
    if failed:
        raise RuntimeError('Failures recorded, no automatic retries')


def aggregate(rows):
    cs = [r['codex_score'] for r in rows if r['codex_score'] is not None]
    ds = [r['dino_score'] for r in rows if r['dino_score'] is not None]
    return dict(entities=len(rows), scored_entities=len(cs), unscored_entities=len(rows)-len(cs),
        codex_score=100-math.sqrt(sum((100-c)**2 for c in cs)/len(cs)) if cs else None,
        codex_entity_mean=sum(cs)/len(cs) if cs else None,
        dino_score=sum(ds)/len(ds) if ds else None, dino_scored_entities=len(ds),
        assessable_dimensions=sum(r.get('assessable_dimensions', 0) for r in rows),
        unknown_dimensions=sum(r.get('unknown_dimensions', 4) for r in rows))


def report(runs, output):
    summaries, all_usage = [], []
    for out in runs:
        rows, usage = [], []
        m = verify(out)
        for e in m['entities']:
            eid = e['global_entity_id']; f = out / 'entities' / eid
            c = read(f / 'codex.json'); d = read(f / 'dino.json')
            if c['status'] == 'failed':
                raise ValueError('Cannot report incomplete result')
            result = c.get('result', {})
            if c['status'] == 'success':
                assert result == expand(read(out / 'calls' / eid / 'response.json'), read(f / 'input.json'))
                status = read(out / 'calls' / eid / 'status.json')
                assert status['status'] == 'success'
                usage += status['usage']
            assert d == read(Path(m['source']) / 'entities' / eid / 'dino.json')
            rows.append(dict(global_entity_id=eid, name=e['name'], observed_shot_ids=e['observed_shot_ids'],
                appearances=e['appearances'], codex_score=c['score'], dino_score=d['score'],
                assessable_dimensions=result.get('assessable_dimensions', 0), unknown_dimensions=result.get('unknown_dimensions', 4),
                dimensions=result.get('dimensions', {}), reason=result.get('reason', c.get('reason', '')), limitations=result.get('limitations', '')))
        u = Counter()
        for item in usage: u.update(item)
        summary = dict(protocol=PROTOCOL, study=out.name, all_entities=aggregate(rows),
            multi_shot_entities=aggregate([r for r in rows if len(r['observed_shot_ids'])>1]),
            single_shot_entities=aggregate([r for r in rows if len(r['observed_shot_ids'])==1]),
            entities=rows, usage=dict(u), total_tokens=u['input_tokens']+u['output_tokens'],
            cost=dict(standard_api_equivalent_usd=transport.cost(usage), not_invoice=True,
                source='https://developers.openai.com/api/docs/models/gpt-6-astra', verified_date='2026-09-20'))
        dump(out / 'summary.json', summary)
        summaries.append(summary); all_usage += usage
    u = Counter()
    for item in all_usage: u.update(item)
    result = dict(protocol=PROTOCOL, studies=summaries, usage=dict(u),
        total_tokens=u['input_tokens']+u['output_tokens'], standard_api_equivalent_usd=transport.cost(all_usage))
    dump(output, result)
    print(json.dumps({s['study']: s['all_entities'] for s in summaries}), flush=True)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('phase', choices=['prepare','score','report'])
    p.add_argument('--source', type=Path); p.add_argument('--out', type=Path)
    p.add_argument('--runs', nargs='+', type=Path); p.add_argument('--only', nargs='*')
    p.add_argument('--workers', type=int, default=3); p.add_argument('--timeout', type=int, default=600)
    a = p.parse_args()
    if a.phase == 'prepare': prepare(a.source, a.out)
    elif a.phase == 'score': score([r.resolve() for r in a.runs], a.workers, a.only, a.timeout)
    else: report([r.resolve() for r in a.runs], a.out)


if __name__ == '__main__': main()
