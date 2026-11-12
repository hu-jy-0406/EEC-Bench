#!/usr/bin/env python3
"""Compiled episode requirements (docs/contract-and-requirements-design.md): offline, no model or API call."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import episode_contract as contract_io  # noqa: E402
import episode_requirements as compiled  # noqa: E402
import run_vl_vv_branch_detection as detection  # noqa: E402
import run_vl_vv_detection as frontend  # noqa: E402
import vl_vv_branch_common as common  # noqa: E402
import vl_vv_requirement_answers as answers  # noqa: E402
import test_vl_vv_contract_v2 as v2  # noqa: E402
import test_vl_vv_requirement_answers as answers_test  # noqa: E402

CLEANED = ROOT / 'experiments/contract_cleanup_20261031/deliverables/contracts_1_200_with_evidence.jsonl'
REWRITES = ROOT / 'experiments/episode_contracts_v2_20261029/deliverables/episodes'
FIXTURE = v2.FIXTURES / v2.EPISODE / 'contract_with_evidence.json'


def partial_ledger(contract, keep):
    """A ledger with ids for every `keep`-th label only, two records for one label (a group entity)."""
    full = v2.ledger(contract)
    rows = [row for index, row in enumerate(full['prompt_bound']) if index % keep == 0]
    if rows:
        rows.append(dict(rows[0], global_entity_id='pb9999'))
    return dict(full, prompt_bound=rows)


def old_narrative(registry, shots):
    """The narrative lines of prepare before they became narrative_for."""
    facts = [dict(fact_id=s['shot_id'], shot_id=s['shot_id'], text='; '.join(
        e['name'] for e in registry['entities'] if next(x for x in e['schedule'] if x['shot_id'] == s['shot_id'])['expectation'] == 'required')
        or '(no scheduled entities)') for s in shots]
    extra = contract_io.no_presence_fact(registry)
    return dict(facts=facts + ([extra] if extra else []))


def check_contract(test, raw, path):
    package = compiled.compile_episode(path)
    contract, prompt = contract_io.split_v2(raw)
    memory = dict(contract, prompt=prompt)
    manifest = v2.manifest(memory)
    cuts = common.cut_boundaries(manifest)
    stored = json.loads(json.dumps(package[compiled.FILE]))
    for ledger in (v2.ledger(memory), partial_ledger(memory, 2), partial_ledger(memory, 3), {}):
        expected = common.contract_template_v2(memory, ledger, manifest, cuts, requirement_ids=True)
        test.assertEqual(json.dumps(compiled.join_ledger(stored['template'], ledger)), json.dumps(expected), contract['episode_id'])
    template = common.contract_template_v2(memory, v2.ledger(memory), manifest, cuts, requirement_ids=True)
    test.assertEqual(stored['requirements'], answers.requirements(template))
    registry = frontend.normalize_contract(contract, manifest['shots'])
    test.assertEqual(package['prompt_registry.json'], registry)
    test.assertEqual(package['narrative.json'], old_narrative(registry, manifest['shots']))
    test.assertEqual(stored['shot_ids'], common.shot_ids(manifest))
    test.assertEqual(stored['model_contract_sha256'], compiled.canonical_sha(contract))


class Equivalence(unittest.TestCase):
    def test_fixtures(self):
        for episode in v2.EPISODES:
            path = v2.FIXTURES / episode / 'contract_with_evidence.json'
            check_contract(self, json.loads(path.read_text()), path)

    def test_every_cleaned_and_rewritten_contract_compiles_to_what_a_run_derives(self):
        with tempfile.TemporaryDirectory() as temporary:
            count = 0
            for line in CLEANED.read_text().splitlines():
                raw = json.loads(line)
                path = Path(temporary) / 'cleaned.json'
                path.write_text(json.dumps(raw))
                check_contract(self, raw, path)
                count += 1
            for path in sorted(REWRITES.glob('*/contract_with_evidence.json')):
                check_contract(self, json.loads(path.read_text()), path)
                count += 1
        self.assertGreaterEqual(count, 600)


class LoadForCase(unittest.TestCase):
    def case(self, root, with_compiled):
        case = v2.v2_case(root)
        if with_compiled:
            package = compiled.compile_episode(FIXTURE)
            compiled.write_package(root / 'package', package)
            shutil.copy2(root / 'package' / compiled.FILE, case / compiled.FILE)
        return case

    def args(self, case):
        contract = contract_io.load_case_contract(case)
        return case, contract, json.loads((case / 'episode_entities.json').read_text()), v2.manifest(contract)

    def test_a_compiled_case_uses_the_stored_list_and_an_older_case_derives_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = self.case(root, True)
            template, reqs, info = compiled.load_for_case(*self.args(case))
            self.assertEqual(info['requirements_source'], 'compiled')
            self.assertEqual(info['requirements_sha256'], compiled.file_sha(case / compiled.FILE))
            (case / compiled.FILE).unlink()
            derived, derived_reqs, info = compiled.load_for_case(*self.args(case))
            self.assertEqual(info, dict(requirements_source='derived_at_run'))
            self.assertEqual(json.dumps(template), json.dumps(derived))
            self.assertEqual(reqs, derived_reqs)

    def test_a_package_of_another_contract_or_other_shots_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = self.case(root, True)
            other = v2.FIXTURES / v2.CAMERA_EPISODE / 'contract_with_evidence.json'
            (case / compiled.FILE).write_text(compiled.dump_text(compiled.compile_episode(other)[compiled.FILE]))
            with self.assertRaisesRegex(ValueError, 'different contract'):
                compiled.load_for_case(*self.args(case))
            stored = json.loads((root / 'package' / compiled.FILE).read_text())
            stored['shot_ids'] = stored['shot_ids'][:-1]
            (case / compiled.FILE).write_text(json.dumps(stored))
            with self.assertRaisesRegex(ValueError, 'differ'):
                compiled.load_for_case(*self.args(case))

    def test_the_detection_input_is_byte_identical_with_and_without_the_compiled_list(self):
        env = {'EECBENCH_CODEX_BACKEND': 'api', 'EECBENCH_API_MODEL': common.MODEL}
        shots = [block['shot_id'] for block in v2.load()['shots']]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = self.case(root, True)
            plain = root / 'plain'
            shutil.copytree(case, plain)
            (plain / compiled.FILE).unlink()
            with mock.patch.dict('os.environ', env), mock.patch.object(
                    detection.repair_loop, 'call_with_repair', answers_test.fake_loop(shots)):
                for fmt in ('answers', 'answers_no_contract', 'checks'):
                    detection.run(case, root / f'with_{fmt}', 'vl', vl_format=fmt)
                    detection.run(plain, root / f'without_{fmt}', 'vl', vl_format=fmt)
                    self.assertEqual((root / f'with_{fmt}/input.json').read_bytes(), (root / f'without_{fmt}/input.json').read_bytes())
                    with_run = json.loads((root / f'with_{fmt}/run.json').read_text())
                    self.assertEqual(with_run['requirements_source'], 'compiled')
                    self.assertEqual(with_run['requirements_sha256'], compiled.file_sha(case / compiled.FILE))
                    result = json.loads((root / f'without_{fmt}/result.json').read_text())
                    self.assertEqual(result['requirements_source'], 'derived_at_run')
                    hashes = json.loads((root / f'with_{fmt}/source_hashes.json').read_text())
                    self.assertIn(str((case / compiled.FILE).resolve()), hashes)


class Prepare(unittest.TestCase):
    def prepare(self, root, name, **kwargs):
        (root / 'manifest.json').write_text(json.dumps(v2.manifest(v2.load(), root)))
        frontend.prepare(root / 'manifest.json', FIXTURE, root / name, **kwargs)
        return root / name

    def test_prepare_with_a_package_copies_the_list_and_writes_identical_registry_and_narrative(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compiled.write_package(root / 'package', compiled.compile_episode(FIXTURE))
            plain, packaged = self.prepare(root, 'plain'), self.prepare(root, 'packaged', compiled=root / 'package')
            for name in ('prompt_registry.json', 'narrative.json', 'contract.json', 'prompt.json'):
                self.assertEqual((plain / name).read_bytes(), (packaged / name).read_bytes(), name)
            self.assertFalse((plain / compiled.FILE).exists())
            self.assertEqual((packaged / compiled.FILE).read_bytes(), (root / 'package' / compiled.FILE).read_bytes())
            record = json.loads((packaged / 'run.json').read_text())['compiled_requirements']
            self.assertEqual(record['requirements_sha256'], compiled.file_sha(packaged / compiled.FILE))
            self.assertNotIn('compiled_requirements', json.loads((plain / 'run.json').read_text()))

    def test_prepare_refuses_a_package_of_another_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compiled.write_package(root / 'package', compiled.compile_episode(
                v2.FIXTURES / v2.CAMERA_EPISODE / 'contract_with_evidence.json'))
            with self.assertRaises(ValueError):
                self.prepare(root, 'case', compiled=root / 'package')
            self.assertFalse((root / 'case').exists())


class Resolve(unittest.TestCase):
    def test_a_missing_or_stale_package_is_an_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = root / 'contract_with_evidence.json'
            shutil.copy2(FIXTURE, contract)
            with self.assertRaises(FileNotFoundError):
                contract_io.resolve_compiled('e', contract, root / 'compiled')
            compiled.write_package(root / 'compiled' / 'e', compiled.compile_episode(contract))
            self.assertEqual(contract_io.resolve_compiled('e', contract, root / 'compiled'), root / 'compiled' / 'e')
            contract.write_text(contract.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'Stale'):
                contract_io.resolve_compiled('e', contract, root / 'compiled')


class Cli(unittest.TestCase):
    def test_rerun_is_identical_and_a_changed_contract_needs_update(self):
        import compile_episode_requirements as cli
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = root / 'contract_with_evidence.json'
            shutil.copy2(FIXTURE, contract)
            with mock.patch.object(contract_io, 'resolve_v2_contract', return_value=contract):
                first = cli.compile_all(['e'], root / 'out')
                before = {p.name: p.read_bytes() for p in (root / 'out/e').iterdir()}
                self.assertEqual(cli.compile_all(['e'], root / 'out')[0]['status'], 'unchanged')
                self.assertEqual(before, {p.name: p.read_bytes() for p in (root / 'out/e').iterdir()})
                contract.write_text(contract.read_text() + '\n')
                with self.assertRaisesRegex(ValueError, '--update'):
                    cli.compile_all(['e'], root / 'out')
                self.assertEqual(cli.compile_all(['e'], root / 'out', update=True)[0]['status'], 'updated')
            self.assertEqual(first[0]['status'], 'new')


if __name__ == '__main__':
    unittest.main()
