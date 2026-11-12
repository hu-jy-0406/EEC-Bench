#!/usr/bin/env python3
"""Standalone API tokens and cost of C, C + plug-in, new and new + plug-in on the 1,000 first-200 videos, per model
(zero model calls). Same method as ../vl_vv_entity_scope_validation_20261111/cost_by_version.py (40 videos), extended
to all videos:
  C           ../vl_vv_full_first200_c_20261110/runs/<t>: discovery, boxchoice, case, results/, plus the first detection
              pass (clustering + prompt binding: v3 case entities/ and shot_prompt_recovery/) that the C run took from
              the v3 case instead of calling the model again; the C totals reported on 2026-11-11 left it out;
  C + plug    C without its own V-V review and scoring, plus branch/ (U1-U3) and results_with/ (merged V-V review,
              scoring with its own V-L severity call);
  new         case/ (incl. background frontend) and results/, plus billed cut-off replies that were resent; the 40
              reused validation videos from ../vl_vv_entity_scope_validation_20261111;
  new + plug  new without its V-V review and V-V scoring call, plus results_with/ (plug-in, merged V-V review, V-V
              scoring); new's V-L severity call (results/episode_scoring/call_vl), reused by the plug-in scoring, counts.
Standard estimate: GPT-6 Luna direct standard price (USD 0.10/M uncached input, 0.01/M cached, 0.50/M output), not a
bill. Billed: OpenRouter usage.cost_usd (new versions; C ran on direct OpenAI, whose bill is not available here; the four
new videos rerun through direct OpenAI have no bill either). Failed attempts are excluded (standalone cost of the
finished pipeline). Writes cost_four_versions.json."""
import collections
import json
import os
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent
VALID = EXP.parent / 'vl_vv_entity_scope_validation_20261111'
C = EXP.parent / 'vl_vv_full_first200_c_20261110'
V3 = EXP.parent / 'vl_vv_full_first200_v3_20261109'
sys.path.insert(0, str(VALID))
import cost_by_version as cbv  # noqa: E402

PRICE = cbv.PRICE
MODELS = ('cinetrans', 'holocine', 'storymem', 'wan21', 'wan22')


def staged(base, folders, cutoffs):
    out = collections.defaultdict(list)
    for name in folders:
        for c in cbv.calls_in(base / name, cutoffs=cutoffs):
            rel = str(Path(c['folder']).relative_to(base))
            stage = cbv.stage_of(rel)
            if stage == 'episode_scoring':
                stage = 'episode_scoring_vl' if '/call_vl' in rel else 'episode_scoring_vv'
            out[stage].append(c)
    return out


def pass1(case_dir):
    calls, seen = [], set()
    for top in ('entities', 'shot_prompt_recovery'):
        for dirpath, _, files in os.walk(Path(case_dir) / top, followlinks=True):
            if 'status.json' not in files:
                continue
            try:
                s = json.loads((Path(dirpath) / 'status.json').read_text())
            except ValueError:
                continue
            for index, u in enumerate(cbv.au.usage_rows(s)):
                k = u.get('api_response_id') or f'{dirpath}#{index}'
                if k not in seen:
                    seen.add(k)
                    calls.append(cbv.row(u))
    return calls


def totals(calls):
    t = dict(calls=len(calls), input=sum(c['input'] for c in calls), cached=sum(c['cached'] for c in calls),
             output=sum(c['output'] for c in calls))
    t['uncached'] = t['input'] - t['cached']
    t['standard_usd'] = round((t['uncached'] * PRICE[0] + t['cached'] * PRICE[1] + t['output'] * PRICE[2]) / 1e6, 4)
    billed = [c['billed'] for c in calls if c['billed'] is not None]
    t['billed_usd'] = round(sum(billed), 4)
    t['calls_without_bill'] = len(calls) - len(billed)
    return t


def main():
    v3 = {}
    for prog in (V3 / 'runs').glob('*/progress.json'):
        for tid, t in json.loads(prog.read_text())['tasks'].items():
            if t.get('status') == 'success':
                v3[tid] = t
    tasks = sorted(p.name for p in (EXP / 'runs').iterdir() if (p / 'stages' / 'with_episode_scoring.done').is_file())
    per = collections.defaultdict(list)
    base_stages = ('frontend', 'vl_detection', 'vl_review', 'vv_detection', 'vv_review', 'episode_scoring_vl',
                   'episode_scoring_vv')
    for t in tasks:
        model = t.split('__')[1]
        # C
        s = staged(C / 'runs' / t, ('discovery', 'boxchoice', 'case', 'results', 'branch', 'results_with'), False)
        p1 = pass1(v3[t]['case_dir'])
        c = sum((s[k] for k in base_stages), []) + p1
        cw = sum((s[k] for k in base_stages if k not in ('vv_review', 'episode_scoring_vv', 'episode_scoring_vl')), []) \
            + p1 + s['plugin_detection'] + s['plug_vv_review'] + s['plug_episode_scoring']
        # new
        here = EXP / 'runs' / t
        base = VALID / 'runs' / t if (here / 'reused_from.json').is_file() else here
        s = staged(base, ('case', 'results'), True)
        w = staged(base, ('results_with/vv_plugin', 'results_with/vv_review'), True)
        w2 = staged(here, ('results_with/episode_scoring',), True)
        n = sum((s[k] for k in base_stages), [])
        nw = sum((s[k] for k in base_stages if k not in ('vv_review', 'episode_scoring_vv')), []) \
            + w['plugin_detection'] + w['plug_vv_review'] + w2['plug_episode_scoring']
        for m in (model, 'all'):
            per[('c', m)] += c
            per[('c_plug', m)] += cw
            per[('new', m)] += n
            per[('new_plug', m)] += nw
            per[('c_pass1_from_v3', m)] += p1
    out = dict(videos=len(tasks), definitions=__doc__,
               totals={v: {m: totals(per[(v, m)]) for m in MODELS + ('all',)}
                       for v in ('c', 'c_plug', 'new', 'new_plug', 'c_pass1_from_v3')})
    (EXP / 'cost_four_versions.json').write_text(json.dumps(out, indent=1) + '\n')
    for v, rows in out['totals'].items():
        print(v, rows['all'])


if __name__ == '__main__':
    main()
