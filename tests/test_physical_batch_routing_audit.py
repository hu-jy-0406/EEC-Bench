"""Role-routing artifact mutations, with no model process or frozen-code import."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / 'scripts'))
ROUTE = __import__("role_model_routing")

SPEC = importlib.util.spec_from_file_location('routing_auditor_tested', HERE / 'experiments/study_inconsistent_2/entity_discovery_iterations/audit_physical_batch.py')
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)


class RoutingAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = self.root / 'seed_7' / 'synthetic'
        self.routing = ROUTE.resolve_model_routing('primary-test', 'review-test')
        self.batch = {'model': 'primary-test', 'review_model': 'review-test', 'model_routing': self.routing,
                      'model_config': {'model': 'primary-test', 'review_model': 'review-test', 'model_routing': self.routing,
                                       'codex_wrapper': str(self.root / 'wrapper.sh')}, 'source_hashes': {}}
        self.manifest = {'shot_id': 'synthetic', 'status': 'failed', 'model_routing': copy.deepcopy(self.routing),
                         'revision_output_policy': A.WIRE_SELECTION, 'detector_closure': {'attempts': []}}
        source = self.root / 'frozen_workspace' / A.ROUTING_SOURCE
        source.parent.mkdir(parents=True)
        # Literal reading only: executing this synthetic frozen module is forbidden.
        source.write_text(f'POLICY_VERSION={A.ROUTING_POLICY!r}\nREQUEST_VERSION={A.REQUEST_POLICY!r}\nraise RuntimeError("must never execute")\n')
        self.batch['source_hashes'][A.ROUTING_SOURCE] = A.file_hash(source)
        self.manifest['stage_source_hashes'] = {str(source): A.file_hash(source)}
        self.schemas = {
            'detector': 'codex_entity_detector_ledger_v0.8.schema.json',
            'adjudicator_initial': 'codex_entity_adjudication_v0.6.schema.json',
            'adjudicator_revision': 'codex_entity_revision_wire_v0.1.schema.json',
            'verifier': 'codex_entity_verification_v0.6.schema.json',
            'granularity_group_member': 'codex_granularity_family_plan_v0.3.schema.json',
            'accepted_compact_assembly': 'codex_accepted_compact_assembly_plan_v0.5.schema.json',
            'prompt_bound_matcher': 'codex_prompt_bound_matching_v0.5.schema.json'}
        for filename in self.schemas.values():
            relative = 'EECBench/schemas/' + filename
            path = self.root / 'frozen_workspace' / relative
            self.write(path, {'title': filename})
            self.batch['source_hashes'][relative] = A.file_hash(path)
        self.images = []
        for i in range(6):
            path = self.folder / 'input_bundle' / f'frame{i}.png'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f'fake bytes, frame {i}'.encode())
            self.images.append(path)
        self.write(self.folder / 'input_bundle/shot_manifest.json', {'reference_frames': [
            {'frame_id': i, 'path': str(p), 'sha256': A.file_hash(p)} for i, p in enumerate(self.images)]})
        self.records = []

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False) + '\n')

    def add(self, role, *, role_id=None, attempt=1, round_index=None, status='success', started=True, usage=True):
        fields = {'detector': ('detector_attempts', 'detector_id', 'detector_1'),
                  'verifier': ('verifier_attempts', 'verifier_id', 'verifier_1'),
                  'granularity_group_member': ('granularity_family_attempts', 'planner_index', 1),
                  'accepted_compact_assembly': ('accepted_compact_assembly_attempts', 'planner_index', 1),
                  'adjudicator_initial': ('adjudicator_initial_attempts', None, None),
                  'adjudicator_revision': ('adjudicator_revision_attempts', None, None),
                  'prompt_bound_matcher': ('matcher_attempts', None, None),
                  'detector_closure': (None, 'detector_id', 'detector_1')}
        field, id_key, default = fields[role]
        identifier = default if role_id is None else role_id
        actual_id = f'{role}_planner_{identifier}' if id_key == 'planner_index' else identifier or role
        stem = actual_id + ('' if role.startswith('adjudicator_') and attempt == 1 else f'.attempt{attempt}')
        prompt_name = role + '_planner.txt' if id_key == 'planner_index' else ('prompt_bound_matcher.txt' if role == 'prompt_bound_matcher' else stem + '.txt')
        if role == 'detector_closure':
            round_index = round_index or 1
            base = self.folder / 'detector_closure' / actual_id / f'round_{round_index:02d}' / f'attempt{attempt}'
            prompt, schema = base.parent / 'prompt.txt', base.parent / 'output.schema.json'
            self.write(schema, {'title': 'specialized closure'})
        else:
            base = self.folder / 'codex_attempts' / stem
            prompt = self.folder / 'prompts' / prompt_name
            schema = self.root / 'frozen_workspace/EECBench/schemas' / self.schemas[role]
        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_text('Frozen full prompt for ' + role + '\n')
        output, events, stderr = [Path(str(base) + suffix) for suffix in ('.json', '.events.jsonl', '.stderr.log')]
        base.parent.mkdir(parents=True, exist_ok=True)
        workdir = self.folder / 'work' / stem
        workdir.mkdir(parents=True, exist_ok=True)
        thread = 'review-thread' if role.startswith('adjudicator_') else f'thread-{role}-{actual_id}-{round_index}-{attempt}'
        initial_ref = None
        resume = None
        if role == 'adjudicator_revision':
            origin = self.folder / 'codex_attempts/adjudicator_initial.request.json'
            initial_ref = {'path': str(origin), 'sha256': A.file_hash(origin), 'thread_id': 'review-thread'}
            resume = 'review-thread'
        context = ROUTE.request_context(self.routing, role=role, role_id=actual_id, attempt=attempt,
                                        shot_id='synthetic', round_index=round_index, initial_request=initial_ref)
        persistent = role == 'adjudicator_initial'
        binary = self.batch['model_config']['codex_wrapper']
        if resume:
            argv = [binary, 'exec', 'resume', '--json', '--output-schema', str(schema), '--output-last-message', str(output)]
        else:
            argv = [binary, '--ask-for-approval', 'never', 'exec'] + ([] if persistent else ['--ephemeral'])
            argv += ['--color', 'never', '--json', '--sandbox', 'read-only', '--output-schema', str(schema),
                     '--output-last-message', str(output), '--cd', str(workdir)]
        argv += ['--model', context['requested_model']]
        for image in self.images:
            argv += ['--image', str(image)]
        argv += ([resume] if resume else []) + ['-']
        request = ROUTE.build_request_audit(context, model=context['requested_model'], command=argv,
                    prompt=prompt.read_text(), attachments=self.images, schema_path=schema,
                    output_path=output, events_path=events, stderr_path=stderr, codex_bin=binary,
                    work_dir=workdir, persistent=persistent, resume_thread_id=resume)
        request_path = ROUTE.request_path(events)
        self.write(request_path, request)
        tokens = {'input_tokens': 100, 'cached_input_tokens': 20, 'output_tokens': 10, 'total_tokens': 110} if usage else None
        native = []
        if started is True:
            native += [{'type': 'thread.started', 'thread_id': thread}, {'type': 'turn.started'}]
        if usage:
            native.append({'type': 'turn.completed', 'usage': {k: tokens[k] for k in A.TOKEN_KEYS[:3]}})
        events.write_text(''.join(json.dumps(row) + '\n' for row in native))
        stderr.write_text('Retained native warning\n')
        row = {'attempt': attempt, 'status': status, 'error': 'known validation failure' if status == 'failed' else None,
               'subprocess_started': started, 'subprocess_start_unknown': started is None, 'token_usage': tokens,
               'thread_id': thread if started is True else None, **ROUTE.accounting_fragment(context, events)}
        if id_key:
            row[id_key] = identifier
        if role == 'detector_closure':
            row['round_index'] = round_index
            self.manifest['detector_closure']['attempts'].append(row)
        else:
            self.manifest.setdefault(field, []).append(row)
        record = {'row': row, 'request': request, 'path': request_path, 'events': events, 'prompt': prompt, 'context': context}
        self.records.append(record)
        return record

    def refresh(self, record):
        self.write(record['path'], record['request'])
        record['row'].update(ROUTE.accounting_fragment(record['context'], record['events']))

    def run_audit(self):
        costs = [r['row']['token_usage'] for r in self.records if r['row']['subprocess_started'] is not False]
        self.manifest['token_usage'] = {k: sum(u[k] for u in costs) if costs and all(u and type(u.get(k)) is int for u in costs) else None for k in A.TOKEN_KEYS}
        errors, locks = [], {}
        def check(ok, message):
            if not ok:
                errors.append(message)
        def verify(path, expected, label):
            actual = A.file_hash(path)
            locks[str(path)] = actual
            check(actual == expected, label + ': hash mismatch')
        result = A.audit_model_routing(self.root, self.batch, self.folder, self.manifest, check, verify)
        return result, errors, locks

    def test_real_request_helper_all_eight_roles_and_costs(self):
        for role in ('detector', 'detector_closure', 'adjudicator_initial', 'verifier', 'adjudicator_revision',
                     'granularity_group_member', 'accepted_compact_assembly', 'prompt_bound_matcher'):
            self.add(role)
        result, errors, locks = self.run_audit()
        self.assertEqual(errors, [])
        self.assertEqual(result['recorded_attempt_count'], 8)
        self.assertEqual(result['total_tokens'], 880)
        self.assertEqual(result['known_usage_subtotal']['cached_input_tokens'], 160)
        self.assertEqual(result['usage_by_verified_requested_model']['primary-test']['total_tokens'], 330)
        self.assertEqual(result['usage_by_verified_requested_model']['review-test']['total_tokens'], 550)
        self.assertEqual(result['unattributed_usage']['total_tokens'], 0)
        self.assertTrue(result['complete_cost'])
        self.assertEqual({r['requested_model'] for r in result['attempts'] if r['role'] in ('detector', 'detector_closure', 'prompt_bound_matcher')}, {'primary-test'})
        self.assertFalse(result['pixel_truth_verified'])
        self.assertTrue(any(p.endswith('.stderr.log') for p in locks))

    def test_rehashed_wrong_actual_model_does_not_hide_paid_peers(self):
        bad = self.add('detector', status='failed')
        self.add('verifier')
        pos = bad['request']['argv'].index('--model') + 1
        bad['request']['argv'][pos] = 'review-test'
        self.refresh(bad)
        result, errors, _ = self.run_audit()
        self.assertTrue(any('CLI argv' in e for e in errors), errors)
        self.assertEqual(result['known_usage_subtotal']['total_tokens'], 220)
        self.assertTrue(result['attempts'][1]['request_verified'])
        self.assertEqual(result['unattributed_usage']['known_usage_subtotal']['total_tokens'], 110)
        self.assertEqual(result['usage_by_verified_requested_model']['review-test']['total_tokens'], 110)
        self.assertEqual(result['usage_by_verified_requested_model']['primary-test']['total_tokens'], 0)

    def test_role_schema_prompt_and_attachment_tampering(self):
        rec = self.add('detector')
        original = copy.deepcopy(rec['request'])
        for key, value in (('role', 'verifier'), ('schema', {'path': str(self.root / 'wrong'), 'sha256': '0'*64}),
                           ('attachments', list(reversed(original['attachments']))), ('prompt_sha256', '0'*64)):
            with self.subTest(key=key):
                rec['request'] = {**copy.deepcopy(original), key: value}
                self.refresh(rec)
                result, errors, _ = self.run_audit()
                self.assertTrue(errors)
                self.assertEqual(result['known_usage_subtotal']['total_tokens'], 110)

    def test_revision_initial_reference_and_native_thread_binding(self):
        self.add('adjudicator_initial')
        rec = self.add('adjudicator_revision')
        rec['request']['initial_request']['sha256'] = '0'*64
        self.refresh(rec)
        result, errors, _ = self.run_audit()
        self.assertTrue(any('initial request/thread' in e for e in errors), errors)
        self.assertEqual(result['total_tokens'], 220)
        rec['request']['initial_request']['sha256'] = A.file_hash(self.records[0]['path'])
        self.refresh(rec)
        rec['events'].write_text(rec['events'].read_text().replace('review-thread', 'wrong-thread'))
        _, errors, _ = self.run_audit()
        self.assertTrue(any('revision native thread' in e for e in errors), errors)

    def test_prepared_initial_raw_failure_keeps_cost_and_same_review_thread(self):
        initial = self.add('adjudicator_initial', status='failed')
        initial['row'].update(raw_contract_valid=False, derived_contract_valid=True,
                              recovery_status='pending_identity_review')
        self.add('adjudicator_revision')
        result, errors, _ = self.run_audit()
        self.assertEqual(errors, [])
        self.assertEqual(result['total_tokens'], 220)
        self.assertEqual(result['attempts'][0]['status'], 'failed')
        initial['row']['derived_contract_valid'] = False
        _, errors, _ = self.run_audit()
        self.assertTrue(any('initial request/thread' in e for e in errors), errors)

    def test_batch_entry_checks_launch_route_and_retains_failed_shot_accounting(self):
        self.add('detector', status='failed')
        self.run_audit()  # materialize the normal aggregate
        self.batch.update(seeds=[7], shots=['synthetic'], identity_review_policy=A.POLICY,
                          reasoning_effort='high')
        self.batch['model_config']['reasoning_effort'] = 'high'
        self.manifest.update(shuffle_seed=7, model='primary-test', identity_review_policy=A.POLICY,
                             revision_output_policy='canonical')
        for relative in A.CRITICAL_SOURCES:
            path = self.root / 'frozen_workspace' / relative
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('synthetic never executed')
            self.batch['source_hashes'][relative] = A.file_hash(path)
        self.write(self.root / 'execution_config/model_config.json', self.batch['model_config'])
        self.write(self.root / 'robustness_manifest.json', self.batch)
        self.write(self.folder / 'run_manifest.json', self.manifest)
        launch = {'seed': 7, 'command': ['python', 'replay', '--codex-model', 'primary-test',
                  '--codex-review-model', 'review-test', '--ensemble-identity-review-policy', A.POLICY,
                  '--ensemble-shuffle-seed', '7', '--codex-bin', self.batch['model_config']['codex_wrapper']]}
        self.write(self.root / 'seed_7.launch.json', launch)
        result = A.audit(self.root)
        self.assertTrue(result['integrity_ok'], result['integrity_errors'])
        self.assertEqual(result['runs'][0]['model_routing']['known_usage_subtotal']['total_tokens'], 110)
        self.assertFalse(result['audit_complete'])
        launch['command'][launch['command'].index('--codex-review-model') + 1] = 'wrong'
        self.write(self.root / 'seed_7.launch.json', launch)
        result = A.audit(self.root)
        self.assertTrue(any('--codex-review-model' in e for e in result['integrity_errors']))
        self.assertEqual(result['runs'][0]['model_routing']['total_tokens'], 110)

    def test_explicit_nonstart_is_not_unknown_or_paid(self):
        rec = self.add('detector', status='failed', started=False, usage=False)
        rec['path'].unlink()
        rec['row']['model_request'].update(status='not_materialized', sha256=None)
        self.add('verifier')
        result, errors, _ = self.run_audit()
        self.assertEqual(errors, [])
        self.assertEqual(result['unknown_start_count'], 0)
        self.assertEqual(result['total_tokens'], 110)
        self.assertFalse(result['attempts'][0]['native_started'])

    def test_unknown_start_preserves_known_subtotal_and_null_total(self):
        self.add('detector', status='failed', started=None, usage=False)
        self.add('verifier')
        result, errors, _ = self.run_audit()
        self.assertEqual(errors, [])
        self.assertEqual(result['unknown_start_count'], 1)
        self.assertIsNone(result['usage_by_verified_requested_model']['primary-test']['total_tokens'])
        self.assertEqual(result['usage_by_verified_requested_model']['review-test']['total_tokens'], 110)
        self.assertEqual(result['known_usage_subtotal']['total_tokens'], 110)
        self.assertIsNone(result['total_tokens'])

    def test_known_usage_with_unknown_start_remains_a_subtotal(self):
        rec = self.add('detector', status='failed', started=None)
        rec['events'].write_text('')  # accounting retains usage despite transport artifact loss
        result, errors, _ = self.run_audit()
        self.assertEqual(errors, [])
        self.assertEqual(result['known_usage_subtotal']['total_tokens'], 110)
        self.assertIsNone(result['total_tokens'])

    def test_partial_failed_jsonl_retains_completed_usage(self):
        rec = self.add('detector', status='failed')
        rec['events'].write_text(rec['events'].read_text() + '{partial')
        result, errors, _ = self.run_audit()
        self.assertEqual(errors, [])
        self.assertTrue(result['attempts'][0]['malformed_native_lines'])
        self.assertEqual(result['total_tokens'], 110)
        rec['row']['status'] = 'success'
        _, errors, _ = self.run_audit()
        self.assertTrue(any('successful attempt' in e for e in errors), errors)

    def test_missing_attempt_checkpoint_recovers_native_cost_separately(self):
        self.add('detector')
        self.add('verifier')
        self.manifest['verifier_attempts'] = []
        result, errors, _ = self.run_audit()
        self.assertTrue(any('lost actual' in e for e in errors), errors)
        self.assertEqual(result['recorded_attempt_count'], 1)
        self.assertEqual(result['known_usage_subtotal']['total_tokens'], 220)
        self.assertEqual(result['unrecorded_native_recovery'][0]['usage']['total_tokens'], 110)
        self.assertEqual(result['unattributed_usage']['known_usage_subtotal']['total_tokens'], 110)
        self.assertIsNone(result['total_tokens'])

    def test_request_only_unrecorded_slot_does_not_prove_start(self):
        rec = self.add('detector')
        self.manifest['detector_attempts'] = []
        rec['events'].write_text('')
        result, errors, _ = self.run_audit()
        self.assertTrue(errors)
        self.assertIsNone(result['unrecorded_native_recovery'][0]['subprocess_started'])
        self.assertEqual(result['known_usage_subtotal']['total_tokens'], 0)
        self.assertIsNone(result['total_tokens'])

    def test_synthetic_empty_plans_do_not_create_requests_or_cost(self):
        self.add('detector')
        self.manifest.update(granularity_family_attempts=[], accepted_compact_assembly_attempts=[])
        self.write(self.folder / 'adjudication/granularity_group_member_planner_1.json', {'families': []})
        result, errors, _ = self.run_audit()
        self.assertEqual(errors, [])
        self.assertEqual(result['recorded_attempt_count'], 1)
        self.assertEqual(result['total_tokens'], 110)

    def test_retry_budget_and_fresh_isolation(self):
        first = self.add('verifier', status='failed')
        second = self.add('verifier', attempt=2)
        result, errors, _ = self.run_audit()
        self.assertEqual(errors, [])
        self.assertEqual(result['total_tokens'], 220)
        second['events'].write_text(second['events'].read_text().replace(second['row']['thread_id'], first['row']['thread_id']))
        second['row']['thread_id'] = first['row']['thread_id']
        _, errors, _ = self.run_audit()
        self.assertTrue(any('reused a native thread' in e for e in errors), errors)
        first['row']['status'] = 'success'
        result, errors, _ = self.run_audit()
        self.assertTrue(any('retry without' in e for e in errors), errors)
        self.assertEqual(result['unattributed_usage']['known_usage_subtotal']['total_tokens'], 220)
        self.assertIsNone(result['total_tokens'])

    def test_unknown_or_mixed_policy_rejected_legacy_not_backfilled(self):
        for owner, key, value in ((self.batch, 'review_model', 'wrong'),
                                  (self.routing, 'policy_version', 'future')):
            old = owner[key]
            owner[key] = value
            with self.assertRaisesRegex(ValueError, 'routing'):
                self.run_audit()
            owner[key] = old
        self.batch.pop('review_model')
        self.batch.pop('model_routing')
        self.batch['model_config'].pop('review_model')
        self.batch['model_config'].pop('model_routing')
        self.manifest.pop('model_routing')
        self.manifest['detector_attempts'] = [{'legacy': 'no new fields invented'}]
        result, errors, _ = self.run_audit()
        self.assertIsNone(result)
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
