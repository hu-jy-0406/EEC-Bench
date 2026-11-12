#!/usr/bin/env python3
"""Watch the drivers' event logs (events/*.jsonl). Failures caused by OpenRouter's OpenAI input moderation ("requires
moderation", HTTP 403, not charged) are appended to moderation_blocked.json and do not end the watch; the watch exits,
printing what it found, at the first other failure or when a driver finishes. Zero model calls."""
import json
import subprocess
import sys
import time
from pathlib import Path

EXP = Path(__file__).resolve().parent
SEEN = set(sys.argv[1:])  # failures already handled


def events():
    rows = []
    for f in sorted((EXP / 'events').glob('*.jsonl')):
        for line in f.read_text(errors='replace').splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def moderation(task):
    out = subprocess.run(['grep', '-rl', '--include=stderr.log', 'requires moderation', str(EXP / 'runs' / task)],
                         capture_output=True, text=True).stdout.split()
    return out


def main():
    path = EXP / 'moderation_blocked.json'
    blocked = json.loads(path.read_text()) if path.is_file() else {}
    while True:
        rows = events()
        for e in rows:
            if e.get('event') == 'result' and e['result'] != 'success' and e['task'] not in SEEN:
                SEEN.add(e['task'])
                files = moderation(e['task'])
                if files:
                    blocked[e['task']] = dict(time=e['time'], result=e['result'], calls=files)
                    path.write_text(json.dumps(blocked, indent=1) + '\n')
                    continue
                print('other failure:', json.dumps(e))
                print('moderation blocked so far:', sorted(blocked))
                return
        if any(e.get('event') == 'driver_finished' for e in rows):
            print('a driver finished; moderation blocked:', sorted(blocked))
            return
        time.sleep(60)


if __name__ == '__main__':
    main()
