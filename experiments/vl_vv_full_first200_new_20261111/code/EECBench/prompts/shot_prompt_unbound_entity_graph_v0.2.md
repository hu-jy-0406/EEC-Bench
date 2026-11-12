You are performing a high-recall inventory of prompt-unbound physical entities
in one video shot, using a sparse, chronologically ordered set of reference
frames. The primary objective is to find all visually supported extra entities
that could be tracked or compared across shots, including less salient entities.

Return only the JSON object required by the supplied output schema. Do not use
tools, inspect files, edit files, add Markdown fences, or explain your answer.

The prompt-bound exclusion registry is authoritative about which semantic
entities were specified by the input prompt. Exclude the actual registry entity,
including a renaming or synonym of it. GroundingDINO observations are fallible
localization hints only: a detected box is not an exclusion mask, and everything
inside, overlapping, behind, or adjacent to a box must still be inspected. If a
box visually conflicts with its registry name or description, do not use the
box to suppress the physical entities it covers. A detector miss is unknown and
does not remove the named entity from the registry.

Apply the exclusion at instance level:

- A prompt-bound person or object excludes only that physical instance. It does
  not exclude distinct furniture, containers, contents, props, or background
  objects that it touches, holds, occludes, rests on, or stands near.
- A prompt-bound location such as a study, room, office, or street excludes only
  the corresponding scene/location node. It never excludes the furniture,
  architectural fixtures, surfaces, or movable objects visible within that
  location, regardless of where the location detector placed its box.
- Do not split an excluded person or object into clothing, hair, body parts, or
  ordinary attached components merely to reintroduce it as an extra entity.

Before producing the JSON, perform this coverage procedure internally:

1. Inspect every supplied frame independently before applying exclusions. Scan
   foreground, middle ground, and background, and scan left, center, and right.
   Build the union of distinct physical instances visible in any frame; an
   entity does not need to appear in every frame.
2. Explicitly inspect every major support or container region, including desks,
   tables, shelves, cabinets, floors, and seating. Consider both the support or
   container itself and each distinguishable item on, in, under, beside, or
   behind it. Repeat this inspection around every supplied detector box so that
   the exclusion context cannot create a spatial blind spot.
3. Merge repeated views of the same physical instance across frames. Keep
   visually distinct instances separate even when they share a category.
4. Apply the prompt-bound registry item by item using semantic identity, not
   spatial overlap alone. Remove only candidates that are actually the excluded
   entity or a prohibited component of it.
5. Make a final completeness pass over the cross-frame union. Do not omit an
   entity merely because it is small, stationary, partly occluded, peripheral,
   unrelated to the main action, or lacks a relation. Include it when at least
   one frame supports a recognizable physical identity at a useful granularity.
   Use lower confidence and narrower evidence when appropriate. Return empty
   arrays only after this full scan finds no supported prompt-unbound entity.

Extraction rules:

1. Use an open vocabulary. Emit distinct, visually observable physical
   instances suitable for later localization or cross-shot comparison. People,
   animals, furniture, movable objects, architectural fixtures, plants, and
   physical locations or scene regions are allowed. Do not invent hidden
   entities from commonsense. Do not turn shadows, lighting, colors, patterns,
   depicted content, or readable text into physical entities. Avoid exploding
   one object into ordinary parts, and group repeated tiny items only when their
   individual identities are not visually distinguishable.
2. IDs are local to this shot. Assign consecutive IDs e1, e2, ... . Two
   visually distinct instances with the same name must have different IDs.
3. Entity names must be lowercase singular nouns or short noun phrases. Do not
   include articles, instance numbers, actions, relations, or full sentences.
4. Attributes use open-vocabulary atomic name/value pairs. Include only
   visually supported, entity-local appearance, state, or unary-action facts.
5. Every entity and attribute must cite one or more supplied reference frame
   IDs that visibly support it. Confidence values are uncalibrated self-reports
   in [0, 1]. Be conservative about attributes and relations without making
   entity inclusion depend on having detailed attributes or relations.
6. Relations are positive, visually supported, directed binary semantic edges
   whose endpoints are both prompt-unbound entity IDs in this graph. Do not
   emit relations involving an excluded prompt-bound entity.
7. Relation evidence must use supplied frame IDs. Estimate temporal extents
   conservatively: `frame`, `segment`, `shot`, or `unknown`; unknown requires
   null boundaries, while other intervals use [start_frame,
   end_frame_exclusive) and contain every cited evidence frame.
8. Do not output bounding boxes. GroundingDINO will ground the returned
   prompt-unbound entities in a separate stage.
9. Missing evidence is unknown, not false. Do not invent uncertain identities;
   add a short warning when sparse sampling, blur, or occlusion prevents a
   potentially distinct physical entity from being identified reliably.
