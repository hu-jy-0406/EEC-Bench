#!/usr/bin/env python3
"""Compare every contract file with the second backup: only style and the listed camera moves may differ."""
import collections
import json
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
E = HERE.parents[1]
BACKUP = HERE / 'source_before_style/contract_data_before.tar.gz'
STYLES = json.loads((HERE / 'style_decisions.json').read_text())['episodes']
MOVES = json.loads((HERE / 'camera_moves_second.json').read_text())['moves']
MOVED = {move['episode_id'] for move in MOVES}
RESULT = HERE / 'contract_rewrite_audit_style.json'
counts = collections.Counter()


def plain(value):
    return value['value'] if isinstance(value, dict) else value


def compare(before, after):
    """True when after = before + the expected style values, up to the listed camera moves."""
    eid = before['episode_id']
    rows = [move for move in MOVES if move['episode_id'] == eid]
    expected = {move['expected'] for move in rows}
    new = [item for item in after['cross_shot'] if item['expected'] in expected]
    if new:
        assert len(new) == len(rows), (eid, len(new), len(rows))
    moved_fields = {(move['shot_id'], move['field']): move for move in rows} if new else {}
    if len(after['shots']) != len(before['shots']):
        return False
    for old, now in zip(before['shots'], after['shots']):
        desc = now['shot_description']
        want = STYLES.get(eid, {}).get(old['shot_id'])
        if plain(desc['style']) != (want['value'] if want else None):
            return False
        if want and isinstance(desc['style'], dict):
            counts['style_quotes'] += len(desc['style']['evidence'])
            if [q['quote'] for q in desc['style']['evidence']] != [q['quote'] for q in want['quotes']]:
                return False
        for field in ('camera_view', 'camera_movement'):
            move = moved_fields.get((old['shot_id'], field))
            if move is None:
                if desc[field] != old['shot_description'][field]:
                    return False
            elif plain(desc[field]) != (move['keep']['value'] if 'keep' in move else None):
                return False
        rest = lambda s: {k: v for k, v in s.items() if k != 'shot_description'}
        if rest(old) != rest(now):
            return False
    tail = lambda c: {k: v for k, v in c.items() if k not in ('shots', 'cross_shot')}
    return tail(before) == tail(after) and before['cross_shot'] == [i for i in after['cross_shot'] if i not in new]


def main():
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
            data, now = tar.extractfile(member).read(), path.read_bytes()
            if name in ('contract.json', 'contract_with_evidence.json'):
                ok = compare(json.loads(data), json.loads(now))
            elif name.endswith('.jsonl'):
                old_rows, new_rows = data.decode().splitlines(), now.decode().splitlines()
                ok = len(old_rows) == len(new_rows) and all(compare(json.loads(a), json.loads(b)) for a, b in zip(old_rows, new_rows))
            elif name == 'review.md':
                eid = Path(rel).parent.name
                keep = lambda text: [line for line in text.splitlines() if 'style' not in line]
                ok = eid in MOVED or keep(data.decode()) == keep(now.decode())
            else:
                eid = Path(rel).parent.name
                ok = data == now or eid in MOVED or eid in STYLES or name.startswith('index')
            counts[f'{name if not name.startswith("contracts_") and name != "priority_200.jsonl" else "jsonl"}:{"same" if data == now else "changed"}'] += 1
            if not ok:
                problems.append(f'unexpected difference: {rel}')
    summary = dict(counts=dict(sorted(counts.items())), problems=problems)
    RESULT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(counts=summary['counts'], problems=len(problems), first=problems[:10]), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
