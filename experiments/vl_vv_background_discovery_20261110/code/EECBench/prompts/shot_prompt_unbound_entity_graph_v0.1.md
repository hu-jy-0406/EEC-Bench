You are extracting only prompt-unbound physical entities from one video shot,
using a sparse, chronologically ordered set of reference frames.

Return only the JSON object required by the supplied output schema. Do not use
tools, inspect files, edit files, add Markdown fences, or explain your answer.

The prompt-bound exclusion registry below is authoritative. It contains the
entities specified by the input prompt for this shot and GroundingDINO
observations when they were detected. Do not emit any registry entity, a
renaming or synonym of it, or the same visual instance indicated by one of its
boxes. A detector miss is unknown and does not remove that named entity from
the exclusion registry. Do not split an excluded person or object into
clothing, hair, body parts, or other attached components merely to reintroduce
it as an extra entity.

Extraction rules:

1. Use an open vocabulary. Emit only distinct, visually observable physical
   instances that are salient in the shot and are not prompt-bound. People,
   animals, objects, and physical locations or scene regions are allowed. Do
   not add hidden entities based only on commonsense. Empty `entities` and
   `relations` arrays are valid when no prompt-unbound entity is supported.
2. IDs are local to this shot. Assign consecutive IDs e1, e2, ... . Two
   visually distinct instances with the same name must have different IDs.
3. Entity names must be lowercase singular nouns or short noun phrases. Do not
   include articles, instance numbers, actions, relations, or full sentences.
4. Attributes use open-vocabulary atomic name/value pairs. Include only
   visually supported, entity-local appearance, state, or unary-action facts.
5. Every entity and attribute must cite one or more supplied reference frame
   IDs that visibly support it. Confidence values are uncalibrated self-reports
   in [0, 1].
6. Relations are positive, visually supported, directed binary semantic edges
   whose endpoints are both prompt-unbound entity IDs in this graph. Do not
   emit relations involving an excluded prompt-bound entity.
7. Relation evidence must use supplied frame IDs. Estimate temporal extents
   conservatively: `frame`, `segment`, `shot`, or `unknown`; unknown requires
   null boundaries, while other intervals use [start_frame,
   end_frame_exclusive) and contain every cited evidence frame.
8. Do not output bounding boxes. GroundingDINO will ground the returned
   prompt-unbound entities in a separate stage.
9. Missing evidence is unknown, not false. Omit unreliable claims and add a
   short warning when sparse sampling or occlusion materially limits the result.

