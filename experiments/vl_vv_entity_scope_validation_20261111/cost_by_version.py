#!/usr/bin/env python3
"""API tokens and cost of the five versions on the 40 validation videos, per stage (zero model calls).

Versions and where their calls are recorded:
  v3        ../vl_vv_full_first200_v3_20261109: every call of each video's case and outputs, including the first-run
            frontend and V-L branch that reuse-mode videos reused (deduplicated by response id, as in
            ../vl_vv_full_first200_c_20261110/cost_compare.py);
  C         ../vl_vv_full_first200_c_20261110/runs/<task>: discovery, boxchoice, case, results. That run took its first
            detection pass (clustering + prompt binding, whose entity lists discovery reads) from the v3 case instead
            of calling the model again; "standalone" C adds those v3 calls, "as run" does not;
  C + plug  C plus branch/ (U1-U3) and results_with/ (merged V-V review, scoring);
  new       runs/<task>/case (incl. background_frontend) and results/, plus billed cut-off replies that were resent;
  new+plug  new plus results_with/ (vv_plugin, merged V-V review, scoring).
Two totals for the plug-in versions: "as run" = base + plug-in (what this experiment spent; the base V-V review and
scoring were also run for the version without the plug-in), and "standalone" = as run minus the base V-V review and
base scoring, which the plug-in version does not use.
Standard estimate: GPT-6 Luna direct price (USD 0.10/M uncached input, 0.01/M cached, 0.50/M output), not a bill.
Billed: OpenRouter usage.cost_usd per call (new and new+plug only; v3 and C ran on direct OpenAI, whose bill is not
available here). WeDetect, Grounding DINO and DINO run on GPU and make no API call. Writes cost_by_version.json."""
import collections
import json
import os
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent
V3 = EXP.parent / 'vl_vv_full_first200_v3_20261109'
C = EXP.parent / 'vl_vv_full_first200_c_20261110'
sys.path.insert(0, str(V3))
import analyze_usage as au  # noqa: E402

PRICE = (0.10, 0.01, 0.50)


def row(u):
    return dict(input=int(u.get('input_tokens') or 0), cached=int(u.get('cached_input_tokens') or 0),
                output=int(u.get('output_tokens') or 0), billed=u.get('cost_usd'))


def calls_in(folder, cutoffs=False):
    out = []
    folder = Path(folder)
    if not folder.exists():
        return out
    for st in sorted(folder.rglob('status.json')):
        try:
            s = json.loads(st.read_text())
        except ValueError:
            continue
        out += [dict(row(u), folder=str(st.parent)) for u in au.usage_rows(s)]
    if cutoffs:
        for log in folder.rglob('events.jsonl.transport_failed*'):
            for line in log.read_text(errors='replace').splitlines():
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get('type') == 'response.incomplete' and e.get('usage'):
                    out.append(dict(row(e['usage']), folder=str(log.parent)))
    return out


def stage_of(rel):
    """Stage of a call folder, from its path relative to the video's run folder."""
    parts = rel.split('/')
    if parts[0] in ('case', 'discovery', 'boxchoice'):
        return 'frontend'
    if parts[0] == 'branch' or (parts[0] == 'results_with' and parts[1] == 'vv_plugin'):
        return 'plugin_detection'
    top = parts[1] if parts[0] in ('results', 'results_with') else parts[0]
    prefix = 'plug_' if parts[0] == 'results_with' else ''
    for name in ('vl_detection', 'vl_review', 'vv_detection', 'vv_review', 'episode_scoring'):
        if top == name:
            return prefix + name
    raise ValueError(rel)


def v3_calls(task):
    """Every call of a v3 video. Reuse-mode outputs link vl_detection/ and vl_review/ to the first run
    (vl_vv_full_first200_20261107) as symlinks, which Path.rglob does not enter, so the walk follows links.
    Deduplicated by response id; matching v2 usage from global_match_v2/audit.json when it has no call folders."""
    case, out = Path(task['case_dir']), Path(task['output_dir'])
    calls, seen = [], set()
    for root in (case, out):
        for dirpath, _, files in os.walk(root, followlinks=True):
            if 'status.json' not in files:
                continue
            try:
                s = json.loads((Path(dirpath) / 'status.json').read_text())
            except ValueError:
                continue
            rel = Path(dirpath).relative_to(root)
            stage = 'frontend' if root == case else stage_of('results/' + str(rel))
            for index, u in enumerate(au.usage_rows(s)):
                key = u.get('api_response_id') or f'{dirpath}#{index}'
                if key not in seen:
                    seen.add(key)
                    calls.append((stage, row(u), rel.parts[0] if rel.parts else ''))
    audit = case / 'global_match_v2/audit.json'
    if audit.is_file() and not any((case / 'global_match_v2').rglob('status.json')):
        calls += [('frontend', row(u), 'global_match_v2') for u in au.usage_rows(json.loads(audit.read_text()))]
    return calls


def totals(calls):
    t = dict(calls=len(calls), input=sum(c['input'] for c in calls), cached=sum(c['cached'] for c in calls),
             output=sum(c['output'] for c in calls))
    t['uncached'] = t['input'] - t['cached']
    t['standard_usd'] = round((t['uncached'] * PRICE[0] + t['cached'] * PRICE[1] + t['output'] * PRICE[2]) / 1e6, 4)
    billed = [c['billed'] for c in calls if c['billed'] is not None]
    t['billed_usd'] = round(sum(billed), 4) if billed and len(billed) == len(calls) else None
    t['calls_without_bill'] = len(calls) - len(billed)
    return t


def main():
    tasks = (V3 / 'sample_task_ids.txt').read_text().split()
    v3_tasks = {}
    for prog in (V3 / 'runs').glob('*/progress.json'):
        for tid, t in json.loads(prog.read_text())['tasks'].items():
            if t.get('status') == 'success':
                v3_tasks[tid] = t
    by = collections.defaultdict(list)  # (version, stage) -> calls
    for t in tasks:
        # v3: case -> frontend; outputs by top folder
        task = v3_tasks[t]
        for stage, c, top in v3_calls(task):
            by[('v3', stage)].append(c)
            if stage == 'frontend' and top in ('entities', 'shot_prompt_recovery'):
                by[('c', 'frontend_pass1_from_v3')].append(c)
        for version, base, folders, cut in (
                ('c', C / 'runs' / t, ('discovery', 'boxchoice', 'case', 'results', 'branch', 'results_with'), False),
                ('new', EXP / 'runs' / t, ('case', 'results', 'results_with'), True)):
            for name in folders:
                for c in calls_in(base / name, cutoffs=cut):
                    by[(version, stage_of(str(Path(c['folder']).relative_to(base))))].append(c)
    stages = ['frontend_pass1_from_v3', 'frontend', 'vl_detection', 'vl_review', 'vv_detection', 'vv_review', 'episode_scoring',
              'plugin_detection', 'plug_vv_review', 'plug_episode_scoring']
    base_stages = stages[1:7]
    plug_only = stages[7:]
    out = dict(videos=len(tasks), basis=dict(
        standard='GPT-6 Luna direct standard price: USD 0.10/M uncached input, 0.01/M cached input, 0.50/M output; '
                 'cached input is a subset of input; not a bill',
        billed='OpenRouter usage.cost_usd per call (new versions only)'),
        by_stage={v: {s: totals(by[(v, s)]) for s in stages if by[(v, s)]} for v in ('v3', 'c', 'new')}, versions={})
    for v in ('v3', 'c', 'new'):
        base = sum((by[(v, s)] for s in base_stages), [])
        pass1 = by[(v, 'frontend_pass1_from_v3')]
        out['versions'][v + ('_as_run' if pass1 else '')] = totals(base)
        if pass1:
            out['versions'][v + '_standalone'] = totals(base + pass1)
        if v != 'v3':
            plug = sum((by[(v, s)] for s in plug_only), [])
            out['versions'][v + '_plug_as_run'] = totals(base + plug)
            out['versions'][v + '_plug_standalone'] = totals(
                sum((by[(v, s)] for s in base_stages if s not in ('vv_review', 'episode_scoring')), []) + pass1 + plug)
    (EXP / 'cost_by_version.json').write_text(json.dumps(out, indent=1) + '\n')
    for k, v in out['versions'].items():
        print(f"{k:22s} calls {v['calls']:5d} in {v['input']:11,d} cached {v['cached']:11,d} out {v['output']:10,d}"
              f"  std ${v['standard_usd']:.4f}  billed {v['billed_usd']}  nobill {v['calls_without_bill']}")
    for v, rows in out['by_stage'].items():
        print('--', v)
        for s, r in rows.items():
            print(f"   {s:22s} calls {r['calls']:5d}  std ${r['standard_usd']:.4f}  billed {r['billed_usd']}")


if __name__ == '__main__':
    main()
