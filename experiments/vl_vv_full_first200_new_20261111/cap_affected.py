#!/usr/bin/env python3
"""Videos whose plug-in U1 was shaped by the removed 30-object cap (owner, 2026-11-11: "Remove the cap"): any U1 round
rejected with "objects: at most 30 entries", whether the shot then failed or passed with a shortened list. Their
plug-in, merged V-V review and plug-in scoring are rerun without the cap; the old results_with/ is kept as
results_with_cap30/. With --apply: move results_with/ aside, delete the three stage markers and the claim, so the next
driver takes the video (prepare and pipeline stay done). Zero model calls."""
import argparse
import json
import shutil
from pathlib import Path

EXP = Path(__file__).resolve().parent


def affected():
    out = {}
    for audit in EXP.glob('runs/*/results_with/vv_plugin/u1/*/call_repair_audit.json'):
        a = json.loads(audit.read_text())
        hits = sum(any('objects: at most 30' in e for e in r.get('errors', [])) for r in a.get('rounds', []))
        if hits:
            task = audit.parents[4].name
            out.setdefault(task, []).append(dict(shot=audit.parent.name, rounds_rejected=hits, status=a.get('status')))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    rows = affected()
    print(json.dumps(rows, indent=1))
    if a.apply:
        for task in rows:
            base = EXP / 'runs' / task
            if (base / 'results_with').exists():
                shutil.move(str(base / 'results_with'), str(base / 'results_with_cap30'))
            for name in ('plugin', 'with_vv_review', 'with_episode_scoring'):
                (base / 'stages' / f'{name}.done').unlink(missing_ok=True)
            (EXP / 'claims' / task).unlink(missing_ok=True)
        (EXP / 'cap_affected.json').write_text(json.dumps(rows, indent=1) + '\n')


if __name__ == '__main__':
    main()
