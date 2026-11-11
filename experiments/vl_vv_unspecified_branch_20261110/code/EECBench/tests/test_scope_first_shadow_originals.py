"""Six-original source metadata is private; the public contract stays unchanged."""
from copy import deepcopy
import unittest

import test_scope_first_shadow as fixture

M = fixture.M


def originals():
    old = fixture.view_bundle()
    fields = {"attachment_index", "view_id", "frame_id", "kind", "path", "sha256", "source_size"}
    rows = [{k: v for k, v in row.items() if k in fields} for row in old["views"][:6]]
    return {"protocol_version": M.ORIGINALS_BUNDLE_VERSION, "views": rows,
            "attachments": [v["path"] for v in rows]}


class OriginalOnlyContextTests(unittest.TestCase):
    def test_same_complete_public_context_and_prompt_as_old_fourteen_views(self):
        args = list(fixture.inputs())
        expected = M.build_shadow_context(*args)
        args[3] = originals()
        before = deepcopy(args)
        actual = M.build_shadow_context(*args)
        self.assertEqual(args, before)
        self.assertEqual(actual["public_context"], expected["public_context"])
        self.assertEqual(M.build_shadow_prompt(actual["public_context"]),
                         M.build_shadow_prompt(expected["public_context"]))
        self.assertEqual(len(actual["private_audit"]["original_reference_views"]), 6)
        self.assertNotIn("/private", M.build_shadow_prompt(actual["public_context"]))
        self.assertEqual(M.validate_shadow(fixture.empty_output(actual["public_context"]),
                                           actual["public_context"])["validation_summary"]["contract_valid"], True)

    def test_no_fake_crop_fields_unknown_protocol_or_extra_images(self):
        for change in (lambda b: b["views"][0].update(crop_xyxy=[0, 0, 200, 120]),
                       lambda b: b.update(protocol_version="unknown"),
                       lambda b: b["views"].append(deepcopy(b["views"][0])),
                       lambda b: b.update(instructions="private override")):
            bundle = originals()
            change(bundle)
            with self.assertRaises(ValueError):
                M._original_frames(bundle)

    def test_exact_frame_path_hash_dimension_and_attachment_contract(self):
        mutations = [lambda b: b["views"][0].update(frame_id=True),
                     lambda b: b["views"][0].update(attachment_index=1.0),
                     lambda b: b["views"][0].update(source_size=[200, False]),
                     lambda b: b["views"][0].update(kind="crop"),
                     lambda b: b["views"][0].update(path="relative.jpg"),
                     lambda b: b["views"][0].update(sha256="bad"),
                     lambda b: b["views"][1].update(path=b["views"][0]["path"]),
                     lambda b: b["attachments"].reverse(),
                     lambda b: b["views"].reverse()]
        for change in mutations:
            bundle = originals()
            change(bundle)
            with self.assertRaises(ValueError):
                M._original_frames(bundle)


if __name__ == "__main__":
    unittest.main()
