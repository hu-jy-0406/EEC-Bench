#!/usr/bin/env python3
"""Reading episode contracts: format v2 (default) and v1 (historical chains).

Format v2 (docs/episode-contract-v2-format.md): integer-keyed entity_descriptions,
one block per shot (locations, shot_description with camera and style, presence,
absent, appearance, spatial, motion) and top-level cross_shot requirements.  The
evaluating model gets the version without evidence; the prompt travels separately
and is context, not a checking basis.

A case holds contract.json (model-facing) and prompt.json.  In memory a v2
contract carries the prompt under "prompt", the place a v1 contract keeps it,
so the stages share one access path; model_contract() removes it again before
the contract goes to a model.

Every shot boundary is a cut (owner decision 2026-11-01), so a contract states
no transition.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V2_SCHEMA = 'episode_contract_v2'
PROMPT_FILE = 'prompt.json'
CLEANED_CONTRACTS = ROOT / 'experiments/contract_cleanup_20261031'
V2_CONTRACTS = ROOT / 'experiments/episode_contracts_v2_20261029/deliverables/episodes'
COMPILED_ROOT = ROOT / 'experiments/compiled_requirements_20261105/compiled'
EVIDENCE_KEYS = ('evidence', 'source_claim_ids', 'source_labels', 'origin', 'prompt', 'cleanup')
SHOT_REQUIREMENTS = ('appearance', 'spatial', 'motion')
# Registry categories and subject kinds of the v1 entity_schedule fields, by v2 entity label.
CATEGORY = {'character': 'characters', 'location': 'places', 'object': 'objects'}
KIND = {'character': 'character', 'location': 'place', 'object': 'object'}
SUBJECT_KIND = {'character': 'character', 'location': 'setting'}
# Narrative fact that names the contract entities listed in no shot's presence (only in absent or in a
# requirement); it is the prompt evidence of their registry entries.
NO_PRESENCE_FACT = 'contract_entities_in_no_presence'


def read(path):
    return json.loads(Path(path).read_text())


def is_v2(contract):
    return contract.get('schema_version') == V2_SCHEMA


def model_facing(value):
    """Drop evidence, provenance and the prompt copy; a {value, evidence} field collapses to its value."""
    if isinstance(value, dict):
        out = {key: model_facing(item) for key, item in value.items() if key not in EVIDENCE_KEYS}
        return out['value'] if set(out) == {'value'} else out
    if isinstance(value, list):
        return [model_facing(item) for item in value]
    return value


def split_v2(raw, prompt=None):
    """(model-facing contract, prompt) of a v2 contract file with or without evidence."""
    prompt = raw.get('prompt') if prompt is None else prompt
    if not isinstance(prompt, dict) or not isinstance(prompt.get('shots'), list):
        raise ValueError('A v2 contract without evidence holds no prompt: pass the prompt JSON '
                         '({global_prompt, shots: [{shot_id, text}]}) or the contract with evidence')
    return model_facing(raw), {'global_prompt': prompt.get('global_prompt', ''),
                               'shots': [dict(shot_id=row['shot_id'], text=row['text']) for row in prompt['shots']]}


def validate_v2(contract, prompt, shot_ids):
    """Every shot and entity reference of a v2 contract must resolve; fails listing all problems."""
    errors = []
    if [row['shot_id'] for row in contract['shots']] != list(shot_ids):
        errors.append(f'contract shots {[row["shot_id"] for row in contract["shots"]]} differ from manifest {list(shot_ids)}')
    if [row['shot_id'] for row in prompt['shots']] != list(shot_ids):
        errors.append(f'prompt shots {[row["shot_id"] for row in prompt["shots"]]} differ from manifest {list(shot_ids)}')
    known = set(contract['entity_descriptions'])
    for block in contract['shots']:
        sid = block['shot_id']
        if 'transition_from_previous' in block['shot_description']:
            errors.append(f'{sid}: shot_description.transition_from_previous is no longer part of the contract')
        if 'style' not in block['shot_description']:
            errors.append(f'{sid}: shot_description.style is missing (a string, or null when the prompt states none)')
        for field in ('locations', 'presence', 'absent'):
            errors += [f'{sid} {field}: unknown entity {key}' for key in block[field] if str(key) not in known]
        for dimension in SHOT_REQUIREMENTS:
            for row in block[dimension]:
                errors += [f'{row["id"]}: unknown entity {key}' for key in row['entities'] if str(key) not in known]
    for row in contract.get('cross_shot') or []:
        errors += [f'{row["id"]}: unknown entity {key}' for key in row['entities'] if str(key) not in known]
        errors += [f'{row["id"]}: unknown shot {sid}' for sid in row['shot_ids'] if sid not in shot_ids]
    if errors:
        raise ValueError('Invalid v2 contract: ' + '; '.join(errors))


def load_case_contract(case):
    case = Path(case)
    contract = read(case / 'contract.json')
    if is_v2(contract):
        if not (case / PROMPT_FILE).is_file():
            raise ValueError(f'{case}: a v2 contract needs {PROMPT_FILE} beside it')
        return dict(contract, prompt=read(case / PROMPT_FILE))
    return contract


def model_contract(contract):
    """The contract as a model receives it: v2 without the prompt carried in memory, v1 unchanged."""
    return {key: value for key, value in contract.items() if key != 'prompt'} if is_v2(contract) else contract


def require_v2(contract, allow_v1, where):
    if not is_v2(contract) and not allow_v1:
        raise ValueError(f'{where}: the default chain reads contract v2 (a v1 contract was given); '
                         '--allow-v1-contract is only for reproducing historical results')


def require_v1(contract, where):
    if is_v2(contract):
        raise ValueError(f'{where}: older chains (discovery v1-v4) read v1 contracts; run a v2 contract with discovery v5')


def _labels(contract, block, field):
    listed = {str(key) for key in block[field]}
    return [label for label in contract['entity_descriptions'] if label in listed]


def presence_by_shot(contract):
    """{shot_id: entity IDs expected in the shot, as strings, in entity table order}."""
    return {block['shot_id']: _labels(contract, block, 'presence') for block in contract['shots']}


def absent_by_shot(contract):
    return {block['shot_id']: _labels(contract, block, 'absent') for block in contract['shots']}


def entity_kinds(contract):
    return {label: KIND[row['label']] for label, row in contract['entity_descriptions'].items()}


def shot_settings(contract):
    """Main setting names of each shot (v2 shots[].locations), in the shape of the matching payload."""
    names = contract['entity_descriptions']
    return [dict(shot_id=block['shot_id'], places=[names[str(key)]['name'] for key in block['locations']])
            for block in contract['shots']]


def continuity_schedule(contract):
    """(entity ID, subject kind, shots listing it) for the characters and locations of the contract."""
    present = presence_by_shot(contract)
    rows = []
    for label, row in contract['entity_descriptions'].items():
        if row['label'] in SUBJECT_KIND:
            rows.append((label, SUBJECT_KIND[row['label']], [sid for sid, labels in present.items() if label in labels]))
    return rows


def presence_text(name):
    return f'{name}: visible in this shot.'


def absent_text(name):
    return f'{name}: not visible in this shot.'


def generated_texts(contract):
    """Requirement wording the template generates from presence and absent lists (a V-L issue may quote it)."""
    names = contract['entity_descriptions']
    texts = []
    for block in contract['shots']:
        texts += [presence_text(names[str(key)]['name']) for key in block['presence']]
        texts += [absent_text(names[str(key)]['name']) for key in block['absent']]
    return texts


def prompt_registry(contract, shots):
    """Prompt registry from v2 presence lists: every contract entity, keyed by its contract ID.

    An entity is required in the shots whose presence lists it. Every contract entity has an entry, so
    every contract entity has a ledger record (owner decision 2026-11-02, open-questions Q16): one listed
    in no presence list (only in absent, or only in a requirement) is not_required in every shot, and its
    prompt evidence is the narrative fact NO_PRESENCE_FACT (see no_presence_fact).
    """
    shot_ids = [shot['shot_id'] for shot in shots]
    present = presence_by_shot(contract)
    entities = []
    for label, row in contract['entity_descriptions'].items():
        listed = [sid for sid in shot_ids if label in present[sid]]
        name = row['name'].strip()
        entities.append(dict(
            prompt_entity_id=label, contract_entity_id=label, name=name,
            description=str(row.get('description', name)).strip() or name,
            contract_category=CATEGORY[row['label']],
            evidence=[dict(fact_id=sid, quote=name) for sid in listed] or [dict(fact_id=NO_PRESENCE_FACT, quote=name)],
            schedule=[dict(shot_id=sid, expectation='required' if sid in listed else 'not_required',
                           reason='Listed in contract shots[].presence.' if sid in listed
                           else 'Not listed in contract shots[].presence.') for sid in shot_ids]))
    return dict(schema_version='prompt_registry_v1', source='contract.shots.presence', shot_ids=shot_ids,
                mapping=dict(method='shot_id_exact'), entities=entities)


def no_presence_fact(registry):
    """The episode-level narrative fact naming the registry entities required in no shot, or None."""
    names = [e['name'] for e in registry['entities'] if all(r['expectation'] != 'required' for r in e['schedule'])]
    if not names:
        return None
    return dict(fact_id=NO_PRESENCE_FACT, shot_id=None,
                text="Contract entities listed in no shot's presence: " + '; '.join(names))


def resolve_v2_contract(episode_id):
    """The current contract with evidence of an episode: the cleaned one once exported, else the v2 rewrite."""
    for index in sorted((CLEANED_CONTRACTS / 'deliverables').glob('index_*.json')):
        if any(row['episode_id'] == episode_id for row in read(index)):
            return CLEANED_CONTRACTS / 'episodes' / episode_id / 'contract_with_evidence.json'
    path = V2_CONTRACTS / episode_id / 'contract_with_evidence.json'
    if not path.is_file():
        raise FileNotFoundError(f'No v2 contract for episode {episode_id}')
    return path


COMPILED_FILES = ('requirements.json', 'prompt_registry.json', 'narrative.json')


def resolve_compiled(episode_id, contract_path, root=None):
    """Folder of the compiled requirement package of an episode (experiments/compiled_requirements_20261105/compiled).

    Raises when the package is missing or was compiled from a different version of the contract file
    (stale package: run compile_episode_requirements.py --update)."""
    import hashlib
    folder = Path(root or COMPILED_ROOT) / episode_id
    missing = [name for name in COMPILED_FILES if not (folder / name).is_file()]
    if missing:
        raise FileNotFoundError(f'No compiled requirement package for {episode_id} in {folder} (missing {missing}); '
                                'run scripts/compile_episode_requirements.py')
    recorded = read(folder / 'requirements.json')['source_contract_sha256']
    current = hashlib.sha256(Path(contract_path).read_bytes()).hexdigest()
    if recorded != current:
        raise ValueError(f'Stale compiled package for {episode_id}: {contract_path} changed after compilation; '
                         'recompile with scripts/compile_episode_requirements.py --update')
    return folder
