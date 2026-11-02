#!/usr/bin/env python3
"""Compare every contract file with the backup: only the transition field and the listed camera moves may differ."""
import collections
import json
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
E = HERE.parents[1]
BACKUP = HERE / 'source_before/contract_data_before.tar.gz'
MOVES = json.loads((HERE / 'camera_moves.json').read_text())['moves']
MOVED = {move['episode_id'] for move in MOVES}
RESULT = HERE / 'contract_rewrite_audit.json'


def expected(before):
    """The backup contract with the transition field removed."""
    for shot in before['shots']:
        shot['shot_description'].pop('transition_from_previous', None)
    return before


def camera_delta(before, after):
    """Remove the listed camera change from both sides so the rest can be compared exactly."""
    rows = [move for move in MOVES if move['episode_id'] == before['episode_id']]
    new = [item for item in after['cross_shot'] if item.get('coordinate_frame') == 'camera' and item.get('quantifier') == 'cross_shot'
           and item['expected'] in {move['expected'] for move in rows}]
    if not new:  # the uncleaned v2 copy of a cleaned episode keeps its camera value; the move is in the cleaned contract
        return after
    assert len(new) == len(rows), (before['episode_id'], len(new))
    after = dict(after, cross_shot=[item for item in after['cross_shot'] if item not in new])
    shots = {shot['shot_id']: shot for shot in after['shots']}
    for move in rows:
        fields = [(move['shot_id'], move['field'])]
        if 'also_set_camera' in move:
            fields.append((move['also_set_camera']['shot_id'], move['also_set_camera']['field']))
        for sid, field in fields:
            shots[sid]['shot_description'][field] = next(s for s in before['shots'] if s['shot_id'] == sid)['shot_description'][field]
    return after


def same(before, after):
    before = expected(before)
    if before.get('episode_id') in MOVED:
        after = camera_delta(before, json.loads(json.dumps(after)))
    return before == after


def main():
    counts = collections.Counter()
    problems = []
    with tarfile.open(BACKUP) as tar:
        for member in tar:
            if not member.isfile():
                continue
            rel, name = member.name, Path(member.name).name
            path = E / rel
            if not path.is_file():
                problems.append(f'missing {rel}')
                continue
            data = tar.extractfile(member).read()
            now = path.read_bytes()
            if name in ('contract.json', 'contract_with_evidence.json'):
                ok = same(json.loads(data), json.loads(now))
                assert b'transition_from_previous' not in now, rel
            elif name.endswith('.jsonl'):
                old_rows, new_rows = data.decode().splitlines(), now.decode().splitlines()
                ok = len(old_rows) == len(new_rows) and all(same(json.loads(a), json.loads(b)) for a, b in zip(old_rows, new_rows))
                assert b'transition_from_previous' not in now, rel
            elif name == 'review.md':
                drop = lambda line: '**transition_from_previous**' not in line
                strip = lambda text: [line.split(' | transition:')[0] for line in text.splitlines() if drop(line)]
                ok = strip(data.decode()) == now.decode().splitlines() or Path(rel).parent.name in MOVED
                assert b'transition_from_previous' not in now and b'| transition:' not in now, rel
            else:
                ok = data == now or Path(rel).parent.name in MOVED or name.startswith('index')
            counts[f'{name if not name.startswith("contracts_") and name != "priority_200.jsonl" else "jsonl"}:{"same" if data == now else "changed"}'] += 1
            if not ok:
                problems.append(f'unexpected difference: {rel}')
    summary = dict(counts=dict(sorted(counts.items())), problems=problems, moved_episodes=sorted(MOVED))
    RESULT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(counts=summary['counts'], problems=len(problems), first=problems[:10]), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
