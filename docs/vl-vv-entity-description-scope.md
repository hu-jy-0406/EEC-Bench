# Episode-wide entity descriptions: discovery v4 and review v5

User decision 2026-10-06: "a contract or global description of an entity
applies in every shot where that entity appears, unless that shot's own text
describes it differently."

## Why

The contract's `entity_descriptions` define each character, place and object
once, for the whole episode. Later shot prompts often only name the entity.
For example, in #069 "the Short dark-clothed figure" steps aside in Shot4,
while "brownish trousers" is written only in its description. Reviewers
treated such a description as a requirement of the shot where it was first
written, and so rejected violations in later shots as "not required in this
shot". Discovery likewise did not report them.

## Rule (inserted verbatim into both prompts)

> Entity descriptions are episode-wide. A description of an entity in the
> contract (entity_descriptions) or in global_prompt applies in every shot where
> that entity appears (scheduled in entity_schedule or visibly present),
> including shots whose text only names the entity. A shot's own text overrides
> it only where it explicitly describes that entity differently (a different
> value for the same attribute, or a stated change such as changing clothes); a
> shorter or less specific mention is not a different description.

The last clause is my interpretation, added so the rule can be applied
consistently. For example, #002's Shot3 text "blue-gray shirt" is a shorter
mention, not a different description of the global "faded blue-gray T-shirt".

## Versions

The rule is inserted as one paragraph into each prompt:

- **Discovery v4** (`prompts/vl_vv_issue_discovery_v4.txt`) is discovery v3
  plus the rule. The prompt adds: when a shot shows the entity contradicting
  such a description, report a V-L violation in that shot and quote the
  description (source `contract` or `global_prompt`). The schema is the v3
  schema under a new protocol name; the one-label-per-issue gates are
  unchanged.
- **Review v5** (`prompts/vl_vv_issue_review_v5.txt`) is review v4 plus the
  rule. Its rejection clause adds: never reject a V-L label because the
  violating shot's own text only names the entity without restating its
  description, or because another shot satisfies the description.

## Amendment to review v5: the wording is the requirement (2026-10-06, bug fix)

After validation, the reviewer was found to sometimes treat an earlier
generated shot's look as a V-L requirement. For example, it counted a
jacket's stripes against Shot1's diamond pattern although the contract only
says "patterned jacket". At the user's direction, this sentence was added to
review v5 **in place** as a bug fix (no new version), right after the rule
above:

> The requirement is the wording of the description, not how another shot
> happened to depict it: a visual attribute that merely appeared in another
> generated shot is not a requirement unless the text states it.

| Review v5 prompt | SHA-256 |
| --- | --- |
| Before the fix (used by the `vl_vv_entity_scope_20261006` runs) | `42568de9b4b6788fb38c6e585a0b1b7b29d14cc8a5dac10b8bdfa8bd62ebdc08` |
| After the first fix | `f439fd4ffe9ebdbbc65249deade160e21ed6c00a4be3b175a1b6a8b4d9e9598a` |
| After the second fix (current) | `6bec2d8ed73f84a25f14fdc29012087bf5b0f36f58a5d8bc0748251c4dea7895` |

The first sentence alone did not reliably stop the over-reach. At the user's
direction, a second sentence was added in place right after it:

> Compare the shot directly with the quoted words. If the shot satisfies the
> words (for example, any blue car satisfies "a blue car"), reject the V-L
> label even if the shot looks different from another shot; that difference
> is a V-V question.

Every review run records the prompt hash in its `source_hashes.json`. The
pre-fix prompt is kept in
`experiments/vl_vv_entity_scope_20261006/source_before_fix/`. Discovery v4 is
unchanged.

## Default chain and older versions

- **Default chain:** discovery v4 → review v5 → scoring v3 (unchanged).
- **Older versions:** discovery v3/v2/v1 and review v4/v2 stay selectable with
  `--discovery-protocol` / `--review-protocol`.
- **Tests:** `tests/test_vl_vv_entity_scope.py` checks that each new prompt
  differs from its predecessor only by the inserted rule.

Validation: `experiments/vl_vv_entity_scope_20261006/REPORT.md`.
