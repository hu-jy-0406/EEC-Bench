#!/usr/bin/env python3
"""Compare the contract deliverables with the third backup: only the listed camera moves may differ."""
import copy
import json
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
E = HERE.parents[1]
BACKUP = HERE / 'source_before_third/contract_data_before.tar.gz'
MOVES = json.loads((HERE / 'camera_moves_third.json').read_text())['moves']
REMAINING = {(row['episode_id'], row['shot_id'], row['field']): row for row in map(json.loads, (HERE / 'camera_remaining.jsonl').open())}
C = 'experiments/contract_cleanup_20261031/deliverables/'
V = 'experiments/episode_contracts_v2_20261029/deliverables/'
FILES = {C + 'contracts_1_200.jsonl': 'cleaned', C + 'contracts_1_200_with_evidence.jsonl': 'cleaned',
         V + 'contracts_400.jsonl': 'v2_rewrite', V + 'contracts_400_with_evidence.jsonl': 'v2_rewrite'}


def plain(value):
    return value['value'] if isinstance(value, dict) else value


def rows(text):
    return {row['episode_id']: row for row in map(json.loads, text.splitlines())}


def strip(contract, moves):
    """The contract without the moved fields and the cross-shot rows the moves added."""
    out = copy.deepcopy(contract)
    expected = {move['expected'] for move in moves}
    out['cross_shot'] = [row for row in out['cross_shot'] if row['expected'] not in expected]
    for key in ('cross_shot_ids',):
        out.pop(key, None)
    for block in out['shots']:
        for move in moves:
            if move['shot_id'] == block['shot_id']:
                block['shot_description'].pop(move['field'].replace('camera_view', 'camera_view'), None)
    for row in out['cross_shot']:
        row.pop('id', None)
    return out


def main():
    report = {}
    with tarfile.open(BACKUP) as tar:
        for path, kind in FILES.items():
            before = rows(tar.extractfile(path).read().decode())
            after = rows((E / path).read_text())
            assert set(before) == set(after), path
            changed, added = 0, 0
            for eid, new in after.items():
                moves = [move for move in MOVES if move['episode_id'] == eid
                         and REMAINING[(eid, move['shot_id'], move['field'])]['contract'] == kind]
                if not moves:
                    assert new == before[eid], (path, eid)
                    continue
                changed += 1
                old = before[eid]
                added += len(new['cross_shot']) - len(old['cross_shot'])
                assert len(new['cross_shot']) - len(old['cross_shot']) == len(moves), (path, eid)
                blocks = {block['shot_id']: block for block in new['shots']}
                for move in moves:
                    value = plain(blocks[move['shot_id']]['shot_description'][move['field']])
                    assert value == (move.get('keep') or {}).get('value'), (path, eid, move['shot_id'], value)
                assert strip(new, moves) == strip(old, moves), (path, eid)
            report[path] = dict(episodes=len(after), changed=changed, cross_shot_added=added,
                                cross_shot_total=sum(len(row['cross_shot']) for row in after.values()))
    print(json.dumps(report, indent=1))
    (HERE / 'contract_rewrite_audit_third.json').write_text(json.dumps(report, indent=1) + '\n')


if __name__ == '__main__':
    main()
