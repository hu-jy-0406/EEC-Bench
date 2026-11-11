#!/usr/bin/env python3
"""Results of the first-200 rerun (all finished tasks): scores, confirmed issue counts and the unspecified-entity
metrics, per model and pooled; for the reuse videos also the first run (old) on the same frontend.

Definitions (same as sparse_prompt_test_20261109/entity_issue_rates.py and scoring v6):
- entities = ledger entities of the case: specified = prompt_bound (pb) with >=1 detected occurrence, unspecified =
  prompt_unbound (ge). Entities the V-V agent added at issue time (n...) are not in the ledger; they are counted
  separately (distinct n subjects of confirmed issues), never in the entity denominators.
- an issue involves an unspecified entity when one of its subject entities has label unspecified (ge or n), from
  episode_scoring unit_scores (scoring v6). Issue counts are confirmed issues unless stated.
- an entity "has a problem" when it is a subject of >=1 confirmed issue (vv_review / vl_review entity_refs).
  recurring = detected in >=2 shots. V-L issues can only concern specified (contract) entities.
Writes results_summary.json."""
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

EXP = Path(__file__).resolve().parent
MODELS = dict(cinetrans='CineTrans-DiT', holocine='HoloCine', storymem='StoryMem', wan21='Wan2.1', wan22='Wan2.2')


def read(p):
    return json.loads(Path(p).read_text())


def subjects(units):
    return [{x['entity_key'] for x in u.get('entity_refs') or [] if x.get('role') == 'subject'}
            for u in units if u.get('verdict') == 'confirmed']


def record(case, out, vl_review):
    led = read(case / 'episode_entities.json')
    shots = lambda e: len({o['shot_id'] for o in e.get('occurrences') or []})
    spec = {e['global_entity_id']: shots(e) for e in led['prompt_bound'] if e.get('occurrences')}
    spec_all = {e['global_entity_id'] for e in led['prompt_bound']}
    unspec = {e['global_entity_id']: shots(e) for e in led['prompt_unbound']}
    sc = read(out / 'episode_scoring/result.json')
    vv = subjects(read(out / 'vv_review/result.json')['units'])
    vl = subjects(read(vl_review)['units'])
    vv_subj = set().union(*vv) if vv else set()
    vl_subj = set().union(*vl) if vl else set()
    r = defaultdict(int)
    for u in sc['unit_scores']:
        if u['verdict'] not in ('confirmed', 'uncertain'):
            continue
        b = 'vl' if u['bucket'] == 'v_l' else 'vv'
        keys = [x['entity_key'] for x in u.get('subject_entities') or []]
        labels = {x['label'] for x in u.get('subject_entities') or []}
        tag = f'{b}_{u["verdict"]}'
        r[tag] += 1
        r[f'{tag}_unspec'] += 'unspecified' in labels
        r[f'{tag}_ge'] += any(k.startswith('ge') for k in keys)
        r[f'{tag}_n_only'] += any(k.startswith('n') for k in keys) and not any(k.startswith('ge') for k in keys)
        if b == 'vv':
            r[f'vv_{u["verdict"]}_{u["bucket"]}'] += 1
    r['videos'] = 1
    for label, ents in (('spec', spec), ('unspec', unspec)):
        r[f'{label}_entities'] += len(ents)
        r[f'{label}_with_vv'] += sum(e in vv_subj for e in ents)
        r[f'{label}_recurring'] += sum(n >= 2 for n in ents.values())
        r[f'{label}_recurring_with_vv'] += sum(n >= 2 and e in vv_subj for e, n in ents.items())
    r['contract_entities'] += len(spec_all)
    r['contract_with_vl'] += sum(e in vl_subj for e in spec_all)
    r['contract_with_any'] += sum(e in vl_subj or e in vv_subj for e in spec_all)
    r['added_n_subjects'] += len({k for k in vv_subj if k.startswith('n')})
    s = sc['scores']
    scores = dict(v_l=s['v_l'], within=s['v_v']['within_shot'], cross=s['v_v']['cross_shot'], v_v=s['v_v']['overall'],
                  uec=s['uec'])
    return r, scores


def summarize(rows):
    c = defaultdict(int)
    for r, _ in rows:
        for k, v in r.items():
            c[k] += v
    rate = lambda n, d: round(n / d, 4) if d else None
    mean = lambda k: round(st.mean(s[k] for _, s in rows if s[k] is not None), 2) if rows else None
    vv, vl = c['vv_confirmed'], c['vl_confirmed']
    return dict(
        videos=c['videos'],
        scores=dict(v_l=mean('v_l'), within=mean('within'), cross=mean('cross'), v_v=mean('v_v'), uec=mean('uec')),
        confirmed=dict(v_l=vl, v_v=vv, within=c['vv_confirmed_within_shot'], cross=c['vv_confirmed_cross_shot'],
                       uncertain_v_l=c['vl_uncertain'], uncertain_v_v=c['vv_uncertain']),
        entities=dict(specified=c['spec_entities'], unspecified=c['unspec_entities'],
                      unspecified_share=rate(c['unspec_entities'], c['spec_entities'] + c['unspec_entities']),
                      specified_recurring=c['spec_recurring'], unspecified_recurring=c['unspec_recurring'],
                      unspecified_share_recurring=rate(c['unspec_recurring'], c['spec_recurring'] + c['unspec_recurring']),
                      contract_entities=c['contract_entities'], added_n_subjects=c['added_n_subjects']),
        issues=dict(vv_with_unspecified=c['vv_confirmed_unspec'], vv_share=rate(c['vv_confirmed_unspec'], vv),
                    vv_with_ge=c['vv_confirmed_ge'], vv_with_n_only=c['vv_confirmed_n_only'],
                    all_issues=vl + vv, all_share=rate(c['vv_confirmed_unspec'], vl + vv),
                    vv_uncertain_with_unspecified=c['vv_uncertain_unspec']),
        per_entity=dict(spec_vv=[c['spec_with_vv'], c['spec_entities'], rate(c['spec_with_vv'], c['spec_entities'])],
                        unspec_vv=[c['unspec_with_vv'], c['unspec_entities'], rate(c['unspec_with_vv'], c['unspec_entities'])],
                        spec_recurring_vv=[c['spec_recurring_with_vv'], c['spec_recurring'],
                                           rate(c['spec_recurring_with_vv'], c['spec_recurring'])],
                        unspec_recurring_vv=[c['unspec_recurring_with_vv'], c['unspec_recurring'],
                                             rate(c['unspec_recurring_with_vv'], c['unspec_recurring'])],
                        contract_vl=[c['contract_with_vl'], c['contract_entities'], rate(c['contract_with_vl'], c['contract_entities'])],
                        contract_any=[c['contract_with_any'], c['contract_entities'], rate(c['contract_with_any'], c['contract_entities'])]))


def main():
    new, old = defaultdict(list), defaultdict(list)
    for path in sorted((EXP / 'runs').glob('*/progress.json')):
        for tid, s in read(path)['tasks'].items():
            if s.get('status') != 'success':
                continue
            model = tid.split('__')[1]
            case, out = Path(s['case_dir']), Path(s['output_dir'])
            rec = record(case, out, out / 'vl_review/result.json')
            mode = 'reuse' if s.get('mode') == 'reuse_vv' else 'full'
            for key in (model, 'all', f'{mode}/all'):
                new[key].append(rec)
            if mode == 'reuse':
                src = Path(s['source_attempt'])
                orec = record(case, src / 'results', src / 'results/vl_review/result.json')
                old[model].append(orec)
                old['all'].append(orec)
                new[f'reuse/{model}'].append(rec)
    report = dict(new={k: summarize(v) for k, v in sorted(new.items())},
                  old_reuse={k: summarize(v) for k, v in sorted(old.items())})
    (EXP / 'results_summary.json').write_text(json.dumps(report, indent=1) + '\n')
    for side in ('new', 'old_reuse'):
        print('=' * 30, side)
        for k, s in report[side].items():
            pe = s['per_entity']
            print(f"{k:16s} n={s['videos']:4d} | V-L {s['scores']['v_l']} within {s['scores']['within']} cross {s['scores']['cross']} "
                  f"V-V {s['scores']['v_v']} UEC {s['scores']['uec']} | conf V-L {s['confirmed']['v_l']} V-V {s['confirmed']['v_v']} "
                  f"(w {s['confirmed']['within']}, x {s['confirmed']['cross']})")
            print(f"{'':16s} entities spec {s['entities']['specified']} unspec {s['entities']['unspecified']} share {s['entities']['unspecified_share']} "
                  f"| recurring spec {s['entities']['specified_recurring']} unspec {s['entities']['unspecified_recurring']} share {s['entities']['unspecified_share_recurring']} "
                  f"| added n {s['entities']['added_n_subjects']}")
            print(f"{'':16s} issues V-V w/ unspec {s['issues']['vv_with_unspecified']} share {s['issues']['vv_share']} (ge {s['issues']['vv_with_ge']}, n only {s['issues']['vv_with_n_only']}) "
                  f"| all issues {s['issues']['all_issues']} share {s['issues']['all_share']}")
            print(f"{'':16s} per-entity V-V spec {pe['spec_vv']} unspec {pe['unspec_vv']} | recurring spec {pe['spec_recurring_vv']} unspec {pe['unspec_recurring_vv']} "
                  f"| contract V-L {pe['contract_vl']} any {pe['contract_any']}")


if __name__ == '__main__':
    main()
