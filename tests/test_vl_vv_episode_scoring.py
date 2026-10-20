"""Focused scoring invariants independent of the Luna transport."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_vl_vv_episode_scoring as scoring


def issue(iid, verdict='confirmed', confidence='high'):
    return dict(issue_id=iid, review=dict(issue_id=iid, verdict=verdict, confidence=confidence))


class ScoringInvariants(unittest.TestCase):
    def test_distinct_events_compound_but_duplicates_do_not(self):
        rows = [('v_l', issue('a')), ('v_l', issue('b')),
                ('v_l', issue('c')), ('cross_shot', issue('d', confidence='medium'))]
        response = dict(protocol=scoring.PROTOCOL, assessments=[
            dict(issue_id='a', severity='moderate', duplicate_of=None, reason='a'),
            dict(issue_id='b', severity='moderate', duplicate_of='a', reason='same event'),
            dict(issue_id='c', severity='moderate', duplicate_of=None, reason='distinct event'),
            dict(issue_id='d', severity='major', duplicate_of=None, reason='d')])
        assessments = scoring.validate_assessments(response, rows)
        scores, ledger, events, counts = scoring.materialize_scores(rows, assessments)
        self.assertEqual(scores, dict(v_l=56.25,
                                      v_v=dict(within_shot=100.0, cross_shot=62.5, overall=81.25)))
        self.assertEqual(counts['v_l']['unique_confirmed_events'], 2)
        self.assertEqual([event['issue_ids'] for event in events if event['bucket'] == 'v_l'],
                         [['a', 'b'], ['c']])
        self.assertEqual(ledger[-1]['adjusted_deduction'], 37.5)

    def test_v2_penalty_scale_and_confidence_are_applied_separately(self):
        rows = [('v_l', issue('minor')),
                ('v_l', issue('moderate', confidence='medium')),
                ('v_l', issue('major', confidence='low')),
                ('v_l', issue('critical'))]
        response = dict(protocol=scoring.PROTOCOL, assessments=[
            dict(issue_id='minor', severity='minor', duplicate_of=None, reason='minor'),
            dict(issue_id='moderate', severity='moderate', duplicate_of=None, reason='moderate'),
            dict(issue_id='major', severity='major', duplicate_of=None, reason='major'),
            dict(issue_id='critical', severity='critical', duplicate_of=None, reason='critical')])
        assessments = scoring.validate_assessments(response, rows)
        scores, ledger, _, _ = scoring.materialize_scores(rows, assessments)
        self.assertEqual([row['adjusted_deduction'] for row in ledger], [10.0, 18.75, 25.0, 80.0])
        self.assertEqual(scores['v_l'], 10.97)

    def test_uncertain_and_rejected_are_reported_without_penalty(self):
        rows = [('v_l', issue('u', 'uncertain')), ('within_shot', issue('r', 'rejected'))]
        response = dict(protocol=scoring.PROTOCOL, assessments=[
            dict(issue_id='u', severity='none', duplicate_of=None, reason='unclear'),
            dict(issue_id='r', severity='none', duplicate_of=None, reason='refuted')])
        scores, _, events, counts = scoring.materialize_scores(
            rows, scoring.validate_assessments(response, rows))
        self.assertEqual(scores['v_l'], 100.0)
        self.assertEqual(scores['v_v']['overall'], 100.0)
        self.assertEqual(events, [])
        self.assertEqual(counts['v_l']['uncertain'], 1)
        self.assertEqual(counts['within_shot']['rejected'], 1)

    def test_invalid_output_cannot_change_review_verdict_or_issue_population(self):
        rows = [('v_l', issue('a')), ('within_shot', issue('b', 'uncertain'))]
        with self.assertRaises(ValueError):
            scoring.validate_assessments(dict(protocol=scoring.PROTOCOL, assessments=[
                dict(issue_id='a', severity='major', duplicate_of=None, reason='a')]), rows)
        with self.assertRaises(ValueError):
            scoring.validate_assessments(dict(protocol=scoring.PROTOCOL, assessments=[
                dict(issue_id='a', severity='major', duplicate_of=None, reason='a'),
                dict(issue_id='b', severity='minor', duplicate_of=None, reason='b')]), rows)
        with self.assertRaises(ValueError):
            scoring.validate_assessments(dict(protocol=scoring.PROTOCOL, assessments=[
                dict(issue_id='a', severity='major', duplicate_of='b', reason='a'),
                dict(issue_id='b', severity='none', duplicate_of=None, reason='b')]), rows)


if __name__ == '__main__':
    unittest.main()
