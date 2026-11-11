#!/usr/bin/env python3
"""Join the owner's verdicts (verdicts_raw/reviews/*.json, read 2026-11-10 with ArtifactData list from
https://claude.ai/artifact/Ws5aPmQegonTE3KLfrCuh7) with the audit trace (rerun v3 ledger / V-V outcome) and the
night-arm outcomes; writes verdicts_summary.json and prints the table used in README section 6.
Usage: summarize_verdicts.py [verdict dir] [output name]. First read (11:38 Dubai): verdicts_raw ->
verdicts_summary_first_read.json; second read after the owner watched three videos: verdicts_raw_2nd ->
verdicts_summary.json. INTERPRET records where Claude counts a finding from the owner's note rather than the buttons."""
import collections, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIAG = HERE.parent
NIGHT = {'036-A2': 'C, D confirmed (unspecified subject)', '055-A1': 'C, C2 confirmed (unspecified subject)',
         '078-A1': 'E2 found it, verdict uncertain'}
# Owner notes that override the buttons in the count (second read, 2026-11-10):
INTERPRET = {
    '036-A1': dict(real='no', basis='note: the full video shows the drone entering the view; only the keyframes make it '
                                    'look like a jump; keep as a special case, no pipeline change (button left at yes)'),
    '127-A1': dict(prompt='spec', basis='note: counts as an appearance inconsistency of the hand (the paw of contract '
                                        'character [0] White shaggy creature); question 2 left unanswered'),
}


def main():
    src = HERE / (sys.argv[1] if len(sys.argv) > 1 else 'verdicts_raw_2nd')
    name = sys.argv[2] if len(sys.argv) > 2 else 'verdicts_summary.json'
    summary = json.loads((DIAG / 'audit20_summary.json').read_text())
    rows = []
    for f in summary['primary']:
        fid = f"{f['task'].split('_')[1]}-{f['id']}"
        doc = json.loads((src / 'reviews' / f'{fid}.json').read_text())
        v = doc.get('data', doc)
        row = dict(fid=fid, task=f['task'], scope=f['scope'], auditor_sure=f['sure'], button_real=v.get('real'),
                   button_prompt=v.get('prompt'), real=v.get('real'), prompt=v.get('prompt'), note=v.get('note', ''),
                   ledger_status=f['ledger_status'], vv_outcome=f['vv_outcome'], night=NIGHT.get(fid, 'none'),
                   answered_at=v.get('updated'))
        if name == 'verdicts_summary.json' and fid in INTERPRET:
            row.update({k: x for k, x in INTERPRET[fid].items() if k != 'basis'}, interpretation=INTERPRET[fid]['basis'])
        rows.append(row)
    real = collections.Counter(r['real'] for r in rows)
    ru = [r for r in rows if r['real'] == 'yes' and r['prompt'] == 'unspec']
    out = dict(source=f'owner review page, 2026-11-10, {src.name}', n=len(rows), real=dict(real),
               real_and_specified=[r['fid'] for r in rows if r['real'] == 'yes' and r['prompt'] == 'spec'],
               real_and_unspecified=[r['fid'] for r in ru],
               real_unspecified_ledger=dict(collections.Counter(r['ledger_status'] for r in ru)),
               real_unspecified_vv_outcome=dict(collections.Counter(r['vv_outcome'] for r in ru)),
               real_unspecified_night=[(r['fid'], r['night']) for r in ru if r['night'] != 'none'],
               rows=rows)
    (HERE / name).write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
    for k in ('real', 'real_and_specified', 'real_and_unspecified', 'real_unspecified_ledger',
              'real_unspecified_vv_outcome', 'real_unspecified_night'):
        print(k, out[k])
    for r in rows:
        print(f"{r['fid']:7} {r['real'] or '-':6} {r['prompt'] or '-':7} {r['ledger_status']:34} {r['vv_outcome']:34} {r['night']}")


if __name__ == '__main__':
    main()
