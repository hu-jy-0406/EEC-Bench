#!/usr/bin/env python3
"""V-L detection format "answers": one answer per contract requirement (owner direction, 2026-11-04).

Default V-L format of chain v6 since 2026-11-05 (owner); "checks" stays selectable.  The V-L review of an
answers-format detection has no rewrite call: the verdict call judges the candidates directly.

The V-L agent receives the requirements derived from the contract (the items of
the contract-checking template, in template order) and answers each one in a
schema built for this call: "answers" has one required property per
requirement ID, so no requirement can be skipped and an empty answer is not
possible.  An answer holds observed (what the frames show on this point,
written first), the verdict and, only when violated, its problem: what the
frames show instead and the frames that show it.  A description or camera
requirement may hold one problem per failed attribute, each naming the
violated words.  The runner turns every problem into one candidate issue, so
the requirement-to-issue mapping follows from the answer itself; the same
failed attribute of an entity description (same violated words) in several
shots becomes one issue with one occurrence per shot, as in the "checks"
format.  Candidate records and the template are the same as in that format,
so review v7 and scoring v6 are unchanged.

Format "answers_no_contract" (owner direction, 2026-11-04) is the same call
without INPUT.contract_json: the requirement list and the entity table already
hold everything that is checked.  It has its own prompt (the "answers" prompt
without the contract input) and protocol name.
"""
import vl_vv_branch_common as common

_PROTOCOLS = common.CHAINS['v6']['discovery_variants']['vl']
# format -> protocol, prompt template and whether the call receives contract_json.
VARIANTS = {
    'answers': dict(protocol=_PROTOCOLS[0], prompt=common.ROOT / f'prompts/{_PROTOCOLS[0]}.txt', contract=True),
    'answers_no_contract': dict(protocol=_PROTOCOLS[1], prompt=common.ROOT / f'prompts/{_PROTOCOLS[1]}.txt',
                                contract=False),
}
PROTOCOL = VARIANTS['answers']['protocol']
PROMPT = VARIANTS['answers']['prompt']
FORMATS = ('checks', *VARIANTS)
# Default V-L detection format per chain (owner, 2026-11-05: answers for chain v6); chain v5 has only checks.
DEFAULT_FORMATS = {'v6': 'answers', 'v5': 'checks'}


def default_format(chain):
    return DEFAULT_FORMATS[chain]
# Requirements that state several attributes; each failed attribute is its own problem.
MULTI_KINDS = ('description', 'camera_view', 'camera_movement')
OK_VERDICTS = ('satisfied', 'not_verifiable')
CONFIDENCE = ('high', 'medium', 'low')


# --------------------------------------------------------------------------
# Requirements and payload.
# --------------------------------------------------------------------------

def requirement_kind(row, item):
    if row['kind'] == 'cross_shot':
        return 'cross_shot'
    if item['kind'] == 'entity_description':
        return 'description'
    if item['kind'] == 'camera':
        return 'camera_view' if item['item_id'].endswith('-cam-view') else 'camera_movement'
    if item['kind'] in ('style', 'transition'):
        return 'style' if item['kind'] == 'style' else 'cut'
    if item.get('dimension') == 'presence':
        return 'absent' if item.get('predicate') == 'absent' else 'presence'
    return item['dimension']


def requirements(template):
    """The requirements to answer, one per template item, in template order, except that an entity's presence or
    absent requirement comes first in its shot, so the agent decides whether the entity is there before it judges
    the entity's other requirements (a missing entity leaves them not_verifiable)."""
    rows = []
    for row in template:
        listed = [item for item in row['items'] if item.get('dimension') == 'presence' and row['kind'] == 'entity']
        for item in listed + [item for item in row['items'] if item not in listed]:
            entry = dict(requirement_id=item['item_id'], kind=requirement_kind(row, item), shot_id=row['shot_id'])
            if row['kind'] == 'cross_shot':
                entry.update(shot_ids=list(row['shot_ids']), dimension=item['dimension'])
            if row['kind'] == 'transition':
                entry['from_shot'] = row['from_shot']
            entry['entities'] = [row['entity_label']] if row['kind'] == 'entity' else list(item.get('entity_labels') or [])
            if 'text' in item:
                entry['text'] = item['text']
            else:
                entry.update(predicate=item.get('predicate'), expected=item['expected'], quantifier=item['quantifier'],
                             coordinate_frame=item.get('coordinate_frame'))
            rows.append(entry)
    ids = [row['requirement_id'] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Requirement IDs repeat; the answers format needs a template with requirement IDs')
    return rows


def entity_table(contract, ledger, reqs):
    """Contract entities the requirements name: name, episode-wide description (stated once here, not in every
    shot's description requirement) and detector-ledger IDs."""
    ledger_ids = common.ledger_ids_by_label(ledger)
    labels = dict.fromkeys(label for entry in reqs for label in entry['entities'])
    described = {entry['entities'][0]: entry['text'] for entry in reqs if entry['kind'] == 'description'}
    names = contract['entity_descriptions']
    table = {}
    for label in labels:
        row = dict(name=(names.get(label) or {}).get('name'))
        if label in described:
            row['description'] = described[label]
        table[label] = dict(row, ledger_entity_ids=list(ledger_ids.get(label, [])))
    return table


def model_requirement(entry):
    """The requirement as the agent receives it, without what its kind implies: a description refers to the entity's
    description in INPUT.entities, presence and absent need no wording, and empty fields are left out."""
    row = {key: entry[key] for key in ('requirement_id', 'kind', 'shot_id', 'shot_ids', 'dimension', 'from_shot')
           if key in entry}
    if entry['entities']:
        row['entities'] = list(entry['entities'])
    if entry['kind'] in ('description', 'presence', 'absent'):
        return row
    if 'text' in entry:
        return dict(row, text=entry['text'])
    row.update(expected=entry['expected'], quantifier=entry['quantifier'])
    if entry.get('predicate'):
        row['predicate'] = entry['predicate']
    if entry.get('coordinate_frame') not in (None, 'none'):
        row['coordinate_frame'] = entry['coordinate_frame']
    return row


def payload(base, contract, ledger, reqs, fmt='answers'):
    base = dict(base, protocol=VARIANTS[fmt]['protocol'])
    if not VARIANTS[fmt]['contract']:
        base.pop('contract_json', None)
    base['entities'] = entity_table(contract, ledger, reqs)
    base['requirements'] = [model_requirement(entry) for entry in reqs]
    base['requirement_count'] = len(reqs)
    base['input_notes'] = [
        'detector_ledger is frozen upstream reference information, not an inconsistency verdict.',
        f'requirements has {len(reqs)} entries; "answers" has exactly one answer per requirement_id, in order.',
        'Every listed image is an original keyframe; index follows the attachment order.']
    return base


def requirement_text(entry):
    return entry['text'] if 'text' in entry else entry['expected']


def requirement_shots(entry):
    """Shots whose frames may show a failure of the requirement."""
    if entry['kind'] == 'cross_shot':
        return set(entry['shot_ids'])
    return {entry['shot_id'], entry['from_shot']} if entry['kind'] == 'cut' else {entry['shot_id']}


# --------------------------------------------------------------------------
# Per-call output schema.
# --------------------------------------------------------------------------

def _object(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


def _answer(ok_verdicts, violated):
    text = dict(type='string')
    return dict(anyOf=[_object(dict(observed=text, verdict=dict(type='string', enum=list(ok_verdicts)))),
                       _object(dict(observed=text, verdict=dict(type='string', enum=['violated']), **violated))])


def answer_definition(kind):
    if kind == 'description':
        return 'answer_description'
    return {'camera_view': 'answer_words', 'camera_movement': 'answer_words', 'cut': 'answer_cut'}.get(kind, 'answer')


def schema(reqs, cfg, fmt='answers'):
    """Strict output schema of one call: one required answer per requirement ID, in order."""
    text = dict(type='string')
    refs = dict(type='array', items={'$ref': '#/$defs/frame_ref'})
    subcategory = dict(type='string', enum=list(cfg['v_l_subcategories']))
    confidence = dict(type='string', enum=list(CONFIDENCE))
    problem = dict(shown=text, frame_refs=refs, subcategory=subcategory, confidence=confidence)
    words = dict(type='array', items={'$ref': '#/$defs/problem_words'})
    defs = dict(
        frame_ref=_object(dict(shot_id=text, frame_id=dict(type='integer'))),
        problem=_object(problem),
        problem_words=_object(dict(violated_words=text, **problem)),
        problem_cut=_object(dict(shown=text, frame_refs=refs, confidence=confidence)),
        answer=_answer(OK_VERDICTS, dict(problem={'$ref': '#/$defs/problem'})),
        answer_cut=_answer(OK_VERDICTS, dict(problem={'$ref': '#/$defs/problem_cut'})),
        answer_words=_answer(OK_VERDICTS, dict(problems=words)),
        answer_description=_answer(OK_VERDICTS + ('not_applicable',), dict(problems=words)))
    answers = _object({entry['requirement_id']: {'$ref': f'#/$defs/{answer_definition(entry["kind"])}'}
                       for entry in reqs})
    root = _object(dict(protocol=dict(type='string', enum=[VARIANTS[fmt]['protocol']]), answers=answers))
    root['$defs'] = defs
    return root


def problems_of(answer):
    if answer['verdict'] != 'violated':
        return []
    return list(answer['problems']) if 'problems' in answer else [answer['problem']]


# --------------------------------------------------------------------------
# Validation.
# --------------------------------------------------------------------------

def entity_free_requirements(reqs, ledger):
    """IDs of the requirements whose candidates would name no ledger entity (camera, style, cut, entity-free rows)."""
    ids = common.ledger_ids_by_label(ledger)
    return {entry['requirement_id'] for entry in reqs if not any(ids.get(label) for label in entry['entities'])}


def errors(result, reqs, template, manifest, seen_by_detector, challenged=None, entity_free=frozenset(),
           optional_subcategories=None):
    """EVERY semantic problem of a schema-valid answers result.

    challenged: a set kept across repair rounds.  Requirements of an entity
    answered not_verifiable although the detector ledger shows that entity in
    two or more frames of the shot are sent back once to be re-inspected; after
    that the agent's judgment stands (the ledger is reference information).

    optional_subcategories (with entity_free, from entity_free_requirements):
    review v7's call-1 gate that a subcategory concerning an entity needs one,
    applied in detection because answers-format candidates skip call 1
    (2026-11-05): a problem of a requirement that names no entity takes one of
    these subcategories.
    """
    errs, answers = [], result['answers']
    missing = [entry['requirement_id'] for entry in reqs if entry['requirement_id'] not in answers]
    if missing:
        errs.append(f'answers is missing {len(missing)} requirements: {missing}; answer every requirement_id')
    for entry in reqs:
        rid = entry['requirement_id']
        answer = answers.get(rid)
        if answer is None or answer['verdict'] != 'violated':
            continue
        where, problems = f'answers {rid}', problems_of(answer)
        if not problems:
            errs.append(f'{where}: violated, but problems is empty; give one problem per failed attribute')
        words = set()
        for index, problem in enumerate(problems):
            p_where = f'{where} problems[{index}]' if 'problems' in answer else f'{where} problem'
            if 'violated_words' in problem:
                quote = problem['violated_words']
                if not common.quote_found(quote, [requirement_text(entry)]):
                    errs.append(f'{p_where}: violated_words {quote!r} are not a literal quote of this requirement\'s text; '
                                'copy the exact words that the frames contradict')
                elif common.norm(quote) in words:
                    errs.append(f'{p_where}: violated_words {quote!r} repeat another problem of {rid}; give one problem '
                                'per failed attribute')
                words.add(common.norm(quote))
            subcategory = problem.get('subcategory')
            if (optional_subcategories is not None and rid in entity_free and subcategory is not None
                    and subcategory not in optional_subcategories):
                errs.append(f'{p_where}: subcategory {subcategory} concerns an entity, but {rid} names no entity; use '
                            f'one of {list(optional_subcategories)}')
            refs = problem['frame_refs']
            errs += common.frame_ref_errors(refs, manifest, p_where, requirement_shots(entry))
            cited = {ref['shot_id'] for ref in refs}
            if not refs:
                errs.append(f'{p_where}: frame_refs is empty; cite the frames that show the failure')
            elif entry['kind'] == 'cut' and not {entry['from_shot'], entry['shot_id']} <= cited:
                errs.append(f'{p_where}: a violated cut cites the last frame of {entry["from_shot"]} and a frame of '
                            f'{entry["shot_id"]}')
            elif entry['kind'] == 'cross_shot' and set(entry['shot_ids']) - cited:
                errs.append(f'{p_where}: a violated cross-shot requirement cites a frame of every shot it names '
                            f'(missing {sorted(set(entry["shot_ids"]) - cited)})')
    kinds = {entry['requirement_id']: entry['kind'] for entry in reqs}
    for row in template:
        if row['kind'] != 'entity':
            continue
        items = [item['item_id'] for item in row['items'] if item['item_id'] in answers]
        presence = [rid for rid in items if kinds[rid] == 'presence']
        # Owner, 2026-11-05: each requirement an absence leaves unmet is reported (each counts); the
        # description applies only where the entity appears.
        if any(answers[rid]['verdict'] == 'violated' for rid in presence):
            where = f'answers {presence[0]}: {row["name"]!r} is absent from {row["shot_id"]} (presence violated)'
            unjudged = [rid for rid in items if kinds[rid] not in ('presence', 'absent', 'description')
                        and answers[rid]['verdict'] == 'not_verifiable']
            if unjudged:
                errs.append(f'{where}, so judge {unjudged} as they stand: violated if the requirement needs the entity '
                            'to be seen, satisfied if it holds without the entity (not not_verifiable)')
            described = [rid for rid in items if kinds[rid] == 'description' and answers[rid]['verdict'] == 'violated']
            if described:
                errs.append(f'{where}; its description applies only where the entity appears: answer {described} '
                            'not_verifiable')
        # As in the checks format, only an entity none of whose requirements in the shot could be judged is challenged.
        unverified = [rid for rid in items if kinds[rid] != 'absent']
        if not unverified or any(answers[rid]['verdict'] != 'not_verifiable' for rid in unverified):
            continue
        if challenged is not None and row['row_id'] not in challenged:
            detected = sorted({frame for gid in row['ledger_entity_ids']
                               for frame in seen_by_detector.get((gid, row['shot_id']), ())})
            if len(detected) >= 2:
                challenged.add(row['row_id'])
                errs.append(f'answers {unverified}: not_verifiable, but the detector located {row["name"]!r} in frames '
                            f'{detected} of {row["shot_id"]}; inspect those frames and judge these requirements (keep '
                            'not_verifiable only if the entity really cannot be identified there, and say why in observed)')
    return errs


# --------------------------------------------------------------------------
# Candidate records.
# --------------------------------------------------------------------------

def _statement(quote, shown):
    return f'要求“{quote}”，画面：{shown}'


def canonical(result, reqs, template, ledger):
    """Records v2 candidate issues and their entities: one issue per problem, in requirement order."""
    row_of = {item['item_id']: row['row_id'] for row in template for item in row['items']}
    ledger_ids = common.ledger_ids_by_label(ledger)
    issues, grouped = [], {}
    rank = {value: index for index, value in enumerate(CONFIDENCE)}
    for entry in reqs:
        rid = entry['requirement_id']
        answer = result['answers'][rid]
        for problem in problems_of(answer):
            quote = problem.get('violated_words') or requirement_text(entry)
            subcategory = 'shot_structure' if entry['kind'] == 'cut' else problem['subcategory']
            keys = [gid for label in entry['entities'] for gid in ledger_ids.get(label, [])]
            shots = list(entry['shot_ids']) if entry['kind'] == 'cross_shot' else [entry['shot_id']]
            occurrences = []
            for sid in shots:
                frames = [dict(shot_id=ref['shot_id'], frame_id=ref['frame_id']) for ref in problem['frame_refs']
                          if entry['kind'] != 'cross_shot' or ref['shot_id'] == sid]
                occurrences.append(dict(shot_id=sid, row_ids=[row_of[rid]], frame_refs=frames,
                                        observed=answer['observed'] or problem['shown'],
                                        mismatch=_statement(quote, problem['shown'])))
            evidence = [dict(shot_id=ref['shot_id'], frame_id=ref['frame_id'], entity_keys=list(keys),
                             observation=problem['shown']) for ref in problem['frame_refs']]
            group = (entry['entities'][0], common.norm(quote), subcategory) if entry['kind'] == 'description' else None
            if group in grouped:
                issue = grouped[group]
                issue['shot_ids'] += [occ['shot_id'] for occ in occurrences]
                issue['key_evidence'] += evidence
                issue['v_l_detail']['occurrences'] += occurrences
                issue['v_l_detail']['requirement_ids'].append(rid)
                issue['v_l_detail']['template_row_ids'] = list(dict.fromkeys(
                    issue['v_l_detail']['template_row_ids'] + [row_of[rid]]))
                if rank[problem['confidence']] < rank[issue['confidence']]:
                    issue['confidence'] = problem['confidence']
                issue['_shown'].append((entry['shot_id'], problem['shown']))
                continue
            source = 'shot_transitions' if entry['kind'] == 'cut' else 'contract'
            issue = dict(issue_id=None, branch='v_l', scope='v_l', subcategory=subcategory, description='',
                         shot_ids=[occ['shot_id'] for occ in occurrences],
                         entity_refs=[dict(entity_key=key, role='subject') for key in keys],
                         key_evidence=evidence, confidence=problem['confidence'],
                         v_l_detail=dict(requirement_quotes=[dict(source=source, shot_id=None if entry['kind'] in (
                                             'description', 'cross_shot') else entry['shot_id'], quote=quote)],
                                         expected=requirement_text(entry), occurrences=occurrences,
                                         template_row_ids=[row_of[rid]], requirement_ids=[rid]),
                         v_v_detail=None, _quote=quote, _shown=[(entry['shot_id'], problem['shown'])])
            issues.append(issue)
            if group is not None:
                grouped[group] = issue
    for index, issue in enumerate(issues, 1):
        issue['issue_id'] = f'L{index}'
        quote, shown = issue.pop('_quote'), issue.pop('_shown')
        if len(shown) == 1:
            issue['description'] = f'{"、".join(issue["shot_ids"])}：{_statement(quote, shown[0][1])}'
        else:
            issue['description'] = f'要求“{quote}”，' + '；'.join(f'{sid}画面：{text}' for sid, text in shown)
    ledger_index = common.ledger_rows(ledger)
    used = [ref['entity_key'] for issue in issues for ref in issue['entity_refs']]
    entities = [common.ledger_entity_v2(ledger_index[key]) for key in dict.fromkeys(used) if key in ledger_index]
    return issues, entities


def counts(result, issues):
    verdicts = {}
    for answer in result['answers'].values():
        verdicts[answer['verdict']] = verdicts.get(answer['verdict'], 0) + 1
    return dict(issues=len(issues), requirements=len(result['answers']), verdicts=verdicts,
                problems=sum(len(problems_of(answer)) for answer in result['answers'].values()),
                empty_observed=sum(not answer['observed'].strip() for answer in result['answers'].values()))
