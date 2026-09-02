You are extracting one shot-local semantic entity graph from a sparse,
chronologically ordered set of reference frames.

Return only the JSON object required by the supplied output schema. Do not use
tools, inspect files, edit files, add Markdown fences, or explain your answer.

Extraction rules:

1. Use an open vocabulary. Create one entity node for each distinct, visually
   observable physical instance that is salient in the shot. People, animals,
   objects, and salient physical locations or scene regions are allowed. Do not
   add hidden entities based only on commonsense.
2. IDs are local to this shot. Assign consecutive IDs e1, e2, ... . Two
   visually distinct instances with the same name must have different IDs.
3. Entity names must be lowercase singular nouns or short noun phrases. Do not
   include articles, instance numbers, actions, relations, or full sentences.
4. Attributes use open-vocabulary atomic name/value pairs. Include only
   visually supported, entity-local appearance, state, or unary-action facts.
   A unary action such as walking belongs in an attribute with name "action";
   do not invent a dummy relation object.
5. Each entity and attribute must cite one or more supplied reference frame IDs
   that visibly support it. Confidence values are self-reported estimates in
   [0, 1], not calibrated probabilities.
6. Relations are positive, visually supported, directed binary semantic edges.
   Both endpoints must be entity IDs in this graph. Use an open-vocabulary,
   lowercase, short predicate such as "holding", "inside", "looking at", or
   "standing next to". Do not include subject/object names in the predicate.
   Multiple predicates for one entity pair are allowed. Do not emit negative
   relations, self-relations, geometry, coordinates, vectors, or relation types.
7. Relation evidence_frame_ids must cite supplied reference frames that support
   the relation. Estimate temporal_extent conservatively from the sparse frames:
   - "frame" only when the boundary is actually localized to a frame;
   - "segment" for an approximate interval;
   - "shot" for a relation observed throughout the available shot evidence;
   - "unknown" with null boundaries when no defensible interval is possible.
   For non-unknown intervals use [start_frame, end_frame_exclusive), and ensure
   all relation evidence frames lie inside it. Do not fabricate exact boundaries
   between widely separated reference frames.
8. Do not output bounding boxes. A separate GroundingDINO stage will produce
   boxes using the names and attributes extracted here.
9. Missing evidence is unknown, not false. If sparse sampling or occlusion makes
   a material decision unreliable, omit the claim and add a short warning.

