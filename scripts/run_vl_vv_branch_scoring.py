#!/usr/bin/env python3
"""Branch scoring (scoring v5): V-L and V-V scored separately from reviewed units.

Two independent text-only model calls assign impact severities and
same-bucket duplicate links: one sees only the V-L units, the other only the
V-V units.  A branch without units makes no call.  Python then applies the
existing penalty rubric v2 (base deductions 10/25/50/80 x reviewer
confidence 1/0.75/0.5; a duplicate group deducts its maximum; a bucket is
100 * product(1 - deduction/100)):

- V-L score: bucket v_l.
- V-V scores: within_shot and cross_shot, and their mean (overall).
- Unintentional-entity subset: the same product over only the V-V issues
  whose subject entities include an entity with final provenance
  prompt_unbound (an unintentional entity); the remainder is the product
  over the other V-V issues, so that bucket = unintentional x remainder / 100
  exactly before rounding.  An upper bound also counts issues whose subject
  provenance is only uncertain.
- Counts and proportions of confirmed V-V issues involving at least one
  unintentional entity, total and per scope.  An independent issue is one
  duplicate group of confirmed units (a unit split by the reviewer is its own
  issue); each is counted once however many unintentional entities it has.
"""
import argparse
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import run_wedetect_shot_entities as io  # noqa: E402
import vl_vv_branch_common as common  # noqa: E402
import vl_vv_repair_loop as repair_loop  # noqa: E402

CENT = Decimal('0.01')
BUCKETS = ('v_l', 'within_shot', 'cross_shot')
STATUS_ORDER = {'none': 0, 'possible': 1, 'definite': 2}


def save(path, value):
    io.dump(Path(path), value)


def rubric():
    cfg = common.config()['scoring']
    return ({key: Decimal(value) for key, value in cfg['base_deductions'].items()},
            {key: Decimal(str(value)) for key, value in cfg['reviewer_confidence_factors'].items()})


def rounded(value):
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def load_review(path, branch):
    review = common.read(path)
    spec = common.REVIEW[branch]
    if review.get('protocol') != spec['protocol'] or review.get('status') != 'success':
        raise ValueError(f'Expected a successful {spec["protocol"]} result: {path}')
    common.require_records(dict(units=review['units']), str(path))
    ids = [unit['unit_id'] for unit in review['units']]
    if len(ids) != len(set(ids)):
        raise ValueError(f'Repeated unit IDs in {path}')
    if any(unit['branch'] != common.LABEL[branch] for unit in review['units']):
        raise ValueError(f'{path} contains units of another branch')
    return review


def scorer_input(branch, review):
    names = {row['entity_key']: row['name'] for row in review.get('entities', [])}
    units = []
    for unit in review['units']:
        row = dict(unit_id=unit['unit_id'], parent_issue_id=unit['parent_issue_id'], scope=unit['scope'],
                   subcategory=unit['subcategory'], description=unit['description'], shot_ids=unit['shot_ids'],
                   verdict=unit['verdict'], basis=unit['basis'], confidence=unit['confidence'],
                   assessment=unit['assessment'],
                   evidence=[dict(shot_id=ev['shot_id'], frame_id=ev['frame_id'], role=ev['role'],
                                  observation=ev['observation']) for ev in unit['evidence']])
        if branch == 'vl':
            row['requirement_quote'] = unit['v_l_detail']['requirement_quote']
        else:
            row['comparison'] = unit['v_v_detail']['comparison']
            row['entities'] = [dict(name=names.get(ref['entity_key'], ref['entity_key']), role=ref['role'])
                               for ref in unit['entity_refs']]
        units.append(row)
    return dict(protocol=common.SCORING[branch]['protocol'], units=units)


def assessment_errors(response, units, base):
    """EVERY semantic problem of a schema-valid severity response."""
    order = {unit['unit_id']: index for index, unit in enumerate(units)}
    by_id = {unit['unit_id']: unit for unit in units}
    errors, got = [], {}
    for position, row in enumerate(response['assessments']):
        uid = row['unit_id']
        if uid not in by_id or uid in got:
            errors.append(f'Unknown or repeated unit_id {uid!r} (assessments[{position}]; assess each unit exactly once)')
            continue
        got[uid] = row
        unit, severity, duplicate = by_id[uid], row['severity'], row['duplicate_of']
        if unit['verdict'] == 'confirmed':
            if severity not in base:
                errors.append(f'Confirmed unit {uid} needs a severity (got {severity!r}; allowed {sorted(base)})')
            if duplicate is not None:
                other = by_id.get(duplicate)
                if duplicate == uid:
                    errors.append(f'{uid}: duplicate_of cannot point to itself')
                elif other is None or order[duplicate] >= order[uid]:
                    errors.append(f'{uid}: duplicate_of must be an earlier unit (got {duplicate!r})')
                elif other['verdict'] != 'confirmed':
                    errors.append(f'{uid}: duplicate_of must be a confirmed unit ({duplicate} is {other["verdict"]})')
                elif other['scope'] != unit['scope']:
                    errors.append(f'{uid}: duplicate_of must be in the same scope ({duplicate} is {other["scope"]}, '
                                  f'{uid} is {unit["scope"]})')
                elif other['parent_issue_id'] == unit['parent_issue_id'] and other['split']:
                    errors.append(f'{uid}: split siblings are distinct problems; duplicate_of cannot link {duplicate}')
        elif severity != 'none' or duplicate is not None:
            errors.append(f'{uid}: a {unit["verdict"]} unit gets severity "none" and duplicate_of null')
    missing = sorted(set(by_id) - set(got))
    if missing:
        errors.append(f'Missing assessments for units {missing}')
    for uid, row in got.items():
        target = row['duplicate_of']
        if target is not None and target in got and got[target]['duplicate_of'] is not None:
            errors.append(f'{uid}: duplicate chains are not allowed ({target} itself has duplicate_of '
                          f'{got[target]["duplicate_of"]!r}); point to the root')
    return errors, got


def unintentional_status(unit):
    """definite: a subject entity is prompt_unbound; possible: only uncertain subjects; none otherwise."""
    if unit['branch'] != 'v_v':
        return 'none'
    labels = {ref['provenance'] for ref in unit['entity_refs'] if ref['role'] == 'subject'}
    if 'prompt_unbound' in labels:
        return 'definite'
    if 'uncertain' in labels:
        return 'possible'
    return 'none'


def materialize(units, assessments, entities):
    base, factors = rubric()
    ledger, groups = [], {bucket: {} for bucket in BUCKETS}
    unit_counts = {bucket: dict(units=0, confirmed=0, rejected=0, uncertain=0) for bucket in BUCKETS}
    for unit in units:
        bucket = unit['scope']
        assessment = assessments[unit['unit_id']]
        severity, verdict = assessment['severity'], unit['verdict']
        deduction = base[severity] * factors[unit['confidence']] if severity in base else Decimal(0)
        root = (assessment['duplicate_of'] or unit['unit_id']) if verdict == 'confirmed' else None
        status = unintentional_status(unit)
        unit_counts[bucket]['units'] += 1
        unit_counts[bucket][verdict] += 1
        ledger.append(dict(unit_id=unit['unit_id'], parent_issue_id=unit['parent_issue_id'], bucket=bucket,
                           subcategory=unit['subcategory'], verdict=verdict, review_confidence=unit['confidence'],
                           severity=severity, duplicate_of=assessment['duplicate_of'], event_root_unit_id=root,
                           base_deduction=int(base.get(severity, 0)), adjusted_deduction=float(deduction),
                           unintentional_status=status if verdict == 'confirmed' else None,
                           reason=assessment['reason']))
        if root is not None:
            group = groups[bucket].setdefault(root, dict(unit_ids=[], deduction=Decimal(0), status='none',
                                                         unintentional_entities=set()))
            group['unit_ids'].append(unit['unit_id'])
            group['deduction'] = max(group['deduction'], deduction)
            if STATUS_ORDER[status] > STATUS_ORDER[group['status']]:
                group['status'] = status
            group['unintentional_entities'].update(ref['entity_key'] for ref in unit['entity_refs']
                                                   if ref['role'] == 'subject' and ref['provenance'] == 'prompt_unbound')

    def product(bucket, keep=lambda group: True):
        score = Decimal(100)
        for group in groups[bucket].values():
            if keep(group):
                score *= 1 - group['deduction'] / 100
        return score

    def vv_view(keep):
        within, cross = product('within_shot', keep), product('cross_shot', keep)
        return dict(within_shot=rounded(within), cross_shot=rounded(cross), overall=rounded((within + cross) / 2))

    within, cross = product('within_shot'), product('cross_shot')
    definite = lambda group: group['status'] == 'definite'  # noqa: E731
    scores = dict(
        v_l=rounded(product('v_l')),
        v_v=dict(within_shot=rounded(within), cross_shot=rounded(cross), overall=rounded((within + cross) / 2)),
        v_v_unintentional=vv_view(definite),
        v_v_unintentional_or_uncertain=vv_view(lambda group: group['status'] in ('definite', 'possible')),
        v_v_remainder=vv_view(lambda group: group['status'] != 'definite'))
    factorization = {bucket: dict(
        bucket_score=float(product(bucket)),
        unintentional_times_remainder=float(product(bucket, definite) * product(bucket, lambda g: not definite(g)) / 100))
        for bucket in ('within_shot', 'cross_shot')}

    names = {row['entity_key']: row['name'] for row in entities}

    def issue_stats(buckets):
        rows = [group for bucket in buckets for group in groups[bucket].values()]
        total = len(rows)
        involving = sum(group['status'] == 'definite' for group in rows)
        upper = sum(group['status'] in ('definite', 'possible') for group in rows)
        return dict(confirmed_issues=total, involving_unintentional=involving,
                    proportion=round(involving / total, 6) if total else None,
                    involving_unintentional_or_uncertain=upper,
                    proportion_upper_bound=round(upper / total, 6) if total else None,
                    confirmed_units=sum(len(group['unit_ids']) for group in rows))

    unintentional_entities = sorted({key for bucket in ('within_shot', 'cross_shot') for group in groups[bucket].values()
                                     for key in group['unintentional_entities']})
    statistics = dict(
        counting_unit='independent confirmed V-V issue = one duplicate group of confirmed reviewed units (a unit split '
                      'by the reviewer is its own issue); counted once however many unintentional entities it involves',
        involvement_rule='an issue involves an unintentional entity when one of its subject entities has final '
                         'provenance prompt_unbound; context entities do not count; uncertain provenance counts only '
                         'in the upper bound',
        total=issue_stats(('within_shot', 'cross_shot')), within_shot=issue_stats(('within_shot',)),
        cross_shot=issue_stats(('cross_shot',)),
        unintentional_entities=[dict(entity_key=key, name=names.get(key, key)) for key in unintentional_entities])
    events = [dict(bucket=bucket, root_unit_id=root, unit_ids=group['unit_ids'],
                   applied_deduction=float(group['deduction']), unintentional_status=group['status'])
              for bucket in BUCKETS for root, group in groups[bucket].items()]
    for bucket in BUCKETS:
        unit_counts[bucket]['independent_confirmed_issues'] = len(groups[bucket])
    return scores, statistics, ledger, events, unit_counts, factorization


def run(vl_review_path, vv_review_path, out, timeout=1800, model=common.MODEL, reasoning=common.REASONING):
    common.require_api(model, reasoning, 'branch scoring')
    paths = dict(vl=Path(vl_review_path).resolve(), vv=Path(vv_review_path).resolve())
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError('Use a fresh episode-scoring output directory')
    reviews = {branch: load_review(paths[branch], branch) for branch in common.BRANCHES}
    if reviews['vl']['source_case'] != reviews['vv']['source_case']:
        raise ValueError('The V-L and V-V reviews come from different cases')
    base, _ = rubric()
    source_paths = [paths['vl'], paths['vv'], Path(__file__).resolve(), Path(repair_loop.__file__).resolve(),
                    common.SCORING['vl']['schema'], common.SCORING['vv']['schema'],
                    *common.static_source_paths(common.SCORING['vl']['prompt'], common.SCORING['vv']['prompt'])]
    hashes = {str(Path(path).resolve()): io.sha(path) for path in source_paths}
    out.mkdir(parents=True)
    for branch in common.BRANCHES:
        shutil.copy2(paths[branch], out / f'{branch}_review_input.json')
    save(out / 'source_hashes.json', hashes)
    state = dict(protocol=common.SCORING_PROTOCOL, status='running', model=model, reasoning=reasoning,
                 source_reviews={branch: str(paths[branch]) for branch in common.BRANCHES}, started=time.time(),
                 unit_counts={branch: len(reviews[branch]['units']) for branch in common.BRANCHES})
    save(out / 'run.json', state)

    def score_branch(branch):
        units = reviews[branch]['units']
        if not units:
            return {}, [], None
        spec = common.SCORING[branch]
        payload = scorer_input(branch, reviews[branch])
        save(out / f'scorer_input_{branch}.json', payload)
        prompt_path = common.write_rendered_prompt(spec['prompt'], out / f'prompt_rendered_{branch}.txt')
        assessments, _, usage, repair = repair_loop.call_with_repair(
            out / f'call_{branch}', payload, [], timeout, prompt_path=prompt_path, schema=common.read(spec['schema']),
            model=model, reasoning=reasoning, stage=f'{branch.upper()} scoring', repair_prompt=common.REPAIR_PROMPT,
            collect_errors=lambda candidate: assessment_errors(candidate, units, base))
        return assessments, usage, repair

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {branch: pool.submit(score_branch, branch) for branch in common.BRANCHES}
            outcomes = {branch: future.result() for branch, future in futures.items()}
        units = reviews['vl']['units'] + reviews['vv']['units']
        assessments = {**outcomes['vl'][0], **outcomes['vv'][0]}
        entities = reviews['vl'].get('entities', []) + reviews['vv'].get('entities', [])
        scores, statistics, ledger, events, unit_counts, factorization = materialize(units, assessments, entities)
        if any(io.sha(path) != digest for path, digest in hashes.items()):
            raise ValueError('A reviewed input changed during scoring')
        usage = outcomes['vl'][1] + outcomes['vv'][1]
        calls = {branch: (len(outcomes[branch][2]['rounds']) if outcomes[branch][2] else 0) for branch in common.BRANCHES}
        _, factors = rubric()
        result = dict(
            protocol=common.SCORING_PROTOCOL, status='success', scores=scores,
            v_v_issue_statistics=statistics, counts=unit_counts, unit_scores=ledger, event_scores=events,
            factorization_check=factorization,
            scoring_rule=dict(
                rubric_version='penalty_v2', base_deductions={k: int(v) for k, v in base.items()},
                reviewer_confidence_factors={k: float(v) for k, v in factors.items()},
                event_rule='confirmed units linked by duplicate_of form one event (independent issue); the event deducts '
                           'its maximum adjusted deduction; split units are distinct events',
                bucket_rule='100 * product(1 - event_deduction / 100), rounded half up to 2 decimals',
                v_v_rule='overall = mean of within_shot and cross_shot',
                unintentional_rule='v_v_unintentional = the same product over the events whose subject entities '
                                   'include a prompt_unbound entity; v_v_remainder = product over the other V-V events; '
                                   'bucket = unintentional x remainder / 100 before rounding; '
                                   'v_v_unintentional_or_uncertain also counts events whose subjects are only uncertain',
                empty_bucket='a bucket or subset with no confirmed events scores 100; that is not proof of a '
                             'consistent video, see the issue counts'),
            source_reviews={branch: str(paths[branch]) for branch in common.BRANCHES},
            source_review_sha256={branch: hashes[str(paths[branch])] for branch in common.BRANCHES},
            model=model, reasoning=reasoning, calls=calls,
            repair_rounds={branch: (outcomes[branch][2]['repair_rounds'] if outcomes[branch][2] else 0)
                           for branch in common.BRANCHES},
            usage=usage, token_cost=common.estimated_cost(usage),
            limitation='Scores summarize confirmed reviewed units; severities come from text-only calls; provenance '
                       'labels are model judgments checked against the text; no human calibration.')
        save(out / 'result.json', result)
        state.update(status='success', seconds=time.time() - state['started'], scores=scores,
                     token_cost=result['token_cost'])
        return result
    except BaseException as exc:
        state.update(status='failed', seconds=time.time() - state['started'], error=str(exc)[:4000])
        usage = []
        for branch in common.BRANCHES:
            audit = out / f'call_{branch}_repair_audit.json'
            if audit.is_file():
                usage += common.read(audit).get('usage', [])
        state['token_cost'] = common.estimated_cost(usage)
        raise
    finally:
        save(out / 'run.json', state)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--vl-review', type=Path, required=True, help='Successful V-L review result.json')
    parser.add_argument('--vv-review', type=Path, required=True, help='Successful V-V review result.json')
    parser.add_argument('--output', type=Path, required=True, help='Fresh scoring output directory')
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--model', default=common.MODEL, choices=[common.MODEL])
    parser.add_argument('--reasoning', default=common.REASONING, choices=[common.REASONING])
    args = parser.parse_args()
    run(args.vl_review, args.vv_review, args.output, args.timeout, args.model, args.reasoning)


if __name__ == '__main__':
    main()
