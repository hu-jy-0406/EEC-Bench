#!/usr/bin/env python3
"""Compiled episode requirements: the V-L requirement list and the other pure functions of a contract.

docs/contract-and-requirements-design.md.  The requirement list, the prompt registry and the narrative
facts are functions of the episode contract alone.  They are compiled once per contract
(compile_episode_requirements.py) and reused by every run of the episode; a case holds requirements.json.
Nothing is rewritten here: the template, the requirement list, the registry and the narrative come from the
functions that derived them at every run before (vl_vv_branch_common.contract_template_v2,
vl_vv_requirement_answers.requirements, episode_contract.prompt_registry, run_vl_vv_detection.narrative_for).
Only the ledger IDs of the template rows depend on a video; join_ledger fills them at run time.
"""
import copy
import hashlib
import json
from pathlib import Path

import episode_contract as contract_io
import vl_vv_branch_common as common
import vl_vv_requirement_answers as answers_format

SCHEMA = 'episode_requirements_v1'
FILE = 'requirements.json'
PACKAGE_FILES = (FILE, 'prompt_registry.json', 'narrative.json')
COMPILER_FILES = ('episode_requirements.py', 'vl_vv_branch_common.py', 'vl_vv_requirement_answers.py',
                  'episode_contract.py', 'run_vl_vv_detection.py')
SCRIPTS = Path(__file__).resolve().parent


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def dump_text(value):
    """The text run_vl_vv_detection.dump writes."""
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def _detection():
    import run_vl_vv_detection  # late import: that module imports this one lazily
    return run_vl_vv_detection


def compiler_record():
    return {name: file_sha(SCRIPTS / name) for name in COMPILER_FILES}


def compile_episode(contract_path):
    """The package of a contract with evidence: requirements.json, prompt_registry.json, narrative.json (as dicts)."""
    contract_path = Path(contract_path).resolve()
    raw = json.loads(contract_path.read_text())
    if not contract_io.is_v2(raw):
        raise ValueError(f'{contract_path}: only v2 contracts compile')
    contract, prompt = contract_io.split_v2(raw)
    contract_io.validate_v2(contract, prompt, [block['shot_id'] for block in contract['shots']])
    shots = [dict(shot_id=block['shot_id']) for block in contract['shots']]
    manifest = dict(shots=shots)
    in_memory = dict(contract, prompt=prompt)
    template = common.contract_template_v2(in_memory, {}, manifest, common.cut_boundaries(manifest), requirement_ids=True)
    detection = _detection()
    registry = detection.normalize_contract(contract, shots)
    narrative = detection.narrative_for(registry, [shot['shot_id'] for shot in shots], True)
    requirements = dict(
        schema_version=SCHEMA, episode_id=contract['episode_id'], source_contract=str(contract_path),
        source_contract_sha256=file_sha(contract_path), model_contract_sha256=canonical_sha(contract),
        compiler=compiler_record(), shot_ids=[shot['shot_id'] for shot in shots], template=template,
        requirements=answers_format.requirements(template),
        prompt_registry_sha256=canonical_sha(registry), narrative_sha256=canonical_sha(narrative))
    return {FILE: requirements, 'prompt_registry.json': registry, 'narrative.json': narrative}


def write_package(folder, package):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name in PACKAGE_FILES:
        text = dump_text(package[name])
        path = folder / name
        if not path.is_file() or path.read_text() != text:
            path.write_text(text)


def join_ledger(template, ledger):
    """The template with each row's ledger_entity_ids filled from a detector ledger, as contract_template_v2 does."""
    ids = common.ledger_ids_by_label(ledger)
    rows = copy.deepcopy(template)
    for row in rows:
        if row['kind'] == 'entity':
            row['ledger_entity_ids'] = list(ids.get(row['entity_label'], []))
        elif row['kind'] == 'cross_shot':
            row['ledger_entity_ids'] = [gid for key in row['items'][0]['entity_labels'] for gid in ids.get(str(key), [])]
    return rows


def _read(path):
    return json.loads(Path(path).read_text())


def _check_stored(stored, model_contract, shot_ids, where):
    if stored.get('schema_version') != SCHEMA:
        raise ValueError(f'{where}: not an {SCHEMA} file')
    if stored['model_contract_sha256'] != canonical_sha(model_contract):
        raise ValueError(f'{where}: compiled for a different contract (model_contract_sha256 differs); recompile')
    if list(stored['shot_ids']) != list(shot_ids):
        raise ValueError(f'{where}: shots {stored["shot_ids"]} differ from {list(shot_ids)}')


def load_for_case(case, contract, ledger, manifest, requirement_ids=True):
    """(template, requirements, info) of a V-L run.

    A case holding requirements.json uses the compiled list (verified against the case contract and manifest);
    an older case derives it as before.  requirements is None when the template has no requirement IDs.
    """
    case = Path(case)
    path = case / FILE
    transitions = common.cut_boundaries(manifest)
    if path.is_file() and requirement_ids and contract_io.is_v2(contract):
        stored = _read(path)
        _check_stored(stored, contract_io.model_contract(contract), common.shot_ids(manifest), str(path))
        info = dict(requirements_source='compiled', requirements_sha256=file_sha(path))
        return join_ledger(stored['template'], ledger), stored['requirements'], info
    template = common.contract_template(contract, ledger, manifest, transitions, requirement_ids=requirement_ids)
    requirements = answers_format.requirements(template) if requirement_ids and contract_io.is_v2(contract) else None
    return template, requirements, dict(requirements_source='derived_at_run')


def verify_package(folder, contract_path, model_contract, registry, narrative):
    """Check a package against a contract file and what prepare derived; returns {folder, record}."""
    folder, contract_path = Path(folder).resolve(), Path(contract_path).resolve()
    for name in PACKAGE_FILES:
        if not (folder / name).is_file():
            raise FileNotFoundError(f'{folder}: compiled package lacks {name}')
    stored = _read(folder / FILE)
    if stored.get('schema_version') != SCHEMA:
        raise ValueError(f'{folder / FILE}: not an {SCHEMA} file')
    if stored['source_contract_sha256'] != file_sha(contract_path):
        raise ValueError(f'{folder}: stale package, {contract_path} changed after compilation; recompile')
    _check_stored(stored, model_contract, [block['shot_id'] for block in model_contract['shots']], str(folder / FILE))
    for name, derived, key in (('prompt_registry.json', registry, 'prompt_registry_sha256'),
                               ('narrative.json', narrative, 'narrative_sha256')):
        if canonical_sha(_read(folder / name)) != stored[key] or canonical_sha(derived) != stored[key]:
            raise ValueError(f'{folder / name}: differs from the registry/narrative derived from the contract')
    record = dict(package=str(folder), source_contract=str(contract_path),
                  source_contract_sha256=stored['source_contract_sha256'],
                  requirements_sha256=file_sha(folder / FILE),
                  prompt_registry_sha256=stored['prompt_registry_sha256'], narrative_sha256=stored['narrative_sha256'])
    return dict(folder=folder, record=record)
