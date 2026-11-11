#!/usr/bin/env python3
"""Static contract tests for the standalone detector-only policy."""

import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DETECTOR_POLICY = (
    REPOSITORY_ROOT
    / ".agents"
    / "skills"
    / "ensemble-shot-entity-detection"
    / "references"
    / "detector-protocol.md"
)
SCRIPTS_DIR = REPOSITORY_ROOT / "EECBench" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ensemble_shot_entity_detection as ENSEMBLE  # noqa: E402


class DetectorPolicyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = DETECTOR_POLICY.read_text(encoding="utf-8")
        cls.compact_policy = " ".join(cls.policy.split())

    def test_policy_version_is_v04(self):
        expected_version = "single_shot_detector_three_pass_coverage_v0.4"
        self.assertIn(
            f"Policy version: `{expected_version}`.",
            self.policy,
        )
        self.assertEqual(ENSEMBLE.DETECTOR_POLICY_VERSION, expected_version)

    def test_scope_audit_relocalizes_before_checking_inside_and_perimeter(self):
        for clause in (
            "candidate-boundary and perimeter scope audit",
            "original pixels without trusting its provisional box",
            "narrow perimeter immediately outside it",
            "Confirm the scope on a second usable frame when one exists",
            "separately localizable neighboring physical object",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, self.compact_policy)

    def test_scope_audit_requires_positive_separation_evidence(self):
        for clause in (
            "own coherent boundary in at least two usable frames",
            "at least one scope-separation cue",
            "presumed function alone is not evidence of a separate object",
            "background support alone does not make heterogeneous neighbors one collection",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, self.compact_policy)

    def test_scope_audit_does_not_force_oversegmentation_or_hallucination(self):
        for clause in (
            "scope-completeness audit, not an instruction to decompose every group",
            "Keep homogeneous repeated members, ordinary integrated parts, and positively coupled compact assemblies at their existing scope",
            "Never emit both a broad proposal and a nested proposal for the same physical content",
            "Do not turn a low-contrast patch, shadow, illumination boundary, reflection, texture, depicted content, compression artifact, or off-frame inference into an entity",
            "uncertainty flag instead of inventing a second object",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, self.compact_policy)

    def test_final_box_audit_repeats_boundary_closure(self):
        for clause in (
            "repeat boundary closure for every scope-audited proposal",
            "contains all and only its intended physical content",
            "neither absorb a separately bounded heterogeneous neighbor nor copy the neighbor's footprint",
            "use `uncertain` with a null box rather than copying a stale or borrowed box",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, self.compact_policy)


if __name__ == "__main__":
    unittest.main()
