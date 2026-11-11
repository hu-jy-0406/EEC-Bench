#!/usr/bin/env python3
"""Shared pieces of the branch-separated V-L / V-V pipeline.

Two chains share this module (CHAINS, keyed by the pipeline's discovery protocol):

- v6 (default since 2026-11-02): discovery v6 -> review v7 -> scoring v6, config v2.
  Review makes two calls per branch: the first keeps, splits or merges the
  candidates and rewrites them, the second gives the verdicts on the rewritten
  issues only.  V-L candidates of the answers formats (the default V-L format
  since 2026-11-05) skip the first call: each states one failed requirement, so
  the verdict call judges them directly.  Scoring has no duplicate links; issue
  entities take their specified / unspecified label from the entity ledger.
- v5 (2026-10-09, kept unchanged for ablations): discovery v5 -> review v6 ->
  scoring v5, config v1; one review call per branch, duplicate links in
  scoring, entity provenance registered by V-V detection.

  detection registry -> V-L detection  -> V-L review  -+-> episode scoring (V-L call + V-V call, then Python)
                     -> V-V detection  -> V-V review  -+
Each box is its own stage with its own prompt(s), schema(s) and validator.
This module holds what every stage shares: the configs, prompt rendering
(static placeholders), literal-quote verification, the contract-checking
template, the entity index and the cost estimate.  Helpers that read a config
default to config v1 (chain v5); chain v6 code passes config v2.
"""
import copy
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import episode_contract as contract_io

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / 'configs/vl-vv-branch-v1.json'          # chain v5
CONFIG_V2_PATH = ROOT / 'configs/vl-vv-branch-v2.json'       # chain v6
DEFINITIONS_PATH = ROOT / 'prompts/vl_vv_branch_definitions_v1.txt'
REPAIR_PROMPT = ROOT / 'prompts/vl_vv_validation_repair_v2.txt'
RECORDS_SCHEMA = ROOT / 'schemas/vl-vv-branch-records-v1.schema.json'
RECORDS_SCHEMA_V2 = ROOT / 'schemas/vl-vv-branch-records-v2.schema.json'
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

# Chain v6 (owner decisions Q7 and Q8, 2026-11-01/02; implemented 2026-11-02).
DISCOVERY_V6 = {
    'vl': dict(protocol='vl_vv_issue_discovery_v6_vl', prompt=ROOT / 'prompts/vl_vv_issue_discovery_v6_vl.txt',
               schema=ROOT / 'schemas/vl-vv-issue-discovery-v6-vl.schema.json'),
    'vv': dict(protocol='vl_vv_issue_discovery_v6_vv', prompt=ROOT / 'prompts/vl_vv_issue_discovery_v6_vv.txt',
               schema=ROOT / 'schemas/vl-vv-issue-discovery-v6-vv.schema.json'),
}
# Chain v6 V-V detection makes one call per checklist item (owner, 2026-11-09; default mode per_item; one_call is
# the single call for the whole checklist).  Every item call of a video sends the same prompt, input, schema and
# keyframes and names its item in a trailing message (checklist_item_message); the prompt text goes in a developer
# message, which GPT-6 Luna serves from the prompt cache (the keyframes are not cached).
DISCOVERY_V6_VV_ITEM = dict(protocol='vl_vv_issue_discovery_v6_vv_item',
                            prompt=ROOT / 'prompts/vl_vv_issue_discovery_v6_vv_item.txt',
                            schema=ROOT / 'schemas/vl-vv-issue-discovery-v6-vv-item.schema.json')
VV_DETECTION_MODES = ('per_item', 'one_call')
DEFAULT_VV_DETECTION_MODE = 'per_item'
OPEN_SWEEP_SCOPE = 'episode'


def _review_v7(branch):
    """Review v7: one stage per branch with two calls, rewrite (keep / split / merge) then verdict.

    V-L also has verdict_direct (owner, 2026-11-05): the verdict call alone, on the candidates of an answers-format
    detection (same protocol and schema, its own prompt).
    """
    verdict = dict(protocol=f'vl_vv_issue_review_v7_{branch}_verdict',
                   prompt=ROOT / f'prompts/vl_vv_issue_review_v7_{branch}_verdict.txt',
                   schema=ROOT / f'schemas/vl-vv-issue-review-v7-{branch}-verdict.schema.json')
    spec = dict(protocol=f'vl_vv_issue_review_v7_{branch}',
                rewrite=dict(protocol=f'vl_vv_issue_review_v7_{branch}_rewrite',
                             prompt=ROOT / f'prompts/vl_vv_issue_review_v7_{branch}_rewrite.txt',
                             schema=ROOT / f'schemas/vl-vv-issue-review-v7-{branch}-rewrite.schema.json'),
                verdict=verdict)
    if branch == 'vl':
        spec['verdict_direct'] = dict(verdict, prompt=ROOT / 'prompts/vl_vv_issue_review_v7_vl_verdict_direct.txt')
    return spec


REVIEW_V7 = {branch: _review_v7(branch) for branch in BRANCHES}
SCORING_V6 = {
    'vl': dict(protocol='vl_vv_episode_scoring_v6_vl', prompt=ROOT / 'prompts/vl_vv_episode_scoring_v6_vl.txt',
               schema=ROOT / 'schemas/vl-vv-episode-scoring-v6-vl.schema.json'),
    'vv': dict(protocol='vl_vv_episode_scoring_v6_vv', prompt=ROOT / 'prompts/vl_vv_episode_scoring_v6_vv.txt',
               schema=ROOT / 'schemas/vl-vv-episode-scoring-v6-vv.schema.json'),
}
SCORING_PROTOCOL_V6 = 'vl_vv_episode_scoring_v6'

# Keyed by the pipeline's discovery protocol.
CHAINS = {
    'v5': dict(config=CONFIG_PATH, records=RECORDS_SCHEMA, discovery=DISCOVERY, review=REVIEW, scoring=SCORING,
               review_protocol='v6', scoring_protocol=SCORING_PROTOCOL),
    'v6': dict(config=CONFIG_V2_PATH, records=RECORDS_SCHEMA_V2, discovery=DISCOVERY_V6, review=REVIEW_V7,
               scoring=SCORING_V6, review_protocol='v7', scoring_protocol=SCORING_PROTOCOL_V6,
               # V-L detection formats "answers" (default since 2026-11-05) and "answers_no_contract"
               # (vl_vv_requirement_answers.py): same candidate records; their V-L review skips the rewrite call.
               discovery_variants=dict(vl=('vl_vv_issue_discovery_v6_vl_answers',
                                           'vl_vv_issue_discovery_v6_vl_answers_no_contract'))),
}
DEFAULT_CHAIN = 'v6'
PLACEHOLDER = re.compile(r'\{\{([A-Z_]+)\}\}')


def direct_vl_review(detection_protocol, chain='v6'):
    """Whether a V-L detection result goes straight to the verdict call (answers formats of chain v6)."""
    return detection_protocol in chain_spec(chain).get('discovery_variants', {}).get('vl', ())


def chain_spec(chain):
    if chain not in CHAINS:
        raise ValueError(f'Unknown branch chain {chain!r} (known: {sorted(CHAINS)})')
    return CHAINS[chain]


def read(path):
    return json.loads(Path(path).read_text())


@lru_cache(maxsize=None)
def _config(path):
    return read(path)


def config(path=CONFIG_PATH):
    """A chain's config; the default is config v1 (chain v5)."""
    return _config(str(Path(path)))


def chain_config(chain):
    return config(chain_spec(chain)['config'])


def vv_subcategories(scope=None, cfg=None):
    groups = (cfg or config())['v_v_subcategories']
    if scope is not None:
        return tuple(groups[scope])
    return tuple(dict.fromkeys(tuple(groups['within_shot']) + tuple(groups['cross_shot'])))


def checklist_items(cfg=None):
    return tuple(row['item'] for row in (cfg or config())['vv_checklist'])


def allowed_bases(label, verdict, cfg=None):
    return tuple((cfg or config())['review']['decision_basis'][label][verdict])


# --------------------------------------------------------------------------
# Prompt rendering: static placeholders are filled from repository files.
# Dynamic, episode-specific inputs are never rendered into the prompt text;
# they travel in the INPUT JSON that the transport appends to the prompt.
# --------------------------------------------------------------------------

def _definition_lines(mapping, indent='    '):
    return '\n'.join(f'{indent}{code}: {text}' for code, text in mapping.items())


def _checklist_line(row):
    return f'- {row["item"]} [{row["scope"]}] {row["title"]}: {row["check"]}'


def _checklist_text(cfg):
    return '\n'.join(_checklist_line(row) for row in cfg['vv_checklist'])


def checklist_item_message(cfg, item):
    """Trailing message of a per-item V-V detection call: the call's item; the open sweep (O1) also lists the other
    items as context, since it looks for what they miss."""
    rows = {row['item']: row for row in cfg['vv_checklist']}
    text = 'Checklist item of this call:\n' + _checklist_line(rows[item])
    if rows[item]['scope'] == OPEN_SWEEP_SCOPE:
        text += ('\nChecked in separate calls (context only, do not report under them):\n'
                 + '\n'.join(_checklist_line(row) for key, row in rows.items() if key != item))
    return text + '\n'


def placeholder_values(config_path=CONFIG_PATH):
    cfg = config(config_path)
    values = {
        'VL_SUBCATEGORIES': _definition_lines(cfg['v_l_subcategories']),
        'VV_WITHIN_SUBCATEGORIES': _definition_lines(cfg['v_v_subcategories']['within_shot']),
        'VV_CROSS_SUBCATEGORIES': _definition_lines(cfg['v_v_subcategories']['cross_shot']),
        'VV_CHECKLIST': _checklist_text(cfg),
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


def render_prompt(template_path, config_path=CONFIG_PATH):
    text = _fill(Path(template_path).read_text(), placeholder_values(config_path))
    if '{{' in text or '}}' in text:
        raise ValueError(f'Unrendered placeholder left in {template_path}')
    return text


def write_rendered_prompt(template_path, target, config_path=CONFIG_PATH):
    """Render a prompt template into the stage output folder; the transport sends that file."""
    target = Path(target)
    target.write_text(render_prompt(template_path, config_path))
    return target


def static_source_paths(*templates, chain='v5'):
    """Repository files whose content defines the rendered prompts and schemas."""
    spec = chain_spec(chain)
    return [spec['config'], DEFINITIONS_PATH, REPAIR_PROMPT, spec['records'], SCHEMA_BUILDER,
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
    # A v2 requirement quote comes from the contract; the prompt is context, not a checking basis (owner, 2026-11-01).
    keys = (('entity_descriptions', 'shots', 'cross_shot') if contract_io.is_v2(contract)
            else ('entity_descriptions', 'entity_schedule', 'claims', 'prompt'))
    contract_texts = list(_strings({key: contract.get(key) for key in keys}))
    if contract_io.is_v2(contract):
        contract_texts += contract_io.generated_texts(contract)
    return dict(global_prompt=[prompt.get('global_prompt', '')], shot_prompt=shots, contract=contract_texts,
                shot_transitions=[transition_text(row) for row in transitions])


def quote_errors(quote, sources, where):
    """Problems of one requirement quote: contract text, or the fixed item text of a transition row."""
    source, text = quote['source'], quote['quote']
    if quote_found(text, sources[source]):
        return []
    other = 'shot_transitions' if source == 'contract' else 'contract'
    if quote_found(text, sources[other]):
        hint = f'; the words occur in {other}: set source accordingly'
    elif quote_found(text, sources['global_prompt']) or quote_found(text, list(sources['shot_prompt'].values())):
        hint = ('; the words occur only in the original prompt, which is not a checking basis: quote the contract '
                'text of the violated row')
    else:
        hint = '; copy the exact words of the source text (an ellipsis "..." may join two exact fragments)'
    return [f'{where}: quote {text!r} is not a literal quote of {source}{hint}']


def any_text_found(text, sources):
    pools = [sources['global_prompt'], list(sources['shot_prompt'].values()), sources['contract']]
    return any(quote_found(text, pool) for pool in pools)


# --------------------------------------------------------------------------
# Manifest helpers.
# --------------------------------------------------------------------------

def shot_ids(manifest):
    return [shot['shot_id'] for shot in manifest['shots']]


def cut_boundaries(manifest):
    """Every shot boundary is a cut (owner decision 2026-11-01): the requirement of each boundary, in shot order."""
    shots = shot_ids(manifest)
    return [dict(from_shot=a, to_shot=b, required='cut') for a, b in zip(shots, shots[1:])]


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
    if contract_io.is_v2(contract):
        return contract_io.presence_by_shot(contract)
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
    if contract_io.is_v2(contract):
        return contract_io.entity_kinds(contract)
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


def requirement_links(cfg):
    """True when issues name requirement IDs and the runner derives the links (config v2, owner 2026-11-04)."""
    return cfg['contract_template'].get('issue_links') == 'requirement_ids'


def requirement_index(template):
    """{item_id: (row, item)} over a template whose item IDs are unique requirement IDs."""
    return {item['item_id']: (row, item) for row in template for item in row['items']}


def contract_template(contract, ledger, manifest, transitions, requirement_ids=False):
    """Clause groups to check, per manifest shot (contract-checking template v2).

    One row per entity of the shot (its episode-wide description when the
    entity is scheduled there, plus the shot's single-entity claims about it),
    one relations row with the shot's multi-entity claims, one shot_text
    catch-all row, and one transition row per boundary (attached to the later
    shot).  Each row lists its requirement items; the model reports which items
    are violated.  Grouping by entity keeps the template short enough that the
    agent inspects the frames instead of ticking a long form.
    requirement_ids (chain v6): every item gets an ID that is unique in the
    template, so issues can name the requirements they report.
    """
    if contract_io.is_v2(contract):
        return contract_template_v2(contract, ledger, manifest, transitions, requirement_ids)
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

    for index, sid in enumerate(shots, 1):
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
                items.append(dict(item_id=f'S{index}-des-{label}' if requirement_ids else 'description',
                                  kind='entity_description', text=description))
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
                         items=[dict(item_id=f'S{index}-text' if requirement_ids else 'text', kind='shot_text',
                                     text=(prompt_shots.get(sid) or {}).get('text', ''))]
                         + [claim_item(claim, shot_claim_ids) for claim in loose],
                         note='Every other explicit requirement of this shot prompt, and of the global prompt where it '
                              'applies to this shot, not covered by the other rows of this shot.'))
        if sid in transitions_into:
            boundary = transitions_into[sid]
            rows.append(dict(row_id=f'TR:{boundary["from_shot"]}->{sid}', kind='transition', shot_id=sid,
                             from_shot=boundary['from_shot'], required=boundary['required'],
                             items=[dict(item_id=f'S{index}-cut' if requirement_ids else 'transition', kind='transition',
                                         text=transition_text(boundary))]))
    return _unique_rows(rows, requirement_ids)


def _unique_rows(rows, requirement_ids):
    seen = set()
    for row in rows:
        if row['row_id'] in seen:
            raise ValueError(f'Duplicate contract template row {row["row_id"]}')
        seen.add(row['row_id'])
    if requirement_ids:
        items = [item['item_id'] for row in rows for item in row['items']]
        repeated = sorted({item for item in items if items.count(item) > 1})
        if repeated:
            raise ValueError(f'Requirement IDs repeat in the contract template: {repeated}')
    return rows


def contract_template_v2(contract, ledger, manifest, transitions, requirement_ids=False):
    """The rows of a v2 contract, the only checking basis of the V-L branch (owner, 2026-11-01).

    Entity row: the entity's description and presence item when the shot lists
    it, its absent item when the shot excludes it, and the shot's single-entity
    requirements.  Relations row: the shot's requirements on several entities.
    Camera row and style row: only when the contract sets them.  Transition row:
    a clear cut at the boundary.  Cross-shot row: one cross_shot requirement,
    attached to the last shot it names and judged on all the shots it names.

    requirement_ids: the items that otherwise share one name in every row get
    shot-numbered IDs in the pattern of the contract's own requirement IDs
    (S<n>-des-<entity>, S<n>-cam-view, S<n>-cam-move, S<n>-sty, S<n>-cut).
    """
    descriptions = contract['entity_descriptions']
    blocks = {block['shot_id']: block for block in contract['shots']}
    ledger_ids = ledger_ids_by_label(ledger)
    present, absent = contract_io.presence_by_shot(contract), contract_io.absent_by_shot(contract)
    transitions_into = {row['to_shot']: row for row in transitions}
    order = {label: index for index, label in enumerate(descriptions)}
    rows = []

    def requirement_item(row, dimension):
        return dict(item_id=row['id'], kind='requirement', dimension=dimension, predicate=row.get('predicate'),
                    expected=row['expected'], quantifier=row['quantifier'], coordinate_frame=row.get('coordinate_frame'),
                    entity_labels=[str(key) for key in row['entities']])

    def list_item(index, tag, label, predicate, expected, quantifier):
        return dict(item_id=f'S{index}-{tag}-{label}', kind='requirement', dimension='presence', predicate=predicate,
                    expected=expected, quantifier=quantifier, coordinate_frame='none', entity_labels=[label])

    order_of_shot = {sid: index for index, sid in enumerate(shot_ids(manifest))}
    for index, sid in enumerate(shot_ids(manifest), 1):
        block = blocks[sid]
        items = [requirement_item(row, dimension) for dimension in contract_io.SHOT_REQUIREMENTS for row in block[dimension]]
        single = [item for item in items if len(item['entity_labels']) == 1]
        multi = [item for item in items if len(item['entity_labels']) != 1]
        labels = set(present[sid]) | set(absent[sid]) | {item['entity_labels'][0] for item in single}
        for label in sorted(labels, key=lambda key: order.get(key, len(order))):
            entity = descriptions.get(label) or {}
            name = entity.get('name')
            row_items = []
            if label in present[sid]:
                if entity.get('description'):
                    row_items.append(dict(item_id=f'S{index}-des-{label}' if requirement_ids else 'description',
                                          kind='entity_description', text=entity['description']))
                row_items.append(list_item(index, 'pre', label, 'present', contract_io.presence_text(name), 'exists'))
            if label in absent[sid]:
                row_items.append(list_item(index, 'abs', label, 'absent', contract_io.absent_text(name), 'throughout'))
            row_items += [item for item in single if item['entity_labels'][0] == label]
            rows.append(dict(row_id=f'EN:{label}@{sid}', kind='entity', shot_id=sid, entity_label=label, name=name,
                             ledger_entity_ids=list(ledger_ids.get(label, [])), items=row_items))
        if multi:
            rows.append(dict(row_id=f'RL:{sid}', kind='relations', shot_id=sid, items=multi))
        description = block['shot_description']
        camera_ids = dict(camera_view=f'S{index}-cam-view', camera_movement=f'S{index}-cam-move')
        camera = [dict(item_id=camera_ids[field] if requirement_ids else field, kind='camera', text=description[field])
                  for field in ('camera_view', 'camera_movement') if description.get(field)]
        if camera:
            rows.append(dict(row_id=f'CM:{sid}', kind='camera', shot_id=sid, items=camera))
        if description.get('style'):
            rows.append(dict(row_id=f'ST:{sid}', kind='style', shot_id=sid,
                             items=[dict(item_id=f'S{index}-sty' if requirement_ids else 'style', kind='style',
                                         text=description['style'])]))
        if sid in transitions_into:
            boundary = transitions_into[sid]
            rows.append(dict(row_id=f'TR:{boundary["from_shot"]}->{sid}', kind='transition', shot_id=sid,
                             from_shot=boundary['from_shot'], required=boundary['required'],
                             items=[dict(item_id=f'S{index}-cut' if requirement_ids else 'transition', kind='transition',
                                         text=transition_text(boundary))]))
        for row in contract.get('cross_shot') or []:
            named = sorted(row['shot_ids'], key=order_of_shot.__getitem__)
            if named[-1] == sid:
                rows.append(dict(row_id=f'XS:{row["id"]}', kind='cross_shot', shot_id=sid, shot_ids=named,
                                 ledger_entity_ids=[gid for key in row['entities'] for gid in ledger_ids.get(str(key), [])],
                                 items=[requirement_item(row, row['dimension'])]))
    return _unique_rows(rows, requirement_ids)


def row_shots(row):
    """Shots whose frames may decide a template row."""
    if row['kind'] == 'cross_shot':
        return set(row['shot_ids'])
    return {row['shot_id'], row['from_shot']} if row['kind'] == 'transition' else {row['shot_id']}


def row_occurrence_shots(row):
    """Shots in which an issue occurrence may cite a template row."""
    return set(row['shot_ids']) if row['kind'] == 'cross_shot' else {row['shot_id']}


# --------------------------------------------------------------------------
# Entities.
# --------------------------------------------------------------------------

def ledger_rows(ledger):
    """{global_entity_id: row}; the list a row is in gives its partition (the v2 ledger has no partition field)."""
    return {row['global_entity_id']: dict(row, partition=part) for part in ('prompt_bound', 'prompt_unbound') for row in ledger.get(part, [])}


def occurrence_frame_ids(occurrence):
    """Keyframes with a box: v2 ledger `boxes`, v1 ledger `observed_frame_ids`."""
    if 'boxes' in occurrence:
        return [box['frame_id'] for box in occurrence['boxes']]
    return list(occurrence.get('observed_frame_ids') or [])


def ledger_entity(row):
    return dict(entity_key=row['global_entity_id'], global_entity_id=row['global_entity_id'],
                source='detection_ledger', name=row.get('name') or row['global_entity_id'],
                description=row.get('description') or row.get('short_description') or '', partition=row.get('partition'),
                prompt_entity_id=row.get('prompt_entity_id'), frame_refs=[], provenance=None, basis_type=None,
                contract_label=None, quote=None, part_of=None, note='')


# Chain v6: an entity's specified / unspecified label comes from the entity ledger (owner, 2026-11-01, Q8).
# A ledger entity of the prompt_bound list (pb...) is specified; one of the prompt_unbound list (ge...) and an
# entity added by detection (n...) are unspecified (owner, 2026-11-02).
ENTITY_LABELS = {'prompt_bound': 'specified', 'prompt_unbound': 'unspecified'}


def ledger_label(row):
    """Label of a ledger row (from ledger_rows); the list it is in decides."""
    return ENTITY_LABELS[row['partition']]


def ledger_entity_v2(row):
    """A ledger entity in the chain-v6 record format (records v2): no provenance, the ledger label."""
    return dict(entity_key=row['global_entity_id'], global_entity_id=row['global_entity_id'],
                source='detection_ledger', name=row.get('name') or row['global_entity_id'],
                description=row.get('description') or row.get('short_description') or '', partition=row.get('partition'),
                prompt_entity_id=row.get('prompt_entity_id'), frame_refs=[], label=ledger_label(row))


def added_entity_v2(entity, source):
    """An entity added by a detection call (n...); it is unspecified."""
    return dict(entity_key=entity['entity_key'], global_entity_id=None, source=source, name=entity['name'],
                description=entity['description'], partition=None, prompt_entity_id=None,
                frame_refs=copy.deepcopy(entity['frame_refs']), label='unspecified')


def place_entity_ids(contract, ledger):
    """Ledger IDs of the contract's scheduled places (setting containers, not their elements)."""
    kinds = label_kinds(contract)
    return {gid for label, gids in ledger_ids_by_label(ledger).items() if kinds.get(label) == 'place' for gid in gids}


ELEMENT_SUBCATEGORIES = ('setting_background', 'background_drift')


def model_contract(contract):
    """A deep copy of the contract as the model receives it (a v2 contract without the prompt it carries in memory)."""
    return copy.deepcopy(contract_io.model_contract(contract))


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

def records_errors(value, schema_path=RECORDS_SCHEMA):
    import jsonschema
    schema = read(schema_path)
    validator = jsonschema.validators.validator_for(schema)(schema)
    return [f'{"/".join(map(str, error.absolute_path)) or "<root>"}: {error.message}'
            for error in validator.iter_errors(value)]


def require_records(value, where, schema_path=RECORDS_SCHEMA):
    errors = records_errors(value, schema_path)
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
