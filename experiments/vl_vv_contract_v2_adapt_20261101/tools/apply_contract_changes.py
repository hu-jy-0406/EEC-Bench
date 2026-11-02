#!/usr/bin/env python3
"""Remove transition_from_previous and apply camera_moves.json through the two contract toolchains.

Run once on a compute node, after tools/snapshot.sh.  Each contract is rebuilt by its own tool:
rewrite.py export reassembles all 400 v2 contracts from their decisions and asserts equality with the
stripped files; cleanup.py export rebuilds the cleaned 200 from their ops on the changed v2 inputs and
asserts the same.  tools/verify_contract_changes.py then compares every file with the backup.
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
E = HERE.parents[1]
V2 = E / 'experiments/episode_contracts_v2_20261029'
C = E / 'experiments/contract_cleanup_20261031'
sys.path[:0] = [str(V2), str(C), str(E / 'scripts')]
import cleanup  # noqa: E402
import rewrite  # noqa: E402

MOVES = json.loads((HERE / 'camera_moves.json').read_text())['moves']


def strip(contract):
    for shot in contract['shots']:
        shot['shot_description'].pop('transition_from_previous', None)
    return contract


def v2_work():
    for job in rewrite.read(V2 / 'manifest.json')['jobs']:
        folder = V2 / 'episodes' / job['episode_id']
        contract = strip(rewrite.read(folder / 'contract_with_evidence.json'))
        rewrite.dump(folder / 'contract_with_evidence.json', contract)
        rewrite.dump(folder / 'contract.json', strip(rewrite.read(folder / 'contract.json')))
        (folder / 'review.md').write_text(rewrite.render(rewrite.model_facing(contract), rewrite.read(folder / 'claim_accounting.json')))


def v2_moves(moves):
    """Episodes outside the cleaned set: record the move in the decisions and reassemble the episode."""
    for move in moves:
        eid = move['episode_id']
        folder, payload, meta, v1c = rewrite.load_episode(eid)
        decisions = rewrite.read(folder / 'final_decisions.json')
        decisions.setdefault('camera_to_cross_shot', []).append(
            {key: move[key] for key in ('shot_id', 'field', 'shot_ids', 'entities', 'expected', 'predicate')})
        contract, accounting, _ = rewrite.assemble(decisions, payload, meta, v1c)
        rewrite.dump(folder / 'final_decisions.json', decisions)
        rewrite.dump(folder / 'contract_with_evidence.json', contract)
        rewrite.dump(folder / 'contract.json', rewrite.model_facing(contract))
        rewrite.dump(folder / 'claim_accounting.json', accounting)
        (folder / 'review.md').write_text(rewrite.render(rewrite.model_facing(contract), accounting))


def cleanup_work():
    manifest = cleanup.manifest()
    for job in manifest['episodes']:
        eid = job['episode_id']
        job['source_sha256'] = cleanup.sha(cleanup.V2 / eid / 'contract_with_evidence.json')
        folder = C / 'episodes' / eid
        if not (folder / 'contract_with_evidence.json').exists():
            continue
        contract = strip(cleanup.read(folder / 'contract_with_evidence.json'))
        cleanup.dump(folder / 'contract_with_evidence.json', contract)
        cleanup.dump(folder / 'contract.json', strip(cleanup.read(folder / 'contract.json')))
        (folder / 'review.md').write_text(cleanup.render_md(contract))
    cleanup.dump(C / 'manifest.json', manifest)


def cleanup_moves(moves):
    """Cleaned episodes: append the op to final_ops.json and rebuild the episode; review status stays."""
    for move in moves:
        eid = move['episode_id']
        folder = C / 'episodes' / eid
        ops = cleanup.read(folder / 'final_ops.json')
        working, errors = cleanup.apply_ops(cleanup.load_input(eid), ops)
        assert not errors, (eid, errors)
        keys = {entity['name']: key for key, entity in working.ents.items()}
        reason = 'Owner 2026-11-01: a requirement on how the camera changes between shots belongs in cross_shot.'
        new = [dict(op='camera_to_cross_shot', shot_id=move['shot_id'], field=move['field'], shot_ids=move['shot_ids'],
                    entities=[keys[name] for name in move['entities']], expected=move['expected'],
                    predicate=move['predicate'], reason=reason)]
        if 'also_set_camera' in move:
            new.append(dict(op='set_camera', **move['also_set_camera']))
        ops['ops'] += new
        cleanup.dump(folder / 'final_ops.json', ops)
        c, _, built, new_id, errors, _ = cleanup.build(eid, folder / 'final_ops.json')
        assert not errors, (eid, errors)
        w, out = built
        cleanup.dump(folder / 'contract_with_evidence.json', out)
        cleanup.dump(folder / 'contract.json', cleanup.model_facing(out))
        (folder / 'review.md').write_text(cleanup.render_md(out))
        log = cleanup.read(folder / 'cleanup_log.json')
        log.update(ops=ops['ops'], ops_sha256=cleanup.sha(folder / 'final_ops.json'), changes=cleanup.changes(c, w, out, new_id),
                   post_review_ops=dict(count=len(new), at=time.time(), source='experiments/vl_vv_contract_v2_adapt_20261101/camera_moves.json'))
        cleanup.dump(folder / 'cleanup_log.json', log)
        status = cleanup.read(folder / 'status.json')
        status['ops'] = len(ops['ops'])
        cleanup.dump(folder / 'status.json', status)


def main():
    cleaned = {row['episode_id'] for row in cleanup.read(C / 'deliverables/index_1_200.json')}
    v2_work()
    v2_moves([move for move in MOVES if move['episode_id'] not in cleaned])
    rewrite.export()
    cleanup_work()
    cleanup_moves([move for move in MOVES if move['episode_id'] in cleaned])
    cleanup.export()


if __name__ == '__main__':
    main()
