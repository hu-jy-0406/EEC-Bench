"""List camera wording that refers to another shot, in the current v2 contracts (cleaned first where they exist)."""
import json
import re
from pathlib import Path

R = Path(__file__).resolve().parents[2]
V = R / 'episode_contracts_v2_20261029/deliverables/contracts_400.jsonl'
C = R / 'contract_cleanup_20261031/deliverables/contracts_1_200.jsonl'
OUT = Path(__file__).resolve().parents[1] / 'camera_between_shots_scan.jsonl'

PATTERN = re.compile(
    r'\b(same|again|previous|preceding|earlier|prior|before|return|returns|returning|back to|once more|'
    r'matching|matches|match|repeat|repeats|mirror|mirrors|reverse|opposite|last shot|next shot|first shot|'
    r'shot ?\d|continu|still|unchanged|remain|remains|retain|retains|keep|keeps|maintain|maintains|hold|holds|'
    r'closer than|wider than|tighter than|than the|new angle|new view|different angle|different view|'
    r'another angle|another view|established|familiar|from the other|from the opposite)\b', re.I)
CAMERA_WORDS = re.compile(r'\b(camera|view|angle|framing|frame|shot|close-up|closeup|wide|medium|lens|pan|tilt|dolly|zoom|'
                          r'push|pull|track|reverse|over-the-shoulder|profile|two-shot)\b', re.I)


def main():
    rows = [json.loads(line) for line in V.open()]
    cleaned = {r['episode_id']: json.loads(line) for r, line in
               ((json.loads(line), line) for line in C.open())}
    hits = []
    for row in rows:
        contract = cleaned.get(row['episode_id'], row)
        tag = 'cleaned' if row['episode_id'] in cleaned else 'v2'
        for shot in contract['shots']:
            desc = shot['shot_description']
            for field in ('camera_view', 'camera_movement'):
                text = desc[field]
                if text and PATTERN.search(text):
                    hits.append(dict(episode_id=row['episode_id'], source=tag, shot_id=shot['shot_id'], where=field,
                                     text=text, match=PATTERN.search(text).group(0)))
            for dim in ('appearance', 'spatial', 'motion'):
                for item in shot[dim]:
                    text = item['expected']
                    if CAMERA_WORDS.search(text) and PATTERN.search(text) and re.search(
                            r'\b(camera|view|angle|framing|shot)\b', text, re.I):
                        hits.append(dict(episode_id=row['episode_id'], source=tag, shot_id=shot['shot_id'], where=f'{dim}:{item["id"]}',
                                         text=text, match=PATTERN.search(text).group(0)))
        for item in contract['cross_shot']:
            if re.search(r'\b(camera|view|angle|framing)\b', item['expected'], re.I):
                hits.append(dict(episode_id=row['episode_id'], source=tag, shot_id=','.join(item['shot_ids']),
                                 where=f'cross_shot:{item["id"]}', text=item['expected'], match='cross_shot'))
    OUT.write_text(''.join(json.dumps(h, ensure_ascii=False) + '\n' for h in hits))
    print(len(hits))
    for h in hits:
        print(h['episode_id'][:24], h['source'], h['shot_id'], h['where'], '|', h['match'], '|', h['text'][:170])


if __name__ == '__main__':
    main()
