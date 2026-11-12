#!/usr/bin/env python3
"""Branch scoring: scoring v6 (chain v6, default) or scoring v5 (chain v5).

Scoring v6 (2026-11-02; owner decisions Q7 and Q8): the same two text-only
severity calls (V-L units, V-V units), without duplicate links.  Each confirmed
unit deducts D = base(severity) x factor(verifier confidence) on its own
(10/25/50/80 x 1/0.75/0.5); each uncertain unit deducts base(severity) x 0.25
(config uncertain_factor; owner, 2026-11-03), its severity rated as if the
problem were real; rejected units deduct nothing and are not sent to the
severity calls.  A dimension scores 100 * exp(-sum(D) / (100 * S)), S = number
of shots of the case manifest (per-shot rule, owner 2026-11-09; before, 100 *
product(1 - D/100)), and uec is the mean of V-L, V-V within_shot and V-V
cross_shot.  The statistics
count, per scope, the confirmed V-V issues with at least one unspecified
subject entity; the label comes from the entity ledger (pb... specified;
ge... and entities added by detection, n..., unspecified), with no
unintentional / remainder scores and no upper bound.

Scoring v5 (chain v5, unchanged): V-L and V-V scored separately from reviewed units.

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


def rubric(config=None):
    cfg = (config or common.config())['scoring']
    return ({key: Decimal(value) for key, value in cfg['base_deductions'].items()},
            {key: Decimal(str(value)) for key, value in cfg['reviewer_confidence_factors'].items()})


def uncertain_factor(config):
    """Scoring v6: the factor of an uncertain unit (owner, 2026-11-03)."""
    return Decimal(str(config['scoring']['uncertain_factor']))


def rounded(value):
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def case_shot_count(case):
    """Scoring v6: S, the number of shots of the case's keyframe manifest (raw_manifest.json)."""
    shots = common.read(Path(case) / 'raw_manifest.json')['shots']
    if not shots:
        raise ValueError(f'{case}: the manifest has no shots')
    return len(shots)


def per_shot_score(deductions, shots):
    """Scoring v6 dimension score (owner, 2026-11-09): 100 * exp(-sum(D) / (100 * S)).

    sum(D) / S is the deduction per shot; one full deduction (100) per shot gives 100/e.  No deduction gives 100.
    """
    if shots < 1:
        raise ValueError('The number of shots must be at least 1')
    return Decimal(100) * (-sum(deductions, Decimal(0)) / (Decimal(100) * shots)).exp()


def load_review(path, branch, chain='v5'):
    review = common.read(path)
    chain_row = common.chain_spec(chain)
    spec = chain_row['review'][branch]
    if review.get('protocol') != spec['protocol'] or review.get('status') != 'success':
        raise ValueError(f'Expected a successful {spec["protocol"]} result: {path}')
    common.require_records(dict(units=review['units']), str(path), chain_row['records'])
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
        uec=rounded((product('v_l') + within + cross) / 3),
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


# --------------------------------------------------------------------------
# Scoring v6 (chain v6): no duplicates; labels of issue entities from the ledger.
# --------------------------------------------------------------------------

def scored_units_v6(units):
    """The units that receive a severity: confirmed and uncertain; rejected units deduct nothing and are not sent."""
    return [unit for unit in units if unit['verdict'] != 'rejected']


def scorer_input_v6(branch, review):
    """Text the severity call sees: the confirmed and uncertain issues, without source IDs (no duplicates to find)."""
    names = {row['entity_key']: row['name'] for row in review.get('entities', [])}
    units = []
    for unit in scored_units_v6(review['units']):
        row = dict(unit_id=unit['unit_id'], scope=unit['scope'], subcategory=unit['subcategory'],
                   description=unit['description'], shot_ids=unit['shot_ids'], verdict=unit['verdict'],
                   basis=unit['basis'], confidence=unit['confidence'], assessment=unit['assessment'],
                   evidence=[dict(shot_id=ev['shot_id'], frame_id=ev['frame_id'], role=ev['role'],
                                  observation=ev['observation']) for ev in unit['evidence']])
        if branch == 'vl':
            row['requirement_quote'] = unit['v_l_detail']['requirement_quote']
        else:
            row['comparison'] = unit['v_v_detail']['comparison']
            row['entities'] = [dict(name=names.get(ref['entity_key'], ref['entity_key']), role=ref['role'])
                               for ref in unit['entity_refs']]
        units.append(row)
    return dict(protocol=common.SCORING_V6[branch]['protocol'], units=units)


def assessment_errors_v6(response, units, base):
    """EVERY semantic problem of a schema-valid severity response (scoring v6: no duplicate links).

    units are the scored units (confirmed and uncertain); each needs one severity.
    """
    by_id = {unit['unit_id']: unit for unit in units}
    errors, got = [], {}
    for position, row in enumerate(response['assessments']):
        uid = row['unit_id']
        if uid not in by_id or uid in got:
            errors.append(f'Unknown or repeated unit_id {uid!r} (assessments[{position}]; assess each unit exactly once)')
            continue
        got[uid] = row
        unit, severity = by_id[uid], row['severity']
        if unit['verdict'] == 'rejected':
            errors.append(f'{uid}: a rejected unit is not scored')
        elif severity not in base:
            errors.append(f'{unit["verdict"].capitalize()} unit {uid} needs a severity (got {severity!r}; '
                          f'allowed {sorted(base)})')
    missing = sorted(set(by_id) - set(got))
    if missing:
        errors.append(f'Missing assessments for units {missing}')
    return errors, got


def materialize_v6(units, assessments, entities, cfg, shots):
    """Scores and statistics of chain v6.

    Each confirmed unit deducts D = w(severity) x gamma(confidence) and each uncertain unit
    D = w(severity) x uncertain_factor, each on its own; rejected units deduct nothing and have no severity.  A
    dimension scores 100 * exp(-sum(D) / (100 * shots)) (per_shot_score); uec is the mean of v_l, within_shot and
    cross_shot.  A confirmed V-V
    or uncertain unit involves an unspecified entity when one of its subject entities has the ledger label unspecified
    (ge... or an added n...); the statistics count confirmed units only.
    """
    base, factors = rubric(cfg)
    uncertain = uncertain_factor(cfg)
    labels = {row['entity_key']: row['label'] for row in entities}
    names = {row['entity_key']: row['name'] for row in entities}
    ledger, deductions = [], {bucket: [] for bucket in BUCKETS}
    unit_counts = {bucket: dict(units=0, confirmed=0, rejected=0, uncertain=0) for bucket in BUCKETS}
    involved = {bucket: [] for bucket in ('within_shot', 'cross_shot')}
    for unit in units:
        bucket, verdict = unit['scope'], unit['verdict']
        confirmed = verdict == 'confirmed'
        if verdict == 'rejected':
            severity, reason, factor, factor_basis = None, None, Decimal(0), 'rejected: no deduction'
        else:
            assessment = assessments.get(unit['unit_id'])
            if assessment is None or assessment['severity'] not in base:
                raise ValueError(f'{unit["unit_id"]}: the {verdict} unit needs a severity')
            severity, reason = assessment['severity'], assessment['reason']
            factor, factor_basis = ((factors[unit['confidence']], f'verifier confidence {unit["confidence"]}')
                                    if confirmed else (uncertain, 'uncertain verdict'))
        deduction = base[severity] * factor if severity is not None else Decimal(0)
        subjects = []
        for ref in unit['entity_refs']:
            if ref['role'] != 'subject':
                continue
            if ref['entity_key'] not in labels:
                raise ValueError(f'{unit["unit_id"]}: subject entity {ref["entity_key"]} has no entity record with a label')
            subjects.append(dict(entity_key=ref['entity_key'], label=labels[ref['entity_key']]))
        # Every deducting V-V unit carries the label, so an offline rescoring can drop uncertain ones too.
        involves = (any(row['label'] == 'unspecified' for row in subjects)
                    if severity is not None and unit['branch'] == 'v_v' else None)
        unit_counts[bucket]['units'] += 1
        unit_counts[bucket][verdict] += 1
        ledger.append(dict(unit_id=unit['unit_id'], source_candidate_ids=list(unit['source_candidate_ids']),
                           bucket=bucket, subcategory=unit['subcategory'], verdict=verdict,
                           review_confidence=unit['confidence'], severity=severity,
                           base_deduction=int(base[severity]) if severity is not None else 0,
                           factor=float(factor), factor_basis=factor_basis, adjusted_deduction=float(deduction),
                           subject_entities=subjects, involves_unspecified_entity=involves, reason=reason))
        if severity is not None:
            deductions[bucket].append(deduction)
        if confirmed:
            if unit['branch'] == 'v_v':
                involved[bucket].append((unit['unit_id'], involves, [row['entity_key'] for row in subjects
                                                                     if row['label'] == 'unspecified']))

    v_l, within, cross = (per_shot_score(deductions[bucket], shots) for bucket in BUCKETS)
    scores = dict(v_l=rounded(v_l),
                  v_v=dict(within_shot=rounded(within), cross_shot=rounded(cross), overall=rounded((within + cross) / 2)),
                  uec=rounded((v_l + within + cross) / 3))

    def issue_stats(buckets):
        rows = [row for bucket in buckets for row in involved[bucket]]
        total, count = len(rows), sum(1 for _, flag, _ in rows if flag)
        return dict(confirmed_issues=total, with_unspecified_subject=count,
                    share=round(count / total, 6) if total else None,
                    unit_ids_with_unspecified_subject=[uid for uid, flag, _ in rows if flag])

    keys = sorted({key for bucket in involved for _, _, unspecified in involved[bucket] for key in unspecified})
    statistics = dict(
        counting_unit='one confirmed V-V issue (a verified unit; merged duplicates are already one unit), counted once '
                      'however many unspecified subject entities it has',
        label_rule='subject entity labels come from the entity ledger: a prompt_bound entity (pb...) is specified; a '
                   'prompt_unbound entity (ge...) and an entity added by detection (n...) are unspecified; context '
                   'entities do not count',
        within_shot=issue_stats(('within_shot',)), cross_shot=issue_stats(('cross_shot',)),
        total=issue_stats(('within_shot', 'cross_shot')),
        unspecified_subject_entities=[dict(entity_key=key, name=names.get(key, key)) for key in keys])
    for bucket in BUCKETS:
        unit_counts[bucket]['confirmed_issues'] = unit_counts[bucket]['confirmed']
        unit_counts[bucket]['deducting_issues'] = len(deductions[bucket])
    return scores, statistics, ledger, unit_counts


def reused_vl_scoring(folder, vl_review, model, reasoning):
    """The V-L severity call of an earlier successful scoring v6 run of the same V-L review (--vl-scoring-from).

    Owner, 2026-11-11: when the plug-in version is scored on top of the base version, it reuses the base version's
    V-L severities instead of rating the same V-L review again, so both versions report the same V-L score. The
    earlier run must have scored a byte-identical V-L review with the same model and reasoning; run_v6 also checks
    that the rendered V-L prompt and the V-L scorer input are byte-identical before using the response.
    Returns None when the earlier run made no V-L call (no V-L unit to score)."""
    folder = Path(folder).resolve()
    result = common.read(folder / 'result.json')
    if (result.get('status') != 'success' or result.get('chain') != 'v6'
            or result.get('protocol') != common.SCORING_PROTOCOL_V6):
        raise ValueError(f'{folder}: --vl-scoring-from needs a successful scoring v6 result')
    if (result.get('model'), result.get('reasoning')) != (model, reasoning):
        raise ValueError(f'{folder}: scored with {result.get("model")}/{result.get("reasoning")}, not {model}/{reasoning}')
    if result['source_review_sha256']['vl'] != io.sha(vl_review):
        raise ValueError(f'{folder}: its V-L review differs from {vl_review}')
    audit_path = folder / 'call_vl_repair_audit.json'
    if not audit_path.is_file():
        return None
    audit = common.read(audit_path)
    accepted = [r for r in audit['rounds'] if r.get('accepted')]
    if audit.get('status') != 'passed' or len(accepted) != 1:
        raise ValueError(f'{audit_path}: no single accepted V-L scoring response')
    call = folder / Path(accepted[0]['call_folder']).name  # call folders sit beside the audit, also after a move
    return dict(folder=folder, result=folder / 'result.json', response=call / 'response.json',
                prompt=folder / 'prompt_rendered_vl.txt', scorer_input=folder / 'scorer_input_vl.json',
                repair_rounds=audit.get('repair_rounds', 0), usage_not_counted=audit.get('usage', []))


def run_v6(vl_review_path, vv_review_path, out, timeout=1800, model=common.MODEL, reasoning=common.REASONING,
           vl_scoring_from=None):
    """Scoring v6 (chain v6): severities of confirmed and uncertain issues per branch; each deducts on its own.

    vl_scoring_from: an earlier scoring v6 folder of the same V-L review whose V-L severities are reused (no V-L call)."""
    common.require_api(model, reasoning, 'branch scoring')
    chain_row = common.chain_spec('v6')
    cfg = common.config(chain_row['config'])
    paths = dict(vl=Path(vl_review_path).resolve(), vv=Path(vv_review_path).resolve())
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError('Use a fresh episode-scoring output directory')
    reused = None
    if vl_scoring_from is not None:
        reused = reused_vl_scoring(vl_scoring_from, paths['vl'], model, reasoning)
        reused_source = Path(vl_scoring_from).resolve()
    reviews = {branch: load_review(paths[branch], branch, 'v6') for branch in common.BRANCHES}
    if reviews['vl']['source_case'] != reviews['vv']['source_case']:
        raise ValueError('The V-L and V-V reviews come from different cases')
    manifest_path = Path(reviews['vl']['source_case']) / 'raw_manifest.json'
    shots = case_shot_count(manifest_path.parent)
    base, factors = rubric(cfg)
    specs = chain_row['scoring']
    source_paths = [paths['vl'], paths['vv'], manifest_path, Path(__file__).resolve(), Path(repair_loop.__file__).resolve(),
                    specs['vl']['schema'], specs['vv']['schema'],
                    *common.static_source_paths(specs['vl']['prompt'], specs['vv']['prompt'], chain='v6')]
    if reused is not None:
        source_paths += [reused['result'], reused['response'], reused['prompt'], reused['scorer_input']]
    hashes = {str(Path(path).resolve()): io.sha(path) for path in source_paths}
    out.mkdir(parents=True)
    for branch in common.BRANCHES:
        shutil.copy2(paths[branch], out / f'{branch}_review_input.json')
    save(out / 'source_hashes.json', hashes)
    state = dict(protocol=common.SCORING_PROTOCOL_V6, chain='v6', status='running', model=model, reasoning=reasoning,
                 source_reviews={branch: str(paths[branch]) for branch in common.BRANCHES}, started=time.time(),
                 unit_counts={branch: len(reviews[branch]['units']) for branch in common.BRANCHES},
                 vl_scoring_from=str(reused_source) if vl_scoring_from is not None else None)
    save(out / 'run.json', state)

    def score_branch(branch):
        units = scored_units_v6(reviews[branch]['units'])
        if vl_scoring_from is not None and branch == 'vl' and (reused is None) != (not units):
            raise ValueError(f'{reused_source}: its V-L call does not match the V-L units to score')
        if not units:
            return {}, [], None
        spec = specs[branch]
        payload = scorer_input_v6(branch, reviews[branch])
        save(out / f'scorer_input_{branch}.json', payload)
        prompt_path = common.write_rendered_prompt(spec['prompt'], out / f'prompt_rendered_{branch}.txt',
                                                   chain_row['config'])
        if branch == 'vl' and reused is not None:
            if (Path(prompt_path).read_bytes() != reused['prompt'].read_bytes()
                    or (out / 'scorer_input_vl.json').read_bytes() != reused['scorer_input'].read_bytes()):
                raise ValueError(f'{reused_source}: its V-L prompt or scorer input differs from this run')
            response = common.read(reused['response'])
            errors = repair_loop.schema_errors(response, common.read(spec['schema']))
            if not errors:
                errors, assessments = assessment_errors_v6(response, units, base)
            if errors:
                raise ValueError(f'{reused["response"]}: reused V-L severities are invalid: {errors}')
            return assessments, [], None
        assessments, _, usage, repair = repair_loop.call_with_repair(
            out / f'call_{branch}', payload, [], timeout, prompt_path=prompt_path, schema=common.read(spec['schema']),
            model=model, reasoning=reasoning, stage=f'{branch.upper()} scoring', repair_prompt=common.REPAIR_PROMPT,
            collect_errors=lambda candidate: assessment_errors_v6(candidate, units, base))
        return assessments, usage, repair

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {branch: pool.submit(score_branch, branch) for branch in common.BRANCHES}
            outcomes = {branch: future.result() for branch, future in futures.items()}
        units = reviews['vl']['units'] + reviews['vv']['units']
        assessments = {**outcomes['vl'][0], **outcomes['vv'][0]}
        entities = reviews['vl'].get('entities', []) + reviews['vv'].get('entities', [])
        scores, statistics, ledger, unit_counts = materialize_v6(units, assessments, entities, cfg, shots)
        if any(io.sha(path) != digest for path, digest in hashes.items()):
            raise ValueError('A reviewed input changed during scoring')
        usage = outcomes['vl'][1] + outcomes['vv'][1]
        calls = {branch: (len(outcomes[branch][2]['rounds']) if outcomes[branch][2] else 0) for branch in common.BRANCHES}
        result = dict(
            protocol=common.SCORING_PROTOCOL_V6, chain='v6', status='success', scores=scores,
            consistency_issue_statistics=statistics, counts=unit_counts, unit_scores=ledger,
            scoring_rule=dict(
                rubric_version=cfg['scoring']['rubric_version'], base_deductions={k: int(v) for k, v in base.items()},
                reviewer_confidence_factors={k: float(v) for k, v in factors.items()},
                uncertain_factor=float(uncertain_factor(cfg)),
                issue_rule='each confirmed unit deducts D = base(severity) x factor(verifier confidence) and each '
                           'uncertain unit D = base(severity) x uncertain_factor (severity rated as if the problem '
                           'were real), each on its own; no duplicate links, event groups or maximum (duplicates are '
                           'merged in verification); rejected units get no severity call and deduct nothing',
                aggregation='per_shot_exp',
                shots=shots,
                bucket_rule='100 * exp(-sum(D) / (100 * shots)) over the confirmed and uncertain units of the '
                            'dimension, shots = number of shots of the case manifest, rounded half up to 2 decimals '
                            '(owner, 2026-11-09; results before used 100 * product(1 - D / 100))',
                v_v_rule='overall = mean of within_shot and cross_shot',
                uec_rule='uec = mean of v_l, v_v within_shot and v_v cross_shot',
                empty_bucket='a dimension with no confirmed or uncertain unit scores 100; that is not proof of a '
                             'consistent video, see the counts'),
            source_reviews={branch: str(paths[branch]) for branch in common.BRANCHES},
            source_review_sha256={branch: hashes[str(paths[branch])] for branch in common.BRANCHES},
            model=model, reasoning=reasoning, calls=calls,
            repair_rounds={branch: (outcomes[branch][2]['repair_rounds'] if outcomes[branch][2] else 0)
                           for branch in common.BRANCHES},
            usage=usage, token_cost=common.estimated_cost(usage),
            **(dict(reused_vl_scoring=dict(
                source=str(reused_source),
                source_result_sha256=hashes.get(str(reused['result'])) if reused else None,
                response=str(reused['response']) if reused else None,
                response_sha256=hashes.get(str(reused['response'])) if reused else None,
                source_repair_rounds=reused['repair_rounds'] if reused else 0,
                rule='V-L severities reused from the earlier scoring of the byte-identical V-L review, rendered '
                     'prompt and scorer input (no V-L call here; its usage is counted in the earlier run, not in '
                     'usage above)')) if vl_scoring_from is not None else {}),
            limitation='Scores summarize confirmed verified issues and, at a reduced factor, uncertain ones; '
                       'severities come from text-only calls; entity labels come from the entity ledger and are not '
                       'checked against the text; no human calibration.')
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


def run(vl_review_path, vv_review_path, out, timeout=1800, model=common.MODEL, reasoning=common.REASONING,
        chain=common.DEFAULT_CHAIN, vl_scoring_from=None):
    """Scoring v6 for chain v6 (default), scoring v5 for chain v5."""
    common.chain_spec(chain)
    if chain == 'v6':
        return run_v6(vl_review_path, vv_review_path, out, timeout, model, reasoning, vl_scoring_from)
    if vl_scoring_from is not None:
        raise ValueError('--vl-scoring-from needs chain v6')
    return run_v5(vl_review_path, vv_review_path, out, timeout, model, reasoning)


def run_v5(vl_review_path, vv_review_path, out, timeout=1800, model=common.MODEL, reasoning=common.REASONING):
    """Scoring v5 (chain v5)."""
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
                uec_rule='uec = mean of v_l, v_v within_shot and v_v cross_shot',
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
    parser.add_argument('--chain', choices=sorted(common.CHAINS), default=common.DEFAULT_CHAIN,
                        help='v6 (default): scoring v6, no duplicate links, ledger labels; v5: scoring v5')
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--model', default=common.MODEL, choices=[common.MODEL])
    parser.add_argument('--reasoning', default=common.REASONING, choices=[common.REASONING])
    parser.add_argument('--vl-scoring-from', type=Path,
                        help='Chain v6: an earlier successful scoring folder of the same V-L review; its V-L '
                             'severities are reused and only the V-V call runs (plug-in version scored on top of the '
                             'base version, owner 2026-11-11)')
    args = parser.parse_args()
    run(args.vl_review, args.vv_review, args.output, args.timeout, args.model, args.reasoning, args.chain,
        args.vl_scoring_from)


if __name__ == '__main__':
    main()
