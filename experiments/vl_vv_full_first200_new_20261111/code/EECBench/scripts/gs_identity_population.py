"""Separate all-entity identity from the existing static scoring population."""
import copy


def static_group(group, nodes):
    members = [(side, eid) for side, key in enumerate(('a_ids', 'b_ids'))
               for eid in group[key]]
    return bool(members) and all(nodes[side][eid]['motion_status'] == 'static'
                                 for side, eid in members)


def validate_anchors(matching, nodes):
    for group in matching['groups']:
        if group.get('anchor_eligible') or group['group_id'] in matching['structural_anchor_group_ids']:
            assert group['identity'] == 'matched' and static_group(group, nodes), 'Anchor must be matched and static in both shots'
            assert all(nodes[i][group[key][0]].get('anchor_observed_static', True)
                       for i, key in enumerate(('a_ids', 'b_ids'))), 'Expected-static anomaly is not a stable registration anchor'
            assert all(nodes[i][group[key][0]].get('geometry') is not None
                       for i, key in enumerate(('a_ids', 'b_ids'))), 'Anchor lacks geometry'


def static_matching(matching, nodes):
    """Do not turn a static/moving match into a false single-sided absence."""
    result = copy.deepcopy(matching)
    result['groups'] = [g for g in result['groups'] if static_group(g, nodes)]
    kept = {g['group_id'] for g in result['groups']}
    result['structural_anchor_group_ids'] = [g for g in result.get('structural_anchor_group_ids', []) if g in kept]
    for key in ('local_origin_group_id', 'local_reference_group_id'):
        if result.get(key) not in kept:
            result[key] = ''
    return result


def scene_scope(shots):
    """Explicit scene IDs, or the legacy Shot1/3 room and singleton Shot2."""
    explicit = any('scene_id' in shot for shot in shots)
    scenes = {}
    seen = set()
    for shot in shots:
        sid = shot['shot_id']
        if sid in seen:
            raise ValueError('Duplicate shot ID')
        seen.add(sid)
        scene = shot.get('scene_id') if explicit else ('legacy_primary' if sid in ('shot1', 'shot3') else 'singleton_' + sid)
        if not isinstance(scene, str) or not scene.strip():
            raise ValueError('Provide a nonempty scene_id for every shot when using scene IDs')
        scenes.setdefault(scene, []).append(sid)
    return dict(scenes=scenes,
                cross_shot_pairs=[dict(scene_id=scene, shot_ids=[a, b])
                                  for scene, ids in scenes.items()
                                  for i, a in enumerate(ids) for b in ids[i + 1:]],
                skipped_single_shot_scenes=[dict(scene_id=scene, shot_id=ids[0], reason='single_shot_scene')
                                            for scene, ids in scenes.items() if len(ids) == 1])
