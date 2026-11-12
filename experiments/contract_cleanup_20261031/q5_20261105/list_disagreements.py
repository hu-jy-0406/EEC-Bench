#!/usr/bin/env python3
"""List every open Q5 review disagreement and missed statement, with the item it concerns.

Output (stdout, or --out FILE): one block per episode with each disputed ref (O<n> operation, C<n> checked
statement, M<n> missed statement), the applied operation or checked row, the reviewer's basis and alternative.
Usage: list_disagreements.py [--out FILE] [--json FILE]
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import cleanup as C  # noqa: E402


def rows():
    for job in C.manifest()['episodes']:
        eid = job['episode_id']
        folder = HERE / 'episodes' / eid
        st = C.read(folder / 'status.json')
        q = st.get('q5') or {}
        if q.get('stage') != 'reviewed' or not q.get('disagreements'):
            continue
        applied = C.read(folder / 'q5_ops_applied.json')
        review = C.read(folder / 'q5_review.json')
        verdicts = {x['ref']: x for x in review['items']}
        items = []
        for ref in q['disagreements']:
            kind, index = ref[0], int(ref[1:])
            if kind == 'M':
                m = review['missed'][index]
                items.append(dict(ref=ref, item=None, basis=None, alternative=m))
                continue
            item = applied['ops'][index] if kind == 'O' else applied['checked'][index]
            v = verdicts[ref]
            items.append(dict(ref=ref, item=item, basis=v.get('basis'), alternative=v.get('alternative')))
        yield dict(index=job['index'] + 1, episode_id=eid, items=items)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path)
    p.add_argument('--json', type=Path)
    a = p.parse_args()
    data = list(rows())
    lines = []
    for ep in data:
        lines.append(f'=== priority {ep["index"]} {ep["episode_id"]}')
        for it in ep['items']:
            lines.append(f'  {it["ref"]}: ' + json.dumps(it['item'], ensure_ascii=False) if it['item'] else f'  {it["ref"]}: (missed)')
            if it['basis']:
                lines.append(f'     reviewer: {it["basis"]}')
            lines.append('     alternative: ' + (json.dumps(it['alternative'], ensure_ascii=False)
                                                if isinstance(it['alternative'], dict) else str(it['alternative'])))
    text = '\n'.join(lines)
    print(f'{len(data)} episodes, {sum(len(e["items"]) for e in data)} items')
    if a.out:
        a.out.write_text(text + '\n')
    else:
        print(text)
    if a.json:
        a.json.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n')


if __name__ == '__main__':
    main()
