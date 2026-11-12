#!/usr/bin/env python3
"""Unspecified-entity metrics of four versions on the 1,000 first-200 videos (owner, 2026-11-12: "给我报一下C,C+插件，new，
new+插件各自的unspecific实体相关指标，包括数量占比，相关问题占比，specific/unspecific实体中出问题的比例等"). Zero model calls.

Versions and sources (V-L is the same review in both variants of a version):
  C            ../vl_vv_full_first200_c_20261110/runs/<t>/results/{vv_detection,vv_review,vl_detection,vl_review}
  C + plug-in  same, V-V from results_with/{vv_detection,vv_review}
  new          runs/<t>/results/... (the 40 reused validation videos from ../vl_vv_entity_scope_validation_20261111)
  new + plug-in  V-V from results_with/{vv_plugin,vv_review}

Entities of a video and version: the case ledger (episode_entities.json: prompt_bound pb... = specified, prompt_unbound
ge... = unspecified) plus the entities that this version's detection calls added (source added_by_*; label unspecified
by the ledger label rule). Added entities are keyed per branch, since V-L and V-V numbering can overlap.
An entity "has a problem" when it is a subject (entity_refs role "subject"; "context" refs excluded) of at least one
confirmed issue. An issue "involves an unspecified entity" when at least one of its subjects is unspecified.
Writes unspecified_entity_metrics.json."""
import collections
import json
from pathlib import Path

EXP = Path(__file__).resolve().parent
C = EXP.parent / 'vl_vv_full_first200_c_20261110'
VALID = EXP.parent / 'vl_vv_entity_scope_validation_20261111'
MODELS = ('cinetrans', 'holocine', 'storymem', 'wan21', 'wan22')
VERSIONS = ('c', 'c_plug', 'new', 'new_plug')


def read(p):
    return json.loads(Path(p).read_text())


def sources(task):
    c = C / 'runs' / task
    here = EXP / 'runs' / task
    n = VALID / 'runs' / task if (here / 'reused_from.json').is_file() else here
    return {
        'c': dict(ledger=c / 'case/episode_entities.json', vl_det=c / 'results/vl_detection/result.json',
                  vl=c / 'results/vl_review/result.json', vv_det=c / 'results/vv_detection/result.json',
                  vv=c / 'results/vv_review/result.json'),
        'c_plug': dict(ledger=c / 'case/episode_entities.json', vl_det=c / 'results/vl_detection/result.json',
                       vl=c / 'results/vl_review/result.json', vv_det=c / 'results_with/vv_detection/result.json',
                       vv=c / 'results_with/vv_review/result.json'),
        'new': dict(ledger=n / 'case/episode_entities.json', vl_det=n / 'results/vl_detection/result.json',
                    vl=n / 'results/vl_review/result.json', vv_det=n / 'results/vv_detection/result.json',
                    vv=n / 'results/vv_review/result.json'),
        'new_plug': dict(ledger=n / 'case/episode_entities.json', vl_det=n / 'results/vl_detection/result.json',
                         vl=n / 'results/vl_review/result.json', vv_det=n / 'results_with/vv_plugin/result.json',
                         vv=n / 'results_with/vv_review/result.json'),
    }


def key(branch, entity):
    k = entity['entity_key']
    return k if entity.get('source') == 'detection_ledger' else f'{branch}:{k}'


def video(src):
    led = read(src['ledger'])
    label = {e['global_entity_id']: 'specified' for e in led.get('prompt_bound') or []}
    label.update({e['global_entity_id']: 'unspecified' for e in led.get('prompt_unbound') or []})
    origin = {k: 'ledger' for k in label}
    for branch, det in (('vl', src['vl_det']), ('vv', src['vv_det'])):
        for e in read(det).get('entities') or []:
            k = key(branch, e)
            if k not in label:
                label[k] = e.get('label') or 'unspecified'
                origin[k] = 'added'
    c = collections.Counter()
    for k in label:
        c[f'ent_{label[k]}'] += 1
        c[f'ent_{label[k]}_{origin[k]}'] += 1
    flagged = {'vv': set(), 'vl': set(), 'vv_cu': set()}
    for branch in ('vl', 'vv'):
        r = read(src[branch])
        ents = {e['entity_key']: key(branch, e) for e in r.get('entities') or []}
        for u in r['units']:
            subj = [ents.get(x['entity_key'], f"{branch}:{x['entity_key']}") for x in u.get('entity_refs') or []
                    if x.get('role') == 'subject']
            for k in subj:  # an entity a review introduced without a detection record
                if k not in label:
                    label[k], origin[k] = 'unspecified', 'added'
                    c['ent_unspecified'] += 1
                    c['ent_unspecified_added'] += 1
            uns = any(label[k] == 'unspecified' for k in subj)
            for verdicts, name in ((('confirmed',), ''), (('confirmed', 'uncertain'), '_cu')):
                if u['verdict'] in verdicts:
                    c[f'{branch}_issues{name}'] += 1
                    c[f'{branch}_issues{name}_unspecified'] += uns
                    c[f'{branch}_issues{name}_no_subject'] += not subj
            if u['verdict'] == 'confirmed':
                flagged[branch].update(subj)
            if u['verdict'] in ('confirmed', 'uncertain') and branch == 'vv':
                flagged['vv_cu'].update(subj)
    for name, ks in (('vv', flagged['vv']), ('any', flagged['vv'] | flagged['vl']), ('vv_cu', flagged['vv_cu'])):
        for k in ks:
            c[f'flag_{name}_{label[k]}'] += 1
            c[f'flag_{name}_{label[k]}_{origin[k]}'] += 1
    return c


def pct(a, b):
    return round(100 * a / b, 2) if b else None


def derive(c):
    spec, uns = c['ent_specified'], c['ent_unspecified']
    vv, vl = c['vv_issues'], c['vl_issues']
    return dict(
        videos=c['videos'],
        entities=dict(specified=spec, unspecified=uns, unspecified_ledger=c['ent_unspecified_ledger'],
                      unspecified_added=c['ent_unspecified_added'], unspecified_share=pct(uns, spec + uns),
                      unspecified_share_ledger_only=pct(c['ent_unspecified_ledger'],
                                                        spec + c['ent_unspecified_ledger'])),
        issues=dict(vv_confirmed=vv, vv_unspecified=c['vv_issues_unspecified'],
                    vv_unspecified_share=pct(c['vv_issues_unspecified'], vv),
                    vl_confirmed=vl, vl_unspecified=c['vl_issues_unspecified'],
                    all_unspecified_share=pct(c['vv_issues_unspecified'] + c['vl_issues_unspecified'], vv + vl),
                    vv_confirmed_or_uncertain=c['vv_issues_cu'],
                    vv_cu_unspecified_share=pct(c['vv_issues_cu_unspecified'], c['vv_issues_cu']),
                    vv_without_subject=c['vv_issues_no_subject']),
        entities_with_problem=dict(
            specified_vv=c['flag_vv_specified'], specified_vv_share=pct(c['flag_vv_specified'], spec),
            unspecified_vv=c['flag_vv_unspecified'], unspecified_vv_share=pct(c['flag_vv_unspecified'], uns),
            unspecified_ledger_vv_share=pct(c['flag_vv_unspecified_ledger'], c['ent_unspecified_ledger']),
            unspecified_added_vv_share=pct(c['flag_vv_unspecified_added'], c['ent_unspecified_added']),
            specified_any=c['flag_any_specified'], specified_any_share=pct(c['flag_any_specified'], spec),
            unspecified_any=c['flag_any_unspecified'], unspecified_any_share=pct(c['flag_any_unspecified'], uns),
            specified_vv_cu_share=pct(c['flag_vv_cu_specified'], spec),
            unspecified_vv_cu_share=pct(c['flag_vv_cu_unspecified'], uns),
            # share of problem entities (V-V, confirmed) that are unspecified
            unspecified_share_of_vv_problem_entities=pct(c['flag_vv_unspecified'],
                                                         c['flag_vv_specified'] + c['flag_vv_unspecified'])))


def main():
    tasks = sorted(p.name for p in (EXP / 'runs').iterdir() if (p / 'stages' / 'with_episode_scoring.done').is_file())
    tot = collections.defaultdict(collections.Counter)
    for t in tasks:
        model = t.split('__')[1]
        for v, src in sources(t).items():
            c = video(src)
            c['videos'] = 1
            tot[(v, 'all')].update(c)
            tot[(v, model)].update(c)
    out = dict(videos=len(tasks), definitions=__doc__,
               versions={v: derive(tot[(v, 'all')]) for v in VERSIONS},
               per_model={v: {m: derive(tot[(v, m)]) for m in MODELS} for v in VERSIONS},
               raw={f'{v}|{m}': dict(c) for (v, m), c in tot.items()})
    (EXP / 'unspecified_entity_metrics.json').write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(out['versions'], indent=1))


if __name__ == '__main__':
    main()
