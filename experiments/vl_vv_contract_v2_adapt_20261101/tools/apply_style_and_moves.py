#!/usr/bin/env python3
"""Add shot_description.style and apply camera_moves_second.json through the two contract toolchains.

Run once on a compute node, after tools/snapshot_style.sh. All 400 v2 contracts are reassembled from their
decisions and exported; the cleaned 200 are then rebuilt from their ops on the changed inputs and exported.
Both exports assert equality with the stored files. tools/verify_style_changes.py compares with the backup.
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

STYLES = json.loads((HERE / 'style_decisions.json').read_text())['episodes']
MOVES = json.loads((HERE / 'camera_moves_second.json').read_text())['moves']
REASON = 'Owner 2026-11-01: a requirement on how the camera changes between shots belongs in cross_shot.'


def by_prefix(names, prefix, eid):
    exact = [name for name in names if name == prefix]
    found = exact or [name for name in names if name.startswith(prefix)]
    assert len(found) == 1, (eid, prefix, found)
    return found[0]


def v2_all(moves):
    for job in rewrite.read(V2 / 'manifest.json')['jobs']:
        eid = job['episode_id']
        folder, payload, meta, v1c = rewrite.load_episode(eid)
        decisions = rewrite.read(folder / 'final_decisions.json')
        changed = False
        if STYLES.get(eid):
            decisions['shot_styles'] = [dict(shot_id=sid, **row) for sid, row in STYLES[eid].items()]
            changed = True
        for move in moves.get(eid, []):
            names = [entity['name'] for entity in decisions['entities']]
            row = {key: move[key] for key in ('shot_id', 'field', 'shot_ids', 'expected', 'predicate')}
            row['entities'] = [by_prefix(names, prefix, eid) for prefix in move['entities']]
            if 'keep' in move:
                row['keep'] = move['keep']
            decisions.setdefault('camera_to_cross_shot', []).append(row)
            changed = True
        contract, accounting, _ = rewrite.assemble(decisions, payload, meta, v1c)
        if changed:
            rewrite.dump(folder / 'final_decisions.json', decisions)
        rewrite.dump(folder / 'contract_with_evidence.json', contract)
        rewrite.dump(folder / 'contract.json', rewrite.model_facing(contract))
        rewrite.dump(folder / 'claim_accounting.json', accounting)
        (folder / 'review.md').write_text(rewrite.render(rewrite.model_facing(contract), accounting))


def cleanup_all(moves):
    manifest = cleanup.manifest()
    for job in manifest['episodes']:
        job['source_sha256'] = cleanup.sha(cleanup.V2 / job['episode_id'] / 'contract_with_evidence.json')
    cleanup.dump(C / 'manifest.json', manifest)
    for job in manifest['episodes']:
        eid = job['episode_id']
        folder = C / 'episodes' / eid
        ops = cleanup.read(folder / 'final_ops.json')
        rows = moves.get(eid, [])
        for move in rows:
            working, errors = cleanup.apply_ops(cleanup.load_input(eid), ops)
            assert not errors, (eid, errors)
            names = {entity['name']: key for key, entity in working.ents.items()}
            op = dict(op='camera_to_cross_shot', shot_id=move['shot_id'], field=move['field'], shot_ids=move['shot_ids'],
                      entities=[names[by_prefix(list(names), prefix, eid)] for prefix in move['entities']],
                      expected=move['expected'], predicate=move['predicate'], reason=REASON)
            if 'keep' in move:
                op['keep'] = move['keep']
            ops['ops'].append(op)
        if rows:
            cleanup.dump(folder / 'final_ops.json', ops)
        c, _, built, new_id, errors, _ = cleanup.build(eid, folder / 'final_ops.json')
        assert not errors, (eid, errors)
        w, out = built
        cleanup.dump(folder / 'contract_with_evidence.json', out)
        cleanup.dump(folder / 'contract.json', cleanup.model_facing(out))
        (folder / 'review.md').write_text(cleanup.render_md(out))
        if rows:
            log = cleanup.read(folder / 'cleanup_log.json')
            log.update(ops=ops['ops'], ops_sha256=cleanup.sha(folder / 'final_ops.json'), changes=cleanup.changes(c, w, out, new_id))
            log.setdefault('post_review_ops', dict(source='experiments/vl_vv_contract_v2_adapt_20261101'))['second_pass'] = dict(count=len(rows), at=time.time())
            cleanup.dump(folder / 'cleanup_log.json', log)
            status = cleanup.read(folder / 'status.json')
            status['ops'] = len(ops['ops'])
            cleanup.dump(folder / 'status.json', status)


def main():
    cleaned = {row['episode_id'] for row in cleanup.read(C / 'deliverables/index_1_200.json')}
    by_episode = {}
    for move in MOVES:
        by_episode.setdefault(move['episode_id'], []).append(move)
    v2_all({eid: rows for eid, rows in by_episode.items() if eid not in cleaned})
    rewrite.export()
    cleanup_all({eid: rows for eid, rows in by_episode.items() if eid in cleaned})
    cleanup.export()


if __name__ == '__main__':
    main()
