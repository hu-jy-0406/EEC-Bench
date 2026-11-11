"""Lossless input representation and hostile references, without models or images."""
import copy
import importlib.util
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[1] / "scripts/verifier_input_normalization.py"
SPEC = importlib.util.spec_from_file_location("verifier_input_normalization_tested", PATH)
N = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(N)


def fixture():
    box = [0.0, 0.2, 0.7, 1.0]
    frames = [{"frame_id": i, "status": "visible", "bbox_xyxy_normalized": box.copy()}
              for i in (0, 4, 8)]
    proposals = [{"anonymous_proposal_id": key, "proposed_name": "same text", "frame_presence": copy.deepcopy(frames)}
                 for key in ("p1", "p2", "p3")]
    return {"targets": [{"cluster_id": "c1", "proposals": proposals[:2], "canonical_name": "same name"},
                        {"cluster_id": "c2", "proposals": proposals[2:], "canonical_name": "same name"}],
            "cluster_index": [{"cluster_id": key, "canonical_name": "same name"} for key in ("c1", "c2", "index_only")],
            N.PAIRS: [{"cluster_id_a": "c1", "cluster_id_b": "index_only", "trigger_bases": ["test"],
                       "coarse_locator_jaccard": 0.25, "box_redundancy_challenges": [{"threshold": 1.0}]}],
            N.SPLITS: [{"cluster_id": "c1", "cluster_proposal_ids": ["p1", "p2"],
                        "thresholds": {"maximum_iou": 0.35}, "effect": "verbatim!",
                        "divergent_proposal_pairs": [{"proposal_id_a": "p1", "proposal_id_b": "p2",
                            "frame_evidence": [{"frame_id": 0, "bbox_a_xyxy_normalized": box.copy(),
                                                "bbox_b_xyxy_normalized": box.copy(), "iou": 0.2}]}]}]}


def bbox_entry(encoded):
    return encoded["split_questions"][0]["proposal_pairs"][0]["frame_evidence"][0]


class VerifierInputNormalizationTests(unittest.TestCase):
    def assert_roundtrip(self, view):
        before = copy.deepcopy(view)
        encoded = N.encode_verification_view(view)
        decoded = N.decode_verification_view(encoded)
        self.assertEqual(N.canonical_bytes(decoded), N.canonical_bytes(before))
        self.assertEqual(N.canonical_bytes(view), N.canonical_bytes(before))
        self.assertTrue(N.audit_verification_view(view, encoded)["roundtrip_valid"])
        return encoded

    def test_full_inventory_pair_metadata_and_non_target_index_preserved(self):
        view = fixture()
        encoded = self.assert_roundtrip(view)
        self.assertEqual(len(encoded["proposals"]), 3)
        self.assertEqual([x["proposal_ids"] for x in encoded["scopes"]], [["p1", "p2"], ["p3"]])
        self.assertEqual(encoded["record"]["cluster_index"], view["cluster_index"])
        self.assertNotIn("proposal_ids", encoded["record"]["cluster_index"][-1])
        self.assertEqual(encoded["pair_questions"][0]["record"], view[N.PAIRS][0])
        self.assertEqual(encoded["split_questions"][0]["record"]["thresholds"], view[N.SPLITS][0]["thresholds"])

    def test_only_consecutive_same_proposal_all_field_equal_rows_aggregate(self):
        view = fixture()
        rows = view["targets"][0]["proposals"][0]["frame_presence"]
        rows.extend([copy.deepcopy(rows[0]), copy.deepcopy(rows[0])])
        rows[1]["status"] = "uncertain"
        rows[3]["extra"] = None
        encoded = self.assert_roundtrip(view)
        self.assertEqual(len(encoded["proposals"][0]["frame_table"]["runs"]), 5)
        self.assertEqual(len(encoded["proposals"][1]["frame_table"]["runs"]), 1)
        self.assertEqual(len(encoded["proposals"][2]["frame_table"]["runs"]), 1)

    def test_all_unknown_fields_verbatim_and_no_mutation(self):
        view = fixture()
        values = [None, [], {}, True, 1, 1.0, -0.0, "a\nβ\\literal"]
        destinations = [view, view["targets"][0], view["targets"][0]["proposals"][0],
                        view["targets"][0]["proposals"][0]["frame_presence"][0],
                        view[N.SPLITS][0], view[N.SPLITS][0]["divergent_proposal_pairs"][0],
                        view[N.SPLITS][0]["divergent_proposal_pairs"][0]["frame_evidence"][0]]
        for destination in destinations:
            destination["future_field"] = copy.deepcopy(values)
        self.assert_roundtrip(view)

    def test_missing_null_empty_presence_and_missing_optional_sections_distinct(self):
        view = fixture()
        view.pop(N.SPLITS)
        view.pop(N.PAIRS)
        proposals = [*view["targets"][0]["proposals"], *view["targets"][1]["proposals"]]
        proposals[0].pop("frame_presence")
        proposals[1]["frame_presence"] = None
        proposals[2]["frame_presence"] = []
        encoded = self.assert_roundtrip(view)
        self.assertNotIn("frame_presence", encoded["proposals"][0]["record"])
        self.assertIsNone(encoded["proposals"][1]["record"]["frame_presence"])
        self.assertEqual(encoded["proposals"][2]["frame_table"], {"count": 0, "runs": []})
        self.assertNotIn("pair_questions", encoded)
        self.assertNotIn("split_questions", encoded)

    def test_number_types_boolean_and_signed_zero_not_collapsed(self):
        view = fixture()
        rows = view["targets"][0]["proposals"][0]["frame_presence"]
        rows.clear()
        rows.extend({"frame_id": i, "value": value} for i, value in enumerate([True, 1, 1.0, 0.0, -0.0]))
        encoded = self.assert_roundtrip(view)
        self.assertEqual(len(encoded["proposals"][0]["frame_table"]["runs"]), 5)

    def test_exact_split_reference_and_type_or_value_mismatch_literal(self):
        for replacement in ([0, 0.2, 0.7, 1.0], [-0.0, 0.2, 0.7, 1.0], [0.0000001, 0.2, 0.7, 1.0], None):
            with self.subTest(replacement=replacement):
                view = fixture()
                view[N.SPLITS][0]["divergent_proposal_pairs"][0]["frame_evidence"][0]["bbox_a_xyxy_normalized"] = replacement
                encoded = self.assert_roundtrip(view)
                self.assertEqual(bbox_entry(encoded)["bbox_a"], {"literal": replacement})
                self.assertIn("ref", bbox_entry(encoded)["bbox_b"])

    def test_missing_bbox_stays_missing_and_explicit_null_stays_null(self):
        view = fixture()
        evidence = view[N.SPLITS][0]["divergent_proposal_pairs"][0]["frame_evidence"][0]
        evidence.pop("bbox_a_xyxy_normalized")
        evidence["bbox_b_xyxy_normalized"] = None
        encoded = self.assert_roundtrip(view)
        self.assertNotIn("bbox_a", bbox_entry(encoded))
        self.assertEqual(bbox_entry(encoded)["bbox_b"], {"literal": None})

    def test_duplicate_frame_id_or_unknown_frame_is_literal_not_first_match(self):
        for duplicate in (True, False):
            with self.subTest(duplicate=duplicate):
                view = fixture()
                if duplicate:
                    rows = view["targets"][0]["proposals"][0]["frame_presence"]
                    rows.append(copy.deepcopy(rows[0]))
                else:
                    view[N.SPLITS][0]["divergent_proposal_pairs"][0]["frame_evidence"][0]["frame_id"] = 99
                encoded = self.assert_roundtrip(view)
                self.assertIn("literal", bbox_entry(encoded)["bbox_a"])

    def test_decoder_rejects_wrong_endpoint_even_identical_box_and_frame(self):
        for key in ("p2", "p3", "missing"):
            encoded = N.encode_verification_view(fixture())
            bbox_entry(encoded)["bbox_a"]["ref"]["proposal_id"] = key
            with self.subTest(key=key), self.assertRaises(ValueError):
                N.decode_verification_view(encoded)

    def test_decoder_rejects_index_alias_wrong_frame_and_out_of_range(self):
        for index in (True, 0.0, -1, 1, 100):
            encoded = N.encode_verification_view(fixture())
            bbox_entry(encoded)["bbox_a"]["ref"]["frame_presence_index"] = index
            with self.subTest(index=index), self.assertRaises(ValueError):
                N.decode_verification_view(encoded)

    def test_decoder_rejects_ref_literal_mixture_and_extra_container_fields(self):
        for mode in ("both", "ref_extra", "top_extra", "bbox_extra"):
            encoded = N.encode_verification_view(fixture())
            bbox = bbox_entry(encoded)["bbox_a"]
            if mode == "both":
                bbox["literal"] = None
            elif mode == "ref_extra":
                bbox["ref"]["extra"] = None
            elif mode == "top_extra":
                encoded["extra"] = None
            else:
                bbox["extra"] = None
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                N.decode_verification_view(encoded)

    def test_decoder_checks_ownership_orphans_duplicates_and_order(self):
        for mode in ("orphan", "duplicate", "missing", "reorder", "duplicate_table"):
            encoded = N.encode_verification_view(fixture())
            keys = encoded["scopes"][0]["proposal_ids"]
            if mode == "orphan":
                keys.pop()
            elif mode == "duplicate":
                encoded["scopes"][1]["proposal_ids"] = ["p1"]
            elif mode == "missing":
                keys[0] = "missing"
            elif mode == "reorder":
                keys.reverse()
            else:
                encoded["proposals"].append(copy.deepcopy(encoded["proposals"][0]))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                N.decode_verification_view(encoded)

    def test_decoder_rejects_bad_frame_run_indices_counts_and_frames(self):
        for field, value in (("count", True), ("count", 2), ("start_index", 1),
                             ("start_index", 0.0), ("frame_ids", []), ("frame_ids", [True]),
                             ("frame_ids", [0.0]), ("frame_ids", [-1])):
            encoded = N.encode_verification_view(fixture())
            table = encoded["proposals"][0]["frame_table"]
            (table if field == "count" else table["runs"][0])[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                N.decode_verification_view(encoded)

    def test_question_indices_and_literal_source_drift_rejected(self):
        for mode in ("pair", "split", "split_pair", "literal_drift"):
            encoded = N.encode_verification_view(fixture())
            if mode == "pair":
                encoded["pair_questions"][0]["question_id"] = "pair_000001"
            elif mode == "split":
                encoded["split_questions"][0]["question_id"] = "split_000001"
            elif mode == "split_pair":
                encoded["split_questions"][0]["proposal_pairs"][0]["question_id"] = "split_000000_pair_000001"
            else:
                bbox_entry(encoded)["bbox_a"] = {"literal": [0.1, 0.2, 0.7, 1.0]}
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                N.decode_verification_view(encoded)

    def test_original_duplicate_owners_invalid_ids_nonfinite_and_nonjson_rejected(self):
        for mode in ("proposal", "scope", "index", "frame_bool", "frame_float", "frame_negative", "nan", "inf", "tuple", "key"):
            view = fixture()
            if mode == "proposal":
                view["targets"][1]["proposals"][0]["anonymous_proposal_id"] = "p1"
            elif mode == "scope":
                view["targets"][1]["cluster_id"] = "c1"
            elif mode == "index":
                view["cluster_index"].append(copy.deepcopy(view["cluster_index"][0]))
            elif mode.startswith("frame_"):
                view["targets"][0]["proposals"][0]["frame_presence"][0]["frame_id"] = {
                    "frame_bool": True, "frame_float": 0.0, "frame_negative": -1}[mode]
            elif mode == "key":
                view[5] = "bad"
            else:
                view["extra"] = {"nan": float("nan"), "inf": float("inf"), "tuple": (1, 2)}[mode]
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                N.encode_verification_view(view)

    def test_split_cross_owner_endpoint_rejected_without_reassignment(self):
        view = fixture()
        view[N.SPLITS][0]["divergent_proposal_pairs"][0]["proposal_id_a"] = "p3"
        with self.assertRaises(ValueError):
            N.encode_verification_view(view)

    def test_audit_checks_trusted_original_not_just_embedded_digest(self):
        view = fixture()
        encoded = N.encode_verification_view(view)
        view[N.PAIRS][0]["coarse_locator_jaccard"] = 0.5
        with self.assertRaises(ValueError):
            N.audit_verification_view(view, encoded)

    def test_audit_maps_every_row_and_bbox_without_visual_claim(self):
        view = fixture()
        audit = N.audit_verification_view(view, N.encode_verification_view(view))
        self.assertEqual((audit["frame_row_count"], audit["frame_run_count"], audit["split_bbox_reference_count"]), (9, 3, 2))
        self.assertEqual(len(audit["pointer_maps"]), 3 + 9 + 2)
        self.assertFalse(audit["visual_truth_verified"])
        self.assertEqual(audit["original_sha256"], audit["restored_sha256"])

    def test_empty_view_remains_empty_no_added_scopes_or_questions(self):
        self.assert_roundtrip({"targets": [], "cluster_index": [], N.PAIRS: [], N.SPLITS: []})


if __name__ == "__main__":
    unittest.main()
