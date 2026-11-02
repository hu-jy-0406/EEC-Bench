#!/usr/bin/env python3
"""Shared pieces of the branch-separated V-L / V-V pipeline.

Chain (pipeline --discovery-protocol v5, review v6, scoring v5):
  detection registry -> V-L detection  -> V-L review  -+-> episode scoring (V-L call + V-V call, then Python)
                     -> V-V detection  -> V-V review  -+
Each box is its own model call with its own prompt, schema and validator.
This module holds what every stage shares: the config, prompt rendering
(static placeholders), literal-quote verification, the contract-checking
template, the entity index and the cost estimate.
"""
import copy
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / 'configs/vl-vv-branch-v1.json'
DEFINITIONS_PATH = ROOT / 'prompts/vl_vv_branch_definitions_v1.txt'
REPAIR_PROMPT = ROOT / 'prompts/vl_vv_validation_repair_v2.txt'
RECORDS_SCHEMA = ROOT / 'schemas/vl-vv-branch-records-v1.schema.json'
SCHEMA_BUILDER = ROOT / 'scripts/build_vl_vv_branch_schemas.py'
MODEL = 'gpt-6-luna'
REASONING = 'low'

BRANCHES = ('vl', 'vv')
LABEL = {'vl': 'v_l', 'vv': 'v_v'}
DISCOVERY = {
    'vl': dict(protocol='vl_vv_issue_discovery_v5_vl', prompt=ROOT / 'prompts/vl_vv_issue_discovery_v5_vl.txt',
               schema=ROOT / 'schemas/vl-vv-issue-discovery-v5-vl.schema.json'),
    'vv': dict(protocol='vl_vv_issue_discovery_v5_vv', prompt=ROOT / 'prompts/vl_vv_issue_discovery_v5_vv.txt',
               schema=ROOT / 'schemas/vl-vv-issue-discovery-v5-vv.schema.json'),
}
REVIEW = {
    'vl': dict(protocol='vl_vv_issue_review_v6_vl', prompt=ROOT / 'prompts/vl_vv_issue_review_v6_vl.txt',
               schema=ROOT / 'schemas/vl-vv-issue-review-v6-vl.schema.json'),
    'vv': dict(protocol='vl_vv_issue_review_v6_vv', prompt=ROOT / 'prompts/vl_vv_issue_review_v6_vv.txt',
               schema=ROOT / 'schemas/vl-vv-issue-review-v6-vv.schema.json'),
}
SCORING = {
    'vl': dict(protocol='vl_vv_episode_scoring_v5_vl', prompt=ROOT / 'prompts/vl_vv_episode_scoring_v5_vl.txt',
               schema=ROOT / 'schemas/vl-vv-episode-scoring-v5-vl.schema.json'),
    'vv': dict(protocol='vl_vv_episode_scoring_v5_vv', prompt=ROOT / 'prompts/vl_vv_episode_scoring_v5_vv.txt',
               schema=ROOT / 'schemas/vl-vv-episode-scoring-v5-vv.schema.json'),
}
SCORING_PROTOCOL = 'vl_vv_episode_scoring_v5'
PLACEHOLDER = re.compile(r'\{\{([A-Z_]+)\}\}')


def read(path):
    return json.loads(Path(path).read_text())


@lru_cache(maxsize=1)
def config():
    return read(CONFIG_PATH)


def vv_subcategories(scope=None):
    groups = config()['v_v_subcategories']
    if scope is not None:
        return tuple(groups[scope])
    return tuple(groups['within_shot']) + tuple(groups['cross_shot'])


def checklist_items():
    return tuple(row['item'] for row in config()['vv_checklist'])


def allowed_bases(label, verdict):
    return tuple(config()['review']['decision_basis'][label][verdict])


# --------------------------------------------------------------------------
# Prompt rendering: static placeholders are filled from repository files.
# Dynamic, episode-specific inputs are never rendered into the prompt text;
# they travel in the INPUT JSON that the transport appends to the prompt.
# --------------------------------------------------------------------------

def _definition_lines(mapping, indent='    '):
    return '\n'.join(f'{indent}{code}: {text}' for code, text in mapping.items())


def _checklist_text():
    lines = []
    for row in config()['vv_checklist']:
        lines.append(f'- {row["item"]} [{row["scope"]}] {row["title"]}: {row["check"]}')
    return '\n'.join(lines)


def placeholder_values():
    cfg = config()
    values = {
        'VL_SUBCATEGORIES': _definition_lines(cfg['v_l_subcategories']),
        'VV_WITHIN_SUBCATEGORIES': _definition_lines(cfg['v_v_subcategories']['within_shot']),
        'VV_CROSS_SUBCATEGORIES': _definition_lines(cfg['v_v_subcategories']['cross_shot']),
        'VV_CHECKLIST': _checklist_text(),
        'VV_NORMAL_CAUSES': _definition_lines(cfg['normal_change_causes'], indent='- '),
    }
    values['VL_VV_DEFINITIONS'] = _fill(DEFINITIONS_PATH.read_text(), values).rstrip('\n')
    return values


def _fill(text, values):
    def replace(match):
        name = match.group(1)
        if name not in values:
            raise ValueError(f'Unknown prompt placeholder {{{{{name}}}}}')
        return values[name]
    return PLACEHOLDER.sub(replace, text)


def render_prompt(template_path):
    text = _fill(Path(template_path).read_text(), placeholder_values())
    if '{{' in text or '}}' in text:
        raise ValueError(f'Unrendered placeholder left in {template_path}')
    return text


def write_rendered_prompt(template_path, target):
    """Render a prompt template into the stage output folder; the transport sends that file."""
    target = Path(target)
    target.write_text(render_prompt(template_path))
    return target


def static_source_paths(*templates):
    """Repository files whose content defines the rendered prompts and schemas."""
    return [CONFIG_PATH, DEFINITIONS_PATH, REPAIR_PROMPT, RECORDS_SCHEMA, SCHEMA_BUILDER,
            Path(__file__).resolve(), *map(Path, templates)]


# --------------------------------------------------------------------------
# Literal quote verification.
# --------------------------------------------------------------------------

_QUOTES = str.maketrans({'‘': "'", '’': "'", '‚': "'", '‛': "'", '′': "'",
                         '“': '"', '”': '"', '„': '"', '‟': '"', '″': '"',
                         '‐': '-', '‑': '-', '‒': '-', '–': '-', '—': '-',
                         '―': '-', '−': '-'})


def norm(text):
    text = unicodedata.normalize('NFKC', str(text)).translate(_QUOTES).casefold()
    return re.sub(r'\s+', ' ', text).strip()


def _fragments(quote):
    parts = re.split(r'\.\.\.|…', norm(quote))
    return [part.strip(' "\'.,;:!?()[]') for part in parts if part.strip(' "\'.,;:!?()[]')]


def quote_found(quote, texts):
    """True when every fragment of the quote (split at an ellipsis) occurs in one of the texts."""
    fragments = _fragments(quote)
    if not fragments:
        return False
    haystacks = [norm(text) for text in texts if isinstance(text, str)]
    return all(any(fragment in hay for hay in haystacks) for fragment in fragments)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def transition_text(row):
    return f'{row["from_shot"]}->{row["to_shot"]}: {row["required"]}'


def text_sources(contract, transitions):
    """Source texts by quote source.  shot_prompt is keyed by shot_id."""
    prompt = contract.get('prompt') or {}
    shots = {row.get('shot_id'): row.get('text', '') for row in prompt.get('shots', []) if isinstance(row, dict)}
    contract_texts = list(_strings({key: contract.get(key) for key in
                                    ('entity_descriptions', 'entity_schedule', 'claims', 'prompt')}))
    return dict(global_prompt=[prompt.get('global_prompt', '')], shot_prompt=shots, contract=contract_texts,
                shot_transitions=[transition_text(row) for row in transitions])


def quote_errors(quote, sources, where):
    """Problems of one {source, shot_id, quote} record against the source texts."""
    source, shot_id, text = quote['source'], quote.get('shot_id'), quote['quote']
    if source == 'shot_prompt':
        if shot_id is not None and shot_id not in sources['shot_prompt']:
            return [f'{where}: quote names unknown shot_id {shot_id!r}']
        texts = [sources['shot_prompt'][shot_id]] if shot_id is not None else list(sources['shot_prompt'].values())
    else:
        texts = sources[source]
    if quote_found(text, texts):
        return []
    elsewhere = [name for name in ('global_prompt', 'shot_prompt', 'contract', 'shot_transitions')
                 if name != source and quote_found(text, sources[name] if name != 'shot_prompt'
                                                   else list(sources['shot_prompt'].values()))]
    hint = (f'; the words occur in {elsewhere}: set source accordingly' if elsewhere
            else '; copy the exact words of the source text (an ellipsis "..." may join two exact fragments)')
    label = f'{source}' + (f' {shot_id}' if shot_id else '')
    return [f'{where}: quote {text!r} is not a literal quote of {label}{hint}']


def any_text_found(text, sources):
    pools = [sources['global_prompt'], list(sources['shot_prompt'].values()), sources['contract']]
    return any(quote_found(text, pool) for pool in pools)


# --------------------------------------------------------------------------
# Manifest helpers.
# --------------------------------------------------------------------------

def shot_ids(manifest):
    return [shot['shot_id'] for shot in manifest['shots']]


def frame_pairs(manifest):
    return {(shot['shot_id'], frame['frame_id']) for shot in manifest['shots'] for frame in shot['frames']}


def frame_ref_errors(refs, manifest, where, allowed_shots=None):
    pairs = frame_pairs(manifest)
    errors = []
    for index, ref in enumerate(refs):
        pair = (ref['shot_id'], ref['frame_id'])
        if pair not in pairs:
            errors.append(f'{where}: unknown frame {pair} (frame_refs[{index}]; use a shot-local frame_id of that shot)')
        elif allowed_shots is not None and ref['shot_id'] not in allowed_shots:
            errors.append(f'{where}: frame {pair} lies outside the allowed shots {sorted(allowed_shots)}')
    return errors


def image_order(images):
    return [dict(index=index, shot_id=row['shot_id'], frame_id=row['frame_id'], timestamp_sec=row['timestamp_sec'])
            for index, row in enumerate(images)]


# --------------------------------------------------------------------------
# Contract-checking template (V-L branch).
# --------------------------------------------------------------------------

def schedule_labels_by_shot(contract, manifest):
    """Contract entity labels scheduled in each manifest shot, in entity_descriptions order."""
    descriptions = contract.get('entity_descriptions') or {}
    label_by_name = {}
    for label, row in descriptions.items():
        if isinstance(row, dict) and isinstance(row.get('name'), str):
            label_by_name.setdefault(row['name'], label)
    shot_by_key = {row.get('schedule_key'): row.get('shot_id')
                   for row in (contract.get('prompt') or {}).get('shots', []) if isinstance(row, dict)}
    order = {label: index for index, label in enumerate(descriptions)}
    result = {sid: [] for sid in shot_ids(manifest)}
    for key, entry in (contract.get('entity_schedule') or {}).items():
        sid = shot_by_key.get(key)
        if sid not in result or not isinstance(entry, dict):
            continue
        for field in ('characters', 'places', 'objects'):
            for name in entry.get(field) or []:
                label = label_by_name.get(name)
                if label and label not in result[sid]:
                    result[sid].append(label)
    for sid in result:
        result[sid].sort(key=lambda label: order[label])
    return result


def label_kinds(contract):
    """'character' / 'place' / 'object' for each label, from the schedule field it appears in."""
    descriptions = contract.get('entity_descriptions') or {}
    label_by_name = {row['name']: label for label, row in descriptions.items()
                     if isinstance(row, dict) and isinstance(row.get('name'), str)}
    kinds = {}
    for entry in (contract.get('entity_schedule') or {}).values():
        if not isinstance(entry, dict):
            continue
        for field, kind in (('characters', 'character'), ('places', 'place'), ('objects', 'object')):
            for name in entry.get(field) or []:
                if name in label_by_name:
                    kinds.setdefault(label_by_name[name], kind)
    return kinds


def ledger_ids_by_label(ledger):
    result = {}
    for row in ledger.get('prompt_bound', []):
        label = row.get('prompt_entity_id')
        if label:
            result.setdefault(label, []).append(row['global_entity_id'])
    return result


def contract_template(contract, ledger, manifest, transitions):
    """Clause groups to check, per manifest shot (contract-checking template v2).

    One row per entity of the shot (its episode-wide description when the
    entity is scheduled there, plus the shot's single-entity claims about it),
    one relations row with the shot's multi-entity claims, one shot_text
    catch-all row, and one transition row per boundary (attached to the later
    shot).  Each row lists its requirement items; the model reports which items
    are violated.  Grouping by entity keeps the template short enough that the
    agent inspects the frames instead of ticking a long form.
    """
    shots = shot_ids(manifest)
    descriptions = contract.get('entity_descriptions') or {}
    prompt_shots = {row.get('shot_id'): row for row in (contract.get('prompt') or {}).get('shots', [])
                    if isinstance(row, dict)}
    ledger_ids = ledger_ids_by_label(ledger)
    scheduled = schedule_labels_by_shot(contract, manifest)
    claims = [claim for claim in contract.get('claims') or [] if isinstance(claim, dict) and claim.get('claim_id')]
    transitions_into = {row['to_shot']: row for row in transitions}
    order = {label: index for index, label in enumerate(descriptions)}
    rows = []

    def claim_item(claim, shot_claim_ids):
        return dict(item_id=claim['claim_id'], kind='claim', dimension=claim.get('dimension'),
                    predicate=claim.get('predicate'), expected=claim.get('expected'),
                    quantifier=claim.get('quantifier'), entity_labels=list(claim.get('entity_ids') or []),
                    depends_on=[dep for dep in claim.get('depends_on') or [] if dep in shot_claim_ids],
                    quotes=[ev.get('quote') for ev in claim.get('evidence') or []
                            if isinstance(ev, dict) and ev.get('quote')])

    for sid in shots:
        shot_claims = [claim for claim in claims if sid in (claim.get('shot_ids') or [])]
        shot_claim_ids = {claim['claim_id'] for claim in shot_claims}
        single = [claim for claim in shot_claims if len(claim.get('entity_ids') or []) == 1]
        multi = [claim for claim in shot_claims if len(claim.get('entity_ids') or []) > 1]
        loose = [claim for claim in shot_claims if not claim.get('entity_ids')]
        labels = list(scheduled.get(sid, []))
        for claim in single:
            if claim['entity_ids'][0] not in labels:
                labels.append(claim['entity_ids'][0])
        labels.sort(key=lambda label: order.get(label, len(order)))
        for label in labels:
            items = []
            description = (descriptions.get(label) or {}).get('description')
            if label in scheduled.get(sid, []) and description:
                items.append(dict(item_id='description', kind='entity_description', text=description))
            items += [claim_item(claim, shot_claim_ids) for claim in single if claim['entity_ids'][0] == label]
            if not items:
                continue
            rows.append(dict(row_id=f'EN:{label}@{sid}', kind='entity', shot_id=sid, entity_label=label,
                             name=(descriptions.get(label) or {}).get('name'),
                             ledger_entity_ids=list(ledger_ids.get(label, [])), items=items))
        if multi:
            rows.append(dict(row_id=f'RL:{sid}', kind='relations', shot_id=sid,
                             items=[claim_item(claim, shot_claim_ids) for claim in multi]))
        rows.append(dict(row_id=f'SP:{sid}', kind='shot_text', shot_id=sid,
                         items=[dict(item_id='text', kind='shot_text',
                                     text=(prompt_shots.get(sid) or {}).get('text', ''))]
                         + [claim_item(claim, shot_claim_ids) for claim in loose],
                         note='Every other explicit requirement of this shot prompt, and of the global prompt where it '
                              'applies to this shot, not covered by the other rows of this shot.'))
        if sid in transitions_into:
            boundary = transitions_into[sid]
            rows.append(dict(row_id=f'TR:{boundary["from_shot"]}->{sid}', kind='transition', shot_id=sid,
                             from_shot=boundary['from_shot'], required=boundary['required'],
                             items=[dict(item_id='transition', kind='transition', text=transition_text(boundary))]))
    seen = set()
    for row in rows:
        if row['row_id'] in seen:
            raise ValueError(f'Duplicate contract template row {row["row_id"]}')
        seen.add(row['row_id'])
    return rows


def row_shots(row):
    """Shots whose frames may decide a template row."""
    return {row['shot_id'], row['from_shot']} if row['kind'] == 'transition' else {row['shot_id']}


# --------------------------------------------------------------------------
# Entities.
# --------------------------------------------------------------------------

def ledger_rows(ledger):
    return {row['global_entity_id']: row for part in ('prompt_bound', 'prompt_unbound') for row in ledger.get(part, [])}


def ledger_entity(row):
    return dict(entity_key=row['global_entity_id'], global_entity_id=row['global_entity_id'],
                source='detection_ledger', name=row.get('name') or row['global_entity_id'],
                description=row.get('short_description') or '', partition=row.get('partition'),
                prompt_entity_id=row.get('prompt_entity_id'), frame_refs=[], provenance=None, basis_type=None,
                contract_label=None, quote=None, part_of=None, note='')


def place_entity_ids(contract, ledger):
    """Ledger IDs of the contract's scheduled places (setting containers, not their elements)."""
    kinds = label_kinds(contract)
    return {gid for label, gids in ledger_ids_by_label(ledger).items() if kinds.get(label) == 'place' for gid in gids}


ELEMENT_SUBCATEGORIES = ('setting_background', 'background_drift')


def required_shot_characters(contract, ledger, manifest):
    """Prompt-bound characters scheduled in each shot that the ledger holds."""
    kinds = label_kinds(contract)
    ids = ledger_ids_by_label(ledger)
    scheduled = schedule_labels_by_shot(contract, manifest)
    return {sid: [gid for label in labels if kinds.get(label) == 'character' for gid in ids.get(label, [])]
            for sid, labels in scheduled.items()}


# --------------------------------------------------------------------------
# Records schema and usage.
# --------------------------------------------------------------------------

def records_errors(value):
    import jsonschema
    schema = read(RECORDS_SCHEMA)
    validator = jsonschema.validators.validator_for(schema)(schema)
    return [f'{"/".join(map(str, error.absolute_path)) or "<root>"}: {error.message}'
            for error in validator.iter_errors(value)]


def require_records(value, where):
    errors = records_errors(value)
    if errors:
        raise ValueError(f'{where} is not a valid branch record set: ' + '; '.join(errors[:10]))


def estimated_cost(usage):
    # GPT-6 Luna standard API prices, USD per million tokens; an estimate, not a bill.
    uncached = sum(max(0, int(row.get('input_tokens', 0)) - int(row.get('cached_input_tokens', 0))) for row in usage)
    cached = sum(int(row.get('cached_input_tokens', 0)) for row in usage)
    output = sum(int(row.get('output_tokens', 0)) for row in usage)
    return dict(uncached_input_tokens=uncached, cached_input_tokens=cached, output_tokens=output, api_calls=len(usage),
                estimated_usd=round(uncached / 1_000_000 * 0.10 + cached / 1_000_000 * 0.01 + output / 1_000_000 * 0.50, 9),
                pricing_basis='GPT-6 Luna standard API estimate: USD 0.10/M uncached input, 0.01/M cached input, '
                              '0.50/M output; cached input is a subset of input; estimate, not billed amount.')


def require_api(model, reasoning, stage):
    import os
    if os.environ.get('EECBENCH_CODEX_BACKEND') != 'api':
        raise RuntimeError(f'Run through EECBench/scripts/openai_api_env.sh; {stage} uses the configured API transport')
    if model != MODEL or os.environ.get('EECBENCH_API_MODEL', MODEL) != MODEL:
        raise RuntimeError(f'{stage} is pinned to {MODEL}')
    if reasoning != REASONING:
        raise RuntimeError(f'{stage} is pinned to reasoning={REASONING}')


def deep(value):
    return copy.deepcopy(value)
