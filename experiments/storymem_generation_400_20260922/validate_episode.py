"""Validate complete native StoryMem output without changing model decisions."""
import hashlib
import json
from pathlib import Path
import re
import sys
import time

import imageio_ffmpeg
import numpy as np
from PIL import Image


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode(path, expected, samples=False):
    frames = imageio_ffmpeg.read_frames(str(path), input_params=['-threads', '1'], output_params=['-threads', '1'])
    metadata = next(frames)
    assert tuple(metadata['size']) == (832, 480), metadata
    assert abs(metadata['fps'] - 16) < .001, metadata
    count, picked = 0, []
    for raw in frames:
        assert len(raw) == 832 * 480 * 3
        if samples and count in (0, 40, 80):
            picked.append(Image.frombytes('RGB', (832, 480), raw))
        count += 1
    assert count == expected, (path, count, expected)
    return dict(path=str(path), frames=count, size=[832, 480], fps=metadata['fps'], sha256=sha(path)), picked


def validate(attempt):
    started = time.monotonic()
    task = json.loads((attempt / 'input.json').read_text())
    assert sha(Path(task['script'])) == task['script_sha256']
    native = attempt / 'native'
    logs = [(attempt / f'{phase}.model.log').read_text() for phase in ['t2v', 'memory']]
    rows = re.findall(r'VIDEO_STATS path=(\S+) shape=\(([^)]+)\) finite=(True|False)', '\n'.join(logs))
    assert len(rows) == len(task['mapping'])
    for path, shape, finite in rows:
        assert finite == 'True' and tuple(int(x.strip()) for x in shape.split(',')) == (1, 3, 81, 480, 832)
        assert Path(path).parent == native
    memories = [json.loads(line.split('MEMORY ', 1)[1]) for line in logs[1].splitlines() if 'MEMORY ' in line]
    assert len(memories) == len(task['mapping']) - 1
    ordering = {m['storymem_output_name'][:-4]: i for i, m in enumerate(task['mapping'])}
    memory_audit = []
    for current_index, bank in enumerate(memories, 1):
        assert len(bank) <= 10
        checked = []
        for name in bank:
            path = Path(name)
            assert path.parent == native and path.is_file()
            match = re.fullmatch(r'(\d{2}_\d{2})_keyframe\d+\.jpg', path.name)
            assert match and ordering[match[1]] < current_index
            checked.append(dict(path=str(path), sha256=sha(path)))
        memory_audit.append(checked)
    outputs, contact_rows = [], []
    assert sorted(p.name for p in native.glob('[0-9][0-9]_[0-9][0-9].mp4')) == sorted(m['storymem_output_name'] for m in task['mapping'])
    for mapping in task['mapping']:
        record, pictures = decode(native / mapping['storymem_output_name'], 81, samples=True)
        record.update(shot_id=mapping['shot_id'], prompt_sha256=mapping['prompt_sha256'])
        outputs.append(record)
        contact_rows.append(pictures)
        alias = native / (mapping['shot_id'] + '.mp4')
        if not alias.exists():
            alias.symlink_to(mapping['storymem_output_name'])
    concatenated, _ = decode(native / 'native.mp4', 81 * len(outputs))
    alias = native / 'episode.mp4'
    if not alias.exists():
        alias.symlink_to('native.mp4')
    sheet = Image.new('RGB', (832 * 3, 480 * len(outputs)))
    for row, pictures in enumerate(contact_rows):
        for col, picture in enumerate(pictures):
            sheet.paste(picture, (832 * col, 480 * row))
    sheet.resize((1248, 240 * len(outputs))).save(native / 'contact.jpg')
    result = dict(status='pass', episode_id=task['episode_id'], script_sha256=task['script_sha256'],
        seed=task['seed'], shots=outputs, concatenated=concatenated, memory_inputs=memory_audit,
        memory_counts=[0] + list(map(len, memories)), seconds=time.monotonic() - started, completed=time.time())
    (native / 'episode.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    result = validate(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': 'pass', 'episode_id': result['episode_id'], 'shots': len(result['shots'])}))
