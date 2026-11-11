"""Pipeline sync 2026-11-02 (open-questions Q7, Q8, Q11, Q12): chain v6 = discovery v6 -> review v7 (two calls per
branch) -> scoring v6, the clustering collection rule and several local entities bound to one contract entity.
No API, GPU or Slurm calls."""
import copy
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import build_vl_vv_branch_schemas as builder  # noqa: E402
import gs_shot_prompt_recovery as recovery  # noqa: E402
import run_vl_vv_branch_detection as detection  # noqa: E402
import run_vl_vv_branch_review as review  # noqa: E402
import run_vl_vv_branch_scoring as scoring  # noqa: E402
import run_vl_vv_detection as frontend  # noqa: E402
import run_vl_vv_pipeline as pipeline  # noqa: E402
import run_wedetect_shot_entities as wedetect  # noqa: E402
import vl_vv_branch_common as common  # noqa: E402
import test_vl_vv_branch_pipeline as base  # noqa: E402
import test_vl_vv_matching_v2 as matching  # noqa: E402

spec = importlib.util.spec_from_file_location(
    'run_batch', ROOT / 'experiments/vl_vv_multimodel_first200_20260926/run_batch.py')
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)

CFG = common.chain_config('v6')
fr, has = base.fr, base.has
SENTENCE = ('Every contract entity has a ledger record, even when no box was detected. Use a contract entity\'s ledger '
            'ID whenever one fits, then an unspecified ledger entity; add a new entity (n1, n2, ...) only when no '
            'ledger record fits.')
LAMP_V1 = '同一房间的落地灯颜色由白变红。'


def flat(text):
    return ' '.join(text.split())


# --------------------------------------------------------------------------
# Chain-v6 fixtures (the chain-v5 fixtures of test_vl_vv_branch_pipeline with the v6 protocols).
# --------------------------------------------------------------------------

def v6_template():
    """The chain-v5 fixture contract's template with requirement IDs (chain v6, owner 2026-11-04)."""
    return common.contract_template(base.contract(), base.ledger(), base.manifest(), base.TRANSITIONS,
                                    requirement_ids=True)


def vl_result():
    """The chain-v5 V-L fixture in the v6 format: violated items and occurrences name requirement IDs, and the
    rows list no issue IDs."""
    result = copy.deepcopy(dict(base.vl_result(), protocol='vl_vv_issue_discovery_v6_vl'))
    rename = {old['row_id']: dict(zip([item['item_id'] for item in old['items']], [item['item_id'] for item in new['items']]))
              for old, new in zip(base.template(), v6_template())}
    for check in result['checks']:
        del check['issue_ids']
        check['violated_items'] = [rename[check['row_id']][item] for item in check['violated_items']]
    violated = {check['row_id']: check['violated_items'] for check in result['checks']}
    for issue in result['issues']:
        for occurrence in issue['occurrences']:
            occurrence['requirement_ids'] = [req for rid in occurrence.pop('row_ids') for req in violated[rid]]
    return result


def vv_result():
    """Chain v6 checklist traversal (2026-11-09): X5 and X6 report the same lamp change as V1 and V2 (to be merged
    by the verifier); the open sweep O1 reports V3, a within-shot pop-in of an added bystander."""
    lamp = {key: value for key, value in base.vv_result()['issues'][0].items()
            if key not in ('change_ids', 'checklist_items')}
    found = {
        'X5': [lamp],
        'X6': [dict(lamp, issue_id='V2', description='落地灯在两个镜头中颜色不一致。')],
        'O1': [dict(issue_id='V3', scope='within_shot', subcategory='presence_instability', description='Shot2路人凭空出现。',
                    shot_ids=['Shot2'], entities=[dict(entity_key='n1', role='subject')],
                    key_evidence=[dict(shot_id='Shot2', frame_id=2, entity_keys=[], observation='无人'),
                                  dict(shot_id='Shot2', frame_id=3, entity_keys=['n1'], observation='路人')],
                    confidence='medium')]}
    return dict(protocol='vl_vv_issue_discovery_v6_vv',
                checklist=[dict(item=item, status='checked', note='已检查。', issues=found.get(item, []),
                                earlier_issue_ids=[]) for item in common.checklist_items(CFG)],
                added_entities=[dict(entity_key='n1', name='路人', description='背景中的路人', frame_refs=[fr('Shot2', 3)])])


def vl_candidates():
    return detection.vl_canonical(vl_result(), v6_template(), base.ledger(), 'v6')[0]


def vv_candidates():
    return detection.vv_canonical(vv_result(), base.ledger(), 'v6')


def vl_rewrite():
    return dict(protocol='vl_vv_issue_review_v7_vl_rewrite',
                candidate_actions=[dict(candidate_id='L1', action='keep', reason='')],
                issues=[dict(source_candidate_ids=['L1'], subcategory='attribute',
                             description='Shot1男子穿深色有领衬衫，不是合同所述的蓝灰T恤。', shot_ids=['Shot1'],
                             requirement_quote=dict(source='contract', shot_id=None, quote=base.SHIRT),
                             template_row_ids=['EN:Character 1@Shot1'], frame_refs=[fr('Shot1', 2)],
                             entity_keys=['pb0001'], revision='unchanged', revision_note='')])


def vv_rewrite():
    return dict(protocol='vl_vv_issue_review_v7_vv_rewrite',
                candidate_actions=[dict(candidate_id='V1', action='merge', reason='V1与V2报告同一落地灯颜色变化。'),
                                   dict(candidate_id='V2', action='merge', reason='同上。'),
                                   dict(candidate_id='V3', action='keep', reason='')],
                issues=[dict(source_candidate_ids=['V1', 'V2'], scope='cross_shot', subcategory='object_identity',
                             description='落地灯在Shot1为白色，在Shot2为红色。', shot_ids=['Shot1', 'Shot2'],
                             frame_refs=[fr('Shot1', 1), fr('Shot2', 1)],
                             entities=[dict(entity_key='ge0001', role='subject'), dict(entity_key='pb0002', role='context')],
                             revision='clarified', revision_note='合并两个重复报告，统一颜色描述。'),
                        dict(source_candidate_ids=['V3'], scope='within_shot', subcategory='presence_instability',
                             description='Shot2中路人在f3凭空出现。', shot_ids=['Shot2'],
                             frame_refs=[fr('Shot2', 2), fr('Shot2', 3)], entities=[dict(entity_key='n1', role='subject')],
                             revision='unchanged', revision_note='')])


def vl_verdict():
    return dict(protocol='vl_vv_issue_review_v7_vl_verdict', verdicts=[dict(
        issue_id='L1', requirement_applies='人物描述适用于其出现的每个镜头。', verdict='confirmed',
        basis='requirement_violated', confidence='high',
        evidence=[dict(shot_id='Shot1', frame_id=2, role='supports', observation='深色衬衫')], assessment='衣服不符。')])


def vv_verdict():
    return dict(protocol='vl_vv_issue_review_v7_vv_verdict', verdicts=[
        dict(issue_id='V1+V2', comparison='同一房间的同一落地灯。', normal_cause='none', normal_cause_note='已查光照与视角。',
             verdict='confirmed', basis='inconsistency_confirmed', confidence='high',
             evidence=[dict(shot_id='Shot1', frame_id=1, role='supports', observation='白灯'),
                       dict(shot_id='Shot2', frame_id=1, role='supports', observation='红灯')], assessment='颜色变化。'),
        dict(issue_id='V3', comparison='同一镜头的连续画面。', normal_cause='none', normal_cause_note='无入画动作。',
             verdict='confirmed', basis='inconsistency_confirmed', confidence='medium',
             evidence=[dict(shot_id='Shot2', frame_id=3, role='supports', observation='路人'),
                       dict(shot_id='Shot2', frame_id=2, role='context', observation='无人')], assessment='凭空出现。')])


def schema_ok(value, path):
    import jsonschema
    jsonschema.validate(value, json.loads(Path(path).read_text()))


def rewrite_errors(response, branch):
    schema_ok(response, common.REVIEW_V7[branch]['rewrite']['schema'])
    candidates = vl_candidates() if branch == 'vl' else vv_candidates()[0]
    rows = {row['row_id']: row for row in v6_template()}
    return review.rewrite_errors(response, candidates, base.manifest(), branch,
                                 common.text_sources(base.contract(), base.TRANSITIONS), CFG,
                                 common.place_entity_ids(base.contract(), base.ledger()), rows)


def issues_of(branch):
    candidates = vl_candidates() if branch == 'vl' else vv_candidates()[0]
    rewrite = vl_rewrite() if branch == 'vl' else vv_rewrite()
    return review.rewritten_issues(rewrite, candidates, branch, {row['row_id']: row for row in v6_template()})


def verdict_errors(response, branch):
    schema_ok(response, common.REVIEW_V7[branch]['verdict']['schema'])
    return review.verdict_errors(response, issues_of(branch), base.manifest(), branch, CFG)


# --------------------------------------------------------------------------
# Files: config, schemas, prompts.
# --------------------------------------------------------------------------

ABSENCE_EDITS = [(
    """   absent), list only the presence item: the entity's other requirements
   cannot be judged, and one absence is reported once.""",
    """   absent), also list every other item of the row that needs the entity to be
   seen (an appearance, a position or an action), so each unmet requirement
   is reported; do not list an item that holds without the entity (for
   example, its face stays outside the image), or the description, which
   applies only where the entity appears. A relations row that needs an
   absent entity to be seen is violated as well.""")]
ABSENT_RULE = ('- absent items ("...: not visible in this shot."): satisfied when no frame\n'
               '  shows the entity, violated when any frame shows it. An entity that no frame\n'
               '  shows satisfies its absent item; do not mark the row not_verifiable for\n'
               '  that reason.\n')


# V-L detection v6 links issues by requirement ID (owner, 2026-11-04): the exact prompt edits.
REQUIREMENT_ID_EDITS = [
    ('requirements, each with an item_id):\n',
     'requirements). Every item has an item_id, its requirement ID, which is\n'
     'unique in the whole template (S<n> = the n-th shot):\n'),
    ('  are its episode-wide description (item_id "description"), its presence or\n'
     '  absence in this shot, and each requirement of this shot about it (item_id\n'
     '  = the requirement id, with expected and quantifier);\n',
     '  are its episode-wide description (S<n>-des-<entity>), its presence or\n'
     '  absence in this shot, and each requirement of this shot about it (the\n'
     "  contract's requirement id, with expected and quantifier);\n"),
    ('items "camera_view" and "camera_movement", the', 'items S<n>-cam-view and S<n>-cam-move, the'),
    ('item "style", the contract', 'item S<n>-sty, the contract'),
    ('item "transition", the required cut', 'item S<n>-cut, the required cut'),
    ('3. violated_items: the item_ids that the frames contradict (empty unless\n   status is violated).',
     '3. violated_items: the requirement IDs (item_ids) that the frames contradict\n   (empty unless status is violated).'),
    ('5. issue_ids: the issue(s) that report this row\'s violations; empty\n'
     '   otherwise. A transition, style or cross-shot row belongs to exactly one\n'
     '   issue; other rows may be violated by several independent failures, one\n'
     '   issue each.\n', ''),
    ('Every violated row is reported by at least one issue. One issue is one\n'
     'failed requirement: one requirement (or one entity attribute) that the video\n'
     'does not meet. When the same requirement fails in several shots, report ONE issue\n'
     'with one occurrence per violating shot. Do not merge independent failures\n'
     '(different entities, different attributes or different requirements) into\n'
     'one issue, and never report the same failure twice.',
     'Every violated requirement (every requirement ID in violated_items) is\n'
     'reported by at least one issue. One issue is one failed requirement: one\n'
     'requirement (or one entity attribute) that the video does not meet. When the\n'
     'same requirement fails in several shots, report ONE issue with one occurrence\n'
     'per violating shot. Do not merge independent failures (different entities,\n'
     'different attributes or different requirements) into one issue, and never\n'
     'report the same failure twice: a requirement is reported by exactly one\n'
     'issue, except an entity description or a camera view or movement, where\n'
     'independent failures of different attributes are separate issues. The runner\n'
     'derives from the occurrences which issues report each requirement.'),
    ('- subcategory: the V-L subcategory of the violated requirement (a transition\n  row is always shot_structure).',
     '- subcategory: the V-L subcategory of the violated requirement (a cut\n  requirement, S<n>-cut, is always shot_structure).'),
    ('- occurrences: one per violating shot: shot_id, the violated row_ids of that\n'
     '  shot (a cross-shot row counts for every shot it names), the frame_refs that\n'
     '  show the violation, observed (what the frames\n'
     '  show) and mismatch (exactly how observed contradicts expected).',
     '- occurrences: one per violating shot: shot_id, requirement_ids (the\n'
     '  violated requirement IDs of that shot that this issue reports, each listed\n'
     "  in its row's violated_items; a cross-shot requirement counts for every shot\n"
     '  it names), the frame_refs that show the violation, observed (what the\n'
     '  frames show) and mismatch (exactly how observed contradicts expected).'),
]
LINK_KEYS = ('issue_links', 'issue_links_note', 'multi_issue_item_kinds', 'multi_issue_item_kinds_note')


class ChainFiles(unittest.TestCase):
    def test_config_v2_is_config_v1_without_provenance(self):
        old, new = common.config(), CFG
        self.assertNotIn('provenance', new)
        self.assertEqual(set(new['rewrite']['actions']), {'keep', 'split', 'merge'})
        self.assertEqual(new['rewrite']['v_l_actions'], ['keep', 'split'])
        for key in old:
            if key not in ('protocol', 'note', 'provenance', 'scoring', 'contract_template'):
                self.assertEqual(old[key], new[key], key)
        self.assertEqual(old['contract_template'],
                         {key: value for key, value in new['contract_template'].items() if key not in LINK_KEYS})
        self.assertEqual(new['contract_template']['issue_links'], 'requirement_ids')  # owner, 2026-11-04
        self.assertEqual(new['contract_template']['multi_issue_item_kinds'], ['entity_description', 'camera', 'shot_text'])
        for key in ('rubric_version', 'base_deductions', 'reviewer_confidence_factors'):
            self.assertEqual(old['scoring'][key], new['scoring'][key])
        self.assertEqual(new['scoring']['base_deductions'], {'minor': 10, 'moderate': 25, 'major': 50, 'critical': 80})
        self.assertEqual(new['scoring']['uncertain_factor'], 0.25)  # owner, 2026-11-03

    def test_schemas_are_generated_and_carry_no_provenance_or_duplicates(self):
        for name, schema in builder.build().items():
            self.assertEqual((ROOT / 'schemas' / name).read_text(), builder.render(schema), name)
        vv = json.loads(common.DISCOVERY_V6['vv']['schema'].read_text())
        self.assertIn('added_entities', vv['required'])
        self.assertNotIn('entity_register', vv['properties'])
        self.assertNotIn('provenance', json.dumps(vv))
        for branch in common.BRANCHES:
            for call in ('rewrite', 'verdict'):
                self.assertNotIn('provenance', common.REVIEW_V7[branch][call]['schema'].read_text())
            self.assertNotIn('duplicate_of', common.SCORING_V6[branch]['schema'].read_text())
        rewrite = json.loads(common.REVIEW_V7['vv']['rewrite']['schema'].read_text())
        self.assertNotIn('verdict', rewrite['properties']['issues']['items']['properties'])
        old, new = (json.loads(path.read_text()) for path in (common.DISCOVERY['vl']['schema'], common.DISCOVERY_V6['vl']['schema']))
        for value in (old, new):
            value.pop('title')
            value['properties'].pop('protocol')
        # V-L detection v6 = v5 with requirement-ID links (owner, 2026-11-04): no issue_ids on rows, occurrences name
        # requirement_ids instead of row_ids.
        check = old['properties']['checks']['items']
        check['required'].remove('issue_ids')
        del check['properties']['issue_ids']
        occurrence = old['properties']['issues']['items']['properties']['occurrences']['items']
        occurrence['required'][occurrence['required'].index('row_ids')] = 'requirement_ids'
        occurrence['properties'] = {('requirement_ids' if key == 'row_ids' else key): value
                                    for key, value in occurrence['properties'].items()}
        self.assertEqual(old, new)

    def test_vv_detection_prompt_has_the_owner_sentence_and_no_provenance(self):
        vv = flat(common.render_prompt(common.DISCOVERY_V6['vv']['prompt'], common.CONFIG_V2_PATH))
        self.assertEqual(vv.count(SENTENCE), 1)
        for word in ('provenance', 'entity_register', 'prompt_unbound entity', 'unintentional', 'basis_type'):
            self.assertNotIn(word, vv)
        self.assertIn('part of that person', vv)
        # V-L detection v6 = v5 plus the absent-item rule (owner, 2026-11-02), the requirement-ID links (2026-11-04)
        # and each requirement an absence leaves unmet reported (owner, 2026-11-05).
        expected = common.DISCOVERY['vl']['prompt'].read_text()
        for old, new in REQUIREMENT_ID_EDITS + ABSENCE_EDITS:
            self.assertEqual(expected.count(old), 1, old)
            expected = expected.replace(old, new)
        v6 = common.DISCOVERY_V6['vl']['prompt'].read_text()
        self.assertEqual(v6.replace(ABSENT_RULE, ''), expected)
        self.assertNotIn('issue_ids', v6)
        self.assertNotIn('row_ids', v6)
        for path in (common.DISCOVERY_V6['vl']['prompt'], common.REVIEW_V7['vl']['rewrite']['prompt'],
                     common.REVIEW_V7['vl']['verdict']['prompt']):
            self.assertNotIn('ledger record fits', flat(path.read_text()))

    def test_review_and_scoring_prompts(self):
        definitions = common.placeholder_values(common.CONFIG_V2_PATH)['VL_VV_DEFINITIONS']
        for branch in common.BRANCHES:
            for call in ('rewrite', 'verdict'):
                text = common.render_prompt(common.REVIEW_V7[branch][call]['prompt'], common.CONFIG_V2_PATH)
                self.assertIn(definitions, text)
                self.assertNotIn('provenance', text)
                self.assertIsNone(re.search(r'\bcontinue\b', text))
            rewrite = flat(common.REVIEW_V7[branch]['rewrite']['prompt'].read_text())
            self.assertIn('Give no verdict', rewrite)
            # V-V merges repeats in call 1; V-L is merged by rule in detection (owner, 2026-11-05).
            self.assertIn('same span' if branch == 'vv' else 'V-L candidates are never merged', rewrite)
            verdict = flat(common.REVIEW_V7[branch]['verdict']['prompt'].read_text())
            self.assertIn('You see only these rewritten issues', verdict)
            scoring_text = common.render_prompt(common.SCORING_V6[branch]['prompt'], common.CONFIG_V2_PATH)
            self.assertNotIn('duplicate_of', scoring_text)
            self.assertNotIn('parent_issue_id', scoring_text)
            self.assertNotIn('"none"', scoring_text)
            self.assertIn('rate the severity the problem would have if it were real', flat(scoring_text))
            self.assertIn('rejected issues are not sent', flat(scoring_text))
            severity = json.loads(common.SCORING_V6[branch]['schema'].read_text())
            self.assertEqual(severity['properties']['assessments']['items']['properties']['severity']['enum'],
                             ['minor', 'moderate', 'major', 'critical'])
        # V-V-only wording stays out of V-L calls (owner, 2026-10-21).
        for call in ('rewrite', 'verdict'):
            self.assertNotIn('does not conflict with', common.REVIEW_V7['vl'][call]['prompt'].read_text())
        self.assertIn('does not conflict with', common.REVIEW_V7['vv']['verdict']['prompt'].read_text())

    def test_chain_v5_files_still_drive_chain_v5(self):
        self.assertEqual(common.CHAINS['v5']['discovery'], common.DISCOVERY)
        self.assertEqual(common.CHAINS['v5']['config'], common.CONFIG_PATH)
        self.assertIn('provenance', common.config())
        self.assertEqual(common.DEFAULT_CHAIN, 'v6')


# --------------------------------------------------------------------------
# Discovery v6.
# --------------------------------------------------------------------------

def vl_detection_errors(result):
    schema_ok(result, common.DISCOVERY_V6['vl']['schema'])
    return detection.vl_errors(result, v6_template(), base.ledger(), base.manifest(),
                               common.text_sources(base.contract(), base.TRANSITIONS), set(), CFG)


def vv_detection_errors(result):
    schema_ok(result, common.DISCOVERY_V6['vv']['schema'])
    return detection.vv_checklist_errors(result, base.ledger(), base.manifest(), base.contract(), CFG)


class RequirementLinks(unittest.TestCase):
    """V-L detection v6: issues name requirement IDs; the runner derives and checks the links (owner, 2026-11-04)."""

    def issue(self, iid, requirement_ids, shot='Shot1', subcategory='attribute'):
        return dict(issue_id=iid, subcategory=subcategory, summary='不符。',
                    requirement_quotes=[dict(source='contract', shot_id=None, quote=base.SHIRT)], expected='蓝灰T恤',
                    occurrences=[dict(shot_id=shot, requirement_ids=requirement_ids, frame_refs=[fr(shot, 2)],
                                      observed='深色衬衫', mismatch='不符')],
                    entity_keys=['pb0001'], confidence='high')

    def test_template_ids_are_unique_and_chain_v5_keeps_its_names(self):
        ids = [item['item_id'] for row in v6_template() for item in row['items']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn('S1-des-Character 1', ids)
        self.assertIn('S2-cut', ids)
        self.assertIn('description', [item['item_id'] for row in base.template() for item in row['items']])

    def test_valid_result_and_derived_records(self):
        result = vl_result()
        self.assertEqual(result['issues'][0]['occurrences'][0]['requirement_ids'], ['S1-des-Character 1', 'c11'])
        self.assertEqual(vl_detection_errors(result), [])
        issue = detection.vl_canonical(result, v6_template(), base.ledger(), 'v6')[0][0]
        detail = issue['v_l_detail']
        self.assertEqual(detail['requirement_ids'], ['S1-des-Character 1', 'c11'])
        self.assertEqual(detail['template_row_ids'], ['EN:Character 1@Shot1'])
        self.assertEqual(set(detail['occurrences'][0]), {'shot_id', 'row_ids', 'frame_refs', 'observed', 'mismatch'})
        self.assertEqual(detail['occurrences'][0]['row_ids'], ['EN:Character 1@Shot1'])

    def test_every_violated_requirement_is_reported(self):
        result = vl_result()
        result['issues'][0]['occurrences'][0]['requirement_ids'] = ['S1-des-Character 1']
        self.assertTrue(has(vl_detection_errors(result), 'requirement c11 is violated but no issue reports it'))

    def test_a_requirement_is_one_issue_but_a_description_may_have_several(self):
        result = vl_result()
        result['issues'].append(self.issue('L2', ['c11']))
        self.assertTrue(has(vl_detection_errors(result), "requirement c11 (EN:Character 1@Shot1) is reported by several "
                                                         "issues ['L1', 'L2']"))
        result = vl_result()
        result['issues'].append(self.issue('L2', ['S1-des-Character 1']))
        self.assertEqual(vl_detection_errors(result), [])

    def test_a_reported_requirement_is_violated_and_in_its_shot(self):
        result = vl_result()
        result['issues'].append(self.issue('L2', ['S2-des-Character 1'], shot='Shot1'))
        self.assertTrue(has(vl_detection_errors(result), 'requirement S2-des-Character 1 belongs to Shot2, not Shot1'))
        result = vl_result()
        result['issues'].append(self.issue('L2', ['S2-des-Character 1'], shot='Shot2'))
        self.assertTrue(has(vl_detection_errors(result), 'requirement S2-des-Character 1 is reported, but the check of its '
                                                         'row EN:Character 1@Shot2 does not list it in violated_items'))
        result = vl_result()
        result['issues'].append(self.issue('L2', ['S9-nope']))
        self.assertTrue(has(vl_detection_errors(result), "requirement_id 'S9-nope' is not an item_id"))

    def test_a_cut_requirement_is_shot_structure(self):
        result = vl_result()
        cut = next(check for check in result['checks'] if check['row_id'] == 'TR:Shot1->Shot2')
        cut.update(status='violated', violated_items=['S2-cut'])
        result['issues'].append(self.issue('L2', ['S2-cut'], shot='Shot2'))
        self.assertTrue(has(vl_detection_errors(result), 'requirement S2-cut is the cut at a boundary, so the subcategory '
                                                         'must be shot_structure'))


class DiscoveryV6(unittest.TestCase):
    def test_valid_vv_result_and_ledger_labels(self):
        self.assertEqual(vv_detection_errors(vv_result()), [])
        issues, entities = vv_candidates()
        common.require_records(dict(issues=issues, entities=entities), 'test', common.RECORDS_SCHEMA_V2)
        self.assertEqual({row['entity_key']: row['label'] for row in entities},
                         {'ge0001': 'unspecified', 'pb0002': 'specified', 'n1': 'unspecified'})
        self.assertEqual(detection.counts('vv', vv_result(), issues, 'v6')['added_entities'], 1)
        vl_issues, vl_entities = detection.vl_canonical(vl_result(), v6_template(), base.ledger(), 'v6')
        common.require_records(dict(issues=vl_issues, entities=vl_entities), 'test', common.RECORDS_SCHEMA_V2)
        self.assertEqual(vl_entities[0]['label'], 'specified')

    def test_added_entities_are_declared_used_and_keyed(self):
        result = vv_result()
        result['added_entities'].append(dict(entity_key='x7', name='椅子', description='椅子', frame_refs=[fr('Shot1', 0)]))
        errors = vv_detection_errors(result)
        self.assertTrue(has(errors, 'an added entity_key must be "n1", "n2"'))
        self.assertTrue(has(errors, 'added_entities x7: added entity is not used in any issue'))
        result = vv_result()
        result['added_entities'] = []
        self.assertTrue(has(vv_detection_errors(result), "unknown entity keys ['n1'] (use ledger global_entity_id values or "
                                                          'keys added in added_entities)'))

    def test_v6_payload_notes_drop_provenance(self):
        payload = detection.vv_checklist_payload(base.contract(), base.ledger(), [], base.manifest())
        self.assertNotIn('provenance', json.dumps(payload['input_notes']))
        old = detection.vv_payload(base.contract(), base.ledger(), [], base.manifest(), [], {})
        self.assertIn('entity provenance', old['input_notes'][1])


# --------------------------------------------------------------------------
# Review v7.
# --------------------------------------------------------------------------

class ReviewRewrite(unittest.TestCase):
    def test_valid_rewrites(self):
        self.assertEqual(rewrite_errors(vl_rewrite(), 'vl'), [])
        self.assertEqual(rewrite_errors(vv_rewrite(), 'vv'), [])

    def test_v_l_candidates_are_never_merged_by_the_verifier(self):
        def actions(branch):
            schema = json.loads(common.REVIEW_V7[branch]['rewrite']['schema'].read_text())
            return schema['properties']['candidate_actions']['items']['properties']['action']['enum']
        self.assertEqual(actions('vl'), ['keep', 'split'])
        self.assertEqual(actions('vv'), ['keep', 'split', 'merge'])
        candidates = vl_candidates()
        candidates.append(dict(copy.deepcopy(candidates[0]), issue_id='L2'))
        response = vl_rewrite()
        response['candidate_actions'].append(dict(candidate_id='L2', action='keep', reason=''))
        response['issues'][0]['source_candidate_ids'] = ['L1', 'L2']
        errors = review.rewrite_errors(response, candidates, base.manifest(), 'vl',
                                       common.text_sources(base.contract(), base.TRANSITIONS), CFG,
                                       common.place_entity_ids(base.contract(), base.ledger()),
                                       {row['row_id']: row for row in v6_template()})
        self.assertTrue(has(errors, 'V-L candidates are never merged'))
        self.assertFalse(has(errors, 'does not match the issues'))
        text = flat(common.render_prompt(common.REVIEW_V7['vl']['rewrite']['prompt'], common.CONFIG_V2_PATH))
        self.assertIn('V-L candidates are never merged', text)
        self.assertNotIn('- merge:', text)

    def test_runner_ids_trace_keep_merge_and_split(self):
        vv = issues_of('vv')
        self.assertEqual([row['issue_id'] for row in vv], ['V1+V2', 'V3'])
        self.assertEqual((vv[0]['merged'], vv[0]['split'], vv[1]['merged']), (True, False, False))
        self.assertEqual([row['candidate_id'] for row in vv[0]['original_descriptions']], ['V1', 'V2'])
        response = vv_rewrite()
        part = copy.deepcopy(response['issues'][0])
        response['issues'][0]['source_candidate_ids'] = ['V1']
        part.update(source_candidate_ids=['V2', 'V1'], subcategory='spatial_continuity', description='灯的位置也变了。')
        response['issues'].insert(1, part)
        response['candidate_actions'][0].update(action='split', reason='颜色与位置是两个问题，位置与V2重复。')
        self.assertEqual(rewrite_errors(response, 'vv'), [])
        ids = review.rewritten_ids(response, vv_candidates()[0])
        self.assertEqual(ids, ['V1', 'V1+V2', 'V3'])
        response['issues'][0]['source_candidate_ids'] = ['V1', 'V2']
        response['candidate_actions'][1].update(action='split')
        self.assertEqual(review.rewritten_ids(response, vv_candidates()[0])[:2], ['V1+V2.1', 'V1+V2.2'])

    def test_every_candidate_is_covered_and_actions_match(self):
        response = vv_rewrite()
        del response['issues'][1]
        response['candidate_actions'][0]['action'] = 'keep'
        response['candidate_actions'].pop()
        errors = rewrite_errors(response, 'vv')
        self.assertTrue(has(errors, 'candidate V3 is the source of no issue'))
        self.assertTrue(has(errors, "candidate_actions is missing candidates ['V3']"))
        self.assertTrue(has(errors, 'candidate V1: action keep does not match the issues'))
        response = vv_rewrite()
        response['candidate_actions'][0]['reason'] = ''
        response['issues'][0]['source_candidate_ids'] = ['V1', 'V9']
        errors = rewrite_errors(response, 'vv')
        self.assertTrue(has(errors, 'action merge needs a reason'))
        self.assertTrue(has(errors, "unknown source_candidate_ids ['V9']"))
        self.assertTrue(has(errors, 'candidate V2 is the source of no issue'))

    def test_merged_sources_share_a_dimension(self):
        response = vv_rewrite()
        response['issues'][0]['source_candidate_ids'] = ['V1', 'V2', 'V3']
        del response['issues'][1]
        response['candidate_actions'][2].update(action='merge', reason='同一问题')
        self.assertTrue(has(rewrite_errors(response, 'vv'), 'sources of different dimensions'))

    def test_issues_stay_inside_their_sources(self):
        response = vv_rewrite()
        response['issues'][0]['entities'].append(dict(entity_key='pb0001', role='context'))
        response['issues'][1].update(shot_ids=['Shot1'], frame_refs=[fr('Shot1', 2)])
        response['issues'][0]['scope'] = 'within_shot'
        errors = rewrite_errors(response, 'vv')
        self.assertTrue(has(errors, "entities ['pb0001'] are not entities of its sources"))
        self.assertTrue(has(errors, "shot_ids ['Shot1'] must be distinct shots of its sources ['Shot2']"))
        self.assertTrue(has(errors, 'an issue keeps the scope of its sources (cross_shot)'))
        response = vl_rewrite()
        issue = response['issues'][0]
        issue['requirement_quote']['quote'] = 'a red jacket'
        issue['template_row_ids'] = ['EN:Character 1@Shot2']
        issue['entity_keys'] = []
        issue['revision'] = 'clarified'
        errors = rewrite_errors(response, 'vl')
        self.assertTrue(has(errors, 'is not a literal quote of contract'))
        self.assertTrue(has(errors, "template_row_ids ['EN:Character 1@Shot2'] must be distinct rows of its sources"))
        self.assertTrue(has(errors, 'entity_keys is empty but subcategory attribute concerns an entity'))
        self.assertTrue(has(errors, 'revision clarified needs revision_note'))


def rule_candidate(iid, shot, rids, quote, subcategory='attribute', confidence='high'):
    row = f'EN:0@{shot}'
    return dict(issue_id=iid, branch='v_l', scope='v_l', subcategory=subcategory, description=f'{iid}描述',
                shot_ids=[shot], entity_refs=[dict(entity_key='pb0001', role='subject')],
                key_evidence=[dict(shot_id=shot, frame_id=1, entity_keys=['pb0001'], observation='o')],
                confidence=confidence, v_v_detail=None,
                v_l_detail=dict(requirement_quotes=[dict(source='contract', shot_id=None, quote=quote)], expected='e',
                                occurrences=[dict(shot_id=shot, row_ids=[row], frame_refs=[fr(shot, 1)], observed=f'{iid}见',
                                                  mismatch=f'{iid}不符')],
                                template_row_ids=[row], requirement_ids=list(rids)))


class RuleMergeVL(unittest.TestCase):
    def test_repeats_of_one_requirement_failure_are_merged_by_rule(self):
        issues = [rule_candidate('L1', 'Shot1', ['S1-des-0'], 'white robe'),
                  rule_candidate('L2', 'Shot1', ['S1-spa-1'], 'She stands.'),
                  rule_candidate('L3', 'Shot3', ['S3-des-0'], 'White  robe', confidence='medium'),
                  rule_candidate('L4', 'Shot1', ['S1-spa-1'], 'She stands.'),
                  rule_candidate('L5', 'Shot1', ['S1-spa-1'], 'She stands.', subcategory='spatial_orientation'),
                  rule_candidate('L6', 'Shot1', ['S1-spa-2'], 'She stands.')]
        no_ids = rule_candidate('L7', 'Shot2', [], 'x')
        del no_ids['v_l_detail']['requirement_ids']
        merged, merges = detection.rule_merge_vl(issues + [no_ids, copy.deepcopy(no_ids)])
        self.assertEqual([issue['issue_id'] for issue in merged], ['L1', 'L2', 'L5', 'L6', 'L7', 'L7'])
        robe, stands = merged[0], merged[1]
        self.assertEqual((robe['shot_ids'], robe['confidence']), (['Shot1', 'Shot3'], 'medium'))
        self.assertEqual(robe['v_l_detail']['requirement_ids'], ['S1-des-0', 'S3-des-0'])
        self.assertEqual(len(stands['v_l_detail']['occurrences']), 1)
        self.assertEqual(stands['v_l_detail']['occurrences'][0]['observed'], 'L2见；L4见')
        self.assertEqual(stands['description'], 'L2描述；L4描述')
        self.assertEqual([(m['issue_id'], m['merged_issue_ids']) for m in merges], [('L1', ['L1', 'L3']), ('L2', ['L2', 'L4'])])
        self.assertEqual(detection.rule_merge_vl(issues[:2]), (issues[:2], []))


class ReviewVerdict(unittest.TestCase):
    def test_valid_verdicts_and_units(self):
        self.assertEqual(verdict_errors(vl_verdict(), 'vl'), [])
        self.assertEqual(verdict_errors(vv_verdict(), 'vv'), [])
        units = (review.canonical_units_v7(issues_of('vl'), vl_verdict(), 'vl')
                 + review.canonical_units_v7(issues_of('vv'), vv_verdict(), 'vv'))
        common.require_records(dict(units=units), 'test', common.RECORDS_SCHEMA_V2)
        self.assertEqual(units[1]['source_candidate_ids'], ['V1', 'V2'])
        self.assertEqual(units[1]['entity_refs'][0], dict(entity_key='ge0001', role='subject'))
        self.assertNotIn('provenance', json.dumps(units))

    def test_second_call_sees_only_the_rewritten_issues(self):
        view = [review.verdict_view(issue, 'vv') for issue in issues_of('vv')]
        self.assertNotIn(LAMP_V1, json.dumps(view, ensure_ascii=False))
        self.assertEqual(set(view[0]), {'issue_id', 'scope', 'subcategory', 'description', 'shot_ids', 'frame_refs',
                                        'entities'})
        self.assertEqual(review.verdict_view(issues_of('vl')[0], 'vl')['template_rows'][0]['row_id'], 'EN:Character 1@Shot1')

    def test_verdict_gates(self):
        response = vv_verdict()
        first, second = response['verdicts']
        first['evidence'] = first['evidence'][:1]
        first['normal_cause'] = 'lighting_cause'
        second['evidence'].append(dict(shot_id='Shot1', frame_id=0, role='context', observation='x'))
        response['verdicts'].append(copy.deepcopy(second))
        errors = verdict_errors(response, 'vv')
        self.assertTrue(has(errors, 'confirmed needs normal_cause "none"'))
        self.assertTrue(has(errors, 'from at least two of its shots'))
        self.assertTrue(has(errors, "a within_shot issue cites only frames of its own shot (evidence cites ['Shot1'])"))
        self.assertTrue(has(errors, 'duplicate verdict'))
        response = vv_verdict()
        response['verdicts'][0].update(verdict='rejected', basis='normal_change', normal_cause='none')
        response['verdicts'].pop()
        errors = verdict_errors(response, 'vv')
        self.assertTrue(has(errors, 'basis normal_change needs the normal_cause'))
        self.assertTrue(has(errors, "Missing verdicts for issues ['V3']"))
        response = vl_verdict()
        row = response['verdicts'][0]
        row['evidence'][0]['role'] = 'context'
        errors = verdict_errors(response, 'vl')
        self.assertTrue(has(errors, 'confirmed needs at least one evidence frame'))
        row.update(verdict='rejected', basis='requirement_satisfied')
        self.assertTrue(has(verdict_errors(response, 'vl'), 'requirement_satisfied needs at least one evidence frame'))
        row.update(basis='inconsistency_confirmed')
        self.assertTrue(has(review.verdict_errors(response, issues_of('vl'), base.manifest(), 'vl', CFG),
                            'basis inconsistency_confirmed does not fit verdict rejected'))

    def test_the_verdict_call_schema_has_one_required_entry_per_issue(self):
        # Owner, 2026-11-05: no issue can be skipped, judged twice or invented.
        import jsonschema
        for branch, response in (('vl', vl_verdict()), ('vv', vv_verdict())):
            issues = issues_of(branch)
            base_schema = json.loads(Path(common.REVIEW_V7[branch]['verdict']['schema']).read_text())
            schema = review.verdict_schema(base_schema, issues)
            ids = [issue['issue_id'] for issue in issues]
            self.assertEqual(list(schema['properties']['verdicts']['properties']), ids)
            self.assertEqual(schema['properties']['verdicts']['required'], ids)
            self.assertNotIn('issue_id', schema['$defs']['verdict']['properties'])
            self.assertEqual(set(schema['$defs']['verdict']['properties']) | {'issue_id'},
                             set(base_schema['properties']['verdicts']['items']['properties']))
            keyed = review.keyed_verdicts(response)
            jsonschema.validate(keyed, schema)
            errors, listed = review.keyed_verdict_errors(keyed, issues, base.manifest(), branch, CFG)
            self.assertEqual((errors, listed), ([], response))
            jsonschema.validate(listed, base_schema)
            missing = copy.deepcopy(keyed)
            missing['verdicts'].pop(ids[-1])
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(missing, schema)
            extra = copy.deepcopy(keyed)
            extra['verdicts']['X9'] = copy.deepcopy(keyed['verdicts'][ids[0]])
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(extra, schema)
        with self.assertRaisesRegex(ValueError, 'distinct issue IDs'):
            review.verdict_schema(base_schema, issues_of('vv') * 2)


# --------------------------------------------------------------------------
# Scoring v6.
# --------------------------------------------------------------------------

def v6_unit(uid, scope, verdict='confirmed', confidence='high', subjects=(), context=()):
    row = base.unit(uid, scope, verdict, confidence)
    for key in ('parent_issue_id', 'original_description', 'split_reason'):
        row.pop(key)
    row.update(source_candidate_ids=[uid], original_descriptions=[dict(candidate_id=uid, description='问题')],
               rewrite_actions=[dict(candidate_id=uid, action='keep', reason='')], merged=False,
               frame_refs=[dict(shot_id='Shot1', frame_id=0)],
               entity_refs=[dict(entity_key=key, role='subject') for key in subjects]
               + [dict(entity_key=key, role='context') for key in context])
    return row


ENTITIES = [dict(entity_key=key, label=label, name=key) for key, label in
            (('pb0001', 'specified'), ('pb0002', 'specified'), ('ge0001', 'unspecified'), ('ge0002', 'unspecified'),
             ('n1', 'unspecified'))]


class ScoringV6(unittest.TestCase):
    def test_each_confirmed_or_uncertain_issue_deducts_on_its_own(self):
        units = [v6_unit('L1', 'v_l', subjects=['pb0001']), v6_unit('L2', 'v_l', verdict='rejected'),
                 v6_unit('V1', 'cross_shot', subjects=['ge0001']),
                 v6_unit('V2', 'cross_shot', confidence='medium', subjects=['pb0001']),
                 v6_unit('V3', 'cross_shot', subjects=['pb0001', 'n1'], context=['ge0002']),
                 v6_unit('V4', 'within_shot', confidence='low', subjects=['pb0002'], context=['ge0001']),
                 v6_unit('V5', 'within_shot', verdict='uncertain', confidence='low', subjects=['ge0002']),
                 v6_unit('V6', 'within_shot', subjects=[])]
        common.require_records(dict(units=units), 'test', common.RECORDS_SCHEMA_V2)
        self.assertEqual([unit['unit_id'] for unit in scoring.scored_units_v6(units)],
                         ['L1', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6'])  # the rejected L2 gets no severity call
        assessments = {'L1': 'major', 'V1': 'moderate', 'V2': 'major', 'V3': 'critical', 'V4': 'major',
                       'V5': 'major', 'V6': 'minor'}
        assessments = {uid: dict(unit_id=uid, severity=severity, reason='r') for uid, severity in assessments.items()}
        scores, stats, ledger, counts = scoring.materialize_v6(units, assessments, ENTITIES, CFG)
        cross = Decimal(100) * Decimal('0.75') * (1 - Decimal('0.375')) * Decimal('0.2')  # V1 25, V2 50x.75, V3 80
        within = Decimal(100) * (1 - Decimal('0.25')) * Decimal('0.9') * (1 - Decimal('0.125'))  # V4 50x.5, V6 10,
        self.assertEqual(scores['v_l'], 50.0)                                     # uncertain V5 50x.25
        self.assertEqual(scores['v_v']['cross_shot'], scoring.rounded(cross))
        self.assertEqual(scores['v_v']['within_shot'], scoring.rounded(within))
        self.assertEqual(scores['uec'], scoring.rounded((Decimal(50) + cross + within) / 3))
        self.assertEqual(stats['cross_shot'], dict(confirmed_issues=3, with_unspecified_subject=2, share=0.666667,
                                                   unit_ids_with_unspecified_subject=['V1', 'V3']))
        self.assertEqual(stats['within_shot']['with_unspecified_subject'], 0)  # context entities do not count;
        self.assertEqual(stats['total']['confirmed_issues'], 5)                # uncertain V5 is not counted
        self.assertEqual([row['entity_key'] for row in stats['unspecified_subject_entities']], ['ge0001', 'n1'])
        self.assertNotIn('v_v_unintentional', scores)
        self.assertNotIn('v_v_remainder', scores)
        self.assertEqual(counts['cross_shot']['confirmed_issues'], 3)
        self.assertEqual((counts['within_shot']['confirmed_issues'], counts['within_shot']['uncertain'],
                          counts['within_shot']['deducting_issues']), (2, 1, 3))
        self.assertEqual((counts['v_l']['rejected'], counts['v_l']['deducting_issues']), (1, 1))
        by_id = {row['unit_id']: row for row in ledger}
        self.assertEqual(by_id['V2']['adjusted_deduction'], 37.5)
        self.assertEqual((by_id['V5']['factor'], by_id['V5']['factor_basis'], by_id['V5']['adjusted_deduction']),
                         (0.25, 'uncertain verdict', 12.5))  # the verifier's confidence does not apply to uncertain
        self.assertEqual((by_id['L2']['severity'], by_id['L2']['adjusted_deduction'], by_id['L2']['reason']),
                         (None, 0.0, None))
        self.assertTrue(by_id['V5']['involves_unspecified_entity'])  # labelled, but not in the statistics
        self.assertIsNone(by_id['L1']['involves_unspecified_entity'])
        self.assertNotIn('duplicate_of', by_id['V1'])

    def test_the_severity_call_sees_only_confirmed_and_uncertain_units(self):
        units = [v6_unit('V1', 'cross_shot'), v6_unit('V2', 'within_shot', verdict='uncertain'),
                 v6_unit('V3', 'cross_shot', verdict='rejected')]
        for unit in units:
            unit['v_v_detail'] = dict(comparison='同一物体。')
        payload = scoring.scorer_input_v6('vv', dict(units=units, entities=[]))
        self.assertEqual([(row['unit_id'], row['verdict']) for row in payload['units']],
                         [('V1', 'confirmed'), ('V2', 'uncertain')])

    def test_an_uncertain_unit_without_a_severity_is_an_error(self):
        with self.assertRaisesRegex(ValueError, 'the uncertain unit needs a severity'):
            scoring.materialize_v6([v6_unit('V1', 'cross_shot', verdict='uncertain')], {}, ENTITIES, CFG)

    def test_no_confirmed_vv_gives_null_share(self):
        scores, stats, *_ = scoring.materialize_v6([v6_unit('L1', 'v_l')], {'L1': dict(severity='minor', reason='r')}, [],
                                                   CFG)
        self.assertEqual((scores['v_v']['overall'], scores['v_l']), (100.0, 90.0))
        self.assertIsNone(stats['total']['share'])

    def test_assessment_gates_have_no_duplicates(self):
        units = [v6_unit('V1', 'cross_shot'), v6_unit('V2', 'cross_shot', verdict='uncertain'),
                 v6_unit('V3', 'cross_shot', verdict='rejected')]
        base_values, _ = scoring.rubric(CFG)
        errors, _ = scoring.assessment_errors_v6({'assessments': [
            dict(unit_id='V1', severity='none', reason='r'), dict(unit_id='V2', severity='none', reason='r'),
            dict(unit_id='V3', severity='minor', reason='r')]}, units, base_values)
        self.assertTrue(has(errors, 'Confirmed unit V1 needs a severity'))
        self.assertTrue(has(errors, 'Uncertain unit V2 needs a severity'))
        self.assertTrue(has(errors, 'V3: a rejected unit is not scored'))

    def test_a_subject_without_a_label_is_an_error(self):
        with self.assertRaisesRegex(ValueError, 'has no entity record with a label'):
            scoring.materialize_v6([v6_unit('V1', 'cross_shot', subjects=['ge0099'])],
                                   {'V1': dict(severity='minor', reason='r')}, ENTITIES, CFG)


# --------------------------------------------------------------------------
# Offline end-to-end run of chain v6 with a fake model.
# --------------------------------------------------------------------------

class OfflineChainV6(unittest.TestCase):
    def test_detection_two_call_review_and_scoring_connect(self):
        responses = {'vl_vv_issue_discovery_v6_vl': vl_result(), 'vl_vv_issue_discovery_v6_vv': vv_result(),
                     'vl_vv_issue_review_v7_vl_rewrite': vl_rewrite(), 'vl_vv_issue_review_v7_vv_rewrite': vv_rewrite(),
                     'vl_vv_issue_review_v7_vl_verdict': review.keyed_verdicts(vl_verdict()),
                     'vl_vv_issue_review_v7_vv_verdict': review.keyed_verdicts(vv_verdict()),
                     'vl_vv_episode_scoring_v6_vl': {'protocol': 'vl_vv_episode_scoring_v6_vl', 'assessments': [
                         dict(unit_id='L1', severity='moderate', reason='衣服不符。')]},
                     'vl_vv_episode_scoring_v6_vv': {'protocol': 'vl_vv_episode_scoring_v6_vv', 'assessments': [
                         dict(unit_id='V1+V2', severity='major', reason='灯颜色变化。'),
                         dict(unit_id='V3', severity='minor', reason='路人闪现。')]}}
        stages = []

        def fake(folder, payload, images, timeout, **kwargs):
            stages.append(kwargs['stage'])
            return base.fake_repair_loop(responses)(folder, payload, images, timeout, **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = base.make_case(root)
            env = {'EECBENCH_CODEX_BACKEND': 'api', 'EECBENCH_API_MODEL': common.MODEL}
            with mock.patch.dict('os.environ', env), mock.patch.object(detection.repair_loop, 'call_with_repair', fake):
                for branch in common.BRANCHES:
                    # The checks format keeps the two-call V-L review (answers, the default, needs a v2 contract).
                    detection.run(case, root / 'out' / f'{branch}_detection', branch, allow_v1_contract=True,
                                  vl_format='checks')
                    review.run(case, root / 'out' / f'{branch}_detection/result.json', root / 'out' / f'{branch}_review',
                               branch, allow_v1_contract=True)
                result = scoring.run(root / 'out/vl_review/result.json', root / 'out/vv_review/result.json',
                                     root / 'out/episode_scoring')
            out = root / 'out'
            verdict_input = (out / 'vv_review/verdict_input.json').read_text()
            ledger_ids = {row['global_entity_id'] for part in ('prompt_bound', 'prompt_unbound')
                          for row in json.loads((case / 'episode_entities.json').read_text())[part]}
            inputs = {(branch, call): json.loads((out / f'{branch}_review/{call}_input.json').read_text())
                      for branch in common.BRANCHES for call in ('rewrite', 'verdict')}
            vv_review = json.loads((out / 'vv_review/result.json').read_text())
            run_state = json.loads((out / 'vv_review/run.json').read_text())
            keyed_schema = json.loads((out / 'vv_review/verdict_output.schema.json').read_text())
            prompts = [(out / 'vv_review' / name).is_file() for name in ('prompt_rendered_rewrite.txt',
                                                                          'prompt_rendered_verdict.txt')]
        items = common.checklist_items(CFG)  # V-V detection: one call per checklist item, W1 first (2026-11-09)
        self.assertEqual(stages[:4], ['VL detection', 'VL review rewrite', 'VL review verdict', 'V-V detection W1'])
        self.assertEqual(sorted(stages[3:3 + len(items)]), sorted(f'V-V detection {item}' for item in items))
        self.assertEqual(stages[3 + len(items):5 + len(items)], ['VV review rewrite', 'VV review verdict'])
        self.assertEqual(sorted(stages[5 + len(items):]), ['VL scoring', 'VV scoring'])
        self.assertNotIn('candidate_issues', json.loads(verdict_input))
        # Each verification call sees only the entity records its issues name (owner, 2026-11-03).
        for (branch, call), payload in inputs.items():
            issues = payload['candidate_issues'] if call == 'rewrite' else payload['issues']
            if branch == 'vl':
                named = {key for issue in issues for key in issue['entity_keys']}
            else:
                named = {ref['entity_key'] for issue in issues for ref in issue['entities']}
            listed = {row['global_entity_id'] for part in ('prompt_bound', 'prompt_unbound')
                      for row in payload['detector_ledger'][part]}
            self.assertEqual(listed, named & ledger_ids, (branch, call))
            self.assertLess(listed, ledger_ids, (branch, call))
            self.assertLessEqual({row['entity_key'] for row in payload['added_entities']}, named, (branch, call))
        self.assertEqual([row['entity_key'] for row in inputs['vv', 'verdict']['added_entities']], ['n1'])
        self.assertNotIn(LAMP_V1, verdict_input)
        self.assertTrue(all(prompts))
        self.assertEqual(keyed_schema['properties']['verdicts']['required'], ['V1+V2', 'V3'])
        self.assertEqual((vv_review['verdict_output_form'], run_state['verdict_output_form']),
                         ('keyed_by_issue_id', 'keyed_by_issue_id'))
        self.assertEqual(vv_review['model_output']['verdict'], vv_verdict())
        self.assertEqual((vv_review['protocol'], vv_review['calls']), ('vl_vv_issue_review_v7_vv',
                                                                      {'rewrite': 1, 'verdict': 1}))
        self.assertEqual(vv_review['counts']['candidate_actions'], {'keep': 1, 'split': 0, 'merge': 2})
        self.assertEqual(run_state['token_cost']['api_calls'], 2)
        self.assertEqual(result['protocol'], 'vl_vv_episode_scoring_v6')
        self.assertEqual(result['scores'], dict(v_l=75.0, v_v=dict(within_shot=92.5, cross_shot=50.0, overall=71.25),
                                                uec=72.5))
        self.assertEqual(result['consistency_issue_statistics']['total']['share'], 1.0)
        self.assertEqual([row['entity_key'] for row in result['consistency_issue_statistics']['unspecified_subject_entities']],
                         ['ge0001', 'n1'])


# --------------------------------------------------------------------------
# Pipeline and batch wiring.
# --------------------------------------------------------------------------

class Wiring(unittest.TestCase):
    def test_default_plan_passes_chain_v6_to_every_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = pipeline.build_plan(base.registry_case(root), root / 'run', 'from-registry')
        for stage in plan['stages']:
            self.assertEqual(stage['command'][stage['command'].index('--chain') + 1], 'v6')
        self.assertEqual(len(plan['review_prompt']), 5)  # four two-call prompts and the direct V-L verdict prompt
        self.assertIn(str(ROOT / 'prompts/vl_vv_issue_review_v7_vl_verdict_direct.txt'), plan['review_prompt'])
        sources = {str(path) for path in pipeline.chain_source_files('v6', 'v7')}
        self.assertIn(str(ROOT / 'configs/vl-vv-branch-v2.json'), sources)
        self.assertIn(str(ROOT / 'prompts/vl_vv_issue_review_v7_vv_verdict.txt'), sources)
        self.assertNotIn(str(ROOT / 'configs/vl-vv-branch-v1.json'), sources)

    def test_batch_runs_chain_v6_and_records_its_statistics(self):
        self.assertEqual(batch.resolve_review_protocol(None, 'v6', None), 'v7')
        self.assertEqual(batch.SCORING_PROTOCOLS['v7'], 'vl_vv_episode_scoring_v6')
        self.assertEqual(batch.resolve_contract_format(None, 'v6'), 'v2')
        # V-L format per directory (2026-11-05): answers for a new v6 directory, checks for an older one.
        self.assertEqual(batch.resolve_vl_format(None, 'v6'), 'answers')
        self.assertEqual(batch.resolve_vl_format({'discovery_protocol': 'v6'}, 'v6'), 'checks')
        self.assertEqual(batch.resolve_vl_format({'vl_format': 'answers_no_contract'}, 'v6'), 'answers_no_contract')
        self.assertIsNone(batch.resolve_vl_format(None, 'v5'))
        with self.assertRaisesRegex(ValueError, 'does not apply'):
            batch.resolve_review_protocol(None, 'v6', 'v6')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case, out = root / 'case', root / 'run'
            (case / 'entities').mkdir(parents=True)
            (case / 'entities/run.json').write_text(json.dumps({'shots': []}))
            for name in batch.EVALUATION_STAGES['branch']:
                (out / name).mkdir(parents=True)
                (out / name / 'run.json').write_text(json.dumps({'status': 'success'}))
            (out / 'run.json').write_text(json.dumps({'status': 'success', 'case': str(case)}))
            (out / 'episode_scoring/result.json').write_text(json.dumps(dict(
                status='success', protocol='vl_vv_episode_scoring_v6', counts={},
                scores=dict(v_l=90.0, v_v=dict(within_shot=100.0, cross_shot=50.0, overall=75.0), uec=80.0),
                consistency_issue_statistics=dict(total=dict(share=1.0)))))
            self.assertTrue(batch.valid_success({'output_dir': str(out)}, batch.SCORING_PROTOCOLS['v7']))
            self.assertFalse(batch.valid_success({'output_dir': str(out)}, batch.SCORING_PROTOCOLS['v6']))
            task = dict(generation_priority=1, episode_id='e', model_id='m', model_name='M', variant='v')
            record = batch.score_record(task, out)
        self.assertEqual(record['scores']['uec'], 80.0)
        self.assertNotIn('v_v_unintentional', record['scores'])
        self.assertNotIn('v_v_issue_statistics', record)
        self.assertEqual(record['consistency_issue_statistics'], dict(total=dict(share=1.0)))


# --------------------------------------------------------------------------
# Q11: clustering collection rule.
# --------------------------------------------------------------------------

class ClusteringCollectionRule(unittest.TestCase):
    def test_confirmed_wording_replaces_the_separability_condition(self):
        text = flat((ROOT / 'skills/wedetect-shot-entities/review_prompt.txt').read_text())
        self.assertIn('Keep clearly visible objects as separate nodes by default. Two cups on a table are two entities.',
                      text)
        self.assertIn('Exception: use ONE collection node for a large number of items of the same kind gathered '
                      'together, such as a basket of oranges or a bunch of pens in a holder. Merge them even when every '
                      'item is clearly visible, because the condition is the number and kind of the items, not how '
                      'visible each one is. There is no fixed count, but a few items are not a large number. Separate '
                      'groups stay separate: two baskets of oranges are two nodes.', text)
        for removed in ('Use ONE collection node only when', 'meaningful individual separability',
                        'A dense pile/bundle is different from a few clear individual objects'):
            self.assertNotIn(removed, text)
        self.assertIn('Items a person wears or carries are part of that person', text)


# --------------------------------------------------------------------------
# Q12: several local entities bound to one contract entity.
# --------------------------------------------------------------------------

def binding_payload():
    raw = dict(shot_id='S', entities=[dict(entity_id=eid, name='glass', candidate_ids=[cid]) for eid, cid in
                                      (('e1', 'f0:d1'), ('e2', 'f1:d2'))], rejected_detections=[])
    frames = [dict(frame_id=i, image_size=[100, 100], detections=[]) for i in range(3)]
    frames[0]['detections'].append(dict(candidate_id='f0:d1', name='glass', box_xyxy=[1, 1, 10, 10], score=.5))
    frames[1]['detections'].append(dict(candidate_id='f1:d2', name='glass', box_xyxy=[20, 1, 30, 10], score=.5))
    payload = dict(shot_id='S', frames=frames, candidate_filter={})
    result = wedetect.validate_result(raw, payload)
    own = dict(entities=result['entities'], prompt_entities=[dict(prompt_entity_id='0', name='Three glasses', expectation='required')])
    binding = dict(bindings=[dict(entity_id=eid, status='bound', prompt_entity_id='0', candidate_prompt_entity_ids=[],
                                  witness_frame_ids=[frame], reason='one of the three glasses')
                             for eid, frame in (('e1', 0), ('e2', 1))],
                   queries=[dict(prompt_entity_id='0', detection_query='glass.')])
    return raw, payload, result, own, binding


class SeveralLocalsPerContractEntity(unittest.TestCase):
    def test_binding_v2_keeps_several_members_v1_normalizes(self):
        _, _, _, own, binding = binding_payload()
        errors, kept = recovery.binding_errors(binding, own, 'v2')
        self.assertEqual(errors, [])
        self.assertEqual([row['status'] for row in kept['bindings']], ['bound', 'bound'])
        errors, normalized = recovery.binding_errors(binding, own, 'v1')
        self.assertEqual(errors, [])
        self.assertEqual(sorted(row['status'] for row in normalized['bindings']), ['bound', 'unbound'])
        with self.assertRaisesRegex(ValueError, 'Unknown binding protocol'):
            recovery.binding_errors(binding, own, 'v3')

    def test_binding_prompt_v2_differs_only_in_the_group_rule(self):
        old = recovery.BINDING_PROMPTS['v1'].read_text()
        new = recovery.BINDING_PROMPTS['v2'].read_text()
        added = ('Several detected entities may be bound to the same prompt entity when its name or description states '
                 'several items or members (for example "Three glasses" or "Helpers: a group of several men"): bind each '
                 'detected member to it. Otherwise at most')
        self.assertEqual(new.replace(added, 'At most'), old)

    def test_coverage_uses_all_bound_members(self):
        _, _, _, own, binding = binding_payload()
        rows = recovery.coverage(own, binding, [dict(frame_id=i) for i in range(3)])
        self.assertEqual((rows[0]['entity_ids'], rows[0]['observed_frame_ids'], rows[0]['missing_detection_frame_ids']),
                         (['e1', 'e2'], [0, 1], [2]))

    def test_recovered_box_of_a_group_becomes_a_new_bound_local_entity(self):
        raw, payload, result, own, binding = binding_payload()
        rows = recovery.coverage(own, binding, [dict(frame_id=i) for i in range(3)])
        new = [dict(frame_id=2, detections=[dict(candidate_id='f2:gd1', name='glass', box_xyxy=[40, 1, 50, 10], score=.8,
                                                 prompt_entity_id='0', detector='grounding_dino')])]
        out, _, _, final = recovery.materialize_grounding(result, payload, own, new, binding, rows)
        self.assertEqual([e['entity_id'] for e in out['entities']], ['e1', 'e2', 'e3'])
        self.assertIsNone(out['entities'][0]['observations'][2]['box_xyxy'])
        self.assertEqual(out['entities'][2]['observations'][2]['box_xyxy'], [40, 1, 50, 10])
        self.assertEqual([(row['entity_id'], row['prompt_entity_id']) for row in final['bindings']],
                         [('e1', '0'), ('e2', '0'), ('e3', '0')])
        recovery.validate_binding(final, dict(own, entities=out['entities']), 'v2')

    def test_ledger_keeps_several_locals_under_one_specified_entity(self):
        reg = matching.registry()
        local = [matching.occurrence('Shot1', 'e1', 'bound', 'Character 1', 'man'),
                 matching.occurrence('Shot1', 'e3', 'bound', 'Character 1', 'man'),
                 matching.occurrence('Shot2', 'e1', 'bound', 'Character 1', 'man'),
                 matching.occurrence('Shot2', 'e2', 'unbound', name='lamp')]
        ptag, utag = frontend.match_v2_tags(reg, local)
        raw = dict(assignments=[matching.assignment(['U1'])])
        self.assertEqual(frontend.match_v2_errors(raw, local, ptag, utag), [])
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp)
            for name in ('raw_manifest.json', 'prompt_registry.json', 'contract.json'):
                (case / name).write_text('{}')
            (case / 'shot_prompt_recovery').mkdir()
            (case / 'shot_prompt_recovery/results.json').write_text('{}')
            for shot in ('Shot1', 'Shot2'):
                folder = case / 'shot_prompt_recovery/entities/shots' / shot
                folder.mkdir(parents=True)
                for name in ('entities.json', 'input.json'):
                    (folder / name).write_text('{}')
            ledger = frontend.build_episode_entities_v2(case, raw, [dict(shot_id='Shot1'), dict(shot_id='Shot2')], reg,
                                                        local, ptag, utag)
            compat = json.loads((case / 'global_entities/global_entities.json').read_text())
        man = ledger['prompt_bound'][0]
        self.assertEqual([(o['shot_id'], o['local_entity_id']) for o in man['occurrences']],
                         [('Shot1', 'e1'), ('Shot1', 'e3'), ('Shot2', 'e1')])
        self.assertEqual(compat['entities'][0]['observed_shot_ids'], ['Shot1', 'Shot2'])
        # Downstream readers: detector frames per shot are the union over the entity's occurrences in that shot.
        ledger['prompt_bound'][0]['occurrences'][1]['boxes'] = [dict(frame_id=5, box_xyxy=[1, 1, 2, 2])]
        ledger['prompt_bound'][0]['occurrences'][0]['boxes'] = ledger['prompt_bound'][0]['occurrences'][0]['boxes'][:2]
        frames = detection.detected_frames(ledger)
        self.assertEqual(frames[('pb0001', 'Shot1')], {0, 1, 5})
        self.assertEqual(frontend.schedule_fields(reg, 'Character 1', local[:2])[0]['observed_frame_ids'],
                         list(range(6)) * 2)

    def test_appearance_ids_stay_unique(self):
        import gs_entity_appearance as appearance
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / 'case'
            case.mkdir()
            frame = case / 'f0.png'
            Image.new('RGB', (64, 64)).save(frame)
            digest = hashlib.sha256(frame.read_bytes()).hexdigest()
            (case / 'raw_manifest.json').write_text(json.dumps(dict(shots=[dict(shot_id='Shot1', frames=[
                dict(frame_id=0, path=str(frame), sha256=digest, timestamp_sec=0.0)])])))
            (case / 'narrative.json').write_text('{}')
            folder = case / 'entities/shots/Shot1'
            folder.mkdir(parents=True)
            (folder / 'input.json').write_text(json.dumps(dict(frames=[dict(frame_id=0, detections=[
                dict(candidate_id='a', box_xyxy=[1, 1, 20, 20]), dict(candidate_id='b', box_xyxy=[30, 30, 60, 60])])])))
            local = [dict(shot_id='Shot1', local_entity_id=eid, name='glass', observations=[dict(
                frame_id=0, box_xyxy=box, box_candidate_id=cid, candidate_ids=[cid], exist=True)])
                for eid, cid, box in (('e1', 'a', [1, 1, 20, 20]), ('e2', 'b', [30, 30, 60, 60]))]
            registry = dict(source_hashes={}, counts={}, entities=[
                dict(global_entity_id='pb0001', name='glasses', scene_id='episode', observed_shot_ids=['Shot1'],
                     appearances=local),
                dict(global_entity_id='ge0001', name='glass', scene_id='episode', observed_shot_ids=['Shot1'],
                     appearances=local[:1])])
            (case / 'global_entities').mkdir()
            (case / 'global_entities/global_entities.json').write_text(json.dumps(registry))
            with mock.patch('builtins.print'):
                appearance.prepare(case, case / 'dino/canonical')
            ids = {eid: [row['appearance_id'] for row in json.loads(
                (case / f'dino/canonical/entities/{eid}/input.json').read_text())['appearances']]
                for eid in ('pb0001', 'ge0001')}
        self.assertEqual(ids, {'pb0001': ['Shot1_e1_f0', 'Shot1_e2_f0'], 'ge0001': ['Shot1_f0']})


if __name__ == '__main__':
    unittest.main()
