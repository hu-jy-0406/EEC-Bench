"""Reject transport-incompatible later-role schemas before any paid detector."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from test_prompt_unbound_pipelines import ENSEMBLE


class SchemaTransportTest(unittest.TestCase):
    def test_invalid_later_role_stops_before_first_detector(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schemas = root / "schemas"
            schemas.mkdir()
            bad = schemas / "codex_entity_adjudication_v0.6.schema.json"
            bad.write_text(json.dumps({"type": "object", "$defs": {"evidence": {
                "type": "object", "properties": {"anonymous_proposal_ids": {
                    "type": "array", "items": {"type": "string"}, "uniqueItems": True,
                }},
            }}}))
            with mock.patch.object(ENSEMBLE, "PROJECT_ROOT", root), \
                 mock.patch.object(ENSEMBLE, "run_codex_json") as call, \
                 mock.patch.object(ENSEMBLE, "_codex_version") as version:
                with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "uniqueItems"):
                    ENSEMBLE.run_ensemble_detection(
                        sample=None, shot_id="synthetic", prompt_entities=[],
                        run_dir=root / "run", codex_bin=sys.executable,
                        model="no-model", timeout_sec=1, identity_review_policy="physical_v0.6",
                    )
            call.assert_not_called()
            version.assert_not_called()
            self.assertFalse((root / "run").exists())

    def test_actual_call_path_rechecks_specialized_schema_before_subprocess(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schema = root / "specialized.schema.json"
            schema.write_text(json.dumps({"type": "object", "properties": {
                "value": {"$ref": "#/$defs/value", "description": "unsupported sibling"},
            }, "$defs": {"value": {"type": "string"}}}))
            with mock.patch.object(ENSEMBLE.subprocess, "Popen") as process:
                with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "ref has siblings"):
                    ENSEMBLE.run_codex_json(
                        prompt="no inference", attachments=[], schema_path=schema,
                        output_path=root / "output.json", events_path=root / "events.jsonl",
                        stderr_path=root / "stderr.log", codex_bin=sys.executable,
                        model="no-model", timeout_sec=1, work_dir=root,
                    )
            process.assert_not_called()

    def test_schema_keywords_are_distinct_from_property_names_and_enum_data(self):
        payload = {"type": "object", "properties": {
            "const": {"type": "string", "enum": ["uniqueItems"]},
            "uniqueItems": {"type": "boolean", "const": True},
        }, "required": ["const", "uniqueItems"], "additionalProperties": False}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema.json"
            path.write_text(json.dumps(payload))
            self.assertEqual(ENSEMBLE.validate_codex_schema_transport(path), payload)
            payload["properties"]["const"]["uniqueItems"] = True
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "uniqueItems"):
                ENSEMBLE.validate_codex_schema_transport(path)


if __name__ == "__main__":
    unittest.main()
