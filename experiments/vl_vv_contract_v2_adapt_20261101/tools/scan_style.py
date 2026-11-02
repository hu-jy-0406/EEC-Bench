"""Keyword candidates for an explicit visual or render style in the prompts of all 400 episodes (reading decides)."""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parents[1] / 'scripts'))
import episode_contract as contract_io  # noqa: E402

QUEUE = HERE.parents[1] / 'experiments/source_video_priority_20260921/generation_queue_400.ids.txt'
PATTERN = re.compile(
    r"animat|cartoon|\banime\b|\bcel\b|cel-|hand-drawn|hand drawn|hand-painted|black[- ]and[- ]white|monochrom|sepia|grayscale|greyscale|"
    r"\bCG\b|\bCGI\b|\b3D\b|\b2D\b|pixel|stop-motion|stop motion|claymation|\bclay\b|painterly|watercolou?r|oil paint|illustrat|sketch|"
    r"comic|film grain|grainy|vintage|\bnoir\b|retro\b|archival|home video|home-video|\bVHS\b|live-action|live action|photoreal|"
    r"render|stylized|stylised|puppet|digital|desaturated|storybook|silent film|newsreel|\bstyle\b|rotoscop|video game|videogame|"
    r"webcam|surveillance|footage|film stock|technicolor|muted color|washed-out|washed out", re.I)


def sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


def main():
    ids = [x.strip() for x in QUEUE.read_text().splitlines() if x.strip()]
    rows = []
    for index, eid in enumerate(ids):
        prompt = contract_io.read(contract_io.resolve_v2_contract(eid))['prompt']
        for source, text in [('global', prompt['global_prompt'])] + [(s['shot_id'], s['text']) for s in prompt['shots']]:
            for sentence in sentences(text):
                found = sorted({m.group(0).lower() for m in PATTERN.finditer(sentence)})
                if found:
                    rows.append(dict(index=index, episode_id=eid, source=source, keywords=found, sentence=sentence))
    (HERE / 'style_candidates.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    print(len(rows), 'sentences in', len({r['episode_id'] for r in rows}), 'episodes')


if __name__ == '__main__':
    main()
